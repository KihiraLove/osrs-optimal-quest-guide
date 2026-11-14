"""Focused route replays for Grim Tales and The Path of Glouphrie."""
from copy import deepcopy
from pathlib import Path
import unittest

from quest_optimizer.data import Contracts, DataError, load_catalog, read_json
from quest_optimizer.semantics import CatalogValidator
from quest_optimizer.transitions import RouteState


ROOT = Path(__file__).resolve().parents[2]


class GrimAndGlouphrieTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        contracts = Contracts(ROOT / "schemas")
        catalog = load_catalog(ROOT / "data/manifest.json", contracts)
        cls.tables = CatalogValidator(catalog, contracts).tables
        cls.profile = read_json(ROOT / "data/profiles/main-baseline.json")

    def seeded(self, prerequisites):
        initial = deepcopy(self.profile["initial_state"])
        initial["inventory"]["item.coins"] = 100000
        initial["completed_action_ids"] = list(prerequisites)
        initial["counters"]["token.quest_points"] = 100
        for skill in initial["xp_tenths"]:
            initial["xp_tenths"][skill] = 50000000
        return RouteState(self.tables, self.profile["policies"], initial)

    def at(self, state, location_id):
        snapshot = state.snapshot()
        snapshot["location_id"] = location_id
        return RouteState(self.tables, self.profile["policies"], snapshot)

    def do(self, state, action_id):
        rec = self.tables["actions"][action_id]
        state = self.at(state, rec["start_location_id"])
        step = {"kind": "action", "action_id": action_id,
                "modeled_seconds": rec["duration"]["expected_seconds"]}
        if "planned_outcome" in rec:
            step["planned_outcome"] = rec["planned_outcome"]
        return state.apply(step)

    def travel(self, state, edge_id):
        rec = self.tables["travel_edges"][edge_id]
        return state.apply({"kind": "travel", "edge_id": edge_id,
                            "modeled_seconds": rec["duration"]["expected_seconds"]})

    def run_quest(self, state, quest_id, supply_id):
        for action in self.tables["actions"].values():
            if action["id"] == quest_id + ".start":
                state = self.do(state, action["id"])
                state = self.do(state, supply_id)
            elif action["activity_id"] == quest_id:
                state = self.do(state, action["id"])
        return state

    def test_grim_tales_full_route_and_rewards(self):
        q = "quest.grim_tales"
        state = self.seeded(["quest.witchs_house.complete"])
        state = self.run_quest(state, q, "supply.grim_tales.ge_supplies")
        snapshot = state.snapshot()
        self.assertIn(q + ".complete", snapshot["completed_action_ids"])
        self.assertEqual(snapshot["counters"]["token.quest_points"], 101)
        self.assertEqual(snapshot["xp_tenths"]["skill.woodcutting"], 50600000)
        self.assertEqual(snapshot["xp_tenths"]["skill.herblore"], 50150120)
        self.assertEqual(snapshot["inventory"]["item.grim_dwarven_helmet"], 1)
        self.assertEqual(snapshot["inventory"]["item.lobster"], 4)
        self.assertNotIn("item.grim_shrinking_potion", snapshot["inventory"])
        self.assertTrue(snapshot["flags"]["unlock.nmz_glod"])
        with self.assertRaises(DataError):
            self.do(state, q + ".complete")

    def test_grim_gates_and_mouse_exit(self):
        q = "quest.grim_tales"
        without_witch = self.seeded([])
        with self.assertRaises(DataError):
            self.do(without_witch, q + ".start")
        state = self.seeded(["quest.witchs_house.complete"])
        state = self.do(state, q + ".start")
        state = self.do(state, "supply.grim_tales.ge_supplies")
        for action in self.tables["actions"].values():
            if action["id"] == q + ".mix_potions":
                break
            if action["activity_id"] == q and action["id"] != q + ".start":
                state = self.do(state, action["id"])
        low = state.snapshot()
        low["xp_tenths"]["skill.herblore"] = 0
        with self.assertRaises(DataError):
            self.do(RouteState(self.tables, self.profile["policies"], low), q + ".mix_potions")
        state = self.do(state, q + ".mix_potions")
        state = self.do(state, q + ".shrink_into_mouse_hole")
        self.assertEqual(state.snapshot()["location_id"], "location.grim.mouse_lair")
        state = self.travel(state, "travel.grim.location_grim_mouse_lair.location_grim_mouse_pendant")
        state = self.travel(state, "travel.grim.location_grim_mouse_pendant.location_grim_mouse_lair")
        state = self.travel(state, "travel.grim.location_grim_mouse_lair.location_grim_witch_mousehole")
        self.assertEqual(state.snapshot()["location_id"], "location.grim.witch_mousehole")

    def test_glouphrie_full_route_and_four_lamps(self):
        q = "quest.the_path_of_glouphrie"
        prerequisites = ["quest.the_eyes_of_glouphrie.complete",
                         "quest.waterfall_quest.complete", "quest.tree_gnome_village.complete"]
        state = self.seeded(prerequisites)
        state = self.run_quest(state, q, "supply.path_of_glouphrie.ge_grapple")
        snapshot = state.snapshot()
        self.assertEqual(snapshot["counters"]["token.quest_points"], 102)
        self.assertEqual(snapshot["inventory"]["item.lobster"], 6)
        self.assertTrue(snapshot["flags"]["unlock.poison_waste_spirit_tree"])
        self.assertTrue(snapshot["flags"]["unlock.warped_creatures_slayer"])
        self.assertEqual(snapshot["location_id"], "location.yanille.hazelmere_upstairs")
        self.assertEqual(len(snapshot["held_rewards"]), 4)
        reward_id = "reward.path_of_glouphrie.strength_lamp"
        state = state.apply({"kind": "reward_use", "reward_id": reward_id,
                             "instance_id": reward_id + ".instance.1",
                             "skill_id": "skill.strength", "gain_xp_tenths": 300000,
                             "overrides_observed_skill_restriction": False})
        self.assertEqual(state.snapshot()["xp_tenths"]["skill.strength"], 50300000)
        with self.assertRaises(DataError):
            state.apply({"kind": "reward_use", "reward_id": reward_id,
                         "instance_id": reward_id + ".instance.1",
                         "skill_id": "skill.strength", "gain_xp_tenths": 300000,
                         "overrides_observed_skill_restriction": False})

    def test_glouphrie_prerequisite_grapple_and_return_paths(self):
        q = "quest.the_path_of_glouphrie"
        base = self.seeded(["quest.the_eyes_of_glouphrie.complete",
                            "quest.tree_gnome_village.complete"])
        with self.assertRaises(DataError):
            self.do(base, q + ".start")
        base = self.seeded(["quest.the_eyes_of_glouphrie.complete",
                            "quest.waterfall_quest.complete", "quest.tree_gnome_village.complete"])
        base = self.do(base, q + ".start")
        before_supplies = self.at(base, "location.path.river_bank")
        grapple = "travel.path.location_path_river_bank.location_path_longramble"
        with self.assertRaises(DataError):
            self.travel(before_supplies, grapple)
        base = self.do(base, "supply.path_of_glouphrie.ge_grapple")
        after_gianne = self.at(base, "location.path.river_bank")
        with self.assertRaises(DataError):
            self.travel(after_gianne, grapple)
        for action in self.tables["actions"].values():
            if action["id"] == q + ".ask_gianne":
                base = self.do(base, action["id"])
                break
            if action["activity_id"] == q and action["id"] != q + ".start":
                base = self.do(base, action["id"])
        path_state = self.at(base, "location.path.river_bank")
        path_state = self.travel(path_state, grapple)
        self.assertEqual(path_state.snapshot()["location_id"], "location.path.longramble")
        path_state = self.travel(path_state, "travel.path.location_path_longramble.location_path_river_bank")
        self.assertEqual(path_state.snapshot()["location_id"], "location.path.river_bank")


if __name__ == "__main__":
    unittest.main()
