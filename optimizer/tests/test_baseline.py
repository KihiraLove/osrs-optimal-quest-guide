"""Regression checks for the pinned inventory and draft account seed."""

from pathlib import Path
import unittest

from quest_optimizer.data import Contracts, load_catalog, read_json

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
        goal_ids = [entry["goal_action_id"] for entry in journal if entry["kind"] == "quest"]
        self.assertCountEqual(self.baseline["goal_action_ids"], goal_ids)
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

    def test_start_gaps_and_scope_are_explicit(self):
        self.assertEqual(self.baseline["status"], "awaiting_capture")
        self.assertEqual(self.catalog["coverage_status"], "incomplete")
        observations = self.baseline["initial_state_observations"]
        self.assertEqual(observations["quest_points"]["value"], 1)
        for field in ("location_id", "xp_tenths", "inventory"):
            self.assertIsNone(observations[field]["value"])
            self.assertTrue(observations[field]["reason"])
        for name, validator in self.contracts.policy_validators.items():
            self.assertTrue(validator.is_valid(self.baseline["policies"][name]), name)
        self.assertEqual(self.baseline["policies"]["training_methods"], "user_choice")
        self.assertEqual(self.baseline["policies"]["quest_lamp_skill_policy"], "any_skill")
