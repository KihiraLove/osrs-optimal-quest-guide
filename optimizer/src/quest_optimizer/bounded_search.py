"""Bounded, replay-verified search for larger quest profiles."""

from bisect import bisect_right
from collections import Counter, defaultdict
from dataclasses import dataclass
from fractions import Fraction
from heapq import heappop, heappush
from itertools import product
from math import inf
from random import Random

from .errors import DataError
from .objectives import counted_training, outstanding, priority_xp
from .reachability import unreachable_records
from .replay import verify_solution
from .search import (
    _leaves, _reward_skills, _reward_steps, _state_key, _training_step, _transition_key, _transition_step, build_solution,
)
from .semantics import CatalogValidator
from .transitions import RouteState


def _mandatory_rules(rule):
    if rule["kind"] == "all":
        for child in rule["requirements"]:
            yield from _mandatory_rules(child)
    elif rule["kind"] != "any":
        yield rule


def _step_key(step, tables):
    kind = step["kind"]
    if kind == "training":
        return (step["skill_id"], kind, step["after_xp_tenths"])
    if kind == "reward_use":
        return (step["instance_id"], kind, step["skill_id"])
    if kind == "wait":
        return (kind, kind, step["modeled_seconds"])
    table, field = ("actions", "action_id") if kind == "action" else ("travel_edges", "edge_id")
    return _transition_key(kind, tables[table][step[field]])


def _wait(seconds):
    return {"kind": "wait", "modeled_seconds": seconds, "explanation": "Wait for a route requirement."}


