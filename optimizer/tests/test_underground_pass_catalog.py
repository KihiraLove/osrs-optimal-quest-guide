"""Replay the long Underground Pass route, prerequisites, resources and exits."""

from copy import deepcopy
from pathlib import Path
import unittest

from quest_optimizer.data import Contracts, DataError, load_catalog, read_json
from quest_optimizer.semantics import CatalogValidator
from quest_optimizer.transitions import RouteState

ROOT = Path(__file__).resolve().parents[2]
QUEST = "quest.underground_pass"


class UndergroundPassCatalogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        contracts = Contracts(ROOT / "schemas")
        cls.tables = CatalogValidator(load_catalog(ROOT / "data/manifest.json", contracts), contracts).tables
        cls.profile = read_json(ROOT / "data/profiles/main-baseline.json")
        cls.ordered = read_json(ROOT / "data/catalog/underground-pass/actions.json")

    def seed(self, completed=("quest.biohazard.complete",)):
        initial = deepcopy(self.profile["initial_state"])
        initial["completed_action_ids"] = list(completed)
        initial["inventory"]["item.coins"] = 100000
        initial["counters"]["token.quest_points"] = 100
        for skill in initial["xp_tenths"]:
            initial["xp_tenths"][skill] = 20000000
        return RouteState(self.tables, self.profile["policies"], initial)

    def at(self, state, location):
        snap = state.snapshot()
        snap["location_id"] = location
        return RouteState(self.tables, self.profile["policies"], snap)

    def do(self, state, action_id):
        action = self.tables["actions"][action_id]
        state = self.at(state, action["start_location_id"])
        step = {"kind": "action", "action_id": action_id,
                "modeled_seconds": action["duration"]["expected_seconds"]}
        if action.get("planned_outcome"):
            step["planned_outcome"] = action["planned_outcome"]
        return state.apply(step)

    def replay(self):
        state = self.seed()
        for action in self.ordered:
            if action["id"] == QUEST + ".recover_after_fall":
                continue
            state = self.do(state, action["id"])
        return state

    def test_full_quest_awards_correct_rewards_at_finish(self):
        state = self.replay()
        snap = state.snapshot()
        self.assertIn(QUEST + ".complete", snap["completed_action_ids"])
        self.assertEqual(snap["counters"]["token.quest_points"], 105)
        self.assertEqual(snap["xp_tenths"]["skill.attack"], 20030000)
        self.assertEqual(snap["xp_tenths"]["skill.agility"], 20030000)
        self.assertEqual(snap["inventory"]["item.ibans_staff"], 1)
        self.assertTrue(snap["flags"]["unlock.ibans_blast"])
        self.assertTrue(snap["flags"]["unlock.well_of_voyage"])
        self.assertEqual(snap["inventory"].get("item.up_orb_of_light", 0), 0)
        for badge in ("jerro", "harry", "carl"):
            self.assertEqual(snap["inventory"].get(f"item.up_badge_{badge}", 0), 0)
        with self.assertRaises(DataError):
            self.do(state, QUEST + ".complete")

    def test_start_gates_biohazard_and_25_ranged(self):
        with self.assertRaises(DataError):
            self.do(self.seed(()), QUEST + ".talk_to_king_lathas")
        state = self.seed()
        snap = state.snapshot()
        snap["xp_tenths"]["skill.ranged"] = 0
        with self.assertRaises(DataError):
            self.do(RouteState(self.tables, self.profile["policies"], snap),
                    QUEST + ".talk_to_king_lathas")

    def test_orbs_and_effigy_require_all_materials(self):
        state = self.seed()
        state = self.do(state, QUEST + ".talk_to_king_lathas")
        state = self.do(state, "supply.underground_pass.ge_gear")
        for action in self.ordered:
            if action["id"] in (QUEST + ".talk_to_king_lathas", "supply.underground_pass.ge_gear"):
                continue
            if action["id"] == QUEST + ".orbs_to_furnace":
                snap = state.snapshot()
                snap["inventory"]["item.up_orb_of_light"] = 3
                with self.assertRaises(DataError):
                    self.do(RouteState(self.tables, self.profile["policies"], snap),
                            QUEST + ".orbs_to_furnace")
            if action["id"] == QUEST + ".use_doll_on_well":
                snap = state.snapshot()
                snap["inventory"]["item.up_iban_dove"] = 0
                with self.assertRaises(DataError):
                    self.do(RouteState(self.tables, self.profile["policies"], snap),
                            QUEST + ".use_doll_on_well")
            if action["id"] == QUEST + ".recover_after_fall":
                continue
            state = self.do(state, action["id"])

    def test_explicit_cave_return_paths_and_one_way_drops(self):
        edges = self.tables["travel_edges"]
        tunnel = "location.up.talk_to_koftik"
        walk = next(x for x in edges.values() if x["from_location_id"] ==
                    "location.west_ardougne.teleport" and x["to_location_id"] == tunnel)
        state = self.at(self.seed(), walk["from_location_id"])
        state = state.apply({"kind": "travel", "edge_id": walk["id"],
                             "modeled_seconds": walk["duration"]["expected_seconds"]})
        self.assertEqual(state.snapshot()["location_id"], tunnel)
        returns = [x for x in edges.values() if x["from_location_id"] == tunnel and
                   x["to_location_id"] == "location.west_ardougne.teleport"]
        self.assertEqual(len(returns), 1)
        drop = next(x for x in edges.values() if x["to_location_id"] ==
                    "location.up.climb_down_well" and x["from_location_id"].startswith("location.up."))
        self.assertFalse(any(x["from_location_id"] == drop["to_location_id"] and
                             x["to_location_id"] == drop["from_location_id"] for x in edges.values()
                             if x["id"].startswith("travel.underground_pass.")))


if __name__ == "__main__":
    unittest.main()
