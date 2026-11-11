"""Travel fixtures for one-time setup, repeatable trips and carried fuel."""

from pathlib import Path
import unittest

from quest_optimizer.bounded_search import solve_bounded
from quest_optimizer.data import Contracts, DataError, load_catalog, read_json
from quest_optimizer.replay import verify_solution
from quest_optimizer.semantics import CatalogValidator
from quest_optimizer.transitions import RouteState


ROOT = Path(__file__).resolve().parents[2]
EXAMPLES = ROOT / "examples/build-242"
QUEST = "quest.enlightened_journey"
LIGHT_PACK = "flag.travel.balloon_light_pack"
ENTRANA = "location.balloon.entrana"


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

    def test_one_way_tablet(self):
        tablet = self.edges["travel.tablet.varrock.taverley"]
        self.assertEqual(tablet["consumes"], [{"item_id": "item.varrock_teleport_tablet", "quantity": 1}])
        self.assertFalse(any(
            edge["mode"] == "teleport_item"
            and edge["from_location_id"] == tablet["to_location_id"]
            and edge["to_location_id"] == tablet["from_location_id"]
            for edge in self.edges.values()
        ))

    def test_every_entrana_arrival_checks_the_current_loadout(self):
        pack_gate = {
            "kind": "restricted_items", "location_id": ENTRANA, "container": "inventory", "present": False,
        }
        arrivals = [
            edge for edge in self.edges.values()
            if edge["to_location_id"] == ENTRANA and edge["mode"] in ("ship", "balloon")
        ]
        self.assertEqual(len(arrivals), 6)
        for edge in arrivals:
            self.assertIn(pack_gate, edge["requirements"]["requirements"])
        self.assertNotIn(pack_gate, self.edges["travel.ship.entrana.port_sarim"]["requirements"]["requirements"])

        for edge_id in ("travel.ship.port_sarim.entrana", "travel.balloon.taverley.entrana"):
            with self.subTest(edge_id=edge_id):
                edge = self.edges[edge_id]
                initial = {**self.profile["initial_state"], "location_id": edge["from_location_id"]}
                initial["flags"] = {
                    LIGHT_PACK: True, "unlock.balloon.entrana": True, "unlock.balloon.taverley": True,
                }
                initial["inventory"] = {"item.logs": 1, "item.bronze_arrow": 25, "item.air_rune": 25}
                step = {"kind": "travel", "edge_id": edge_id, "modeled_seconds": edge["duration"]["expected_seconds"]}
                state = RouteState(self.validator.tables, self.profile["policies"], initial)
                self.assertEqual(state.apply(step).location, ENTRANA)
                initial["flags"]["flag.travel.entrana_safe_pack"] = True
                initial["inventory"]["item.iron_axe"] = 1
                state = RouteState(self.validator.tables, self.profile["policies"], initial)
                with self.assertRaisesRegex(DataError, "loadout fails a restriction"):
                    state.apply(step)

    def test_entrana_gear_can_be_withdrawn_at_the_full_bank(self):
        profile = read_json(EXAMPLES / "cooks-assistant-profile.json")
        action_id = "supply.bank.withdraw_entrana_gear"
        profile["goal_action_ids"] = [action_id]
        profile["initial_state"].update(
            inventory={"item.bronze_axe": 1, "item.air_rune": 3},
            bank_inventory={"item.bronze_axe": 2, "item.wooden_shield": 1, "item.mind_rune": 5},
        )
        solution, _ = solve_bounded(self.validator, profile)
        final = verify_solution(solution, profile, self.validator)["final_state"]
        self.assertEqual(final["location_id"], "location.lumbridge_castle.bank")
        self.assertEqual(final["inventory"], {"item.bronze_axe": 3, "item.wooden_shield": 1, "item.air_rune": 3})
        self.assertEqual(final["bank_inventory"], {"item.mind_rune": 5})
        solution["final_state"]["bank_inventory"]["item.wooden_shield"] = 1
        with self.assertRaisesRegex(DataError, "final_state.bank_inventory"):
            verify_solution(solution, profile, self.validator)

    def test_deposit_box_has_no_withdrawal_access(self):
        action_id = "supply.bank.withdraw_entrana_gear"
        action = self.actions[action_id]
        box = "location.port_sarim.deposit_box"
        misplaced = {**action, "start_location_id": box, "end_location_id": box}
        catalog = {**self.validator.catalog, "actions": [
            misplaced if row["id"] == action_id else row for row in self.validator.catalog["actions"]
        ]}
        with self.assertRaisesRegex(DataError, "withdrawals require a full bank"):
            CatalogValidator(catalog, self.contracts).validate_catalog()

    def test_fairy_ring_unlock_precedes_skill_gates_and_ring_travel(self):
        profile = read_json(EXAMPLES / "fairy-ring-access-profile.json")
        [unlock] = profile["priority_action_ids"]
        solution, _ = solve_bounded(self.validator, profile)
        self.assertEqual(solution["manual_training_xp_tenths_by_skill"], {})
        report = verify_solution(solution, profile, self.validator)
        self.assertTrue(report["final_state"]["flags"]["unlock.fairy_rings"])
        self.assertEqual(report["final_state"]["counters"], {"token.quest_points": 1})
        for skill in ("farming", "herblore", "thieving"):
            self.assertEqual(report["final_state"]["xp_tenths"][f"skill.{skill}"], 0)
        unlock_index = next(index for index, step in enumerate(solution["steps"]) if step.get("action_id") == unlock)
        ring_index = next(index for index, step in enumerate(solution["steps"])
                          if step.get("edge_id", "").startswith("travel.fairy_ring."))
        self.assertLess(unlock_index, ring_index)
        self.assertEqual(report["objective"]["priority_elapsed_seconds"], sum(
            step.get("modeled_seconds", 0) for step in solution["steps"][:unlock_index + 1]
        ))
        solution["objective"]["priority_elapsed_seconds"] -= 1
        with self.assertRaisesRegex(DataError, "objective.priority_elapsed_seconds"):
            verify_solution(solution, profile, self.validator)

    def test_fairy_ring_requires_access_and_a_staff(self):
        profile = read_json(EXAMPLES / "fairy-ring-access-profile.json")
        edge = self.edges["travel.fairy_ring.zanaris.dis"]
        initial = {**profile["initial_state"], "location_id": edge["from_location_id"]}
        step = {"kind": "travel", "edge_id": edge["id"], "modeled_seconds": edge["duration"]["expected_seconds"]}
        state = RouteState(self.validator.tables, profile["policies"], initial)
        with self.assertRaises(DataError):
            state.apply(step)
        initial["flags"]["unlock.fairy_rings"] = True
        initial["inventory"] = {}
        state = RouteState(self.validator.tables, profile["policies"], initial)
        with self.assertRaises(DataError):
            state.apply(step)
        initial["inventory"] = {"item.lunar_staff": 1}
        state = RouteState(self.validator.tables, profile["policies"], initial)
        self.assertEqual(state.apply(step).location, edge["to_location_id"])

    def test_public_house_portal_requires_profile_permission(self):
        edge = self.edges["travel.poh.rimmington.varrock"]
        initial = {**self.profile["initial_state"], "location_id": edge["from_location_id"], "inventory": {}}
        step = {"kind": "travel", "edge_id": edge["id"], "modeled_seconds": edge["duration"]["expected_seconds"]}
        state = RouteState(self.validator.tables, self.profile["policies"], initial)
        with self.assertRaises(DataError):
            state.apply(step)
        policies = {**self.profile["policies"], "allow_poh_services": True}
        state = RouteState(self.validator.tables, policies, initial)
        with self.assertRaises(DataError):
            state.apply(step)
        policies["world"] = 330
        state = RouteState(self.validator.tables, policies, initial)
        arrived = state.apply(step)
        self.assertEqual(arrived.location, "location.varrock.square")
        self.assertEqual(arrived.inventory, {})

    def test_varrock_spell_spends_runes_and_awards_magic_xp(self):
        profile = read_json(EXAMPLES / "cooks-assistant-profile.json")
        profile["goal_action_ids"] = ["supply.grand_exchange.spade"]
        magic = self.validator.tables["skills"]["skill.magic"]["xp_thresholds_tenths"][24]
        initial = profile["initial_state"]
        initial.update(
            location_id="location.lumbridge.castle_courtyard",
            inventory={"item.air_rune": 3, "item.fire_rune": 1, "item.law_rune": 1},
            flags={"flag.spellbook.standard": True, "flag.travel.varrock_square_selected": True},
        )
        initial["xp_tenths"]["skill.magic"] = magic
        solution, _ = solve_bounded(self.validator, profile)
        self.assertEqual(solution["steps"][0]["edge_id"], "travel.spell.lumbridge.varrock")
        state = verify_solution(solution, profile, self.validator)["final_state"]
        self.assertEqual(state["xp_tenths"]["skill.magic"], magic + 350)
        self.assertEqual(state["inventory"], {"item.spade": 1})
        initial["inventory"]["item.law_rune"] = 0
        with self.assertRaisesRegex(DataError, "consumes 1 of 'item.law_rune'"):
            RouteState(self.validator.tables, profile["policies"], initial).apply(solution["steps"][0])

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