def _combat_repairs(state, rule):
    formula = state.tables["combat_formulas"][rule["formula_id"]]
    target = rule["minimum_level"] * formula["divisor"]
    for style in formula["styles"]:
        terms = defaultdict(list)
        for term in (*formula["base_terms"], *style):
            terms[term["skill_id"]].append(term)

        def points(skill, level):
            return sum(
                term["weight"] * (level * term["level_multiplier"] // term["level_divisor"])
                for term in terms[skill]
            )

        levels = {skill: state.level(skill) for skill in terms}
        missing = target - sum(points(skill, level) for skill, level in levels.items())
        training = {}
        while missing > 0:
            choices = []
            for skill, level in levels.items():
                current = points(skill, level)
                for next_level in range(level + 1, len(state.thresholds[skill]) + 1):
                    gain = points(skill, next_level) - current
                    if gain > 0:
                        xp = state.thresholds[skill][next_level - 1]
                        cost = xp - training.get(skill, state.xp[skill])
                        choices.append((Fraction(cost, min(gain, missing)), cost, skill, next_level, gain, xp))
            if not choices:
                break
            _, _, skill, level, gain, xp = min(choices)
            levels[skill], training[skill] = level, xp
            missing -= gain
        if missing <= 0:
            yield tuple(sorted(training.items())), 0


def _repairs(state, rule, width):
    """Propose exact XP targets and a wait for a currently blocked transition."""
    if state._progress_gates_met(rule):
        return [((), 0)]
    kind = rule["kind"]
    if kind == "skill":
        skill = rule["skill_id"]
        bonus = state.boosts.get(skill, {}).get("bonus_levels", 0) if rule["boostable"] else 0
        xp = state.thresholds[skill][max(1, rule["minimum_level"] - bonus) - 1]
        return [(((skill, xp),), 0)]
    if kind == "elapsed_time":
        return [((), rule["minimum_seconds"] - state.elapsed)]
    if kind == "cooldown_ready":
        return [((), state.cooldowns[rule["token_id"]] - state.elapsed)]
    if kind == "combat_level":
        candidates = _combat_repairs(state, rule)
    elif kind == "any":
        candidates = (repair for child in rule["requirements"] for repair in _repairs(state, child, width))
    elif kind == "all":
        combined = [((), 0)]
        for child in rule["requirements"]:
            additions = _repairs(state, child, width)
            merged = []
            for (left, left_wait), (right, right_wait) in product(combined, additions):
                targets = dict(left)
                for skill, xp in right:
                    targets[skill] = max(xp, targets.get(skill, 0))
                merged.append((tuple(sorted(targets.items())), max(left_wait, right_wait)))
            combined = _cheapest_repairs(state, merged, width)
            if not combined:
                break
        return combined
    else:
        return []
    return _cheapest_repairs(state, candidates, width)


def _cheapest_repairs(state, repairs, width):
    return sorted(set(repairs), key=lambda row: (
        sum(xp - state.xp[skill] for skill, xp in row[0]), row[1], row[0],
    ))[:width]


def _reward_targets(state, reward, skill, xp):
    thresholds = state.thresholds[skill]
    minimum = reward["minimum_level"]
    if minimum > len(thresholds):
        return []
    eligible = thresholds[minimum - 1]
    candidates = [eligible] if eligible > xp else []
    if reward["amount"]["kind"] == "by_level":
        amounts = state.amounts_by_level[reward["id"]]
        current = max(bisect_right(thresholds, xp), minimum)
        best = max(range(current, len(thresholds) + 1), key=lambda level: (
            amounts[level] - max(0, thresholds[level - 1] - xp), -level,
        ))
        if thresholds[best - 1] > xp:
            candidates.append(thresholds[best - 1])
    return sorted(set(candidates))


def _apply_steps(state, steps):
    try:
        for step in steps:
            state = state.apply(step)
    except DataError:
        return None
    return state


def _producer_training(state, record):
    # Training before a producer can make an immediate pick eligible or
    # improve its award. Subtract XP delivered in the producer itself.
    grants = Counter()
    for effect in record["effects"]:
        if effect["kind"] == "xp":
            grants[effect["skill_id"]] += effect["xp_tenths"]
    for effect in record["effects"]:
        if effect["kind"] != "xp_reward":
            continue
        reward = state.rewards[effect["reward_id"]]
        if reward["retainable"]:
            continue
        for skill in sorted(_reward_skills(reward, state)):
            for target in _reward_targets(state, reward, skill, state.xp[skill] + grants[skill]):
                yield _training_step(state, skill, target - grants[skill], [reward["id"]])


def _moves(state, nearby, repair_width, skill_targets):
    for _, pick in _reward_steps(state):
        yield (pick,)
    if state.pending:
        return
    for skill, target in sorted(outstanding(state.xp, skill_targets).items()):
        yield (_training_step(state, skill, target, [skill]),)
    for _, instance in sorted(state.held.items()):
        reward = state.rewards[instance.reward_id]
        for skill in sorted(set(_reward_skills(reward, state)) - instance.used_skills):
            for target in _reward_targets(state, reward, skill, state.xp[skill]):
                yield (_training_step(state, skill, target, [reward["id"]]),)
    for kind, record in nearby:
        record_id = record["id"]
        counts = state.action_counts if kind == "action" else state.travel_counts
        if counts[record_id] >= record.get("repeat_limit", inf):
            continue
        if any(state.inventory[item["item_id"]] < item["quantity"] for item in record["consumes"]):
            continue
        for targets, seconds in _repairs(state, record["requirements"], repair_width):
            training = tuple(_training_step(state, skill, xp, [record_id]) for skill, xp in targets)
            wait = (_wait(seconds),) if seconds else ()
            if wait:
                yield wait
            yield (*training, *wait, _transition_step(kind, record))
            if any(effect["kind"] == "xp_reward" for effect in record["effects"]):
                repaired = _apply_steps(state, (*training, *wait))
                if repaired is not None:
                    for extra in _producer_training(repaired, record):
                        yield (*training, *wait, extra)


def _distances(destination, incoming):
    distances = {destination: 0}
    queue = [(0, destination)]
    while queue:
        cost, location = heappop(queue)
        if cost != distances[location]:
            continue
        for start, seconds in incoming[location]:
            if cost + seconds < distances.get(start, inf):
                distances[start] = cost + seconds
                heappush(queue, (cost + seconds, start))
    return distances


def _unique_action_producers(tables):
    # A travel effect is an alternative source, even though the guide only
    # follows mandatory dependencies through actions.
    producers = defaultdict(set)
    for table in ("actions", "travel_edges"):
        for record_id, record in tables[table].items():
            for effect in record["effects"]:
                if effect["kind"] == "item":
                    producers["item", effect["item_id"]].add(record_id)
                elif effect["kind"] == "flag" and effect["value"]:
                    producers["flag", effect["token_id"]].add(record_id)
    return {
        key: record_id for key, ids in producers.items() if len(ids) == 1
        for record_id in ids if record_id in tables["actions"]
    }


def _required_actions(initial, goals, producers):
    needed = {}
    remaining = list(goals)
    while remaining:
        action_id = remaining.pop()
        if action_id in needed or action_id in initial.completed:
            continue
        record = initial.tables["actions"][action_id]
        rules = list(_mandatory_rules(record["requirements"]))
        remaining.extend(rule["action_id"] for rule in rules if rule["kind"] == "action_completed")
        for rule in rules:
            if rule["kind"] == "flag" and rule["value"] and not initial.flags.get(rule["token_id"]):
                producer = producers.get(("flag", rule["token_id"]))
                if producer is not None:
                    remaining.append(producer)
        for item in record["consumes"] + [rule for rule in rules if rule["kind"] == "item"]:
            item_id = item["item_id"]
            if initial.inventory[item_id] + initial.bank_inventory[item_id] < item["quantity"]:
                producer = producers.get(("item", item_id))
                if producer is not None:
                    remaining.append(producer)
        needed[action_id] = rules
    return needed


class _Guide:
    def __init__(self, initial, goals, excluded, priorities, skill_targets):
        actions = initial.tables["actions"]
        producers = _unique_action_producers(initial.tables)
        self.needed = _required_actions(initial, goals, producers)
        self.prioritized = set(_required_actions(initial, priorities, producers))
        self.skill_targets = skill_targets
        self.required_items = {}
        for action_id, rules in self.needed.items():
            item_rules = [rule for rule in rules if rule["kind"] == "item"]
            items = {}
            for item in actions[action_id]["consumes"] + item_rules:
                item_id = item["item_id"]
                items[item_id] = max(items.get(item_id, 0), item["quantity"])
            self.required_items[action_id] = items

        self.routes = defaultdict(list)
        item_sources = defaultdict(list)
        route_items = {item for items in self.required_items.values() for item in items}
        incoming = defaultdict(list)
        self.grants = {}
        self.reward_grants = {}
        for reward_id, reward in initial.rewards.items():
            amount = reward["amount"]
            maximum = amount["xp_tenths"] if amount["kind"] == "fixed" else max(
                row["xp_tenths"] for row in amount["values"]
            )
            self.reward_grants[reward_id] = dict.fromkeys(_reward_skills(reward, initial), maximum)
        for kind, records in (("action", actions), ("travel", initial.tables["travel_edges"])):
            for record_id, record in sorted(records.items()):
                if kind == "action" and record_id in excluded:
                    continue
                start = record["start_location_id"] if kind == "action" else record["from_location_id"]
                end = record["end_location_id"] if kind == "action" else record["to_location_id"]
                self.routes[start].append((kind, record))
                if start != end:
                    incoming[end].append((start, record["duration"]["expected_seconds"]))
                grants = Counter()
                for effect in record["effects"]:
                    if effect["kind"] == "item" and effect["item_id"] in route_items:
                        item_sources[effect["item_id"]].append((start, kind, record_id, record.get("repeat_limit", inf)))
                    if effect["kind"] == "xp":
                        grants[effect["skill_id"]] += effect["xp_tenths"]
                    if effect["kind"] == "xp_reward":
                        reward_id = effect["reward_id"]
                        picks = effect["quantity"] * initial.rewards[reward_id]["selection_count"]
                        for skill, xp in self.reward_grants[reward_id].items():
                            grants[skill] += picks * xp
                if grants:
                    self.grants[record_id] = grants
        self.starts = {action_id: actions[action_id]["start_location_id"] for action_id in self.needed}
        self.item_sources = item_sources
        destinations = set(self.starts.values())
        destinations.update(source[0] for sources in item_sources.values() for source in sources)
        self.distances = {start: _distances(start, incoming) for start in sorted(destinations)}
        self.maximum_time = max((
            rule["minimum_seconds"] for transitions in self.routes.values() for _, record in transitions
            for rule in _leaves(record["requirements"]) if rule["kind"] == "elapsed_time"
        ), default=0)

    def estimates(self, state):
        missing = self.needed.keys() - state.completed
        thresholds = {}
        item_gaps = {}
        destinations = set()
        priority_destinations = set()
        for action_id in missing:
            rules = self.needed[action_id]
            for rule in rules:
                if rule["kind"] == "skill" and not rule["boostable"]:
                    skill = rule["skill_id"]
                    required = state.thresholds[skill][rule["minimum_level"] - 1]
                    thresholds[skill] = max(required, thresholds.get(skill, 0))
            lacking = {
                item: quantity - state.inventory[item]
                for item, quantity in self.required_items[action_id].items() if state.inventory[item] < quantity
            }
            for item, deficit in lacking.items():
                item_gaps[item] = max(item_gaps.get(item, 0), deficit)
            if any(rule["kind"] == "action_completed" and rule["action_id"] not in state.completed for rule in rules):
                continue
            targets = set()
            if lacking:
                for item in lacking:
                    for start, kind, record_id, limit in self.item_sources[item]:
                        counts = state.action_counts if kind == "action" else state.travel_counts
                        if counts[record_id] < limit:
                            targets.add(start)
            else:
                targets.add(self.starts[action_id])
            destinations.update(targets)
            if action_id in self.prioritized:
                priority_destinations.update(targets)
        gaps = {skill: max(0, xp - state.xp[skill]) for skill, xp in thresholds.items()}
        # Credit all remaining awards, with every selectable pick credited to
        # every eligible skill. Ignoring timing and exclusive choices keeps
        # this a lower bound even when the credits cannot all be realised.
        available = Counter()
        for record_id in self.grants.keys() - state.used_transitions:
            available.update(self.grants[record_id])
        for reward in state.held.values():
            for skill, amount in self.reward_grants[reward.reward_id].items():
                available[skill] += reward.remaining_picks * amount
        bound = sum(
            max(0, gap - available[skill] - max(0, self.skill_targets.get(skill, 0) - state.xp[skill]))
            for skill, gap in gaps.items()
        )
        def distance(destinations, remaining):
            return min((self.distances[start].get(state.location, inf) for start in destinations),
                       default=inf if remaining else 0)

        priority_remaining = len(missing & self.prioritized)
        return (bound, len(missing), sum(gaps.values()), sum(item_gaps.values()), distance(destinations, missing),
                priority_remaining, distance(priority_destinations, priority_remaining))


@dataclass
class _Node:
    state: RouteState
    steps: tuple
    cost: tuple


def _train_during_waits(initial, steps, skill_targets):
    """Move planned XP into an idle interval when same-skill XP is unchanged."""
    state = initial
    waits = {}
    emitted = []
    before_wait = defaultdict(list)
    for step in steps:
        kind = step["kind"]
        if kind == "wait":
            for skill in state.xp:
                waits.setdefault(skill, (len(emitted), state.location))
        elif kind == "training":
            skill = step["skill_id"]
            if skill not in skill_targets and skill in waits:
                index, waypoint = waits.pop(skill)
                before_wait[index].append({
                    **step, "resume_location_id": waypoint,
                    "explanation": f"Work on the {step['gain_xp_tenths']} XP tenths target during this wait.",
                })
                state = state.apply(step)
                continue
            waits.pop(skill, None)
        elif kind == "reward_use":
            waits.pop(step["skill_id"], None)
        elif kind in ("action", "travel"):
            table, field = ("actions", "action_id") if kind == "action" else ("travel_edges", "edge_id")
            for effect in state.tables[table][step[field]]["effects"]:
                if effect["kind"] == "xp":
                    waits.pop(effect["skill_id"], None)
        emitted.append(step)
        state = state.apply(step)
    return tuple(part for index, step in enumerate(emitted) for part in (*before_wait[index], step))


def solve_bounded(
    validator: CatalogValidator, profile: dict, *, beam_width: int = 32, max_expansions: int = 20_000,
    seed: int = 0, excluded_actions: tuple[str, ...] = (), incumbent: dict | None = None,
) -> tuple[dict, dict]:
    """Return a replay-verified route and deterministic search counters."""
    if beam_width < 1 or max_expansions < 1 or seed < 0:
        raise DataError("beam width and max expansions must be positive and seed must be nonnegative")
    validator.contracts.validate("profile", profile)
    validator.validate_profile(profile)
    priorities = set(profile.get("priority_action_ids", ()))
    skill_targets = priority_xp(profile, validator.tables["skills"])
    goals = set(profile["goal_action_ids"]) | priorities
    excluded = set(excluded_actions)
    if excluded - validator.tables["actions"].keys():
        raise DataError("Unknown excluded action: " + ", ".join(sorted(excluded - validator.tables["actions"].keys())))
    initial = RouteState(validator.tables, profile["policies"], profile["initial_state"])
    guide = _Guide(initial, goals, excluded, priorities, skill_targets)

    def complete(state):
        return goals <= state.completed and not state.pending and not outstanding(state.xp, skill_targets)

    def step_keys(steps):
        return tuple(_step_key(step, initial.tables) for step in steps)
    if excluded & guide.needed.keys():
        raise DataError("Cannot exclude a required action: " + ", ".join(sorted(excluded & guide.needed.keys())))
    allowed = {**validator.catalog, "actions": [
        record for record in validator.catalog["actions"] if record["id"] not in excluded
    ]}
    unreachable = goals.intersection(unreachable_records(allowed, profile)["actions"])
    if unreachable:
        raise DataError("Catalog reachability blocks goals: " + ", ".join(sorted(unreachable)))
    initial_bound = guide.estimates(initial)[0]
    rng = Random(seed)
    best = None
    if incumbent is not None:
        verify_solution(incumbent, profile, validator)
        steps = tuple({key: value for key, value in step.items() if key != "step_id"} for step in incumbent["steps"])
        if any(step.get("action_id") in excluded for step in steps):
            raise DataError("Incumbent uses an excluded action")
        objective = incumbent["objective"]
        best = _Node(_apply_steps(initial, steps), steps, (
            objective.get("counted_manual_training_xp_tenths", objective["manual_training_xp_tenths"]),
            objective.get("priority_skill_elapsed_seconds", 0), objective.get("priority_elapsed_seconds", 0),
            objective["modeled_non_training_seconds"],
            step_keys(steps),
        ))

    frontier = [_Node(initial, (), (0, 0, 0, 0, ()))]
    expanded = {}
    expansion_count = 0
    generated = 0
    while frontier and expansion_count < max_expansions:
        candidates = {}
        for node in frontier:
            if complete(node.state):
                if best is None or node.cost < best.cost:
                    best = node
                continue
            key = _state_key(node.state, guide.maximum_time, "")
            if expanded.get(key, (inf,)) <= node.cost:
                continue
            expanded[key] = node.cost
            expansion_count += 1
            for moves in _moves(node.state, guide.routes[node.state.location], min(beam_width, 8), skill_targets):
                state = _apply_steps(node.state, moves)
                if state is None:
                    continue
                generated += 1
                manual = node.cost[0] + sum(counted_training(move, skill_targets) for move in moves)
                seconds = state.elapsed - initial.elapsed
                skill_seconds = node.cost[1]
                priority_seconds = node.cost[2]
                before = dict(outstanding(node.state.xp, skill_targets))
                for move in moves:
                    if move["kind"] == "training" and move["after_xp_tenths"] >= before.get(move["skill_id"], 0):
                        before.pop(move["skill_id"], None)
                    if before:
                        skill_seconds += move.get("modeled_seconds", 0)
                if priorities - node.state.completed:
                    priority_seconds += state.elapsed - node.state.elapsed
                objective = manual, skill_seconds, priority_seconds, seconds
                if best is not None and objective > best.cost[:4]:
                    continue
                cost = (*objective, node.cost[4] + step_keys(moves))
                successor = _Node(state, node.steps + moves, cost)
                if complete(state):
                    if best is None or cost < best.cost:
                        best = successor
                    continue
                successor_key = _state_key(state, guide.maximum_time, "")
                if expanded.get(successor_key, (inf,)) <= cost:
                    continue
                previous = candidates.get(successor_key)
                if previous is None or cost < previous.cost:
                    candidates[successor_key] = successor
            if expansion_count >= max_expansions:
                break

        ranked = []
        for candidate in candidates.values():
            bound, remaining, deficit, item_gap, distance, priority_remaining, priority_distance = guide.estimates(
                candidate.state,
            )
            manual, skill_seconds, priority_seconds, seconds, ids = candidate.cost
            if best is not None and (manual + bound, skill_seconds, priority_seconds, seconds) > best.cost[:4]:
                continue
            rank = (manual + bound, skill_seconds, len(outstanding(candidate.state.xp, skill_targets)),
                    priority_remaining, priority_seconds + priority_distance,
                    remaining, deficit, item_gap, seconds + distance, rng.getrandbits(64), ids)
            ranked.append((rank, candidate))
        ranked.sort(key=lambda row: row[0])
        frontier = [candidate for _, candidate in ranked[:beam_width]]

    if best is None:
        raise DataError(f"Bounded search found no complete route after expanding {expansion_count} states")
    limitations = [
        f"Bounded beam search with width {beam_width}, {max_expansions} allowed expansions and seed {seed}.",
        "The reported lower bound relaxes award ordering, prerequisites and mutually exclusive reward picks.",
    ]
    if excluded:
        limitations.append("Comparison excludes actions: " + ", ".join(sorted(excluded)))
    steps = _train_during_waits(initial, best.steps, skill_targets)
    solution = build_solution(
        validator, profile, best.state, steps,
        solution_id="solution.bounded." + profile["profile_id"],
        solver={
            "name": "bounded-beam", "seed": seed, "status": "feasible" if excluded else "best_known",
            "primary_lower_bound_xp_tenths": initial_bound, "secondary_lower_bound_seconds": None,
        },
        priority_seconds=best.cost[2], priority_skill_seconds=best.cost[1],
        limitations=limitations,
    )
    return solution, {
        "beam_width": beam_width, "max_expansions": max_expansions, "seed": seed,
        "excluded_actions": sorted(excluded), "states_expanded": expansion_count, "successors_generated": generated,
        "termination": "expansion_budget" if expansion_count >= max_expansions else "frontier_empty",
    }
