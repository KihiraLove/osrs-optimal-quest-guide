"""Travel fixtures for one-time setup, repeatable trips and carried fuel."""

from pathlib import Path
import unittest

from quest_optimizer.data import Contracts, DataError, load_catalog, read_json
from quest_optimizer.semantics import CatalogValidator


ROOT = Path(__file__).resolve().parents[2]
EXAMPLES = ROOT / "examples/build-242"
QUEST = "quest.enlightened_journey"
LIGHT_PACK = "flag.travel.balloon_light_pack"
ENTRANA_PACK = "flag.travel.entrana_safe_pack"


class TravelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.contracts = Contracts(ROOT / "schemas")
        catalog = load_catalog(ROOT / "data/manifest.json", cls.contracts)
        cls.validator = CatalogValidator(catalog, cls.contracts)
        cls.actions = cls.validator.tables["actions"]
        cls.edges = cls.validator.tables["travel_edges"]
        cls.locations = cls.validator.tables["locations"]

    def setUp(self):
        self.profile = read_json(EXAMPLES / "balloon-travel-profile.json")
        self.solution = read_json(EXAMPLES / "balloon-travel-solution.json")

    def check_solution(self):
        self.contracts.validate("profile", self.profile)
        self.validator.validate_profile(self.profile)
        self.contracts.validate("solution", self.solution)
        self.validator.validate_solution(self.solution, self.profile)

    def test_setup_and_reusable_trip_have_distinct_fuel_and_destinations(self):
        self.check_solution()
        initial = self.profile["initial_state"]
        location = initial["location_id"]
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
        final = self.solution["final_state"]
        self.assertEqual(final["location_id"], location)
        self.assertEqual(final["inventory"], {"item.tinderbox": 1})
        self.assertEqual(final["xp_tenths"]["skill.firemaking"] - initial["xp_tenths"]["skill.firemaking"], 20000)

        walk = [
            self.edges[edge_id]
            for edge_id in ("travel.walk.taverley.varrock.out", "travel.walk.varrock.balloon.out")
        ]
        flight = self.edges["travel.balloon.taverley.varrock"]
        self.assertEqual(walk[0]["from_location_id"], flight["from_location_id"])
        self.assertEqual(walk[0]["to_location_id"], walk[1]["from_location_id"])
        self.assertEqual(walk[1]["to_location_id"], flight["to_location_id"])
        self.assertGreater(
            sum(edge["duration"]["expected_seconds"] for edge in walk),
            flight["duration"]["expected_seconds"],
        )

    def test_routine_flight_is_locked_until_discovery(self):
        discovery, return_flight, repeat_flight = self.solution["steps"]
        self.solution["steps"] = [repeat_flight, discovery, return_flight]
        with self.assertRaisesRegex(DataError, "flag or counter threshold"):
            self.check_solution()

    def test_discovery_xp_cannot_be_awarded_twice(self):
        discovery = self.solution["steps"][0]
        self.solution["steps"].append({**discovery, "step_id": "step.discovery_again"})
        with self.assertRaisesRegex(DataError, "XP producer .* already used"):
            self.check_solution()

    def test_first_flight_checks_completed_quest_pack_and_firemaking(self):
        initial = self.profile["initial_state"]
        mutations = [
            (initial, "completed_action_ids", []),
            (initial["flags"], LIGHT_PACK, False),
            (initial["xp_tenths"], "skill.firemaking", initial["xp_tenths"]["skill.firemaking"] - 1),
            (initial["inventory"], "item.tinderbox", 0),
        ]
        for target, key, value in mutations:
            with self.subTest(key=key):
                original = target[key]
                target[key] = value
                try:
                    with self.assertRaisesRegex(DataError, "threshold.*missing"):
                        self.check_solution()
                finally:
                    target[key] = original

    def test_consumed_fuel_cannot_be_reused_or_forged(self):
        self.profile["initial_state"]["inventory"]["item.willow_logs"] = 10
        with self.assertRaisesRegex(DataError, "consumes 1 of 'item.willow_logs'"):
            self.check_solution()
        self.profile["initial_state"]["inventory"]["item.willow_logs"] = 11
        self.solution["final_state"]["inventory"]["item.willow_logs"] = 1
        with self.assertRaisesRegex(DataError, "final_state.inventory"):
            self.check_solution()

    def test_one_way_tablet_and_entrana_pack_gate(self):
        tablet = self.edges["travel.tablet.varrock.taverley"]
        self.assertEqual(tablet["consumes"], [{"item_id": "item.varrock_teleport_tablet", "quantity": 1}])
        self.assertFalse(any(
            edge["mode"] == "teleport_item"
            and edge["from_location_id"] == tablet["to_location_id"]
            and edge["to_location_id"] == tablet["from_location_id"]
            for edge in self.edges.values()
        ))
        pack_gate = {"kind": "flag", "token_id": ENTRANA_PACK, "value": True}
        for edge_id in ("travel.ship.port_sarim.entrana", "travel.balloon.taverley.entrana"):
            self.assertIn(pack_gate, self.edges[edge_id]["requirements"]["requirements"])
        self.assertNotIn(pack_gate, self.edges["travel.ship.entrana.port_sarim"]["requirements"]["requirements"])

    def test_every_stop_links_basket_unlock_and_routine_edges(self):
        review = read_json(ROOT / "data/raw/build-242/balloon-stops.json")
        stops = review["stops"]
        self.assertEqual(len(stops), 6)
        self.assertEqual(len({stop["tracker_varbit"] for stop in stops}), 6)
        for origin in stops:
            location = self.locations[origin["location_id"]]
            self.assertEqual([location["x"], location["y"], location["plane"]], origin["basket"]["tile"])
            setup = self.actions[origin["first_flight_action_id"]]
            self.assertIn({"kind": "flag", "token_id": origin["flag_id"], "value": True}, setup["effects"])
            if setup["kind"] == "transport_unlock":
                self.assertEqual(setup["consumes"], [{"item_id": origin["log_item_id"], "quantity": origin["setup_logs"]}])
                self.assertEqual(setup["start_location_id"], "location.balloon.entrana")
                self.assertEqual(setup["end_location_id"], origin["location_id"])
                self.assertEqual(setup["repeat_limit"], 1)
                self.assertIn({"kind": "xp", "skill_id": "skill.firemaking", "xp_tenths": 20000}, setup["effects"])
            for destination in stops:
                if origin is destination:
                    continue
                [edge] = [
                    row for row in self.edges.values()
                    if row["mode"] == "balloon"
                    and row["from_location_id"] == origin["location_id"]
                    and row["to_location_id"] == destination["location_id"]
                ]
                self.assertEqual(edge["consumes"], [{"item_id": destination["log_item_id"], "quantity": 1}])
                flags = {rule["token_id"] for rule in edge["requirements"]["requirements"] if rule["kind"] == "flag"}
                self.assertTrue({origin["flag_id"], destination["flag_id"], LIGHT_PACK} <= flags)

        first_flight = self.actions[QUEST + ".first_flight"]
        self.assertEqual(first_flight["consumes"], [{"item_id": "item.logs", "quantity": 10}])
        self.assertEqual(first_flight["end_location_id"], "location.balloon.taverley")
