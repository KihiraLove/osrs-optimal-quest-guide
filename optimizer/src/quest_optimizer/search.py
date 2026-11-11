"""Exhaustive lexicographic reference search for small, finite catalogs."""

from collections import Counter, defaultdict
from heapq import heappop, heappush
from itertools import chain, count

from . import __version__
from .errors import DataError
from .objectives import counted_training, outstanding, priority_xp
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
        pairs(state.bank_inventory),
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


def _reward_steps(state: RouteState):
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


def _transition_step(kind: str, record: dict) -> dict:
    step = {
        "kind": kind, ("action_id" if kind == "action" else "edge_id"): record["id"],
        "modeled_seconds": record["duration"]["expected_seconds"], "explanation": record["name"],
    }
    if "planned_outcome" in record:
        step["planned_outcome"] = record["planned_outcome"].copy()
    return step


def _transition_key(kind: str, record: dict) -> tuple[str, str]:
    spell = kind == "travel" and record["mode"] == "teleport_spell" and any(
        effect["kind"] == "xp" and effect["skill_id"] == "skill.magic" for effect in record["effects"]
    )
    return (("!" if spell else "") + record["id"], kind)


def _progress_steps(state: RouteState, routes: dict, maximum_time: int):
    yield from _reward_steps(state)
    if state.pending:
        return
    for kind, record in routes[state.location]:
        yield _transition_key(kind, record), _transition_step(kind, record)
    if state.elapsed < maximum_time or state.boosts or state.cooldowns:
        yield ("wait",), {"kind": "wait", "modeled_seconds": 1, "explanation": "Advance the modelled clock."}


def _training_step(state: RouteState, skill: str, after: int, reasons: list[str]) -> dict:
    before = state.xp[skill]
    return {
        "kind": "training", "skill_id": skill, "before_xp_tenths": before,
        "gain_xp_tenths": after - before, "after_xp_tenths": after,
        "required_by": reasons, "resume_location_id": state.location,
        "explanation": f"Gain {after - before} XP tenths and resume at this waypoint.",
    }


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
            yield (skill, "training", after), _training_step(state, skill, after, reasons)


def solve_small(validator: CatalogValidator, profile: dict, *, max_states: int = 50_000) -> dict:
    """Return an independently replayed optimum or raise on exhaustion or budget."""
    if max_states < 1:
        raise DataError("max_states must be positive")
    validator.contracts.validate("profile", profile)
    validator.validate_profile(profile)
    _check_finite(validator.tables)
    initial = RouteState(validator.tables, profile["policies"], profile["initial_state"])
    priorities = set(profile.get("priority_action_ids", ()))
    skill_targets = priority_xp(profile, validator.tables["skills"])
    goals = set(profile["goal_action_ids"]) | priorities
    targets, maximum_time = _training_targets(initial)
    for skill, threshold in skill_targets.items():
        existing, reasons = targets.get(skill, ((), []))
        targets[skill] = (tuple(sorted(set(existing) | {threshold})), sorted(set(reasons) | {skill}))
    routes = defaultdict(list)
    for record in validator.tables["actions"].values():
        routes[record["start_location_id"]].append(("action", record))
    for record in validator.tables["travel_edges"].values():
        routes[record["from_location_id"]].append(("travel", record))

    serial = count()
    initial_key = _state_key(initial, maximum_time, "")
    zero = (0, 0, 0, 0, ())
    queue = [(zero, next(serial), initial_key, initial, "", ())]
    best = {initial_key: zero}
    incumbent = None
    while queue:
        score, _, key, state, last_skill, steps = heappop(queue)
        if best[key] != score:
            continue
        if goals <= state.completed and not state.pending and not outstanding(state.xp, skill_targets):
            return build_solution(
                validator, profile, state, steps,
                solution_id="solution.exact." + profile["profile_id"],
                solver={
                    "name": "exact-small-dijkstra", "seed": 0, "status": "optimal",
                    "primary_lower_bound_xp_tenths": score[0],
                    "secondary_lower_bound_seconds": None if priorities or skill_targets else score[3],
                },
                priority_seconds=score[2], priority_skill_seconds=score[1],
                limitations=["Exact for the supplied finite catalog and profile using the catalog's expected durations."],
            )

        def offer(move_id, step):
            nonlocal incumbent
            training_skill = step["skill_id"] if step["kind"] == "training" else ""
            manual = score[0] + counted_training(step, skill_targets)
            duration = step.get("modeled_seconds", 0)
            skill_seconds = score[1] + (duration if outstanding(state.xp, skill_targets) else 0)
            priority_seconds = score[2] + (duration if priorities - state.completed else 0)
            seconds = score[3] + duration
            objective = (manual, skill_seconds, priority_seconds, seconds)
            if incumbent is not None and objective > incumbent:
                return
            try:
                successor = state.apply(step)
            except DataError:
                return
            cost = (*objective, score[4] + (move_id,))
            successor_key = _state_key(successor, maximum_time, training_skill)
            previous = best.get(successor_key)
            if previous is not None and previous <= cost:
                return
            if previous is None and len(best) >= max_states:
                raise DataError(f"Exact search exceeded its {max_states}-state limit")
            best[successor_key] = cost
            if goals <= successor.completed and not successor.pending and not outstanding(successor.xp, skill_targets):
                incumbent = objective if incumbent is None else min(incumbent, objective)
            heappush(queue, (cost, next(serial), successor_key, successor, training_skill, steps + (step,)))

        for move_id, step in _progress_steps(state, routes, maximum_time):
            offer(move_id, step)
        budget = incumbent[0] - score[0] if incumbent is not None and not skill_targets else None
        for move_id, step in _training_steps(state, targets, last_skill, budget):
            offer(move_id, step)
    raise DataError("Exact search found no feasible route for the supplied goals")


