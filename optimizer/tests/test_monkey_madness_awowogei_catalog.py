"""Focused Monkey Madness I and RFD King Awowogei seeded replay tests."""
from copy import deepcopy
from pathlib import Path
import unittest

from quest_optimizer.data import Contracts, DataError, load_catalog, read_json
from quest_optimizer.semantics import CatalogValidator
from quest_optimizer.transitions import RouteState

ROOT = Path(__file__).resolve().parents[2]
MM = "quest.monkey_madness_i"
RFD = "rfd.freeing_king_awowogei"


class MonkeyMadnessAndAwowogeiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        contracts = Contracts(ROOT / "schemas")
        cls.tables = CatalogValidator(load_catalog(ROOT / "data/manifest.json", contracts), contracts).tables
        cls.profile = read_json(ROOT / "data/profiles/main-baseline.json")

    def seed(self, prerequisites=()):
        initial = deepcopy(self.profile["initial_state"])
        initial["completed_action_ids"] = list(prerequisites)
        initial["counters"]["token.quest_points"] = 100
        initial["inventory"]["item.coins"] = 100000
        for skill_id in initial["xp_tenths"]:
            initial["xp_tenths"][skill_id] = 50000000
        return RouteState(self.tables, self.profile["policies"], initial)

    def at(self, state, location_id):
        snapshot = state.snapshot()
        snapshot["location_id"] = location_id
        return RouteState(self.tables, self.profile["policies"], snapshot)

    def do(self, state, action_id):
        action = self.tables["actions"][action_id]
        state = self.at(state, action["start_location_id"])
        step = {"kind": "action", "action_id": action_id,
                "modeled_seconds": action["duration"]["expected_seconds"]}
        if "planned_outcome" in action:
            step["planned_outcome"] = action["planned_outcome"]
        return state.apply(step)

    def travel(self, state, edge_id):
        edge = self.tables["travel_edges"][edge_id]
        return state.apply({"kind": "travel", "edge_id": edge_id,
                            "modeled_seconds": edge["duration"]["expected_seconds"]})

    def replay(self, state, quest_id, supply_action):
        state = self.do(state, quest_id + ".start")
        state = self.do(state, supply_action)
        for action in self.tables["actions"].values():
            if action["activity_id"] == quest_id and action["id"] != quest_id + ".start":
                state = self.do(state, action["id"])
        return state

    def completed_mm(self):
        prerequisites = ("quest.the_grand_tree.complete", "quest.tree_gnome_village.complete",
                         "rfd.another_cooks_quest.complete")
        return self.replay(self.seed(prerequisites), MM, "supply.monkey_madness_i.ge_supplies")

    def test_monkey_madness_full_quest_rewards_and_gate(self):
        with self.assertRaises(DataError):
            self.do(self.seed(["quest.tree_gnome_village.complete"]), MM + ".start")
        state = self.completed_mm()
        snapshot = state.snapshot()
        self.assertIn(MM + ".complete", snapshot["completed_action_ids"])
        self.assertEqual(snapshot["counters"]["token.quest_points"], 103)
        self.assertEqual(snapshot["inventory"]["item.diamond"], 3)
        self.assertEqual(snapshot["inventory"]["item.mm_mamulet"], 1)
        self.assertEqual(snapshot["inventory"]["item.mm_karamjan_greegree"], 1)
        self.assertEqual(snapshot["inventory"]["item.lobster"], 10)
        self.assertTrue(snapshot["flags"]["unlock.ape_atoll"])
        self.assertTrue(snapshot["flags"]["unlock.dragon_scimitar"])
        with self.assertRaises(DataError):
            self.do(state, MM + ".complete")

    def test_daero_training_is_optional_and_exclusive(self):
        state = self.completed_mm()
        self.assertEqual(state.snapshot()["xp_tenths"]["skill.attack"], 50000000)
        state = self.do(state, "claim.monkey_madness_i.daero_attack_defence")
        snap = state.snapshot()
        self.assertEqual(snap["xp_tenths"]["skill.attack"], 50350000)
        self.assertEqual(snap["xp_tenths"]["skill.defence"], 50350000)
        self.assertEqual(snap["xp_tenths"]["skill.strength"], 50200000)
        self.assertEqual(snap["xp_tenths"]["skill.hitpoints"], 50200000)
        with self.assertRaises(DataError):
            self.do(state, "claim.monkey_madness_i.daero_strength_hitpoints")

    def test_king_awowogei_route_and_rewards(self):
        state = self.completed_mm()
        state = self.replay(state, RFD, "supply.rfd_awowogei.ge_supplies")
        snap = state.snapshot()
        self.assertIn(RFD + ".complete", snap["completed_action_ids"])
        self.assertEqual(snap["counters"]["token.quest_points"], 104)
        self.assertEqual(snap["xp_tenths"]["skill.cooking"], 50100000)
        self.assertEqual(snap["xp_tenths"]["skill.agility"], 50100000)
        self.assertTrue(snap["flags"]["unlock.ape_atoll_teleport"])
        self.assertTrue(snap["flags"]["unlock.rfd.awowogei_chest"])
        self.assertEqual(snap["inventory"]["item.rfd_zombie_greegree"], 1)
        self.assertEqual(snap["inventory"]["item.rfd_ninja_greegree"], 1)
        self.assertEqual(snap["inventory"]["item.rfd_gorilla_greegree"], 1)
        with self.assertRaises(DataError):
            self.do(state, RFD + ".complete")

    def test_awowogei_requires_monkey_madness_and_cooking(self):
        state = self.seed(["rfd.another_cooks_quest.complete"])
        with self.assertRaises(DataError):
            self.do(state, RFD + ".start")
        state = self.completed_mm()
        state = self.do(state, RFD + ".start")
        state = self.do(state, "supply.rfd_awowogei.ge_supplies")
        for action in self.tables["actions"].values():
            if action["id"] == RFD + ".cook_stuffed_snake":
                break
            if action["activity_id"] == RFD and action["id"] != RFD + ".start":
                state = self.do(state, action["id"])
        low = state.snapshot()
        low["xp_tenths"]["skill.cooking"] = 0
        with self.assertRaises(DataError):
            self.do(RouteState(self.tables, self.profile["policies"], low), RFD + ".cook_stuffed_snake")
        state = self.do(state, RFD + ".cook_stuffed_snake")
        self.assertEqual(state.snapshot()["inventory"]["item.rfd_cooked_stuffed_snake"], 1)

    def test_return_travel_includes_ape_atoll_caves(self):
        state = self.completed_mm()
        state = self.at(state, "location.mm.zooknock")
        path = "travel.mm.location_mm_zooknock.location_mm_mould"
        state = self.travel(state, path)
        self.assertEqual(state.snapshot()["location_id"], "location.mm.mould")
        state = self.travel(state, "travel.mm.location_mm_mould.location_mm_zooknock")
        self.assertEqual(state.snapshot()["location_id"], "location.mm.zooknock")


if __name__ == "__main__":
    unittest.main()
