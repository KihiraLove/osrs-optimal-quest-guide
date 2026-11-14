"""Focused staged route replay for Royal Trouble and Cold War."""
from copy import deepcopy
from pathlib import Path
import unittest

from quest_optimizer.data import Contracts, DataError, load_catalog, read_json
from quest_optimizer.semantics import CatalogValidator
from quest_optimizer.transitions import RouteState


ROOT = Path(__file__).resolve().parents[2]


class RoyalAndColdWarTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        contracts = Contracts(ROOT / "schemas")
        catalog = load_catalog(ROOT / "data/manifest.json", contracts)
        cls.tables = CatalogValidator(catalog, contracts).tables
        cls.profile = read_json(ROOT / "data/profiles/main-baseline.json")

    def seeded(self, location, skills, completed=(), flags=(), qp=0):
        initial = deepcopy(self.profile["initial_state"])
        initial["location_id"] = location
        initial["inventory"]["item.coins"] = 50000
        initial["counters"]["token.quest_points"] = qp
        initial["completed_action_ids"] = list(completed)
        for skill in skills:
            initial["xp_tenths"]["skill." + skill] = 2000000
        for flag in flags:
            initial["flags"][flag] = True
        return RouteState(self.tables, self.profile["policies"], initial)

    def at(self, state, location):
        snapshot = state.snapshot()
        snapshot["location_id"] = location
        return RouteState(self.tables, self.profile["policies"], snapshot)

    def step(self, state, action_id):
        travel = action_id.startswith("travel.")
        record = self.tables["travel_edges" if travel else "actions"][action_id]
        move = {
            "kind": "travel" if travel else "action",
            "edge_id" if travel else "action_id": action_id,
            "modeled_seconds": record["duration"]["expected_seconds"],
        }
        if "planned_outcome" in record:
            move["planned_outcome"] = record["planned_outcome"]
        return state.apply(move)

    def action_at(self, state, action_id):
        record = self.tables["actions"][action_id]
        return self.step(self.at(state, record["start_location_id"]), action_id)

    def royal(self, spouse):
        state = self.seeded(
            "location.miscellania.ghrim",
            ("agility", "slayer"),
            completed=("quest.throne_of_miscellania.complete",),
            flags=("flag.quest.throne_of_miscellania." + spouse,),
            qp=57,
        )
        p = "quest.royal_trouble."
        state = self.action_at(state, p + "start")
        state = self.action_at(state, p + "speak_" + spouse)
        with self.assertRaises(DataError):
            other = "brand" if spouse == "astrid" else "astrid"
            self.action_at(state, p + "speak_" + other)
        for suffix in (
            "ask_vargas", "ask_gunnhild", "ask_sigrid", "ask_matilda",
            "report_to_sigrid", "dungeon_order", "ask_ghrim_again",
            "find_sailor", "get_scroll",
        ):
            state = self.action_at(state, p + suffix)
        state = self.at(state, "location.miscellania.castle_stairs")
        state = self.step(state, "travel.royal_cold_war.royal_ladder.out")
        state = self.action_at(state, "supply.grand_exchange.purchase_royal_trouble_reserve")
        for suffix in (
            "enter_cave", "prop_crevice", "repair_lift",
            "navigate_cave", "defeat_sea_snake",
        ):
            state = self.action_at(state, p + suffix)
        state = self.step(state, "travel.royal_cold_war.snake_escape")
        state = self.step(state, "travel.royal_cold_war.escape_etceteria")
        state = self.action_at(state, p + "report_to_queen")
        snapshot = state.snapshot()
        self.assertEqual(snapshot["inventory"]["item.coins"], 50000 - 9000 + 20000)
        self.assertEqual(snapshot["counters"]["token.quest_points"], 57)
        state = self.action_at(state, p + "complete")
        snapshot = state.snapshot()
        self.assertEqual(snapshot["counters"]["token.quest_points"], 58)
        for skill in ("agility", "slayer", "hitpoints"):
            start = 2000000 if skill != "hitpoints" else self.profile["initial_state"]["xp_tenths"]["skill.hitpoints"]
            self.assertEqual(snapshot["xp_tenths"]["skill." + skill], start + 50000)
        self.assertTrue(snapshot["flags"]["unlock.manage_miscellania_enhanced"])
        self.assertTrue(snapshot["flags"]["unlock.bosun_zarah"])
        self.assertNotIn("item.royal_peace_letter", snapshot["inventory"])

    def test_royal_trouble_astrid(self):
        self.royal("astrid")

    def test_royal_trouble_brand(self):
        self.royal("brand")

    def test_royal_trouble_requires_throne(self):
        state = self.seeded("location.miscellania.ghrim", ("agility", "slayer"))
        with self.assertRaises(DataError):
            self.action_at(state, "quest.royal_trouble.start")

    def test_cold_war_full_route(self):
        state = self.seeded(
            "location.cold_war.larry_zoo",
            ("hunter", "agility", "crafting", "construction", "thieving"),
        )
        p = "quest.cold_war."
        state = self.action_at(state, p + "start")
        state = self.action_at(state, "supply.grand_exchange.purchase_cold_war_materials")
        state = self.at(state, "location.cold_war.larry_zoo")
        state = self.step(state, "travel.royal_cold_war.cold_zoo_iceberg.out")
        state = self.action_at(state, p + "build_hide")
        state = self.action_at(state, p + "observe_emotes")
        with self.assertRaises(DataError):
            self.action_at(state, p + "make_clockwork_suit")
        for suffix in (
            "access_clockmaker_table", "make_clockwork_suit", "show_larry_suit",
            "zoo_mission", "lumbridge_sheep", "offer_cod", "steal_cowbell",
            "fred_followup", "obtain_id", "enter_outpost", "agility_course",
            "ask_musicians", "craft_bongos", "enter_war_room", "defeat_icelord",
        ):
            state = self.action_at(state, p + suffix)
        state = self.step(self.at(state, "location.cold_war.icelords"), "travel.royal_cold_war.icelords_chasm")
        state = self.step(state, "travel.royal_cold_war.cold_chasm_iceberg.out")
        self.assertEqual(state.snapshot()["xp_tenths"]["skill.attack"], self.profile["initial_state"]["xp_tenths"]["skill.attack"] + 400)
        state = self.action_at(state, p + "complete")
        final = state.snapshot()
        self.assertEqual(final["counters"]["token.quest_points"], 1)
        for skill, amount in (("agility", 50000), ("crafting", 20000), ("construction", 15000)):
            self.assertEqual(final["xp_tenths"]["skill." + skill], 2000000 + amount)
        self.assertTrue(final["flags"]["unlock.penguin_agility_course"])
        self.assertTrue(final["flags"]["unlock.penguin_suit"])
        self.assertNotIn("item.raw_cod", final["inventory"])
        self.assertIn("item.cold_war_clockwork_suit", final["inventory"])

    def test_cold_war_start_requires_skills(self):
        state = self.seeded("location.cold_war.larry_zoo", ("agility", "crafting", "construction", "thieving"))
        with self.assertRaises(DataError):
            self.action_at(state, "quest.cold_war.start")


if __name__ == "__main__":
    unittest.main()
