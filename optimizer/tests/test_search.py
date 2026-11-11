"""Independent optima and end-to-end tests for the small reference solver."""

from itertools import permutations, product
from pathlib import Path
import unittest
from unittest.mock import patch

from quest_optimizer.bounded_search import solve_bounded
from quest_optimizer.data import Contracts, DataError, load_catalog, read_json
from quest_optimizer.replay import verify_solution
from quest_optimizer.search import solve_small
from quest_optimizer.semantics import CatalogValidator


ROOT = Path(__file__).resolve().parents[2]
EXAMPLE = ROOT / "examples/synthetic"
SKILL = "skill.example"


class SearchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.contracts = Contracts(ROOT / "schemas")

    def setUp(self):
        self.catalog = load_catalog(EXAMPLE / "manifest.json", self.contracts)
        self.profile = read_json(EXAMPLE / "profile.json")
        self.action = self.catalog["actions"][0]

    def validator(self):
        self.contracts.validate("catalog", self.catalog)
        validator = CatalogValidator(self.catalog, self.contracts)
        validator.validate_catalog()
        return validator

    def test_exact_quest_order_beats_largest_xp_first(self):
        self.catalog["skills"][0]["xp_thresholds_tenths"] = [0, 4, 8]
        self.catalog["skills"].append({
            **self.catalog["skills"][0], "id": "skill.other", "name": "Other", "xp_thresholds_tenths": [0, 3, 8],
        })
        self.profile["initial_state"]["xp_tenths"]["skill.other"] = 0
        rules = [("action.a", SKILL, 4, "skill.other", 8, 3), ("action.b", "skill.other", 3, SKILL, 4, 4)]
        actions = [
            {**self.action, "id": action_id, "name": action_id,
             "requirements": {"kind": "skill", "skill_id": required, "minimum_level": 2, "boostable": False},
             "effects": [{"kind": "xp", "skill_id": awarded, "xp_tenths": xp}],
             "duration": {"min_seconds": seconds, "expected_seconds": seconds, "max_seconds": seconds}}
            for action_id, required, _, awarded, xp, seconds in rules
        ]
        self.catalog["actions"] = actions
        self.profile["goal_action_ids"] = [action["id"] for action in actions]
        self.catalog["activities"][0]["completion_action_ids"] = self.profile["goal_action_ids"]

        # Enumerate both orders and every pre-quest gain for both skills.
        def cost(order, gains):
            state = {SKILL: 0, "skill.other": 0}
            for index, (_, required, minimum, awarded, xp, _) in enumerate(order):
                state[SKILL] += gains[2 * index]
                state["skill.other"] += gains[2 * index + 1]
                if state[required] < minimum:
                    return None
                state[awarded] += xp
            return sum(gains), sum(row[-1] for row in order)

        def best_for(order):
            return min(value for gains in product(range(9), repeat=4) if (value := cost(order, gains)) is not None)

        expected = min(best_for(order) for order in permutations(rules))
        self.assertEqual(expected, (3, 7))
        # Both quests are dependency-ready. Stable dependency order and
        # largest-reward-first each choose A before B.
        dependency_order = sorted(rules)
        largest_reward_first = sorted(rules, key=lambda rule: -rule[4])
        self.assertEqual(best_for(dependency_order), (4, 7))
        self.assertEqual(best_for(largest_reward_first), (4, 7))
        validator = self.validator()
        with patch("socket.socket", side_effect=AssertionError("Network forbidden")):
            solution = solve_small(validator, self.profile)
            verify_solution(solution, self.profile, validator)
        self.assertEqual(solution["manual_training_xp_tenths_by_skill"], {"skill.other": 3})
        self.assertEqual(solution["objective"]["modeled_non_training_seconds"], expected[1])
        self.assertEqual([step["action_id"] for step in solution["steps"] if step["kind"] == "action"],
                         ["action.b", "action.a"])

    def test_training_before_immediate_scaled_reward_uses_exact_nonthreshold_amount(self):
        self.catalog["skills"][0]["xp_thresholds_tenths"] = [0, 5, 10, 20]
        reward = {
            "id": "reward.scaled", "name": "Scaled reward", "kind": "other_lamp",
            "eligible_skills": [SKILL], "minimum_level": 1, "selection_count": 1,
            "distinct_skills": False, "retainable": False, "observed_restrictions": "Fixture skill only.",
            "amount": {"kind": "by_level", "values": [
                {"level": level, "xp_tenths": amount} for level, amount in enumerate((1, 7, 8, 8), 1)
            ]},
            "evidence": self.action["evidence"],
        }
        self.catalog["xp_rewards"].append(reward)
        self.catalog["actions"].append({
            **self.action, "id": "claim.scaled", "kind": "reward_claim", "activity_id": None,
            "requirements": {"kind": "all", "requirements": []},
            "effects": [{"kind": "xp", "skill_id": SKILL, "xp_tenths": 2},
                        {"kind": "xp_reward", "reward_id": reward["id"], "quantity": 1}],
        })
        self.action["requirements"] = {"kind": "skill", "skill_id": SKILL, "minimum_level": 3, "boostable": False}

        # Check every training amount before the claim and any residual deficit.
        expected = min(
            before + max(0, 10 - (before + 2 + (7 if before + 2 >= 5 else 1)))
            for before in range(11)
        )
        self.assertEqual(expected, 3)
        validator = self.validator()
        solution = solve_small(validator, self.profile)
        self.assertEqual(solution["objective"]["manual_training_xp_tenths"], expected)
        self.assertEqual([step["kind"] for step in solution["steps"]],
                         ["training", "action", "reward_use", "action"])
        self.assertEqual(solution["steps"][2]["gain_xp_tenths"], 7)
        bounded, _ = solve_bounded(validator, self.profile)
        self.assertEqual(bounded["objective"], solution["objective"])

    def test_optional_detour_and_quest_lamp_policy(self):
        self.catalog["skills"][0]["xp_thresholds_tenths"] = [0, 4]
        self.catalog["skills"].append({**self.catalog["skills"][0], "id": "skill.other", "name": "Other"})
        self.profile["initial_state"]["xp_tenths"]["skill.other"] = 0
        self.action["requirements"] = {"kind": "all", "requirements": [
            {"kind": "skill", "skill_id": skill, "minimum_level": 2, "boostable": False}
            for skill in (SKILL, "skill.other")
        ]}
        reward = {
            "id": "reward.detour", "name": "Detour lamp", "kind": "quest_lamp",
            "eligible_skills": [SKILL], "minimum_level": 1, "selection_count": 1,
            "distinct_skills": False, "retainable": True, "observed_restrictions": "Fixture skill only.",
            "amount": {"kind": "fixed", "xp_tenths": 4}, "evidence": self.action["evidence"],
        }
        self.catalog["xp_rewards"].append(reward)
        self.catalog["actions"].append({
            **self.action, "id": "action.detour", "activity_id": None, "kind": "other",
            "requirements": {"kind": "all", "requirements": []},
            "effects": [{"kind": "xp", "skill_id": SKILL, "xp_tenths": 4},
                        {"kind": "xp_reward", "reward_id": reward["id"], "quantity": 1}],
        })
        validator = self.validator()
        solution = solve_small(validator, self.profile)
        self.assertEqual(solution["objective"]["manual_training_xp_tenths"], 0)
        [pick] = [step for step in solution["steps"] if step["kind"] == "reward_use"]
        self.assertEqual(pick["skill_id"], "skill.other")
        self.assertTrue(pick["overrides_observed_skill_restriction"])
        self.profile["policies"]["quest_lamp_skill_policy"] = "observed"
        strict = solve_small(validator, self.profile)
        self.assertEqual(strict["manual_training_xp_tenths_by_skill"], {"skill.other": 4})

    def test_already_complete_has_an_empty_route(self):
        self.profile["initial_state"]["completed_action_ids"] = [self.action["id"]]
        solution = solve_small(self.validator(), self.profile)
        self.assertEqual(solution["steps"], [])
        self.assertEqual(solution["objective"]["manual_training_xp_tenths"], 0)

    def test_secondary_time_precedes_stable_id(self):
        def edge(edge_id, seconds):
            return {
                "id": edge_id, "name": edge_id, "mode": "other", "from_location_id": "location.example",
                "to_location_id": "location.remote", "requirements": {"kind": "all", "requirements": []},
                "consumes": [], "effects": [], "evidence": self.action["evidence"],
                "duration": dict.fromkeys(("min_seconds", "expected_seconds", "max_seconds"), seconds),
            }

        self.catalog["locations"].append({
            **self.catalog["locations"][0], "id": "location.remote", "name": "Remote", "x": 1,
        })
        self.action.update(start_location_id="location.remote", end_location_id="location.remote",
                           requirements={"kind": "all", "requirements": []})
        for first_time, expected in [(3, "travel.b"), (2, "travel.a")]:
            with self.subTest(first_time=first_time):
                self.catalog["travel_edges"] = [edge("travel.b", 2), edge("travel.a", first_time)]
                solution = solve_small(self.validator(), self.profile)
                self.assertEqual(solution["steps"][0]["edge_id"], expected)
                self.assertEqual(solution["objective"]["modeled_non_training_seconds"], 62)

    def test_priority_time_precedes_total_time_at_equal_training(self):
        start = "location.example"
        goal = "location.goal"
        priority = "location.priority"
        for x, location_id in enumerate((goal, priority), 1):
            self.catalog["locations"].append({
                **self.catalog["locations"][0], "id": location_id, "name": location_id, "x": x,
            })
        requirements = {"kind": "all", "requirements": []}
        duration = dict.fromkeys(("min_seconds", "expected_seconds", "max_seconds"), 1)
        self.action.update(start_location_id=goal, end_location_id=goal, requirements=requirements, duration=duration)
        self.catalog["actions"].append({
            **self.action, "id": "action.priority", "activity_id": None,
            "start_location_id": priority, "end_location_id": priority, "effects": [],
        })
        for index, (left, right, seconds) in enumerate(((start, goal, 1), (goal, priority, 2),
                                                        (start, priority, 1), (priority, goal, 9))):
            self.catalog["travel_edges"].append({
                "id": f"travel.path.{index}", "name": f"Travel path {index}", "mode": "walk",
                "from_location_id": left, "to_location_id": right, "requirements": requirements,
                "consumes": [], "effects": [], "duration": dict.fromkeys(duration, seconds),
                "evidence": self.action["evidence"],
            })
        self.profile["priority_action_ids"] = ["action.priority"]
        self.profile["objective"].insert(1, "priority_elapsed_seconds")
        validator = self.validator()
        exact = solve_small(validator, self.profile)
        bounded, _ = solve_bounded(validator, self.profile)
        self.assertEqual(exact["objective"], bounded["objective"])
        self.assertEqual(exact["objective"]["priority_elapsed_seconds"], 2)
        self.assertEqual(exact["objective"]["modeled_non_training_seconds"], 12)

        # If the same two actions have equal priority, total time selects the other order.
        self.profile["goal_action_ids"].extend(self.profile.pop("priority_action_ids"))
        self.profile["objective"].remove("priority_elapsed_seconds")
        self.assertEqual(solve_small(validator, self.profile)["objective"]["modeled_non_training_seconds"], 5)

    def test_limits_and_impossible_goals_fail_without_claiming_an_optimum(self):
        with self.assertRaisesRegex(DataError, "state limit"):
            solve_small(self.validator(), self.profile, max_states=2)
        self.action["requirements"] = {"kind": "policy", "name": "allow_poh_services", "value": True}
        with self.assertRaisesRegex(DataError, "no feasible route"):
            solve_small(self.validator(), self.profile)

    def test_cooks_assistant_finishes_with_no_training_and_stable_output(self):
        catalog = load_catalog(ROOT / "data/manifest.json", self.contracts)
        profile = read_json(ROOT / "examples/build-242/cooks-assistant-profile.json")
        validator = CatalogValidator(catalog, self.contracts)
        solution = solve_small(validator, profile)
        self.assertEqual(solution, solve_small(validator, profile))
        self.assertEqual(solution["manual_training_xp_tenths_by_skill"], {})
        self.assertEqual([step["action_id"] for step in solution["steps"]], ["quest.cooks_assistant.complete"])
