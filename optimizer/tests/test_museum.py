"""Regression checks for the build 242 museum route and partial quiz profile."""

from pathlib import Path
import unittest

from quest_optimizer.data import Contracts, DataError, load_catalog, read_json
from quest_optimizer.reward_trace import RewardTrace
from quest_optimizer.semantics import CatalogValidator
from quest_optimizer.transitions import RouteState


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

    def fossil_route(self, state, *records):
        for record_id in records:
            if record_id in self.edges:
                record = self.edges[record_id]
                step = {"kind": "travel", "edge_id": record_id}
            else:
                record = self.actions[record_id]
                step = {"kind": "action", "action_id": record_id}
            state = state.apply({**step, "modeled_seconds": record["duration"]["expected_seconds"]})
        return state

    def finish_bone_voyage(self, **tools):
        initial = dict(self.profile["initial_state"], location_id="location.digsite.barge_wharf",
                       completed_action_ids=["quest.bone_voyage.get_potion"],
                       inventory={"item.bone_voyage.bone_charm": 1, "item.bone_voyage.potion_of_sealegs": 1, **tools})
        state = RouteState(self.validator.tables, self.profile["policies"], initial)
        with self.assertRaises(DataError):
            self.fossil_route(state, "travel.fossil_island.barge.out")
        return self.fossil_route(state, "quest.bone_voyage.complete")

    def test_mushtrees_require_local_discovery_and_allow_return_trips(self):
        travel = "travel.fossil_island."
        discover = "transport.fossil_island.mushtree."
        ride = travel + "mushtree."
        walk = travel + "walk."
        state = self.fossil_route(self.finish_bone_voyage(), travel + "camp_pier.out",
                                  walk + "valley_mushtree.out", discover + "verdant_valley")
        with self.assertRaises(DataError):
            self.fossil_route(state, ride + "verdant_valley.mushroom_meadow")
        state = self.fossil_route(state, walk + "valley_mushtree.back", walk + "meadow_mushtree.out")
        with self.assertRaises(DataError):
            self.fossil_route(state, ride + "mushroom_meadow.verdant_valley")
        state = self.fossil_route(state, discover + "mushroom_meadow")
        with self.assertRaises(DataError):
            self.fossil_route(state, discover + "mushroom_meadow")

        walked = self.fossil_route(state, walk + "meadow_mushtree.back", walk + "valley_mushtree.out")
        landed = self.fossil_route(state, ride + "mushroom_meadow.verdant_valley")
        arrived = self.fossil_route(landed, walk + "valley_landing")
        self.assertEqual(arrived.location, walked.location)
        self.assertLess(arrived.elapsed, walked.elapsed)
        repeat = self.fossil_route(arrived, ride + "verdant_valley.mushroom_meadow",
                                   ride + "mushroom_meadow.verdant_valley")
        self.assertEqual(repeat.location, landed.location)
        self.assertEqual(repeat.inventory, state.inventory)
        self.assertEqual(repeat.xp, state.xp)

        for tools in ({}, {"item.rake": 1}, {"item.bronze_axe": 1}):
            camp = self.fossil_route(self.finish_bone_voyage(**tools), travel + "camp_pier.out")
            with self.assertRaises(DataError):
                self.fossil_route(camp, walk + "swamp_mushtree.out")
        camp = self.fossil_route(self.finish_bone_voyage(**{"item.rake": 1, "item.bronze_axe": 1}),
                                 travel + "camp_pier.out")
        swamp = self.fossil_route(camp, walk + "swamp_mushtree.out", discover + "sticky_swamp")
        hill = self.fossil_route(swamp, walk + "swamp_mushtree.back", "travel.other.varrock_specimens.approach_house",
                                 "travel.other.varrock_specimens.enter_house", "travel.walk.varrock_specimens.leg_5.back",
                                 walk + "hill_mushtree.out", discover + "house_on_the_hill")
        returned = self.fossil_route(hill, ride + "house_on_the_hill.sticky_swamp",
                                    ride + "sticky_swamp.house_on_the_hill")
        self.assertEqual(returned.location, hill.location)
        self.assertEqual(returned.inventory, camp.inventory)

    def test_north_shore_rowboat_unlocks_the_direct_camp_departure(self):
        boat = "travel.fossil_island.rowboat."
        camp = self.finish_bone_voyage()
        with self.assertRaises(DataError):
            self.fossil_route(camp, boat + "camp_to_sea")
        north = self.fossil_route(camp, boat + "camp_to_north")
        back = self.fossil_route(north, boat + "north_to_camp")
        with self.assertRaises(DataError):
            self.fossil_route(back, boat + "camp_to_sea")
        island = self.fossil_route(north, boat + "north_to_sea")
        back = self.fossil_route(island, boat + "sea_to_north", boat + "north_to_camp")
        direct = self.fossil_route(back, boat + "camp_to_sea")
        self.assertEqual(direct.location, island.location)
        self.assertLess(direct.elapsed - back.elapsed, island.elapsed - camp.elapsed)
        self.assertEqual(direct.inventory, camp.inventory)
        self.assertEqual(direct.counters, camp.counters)
        self.assertEqual(direct.xp, camp.xp)

    def test_defender_of_varrock_uses_one_history_and_lamp_claim(self):
        [report] = [row for row in self.review["history_reports"] if row["id"] == "museum.history.dov"]
        registry = read_json(RAW / "reward-registry.json")["entries"]
        [claim] = [entry for entry in registry if entry["id"] == report["reward_claim_id"]]
        self.assertEqual(claim["other_effects"]["kudos"], report["kudos"])
        self.assertEqual(claim["repeat_limit"], report["repeat_limit"])
