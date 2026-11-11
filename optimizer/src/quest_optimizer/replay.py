"""Verify an ordered route from the original catalog and account profile."""

from collections import Counter
from hashlib import sha256

from .errors import DataError
from .normalization import canonical_json
from .objectives import counted_training, outstanding, priority_xp
from .semantics import CatalogValidator
from .transitions import RouteState


def input_identity(catalog: dict, profile: dict, schemas: dict) -> dict:
    def digest(value) -> str:
        return sha256(canonical_json(value).encode("utf-8")).hexdigest()

    normalized = {
        name: sorted(value, key=lambda row: row["id"]) if isinstance(value, list) else value
        for name, value in catalog.items()
    }
    return {
        "dataset_id": catalog["dataset_id"],
        "dataset_version": catalog["dataset_version"],
        "profile_id": profile["profile_id"],
        "catalog_sha256": digest(normalized),
        "profile_sha256": digest(profile),
        "schemas_sha256": digest(schemas),
    }


def verify_solution(
    solution: dict, profile: dict, validator: CatalogValidator, *, release_ready: bool = False,
) -> dict:
    contracts = validator.contracts
    contracts.validate("profile", profile)
    validator.validate_profile(profile)
    contracts.validate("solution", solution)
    for field, expected in input_identity(validator.catalog, profile, contracts.schemas).items():
        if solution["inputs"][field] != expected:
            raise DataError(f"inputs.{field}: does not match the supplied input")
    policies = profile["policies"]
    if solution["policies"] != policies:
        raise DataError("policies: do not match the supplied profile")
    if release_ready and profile["status"] != "reviewed":
        raise DataError("profile.status: release replay requires a reviewed profile")
    if solution["verification"]["catalog_release_ready"] and not release_ready:
        raise DataError("verification.catalog_release_ready: the catalog has not passed a release audit")
    if profile["status"] == "synthetic" and solution["solver"]["status"] != "example":
        raise DataError("solver.status: synthetic inputs require an example solution")

    initial = profile["initial_state"]
    state = RouteState(validator.tables, policies, initial, f"solution {solution['solution_id']}")
    priorities = set(profile.get("priority_action_ids", ()))
    skill_targets = priority_xp(profile, validator.tables["skills"])
    priority_seconds = 0
    skill_seconds = 0
    counted = 0
    training = Counter()
    step_ids = set()
    for index, step in enumerate(solution["steps"]):
        path = f"steps.{index} ({step['step_id']})"
        if step["step_id"] in step_ids:
            raise DataError(f"{path}: duplicate step ID")
        step_ids.add(step["step_id"])
        successor = state.apply(step, path)
        if priorities - state.completed:
            priority_seconds += successor.elapsed - state.elapsed
        if outstanding(state.xp, skill_targets):
            skill_seconds += successor.elapsed - state.elapsed
        counted += counted_training(step, skill_targets)
        state = successor
        if step["kind"] == "training":
            training[step["skill_id"]] += step["gain_xp_tenths"]
    if state.pending:
        raise DataError(f"final_state.held_rewards: unresolved immediate reward {min(state.pending)!r}")
    unmet = sorted(set(profile["goal_action_ids"]) - state.completed)
    if unmet:
        raise DataError("goal_action_ids: unmet goals " + ", ".join(unmet))
    unmet_priorities = sorted(priorities - state.completed)
    if unmet_priorities:
        raise DataError("priority_action_ids: unmet priorities " + ", ".join(unmet_priorities))
    if missing_skills := outstanding(state.xp, skill_targets):
        raise DataError("priority_skill_levels: unmet targets " + ", ".join(sorted(missing_skills)))

    validator._state(solution["final_state"], policies, state.context, "final_state")
    declared = RouteState(validator.tables, policies, solution["final_state"]).snapshot()
    actual = state.snapshot()
    for field in sorted(declared.keys() | actual.keys()):
        if actual.get(field) != declared.get(field):
            raise DataError(f"final_state.{field}: differs from the replayed state")
    if training != Counter(solution["manual_training_xp_tenths_by_skill"]):
        raise DataError("manual_training_xp_tenths_by_skill: differs from the replayed training")
    objective = {
        "order": profile["objective"],
        "manual_training_xp_tenths": sum(training.values()),
        "modeled_non_training_seconds": state.elapsed - initial["modeled_elapsed_seconds"],
    }
    if priorities:
        objective["priority_elapsed_seconds"] = priority_seconds
    if skill_targets:
        objective.update(priority_skill_elapsed_seconds=skill_seconds, counted_manual_training_xp_tenths=counted)
    for field, value in objective.items():
        if solution["objective"][field] != value:
            raise DataError(f"objective.{field}: expected {value} from replay")
    return {
        "objective": objective,
        "manual_training_xp_tenths_by_skill": dict(training),
        "final_state": actual,
        "verification": {
            "schema_valid": True, "replay_valid": True, "catalog_release_ready": release_ready,
        },
    }
