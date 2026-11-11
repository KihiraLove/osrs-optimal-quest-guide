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
from .reachability import unreachable_records
from .replay import verify_solution
from .search import _leaves, _reward_skills, _reward_steps, _state_key, _training_step, _transition_step, build_solution
from .semantics import CatalogValidator
from .transitions import RouteState


def _mandatory_rules(rule):
    if rule["kind"] == "all":
        for child in rule["requirements"]:
            yield from _mandatory_rules(child)
    elif rule["kind"] != "any":
        yield rule


def _step_key(step):
    kind = step["kind"]
    if kind == "training":
        return (step["skill_id"], kind, step["after_xp_tenths"])
    if kind == "reward_use":
        return (step["instance_id"], kind, step["skill_id"])
    if kind == "wait":
        return (kind, kind, step["modeled_seconds"])
    return (step.get("action_id") or step["edge_id"], kind)


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


def _moves(state, nearby, repair_width):
    for _, pick in _reward_steps(state):
        yield (pick,)
    if state.pending:
        return
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


class _Guide:
    def __init__(self, initial, goals, excluded):
        actions = initial.tables["actions"]
        self.needed = {}
        remaining = list(goals)
        while remaining:
            action_id = remaining.pop()
            if action_id in self.needed or action_id in initial.completed:
                continue
            rules = list(_mandatory_rules(actions[action_id]["requirements"]))
            remaining.extend(rule["action_id"] for rule in rules if rule["kind"] == "action_completed")
            self.needed[action_id] = rules

        self.routes = defaultdict(list)
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
        self.distances = {start: _distances(start, incoming) for start in sorted(set(self.starts.values()))}
        self.maximum_time = max((
            rule["minimum_seconds"] for transitions in self.routes.values() for _, record in transitions
            for rule in _leaves(record["requirements"]) if rule["kind"] == "elapsed_time"
        ), default=0)

    def estimates(self, state):
        missing = self.needed.keys() - state.completed
        thresholds = {}
        for action_id in missing:
            for rule in self.needed[action_id]:
                if rule["kind"] == "skill" and not rule["boostable"]:
                    skill = rule["skill_id"]
                    required = state.thresholds[skill][rule["minimum_level"] - 1]
                    thresholds[skill] = max(required, thresholds.get(skill, 0))
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
        bound = sum(max(0, gap - available[skill]) for skill, gap in gaps.items())
        ready = [
            action_id for action_id in missing if all(
                rule["kind"] != "action_completed" or rule["action_id"] in state.completed
                for rule in self.needed[action_id]
            )
        ]
        distance = min((
            self.distances[self.starts[action_id]].get(state.location, inf) for action_id in ready
        ), default=0)
        return bound, len(missing), sum(gaps.values()), distance


@dataclass
class _Node:
    state: RouteState
    steps: tuple
    cost: tuple


def solve_bounded(
    validator: CatalogValidator, profile: dict, *, beam_width: int = 32, max_expansions: int = 20_000,
    seed: int = 0, excluded_actions: tuple[str, ...] = (), incumbent: dict | None = None,
) -> tuple[dict, dict]:
    """Return a replay-verified route and deterministic search counters."""
    if beam_width < 1 or max_expansions < 1 or seed < 0:
        raise DataError("beam width and max expansions must be positive and seed must be nonnegative")
    validator.contracts.validate("profile", profile)
    validator.validate_profile(profile)
    goals = set(profile["goal_action_ids"])
    excluded = set(excluded_actions)
    if excluded - validator.tables["actions"].keys():
        raise DataError("Unknown excluded action: " + ", ".join(sorted(excluded - validator.tables["actions"].keys())))
    initial = RouteState(validator.tables, profile["policies"], profile["initial_state"])
    guide = _Guide(initial, goals, excluded)
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
            objective["manual_training_xp_tenths"], objective["modeled_non_training_seconds"],
            tuple(map(_step_key, steps)),
        ))

    frontier = [_Node(initial, (), (0, 0, ()))]
    expanded = {}
    expansion_count = 0
    generated = 0
    while frontier and expansion_count < max_expansions:
        candidates = {}
        for node in frontier:
            if goals <= node.state.completed and not node.state.pending:
                if best is None or node.cost < best.cost:
                    best = node
                continue
            key = _state_key(node.state, guide.maximum_time, "")
            if expanded.get(key, (inf,)) <= node.cost:
                continue
            expanded[key] = node.cost
            expansion_count += 1
            for moves in _moves(node.state, guide.routes[node.state.location], min(beam_width, 8)):
                state = _apply_steps(node.state, moves)
                if state is None:
                    continue
                generated += 1
                manual = node.cost[0] + sum(move["gain_xp_tenths"] for move in moves if move["kind"] == "training")
                seconds = state.elapsed - initial.elapsed
                if best is not None and (manual, seconds) > best.cost[:2]:
                    continue
                cost = manual, seconds, node.cost[2] + tuple(map(_step_key, moves))
                successor = _Node(state, node.steps + moves, cost)
                if goals <= state.completed and not state.pending:
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
            bound, remaining, deficit, distance = guide.estimates(candidate.state)
            manual, seconds, ids = candidate.cost
            if best is not None and (manual + bound, seconds) > best.cost[:2]:
                continue
            ranked.append(((manual + bound, remaining, deficit, seconds + distance, rng.getrandbits(64), ids), candidate))
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
    solution = build_solution(
        validator, profile, best.state, best.steps,
        solution_id="solution.bounded." + profile["profile_id"],
        solver={
            "name": "bounded-beam", "seed": seed, "status": "feasible" if excluded else "best_known",
            "primary_lower_bound_xp_tenths": initial_bound, "secondary_lower_bound_seconds": None,
        },
        limitations=limitations,
    )
    return solution, {
        "beam_width": beam_width, "max_expansions": max_expansions, "seed": seed,
        "excluded_actions": sorted(excluded), "states_expanded": expansion_count, "successors_generated": generated,
        "termination": "expansion_budget" if expansion_count >= max_expansions else "frontier_empty",
    }
