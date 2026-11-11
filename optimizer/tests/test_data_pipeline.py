"""Coverage release gates and deterministic offline normalization."""

from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
import json
from pathlib import Path
import shutil
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from quest_optimizer.cli import main
from quest_optimizer.coverage import audit_coverage
from quest_optimizer.data import Contracts, DataError, load_catalog, read_json
from quest_optimizer.normalization import canonical_json, catalog_diff, normalize_catalog


ROOT = Path(__file__).resolve().parents[2]
EXAMPLE = ROOT / "examples/synthetic"


class DataPipelineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.contracts = Contracts(ROOT / "schemas")

    def setUp(self):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.folder = Path(directory.name) / "dataset"
        shutil.copytree(EXAMPLE, self.folder)
        self.manifest = self.folder / "manifest.json"

    def write(self, name, value):
        path = self.folder / name
        path.write_bytes(canonical_json(value).encode("utf-8"))
        return path

    def reviewed_fixture(self):
        manifest = read_json(self.manifest)
        manifest.update(
            status="reviewed", coverage_status="complete", game_revision="fixture-build", as_of="2026-11-03",
            coverage_ledger="coverage.json", release_profile="profile.json",
        )
        self.write("manifest.json", manifest)
        profile = read_json(self.folder / "profile.json")
        profile.update(status="reviewed")
        self.write("profile.json", profile)
        for name, files in manifest["collections"].items():
            rows = read_json(self.folder / files[0])
            for row in rows:
                if name == "sources":
                    row.update(kind="in_game", license="Original fixture observation")
                else:
                    row["evidence"]["status"] = "verified"
            self.write(files[0], rows)
        evidence = {"source_ids": ["source.synthetic"], "status": "reviewed"}
        self.write("coverage.json", {
            "ledger_version": 1,
            **{field: manifest[field] for field in ("dataset_id", "dataset_version", "game_revision", "as_of")},
            "entries": {name: f"{name}.json" for name in ("journal", "diaries", "reward_reviews", "optional_activities")},
            "skills": [{"id": "skill.example", **evidence}],
            "open_reviews": [],
            "reconciliation": "reconciliation.json",
            "attribution": "ATTRIBUTION.md",
        })
        self.write("journal.json", [{
            "id": "activity.example", "kind": "quest", "client_quest_id": 1,
            "goal_action_id": "action.example", "completion_reward_review_id": "review.example.reward", **evidence,
        }])
        self.write("diaries.json", {"regions": []})
        self.write("optional_activities.json", [])
        [action] = read_json(self.folder / "actions.json")
        self.write("reward_reviews.json", [{
            "id": "review.example.reward", "catalog_ids": ["action.example"],
            "expected_effects": {"action.example": action["effects"]}, **evidence,
        }])
        self.write("reconciliation.json", {"revision": "fixture-build", "observations": []})
        (self.folder / "ATTRIBUTION.md").write_text("Original fixture observation.\n", encoding="utf-8")

    def test_complete_reviewed_catalog_can_pass_release_offline(self):
        self.reviewed_fixture()
        with patch("socket.socket", side_effect=AssertionError("Network forbidden")):
            catalog = load_catalog(self.manifest, self.contracts, release=True)
            report = audit_coverage(self.manifest, catalog, self.contracts)
        self.assertTrue(report["release_ready"])
        self.assertEqual(report["unreachable"], {"actions": [], "locations": [], "travel_edges": []})

    def test_review_status_cannot_hide_a_missing_inventory_record(self):
        self.reviewed_fixture()
        journal = read_json(self.folder / "journal.json")
        journal.append({**journal[0], "id": "quest.missing", "client_quest_id": 2, "goal_action_id": "quest.missing.complete"})
        self.write("journal.json", journal)
        with self.assertRaisesRegex(DataError, "quest.missing.*missing or has the wrong type"):
            load_catalog(self.manifest, self.contracts, release=True)

    def test_reward_conflict_and_missing_exclusion_reason_block_release(self):
        self.reviewed_fixture()
        rows = read_json(self.folder / "reward_reviews.json")
        rows[0]["expected_effects"]["action.example"][0]["xp_tenths"] = 499
        self.write("reward_reviews.json", rows)
        with self.assertRaisesRegex(DataError, "effects differ"):
            load_catalog(self.manifest, self.contracts, release=True)
        self.write("optional_activities.json", [{"id": "scope.incomplete", "status": "excluded"}])
        with self.assertRaisesRegex(DataError, "scope.incomplete.reason"):
            load_catalog(self.manifest, self.contracts, release=True)

    def test_disconnected_location_and_one_way_edge_are_detected(self):
        self.reviewed_fixture()
        locations = read_json(self.folder / "locations.json")
        locations.append({**locations[0], "id": "location.remote"})
        self.write("locations.json", locations)
        actions = read_json(self.folder / "actions.json")
        actions[0].update(start_location_id="location.remote", end_location_id="location.remote")
        self.write("actions.json", actions)
        self.write("travel_edges.json", [{
            "id": "travel.return", "name": "Return", "mode": "walk",
            "from_location_id": "location.remote", "to_location_id": "location.example",
            "requirements": {"kind": "all", "requirements": []}, "consumes": [], "effects": [],
            "duration": actions[0]["duration"], "evidence": actions[0]["evidence"],
        }])
        with self.assertRaisesRegex(DataError, "location.remote: unreachable"):
            load_catalog(self.manifest, self.contracts, release=True)

    def test_or_branch_can_break_a_phase_cycle(self):
        self.reviewed_fixture()
        [goal] = read_json(self.folder / "actions.json")
        phase = {**goal, "id": "action.phase", "effects": [],
                 "requirements": {"kind": "action_completed", "action_id": goal["id"]}}
        hard_dependency = {"kind": "action_completed", "action_id": phase["id"]}
        goal["requirements"] = {"kind": "any", "requirements": [hard_dependency, goal["requirements"]]}
        self.write("actions.json", [goal, phase])
        load_catalog(self.manifest, self.contracts, release=True)
        goal["requirements"] = hard_dependency
        self.write("actions.json", [goal, phase])
        catalog = load_catalog(self.manifest, self.contracts)
        report = audit_coverage(self.manifest, catalog, self.contracts)
        self.assertEqual(report["unreachable"]["actions"], ["action.example", "action.phase"])
        with self.assertRaisesRegex(DataError, "action.example: unreachable"):
            load_catalog(self.manifest, self.contracts, release=True)

    def test_disabled_optional_route_remains_visible_in_a_passing_audit(self):
        self.reviewed_fixture()
        [goal] = read_json(self.folder / "actions.json")
        optional = {
            **goal, "id": "action.poh_service", "activity_id": None, "kind": "supply", "effects": [],
            "requirements": {"kind": "policy", "name": "allow_poh_services", "value": True},
        }
        self.write("actions.json", [goal, optional])
        catalog = load_catalog(self.manifest, self.contracts, release=True)
        report = audit_coverage(self.manifest, catalog, self.contracts)
        self.assertEqual(report["unreachable"]["actions"], ["action.poh_service"])

    def test_counter_gate_respects_finite_awards(self):
        self.reviewed_fixture()
        [goal] = read_json(self.folder / "actions.json")
        self.write("tokens.json", [{
            "id": "token.points", "name": "Points", "kind": "counter", "maximum": 5, "evidence": goal["evidence"],
        }])
        phase = {
            **goal, "id": "action.phase", "requirements": {"kind": "all", "requirements": []},
            "effects": [{"kind": "counter", "token_id": "token.points", "delta": 3}],
        }
        goal["requirements"] = {"kind": "counter", "token_id": "token.points", "minimum": 4}
        self.write("actions.json", [goal, phase])
        with self.assertRaisesRegex(DataError, "action.example: unreachable"):
            load_catalog(self.manifest, self.contracts, release=True)
        phase["effects"][0]["delta"] = 4
        self.write("actions.json", [goal, phase])
        load_catalog(self.manifest, self.contracts, release=True)

    def test_pinned_catalog_audit_and_normalization_are_offline(self):
        path = ROOT / "data/manifest.json"
        with patch("socket.socket", side_effect=AssertionError("Network forbidden")):
            catalog = load_catalog(path, self.contracts)
            audit = audit_coverage(path, catalog, self.contracts)
            skills = ROOT / "data/raw/build-242/skills.json"
            first = canonical_json(normalize_catalog(catalog, self.contracts, [], skills=skills))
            second = canonical_json(normalize_catalog(catalog, self.contracts, [], skills=skills))
        self.assertEqual(audit["errors"], [])
        self.assertFalse(audit["release_ready"])
        journal = read_json(ROOT / "data/coverage/build-242/journal.json")
        self.assertEqual(
            audit["coverage_counts"]["journal"]["expected"],
            sum(entry["status"] == "expected" for entry in journal),
        )
        self.assertEqual(first.encode("utf-8"), second.encode("utf-8"))

    def test_aliases_tiles_and_fractional_xp_normalize_and_diff(self):
        catalog = load_catalog(self.manifest, self.contracts)
        [location] = catalog["locations"]
        tile = [location[key] for key in ("x", "y", "plane")]
        new_location = {key: value for key, value in location.items() if key not in ("x", "y", "plane")}
        new_location.update(id="New spot", tile=tile)
        [action] = catalog["actions"]
        new_action = {**action, "id": "action.bonus", "start_location_id": "New spot", "effects": [
            {"kind": "xp", "skill_id": "Example", "xp": "62.50"},
        ]}
        batch = self.write("batch.json", {
            "batch_version": 1, "game_revision": None,
            "aliases": {"New spot": "location.new", "Example": "skill.example"},
            "collections": {"actions": [new_action], "locations": [new_location]},
        })
        normalized = normalize_catalog(catalog, self.contracts, [batch])
        [added] = [row for row in normalized["actions"] if row["id"] == "action.bonus"]
        self.assertEqual(added["effects"][0]["xp_tenths"], 625)
        self.assertEqual(added["start_location_id"], "location.new")
        diff = catalog_diff(catalog, normalized)
        self.assertEqual(diff["actions"]["added"], ["action.bonus"])
        self.assertEqual(diff["locations"]["added"], ["location.new"])
        self.assertEqual(catalog_diff(normalized, catalog)["actions"]["removed"], ["action.bonus"])
        added["effects"][0]["xp_tenths"] = 626
        before = normalize_catalog(catalog, self.contracts, [batch])
        self.assertEqual(
            catalog_diff(before, normalized)["actions"]["changed"]["action.bonus"]["effects"]["after"],
            added["effects"],
        )

    def test_conflicts_and_unknowns_emit_queue_without_normalized_output(self):
        catalog = load_catalog(self.manifest, self.contracts)
        [location] = catalog["locations"]
        batch = self.write("batch.json", {
            "batch_version": 1, "game_revision": None, "collections": {"locations": [
                {**location, "x": location["x"] + 1},
                {**location, "id": "location.unknown", "unknown_fields": ["x"]},
            ]},
        })
        output, error = StringIO(), StringIO()
        with redirect_stdout(output), redirect_stderr(error):
            code = main(["--schemas", str(ROOT / "schemas"), "normalize-data", str(self.manifest),
                         "--observations", str(batch)])
        self.assertEqual(code, 2)
        self.assertEqual(output.getvalue(), "")
        queue = json.loads(error.getvalue())["review_queue"]
        self.assertCountEqual([entry["kind"] for entry in queue], ["conflict", "unknown"])

    def test_malformed_batch_fails_clearly(self):
        catalog = load_catalog(self.manifest, self.contracts)
        [action] = catalog["actions"]
        action["effects"][0]["xp"] = "0.01"
        batch = self.write("batch.json", {
            "batch_version": 1, "game_revision": None, "collections": {"actions": [action]},
        })
        with self.assertRaisesRegex(DataError, "xp must be an exact"):
            normalize_catalog(catalog, self.contracts, [batch])
