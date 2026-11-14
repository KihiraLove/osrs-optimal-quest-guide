"""Defender of Varrock, The Curse of Arrav and the separate Minas claim."""

from collections import defaultdict, deque
from pathlib import Path
import unittest

from quest_optimizer.data import Contracts, DataError, load_catalog, read_json
from quest_optimizer.semantics import CatalogValidator
from quest_optimizer.transitions import RouteState


ROOT = Path(__file__).resolve().parents[2]
DOV = "quest.defender_of_varrock."
ARR = "quest.the_curse_of_arrav."
MINAS = "claim.defender_of_varrock.minas"


class ArravVarrockSequelsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        contracts = Contracts(ROOT / "schemas")
        cls.tables = CatalogValidator(load_catalog(ROOT / "data/manifest.json",contracts),contracts).tables
        cls.profile = read_json(ROOT / "data/profiles/main-baseline.json")

    def seed(self):
        initial = {**self.profile["initial_state"]}
        initial["location_id"] = "location.arrav.elias_varrock"
        initial["xp_tenths"] = {key:10000000 for key in initial["xp_tenths"]}
        initial["counters"] = {**initial["counters"],"token.quest_points":100,"token.museum.kudos":100}
        initial["completed_action_ids"] = [
            "quest.shield_of_arrav.complete", "quest.temple_of_ikov.complete",
            "quest.below_ice_mountain.complete", "quest.family_crest.complete",
            "quest.garden_of_tranquillity.complete", "quest.what_lies_below.complete",
            "quest.romeo_juliet.complete", "quest.demon_slayer.complete",
            "quest.troll_romance.complete",
        ]
        initial["inventory"]={**initial["inventory"],"item.coins":400000}
        return RouteState(self.tables,self.profile["policies"],initial)

    def action(self,state,aid):
        record=self.tables["actions"][aid]
        snap=state.snapshot()
        snap["location_id"]=record["start_location_id"]
        state=RouteState(self.tables,self.profile["policies"],snap)
        transition={"kind":"action","action_id":aid,
                    "modeled_seconds":record["duration"]["expected_seconds"]}
        if record.get("planned_outcome"):
            transition["planned_outcome"]=record["planned_outcome"]
        return state.apply(transition,aid)

    def quest(self,state,quest):
        for record in self.tables["actions"].values():
            if (record.get("activity_id")==quest[:-1]
                or record["id"] == ("supply.arrav.defender_provisions" if quest == DOV else "supply.arrav.curse_provisions")):
                state=self.action(state,record["id"])
        return state

    def test_defender_complete_rewards_once_but_not_museum_claim(self):
        state=self.quest(self.seed(),DOV)
        snap=state.snapshot()
        self.assertEqual(snap["counters"]["token.quest_points"],102)
        self.assertEqual(snap["xp_tenths"]["skill.smithing"],10150000)
        self.assertEqual(snap["xp_tenths"]["skill.hunter"],10150000)
        self.assertEqual(snap["counters"]["token.museum.kudos"],100)
        self.assertEqual(snap["held_rewards"],[])
        self.assertEqual(snap["inventory"].get("item.dov_barronite_ore",0),0)
        self.assertEqual(snap["inventory"].get("item.dov_golem_fragment",0),0)
        self.assertTrue(snap["flags"]["unlock.arrav.base_deep"])
        with self.assertRaises(DataError):
            self.action(state,DOV+"complete")

    def test_historian_minas_claim_pays_once_and_is_spendable(self):
        state=self.quest(self.seed(),DOV)
        state=self.action(state,MINAS)
        snap=state.snapshot()
        self.assertEqual(snap["counters"]["token.museum.kudos"],105)
        self.assertEqual(len(snap["held_rewards"]),1)
        with self.assertRaises(DataError):
            self.action(state,MINAS)
        reward=snap["held_rewards"][0]
        self.assertEqual(reward["reward_id"],"reward.defender_of_varrock.minas_lamp")
        state=state.apply({"kind":"reward_use","reward_id":reward["reward_id"],
                           "instance_id":reward["instance_id"],"skill_id":"skill.smithing",
                           "gain_xp_tenths":50000,"overrides_observed_skill_restriction":False})
        self.assertEqual(state.snapshot()["xp_tenths"]["skill.smithing"],10200000)

    def test_curse_of_arrav_follows_defender_and_awards_once(self):
        state=self.quest(self.seed(),DOV)
        state=self.quest(state,ARR)
        snap=state.snapshot()
        self.assertEqual(snap["counters"]["token.quest_points"],104)
        for s in ("mining","thieving","agility"):
            self.assertEqual(snap["xp_tenths"]["skill."+s],10400000)
        self.assertEqual(snap["inventory"].get("item.arrav_heart",0),0)
        self.assertEqual(snap["inventory"].get("item.arrav_filled_canopic_jar",0),0)
        self.assertTrue(snap["flags"]["unlock.arrav.fort_passage"])
        self.assertTrue(snap["flags"]["unlock.arrav.heist_passage"])
        with self.assertRaises(DataError):
            self.action(state,ARR+"complete")

    def test_quest_start_levels_and_dependency_gates(self):
        snap=self.seed().snapshot()
        snap["completed_action_ids"].remove("quest.temple_of_ikov.complete")
        with self.assertRaises(DataError):
            self.action(RouteState(self.tables,self.profile["policies"],snap),DOV+"start")
        snap=self.seed().snapshot()
        snap["xp_tenths"]["skill.hunter"]=0
        with self.assertRaises(DataError):
            self.action(RouteState(self.tables,self.profile["policies"],snap),DOV+"start")
        with self.assertRaises(DataError):
            self.action(self.seed(),ARR+"start")
        with self.assertRaises(DataError):
            self.action(self.seed(),MINAS)

    def test_supplies_mural_keys_and_grapple_must_be_real(self):
        state=self.action(self.seed(),DOV+"start")
        with self.assertRaises(DataError):
            self.action(state,DOV+"ramarno")
        state=self.quest(self.seed(),DOV)
        state=self.action(state,ARR+"start")
        with self.assertRaises(DataError):
            self.action(state,ARR+"tomb_entry")
        state=self.action(state,"supply.arrav.curse_provisions")
        state=self.action(state,ARR+"tomb_entry")
        with self.assertRaises(DataError):
            self.action(state,ARR+"tomb_levers")
        state=self.action(state,ARR+"tomb_keys")
        state=self.action(state,ARR+"tomb_levers")
        self.assertEqual(state.snapshot()["inventory"].get("item.arrav_tomb_key_south",0),0)
        # Later grapple must not be eligible before the complete heist chain.
        with self.assertRaises(DataError):
            self.action(state,ARR+"grapple")

    def test_travel_gates_are_directed_and_exits_remain_available(self):
        state=self.seed()
        edge=self.tables["travel_edges"]["travel.arrav.trapdoor_base_out"]
        snap=state.snapshot()
        snap["location_id"]=edge["from_location_id"]
        state=RouteState(self.tables,self.profile["policies"],snap)
        transit={"kind":"travel","edge_id":edge["id"],"modeled_seconds":edge["duration"]["expected_seconds"]}
        with self.assertRaises(DataError):
            state.apply(transit,edge["id"])
        snap=state.snapshot()
        snap["completed_action_ids"].append(DOV+"trace_bushes")
        state=RouteState(self.tables,self.profile["policies"],snap).apply(transit,edge["id"])
        self.assertEqual(state.snapshot()["location_id"],"location.arrav.dov_base")
        edge=self.tables["travel_edges"]["travel.arrav.trapdoor_base_back"]
        with self.assertRaises(DataError):
            state.apply({"kind":"travel","edge_id":edge["id"],
                         "modeled_seconds":edge["duration"]["expected_seconds"]},edge["id"])

    def test_every_new_waypoint_is_connected_and_has_an_exit(self):
        adjacency=defaultdict(set)
        for e in self.tables["travel_edges"].values():
            adjacency[e["from_location_id"]].add(e["to_location_id"])
        reachable={"location.varrock.east_bank","location.uzer.rug_merchant"}
        queue=deque(reachable)
        while queue:
            for nxt in adjacency[queue.popleft()]:
                if nxt not in reachable:
                    reachable.add(nxt)
                    queue.append(nxt)
        for lid in self.tables["locations"]:
            if lid.startswith("location.arrav."):
                self.assertIn(lid,reachable,lid)
                self.assertTrue(any(lid in adjacency[t] for t in adjacency[lid]),lid)


if __name__=="__main__":
    unittest.main()
