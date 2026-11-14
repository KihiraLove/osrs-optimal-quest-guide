"""Seeded progression and reward checks for the two build-242 quest routes."""

from collections import defaultdict, deque
from pathlib import Path
import unittest

from quest_optimizer.data import Contracts, DataError, load_catalog, read_json
from quest_optimizer.semantics import CatalogValidator
from quest_optimizer.transitions import RouteState


ROOT = Path(__file__).resolve().parents[2]
NIGHT = "quest.a_night_at_the_theatre"
HEART = "quest.the_heart_of_darkness"


class TheatreHeartTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        contracts = Contracts(ROOT / "schemas")
        cls.tables = CatalogValidator(load_catalog(ROOT / "data/manifest.json", contracts), contracts).tables
        cls.profile = read_json(ROOT / "data/profiles/main-baseline.json")

    def seed(self, *, taste=True, promise=True, skills=True, flail=True):
        initial = {**self.profile["initial_state"]}
        initial["xp_tenths"] = {k: 10000000 if skills else 0 for k in initial["xp_tenths"]}
        initial["completed_action_ids"] = ["quest.twilights_promise.complete"] if promise else []
        initial["flags"] = {**initial["flags"], "flag.external.a_taste_of_hope_complete": taste}
        inventory = {**initial["inventory"], "item.coins": 50000,
                     "item.saw":1, "item.ghostspeak_amulet":1, "item.iron_axe":1}
        if flail:
            inventory["item.theatre_ivandis_flail"] = 1
        initial["inventory"] = inventory
        initial["counters"] = {**initial["counters"], "token.quest_points":50}
        initial["location_id"] = "location.theatre.speak_with_mysterious_stranger_to_start"
        return RouteState(self.tables,self.profile["policies"],initial)

    def apply(self,state,record):
        snapshot=state.snapshot()
        snapshot["location_id"] = record["start_location_id"]
        state=RouteState(self.tables,self.profile["policies"],snapshot)
        step={"kind":"action","action_id":record["id"],
              "modeled_seconds":record["duration"]["expected_seconds"]}
        if "planned_outcome" in record:
            step["planned_outcome"]=record["planned_outcome"]
        return state.apply(step,record["id"])

    def quest(self,state,activity_id):
        records=[a for a in self.tables["actions"].values() if a.get("activity_id")==activity_id]
        for record in records:
            state=self.apply(state,record)
        return state

    def test_night_rewards_and_raid_clear_gate(self):
        state=self.quest(self.seed(),NIGHT)
        snapshot=state.snapshot()
        self.assertEqual(snapshot["counters"]["token.quest_points"],52)
        self.assertEqual(snapshot["inventory"].get("item.theatre_spider_eggs",0),0)
        self.assertEqual(snapshot["inventory"].get("item.theatre_hespori_bark",0),0)
        self.assertTrue(all(NIGHT+".entry_mode_"+boss in snapshot["completed_action_ids"]
                            for boss in ("maiden","bloat","nylocas","sotetseg","xarpus","verzik")))
        self.assertEqual(snapshot["inventory"].get("item.theatre_ivandis_flail"),1)
        with self.assertRaises(DataError):
            self.apply(state,self.tables["actions"][NIGHT+".complete"])

    def test_night_unmerged_prerequisite_and_tools_are_mandatory(self):
        for state in (self.seed(taste=False),self.seed(flail=False)):
            with self.assertRaises(DataError):
                self.apply(state,self.tables["actions"][NIGHT+".speak_with_mysterious_stranger_to_start"])

    def test_night_cannot_claim_lamps_before_clearing_entry_mode(self):
        state=self.seed()
        with self.assertRaises(DataError):
            self.apply(state,self.tables["actions"][NIGHT+".complete"])
        reward=self.tables["xp_rewards"]["reward.a_night_at_the_theatre.antique_lamp"]
        self.assertEqual(reward["minimum_level"],50)
        self.assertEqual(len(reward["eligible_skills"]),6)
        self.assertTrue(reward["retainable"])
        self.assertEqual(reward["amount"]["xp_tenths"],200000)

    def test_heart_completion_rewards_and_once_only(self):
        state=self.quest(self.seed(),HEART)
        snap=state.snapshot()
        self.assertEqual(snap["counters"]["token.quest_points"],52)
        for skill in ("mining","thieving","slayer","agility"):
            self.assertEqual(snap["xp_tenths"]["skill."+skill],10080000)
        for item in ("air","earth","water","fire"):
            self.assertEqual(snap["inventory"].get("item.heart_"+item+"_urn",0),0)
        self.assertEqual(snap["inventory"].get("item.heart_emissary_robes"),1)
        with self.assertRaises(DataError):
            self.apply(state,self.tables["actions"][HEART+".complete"])

    def test_heart_requires_twilight_and_four_nonboostable_skills(self):
        record=self.tables["actions"][HEART+".talk_to_itzla_at_teomat"]
        for state in (self.seed(promise=False),self.seed(skills=False)):
            with self.assertRaises(DataError): self.apply(state,record)
        checks=record["requirements"]["requirements"]
        self.assertEqual({r["skill_id"]:r["minimum_level"] for r in checks if r["kind"]=="skill"},
                         {"skill.mining":55,"skill.thieving":48,"skill.slayer":48,"skill.agility":46})
        self.assertFalse(any(r.get("boostable",False) for r in checks))

    def test_heart_key_urn_and_robe_gates(self):
        for action in ("use_key_on_south_east_gate","fix_air_statue","enter_temple"):
            with self.assertRaises(DataError):
                self.apply(self.seed(),self.tables["actions"][HEART+"."+action])
        for element in ("air","earth","water","fire"):
            action=self.tables["actions"][HEART+".fix_"+element+"_statue"]
            self.assertEqual(action["consumes"],[{"item_id":"item.heart_"+element+"_urn","quantity":1}])

    def test_bosses_and_puzzles_are_conditional(self):
        for name in ("defeat_amoxliatl","fight_prince","complete_combat_trial",
                     "fourth_statue_step"):
            self.assertIn("planned_outcome",self.tables["actions"][HEART+"."+name])
        for name in ("entry_mode_verzik","activate_hespori_fight"):
            self.assertIn("planned_outcome",self.tables["actions"][NIGHT+"."+name])

    def test_directed_travel_joins_the_existing_graph(self):
        neighbours=defaultdict(set)
        for edge in self.tables["travel_edges"].values():
            neighbours[edge["from_location_id"]].add(edge["to_location_id"])
        for root,target in (("location.burgh_de_rott.bank","location.theatre.enter_ver_sinhaza_crypts"),
                            ("location.varlamore.teomat_prince","location.heart.defeat_amoxliatl")):
            visited={root}; frontier=deque([root])
            while frontier:
                for dest in neighbours[frontier.popleft()]:
                    if dest not in visited: visited.add(dest);frontier.append(dest)
            self.assertIn(target,visited)


if __name__=="__main__": unittest.main()