def build_solution(
    validator: CatalogValidator, profile: dict, state: RouteState, steps: tuple[dict, ...],
    *, solution_id: str, solver: dict, limitations: list[str], priority_seconds: int = 0,
    priority_skill_seconds: int = 0,
) -> dict:
    def transition_id(step):
        return step.get("action_id") or step.get("edge_id") or step.get("reward_id")

    training = Counter()
    remaining = Counter(map(transition_id, steps))
    ordered_steps = []
    for index, step in enumerate(steps, 1):
        remaining[transition_id(step)] -= 1
        if step["kind"] == "training":
            training[step["skill_id"]] += step["gain_xp_tenths"]
            relevant = [record_id for record_id in step["required_by"] if remaining[record_id]]
            if relevant:
                step = {**step, "required_by": relevant}
        ordered_steps.append({"step_id": f"step.{index:06d}", **step})
    manual = sum(training.values())
    seconds = state.elapsed - profile["initial_state"]["modeled_elapsed_seconds"]
    solution = {
        "schema_version": profile["schema_version"],
        "solution_id": solution_id,
        "inputs": input_identity(validator.catalog, profile, validator.contracts.schemas),
        "policies": profile["policies"],
        "solver": {
            **solver, "version": __version__, "proof_artifact": None,
        },
        "objective": {
            "order": profile["objective"], "manual_training_xp_tenths": manual, "modeled_non_training_seconds": seconds,
        },
        "manual_training_xp_tenths_by_skill": dict(training),
        "steps": ordered_steps,
        "final_state": state.snapshot(),
        "verification": {"schema_valid": True, "replay_valid": True, "catalog_release_ready": False},
        "limitations": [
            *limitations,
            "Training steps specify XP gains and resume waypoints. The player chooses the method.",
        ],
    }
    if profile["status"] == "synthetic":
        solution["solver"]["status"] = "example"
    if any("planned_outcome" in step for step in steps):
        solution["limitations"].append(
            "Replay checks the planned success path. Confirm each conditional outcome in game before continuing."
        )
    if "priority_action_ids" in profile:
        solution["objective"]["priority_elapsed_seconds"] = priority_seconds
    if "priority_skill_levels" in profile:
        targets = priority_xp(profile, validator.tables["skills"])
        solution["objective"].update(
            priority_skill_elapsed_seconds=priority_skill_seconds,
            counted_manual_training_xp_tenths=sum(counted_training(step, targets) for step in steps),
        )
    verify_solution(solution, profile, validator)
    return solution
