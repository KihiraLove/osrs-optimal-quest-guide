"""Focused seeded replays of the three build-242 optional-unlock activities."""

from copy import deepcopy
from pathlib import Path
import unittest

from quest_optimizer.data import Contracts, DataError, load_catalog, read_json
from quest_optimizer.reachability import unreachable_records
from quest_optimizer.semantics import CatalogValidator
from quest_optimizer.transitions import RouteState


ROOT = Path(__file__).resolve().parents[2]


class QuestmonthOptionalUnlocksTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        contracts = Contracts(ROOT / "schemas")
        cls.catalog = load_catalog(ROOT / "data/manifest.json", contracts)
        cls.tables = CatalogValidator(cls.catalog, contracts).tables
        cls.profile = read_json(ROOT / "data/profiles/main-baseline.json")

    def seeded_state(self, location, *, completed=(), flags=None, inventory=None):
        initial = deepcopy(self.profile["initial_state"])
        initial["location_id"] = location
        initial["completed_action_ids"].extend(completed)
        initial["flags"].update(flags or {})
        initial["inventory"].update(inventory or {})
        return RouteState(self.tables, self.profile["policies"], initial)

    def step(self, state, record_id):
        travel = record_id.startswith("travel.")
        record = self.tables["travel_edges" if travel else "actions"][record_id]
        step = {
            "kind": "travel" if travel else "action",
            "edge_id" if travel else "action_id": record_id,
            "modeled_seconds": record["duration"]["expected_seconds"],
        }
        if "planned_outcome" in record:
            step["planned_outcome"] = record["planned_outcome"]
        return state.apply(step, record_id)

    def test_harlan_first_claim_repeat_and_shared_cooldown(self):
        claim = "claim.harlan_weapons.magic"
        repeat = "claim.harlan_weapons.magic_repeat"
        location = "location.lumbridge.captain_harlan"
        without_quest = self.seeded_state(location)
        with self.assertRaises(DataError):
            self.step(without_quest, claim)

        state = self.seeded_state(location, flags={"flag.quest.mudfoots_big_adventure.complete": True})
        with self.assertRaises(DataError):
            self.step(state, repeat)
        before = state.snapshot()["inventory"]
        state = self.step(state, claim)
        self.assertEqual(state.snapshot()["inventory"]["item.staff"], before.get("item.staff", 0) + 1)
        self.assertEqual(state.snapshot()["inventory"]["item.air_rune"], before["item.air_rune"] + 40)
        self.assertEqual(state.snapshot()["inventory"]["item.mind_rune"], before["item.mind_rune"] + 40)
        with self.assertRaises(DataError):
            self.step(state, repeat)
        state = state.apply({"kind": "wait", "modeled_seconds": 1799})
        with self.assertRaises(DataError):
            self.step(state, repeat)
        state = state.apply({"kind": "wait", "modeled_seconds": 1})
        state = self.step(state, repeat)
        self.assertEqual(state.snapshot()["inventory"]["item.staff"], before.get("item.staff", 0) + 2)

    def test_beas_field_material_loop_and_supply_bags(self):
        state = self.seeded_state(
            "location.digsite.farmer_bea",
            flags={"unlock.beas_hunter_field": True},
            inventory={
                "item.bee_hunters_hat": 1,
                "item.butterfly_net": 1,
                "item.insect_repellent": 1,
                "item.bird_snare": 1,
            },
        )
        state.xp["skill.hunter"] = 100000
        state.xp["skill.fletching"] = 100000
        state = self.step(state, "travel.walk.birds_and_wasps.bea_hives.out")
        for _ in range(35):
            state = self.step(state, "activity.beas_hunter_field.catch_wasps")
            state = self.step(state, "activity.beas_hunter_field.trap_honey_buzzard")
        state = self.step(state, "activity.beas_hunter_field.fletch_wasp_dart")
        for _ in range(34):
            state = self.step(state, "activity.beas_hunter_field.fletch_wasp_dart_repeat")
        self.assertEqual(state.snapshot()["inventory"]["item.wasp_dart"], 35)
        self.assertNotIn("item.wasp_sting", state.snapshot()["inventory"])
        self.assertNotIn("item.brown_feather", state.snapshot()["inventory"])
        for _ in range(20):
            state = self.step(state, "activity.beas_hunter_field.catch_killer_wasps")
            state = self.step(state, "activity.beas_hunter_field.trap_black_honey_buzzard")
            state = self.step(state, "activity.beas_hunter_field.fletch_killer_wasp_dart")
        state = self.step(state, "travel.walk.birds_and_wasps.bea_hives.back")
        state = self.step(state, "claim.beas_supplies.wasp_darts")
        state = self.step(state, "claim.beas_supplies.killer_wasp_darts")
        result = state.snapshot()["inventory"]
        self.assertEqual(result["item.beas_supplies"], 2)
        self.assertNotIn("item.wasp_dart", result)
        self.assertNotIn("item.killer_wasp_dart", result)

        locked = self.seeded_state("location.digsite.beas_hives", inventory={"item.bird_snare": 1})
        with self.assertRaises(DataError):
            self.step(locked, "activity.beas_hunter_field.trap_honey_buzzard")

    def test_north_aldarin_unlock_and_charged_teleport(self):
        first = "unlock.north_aldarin_pendant_of_ates.pickpocket_key"
        villa = "location.aldarin.villa_lucens_party"
        with self.assertRaises(DataError):
            self.step(self.seeded_state(villa), first)
        state = self.seeded_state(villa, completed=[
            "quest.death_on_the_isle.complete", "quest.the_heart_of_darkness.complete",
        ])
        state.xp["skill.thieving"] = 10000000
        state = self.step(state, first)
        self.assertEqual(state.snapshot()["inventory"]["item.aldarin_chest_key"], 1)
        for edge in ("travel.walk.death_on_the_isle.leg_10.out", "travel.other.death_on_the_isle.enter_cellar"):
            state = self.step(state, edge)
        state = self.step(state, "unlock.north_aldarin_pendant_of_ates.open_chest")
        self.assertNotIn("item.aldarin_chest_key", state.snapshot()["inventory"])
        for edge in ("travel.other.death_on_the_isle.exit_cellar", "travel.walk.death_on_the_isle.leg_10.back", "travel.aldarin.villa_to_southwest_fountain"):
            state = self.step(state, edge)
        state = self.step(state, "unlock.north_aldarin_pendant_of_ates.find_icon")
        state = self.step(state, "travel.aldarin.southwest_fountain_to_villa")
        state = self.step(state, "travel.aldarin.villa_to_ates_statue")
        state = self.step(state, "unlock.north_aldarin_pendant_of_ates.activate")
        self.assertTrue(state.snapshot()["flags"]["unlock.pendant_of_ates.north_aldarin"])
        with self.assertRaises(DataError):
            self.step(state, "unlock.north_aldarin_pendant_of_ates.activate")
        before_runes = state.snapshot()["inventory"].get("item.water_rune", 0)
        state = self.step(state, "supply.north_aldarin_ates.pickup_water_rune")
        self.assertEqual(state.snapshot()["inventory"]["item.water_rune"], before_runes + 1)
        state = self.step(state, "travel.aldarin.ates_statue_to_pendant_arrival")
        state = self.step(state, "travel.aldarin.pendant_arrival_to_ates_statue")
        state = self.step(state, "travel.aldarin.ates_statue_to_villa")

        source = "supply.amoxliatl.obtain_inert_pendant"
        arena = "location.heart.defeat_amoxliatl"
        with self.assertRaises(DataError):
            self.step(self.seeded_state(arena), source)
        at_arena = {**state.snapshot(), "location_id": arena}
        state = self.step(RouteState(self.tables, self.profile["policies"], at_arena), source)
        self.assertEqual(state.snapshot()["inventory"]["item.pendant_of_ates_inert"], 1)

        at_ge = state.snapshot()
        at_ge["location_id"] = "location.varrock.grand_exchange"
        at_ge["inventory"]["item.coins"] = 1500
        state = RouteState(self.tables, self.profile["policies"], at_ge)
        with self.assertRaises(DataError):
            self.step(state, "travel.pendant_of_ates.grand_exchange_to_north_aldarin")
        state = self.step(state, "supply.grand_exchange.buy_frozen_tears")
        self.assertEqual(state.snapshot()["inventory"]["item.frozen_tear"], 5)
        self.assertNotIn("item.coins", state.snapshot()["inventory"])
        state = self.step(state, "supply.pendant_of_ates.charge_inert")
        state = self.step(state, "supply.pendant_of_ates.add_frozen_tear")
        self.assertEqual(state.snapshot()["counters"]["token.pendant_of_ates.charges"], 2)
        state = self.step(state, "travel.pendant_of_ates.grand_exchange_to_north_aldarin")
        self.assertEqual(state.snapshot()["location_id"], "location.aldarin.pendant_of_ates_arrival")
        self.assertEqual(state.snapshot()["counters"]["token.pendant_of_ates.charges"], 1)

    def test_optional_routes_are_reachable_from_the_main_baseline(self):
        batch = ROOT / "data/catalog/questmonth-optional-unlocks"
        unreachable = unreachable_records(self.catalog, self.profile)
        for collection in ("actions", "travel_edges"):
            ids = {row["id"] for row in read_json(batch / f"{collection}.json")}
            self.assertEqual(ids.intersection(unreachable[collection]), set())


if __name__ == "__main__":
    unittest.main()
