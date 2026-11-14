"""Replay one A Kingdom Divided route, resource transformations and two lamps."""

from copy import deepcopy
from pathlib import Path
import unittest

from quest_optimizer.data import Contracts, DataError, load_catalog, read_json
from quest_optimizer.semantics import CatalogValidator
from quest_optimizer.transitions import RouteState


ROOT = Path(__file__).resolve().parents[2]
QUEST = "quest.a_kingdom_divided"
PREREQUISITES = ("quest.client_of_kourend", "quest.x_marks_the_spot",
                 "quest.the_queen_of_thieves", "quest.the_depths_of_despair",
                 "quest.the_ascent_of_arceuus", "quest.the_forsaken_tower",
                 "quest.tale_of_the_righteous")


class KingdomDividedCatalogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        contracts = Contracts(ROOT / "schemas")
        cls.tables = CatalogValidator(load_catalog(ROOT / "data/manifest.json", contracts), contracts).tables
        cls.profile = read_json(ROOT / "data/profiles/main-baseline.json")
        cls.actions = read_json(ROOT / "data/catalog/a-kingdom-divided/actions.json")

    def seed(self, earlier=None, *, trade=True, owns_materials=False):
        initial = deepcopy(self.profile["initial_state"])
        initial["completed_action_ids"] = [q + ".complete" for q in (PREREQUISITES if earlier is None else earlier)]
        initial["inventory"]["item.coins"] = 500_000
        initial["inventory"]["item.kharedsts_memoirs"] = 1
        if owns_materials:
            for item in ("bronze_axe", "bronze_pickaxe", "chisel", "akd_defence_potion_4",
                         "akd_volcanic_sulphur", "molten_glass", "chaos_rune"):
                initial["inventory"]["item." + item] = 1
            initial["inventory"]["item.air_rune"] = 3
            initial["inventory"]["item.fire_rune"] = 4
        initial["counters"]["token.quest_points"] = 120
        for skill in initial["xp_tenths"]:
            initial["xp_tenths"][skill] = 20_000_000
        policies = deepcopy(self.profile["policies"])
        policies["trade_enabled"] = trade
        return RouteState(self.tables, policies, initial)

    def do(self, state, action_id):
        action = self.tables["actions"][action_id]
        snap = state.snapshot()
        snap["location_id"] = action["start_location_id"]
        state = RouteState(self.tables, state.policies, snap)
        transition = {"kind": "action", "action_id": action_id,
                      "modeled_seconds": action["duration"]["expected_seconds"]}
        if action.get("planned_outcome"):
            transition["planned_outcome"] = action["planned_outcome"]
        return state.apply(transition)

    def route(self, state=None, *, purchase=True, claim=True, until=None):
        state = state or self.seed()
        for action in self.actions:
            if not purchase and action["id"] == "supply.akd.purchase_requirements":
                continue
            if not claim and action["id"] == QUEST + ".claim_rewards":
                continue
            state = self.do(state, action["id"])
            if until == action["id"]:
                return state
        if until is not None:
            self.fail("Missing route stage: " + until)
        return state

    def test_full_route_grants_two_lamps_and_quest_points(self):
        state = self.route()
        snap = state.snapshot()
        self.assertEqual(snap["counters"]["token.quest_points"], 122)
        self.assertTrue(snap["flags"]["unlock.akd_complete"])
        self.assertTrue(snap["flags"]["unlock.akd_arceuus_spells"])
        self.assertTrue(snap["flags"]["unlock.akd_kourend_respawn"])
        self.assertTrue(snap["flags"]["unlock.akd_accord"])
        self.assertEqual(snap["inventory"]["item.akd_book_of_the_dead"], 1)
        self.assertEqual(snap["inventory"].get("item.kharedsts_memoirs", 0), 0)
        self.assertEqual(len(snap["held_rewards"]), 2)
        self.assertEqual({x["reward_id"] for x in snap["held_rewards"]}, {"reward.akd.antique_lamp"})
        self.assertEqual(snap["xp_tenths"]["skill.magic"], 20_000_225)
        self.assertEqual(snap["xp_tenths"]["skill.mining"], 20_000_120)
        self.assertEqual(snap["xp_tenths"]["skill.crafting"], 20_000_080)
        with self.assertRaises(DataError):
            self.do(state, QUEST + ".claim_rewards")

    def test_preconditions_require_all_seven_quests(self):
        for absent in PREREQUISITES:
            state = self.seed([q for q in PREREQUISITES if q != absent])
            with self.subTest(absent=absent), self.assertRaises(DataError):
                self.do(state, QUEST + ".talk_to_martin_holt")

    def test_each_nonboostable_skill_gate(self):
        for skill_name in ("agility", "thieving", "woodcutting", "herblore", "mining", "crafting", "magic"):
            state = self.seed()
            snap = state.snapshot()
            snap["xp_tenths"]["skill." + skill_name] = 0
            with self.subTest(skill=skill_name), self.assertRaises(DataError):
                self.do(RouteState(self.tables, state.policies, snap), QUEST + ".talk_to_martin_holt")

    def test_missing_runes_block_ice_fire_bolt(self):
        state = self.route(until=QUEST + ".talk_to_martin_holt_settlement_ruins2")
        snap = state.snapshot()
        snap["inventory"]["item.chaos_rune"] = 0
        with self.assertRaises(DataError):
            self.do(RouteState(self.tables, state.policies, snap), QUEST + ".cast_fire_spell_on_ice")

    def test_sulphur_potion_and_dark_essence_spend_supplies(self):
        state = self.route(until=QUEST + ".brew_sulphur_potion")
        snap = state.snapshot()
        self.assertEqual(snap["inventory"].get("item.akd_volcanic_sulphur", 0), 0)
        self.assertEqual(snap["inventory"].get("item.akd_defence_potion_4", 0), 0)
        self.assertEqual(snap["inventory"]["item.akd_sulphur_potion"], 1)
        state = self.route(until=QUEST + ".talk_to_mori")
        snap = state.snapshot()
        self.assertEqual(snap["inventory"].get("item.akd_dark_essence_block", 0), 0)
        self.assertEqual(snap["inventory"].get("item.molten_glass", 0), 0)
        self.assertEqual(snap["inventory"]["item.akd_dark_nullifier"], 1)

    def test_trade_disabled_existing_equipment_and_deferred_reward(self):
        state = self.route(self.seed(trade=False, owns_materials=True), purchase=False, claim=False)
        self.assertTrue(state.snapshot()["flags"]["unlock.akd_complete"])
        self.assertEqual(len(state.snapshot()["held_rewards"]), 0)
        state = self.do(state, QUEST + ".claim_rewards")
        self.assertEqual(len(state.snapshot()["held_rewards"]), 2)

    def test_reversible_quest_graph_and_houses(self):
        edges = [edge for edge in self.tables["travel_edges"].values()
                 if edge["id"].startswith("travel.akd.")]
        self.assertGreaterEqual(len(edges), 130)
        graph = {(e["from_location_id"], e["to_location_id"]) for e in edges}
        for frm, to in list(graph):
            self.assertIn((to, frm), graph)
        self.assertTrue(self.route().snapshot()["flags"]["unlock.akd_piscarilius_aid"])


if __name__ == "__main__":
    unittest.main()
