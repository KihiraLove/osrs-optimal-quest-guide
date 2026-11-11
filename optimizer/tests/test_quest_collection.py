"""Checks against the independent build 242 journal and source observations."""

from collections import defaultdict
from pathlib import Path
import unittest

from quest_optimizer.bounded_search import solve_bounded
from quest_optimizer.data import Contracts, DataError, load_catalog, read_json
from quest_optimizer.replay import verify_solution
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
            {row["id"] for row in self.catalog["activities"] if row["kind"] in ("quest", "subquest", "miniquest")},
        )
        variants = {row["helper_symbol"] for row in self.observations["quest.shield_of_arrav"]}
        self.assertEqual(variants, {"SHIELD_OF_ARRAV_BLACK_ARM_GANG", "SHIELD_OF_ARRAV_PHOENIX_GANG"})

    def test_restless_ghost_replays_from_lumbridge_with_no_manual_xp(self):
        quest = "quest.the_restless_ghost"
        [source] = self.observations[quest]
        review = read_json(RAW / "restless-ghost-review.json")
        profile = read_json(ROOT / "examples/build-242/restless-ghost-profile.json")
        validator = CatalogValidator(self.catalog, self.contracts)
        solution, _ = solve_bounded(validator, profile, max_expansions=4000)
        verify_solution(solution, profile, validator)
        self.assertEqual(solution["manual_training_xp_tenths_by_skill"], {})
        self.assertEqual([step["action_id"] for step in solution["steps"] if step["kind"] == "action"], review["stages"])
        expected_xp = profile["initial_state"]["xp_tenths"].copy()
        for reward in source["declared_xp"]["observations"]:
            expected_xp[reward["skill_id"]] += reward["xp_tenths"]
        state = solution["final_state"]
        self.assertEqual(state["xp_tenths"], expected_xp)
        self.assertEqual(state["inventory"], {"item.ghostspeak_amulet": 1})
        self.assertEqual(state["counters"]["token.quest_points"], 1)
        ladders = {step.get("edge_id") for step in solution["steps"]}
        self.assertTrue({
            "travel.walk.wizards_tower.basement_ladder.out", "travel.walk.wizards_tower.basement_ladder.back",
        } <= ladders)

        for stage in ("get_amulet", "take_skull"):
            with self.subTest(stage=stage):
                skipped = {**solution, "steps": [
                    step for step in solution["steps"] if step.get("action_id") != f"{quest}.{stage}"
                ]}
                with self.assertRaisesRegex(DataError, r"steps\.\d+ .* required completed action"):
                    verify_solution(skipped, profile, validator)

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

    def test_reward_registry_tracks_claims_separately_from_completion(self):
        registry = read_json(RAW / "reward-registry.json")
        entries = registry["entries"]
        exclusions = registry["exclusions"]
        known_sources = {source["id"] for source in self.catalog["sources"]}
        records = entries + exclusions
        self.assertEqual(len({row["id"] for row in records}), len(records))
        self.assertTrue({source for row in records for source in row["source_ids"]} <= known_sources)
        claims = [row for row in entries if row["delivery"] == "post_quest_claim"]
        self.assertEqual(len({row["producer_action_id"] for row in claims}), len(claims))
        for claim in claims:
            self.assertIn({
                "kind": "action_completed", "action_id": claim["activity_id"] + ".complete",
            }, claim["requires"]["requirements"])
            self.assertEqual(claim["repeat_limit"], 1)
        aris = next(claim for claim in claims if claim["id"] == "claim.demon_slayer.aris")
        self.assertEqual(aris["claim_location"]["tile"], [3204, 3424, 0])
        self.assertEqual(aris["package"]["quantity"], 2)
        self.assertEqual(aris["package"]["amount"], {"kind": "fixed", "xp_tenths": 10000})
        self.assertIsNone(aris["package"]["minimum_level"])
        self.assertTrue(all(row["status"] == "excluded" and row["reason"] for row in exclusions))

    def test_catalog_lamp_is_spendable_after_veos_awards_it(self):
        reward_id = "reward.x_marks_the_spot.ancient_lamp"
        producers = [
            action for action in self.catalog["actions"]
            if any(effect.get("reward_id") == reward_id for effect in action["effects"])
        ]
        [completion] = producers
        self.assertEqual(completion["id"], "quest.x_marks_the_spot.complete")
        profile = read_json(ROOT / "examples/build-242/cooks-assistant-profile.json")
        profile["profile_id"] = "profile.fixture.veos"
        profile["goal_action_ids"] = [completion["id"]]
        profile["initial_state"].update(
            location_id=completion["start_location_id"],
            inventory={"item.ancient_casket.x_marks_the_spot": 1},
            completed_action_ids=[
                action["id"] for action in self.catalog["actions"]
                if action["activity_id"] == completion["activity_id"] and action != completion
            ],
        )
        solution = read_json(ROOT / "examples/synthetic/solution.json")
        solution["inputs"].update(
            dataset_id=profile["dataset_id"], dataset_version=profile["dataset_version"],
            profile_id=profile["profile_id"],
        )
        solution["policies"] = profile["policies"]
        solution["objective"].update(manual_training_xp_tenths=0, modeled_non_training_seconds=20)
        solution["manual_training_xp_tenths_by_skill"] = {}
        solution["steps"] = [
            {"step_id": "step.veos", "kind": "action", "action_id": completion["id"],
             "modeled_seconds": 20, "explanation": "Complete the quest and receive one lamp."},
            {"step_id": "step.spend", "kind": "reward_use", "reward_id": reward_id,
             "instance_id": reward_id + ".instance.1", "skill_id": "skill.agility",
             "gain_xp_tenths": 3000, "overrides_observed_skill_restriction": False,
             "explanation": "Use the whole lamp on Agility."},
        ]
        state = profile["initial_state"]
        solution["final_state"] = {
            **state, "xp_tenths": {**state["xp_tenths"], "skill.agility": 3000},
            "completed_action_ids": state["completed_action_ids"] + [completion["id"]],
            "inventory": {"item.coins": 200}, "counters": {"token.quest_points": 1},
            "modeled_elapsed_seconds": 20,
        }
        validator = CatalogValidator(self.catalog, self.contracts)
        self.contracts.validate("profile", profile)
        validator.validate_profile(profile)
        self.contracts.validate("solution", solution)
        validator.validate_solution(solution, profile)
