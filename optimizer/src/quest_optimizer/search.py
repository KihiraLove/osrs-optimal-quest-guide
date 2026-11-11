"""Exhaustive lexicographic reference search for small, finite catalogs."""

from collections import Counter, defaultdict
from heapq import heappop, heappush
from itertools import chain, count

from . import __version__
from .errors import DataError
from .replay import input_identity, verify_solution
from .semantics import CatalogValidator
from .transitions import RouteState


def _leaves(rule):
    if rule["kind"] in ("all", "any"):
        for child in rule["requirements"]:
            yield from _leaves(child)
    else:
        yield rule


def _check_finite(tables: dict) -> None:
    for edge in tables["travel_edges"].values():
        if "repeat_limit" in edge:
            continue
        if edge["duration"]["expected_seconds"] == 0:
            raise DataError(f"{edge['id']}: exact search requires a limit on zero-time travel")
        for effect in edge["effects"]:
            if effect["kind"] == "item" or (
                effect["kind"] == "counter" and effect["delta"] > 0
                and tables["tokens"][effect["token_id"]]["maximum"] is None
            ):
                raise DataError(f"{edge['id']}: exact search requires a bound on repeatable resource gains")


def _reward_skills(reward: dict, state: RouteState):
    if reward["eligible_skills"] == "all" or (
        reward["kind"] == "quest_lamp" and state.policies["quest_lamp_skill_policy"] == "any_skill"
    ):
        return state.xp
    return reward["eligible_skills"]


def _training_targets(state: RouteState) -> tuple[dict, int]:
    points = defaultdict(set)
    reasons = defaultdict(set)
    maximum_time = 0
    boosts = defaultdict(set)
    for skill_id, boost in state.boosts.items():
        boosts[skill_id].add(boost["bonus_levels"])
    records = [*state.tables["actions"].values(), *state.tables["travel_edges"].values()]
    for record in records:
        for effect in record["effects"]:
            if effect["kind"] == "skill_boost" and state.policies["allow_boosts"]:
                boosts[effect["skill_id"]].add(effect["bonus_levels"])
    for record in records:
        for rule in _leaves(record["requirements"]):
            kind = rule["kind"]
            if kind == "skill":
                skill = rule["skill_id"]
                level = rule["minimum_level"]
                table = state.thresholds[skill]
                points[skill].add(table[level - 1])
                if rule["boostable"]:
                    points[skill].update(table[max(1, level - bonus) - 1] for bonus in boosts[skill])
                reasons[skill].add(record["id"])
            elif kind == "combat_level":
                formula = state.tables["combat_formulas"][rule["formula_id"]]
                for terms in (formula["base_terms"], *formula["styles"]):
                    for term in terms:
                        skill = term["skill_id"]
                        points[skill].update(state.thresholds[skill])
                        reasons[skill].add(record["id"])
            elif kind == "elapsed_time":
                maximum_time = max(maximum_time, rule["minimum_seconds"])
    for reward in state.rewards.values():
        for skill in _reward_skills(reward, state):
            minimum = reward["minimum_level"]
            table = state.thresholds[skill]
            if minimum > len(table):
                continue
            points[skill].add(table[minimum - 1])
            if reward["amount"]["kind"] == "by_level":
                points[skill].update(table[minimum - 1:])
            reasons[skill].add(reward["id"])
    return {
        skill: (tuple(sorted(values)), sorted(reasons[skill]))
        for skill, values in points.items() if max(values) > 0
    }, maximum_time


def _state_key(state: RouteState, maximum_time: int, last_training_skill: str) -> tuple:
    def pairs(values):
        return tuple(sorted((key, value) for key, value in values.items() if value))

    return (
        state.location, min(state.elapsed, maximum_time), last_training_skill,
        pairs(state.xp), pairs(state.inventory), pairs(state.counters), pairs(state.flags), pairs(state.choices),
        pairs(state.action_counts), pairs(state.travel_counts), frozenset(state.issued),
        frozenset(state.awarded_rewards), frozenset(state.pending),
        tuple(sorted(
            (instance_id, entry.reward_id, entry.remaining_picks, tuple(sorted(entry.used_skills)))
            for instance_id, entry in state.held.items()
        )),
        tuple(sorted(
            (skill, boost["bonus_levels"], boost["expires_at_seconds"] - state.elapsed)
            for skill, boost in state.boosts.items()
        )),
        tuple(sorted((token, ready - state.elapsed) for token, ready in state.cooldowns.items())),
    )


def _progress_steps(state: RouteState, routes: dict, maximum_time: int):
    for instance_id in sorted(state.pending or state.held):
        reward = state.rewards[state.held[instance_id].reward_id]
        for skill in sorted(_reward_skills(reward, state)):
            try:
                amount = state.reward_pick(instance_id, skill, "reward")
                override = state.reward_override(reward, skill, "reward")
            except DataError:
                continue
            yield (instance_id, "reward_use", skill), {
                "kind": "reward_use", "instance_id": instance_id, "reward_id": reward["id"],
                "skill_id": skill, "gain_xp_tenths": amount, "overrides_observed_skill_restriction": override,
                "explanation": f"Use {reward['name']} on {state.tables['skills'][skill]['name']}.",
            }
    if state.pending:
        return
    for kind, record in routes[state.location]:
        record_id = record["id"]
        yield (record_id, kind), {
            "kind": kind, ("action_id" if kind == "action" else "edge_id"): record_id,
            "modeled_seconds": record["duration"]["expected_seconds"], "explanation": record["name"],
        }
    if state.elapsed < maximum_time or state.boosts or state.cooldowns:
        yield ("wait",), {"kind": "wait", "modeled_seconds": 1, "explanation": "Advance the modelled clock."}


