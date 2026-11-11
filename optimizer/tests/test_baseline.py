"""Regression checks for the pinned inventory and draft account seed."""

from pathlib import Path
import unittest

from quest_optimizer.bounded_search import solve_bounded
from quest_optimizer.data import Contracts, DataError, load_catalog, read_json
from quest_optimizer.replay import verify_solution
from quest_optimizer.semantics import CatalogValidator

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data"
COVERAGE = DATA / "coverage"


def evidence_references(value):
    if isinstance(value, dict):
        yield from value.get("source_ids", ())
        if "source_id" in value:
            yield value["source_id"]
        for child in value.values():
            yield from evidence_references(child)
    elif isinstance(value, list):
        for child in value:
            yield from evidence_references(child)


class Build242BaselineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.contracts = Contracts(ROOT / "schemas")
        cls.catalog = load_catalog(DATA / "manifest.json", cls.contracts)
        cls.ledger = read_json(COVERAGE / "build-242.json")
        cls.entries = {kind: read_json(COVERAGE / path) for kind, path in cls.ledger["entries"].items()}
        cls.baseline = read_json(DATA / "profiles/main-baseline.json")
        cls.skills = read_json(DATA / "raw/build-242/skills.json")
        cls.reconciliation = read_json(DATA / "raw/build-242/reconciliation.json")

    def test_snapshot_identity_and_evidence(self):
        for field in ("dataset_id", "dataset_version", "game_revision", "as_of"):
            self.assertEqual(self.ledger[field], self.catalog[field])
        for field in ("dataset_id", "dataset_version"):
            self.assertEqual(self.baseline[field], self.catalog[field])
        self.assertEqual(self.catalog["as_of"], self.ledger["snapshot"]["cache_timestamp_utc"][:10])
        sources = {source["id"] for source in self.catalog["sources"]}
        documents = [self.ledger, self.baseline, self.entries, self.skills, self.reconciliation]
        self.assertEqual(set(evidence_references(documents)) - sources, set())

    def test_catalog_skill_tables_match_the_recorded_source(self):
        skills = {skill["id"]: skill for skill in self.catalog["skills"]}
        self.assertCountEqual(skills, [skill["id"] for skill in self.ledger["skills"]])
        self.assertCountEqual(skills, [skill["id"] for skill in self.skills["skill_index"]])
        curve = self.skills["base_level_thresholds_tenths"]
        self.assertEqual(len(curve), 99)
        self.assertEqual((curve[0], curve[9], curve[-1]), (0, 11540, 130344310))
        self.assertIn("skill.sailing", skills)
        for skill in skills.values():
            self.assertEqual(skill["xp_thresholds_tenths"], curve)

    def test_goals_keep_journal_identity_and_separate_subquests(self):
        journal = self.entries["journal"]
        self.assertEqual(len(journal), 216)
        self.assertEqual(len({entry["id"] for entry in journal}), len(journal))
        self.assertEqual(len({entry["client_quest_id"] for entry in journal}), len(journal))
        goal_ids = [entry["goal_action_id"] for entry in journal
                    if entry["kind"] == "quest" and entry["status"] != "excluded"]
        self.assertCountEqual(self.baseline["goal_action_ids"], goal_ids)
        tutorial = next(row for row in journal if row["id"] == "quest.learning_the_ropes")
        self.assertEqual(tutorial["status"], "excluded")
        self.assertNotIn("goal_action_id", tutorial)
        self.assertIn("quest.daddys_home.complete", goal_ids)
        self.assertIn("quest.recipe_for_disaster.complete", goal_ids)
        subquests = [entry for entry in journal if entry["kind"] == "subquest"]
        self.assertEqual(len(subquests), 10)
        self.assertTrue(all(entry["parent_id"] == "quest.recipe_for_disaster" for entry in subquests))
        self.assertTrue(all("goal_action_id" not in entry for entry in journal if entry["kind"] != "quest"))

    def test_diary_trackers_are_unique_at_this_revision(self):
        regions = self.entries["diaries"]["regions"]
        tiers = [tier for region in regions for tier in region["tiers"]]
        tasks = [task for tier in tiers for task in tier["tasks"]]
        self.assertEqual((len(regions), len(tiers), len(tasks)), (12, 48, 492))
        trackers = {(task["tracker"]["kind"], task["tracker"]["id"], task["tracker"].get("bit")) for task in tasks}
        self.assertEqual(len(trackers), len(tasks))
        self.assertEqual(len({tier["reward_claim_id"] for tier in tiers}), len(tiers))

    def test_lumbridge_baseline_has_only_the_tutorial_quest_point(self):
        self.contracts.validate("profile", self.baseline)
        self.assertEqual(self.baseline["status"], "draft")
        self.assertEqual(self.catalog["coverage_status"], "incomplete")
        initial = self.baseline["initial_state"]
        self.assertEqual(initial["location_id"], "location.lumbridge.castle_courtyard")
        self.assertEqual(initial["counters"], {"token.quest_points": 1})
        self.assertEqual(initial["completed_action_ids"], [])
        self.assertEqual(initial["inventory"], {})
        self.assertEqual(initial["flags"], {})
        self.assertEqual(initial["held_rewards"], [])
        expected_xp = {skill["id"]: 0 for skill in self.catalog["skills"]}
        expected_xp["skill.hitpoints"] = 11540
        self.assertEqual(initial["xp_tenths"], expected_xp)
        for name, validator in self.contracts.policy_validators.items():
            self.assertTrue(validator.is_valid(self.baseline["policies"][name]), name)
        self.assertEqual(self.baseline["policies"]["training_methods"], "user_choice")
        self.assertEqual(self.baseline["policies"]["quest_lamp_skill_policy"], "any_skill")

    def test_starter_route_buys_supplies_and_keeps_the_initial_quest_point(self):
        profile = read_json(ROOT / "examples/build-242/lumbridge-arrival-profile.json")
        self.assertEqual(profile["initial_state"], self.baseline["initial_state"])
        self.assertEqual(profile["policies"], self.baseline["policies"])
        self.assertLess(set(profile["goal_action_ids"]), set(self.baseline["goal_action_ids"]))
        validator = CatalogValidator(self.catalog, self.contracts)
        solution, _ = solve_bounded(validator, profile)
        report = verify_solution(solution, profile, validator)
        self.assertEqual(report["manual_training_xp_tenths_by_skill"], {})
        self.assertEqual(report["final_state"]["counters"]["token.quest_points"], 5)
        self.assertEqual(report["final_state"]["xp_tenths"]["skill.hitpoints"], 11540)
        purchases = [step["action_id"] for step in solution["steps"]
                     if step.get("action_id", "").startswith("supply.grand_exchange.")]
        self.assertCountEqual(purchases, [
            "supply.grand_exchange.cooks_assistant", "supply.grand_exchange.sheep_shearer", "supply.grand_exchange.spade",
        ])
        for purchase in purchases:
            record = validator.tables["actions"][purchase]
            self.assertTrue(all(
                effect["kind"] == "item" and validator.tables["items"][effect["item_id"]]["tradeable"]
                for effect in record["effects"]
            ))
        without_ingredients = {**solution, "steps": [
            step for step in solution["steps"] if step.get("action_id") != "supply.grand_exchange.cooks_assistant"
        ]}
        with self.assertRaisesRegex(DataError, "required items"):
            verify_solution(without_ingredients, profile, validator)
