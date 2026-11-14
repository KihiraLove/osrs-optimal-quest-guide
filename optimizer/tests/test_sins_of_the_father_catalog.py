"""Seeded end-to-end checks for Sins of the Father and permanent unlocks."""

from copy import deepcopy
from pathlib import Path
import unittest

from quest_optimizer.data import Contracts, DataError, load_catalog, read_json
from quest_optimizer.semantics import CatalogValidator
from quest_optimizer.transitions import RouteState


ROOT = Path(__file__).resolve().parents[2]
QUEST = "quest.sins_of_the_father"
GATES = {"woodcutting": 62, "fletching": 60, "crafting": 56, "agility": 52,
         "attack": 50, "slayer": 50, "magic": 49}


class SinsOfTheFatherCatalogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        contracts = Contracts(ROOT / "schemas")
        cls.tables = CatalogValidator(load_catalog(ROOT / "data/manifest.json", contracts), contracts).tables
        cls.profile = read_json(ROOT / "data/profiles/main-baseline.json")
        cls.actions = read_json(ROOT / "data/catalog/sins-of-the-father/actions.json")

    def seed(self, *, taste=True, vampyre=True, trade=True, owned=False):
        initial = deepcopy(self.profile["initial_state"])
        initial["completed_action_ids"] = (["quest.a_taste_of_hope.complete"] if taste else []) + (
            ["quest.vampyre_slayer.complete"] if vampyre else [])
        initial["counters"]["token.quest_points"] = 100
        initial["inventory"]["item.coins"] = 500_000
        initial["inventory"]["item.ivandis_flail"] = 1
        for name in initial["xp_tenths"]:
            initial["xp_tenths"][name] = 20_000_000
        if owned:
            for name, qty in (("ruby", 1), ("chisel", 1), ("knife", 1),
                              ("cosmic_rune", 1), ("fire_rune", 5),
                              ("sotf_vyrewatch_top", 1), ("sotf_vyrewatch_legs", 1),
                              ("sotf_vyrewatch_shoes", 1)):
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

    def route(self, state=None, *, supplied=True, until=None):
        state = state or self.seed()
        for action in self.actions:
            if not supplied and action["id"].startswith("supply.sotf."):
                continue
            state = self.do(state, action["id"])
            if action["id"] == until:
                return state
        if until:
            self.fail("Missing action " + until)
        return state

    def test_complete_route_rewards_and_unlocks(self):
        state = self.route()
        snap = state.snapshot()
        self.assertEqual(snap["counters"]["token.quest_points"], 102)
        self.assertEqual(snap["xp_tenths"]["skill.woodcutting"], 20_006_080)
        self.assertEqual(snap["xp_tenths"]["skill.magic"], 20_000_590)
        self.assertEqual(snap["inventory"]["item.blisterwood_flail"], 1)
        self.assertEqual(snap["inventory"].get("item.sotf_blisterwood_logs", 0), 0)
        self.assertTrue(snap["flags"]["unlock.sotf_vanstrom"])
        for token in ("complete", "darkmeyer", "hallowed_sepulchre", "daeyalt_mine",
                      "darkmeyer_teleport", "graveyard_boats", "true_blood_altar"):
            with self.subTest(token=token):
                self.assertTrue(snap["flags"]["unlock.sotf_" + token])
        self.assertEqual(len(snap["held_rewards"]), 1)
        self.assertEqual(snap["held_rewards"][0]["reward_id"], "reward.sotf.tome_of_experience")
        with self.assertRaises(DataError):
            self.do(state, QUEST + ".complete")

    def test_both_predecessors_are_required(self):
        for taste, vampyre in ((False, True), (True, False)):
            with self.subTest(taste=taste, vampyre=vampyre), self.assertRaises(DataError):
                self.do(self.seed(taste=taste, vampyre=vampyre), QUEST + ".start")

    def test_seven_nonboostable_skill_gates(self):
        for name in GATES:
            state = self.seed()
            snap = state.snapshot()
            snap["xp_tenths"]["skill." + name] = 0
            with self.subTest(skill=name), self.assertRaises(DataError):
                self.do(RouteState(self.tables, state.policies, snap), QUEST + ".start")

    def test_ironman_owns_inputs_and_skips_optional_stores(self):
        state = self.route(self.seed(trade=False, owned=True), supplied=False)
        snap = state.snapshot()
        self.assertTrue(snap["flags"]["unlock.sotf_complete"])
        self.assertEqual(snap["inventory"].get("item.ivandis_flail", 0), 0)

    def test_three_bridge_repairs_consume_distinct_logs(self):
        state = self.route(until=QUEST + ".cut_bridge_logs")
        self.assertEqual(state.snapshot()["inventory"]["item.sotf_bridge_log"], 3)
        for i in range(1, 4):
            state = self.do(state, QUEST + ".repair_bridge" + str(i))
            self.assertEqual(state.snapshot()["inventory"].get("item.sotf_bridge_log", 0), 3 - i)

    def test_vyre_outfit_and_vanstrom_weapon_are_required(self):
        state = self.route(until=QUEST + ".go_down_to_polmafi_no_items")
        with self.assertRaises(DataError):
            self.do(state, QUEST + ".talk_to_polmafi")
        state = self.do(state, "supply.sotf.vyrewatch_outfit")
        state = self.do(state, QUEST + ".talk_to_polmafi")
        self.assertEqual(state.snapshot()["inventory"].get("item.sotf_vyrewatch_top", 0), 0)
        state = self.route(until=QUEST + ".talk_to_veliaf_for_final_fight")
        snap = state.snapshot()
        snap["inventory"]["item.blisterwood_flail"] = 0
        with self.assertRaises(DataError):
            self.do(RouteState(self.tables, state.policies, snap), QUEST + ".fight_vanstrom_phase_one")

    def test_arboretum_and_six_chapter_tome_rules(self):
        state = self.route(until=QUEST + ".get_note")
        with self.assertRaises(DataError):
            self.do(state, QUEST + ".cut_logs")
        state = self.do(state, QUEST + ".solve_arboretum_valves")
        state = self.do(state, QUEST + ".cut_logs")
        self.assertEqual(state.snapshot()["inventory"]["item.sotf_blisterwood_logs"], 8)
        tome = self.tables["xp_rewards"]["reward.sotf.tome_of_experience"]
        self.assertEqual(tome["selection_count"], 6)
        self.assertEqual(tome["minimum_level"], 60)
        self.assertFalse(tome["distinct_skills"])
        self.assertEqual(tome["amount"]["xp_tenths"], 150000)

    def test_reversible_travel_and_three_post_quest_boats(self):
        edges = [e for e in self.tables["travel_edges"].values() if e["id"].startswith("travel.sotf.")]
        self.assertGreaterEqual(len(edges), 145)
        pairs = {(e["from_location_id"], e["to_location_id"]) for e in edges}
        self.assertTrue(all((b, a) in pairs for a, b in pairs))
        boats = [e for e in edges if e["id"].startswith("travel.sotf.boat_")]
        self.assertEqual(len(boats), 6)
        self.assertTrue(all(e["requirements"]["requirements"][0]["token_id"] ==
                            "unlock.sotf_graveyard_boats" for e in boats))


if __name__ == "__main__":
    unittest.main()
