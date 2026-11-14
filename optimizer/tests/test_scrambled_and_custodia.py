"""Varlamore egg and missing-person quest stages, supplies, rewards and gates."""

from collections import defaultdict, deque
from pathlib import Path
import unittest

from quest_optimizer.data import Contracts, DataError, load_catalog, read_json
from quest_optimizer.semantics import CatalogValidator
from quest_optimizer.transitions import RouteState


ROOT = Path(__file__).resolve().parents[2]
SCR = "quest.scrambled."
CUS = "quest.shadows_of_custodia."
SUP = "supply.varlamore.custodia_defence_kit"


class ScrambledCustodiaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        contracts = Contracts(ROOT / "schemas")
        cls.tables = CatalogValidator(
            load_catalog(ROOT / "data/manifest.json", contracts), contracts
        ).tables
        cls.profile = read_json(ROOT / "data/profiles/main-baseline.json")

    def seed(self, *, children=True):
        initial = {**self.profile["initial_state"]}
        initial["location_id"] = "location.scrambled.tal_teok_temple"
        initial["xp_tenths"] = {k: 10000000 for k in initial["xp_tenths"]}
        initial["counters"] = {**initial["counters"], "token.quest_points": 50}
        initial["completed_action_ids"] = (
            ["quest.children_of_the_sun.complete"] if children else []
        )
        initial["inventory"] = {**initial["inventory"], "item.coins": 50000}
        return RouteState(self.tables, self.profile["policies"], initial)

    def apply_action(self, state, action_id):
        record = self.tables["actions"][action_id]
        snap = state.snapshot()
        snap["location_id"] = record["start_location_id"]
        state = RouteState(self.tables, self.profile["policies"], snap)
        step = {
            "kind": "action", "action_id": action_id,
            "modeled_seconds": record["duration"]["expected_seconds"],
        }
        if record.get("planned_outcome"):
            step["planned_outcome"] = record["planned_outcome"]
        return state.apply(step, action_id)

    def quest(self, state, prefix):
        for record in self.tables["actions"].values():
            if record.get("activity_id") == prefix[:-1] or (
                prefix == CUS and record["id"] == SUP
            ):
                state = self.apply_action(state, record["id"])
        return state

    def test_scrambled_completion_rewards_once(self):
        state = self.quest(self.seed(), SCR)
        snap = state.snapshot()
        self.assertEqual(snap["counters"]["token.quest_points"], 51)
        for s in ("construction", "cooking", "smithing"):
            self.assertEqual(snap["xp_tenths"]["skill."+s], 10050000)
        for item in ("scrambled_smith_axe", "scrambled_tea", "scrambled_large_egg",
                     "scrambled_dragon_egg", "scrambled_jaguar_egg", "scrambled_reassembled_egg"):
            self.assertEqual(snap["inventory"].get("item."+item, 0), 0, item)
        self.assertEqual(snap["inventory"]["item.iron_nails"], 14)
        with self.assertRaises(DataError):
            self.apply_action(state, SCR+"complete")

    def test_custodia_completion_and_stalker_den_unlock(self):
        state = self.quest(self.seed(), CUS)
        snap = state.snapshot()
        self.assertEqual(snap["counters"]["token.quest_points"], 52)
        for skill, amount in (("slayer",100000),("hunter",40000),
                              ("fishing",30000),("construction",30000)):
            self.assertEqual(snap["xp_tenths"]["skill."+skill], 10000000+amount)
        self.assertTrue(snap["flags"]["unlock.custodia.stalker_den"])
        for item in ("willow_longbow", "maple_logs", "custodia_wet_scrap"):
            self.assertEqual(snap["inventory"].get("item."+item, 0), 0)
        with self.assertRaises(DataError):
            self.apply_action(state, CUS+"complete")

    def test_starts_require_children_of_the_sun_and_unboostable_skills(self):
        for start in (SCR+"start",CUS+"start"):
            with self.assertRaises(DataError):
                self.apply_action(self.seed(children=False), start)
        snap = self.seed().snapshot()
        snap["xp_tenths"]["skill.construction"] = 0
        with self.assertRaises(DataError):
            self.apply_action(RouteState(self.tables,self.profile["policies"],snap),SCR+"start")
        snap = self.seed().snapshot()
        snap["xp_tenths"]["skill.slayer"] = 0
        with self.assertRaises(DataError):
            self.apply_action(RouteState(self.tables,self.profile["policies"],snap),CUS+"start")

    def test_scrambled_cart_and_egg_puzzle_need_real_materials(self):
        state = self.apply_action(self.seed(), SCR+"start")
        with self.assertRaises(DataError):
            self.apply_action(state, SCR+"cart")
        with self.assertRaises(DataError):
            self.apply_action(state, SCR+"reassemble")
        self.assertEqual(
            len(self.tables["actions"][SCR+"reassemble"]["consumes"]),3
        )
        self.assertEqual(
            self.tables["actions"][SCR+"cart"]["consumes"],
            [{"item_id":"item.plank","quantity":2},
             {"item_id":"item.iron_nails","quantity":6}],
        )

    def test_custodia_supply_and_wall_cannot_be_skipped(self):
        state = self.apply_action(self.seed(), CUS+"start")
        with self.assertRaises(DataError):
            self.apply_action(state, CUS+"arm_guards")
        with self.assertRaises(DataError):
            self.apply_action(state, CUS+"reinforce_wall")
        self.assertEqual(self.tables["actions"][CUS+"arm_guards"]["consumes"],
                         [{"item_id":"item.willow_longbow","quantity":4}])
        self.assertEqual(self.tables["actions"][CUS+"reinforce_wall"]["consumes"],
                         [{"item_id":"item.maple_logs","quantity":4}])

    def test_stalker_den_edge_is_locked_until_clues(self):
        edge = self.tables["travel_edges"]["travel.varlamore_batch.den_interior_out"]
        state = self.seed()
        snap = state.snapshot()
        snap["location_id"] = edge["from_location_id"]
        state = RouteState(self.tables,self.profile["policies"],snap)
        transition = {"kind":"travel","edge_id":edge["id"],
                      "modeled_seconds":edge["duration"]["expected_seconds"]}
        with self.assertRaises(DataError):
            state.apply(transition,edge["id"])
        snap = state.snapshot()
        snap["completed_action_ids"].append(CUS+"track_cave")
        state = RouteState(self.tables,self.profile["policies"],snap).apply(transition,edge["id"])
        self.assertEqual(state.snapshot()["location_id"],"location.custodia.injured_boys")
        back = self.tables["travel_edges"]["travel.varlamore_batch.den_interior_back"]
        state = state.apply({"kind":"travel","edge_id":back["id"],
                             "modeled_seconds":back["duration"]["expected_seconds"]},back["id"])
        self.assertEqual(state.snapshot()["location_id"],"location.custodia.stalker_cave")

    def test_all_new_locations_connect_to_the_quetzal_network(self):
        adjacency = defaultdict(set)
        for edge in self.tables["travel_edges"].values():
            adjacency[edge["from_location_id"]].add(edge["to_location_id"])
        start = {"location.varlamore.renu_tal_teklan", "location.varlamore.renu_auburnvale"}
        visited, queue = set(start), deque(start)
        while queue:
            for neighbor in adjacency[queue.popleft()]:
                if neighbor not in visited:
                    visited.add(neighbor)
                    queue.append(neighbor)
        for location_id in self.tables["locations"]:
            if location_id.startswith(("location.scrambled.","location.custodia.")):
                self.assertIn(location_id,visited,location_id)
                self.assertTrue(adjacency[location_id],location_id)


if __name__ == "__main__":
    unittest.main()
