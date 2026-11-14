"""Focused draft transition coverage for Heroes' Quest and Throne of Miscellania."""
from copy import deepcopy
from pathlib import Path
import unittest

from quest_optimizer.data import Contracts, DataError, load_catalog, read_json
from quest_optimizer.semantics import CatalogValidator
from quest_optimizer.transitions import RouteState


ROOT = Path(__file__).resolve().parents[2]


class HeroesAndMiscellaniaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        contracts = Contracts(ROOT / "schemas")
        catalog = load_catalog(ROOT / "data/manifest.json", contracts)
        cls.tables = CatalogValidator(catalog, contracts).tables
        cls.profile = read_json(ROOT / "data/profiles/main-baseline.json")

    def seeded(self, gang):
        initial = deepcopy(self.profile["initial_state"])
        initial["location_id"] = "location.heroes_guild.achietties"
        initial["counters"]["token.quest_points"] = 55
        initial["inventory"]["item.coins"] = 50000
        initial["completed_action_ids"] = [
            "quest.dragon_slayer_i.complete",
            "quest.shield_of_arrav.complete",
            "quest.lost_city.complete",
            "quest.merlins_crystal.complete",
            "quest.the_fremennik_trials.complete",
        ]
        initial["flags"]["flag.shield_of_arrav." + gang] = True
        for skill in ("herblore", "fishing", "cooking", "mining", "defence", "farming", "woodcutting"):
            initial["xp_tenths"]["skill." + skill] = 2000000
        if gang == "phoenix":
            initial["inventory"]["item.ice_gloves"] = 1
        return RouteState(self.tables, self.profile["policies"], initial)

    def at(self, state, location):
        snapshot = state.snapshot()
        snapshot["location_id"] = location
        return RouteState(self.tables, self.profile["policies"], snapshot)

    def step(self, state, id):
        travel = id.startswith("travel.")
        record = self.tables["travel_edges" if travel else "actions"][id]
        move = {
            "kind": "travel" if travel else "action",
            "edge_id" if travel else "action_id": id,
            "modeled_seconds": record["duration"]["expected_seconds"],
        }
        if "planned_outcome" in record:
            move["planned_outcome"] = record["planned_outcome"]
        return state.apply(move)

    def action_at(self, state, id):
        record = self.tables["actions"][id]
        return self.step(self.at(state, record["start_location_id"]), id)

    def heroes(self, gang):
        state = self.seeded(gang)
        state = self.step(state, "quest.heroes_quest.start")
        state = self.action_at(state, "supply.grand_exchange.purchase_heroes_materials")
        state = self.action_at(state, "quest.heroes_quest.get_blamish_slime")
        state = self.action_at(state, "quest.heroes_quest.prepare_oily_rod")
        state = self.action_at(state, "quest.heroes_quest.catch_lava_eel")
        state = self.step(state, "quest.heroes_quest.cook_lava_eel")
        if gang == "black_arm":
            state = self.action_at(state, "quest.heroes_quest.defeat_ice_queen")
        state = self.action_at(state, "quest.heroes_quest.get_fire_feather")
        if gang == "black_arm":
            state = self.action_at(state, "supply.grand_exchange.purchase_heroes_black_disguise")
            state = self.action_at(state, "quest.heroes_quest.black_arm_contact")
            state = self.at(state, "location.brimhaven.trobert")
            without_partner = dict(self.profile["policies"])
            without_partner["allow_player_assistance"] = False
            with self.assertRaises(DataError):
                self.step(
                    RouteState(self.tables, without_partner, state.snapshot()),
                    "quest.heroes_quest.black_arm_heist",
                )
            state = self.step(state, "quest.heroes_quest.black_arm_heist")
            state = self.step(state, "travel.heroes_miscellania.brimhaven_chest.back")
        else:
            state = self.action_at(state, "quest.heroes_quest.phoenix_contact")
            state = self.action_at(state, "quest.heroes_quest.phoenix_heist")
            state = self.step(state, "travel.heroes_miscellania.brimhaven_phoenix_mansion.back")
        state = self.action_at(state, "quest.heroes_quest.complete")
        end = state.snapshot()
        self.assertEqual(end["counters"]["token.quest_points"], 56)
        self.assertEqual(end["xp_tenths"]["skill.mining"], 2000000 + 25750)
        self.assertEqual(end["xp_tenths"]["skill.herblore"], 2000000 + 800 + 13250)
        self.assertEqual(end["xp_tenths"]["skill.fishing"], 2000000 + 600 + 27250)
        self.assertEqual(end["xp_tenths"]["skill.cooking"], 2000000 + 300 + 28250)
        self.assertTrue(end["flags"]["unlock.heroes_guild"])
        self.assertTrue(end["flags"]["unlock.fountain_of_rune_six_charges"])
        for used in ("item.cooked_lava_eel", "item.heroes_fire_feather", "item.heroes_master_thieves_armband"):
            self.assertNotIn(used, end["inventory"])
        return state

    def throne(self, state, partner, favour="rake"):
        state = self.action_at(state, "quest.throne_of_miscellania.start")
        state = self.action_at(state, "supply.grand_exchange.purchase_miscellania_supplies")
        optional_tools = {"coal": "favour_pickaxe", "maple_trees": "favour_axe", "fish": "favour_lobster_pot"}
        if favour in optional_tools:
            state = self.action_at(state, "supply.grand_exchange.purchase_miscellania_" + optional_tools[favour])
        if partner == "brand":
            state = self.action_at(state, "supply.grand_exchange.purchase_miscellania_cake")
        state = self.action_at(state, "quest.throne_of_miscellania.buy_flowers")
        wedding = "court_brand" if partner == "brand" else "court_astrid"
        state = self.action_at(state, "quest.throne_of_miscellania." + wedding)
        self.assertTrue(state.snapshot()["flags"]["flag.quest.throne_of_miscellania.courtship"])
        with self.assertRaises(DataError):
            self.action_at(state, "quest.throne_of_miscellania." + ("court_astrid" if partner == "brand" else "court_brand"))
        for stage in (
            "visit_sigrid",
            "report_to_vargas",
            "get_anthem",
            "rewrite_anthem",
            "agree_with_sigrid",
            "get_nib",
            "make_pen",
            "write_treaty",
            "deliver_treaty",
        ):
            state = self.action_at(state, "quest.throne_of_miscellania." + stage)
        approval_action = "quest.throne_of_miscellania.raise_approval"
        if favour != "rake":
            approval_action += "_" + favour
        state = self.action_at(state, approval_action)
        with self.assertRaises(DataError):
            self.action_at(state, "quest.throne_of_miscellania.raise_approval")
        state = self.action_at(state, "quest.throne_of_miscellania.complete")
        end = state.snapshot()
        self.assertEqual(end["counters"]["token.quest_points"], 57)
        self.assertTrue(end["flags"]["unlock.manage_miscellania"])
        self.assertTrue(end["flags"]["flag.quest.throne_of_miscellania.etceteria_support"])
        return state

    def test_black_arm_and_astrid_chain(self):
        self.throne(self.heroes("black_arm"), "astrid")

    def test_phoenix_and_brand_chain(self):
        self.throne(self.heroes("phoenix"), "brand", "coal")

    def test_kingdom_maple_approval_route(self):
        self.throne(self.heroes("phoenix"), "astrid", "maple_trees")

    def test_kingdom_fishing_approval_route(self):
        self.throne(self.heroes("phoenix"), "brand", "fish")

    def test_kingdom_flower_approval_route(self):
        self.throne(self.heroes("black_arm"), "astrid", "flowers")

    def test_kingdom_requires_heroes_quest(self):
        state = self.seeded("phoenix")
        with self.assertRaises(DataError):
            self.action_at(state, "quest.throne_of_miscellania.start")


if __name__ == "__main__":
    unittest.main()
