"""Lunar Diplomacy, Dream Mentor, their rewards and island travel gates."""

from collections import defaultdict, deque
from pathlib import Path
import unittest

from quest_optimizer.data import Contracts, DataError, load_catalog, read_json
from quest_optimizer.semantics import CatalogValidator
from quest_optimizer.transitions import RouteState


ROOT = Path(__file__).resolve().parents[2]
LUNAR = "quest.lunar_diplomacy."
MENTOR = "quest.dream_mentor."
SUPPLIES = "supply.lunar_quests."


class LunarIsleQuestTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        contracts = Contracts(ROOT / "schemas")
        cls.tables = CatalogValidator(load_catalog(ROOT / "data/manifest.json", contracts), contracts).tables
        cls.profile = read_json(ROOT / "data/profiles/main-baseline.json")

    def seed(self):
        initial = {**self.profile["initial_state"]}
        initial["location_id"] = "location.lunar_quests.lokar"
        initial["xp_tenths"] = {name: 10000000 for name in initial["xp_tenths"]}
        initial["counters"] = {**initial["counters"], "token.quest_points": 100}
        initial["completed_action_ids"] = [
            "quest.the_fremennik_trials.complete", "quest.lost_city.complete",
            "quest.rune_mysteries.complete", "quest.shilo_village.complete",
            "quest.eadgars_ruse.complete",
        ]
        initial["inventory"] = {
            **initial["inventory"], "item.coins": 150000,
            "item.dramen_staff": 1, "item.goutweed": 1,
            "item.troll_storeroom_key": 1,
        }
        return RouteState(self.tables, self.profile["policies"], initial)

    def action(self, state, action_id):
        record = self.tables["actions"][action_id]
        snapshot = state.snapshot()
        snapshot["location_id"] = record["start_location_id"]
        state = RouteState(self.tables, self.profile["policies"], snapshot)
        step = {"kind": "action", "action_id": action_id,
                "modeled_seconds": record["duration"]["expected_seconds"]}
        if record.get("planned_outcome"):
            step["planned_outcome"] = record["planned_outcome"]
        return state.apply(step, action_id)

    def travel(self, state, edge_id):
        record = self.tables["travel_edges"][edge_id]
        return state.apply({"kind": "travel", "edge_id": edge_id,
                            "modeled_seconds": record["duration"]["expected_seconds"]}, edge_id)

    def lunar(self):
        state = self.seed()
        for action in self.tables["actions"].values():
            if action["id"] in {SUPPLIES + "lunar_supplies"} or action.get("activity_id") == "quest.lunar_diplomacy":
                state = self.action(state, action["id"])
        return state

    def mentor(self):
        state = self.lunar()
        for action in self.tables["actions"].values():
            if action["id"] == SUPPLIES + "dream_food" or action.get("activity_id") == "quest.dream_mentor":
                state = self.action(state, action["id"])
        return state

    def test_lunar_quest_full_route_awards_once_and_retains_equipment(self):
        state = self.lunar()
        snap = state.snapshot()
        self.assertEqual(snap["counters"]["token.quest_points"], 102)
        self.assertEqual(snap["xp_tenths"]["skill.magic"], 10050000)
        self.assertEqual(snap["xp_tenths"]["skill.runecraft"], 10050000)
        self.assertEqual(snap["inventory"].get("item.astral_rune"), 50)
        self.assertEqual(snap["inventory"].get("item.lunar_seal_of_passage"), 1)
        self.assertTrue(snap["flags"]["unlock.lunar_spellbook"])
        self.assertTrue(snap["flags"]["unlock.astral_altar"])
        for name in ("lunar_staff", "lunar_helm", "lunar_amulet", "lunar_cape", "lunar_torso", "lunar_legs", "lunar_gloves", "lunar_boots", "lunar_ring"):
            self.assertEqual(snap["inventory"].get("item." + name), 1, name)
        self.assertEqual(snap["inventory"].get("item.lunar_suqah_hide", 0), 0)
        with self.assertRaises(DataError):
            self.action(state, LUNAR + "complete")

    def test_lunar_start_prerequisites_and_dream_trial_join(self):
        snap = self.seed().snapshot()
        snap["completed_action_ids"].remove("quest.shilo_village.complete")
        with self.assertRaises(DataError):
            self.action(RouteState(self.tables,self.profile["policies"],snap), LUNAR + "start")
        snap = self.seed().snapshot()
        snap["xp_tenths"]["skill.crafting"] = 0
        with self.assertRaises(DataError):
            self.action(RouteState(self.tables,self.profile["policies"],snap), LUNAR + "start")
        state = self.action(self.seed(), LUNAR + "start")
        with self.assertRaises(DataError):
            self.action(state, LUNAR + "defeat_me")
        # Cannot light the emerald lantern with an unfuelled quest lantern.
        with self.assertRaises(DataError):
            self.action(state, LUNAR + "prepare_lantern")

    def test_dream_mentor_four_bosses_and_retainable_lamp(self):
        state = self.mentor()
        snap = state.snapshot()
        self.assertEqual(snap["counters"]["token.quest_points"], 104)
        self.assertEqual(snap["xp_tenths"]["skill.hitpoints"], 10150000)
        self.assertEqual(snap["xp_tenths"]["skill.magic"], 10150000)
        self.assertTrue(snap["flags"]["unlock.dream_mentor_spells"])
        self.assertTrue(snap["flags"]["unlock.lunar_bank_no_seal"])
        self.assertEqual(len(snap["held_rewards"]), 1)
        self.assertEqual(snap["inventory"].get("item.goutweed",0),0)
        self.assertEqual(snap["inventory"].get("item.astral_rune"),49)
        with self.assertRaises(DataError):
            self.action(state, MENTOR + "complete")
        with self.assertRaises(DataError):
            state.apply({"kind": "reward_use", "reward_id": "reward.dream_mentor.dreamy_lamp",
                         "instance_id": "reward.dream_mentor.dreamy_lamp.instance.1",
                         "skill_id": "skill.prayer", "gain_xp_tenths":150000,
                         "overrides_observed_skill_restriction":False})
        state = state.apply({"kind": "reward_use", "reward_id": "reward.dream_mentor.dreamy_lamp",
                             "instance_id": "reward.dream_mentor.dreamy_lamp.instance.1",
                             "skill_id": "skill.strength", "gain_xp_tenths":150000,
                             "overrides_observed_skill_restriction":False})
        self.assertEqual(state.snapshot()["xp_tenths"]["skill.strength"],10150000)
        self.assertEqual(state.snapshot()["held_rewards"],[])

    def test_dream_mentor_combat_and_supply_gates(self):
        fresh=self.seed()
        formula=self.tables["combat_formulas"]["formula.osrs_combat_level"]
        def level(name):
            return fresh.level("skill."+name)
        expected=(20*(level("defence")+level("hitpoints")+level("prayer")//2)
                  + max(26*(level("attack")+level("strength")),
                        39*level("magic"),39*level("ranged")))//80
        self.assertEqual(fresh._combat_level(formula),expected)
        snap = self.seed().snapshot()
        snap["completed_action_ids"].append(LUNAR + "complete")
        snap["xp_tenths"] = {name:0 for name in snap["xp_tenths"]}
        with self.assertRaises(DataError):
            self.action(RouteState(self.tables,self.profile["policies"],snap), MENTOR + "start")
        snap = self.lunar().snapshot()
        snap["inventory"].pop("item.goutweed")
        state = RouteState(self.tables,self.profile["policies"],snap)
        for sid in ("start","feed_first","feed_second","feed_third","ask_armour","jack_equipment", "equip_cyrisus","restore_cyrisus","oneiromancer","water_vial"):
            if sid=="feed_first":
                state = self.action(state,SUPPLIES+"dream_food")
            state=self.action(state,MENTOR+sid)
        with self.assertRaises(DataError):
            self.action(state,MENTOR+"add_goutweed")

    def test_ship_passage_and_cave_exits_use_directed_travel(self):
        state = self.action(self.seed(), LUNAR + "start")
        state = self.action(state,LUNAR + "brundt_seal")
        snap=state.snapshot()
        snap["location_id"]="location.lunar_quests.lokar"
        state=RouteState(self.tables,self.profile["policies"],snap)
        state=self.travel(state,"travel.lunar_quests.ship_pier_out")
        with self.assertRaises(DataError):
            self.travel(state,"travel.lunar_quests.ship_to_isle_out")
        snap=state.snapshot()
        snap["completed_action_ids"].append(LUNAR+"clean_crate")
        state=RouteState(self.tables,self.profile["policies"],snap)
        state=self.travel(state,"travel.lunar_quests.ship_to_isle_out")
        self.assertEqual(state.snapshot()["location_id"],"location.lunar_quests.isle_landing")
        # Intra-island reverse paths are explicit; the cave is not a one-way sink.
        snap=state.snapshot()
        snap["location_id"]="location.lunar_quests.cyrisus_cave"
        cave=RouteState(self.tables,self.profile["policies"],snap)
        cave=self.travel(cave,"travel.lunar_quests.isle_cyrisus_back")
        self.assertEqual(cave.snapshot()["location_id"],"location.lunar_quests.isle_stalagmite")

    def test_each_new_waypoint_connected_in_both_directions(self):
        adjacency=defaultdict(set)
        for e in self.tables["travel_edges"].values():
            adjacency[e["from_location_id"]].add(e["to_location_id"])
        reachable={"location.rellekka.brundt"}
        queue=deque(reachable)
        while queue:
            for target in adjacency[queue.popleft()]:
                if target not in reachable:
                    reachable.add(target)
                    queue.append(target)
        for loc in self.tables["locations"]:
            if loc.startswith("location.lunar_quests."):
                self.assertIn(loc,reachable,loc)
                self.assertTrue(any(loc in adjacency[t] for t in adjacency[loc]),loc)


if __name__=="__main__":
    unittest.main()
