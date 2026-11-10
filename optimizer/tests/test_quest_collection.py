"""Checks against the independent build 242 journal and source observations."""

from collections import defaultdict
from pathlib import Path
import unittest

from quest_optimizer.data import Contracts, load_catalog, read_json
from quest_optimizer.semantics import CatalogValidator


ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data"
RAW = DATA / "raw/build-242"


class QuestCollectionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.contracts = Contracts(ROOT / "schemas")
        cls.catalog = load_catalog(DATA / "manifest.json", cls.contracts)
        cls.journal = read_json(DATA / "coverage/build-242/journal.json")
        cls.observation_index = read_json(RAW / "quest-helper/index.json")
        cls.observations = defaultdict(list)
        for file in cls.observation_index["files"]:
            for observation in read_json(RAW / "quest-helper" / file):
                cls.observations[observation["activity_id"]].append(observation)
        cls.rfd = read_json(RAW / "recipe-for-disaster-review.json")

    def test_inventory_distinguishes_observed_and_collected_quests(self):
        journal_ids = {row["id"] for row in self.journal}
        missing = set(self.observation_index["missing_helper_activity_ids"])
        self.assertEqual(len(self.observations), self.observation_index["observed_activity_count"])
        self.assertEqual(journal_ids - self.observations.keys(), missing | {"quest.recipe_for_disaster"})
        self.assertEqual(
            {row["id"] for row in self.journal if row["status"] == "collected"},
            {row["id"] for row in self.catalog["activities"]},
        )
        variants = {row["helper_symbol"] for row in self.observations["quest.shield_of_arrav"]}
        self.assertEqual(variants, {"SHIELD_OF_ARRAV_BLACK_ARM_GANG", "SHIELD_OF_ARRAV_PHOENIX_GANG"})

    def test_rfd_preserves_each_stage_and_awards_points_once(self):
        stages = self.rfd["stages"]
        self.assertCountEqual(
            [stage["activity_id"] for stage in stages],
            [row["id"] for row in self.journal if row.get("parent_id") == "quest.recipe_for_disaster"],
        )
        self.assertEqual(sum(stage["completion_rewards"]["quest_points"] for stage in stages), 10)
        self.assertEqual(self.rfd["parent_goal"]["completion_effects"], [])
        for stage in stages:
            source = self.observations[stage["activity_id"]][0]
            fixed_xp = {
                award["skill_id"]: award["xp_tenths"]
                for award in source["declared_xp"].get("observations", [])
            }
            self.assertEqual(stage["completion_rewards"]["fixed_xp_tenths"], fixed_xp)
        finale = stages[-1]
        self.assertEqual(finale["completion_action_id"], self.rfd["parent_goal"]["requires_action_id"])
        self.assertEqual(finale["completion_rewards"]["choice_reward"]["xp_tenths"], 200000)
        self.assertIsNone(finale["completion_rewards"]["choice_reward"]["minimum_level"])
        requirements = finale["progression_requirements"]["requirements"]
        self.assertIn({"kind": "counter", "token_id": "token.quest_points", "minimum": 175}, requirements)
        previous_completions = {stage["completion_action_id"] for stage in stages[:-1]}
        self.assertTrue(previous_completions <= {rule.get("action_id") for rule in requirements})

    def test_pirate_pete_preserves_account_specific_or_observation(self):
        [source] = self.observations["rfd.freeing_pirate_pete"]
        [ironman] = [
            row["observation"]
            for row in source["general_requirements"]["observations"]
            if row["guards"] == ["ironman"]
        ]
        self.assertEqual(ironman["kind"], "or")
        self.assertEqual({rule["kind"] for rule in ironman["requirements"]}, {"quest", "skill"})
        stage = next(stage for stage in self.rfd["stages"] if stage["activity_id"] == "rfd.freeing_pirate_pete")
        self.assertEqual(stage["skill_checks"], [
            {"kind": "skill", "skill_id": "skill.cooking", "minimum_level": 31, "boostable": False},
        ])

    def test_publisher_reward_delta_and_separate_claim(self):
        rewards = read_json(RAW / "quest-month-rewards.json")["changes"]
        by_activity = {change["activity_id"]: change for change in rewards}
        self.assertEqual(len(by_activity), 18)
        self.assertEqual(by_activity["quest.demon_slayer"]["claim_id"], "claim.demon_slayer.aris")
        rune_actions = [row for row in self.catalog["actions"] if row["activity_id"] == "quest.rune_mysteries"]
        xp_effects = [
            (row["id"], effect["xp_tenths"])
            for row in rune_actions for effect in row["effects"] if effect["kind"] == "xp"
        ]
        expected = by_activity["quest.rune_mysteries"]["fixed_xp_tenths"]["skill.runecraft"]
        self.assertEqual(xp_effects, [("quest.rune_mysteries.complete", expected)])

    def test_cooks_assistant_fixture_has_supplies_and_completion_effects(self):
        profile = read_json(ROOT / "examples/build-242/cooks-assistant-profile.json")
        self.contracts.validate("profile", profile)
        CatalogValidator(self.catalog, self.contracts).validate_profile(profile)
        [goal_id] = profile["goal_action_ids"]
        action = next(row for row in self.catalog["actions"] if row["id"] == goal_id)
        self.assertEqual(action["start_location_id"], profile["initial_state"]["location_id"])
        self.assertEqual({item["item_id"]: item["quantity"] for item in action["consumes"]},
                         profile["initial_state"]["inventory"])
        self.assertIn({"kind": "xp", "skill_id": "skill.cooking", "xp_tenths": 3000}, action["effects"])
        self.assertIn({"kind": "counter", "token_id": "token.quest_points", "delta": 1}, action["effects"])