def _training_steps(state: RouteState, targets: dict, last_skill: str, budget: int | None):
    if state.pending or budget == 0:
        return
    for skill, (thresholds, reasons) in sorted(targets.items()):
        if skill <= last_skill:
            continue
        before = state.xp[skill]
        maximum = thresholds[-1]
        if budget is not None:
            maximum = min(maximum, before + budget)
        preferred = {target for target in thresholds if before < target <= maximum}
        # Include every tenth of XP. Threshold moves alone can miss gains
        # immediately before an action that forces a level-scaled reward pick.
        other_amounts = (target for target in range(before + 1, maximum + 1) if target not in preferred)
        for after in chain(sorted(preferred), other_amounts):
            yield (skill, "training", after), {
                "kind": "training", "skill_id": skill, "before_xp_tenths": before,
                "gain_xp_tenths": after - before, "after_xp_tenths": after,
                "required_by": reasons, "resume_location_id": state.location,
                "explanation": f"Gain {after - before} XP tenths and resume at this waypoint.",
            }


def solve_small(validator: CatalogValidator, profile: dict, *, max_states: int = 50_000) -> dict:
    """Return an independently replayed optimum or raise on exhaustion or budget."""
    if max_states < 1:
        raise DataError("max_states must be positive")
    validator.contracts.validate("profile", profile)
    validator.validate_profile(profile)
    _check_finite(validator.tables)
    initial = RouteState(validator.tables, profile["policies"], profile["initial_state"])
    goals = set(profile["goal_action_ids"])
    targets, maximum_time = _training_targets(initial)
    routes = defaultdict(list)
    for record in validator.tables["actions"].values():
        routes[record["start_location_id"]].append(("action", record))
    for record in validator.tables["travel_edges"].values():
        routes[record["from_location_id"]].append(("travel", record))

    serial = count()
    initial_key = _state_key(initial, maximum_time, "")
    queue = [((0, 0, ()), next(serial), initial_key, initial, "", ())]
    best = {initial_key: (0, 0, ())}
    incumbent = None
    while queue:
        score, _, key, state, last_skill, steps = heappop(queue)
        if best[key] != score:
            continue
        if goals <= state.completed and not state.pending:
            return _solution(validator, profile, state, steps)

        def offer(move_id, step):
            nonlocal incumbent
            training_skill = step["skill_id"] if step["kind"] == "training" else ""
            manual = score[0] + (step["gain_xp_tenths"] if training_skill else 0)
            seconds = score[1] + step.get("modeled_seconds", 0)
            if incumbent is not None and (manual, seconds) > incumbent:
                return
            try:
                successor = state.apply(step)
            except DataError:
                return
            cost = (manual, seconds, score[2] + (move_id,))
            successor_key = _state_key(successor, maximum_time, training_skill)
            previous = best.get(successor_key)
            if previous is not None and previous <= cost:
                return
            if previous is None and len(best) >= max_states:
                raise DataError(f"Exact search exceeded its {max_states}-state limit")
            best[successor_key] = cost
            if goals <= successor.completed and not successor.pending:
                incumbent = cost[:2] if incumbent is None else min(incumbent, cost[:2])
            heappush(queue, (cost, next(serial), successor_key, successor, training_skill, steps + (step,)))

        for move_id, step in _progress_steps(state, routes, maximum_time):
            offer(move_id, step)
        budget = incumbent[0] - score[0] if incumbent is not None else None
        for move_id, step in _training_steps(state, targets, last_skill, budget):
            offer(move_id, step)
    raise DataError("Exact search found no feasible route for the supplied goals")


def _solution(validator: CatalogValidator, profile: dict, state: RouteState, steps: tuple[dict, ...]) -> dict:
    def transition_id(step):
        return step.get("action_id") or step.get("edge_id") or step.get("reward_id")

    training = Counter()
    remaining = Counter(map(transition_id, steps))
    ordered_steps = []
    for index, step in enumerate(steps, 1):
        remaining[transition_id(step)] -= 1
        if step["kind"] == "training":
            training[step["skill_id"]] += step["gain_xp_tenths"]
            step = {**step, "required_by": [record_id for record_id in step["required_by"] if remaining[record_id]]}
        ordered_steps.append({"step_id": f"step.{index:06d}", **step})
    manual = sum(training.values())
    seconds = state.elapsed - profile["initial_state"]["modeled_elapsed_seconds"]
    solution = {
        "schema_version": profile["schema_version"],
        "solution_id": "solution.exact." + profile["profile_id"],
        "inputs": input_identity(validator.catalog, profile, validator.contracts.schemas),
        "policies": profile["policies"],
        "solver": {
            "name": "exact-small-dijkstra", "version": __version__, "seed": 0,
            "status": "example" if profile["status"] == "synthetic" else "optimal",
            "primary_lower_bound_xp_tenths": manual, "secondary_lower_bound_seconds": seconds,
            "proof_artifact": None,
        },
        "objective": {
            "order": profile["objective"], "manual_training_xp_tenths": manual, "modeled_non_training_seconds": seconds,
        },
        "manual_training_xp_tenths_by_skill": dict(training),
        "steps": ordered_steps,
        "final_state": state.snapshot(),
        "verification": {"schema_valid": True, "replay_valid": True, "catalog_release_ready": False},
        "limitations": [
            "Exact for the supplied finite catalog and profile using the catalog's expected durations.",
            "Training steps specify XP gains and resume waypoints. The player chooses the method.",
        ],
    }
    verify_solution(solution, profile, validator)
    return solution
