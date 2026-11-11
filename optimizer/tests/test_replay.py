"""Replay hand-audited routes and reject forged or infeasible steps."""

from copy import deepcopy
from pathlib import Path
import unittest
from unittest.mock import patch

from quest_optimizer.data import Contracts, DataError, load_catalog, read_json
from quest_optimizer.replay import input_identity, verify_solution
from quest_optimizer.semantics import CatalogValidator
from quest_optimizer.transitions import RouteState


ROOT = Path(__file__).resolve().parents[2]
EXAMPLE = ROOT / "examples/synthetic"
SKILL = "skill.example"


def all_of(*requirements):
    return {"kind": "all", "requirements": list(requirements)}


def completed(action_id):
    return {"kind": "action_completed", "action_id": action_id}


class ReplayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.contracts = Contracts(ROOT / "schemas")

    def setUp(self):
        self.catalog = load_catalog(EXAMPLE / "manifest.json", self.contracts)
        self.profile = read_json(EXAMPLE / "profile.json")
        self.solution = read_json(EXAMPLE / "solution.json")
        finale = self.catalog["actions"][0]
        evidence = finale["evidence"]
        duration = dict.fromkeys(("min_seconds", "expected_seconds", "max_seconds"), 1)

        def token(name, kind, maximum=None, **extra):
            return {"id": f"token.{name}", "name": name, "kind": kind, "maximum": maximum,
                    "evidence": evidence, **extra}

        def action(name, kind, requirements, effects, activity_id=None, **extra):
            return {**finale, "id": f"action.{name}", "name": name, "kind": kind,
                    "activity_id": activity_id, "requirements": requirements, "effects": effects,
                    "duration": duration, **extra}

        self.catalog["tokens"] = [
            token("branch", "choice", options=["option.rescue", "option.leave"]),
            token("unlocked", "flag"), token("kudos", "counter", 2), token("transport", "cooldown"),
        ]
        self.catalog["items"] = [{
            "id": "item.permit", "name": "Permit", "tradeable": True, "stackable": True, "evidence": evidence,
        }]
        self.catalog["locations"].append({
            **self.catalog["locations"][0], "id": "location.remote", "name": "Remote waypoint", "x": 1,
        })
        self.catalog["activities"].extend([
            {**self.catalog["activities"][0], "id": "activity.rescue", "name": "Rescue",
             "kind": "subquest", "parent_activity_id": "activity.example", "completion_action_ids": ["action.rescue"]},
            {**self.catalog["activities"][0], "id": "activity.diary", "name": "Diary tier",
             "kind": "diary_tier", "completion_action_ids": ["action.diary"]},
        ])
        term = {"skill_id": SKILL, "level_multiplier": 1, "level_divisor": 1, "weight": 1}
        self.combat_gate = {"kind": "combat_level", "formula_id": "combat.example", "minimum_level": 2}
        self.catalog["combat_formulas"] = [{
            "id": "combat.example", "name": "Example combat level", "base_terms": [],
            "styles": [[term]], "divisor": 1, "evidence": evidence,
        }]
        self.boost_gate = {"kind": "skill", "skill_id": SKILL, "minimum_level": 2, "boostable": True}
        self.choice = {"kind": "choice", "token_id": "token.branch", "option": "option.rescue"}
        unlocked = {"kind": "flag", "token_id": "token.unlocked", "value": True}
        self.catalog["xp_rewards"].append({
            "id": "reward.diary", "name": "Example diary lamp", "kind": "other_lamp",
            "eligible_skills": "all", "minimum_level": 1, "selection_count": 1,
            "distinct_skills": False, "retainable": True, "observed_restrictions": "Any fixture skill.",
            "amount": {"kind": "fixed", "xp_tenths": 900}, "evidence": evidence,
        })
        self.catalog["actions"].extend([
            action("opening", "quest_stage", all_of(), [
                {"kind": "choose", "token_id": "token.branch", "option": "option.rescue"},
                {"kind": "skill_boost", "skill_id": SKILL, "bonus_levels": 1, "duration_seconds": 3},
            ], "activity.example"),
            action("rescue", "quest_stage", self.choice, [
                {"kind": "flag", "token_id": "token.unlocked", "value": True},
                {"kind": "xp", "skill_id": SKILL, "xp_tenths": 100},
            ], "activity.rescue"),
            action("task", "diary_task", self.boost_gate, [
                {"kind": "counter", "token_id": "token.kudos", "delta": 2},
            ], "activity.diary"),
            action("diary", "other", completed("action.task"), [], "activity.diary"),
            action("claim", "reward_claim", all_of(completed("action.rescue"), completed("action.diary")), [
                {"kind": "xp_reward", "reward_id": "reward.diary", "quantity": 1},
            ]),
            action("alternative", "other", all_of(), [
                {"kind": "choose", "token_id": "token.branch", "option": "option.leave"},
            ]),
            action("repeatable", "other", all_of(), [], repeat_limit=2),
            action("overflow", "other", all_of(), [
                {"kind": "xp", "skill_id": SKILL, "xp_tenths": 500},
                {"kind": "counter", "token_id": "token.kudos", "delta": 1},
            ], consumes=[{"item_id": "item.permit", "quantity": 1}]),
        ])
        finale.update(
            start_location_id="location.remote", end_location_id="location.remote", duration=duration, effects=[],
            requirements=all_of(
                self.combat_gate, completed("action.rescue"), completed("action.diary"),
                {"kind": "cooldown_ready", "token_id": "token.transport"},
                {"kind": "elapsed_time", "minimum_seconds": 8},
            ),
        )
        self.catalog["travel_edges"].append({
            "id": "travel.remote", "name": "Permit crossing", "mode": "other",
            "from_location_id": "location.example", "to_location_id": "location.remote",
            "duration": duration, "repeat_limit": 2, "evidence": evidence,
            "consumes": [{"item_id": "item.permit", "quantity": 1}],
            "effects": [{"kind": "start_cooldown", "token_id": "token.transport", "duration_seconds": 2}],
            "requirements": all_of(
                {"kind": "any", "requirements": [unlocked, completed("action.alternative")]},
                self.choice, {"kind": "counter", "token_id": "token.kudos", "minimum": 2},
            ),
        })
        self.contracts.validate("catalog", self.catalog)
        self.validator = CatalogValidator(self.catalog, self.contracts)
        self.validator.validate_catalog()
        self.profile["policies"]["allow_boosts"] = True
        self.profile["initial_state"]["inventory"] = {"item.permit": 1}
        self.solution.update(
            inputs=input_identity(self.catalog, self.profile, self.contracts.schemas),
            policies=self.profile["policies"],
            steps=[self.action(name) for name in ("opening", "rescue", "task", "diary", "claim")] + [
                {"step_id": "step.travel", "kind": "travel", "edge_id": "travel.remote",
                 "modeled_seconds": 1, "explanation": "Cross to the finale."},
                {"step_id": "step.wait", "kind": "wait", "modeled_seconds": 2, "explanation": "Wait for the cooldown."},
                {"step_id": "step.reward", "kind": "reward_use", "reward_id": "reward.diary",
                 "instance_id": "reward.diary.instance.1", "skill_id": SKILL, "gain_xp_tenths": 900,
                 "overrides_observed_skill_restriction": False, "explanation": "Raise the base level."},
                self.action("example"),
            ],
            manual_training_xp_tenths_by_skill={},
            final_state={
                "location_id": "location.remote", "xp_tenths": {SKILL: 1000},
                "completed_action_ids": [
                    "action.opening", "action.rescue", "action.task", "action.diary", "action.claim", "action.example",
                ],
                "flags": {"token.unlocked": True}, "counters": {"token.kudos": 2},
                "inventory": {}, "held_rewards": [], "modeled_elapsed_seconds": 9,
                "choices": {"token.branch": "option.rescue"}, "travel_counts": {"travel.remote": 1},
            },
        )
        self.solution["objective"].update(manual_training_xp_tenths=0, modeled_non_training_seconds=9)

    @staticmethod
    def action(name):
        return {"step_id": f"step.{name}", "kind": "action", "action_id": f"action.{name}",
                "modeled_seconds": 1, "explanation": name}

    def replay(self):
        return verify_solution(self.solution, self.profile, self.validator)

    def test_staged_quest_diary_claim_and_timed_travel(self):
        report = self.replay()
        self.assertEqual(report["objective"]["modeled_non_training_seconds"], 9)
        self.assertEqual(report["final_state"]["xp_tenths"], {SKILL: 1000})
        self.assertEqual(report["final_state"]["inventory"], {})
        self.assertTrue(report["verification"]["replay_valid"])

    def test_rejects_infeasible_steps(self):
        original = self.solution["steps"]
        for index, replacement, error in [
            (1, self.action("claim"), "reward claim"),
            (1, self.action("alternative"), "already set"),
            (1, original[5], r"steps\.1"),
            (4, original[8], "starts at"),
            (5, {**original[5], "modeled_seconds": 2}, "expected 1"),
            (6, {**original[6], "modeled_seconds": 1}, r"steps\.8"),
        ]:
            with self.subTest(error=error):
                self.solution["steps"] = deepcopy(original)
                self.solution["steps"][index] = {**replacement, "step_id": "step.replacement"}
                with self.assertRaisesRegex(DataError, error):
                    self.replay()

        self.solution["steps"] = original
        self.profile["initial_state"]["inventory"].clear()
        self.solution["inputs"] = input_identity(self.catalog, self.profile, self.contracts.schemas)
        with self.assertRaisesRegex(DataError, "consumes 1 of 'item.permit'"):
            self.replay()

    def test_rejects_forged_results_and_hashes(self):
        original = deepcopy(self.solution)
        for container, field, value in [
            ("inputs", "catalog_sha256", "0" * 64),
            ("inputs", "profile_sha256", "0" * 64),
            ("inputs", "schemas_sha256", "0" * 64),
            ("objective", "modeled_non_training_seconds", 8),
            ("final_state", "counters", {"token.kudos": 1}),
            ("final_state", "xp_tenths", {SKILL: 1001}),
            ("verification", "catalog_release_ready", True),
        ]:
            with self.subTest(field=field):
                self.solution = deepcopy(original)
                self.solution[container][field] = value
                with self.assertRaisesRegex(DataError, field):
                    self.replay()
        self.solution = original
        self.solution["steps"] = original["steps"][:-1]
        with self.assertRaisesRegex(DataError, "unmet goals"):
            self.replay()

    def test_boosts_expire_on_boundary_and_failed_effects_are_atomic(self):
        state = RouteState(self.validator.tables, self.profile["policies"], self.profile["initial_state"])
        state = state.apply(self.action("opening")).apply(self.action("rescue"))
        self.assertTrue(state._progress_gates_met(self.boost_gate))
        self.assertFalse(state._progress_gates_met(self.combat_gate))
        state = state.apply(self.action("task")).apply(self.action("diary"))
        self.assertEqual(state.elapsed, 4)
        self.assertFalse(state._progress_gates_met(self.boost_gate))
        before = state.snapshot()
        with self.assertRaisesRegex(DataError, "outside its bounds"):
            state.apply(self.action("overflow"))
        self.assertEqual(state.snapshot(), before)
        repeat = self.action("repeatable")
        state = state.apply(repeat).apply(repeat)
        self.assertEqual(state.snapshot()["action_counts"], {"action.repeatable": 2})
        with self.assertRaisesRegex(DataError, "repeat limit of 2"):
            state.apply(repeat)

    def test_committed_routes_replay_offline(self):
        build = ROOT / "examples/build-242"
        with patch("socket.socket", side_effect=AssertionError("Network forbidden")):
            catalog = load_catalog(ROOT / "data/manifest.json", self.contracts)
            validator = CatalogValidator(catalog, self.contracts)
            for name in ("museum-quiz", "balloon-travel"):
                with self.subTest(name=name):
                    report = verify_solution(read_json(build / f"{name}-solution.json"),
                                             read_json(build / f"{name}-profile.json"), validator)
                    self.assertTrue(report["verification"]["replay_valid"])
            validator = CatalogValidator(load_catalog(EXAMPLE / "manifest.json", self.contracts), self.contracts)
            report = verify_solution(read_json(EXAMPLE / "solution.json"), read_json(EXAMPLE / "profile.json"), validator)
            self.assertEqual(report["manual_training_xp_tenths_by_skill"], {SKILL: 1000})


