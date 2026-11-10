"""Regression checks for the build 242 museum route and partial quiz profile."""

from pathlib import Path
import unittest

from quest_optimizer.data import Contracts, DataError, load_catalog, read_json
from quest_optimizer.reward_trace import RewardTrace
from quest_optimizer.semantics import CatalogValidator


ROOT = Path(__file__).resolve().parents[2]
EXAMPLES = ROOT / "examples/build-242"
RAW = ROOT / "data/raw/build-242"
QUIZ = "museum.natural_history_quiz"
KUDOS = "token.museum.kudos"
DIG_SITE = "flag.quest.the_dig_site.complete"
ISLAND = "unlock.fossil_island"


class MuseumTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.contracts = Contracts(ROOT / "schemas")
        cls.catalog = load_catalog(ROOT / "data/manifest.json", cls.contracts)
        cls.actions = {row["id"]: row for row in cls.catalog["actions"]}
        cls.edges = {row["id"]: row for row in cls.catalog["travel_edges"]}
        cls.locations = {row["id"]: row for row in cls.catalog["locations"]}
        cls.review = read_json(RAW / "museum-review.json")
        cls.validator = CatalogValidator(cls.catalog, cls.contracts)

    def setUp(self):
        self.profile = read_json(EXAMPLES / "museum-quiz-profile.json")
        self.solution = read_json(EXAMPLES / "museum-quiz-solution.json")

    def test_all_plaque_tiles_and_one_time_kudos_match_the_inventory(self):
        inventory = read_json(ROOT / "data/coverage/build-242/optional-activities.json")
        plaque_ids = {
            row["id"] for row in inventory if row["id"].startswith(QUIZ + ".")
        }
        self.assertEqual(len(plaque_ids), 14)
        self.assertEqual(plaque_ids, {row["id"] for row in self.review["quiz"]["plaque_actions"]})
        objects = read_json(RAW / "museum-map.json")["objects"]
        plaque_tiles = {
            obj["object_id"]: obj["tile"] for obj in objects if obj["symbol"].startswith("VM_PLAQUE_")
        }
        for plaque in self.review["quiz"]["plaque_actions"]:
            action = self.actions[plaque["id"]]
            location = self.locations[action["start_location_id"]]
            self.assertEqual([location["x"], location["y"], location["plane"]], plaque_tiles[plaque["object_id"]])
            self.assertEqual(action["effects"], [{"kind": "counter", "token_id": KUDOS, "delta": 2}])
            self.assertEqual(action["repeat_limit"], 1)
        claim = self.actions["claim." + QUIZ]
        self.assertEqual({rule["action_id"] for rule in claim["requirements"]["requirements"]}, plaque_ids)
        self.assertEqual(
            {effect["skill_id"]: effect["xp_tenths"] for effect in claim["effects"]},
            {"skill.hunter": 10000, "skill.slayer": 10000},
        )
        self.assertEqual(claim["repeat_limit"], 1)

    def test_final_plaque_reaches_quest_gate_and_award_is_separate(self):
        self.contracts.validate("profile", self.profile)
        self.validator.validate_profile(self.profile)
        self.contracts.validate("solution", self.solution)
        self.validator.validate_solution(self.solution, self.profile)

        location = self.profile["initial_state"]["location_id"]
        for step in self.solution["steps"]:
            if step["kind"] == "action":
                record = self.actions[step["action_id"]]
                self.assertEqual(record["start_location_id"], location)
                location = record["end_location_id"]
            else:
                record = self.edges[step["edge_id"]]
                self.assertEqual(record["from_location_id"], location)
                location = record["to_location_id"]
            self.assertEqual(record["duration"]["expected_seconds"], step["modeled_seconds"])
        self.assertEqual(location, self.solution["final_state"]["location_id"])
        self.assertEqual(self.profile["initial_state"]["counters"][KUDOS], 98)
        self.assertEqual(self.solution["final_state"]["counters"][KUDOS], 100)

    def test_start_requires_100_kudos_and_dig_site_completion(self):
        self.profile["initial_state"]["counters"][KUDOS] = 97
        with self.assertRaisesRegex(DataError, "counter threshold has not been reached"):
            self.validator.validate_solution(self.solution, self.profile)
        self.profile["initial_state"]["counters"][KUDOS] = 98
        del self.profile["initial_state"]["flags"][DIG_SITE]
        with self.assertRaisesRegex(DataError, "flag or counter threshold"):
            self.validator.validate_solution(self.solution, self.profile)

    def test_bone_voyage_accepts_kudos_with_quiz_xp_unclaimed(self):
        claim_id = "claim." + QUIZ
        claim = next(step for step in self.solution["steps"] if step.get("action_id") == claim_id)
        self.solution["steps"].remove(claim)
        self.solution["objective"]["modeled_non_training_seconds"] -= claim["modeled_seconds"]
        final = self.solution["final_state"]
        final["completed_action_ids"].remove(claim_id)
        final["modeled_elapsed_seconds"] -= claim["modeled_seconds"]
        final["xp_tenths"] = self.profile["initial_state"]["xp_tenths"].copy()
        self.validator.validate_solution(self.solution, self.profile)

    def test_early_or_repeated_claim_and_repeated_plaque_are_rejected(self):
        plaque, *_, claim, stairs, start = self.solution["steps"]
        self.solution["steps"] = [claim, plaque, stairs, start]
        with self.assertRaisesRegex(DataError, "reward claim precedes"):
            self.validator.validate_solution(self.solution, self.profile)
        self.solution["steps"] = [plaque, {**plaque, "step_id": "step.repeat"}, claim, stairs, start]
        with self.assertRaisesRegex(DataError, "one-time transition .* already used"):
            self.validator.validate_solution(self.solution, self.profile)
        self.solution["steps"] = [plaque, claim, {**claim, "step_id": "step.repeat"}, stairs, start]
        with self.assertRaisesRegex(DataError, "XP producer .* already used"):
            self.validator.validate_solution(self.solution, self.profile)

    def test_forged_kudos_total_is_rejected(self):
        self.solution["final_state"]["counters"][KUDOS] += 1
        with self.assertRaisesRegex(DataError, "final_state.counters"):
            self.validator.validate_solution(self.solution, self.profile)

    def test_camp_waypoints_and_barge_require_island_unlock(self):
        finish = self.actions["quest.bone_voyage.complete"]
        island_gate = {"kind": "flag", "token_id": ISLAND, "value": True}
        self.assertIn(island_gate, finish["effects"])
        camp = self.review["camp"]
        self.assertEqual(finish["end_location_id"], camp["arrival_location_id"])
        for facility in camp["facilities"]:
            outbound, inbound = (self.edges[id] for id in facility["access_edge_ids"])
            self.assertEqual(outbound["from_location_id"], camp["hub_location_id"])
            self.assertEqual(outbound["to_location_id"], facility["location_id"])
            self.assertEqual(inbound["to_location_id"], camp["hub_location_id"])
            self.assertEqual(inbound["from_location_id"], facility["location_id"])
            self.assertEqual(outbound["requirements"], island_gate)
            self.assertEqual(inbound["requirements"], island_gate)

        initial = self.profile["initial_state"]
        initial["completed_action_ids"].append("quest.bone_voyage.get_potion")
        initial["inventory"] = {item["item_id"]: item["quantity"] for item in finish["consumes"]}
        trace = RewardTrace(
            self.validator.tables["skills"], self.validator.tables["xp_rewards"],
            self.validator.tables["tokens"], initial, "barge progression fixture",
        )
        with self.assertRaisesRegex(DataError, "flag or counter threshold"):
            trace.award(self.edges["travel.fossil_island.barge.out"], "before_voyage")
        trace.award(finish, "voyage_completion")
        trace.award(self.edges["travel.fossil_island.barge.back"], "after_voyage")

    def test_defender_of_varrock_uses_one_history_and_lamp_claim(self):
        [report] = [row for row in self.review["history_reports"] if row["id"] == "museum.history.dov"]
        registry = read_json(RAW / "reward-registry.json")["entries"]
        [claim] = [entry for entry in registry if entry["id"] == report["reward_claim_id"]]
        self.assertEqual(claim["other_effects"]["kudos"], report["kudos"])
        self.assertEqual(claim["repeat_limit"], report["repeat_limit"])
