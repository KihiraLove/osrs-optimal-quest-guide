"""The Red Reef: ship combat, lighthouse, Zenith dive, and milestone rewards."""

from collections import defaultdict, deque
from pathlib import Path
import unittest

from quest_optimizer.data import Contracts, DataError, load_catalog, read_json
from quest_optimizer.semantics import CatalogValidator
from quest_optimizer.transitions import RouteState


ROOT = Path(__file__).resolve().parents[2]
PREFIX = "quest.the_red_reef"


class RedReefTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        contracts = Contracts(ROOT / "schemas")
        cls.tables = CatalogValidator(load_catalog(ROOT / "data/manifest.json", contracts), contracts).tables
        cls.profile = read_json(ROOT / "data/profiles/main-baseline.json")
        cls.actions = read_json(ROOT / "data/catalog/red-reef/actions.json")
        cls.edges = read_json(ROOT / "data/catalog/red-reef/travel_edges.json")
        cls.adj = defaultdict(list)
        for edge in cls.tables["travel_edges"].values():
            cls.adj[edge["from_location_id"]].append(edge)

    def seeded(self, *, sailing=52, smithing=48, tortured=True, boat=True):
        raw = read_json(ROOT / "data/profiles/main-baseline.json")["initial_state"]
        raw["location_id"] = "location.tortugans.raley"
        raw["inventory"] = {"item.prying.captains_log": 1}
        for skill, level in (("sailing", sailing), ("smithing", smithing)):
            raw["xp_tenths"][f"skill.{skill}"] = self.tables["skills"][f"skill.{skill}"]["xp_thresholds_tenths"][level-1]
        if tortured:
            raw["flags"]["flag.quest.troubled_tortugans.complete"] = True
            raw["flags"]["unlock.tortugans.great_conch_dock"] = True
        if boat:
            raw["flags"]["unlock.pandemonium.raft"] = True
            raw["flags"]["unlock.pandemonium.captains_log"] = True
        return RouteState(self.tables, self.profile["policies"], raw)

    @staticmethod
    def apply(state, record, *, travel=False):
        instruction = {"kind":"travel" if travel else "action",
                       "edge_id" if travel else "action_id":record["id"],
                       "modeled_seconds":record["duration"]["expected_seconds"]}
        if record.get("planned_outcome"):
            instruction["planned_outcome"] = record["planned_outcome"]
        return state.apply(instruction)

    def arrive(self, state, target):
        if state.location == target:
            return state
        queue=deque([state])
        seen={state.location}
        while queue:
            current=queue.popleft()
            for edge in self.adj[current.location]:
                new=edge["to_location_id"]
                if new in seen:
                    continue
                try:
                    moved=self.apply(current,edge,travel=True)
                except DataError:
                    continue
                if new == target:
                    return moved
                seen.add(new)
                queue.append(moved)
        self.fail(f"No connected travel from {state.location} to {target} ({len(seen)} visited)")

    def step(self, state, key):
        action=self.tables["actions"][PREFIX+"."+key]
        return self.apply(self.arrive(state,action["start_location_id"]),action)

    def at_action(self, state, key):
        action=self.tables["actions"][PREFIX+"."+key]
        snap=state.snapshot()
        snap["location_id"]=action["start_location_id"]
        return self.apply(RouteState(self.tables,self.profile["policies"],snap),action)

    def at_edge(self, state, target):
        edge=next(e for e in self.edges if e["to_location_id"] == target and e["mode"] == "ship")
        snap=state.snapshot()
        snap["location_id"]=edge["from_location_id"]
        return self.apply(RouteState(self.tables,self.profile["policies"],snap),edge,travel=True)

    def replay(self,state,*,claim_marker=True):
        milestones={}
        for action in self.actions:
            key=action["id"].split(PREFIX+".",1)[1]
            if key == "inspect_sailors_marker" and not claim_marker:
                continue
            state=self.step(state,key)
            if key in ("land_red_rock", "clear_four_of_kind", "defeat_bethel", "equip_diving_gear",
                       "clear_lobster", "repair_north_dredger", "surface", "complete"):
                milestones[key]=state.snapshot()
        return state,milestones

    def test_connected_route_and_exact_quest_rewards(self):
        beginning=self.seeded()
        state,points=self.replay(beginning)
        snap=state.snapshot()
        self.assertEqual(snap["counters"]["token.quest_points"]-beginning.counters["token.quest_points"],2)
        self.assertEqual(snap["xp_tenths"]["skill.sailing"]-beginning.xp["skill.sailing"],150000)
        self.assertEqual(snap["xp_tenths"]["skill.smithing"]-beginning.xp["skill.smithing"],50000)
        self.assertEqual(snap["inventory"]["item.redreef.bosun_schematic"],1)
        self.assertNotIn("item.redreef.deep_sea_helmet",snap["inventory"])
        self.assertNotIn("item.redreef.deep_sea_apparatus",snap["inventory"])
        self.assertTrue(points["land_red_rock"]["flags"]["unlock.redreef.red_rock_dock"])
        self.assertNotIn("flag.quest.the_red_reef.complete",points["land_red_rock"]["flags"])
        for key in ("flag.redreef.pirate_ships_cleared", "flag.redreef.bethel_defeated",
                    "flag.redreef.diving_gear_equipped", "flag.redreef.lobster_cleared",
                    "flag.redreef.northern_dredger_repaired", "unlock.redreef.sacred_grove",
                    "unlock.redreef.bosuns_bench_schematic", "unlock.redreef.sailors_amulet_red_rock",
                    "flag.quest.the_red_reef.complete"):
            self.assertTrue(snap["flags"][key],key)
        self.assertEqual(points["equip_diving_gear"]["inventory"]["item.redreef.deep_sea_helmet"],1)
        self.assertNotIn("item.redreef.deep_sea_helmet",points["surface"]["inventory"])
        with self.assertRaises(DataError):
            self.at_action(state,"complete")

    def test_sailors_marker_is_optional_and_claimable_later(self):
        state,_=self.replay(self.seeded(),claim_marker=False)
        self.assertTrue(state.snapshot()["flags"]["flag.quest.the_red_reef.complete"])
        self.assertNotIn("unlock.redreef.sailors_amulet_red_rock",state.snapshot()["flags"])
        state=self.step(state,"inspect_sailors_marker")
        self.assertTrue(state.snapshot()["flags"]["unlock.redreef.sailors_amulet_red_rock"])
        with self.assertRaises(DataError):
            self.at_action(state,"inspect_sailors_marker")

    def test_quest_level_boat_and_stage_gates(self):
        for opts in ({"sailing":51},{"smithing":47},{"tortured":False}):
            with self.subTest(opts=opts),self.assertRaises(DataError):
                self.at_action(self.seeded(**opts),"start")
        with self.assertRaises(DataError):
            self.at_edge(self.seeded(boat=False),"location.redreef.red_dock")
        with self.assertRaises(DataError):
            self.at_action(self.seeded(),"complete")
        for key in ("clear_bark_of_bight", "defeat_bethel", "dive", "repair_north_dredger"):
            with self.subTest(stage=key),self.assertRaises(DataError):
                self.at_action(self.seeded(),key)

    def test_mandatory_ship_and_diving_gates(self):
        state=self.seeded()
        for action in self.actions:
            key=action["id"].split(PREFIX+".",1)[1]
            if key == "clear_four_of_kind":
                with self.assertRaises(DataError):
                    self.at_edge(state,"location.redreef.last_dock")
            if key == "equip_diving_gear":
                with self.assertRaises(DataError):
                    self.at_action(state,"dive")
            if key == "clear_lobster":
                with self.assertRaises(DataError):
                    self.at_action(state,"repair_north_dredger")
            state=self.step(state,key)


if __name__ == "__main__":
    unittest.main()