class RecipeForDisasterReplayTests(unittest.TestCase):
    def test_parent_goal_needs_rescues_finale_and_quest_points(self):
        contracts = Contracts(ROOT / "schemas")
        catalog = load_catalog(EXAMPLE / "manifest.json", contracts)
        profile = read_json(EXAMPLE / "profile.json")
        solution = read_json(EXAMPLE / "solution.json")
        review = read_json(ROOT / "data/raw/build-242/recipe-for-disaster-review.json")
        parent_id = review["activity_id"]
        goal_id = review["parent_goal"]["action_id"]
        finale_id = review["parent_goal"]["requires_action_id"]
        stages = {row["completion_action_id"]: row for row in review["stages"]}
        rescue_id = "rfd.freeing_the_mountain_dwarf.complete"
        finale_rules = stages[finale_id]["progression_requirements"]
        starting_actions = [
            rule["action_id"] for rule in finale_rules["requirements"]
            if rule["kind"] == "action_completed" and rule["action_id"] != rescue_id
        ]
        template = catalog["actions"][0]
        evidence = template["evidence"]
        catalog["tokens"] = [{
            "id": "token.quest_points", "name": "Quest points", "kind": "counter", "maximum": None,
            "evidence": evidence,
        }]
        # Use the pinned finale dependencies and quest points. Waypoints,
        # durations and the saved account are synthetic.
        catalog["activities"] = []
        catalog["actions"] = []
        for action_id in [*starting_actions, rescue_id, finale_id, goal_id]:
            stage = stages.get(action_id)
            activity_id = stage["activity_id"] if stage else action_id.removesuffix(".complete")
            catalog["activities"].append({
                "id": activity_id, "name": activity_id, "kind": "subquest" if stage else "quest",
                "parent_activity_id": parent_id if stage else None,
                "completion_action_ids": [action_id], "evidence": evidence,
            })
            requirements = {finale_id: finale_rules, goal_id: completed(finale_id)}.get(action_id, all_of())
            points = stage["completion_rewards"]["quest_points"] if stage else 0
            catalog["actions"].append({
                **template, "id": action_id, "name": action_id, "activity_id": activity_id,
                "requirements": requirements,
                "effects": [{"kind": "counter", "token_id": "token.quest_points", "delta": points}] if points else [],
                "duration": dict.fromkeys(("min_seconds", "expected_seconds", "max_seconds"), 1),
            })
        contracts.validate("catalog", catalog)
        validator = CatalogValidator(catalog, contracts)
        validator.validate_catalog()
        profile["initial_state"].update(
            completed_action_ids=starting_actions, counters={"token.quest_points": 174},
        )
        profile["goal_action_ids"] = [goal_id]
        solution.update(
            inputs=input_identity(catalog, profile, contracts.schemas),
            steps=[
                {"kind": "action", "action_id": action_id, "step_id": f"step.{index}", "modeled_seconds": 1,
                 "explanation": action_id}
                for index, action_id in enumerate((rescue_id, finale_id, goal_id))
            ],
            manual_training_xp_tenths_by_skill={},
            final_state={
                **profile["initial_state"], "completed_action_ids": [*starting_actions, rescue_id, finale_id, goal_id],
                "counters": {"token.quest_points": 176}, "modeled_elapsed_seconds": 3,
            },
        )
        solution["objective"].update(manual_training_xp_tenths=0, modeled_non_training_seconds=3)
        with patch("socket.socket", side_effect=AssertionError("Network forbidden")):
            verify_solution(solution, profile, validator)
            for skipped in (0, 1):
                without_stage = {**solution, "steps": [
                    step for index, step in enumerate(solution["steps"]) if index != skipped
                ]}
                with self.assertRaisesRegex(DataError, r"steps\.0|steps\.1"):
                    verify_solution(without_stage, profile, validator)
            profile["initial_state"]["counters"]["token.quest_points"] = 173
            solution["inputs"] = input_identity(catalog, profile, contracts.schemas)
            with self.assertRaisesRegex(DataError, r"steps\.1"):
                verify_solution(solution, profile, validator)
