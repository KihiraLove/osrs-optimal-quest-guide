"""Replay Darkness of Hallowvale, its supplies and deferred experience tome."""

from copy import deepcopy
from pathlib import Path
import unittest

from quest_optimizer.data import Contracts, DataError, load_catalog, read_json
from quest_optimizer.semantics import CatalogValidator
from quest_optimizer.transitions import RouteState


ROOT = Path(__file__).resolve().parents[2]
QUEST = "quest.darkness_of_hallowvale"
GATES = {"construction": 5, "mining": 20, "thieving": 22, "agility": 26,
         "crafting": 32, "magic": 33, "strength": 40}


class DarknessOfHallowvaleCatalogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        contracts = Contracts(ROOT / "schemas")
        cls.tables = CatalogValidator(load_catalog(ROOT / "data/manifest.json", contracts), contracts).tables
        cls.profile = read_json(ROOT / "data/profiles/main-baseline.json")
        cls.actions = read_json(ROOT / "data/catalog/darkness-of-hallowvale/actions.json")

    def seed(self, *, predecessor=True, trade=True, own=False):
        initial = deepcopy(self.profile["initial_state"])
        initial["completed_action_ids"] = ["quest.in_aid_of_the_myreque.complete"] if predecessor else []
        initial["counters"]["token.quest_points"] = 100
        initial["inventory"]["item.coins"] = 500_000
        for skill in initial["xp_tenths"]:
            initial["xp_tenths"][skill] = 20_000_000
        if own:
            for id, qty in (("plank", 2), ("steel_nails", 8), ("hammer", 1), ("knife", 1)):
                initial["inventory"]["item." + id] = qty
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

    def route(self, state=None, *, supply=True, until=None):
        state = state or self.seed()
        for action in self.actions:
            if not supply and action["id"] == "supply.doh.boat_repair_and_knife":
                continue
            state = self.do(state, action["id"])
            if action["id"] == until:
                return state
        if until:
            self.fail("Missing action " + until)
        return state

    def test_complete_route_reconciles_fixed_rewards_and_tome(self):
        state = self.route()
        snap = state.snapshot()
        self.assertEqual(snap["counters"]["token.quest_points"], 102)
        self.assertEqual(snap["xp_tenths"]["skill.agility"], 20_070_000)
        self.assertEqual(snap["xp_tenths"]["skill.thieving"], 20_060_000)
        self.assertEqual(snap["xp_tenths"]["skill.construction"], 20_020_000)
        self.assertEqual(snap["xp_tenths"]["skill.magic"], 20_000_430)
        self.assertTrue(snap["flags"]["unlock.doh_complete"])
        self.assertTrue(snap["flags"]["unlock.doh_shortcut_doors"])
        self.assertTrue(snap["flags"]["unlock.doh_vanstrom_survived"])
        self.assertEqual(snap["inventory"].get("item.plank", 0), 0)
        self.assertEqual(snap["inventory"].get("item.steel_nails", 0), 0)
        self.assertEqual(len(snap["held_rewards"]), 1)
        self.assertEqual(snap["held_rewards"][0]["reward_id"], "reward.doh.tome_of_experience")
        with self.assertRaises(DataError):
            self.do(state, QUEST + ".complete")

    def test_in_aid_of_the_myreque_is_mandatory(self):
        state = self.seed(predecessor=False)
        state = self.do(state, QUEST + ".climb_over_broken_wall")
        state = self.do(state, QUEST + ".enter_burgh_pub_basement")
        with self.assertRaises(DataError):
            self.do(state, QUEST + ".start")

    def test_all_seven_skill_gates(self):
        for skill_name in GATES:
            state = self.seed()
            state = self.do(state, QUEST + ".climb_over_broken_wall")
            state = self.do(state, QUEST + ".enter_burgh_pub_basement")
            snap = state.snapshot()
            snap["xp_tenths"]["skill." + skill_name] = 0
            with self.subTest(skill=skill_name), self.assertRaises(DataError):
                self.do(RouteState(self.tables, state.policies, snap), QUEST + ".start")

    def test_ironman_materials_and_two_independent_boat_repairs(self):
        state = self.route(self.seed(trade=False, own=True), supply=False,
                           until=QUEST + ".use_plank_on_boat")
        self.assertEqual(state.snapshot()["inventory"]["item.plank"], 1)
        self.assertEqual(state.snapshot()["inventory"]["item.steel_nails"], 4)
        state = self.do(state, QUEST + ".use_plank_on_chute")
        self.assertEqual(state.snapshot()["inventory"].get("item.plank", 0), 0)
        self.assertTrue(state.snapshot()["flags"]["unlock.doh_boat_repaired"])

    def test_telegrab_requires_both_runes_and_five_attack_boss_flag(self):
        state = self.route(until=QUEST + ".get_runes")
        snap = state.snapshot()
        snap["inventory"]["item.law_rune"] = 0
        with self.assertRaises(DataError):
            self.do(RouteState(self.tables, state.policies, snap), QUEST + ".telegrab_book")
        state = self.do(state, QUEST + ".telegrab_book")
        self.assertEqual(state.snapshot()["inventory"]["item.doh_haemalchemy_book"], 1)

    def test_travel_graph_has_return_legs_and_tome_three_picks(self):
        edges = [e for e in self.tables["travel_edges"].values() if e["id"].startswith("travel.doh.")]
        self.assertGreaterEqual(len(edges), 100)
        pairs = {(e["from_location_id"], e["to_location_id"]) for e in edges}
        self.assertTrue(all((end, start) in pairs for start, end in pairs))
        reward = self.tables["xp_rewards"]["reward.doh.tome_of_experience"]
        self.assertEqual(reward["selection_count"], 3)
        self.assertEqual(reward["minimum_level"], 30)
        self.assertFalse(reward["distinct_skills"])


if __name__ == "__main__":
    unittest.main()
