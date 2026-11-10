from copy import deepcopy
from pathlib import Path
import unittest
from unittest.mock import patch

from quest_optimizer.data import Contracts, DataError, load_catalog, read_json
from quest_optimizer.semantics import CatalogValidator

ROOT = Path(__file__).resolve().parents[2]
EXAMPLE = ROOT / "examples" / "synthetic"


class SemanticTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.contracts = Contracts(ROOT / "schemas")
        cls.example = load_catalog(EXAMPLE / "manifest.json", cls.contracts)

    def setUp(self):
        self.catalog = deepcopy(self.example)
        self.profile = read_json(EXAMPLE / "profile.json")
        self.solution = read_json(EXAMPLE / "solution.json")
        self.quest = self.catalog["actions"][0]
        evidence = self.quest["evidence"]
        self.catalog["skills"].append({
            **self.catalog["skills"][0], "id": "skill.other", "name": "Other skill",
        })
        for document_state in (self.profile["initial_state"], self.solution["final_state"]):
            document_state["xp_tenths"]["skill.other"] = 0
        self.catalog["tokens"] = [
            {"id": "token.open", "name": "Open", "kind": "flag", "maximum": None, "evidence": evidence},
            {"id": "token.points", "name": "Points", "kind": "counter", "maximum": 3, "evidence": evidence},
            {"id": "token.timer", "name": "Timer", "kind": "cooldown", "maximum": None, "evidence": evidence},
            {"id": "token.path", "name": "Path", "kind": "choice", "maximum": None,
             "options": ["path.east", "path.west"], "evidence": evidence},
        ]
        self.catalog["items"].append({
            "id": "item.ticket", "name": "Ticket", "tradeable": True, "stackable": True, "evidence": evidence,
        })
        term = {"skill_id": "skill.example", "level_multiplier": 3, "level_divisor": 2, "weight": 2}
        self.catalog["combat_formulas"] = [{
            "id": "combat.example", "name": "Example combat formula", "base_terms": [],
            "styles": [[term], [{**term, "skill_id": "skill.other", "weight": 1}]],
            "divisor": 2, "evidence": evidence,
        }]
        self.quest["requirements"] = {"kind": "all", "requirements": [
            {"kind": "any", "requirements": [
                self.quest["requirements"], {"kind": "flag", "token_id": "token.open", "value": True},
            ]},
            {"kind": "combat_level", "formula_id": "combat.example", "minimum_level": 2},
            {"kind": "choice", "token_id": "token.path", "option": None},
            {"kind": "counter", "token_id": "token.points", "minimum": 1},
        ]}
        self.quest["effects"] += [
            {"kind": "choose", "token_id": "token.path", "option": "path.east"},
            {"kind": "xp_reward", "reward_id": "reward.example", "quantity": 1},
        ]
        self.boost = {
            **self.quest, "id": "action.boost", "name": "Temporary bonus",
            "activity_id": None, "kind": "other", "repeat_limit": 3,
            "requirements": {"kind": "all", "requirements": [
                {"kind": "cooldown_ready", "token_id": "token.timer"},
                {"kind": "elapsed_time", "minimum_seconds": 5},
            ]},
            "effects": [
                {"kind": "skill_boost", "skill_id": "skill.example", "bonus_levels": 2, "duration_seconds": 5},
                {"kind": "start_cooldown", "token_id": "token.timer", "duration_seconds": 10},
            ],
        }
        self.catalog["actions"].append(self.boost)
        self.edge = {
            "id": "travel.example", "name": "Example transport", "mode": "other",
            "from_location_id": "location.example", "to_location_id": "location.example",
            "requirements": {"kind": "all", "requirements": []},
            "consumes": [{"item_id": "item.ticket", "quantity": 1}], "effects": [],
            "duration": self.quest["duration"], "repeat_limit": 2, "evidence": evidence,
        }
        self.catalog["travel_edges"].append(self.edge)
        self.reward = {
            "id": "reward.example", "name": "Example lamp", "kind": "quest_lamp",
            "eligible_skills": "all", "minimum_level": 2, "selection_count": 2,
            "distinct_skills": True, "retainable": True,
            "amount": {"kind": "by_level", "values": [
                {"level": 2, "xp_tenths": 100}, {"level": 3, "xp_tenths": 200},
            ]},
            "observed_restrictions": "Invented eligibility", "evidence": evidence,
        }
        self.catalog["xp_rewards"].append(self.reward)
        self.state = self.profile["initial_state"]
        self.state.update({
            "modeled_elapsed_seconds": 10,
            "flags": {"token.open": True},
            "counters": {"token.points": 1},
            "inventory": {"item.ticket": 1},
            "choices": {"token.path": "path.west"},
            "active_boosts": {"skill.example": {"bonus_levels": 2, "expires_at_seconds": 15}},
            "cooldowns": {"token.timer": 20},
            "completed_action_ids": ["action.boost"],
            "action_counts": {"action.boost": 2},
            "travel_counts": {"travel.example": 1},
        })
        self.solution["final_state"]["counters"] = self.state["counters"].copy()
        self.profile["policies"]["allow_boosts"] = True
        self.solution["policies"]["allow_boosts"] = True

    def validator(self):
        self.contracts.validate("catalog", self.catalog)
        validator = CatalogValidator(self.catalog, self.contracts)
        validator.validate_catalog()
        return validator

    def check_profile(self):
        self.contracts.validate("profile", self.profile)
        self.validator().validate_profile(self.profile)

    def check_solution(self):
        self.contracts.validate("solution", self.solution)
        self.validator().validate_solution(self.solution, self.profile)

    def test_typed_mechanics_and_wait_conform(self):
        self.state["held_rewards"] = [{
            "instance_id": "instance.example", "reward_id": "reward.example",
            "remaining_picks": 1, "used_skill_ids": ["skill.example"],
        }]
        self.solution["steps"].insert(0, {
            "step_id": "step.wait", "kind": "wait", "modeled_seconds": 1, "explanation": "Wait for a timer.",
        })
        self.check_profile()
        self.state["held_rewards"] = []
        self.solution["final_state"]["held_rewards"] = [{
            "instance_id": "reward.example.instance.1", "reward_id": "reward.example", "remaining_picks": 2,
        }]
        self.check_solution()

    def test_nested_unknown_reference_reports_record_field_and_source(self):
        branch = self.quest["requirements"]["requirements"][0]["requirements"][1]
        branch["token_id"] = "token.missing"
        with self.assertRaisesRegex(
            DataError, r"action.example .*source.synthetic.*requirements\.requirements\.0\.requirements\.1\.token_id"
        ):
            self.validator()

    def test_invalid_catalog_mechanics(self):
        cases = [
            (self.catalog["skills"][0], "xp_thresholds_tenths", [0, 1000, 1000], "strictly increase"),
            (self.quest["requirements"]["requirements"][0]["requirements"][0], "minimum_level", 4, "exceeds level table"),
            (self.quest["requirements"]["requirements"][1], "minimum_level", 5, "exceeds the maximum for formula"),
            (self.quest["requirements"]["requirements"][2], "option", "path.north", "unknown option"),
            (self.quest["requirements"]["requirements"][3], "minimum", 4, "exceeds the cap"),
            (self.boost["requirements"]["requirements"][0], "token_id", "token.open", "expected cooldown"),
            (self.boost["requirements"]["requirements"][1], "minimum_seconds", -1, "validation failed"),
            (self.boost["effects"][0], "duration_seconds", 0, "validation failed"),
            (self.boost["effects"][1], "token_id", "token.points", "expected cooldown"),
            (self.edge["duration"], "min_seconds", 1000, "min_seconds <= expected_seconds"),
            (self.edge["consumes"][0], "item_id", "item.missing", "unknown items ID"),
            (self.edge, "effects", [{"kind": "xp", "skill_id": "skill.other", "xp_tenths": 1}], "one-time transition"),
            (self.reward, "selection_count", 3, "number of eligible skills"),
            (self.reward["amount"], "values", [{"level": 2, "xp_tenths": 100}], "missing XP amount for eligible level 3"),
            (self.catalog["activities"][0], "parent_activity_id", "activity.example", "activity parent cycle"),
            (self.quest, "activity_id", None, "must belong to"),
        ]
        for target, key, value, message in cases:
            with self.subTest(key=key, message=message):
                original = target[key]
                target[key] = value
                try:
                    with self.assertRaisesRegex(DataError, message):
                        self.validator()
                finally:
                    target[key] = original

    def test_reward_cannot_have_two_producers(self):
        self.edge["repeat_limit"] = 1
        self.edge["effects"].append({"kind": "xp_reward", "reward_id": "reward.example", "quantity": 1})
        with self.assertRaisesRegex(DataError, "duplicate producer.*action.example"):
            self.validator()

    def test_invalid_profile_state(self):
        cases = [
            (self.profile, "dataset_version", "old", "dataset_version: expected"),
            (self.profile, "goal_action_ids", ["travel.example"], "unknown actions ID"),
            (self.state, "xp_tenths", {"skill.example": 0}, "missing XP"),
            (self.state, "counters", {"token.points": 4}, "exceeds token cap"),
            (self.state, "flags", {"token.timer": True}, "expected flag"),
            (self.state, "action_counts", {"action.boost": 4}, "respect its repeat_limit"),
            (self.state, "travel_counts", {"travel.example": 3}, "respect its repeat_limit"),
            (self.state, "cooldowns", {"token.timer": 10}, "ready time must be after"),
            (self.state["active_boosts"]["skill.example"], "expires_at_seconds", 10, "expiry must be after"),
            (self.profile["policies"], "allow_boosts", False, "conflicts with.*allow_boosts"),
            (self.state, "held_rewards", [{
                "instance_id": "instance.example", "reward_id": "reward.example", "remaining_picks": 1,
            }], "must record exactly the spent distinct skill picks"),
        ]
        for target, key, value, message in cases:
            with self.subTest(key=key, message=message):
                original = target[key]
                target[key] = value
                try:
                    with self.assertRaisesRegex(DataError, message):
                        self.check_profile()
                finally:
                    target[key] = original

    def test_solution_checks_lamp_policy_override_and_training_gate(self):
        self.reward.update(eligible_skills=["skill.example"], selection_count=1)
        self.state["xp_tenths"]["skill.other"] = 1000
        use = {
            "step_id": "step.lamp", "kind": "reward_use", "instance_id": "reward.example.instance.1",
            "reward_id": "reward.example", "skill_id": "skill.other", "gain_xp_tenths": 100,
            "overrides_observed_skill_restriction": True, "explanation": "Use the quest lamp.",
        }
        self.solution["steps"].append(use)
        self.check_solution()
        use["overrides_observed_skill_restriction"] = False
        with self.assertRaisesRegex(DataError, "must match observed eligibility"):
            self.check_solution()
        self.solution["steps"].pop()
        self.solution["steps"][0]["required_by"] = ["action.missing"]
        with self.assertRaisesRegex(DataError, "required_by.0: unknown action"):
            self.check_solution()

    def add_claim(self, quantity=1):
        effect = self.quest["effects"].pop()
        effect["quantity"] = quantity
        self.catalog["actions"].append({
            **self.quest, "id": "claim.example", "name": "Claim the reward", "kind": "reward_claim",
            "requirements": {"kind": "action_completed", "action_id": self.quest["id"]},
            "effects": [effect],
        })
        self.solution["steps"].append({
            "step_id": "step.claim", "kind": "action", "action_id": "claim.example",
            "modeled_seconds": 60, "explanation": "Make a separate reward visit.",
        })

    def spend(self, skill="skill.example", amount=100, instance=1, step_id="step.spend"):
        return {
            "step_id": step_id, "kind": "reward_use", "instance_id": f"reward.example.instance.{instance}",
            "reward_id": "reward.example", "skill_id": skill, "gain_xp_tenths": amount,
            "overrides_observed_skill_restriction": False, "explanation": "Spend one whole reward pick.",
        }

    def test_delayed_held_lamp_requires_its_own_claim(self):
        self.reward.update(selection_count=1, distinct_skills=False)
        self.add_claim()
        self.solution["steps"][-2:] = reversed(self.solution["steps"][-2:])
        with self.assertRaisesRegex(DataError, "claim precedes a required completed action"):
            self.check_solution()
        self.solution["steps"][-2:] = reversed(self.solution["steps"][-2:])
        spend = self.spend()
        self.solution["steps"].insert(-1, spend)
        with self.assertRaisesRegex(DataError, "reward instance .* unavailable"):
            self.check_solution()
        self.solution["steps"].remove(spend)
        self.solution["steps"].append({
            "step_id": "step.defer", "kind": "wait", "modeled_seconds": 1, "explanation": "Hold the lamp.",
        })
        self.solution["steps"].append(spend)
        self.check_solution()

    def test_immediate_distinct_picks_allow_no_intervening_step(self):
        self.reward["retainable"] = False
        self.state["xp_tenths"]["skill.other"] = 1000
        self.add_claim()
        first = self.spend()
        second = self.spend(skill="skill.other", step_id="step.second")
        self.solution["steps"] += [first, second]
        self.check_solution()
        second["skill_id"] = first["skill_id"]
        with self.assertRaisesRegex(DataError, "already selected"):
            self.check_solution()
        second["skill_id"] = "skill.other"
        self.solution["steps"].insert(-1, {
            "step_id": "step.defer", "kind": "wait", "modeled_seconds": 1, "explanation": "Attempt to defer a pick.",
        })
        with self.assertRaisesRegex(DataError, "resolve immediate reward"):
            self.check_solution()

    def test_level_scaled_pick_is_atomic_and_uses_base_level_at_use(self):
        self.reward.update(selection_count=1, distinct_skills=False)
        self.state["active_boosts"]["skill.other"] = {"bonus_levels": 2, "expires_at_seconds": 15}
        self.add_claim()
        spend = self.spend(skill="skill.other")
        self.solution["steps"].append(spend)
        with self.assertRaisesRegex(DataError, "requires base level 2, has 1"):
            self.check_solution()
        self.state["xp_tenths"]["skill.other"] = 3000
        with self.assertRaisesRegex(DataError, "expected a whole pick of 200"):
            self.check_solution()
        spend["gain_xp_tenths"] = 200
        self.check_solution()
        spend["gain_xp_tenths"] = 100
        self.solution["steps"].append(self.spend(skill="skill.other", amount=100, step_id="step.split"))
        with self.assertRaisesRegex(DataError, "expected a whole pick of 200"):
            self.check_solution()

    def test_two_lamps_are_separate_instances_with_one_source(self):
        self.reward.update(selection_count=1, distinct_skills=False)
        self.add_claim(quantity=2)
        second = self.spend(instance=2, step_id="step.second")
        self.solution["steps"] += [self.spend(), second]
        self.check_solution()
        second["instance_id"] = "reward.example.instance.1"
        with self.assertRaisesRegex(DataError, "reward instance .* unavailable"):
            self.check_solution()
        second["instance_id"] = "reward.example.instance.2"
        repeated = {**self.solution["steps"][2], "step_id": "step.claim_again"}
        self.solution["steps"].append(repeated)
        with self.assertRaisesRegex(DataError, "XP producer .* already used"):
            self.check_solution()

    def test_non_lamp_keeps_its_observed_eligibility(self):
        self.reward.update(kind="tome", eligible_skills=["skill.example"], selection_count=1)
        self.add_claim()
        self.solution["steps"].append(self.spend(skill="skill.other"))
        with self.assertRaisesRegex(DataError, "ineligible"):
            self.check_solution()

    def test_exact_integer_units_and_unknown_mechanic_fields(self):
        self.state["xp_tenths"]["skill.example"] = 1000.0
        with self.assertRaisesRegex(DataError, "not of type 'integer'"):
            self.check_profile()
        self.boost["effects"][0]["unmodeled_bonus"] = True
        with self.assertRaisesRegex(DataError, "validation failed"):
            self.validator()

    def test_schema_refs_never_retrieve_remote_resources(self):
        contracts = Contracts(ROOT / "schemas")
        contracts.schemas["profile"] = {"$ref": "https://example.invalid/schema"}
        with patch("socket.socket", side_effect=AssertionError("Network forbidden")):
            with self.assertRaisesRegex(DataError, "Unresolvable local schema reference"):
                contracts.validate("profile", self.profile)
