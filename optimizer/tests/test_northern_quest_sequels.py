"""Seeded continuations of the My Arm and Fremennik quest chains."""

from collections import defaultdict, deque
from pathlib import Path
import unittest

from quest_optimizer.data import Contracts, DataError, load_catalog, read_json
from quest_optimizer.semantics import CatalogValidator
from quest_optimizer.transitions import RouteState


ROOT = Path(__file__).resolve().parents[2]
ARM = "quest.making_friends_with_my_arm."
EX = "quest.the_fremennik_exiles."


class NorthernQuestSequelsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        contracts = Contracts(ROOT / "schemas")
        cls.tables = CatalogValidator(load_catalog(ROOT / "data/manifest.json", contracts), contracts).tables
        cls.profile = read_json(ROOT / "data/profiles/main-baseline.json")

    def seed(self, missing=()):
        initial = {**self.profile["initial_state"]}
        initial["location_id"] = "location.troll_stronghold.burntmeat"
        initial["xp_tenths"] = {key: 10000000 for key in initial["xp_tenths"]}
        initial["counters"] = {**initial["counters"], "token.quest_points": 100}
        earlier = [
            "quest.swan_song.complete", "quest.romeo_juliet.complete",
            "quest.the_fremennik_isles.complete", "quest.lunar_diplomacy.complete",
            "quest.mountain_daughter.complete", "quest.my_arms_big_adventure.complete",
            "quest.cold_war.complete", "quest.heroes_quest.complete",
        ]
        initial["completed_action_ids"] = [action for action in earlier if action not in missing]
        initial["inventory"] = {**initial["inventory"], "item.coins": 200000,
                                "item.ice_gloves": 1, "item.fremennik_pet_rock": 1,
                                "item.lunar_seal_of_passage": 1}
        return RouteState(self.tables, self.profile["policies"], initial)

    def act(self, state, action_id):
        act = self.tables["actions"][action_id]
        snap = state.snapshot()
        snap["location_id"] = act["start_location_id"]
        state = RouteState(self.tables, self.profile["policies"], snap)
        transition = {"kind": "action", "action_id": action_id,
                      "modeled_seconds": act["duration"]["expected_seconds"]}
        if act.get("planned_outcome"):
            transition["planned_outcome"] = act["planned_outcome"]
        return state.apply(transition, action_id)

    def route(self, state, prefix):
        for act in self.tables["actions"].values():
            if act["id"] == ("supply.northern.arm_materials" if prefix == ARM else "supply.northern.exiles_supplies") or act.get("activity_id") == prefix[:-1]:
                state = self.act(state, act["id"])
        return state

    def test_my_arm_rewards_consumption_and_repeat_protection(self):
        snap = self.route(self.seed(), ARM).snapshot()
        self.assertEqual(snap["counters"]["token.quest_points"], 102)
        for skill, gain in (("construction",100000),("firemaking",400000),("mining",500000),("agility",500000)):
            self.assertEqual(snap["xp_tenths"]["skill."+skill],10000000+gain)
        self.assertEqual(snap["inventory"].get("item.mahogany_plank",0),0)
        self.assertEqual(snap["inventory"].get("item.northern_goat_dung",0),0)
        self.assertEqual(snap["inventory"].get("item.northern_ice_bucket",0),0)
        self.assertTrue(snap["flags"]["unlock.northern.weiss_passage"])
        with self.assertRaises(DataError):
            self.act(RouteState(self.tables,self.profile["policies"],snap), ARM+"complete")

    def test_fremennik_exiles_rewards_and_one_time_shield(self):
        snap = self.route(self.seed(), EX).snapshot()
        self.assertEqual(snap["counters"]["token.quest_points"],102)
        for skill, gain in (("slayer",500000),("crafting",500000),("runecraft",300000)):
            self.assertEqual(snap["xp_tenths"]["skill."+skill],10000000+gain)
        self.assertEqual(snap["inventory"].get("item.exiles_v_shield_reward"),1)
        self.assertTrue(snap["flags"]["unlock.northern.isle_of_stone"])
        self.assertTrue(snap["flags"]["unlock.northern.jormungand"])
        self.assertEqual(snap["inventory"].get("item.exiles_kegs",0),0)
        self.assertEqual(snap["inventory"].get("item.exiles_v_shield",0),0)
        with self.assertRaises(DataError):
            self.act(RouteState(self.tables,self.profile["policies"],snap),EX+"complete")

    def test_upstream_quest_completions_are_required(self):
        for quest, target in (("my_arms_big_adventure", ARM), ("cold_war", ARM), ("heroes_quest", EX)):
            with self.subTest(quest=quest), self.assertRaises(DataError):
                self.act(self.seed(missing=(f"quest.{quest}.complete",)), target + "start")
        snap=self.seed().snapshot()
        snap["completed_action_ids"].remove("quest.swan_song.complete")
        with self.assertRaises(DataError):
            self.act(RouteState(self.tables,self.profile["policies"],snap),ARM+"start")
        snap=self.seed().snapshot()
        snap["xp_tenths"]["skill.crafting"]=0
        with self.assertRaises(DataError):
            self.act(RouteState(self.tables,self.profile["policies"],snap),EX+"start")

    def test_supply_deficiencies_and_stage_order(self):
        state=self.seed()
        with self.assertRaises(DataError):
            self.act(state,ARM+"rooftop")
        with self.assertRaises(DataError):
            self.act(state,ARM+"build_coffin")
        state=self.act(state,ARM+"start")
        state=self.act(state,ARM+"rooftop")
        state=self.act(state,"supply.northern.arm_materials")
        state=self.act(state,ARM+"larry")
        state=self.act(state,ARM+"weiss_landfall")
        snap=state.snapshot()
        snap["inventory"].pop("item.rope",None)
        with self.assertRaises(DataError):
            self.act(RouteState(self.tables,self.profile["policies"],snap),ARM+"rope_ledge")

    def test_entrance_travel_requires_unlock_and_returns(self):
        state=self.seed()
        def travel(s, edge):
            spec=self.tables["travel_edges"][edge]
            snap=s.snapshot()
            snap["location_id"]=spec["from_location_id"]
            return RouteState(self.tables,self.profile["policies"],snap).apply(
                {"kind":"travel","edge_id":edge,"modeled_seconds":spec["duration"]["expected_seconds"]}, edge)
        with self.assertRaises(DataError):
            travel(state,"travel.northern.larry_weiss_ship_out")
        state=self.act(state,ARM+"start")
        state=self.act(state,ARM+"rooftop")
        state=self.act(state,"supply.northern.arm_materials")
        state=self.act(state,ARM+"larry")
        state=travel(state,"travel.northern.larry_weiss_ship_out")
        self.assertEqual(state.snapshot()["location_id"],"location.northern.weiss_jetty")
        state=self.act(state,ARM+"weiss_landfall")
        state=travel(state,"travel.northern.larry_weiss_ship_back")
        self.assertEqual(state.snapshot()["location_id"],"location.northern.larry")

    def test_weiss_cave_path_follows_stealth_and_cave_success(self):
        state=self.seed()
        spec=self.tables["travel_edges"]["travel.northern.weiss_boulder_cave_out"]
        snap=state.snapshot()
        snap["location_id"]=spec["from_location_id"]
        state=RouteState(self.tables,self.profile["policies"],snap)
        with self.assertRaises(DataError):
            state.apply({"kind":"travel","edge_id":spec["id"],
                         "modeled_seconds":spec["duration"]["expected_seconds"]},spec["id"])
        snap=state.snapshot()
        snap["completed_action_ids"].append(ARM+"sneak")
        state=RouteState(self.tables,self.profile["policies"],snap)
        state=state.apply({"kind":"travel","edge_id":spec["id"],
                           "modeled_seconds":spec["duration"]["expected_seconds"]},spec["id"])
        self.assertEqual(state.snapshot()["location_id"],"location.northern.weiss_cave")

    def test_northern_waypoints_have_bidirectional_exits(self):
        adj=defaultdict(set)
        for e in self.tables["travel_edges"].values():
            adj[e["from_location_id"]].add(e["to_location_id"])
        reach={"location.rellekka.brundt"}
        q=deque(reach)
        while q:
            for target in adj[q.popleft()]:
                if target not in reach:
                    reach.add(target)
                    q.append(target)
        for loc in self.tables["locations"]:
            if loc.startswith("location.northern."):
                self.assertIn(loc,reach,loc)
                self.assertTrue(any(loc in adj[t] for t in adj[loc]),loc)


if __name__ == "__main__":
    unittest.main()
