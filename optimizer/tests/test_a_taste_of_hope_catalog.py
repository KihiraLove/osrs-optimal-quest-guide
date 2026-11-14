"""Focused replay of the Myreque's A Taste of Hope route and reward choices."""

from copy import deepcopy
from pathlib import Path
import unittest

from quest_optimizer.data import Contracts, DataError, load_catalog, read_json
from quest_optimizer.semantics import CatalogValidator
from quest_optimizer.transitions import RouteState


ROOT = Path(__file__).resolve().parents[2]
QUEST = "quest.a_taste_of_hope"
GATES = {"crafting": 48, "agility": 45, "attack": 40, "herblore": 40, "slayer": 38}


class ATasteOfHopeCatalogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        contracts = Contracts(ROOT / "schemas")
        cls.tables = CatalogValidator(load_catalog(ROOT / "data/manifest.json", contracts), contracts).tables
        cls.profile = read_json(ROOT / "data/profiles/main-baseline.json")
        cls.actions = read_json(ROOT / "data/catalog/a-taste-of-hope/actions.json")

    def seed(self, *, predecessor=True, trade=True, owned=False):
        initial = deepcopy(self.profile["initial_state"])
        initial["completed_action_ids"] = ["quest.darkness_of_hallowvale.complete"] if predecessor else []
        initial["counters"]["token.quest_points"] = 100
        initial["inventory"]["item.coins"] = 500_000
        for name in initial["xp_tenths"]:
            initial["xp_tenths"][name] = 20_000_000
        if owned:
            for name, qty in (("emerald", 1), ("chisel", 1), ("cosmic_rune", 1),
                              ("air_rune", 3), ("rod_of_ivandis_10", 1)):
                initial["inventory"]["item." + name] = qty
        policies = deepcopy(self.profile["policies"])
        policies["trade_enabled"] = trade
        return RouteState(self.tables, policies, initial)

    def do(self, state, id):
        action = self.tables["actions"][id]
        snap = state.snapshot()
        snap["location_id"] = action["start_location_id"]
        state = RouteState(self.tables, state.policies, snap)
        transition = {"kind": "action", "action_id": id,
                      "modeled_seconds": action["duration"]["expected_seconds"]}
        if "planned_outcome" in action:
            transition["planned_outcome"] = action["planned_outcome"]
        return state.apply(transition)

    def route(self, state=None, *, optional=True, until=None):
        state = state or self.seed()
        for action in self.actions:
            if not optional and action["id"].startswith("supply.ath."):
                continue
            state = self.do(state, action["id"])
            if until and action["id"] == until:
                return state
        if until:
            self.fail("Missing action " + until)
        return state

    def test_route_awards_quest_point_tome_flail_and_medallion(self):
        state = self.route()
        snap = state.snapshot()
        self.assertEqual(snap["counters"]["token.quest_points"], 101)
        self.assertEqual(snap["xp_tenths"]["skill.magic"], 20_000_370)
        self.assertTrue(snap["flags"]["unlock.ath_complete"])
        self.assertTrue(snap["flags"]["unlock.ath_ranis"])
        self.assertEqual(snap["inventory"]["item.ivandis_flail"], 1)
        self.assertEqual(snap["inventory"]["item.drakans_medallion"], 1)
        self.assertEqual(len(snap["held_rewards"]), 1)
        self.assertEqual(snap["held_rewards"][0]["reward_id"], "reward.ath.tome_of_experience")
        with self.assertRaises(DataError):
            self.do(state, QUEST + ".complete")

    def test_darkness_of_hallowvale_completion_is_required(self):
        with self.assertRaises(DataError):
            self.do(self.seed(predecessor=False), QUEST + ".start")

    def test_five_nonboostable_level_gates(self):
        for name in GATES:
            state = self.seed()
            snap = state.snapshot()
            snap["xp_tenths"]["skill." + name] = 0
            with self.subTest(skill=name), self.assertRaises(DataError):
                self.do(RouteState(self.tables, state.policies, snap), QUEST + ".start")

    def test_trade_disabled_preowned_supplies_no_reclaim(self):
        state = self.route(self.seed(trade=False, owned=True), optional=False)
        self.assertTrue(state.snapshot()["flags"]["unlock.ath_complete"])
        self.assertEqual(state.snapshot()["inventory"].get("item.rod_of_ivandis_10", 0), 0)

    def test_flail_and_boss_are_hard_gated(self):
        state = self.route(until=QUEST + ".get_chain")
        with self.assertRaises(DataError):
            self.do(state, QUEST + ".kill_ranis")
        state = self.do(state, "supply.ath.reclaim_rod_from_veliaf")
        state = self.do(state, "supply.ath.flail_inputs")
        before = state.snapshot()["inventory"].get("item.air_rune", 0)
        state = self.do(state, QUEST + ".make_emerald_sickle")
        state = self.do(state, QUEST + ".enchant_emerald_sickle")
        state = self.do(state, QUEST + ".make_ivandis_flail")
        self.assertEqual(state.snapshot()["inventory"].get("item.cosmic_rune", 0), 0)
        self.assertEqual(state.snapshot()["inventory"].get("item.air_rune", 0), before - 3)

    def test_tome_three_same_skill_picks_and_return_edges(self):
        tome = self.tables["xp_rewards"]["reward.ath.tome_of_experience"]
        self.assertEqual(tome["selection_count"], 3)
        self.assertEqual(tome["amount"]["xp_tenths"], 25000)
        self.assertEqual(tome["minimum_level"], 35)
        self.assertFalse(tome["distinct_skills"])
        edges = [e for e in self.tables["travel_edges"].values() if e["id"].startswith("travel.ath.")]
        self.assertGreaterEqual(len(edges), 70)
        pairs = {(e["from_location_id"], e["to_location_id"]) for e in edges}
        self.assertTrue(all((b, a) in pairs for a, b in pairs))


if __name__ == "__main__":
    unittest.main()
