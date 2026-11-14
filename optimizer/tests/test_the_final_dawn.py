"""Full seeded sequence, conditional fights and XP-choice checks for Final Dawn."""

from collections import defaultdict, deque
from pathlib import Path
import unittest

from quest_optimizer.data import Contracts, DataError, load_catalog, read_json
from quest_optimizer.semantics import CatalogValidator
from quest_optimizer.transitions import RouteState


ROOT=Path(__file__).resolve().parents[2]
Q="quest.the_final_dawn"
LAMP="reward.the_final_dawn.combat_lamp"
SUPPLY="supply.final_dawn.find_knife"


class FinalDawnTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        contracts=Contracts(ROOT/"schemas")
        cls.tables=CatalogValidator(load_catalog(ROOT/"data/manifest.json",contracts),contracts).tables
        cls.profile=read_json(ROOT/"data/profiles/main-baseline.json")

    def seed(self,*,heart=True,moons=True,skills=True,bone=True,robes=True):
        initial={**self.profile["initial_state"]}
        initial["xp_tenths"]={k:10000000 if skills else 0 for k in initial["xp_tenths"]}
        initial["completed_action_ids"]=["quest.the_heart_of_darkness.complete"] if heart else []
        if moons:
            initial["completed_action_ids"].append("quest.perilous_moons.complete")
        initial["inventory"]={**initial["inventory"],"item.coins":5000,
                              "item.beer":1}
        if bone:initial["inventory"]["item.bones"]=1
        if robes:initial["inventory"]["item.heart_emissary_robes"]=1
        initial["counters"]={**initial["counters"],"token.quest_points":50}
        initial["location_id"]="location.final_dawn.start_quest"
        return RouteState(self.tables,self.profile["policies"],initial)

    def apply(self,state,action_id):
        action=self.tables["actions"][action_id]
        initial=state.snapshot();initial["location_id"]=action["start_location_id"]
        state=RouteState(self.tables,self.profile["policies"],initial)
        step={"kind":"action","action_id":action_id,
              "modeled_seconds":action["duration"]["expected_seconds"]}
        if action.get("planned_outcome"):
            step["planned_outcome"]=action["planned_outcome"]
        return state.apply(step,action_id)

    def route(self,state):
        for record in self.tables["actions"].values():
            if record.get("activity_id")!=Q:continue
            if record["id"]==Q+".use_knife_on_potted_fan":state=self.apply(state,SUPPLY)
            state=self.apply(state,record["id"])
        return state

    def test_full_completion_and_exact_non_choice_rewards(self):
        state=self.route(self.seed())
        snap=state.snapshot()
        self.assertEqual(snap["counters"]["token.quest_points"],53)
        for name,amount in (("thieving",550000),("fletching",250000),("runecraft",250000)):
            self.assertEqual(snap["xp_tenths"]["skill."+name],10000000+amount)
        self.assertEqual(snap["inventory"].get("item.arkan_blade"),1)
        self.assertEqual(snap["inventory"].get("item.final_dawn_sun_essence",0),0)
        self.assertEqual(snap["inventory"].get("item.final_dawn_canvas_fragment",0),0)
        self.assertEqual(snap["inventory"].get("item.final_dawn_moon_roots",0),0)
        self.assertIn(Q+".complete",snap["completed_action_ids"])
        with self.assertRaises(DataError): self.apply(state,Q+".complete")

    def test_all_start_requirements_and_quest_dependencies(self):
        first=Q+".start_quest"
        for state in (self.seed(heart=False),self.seed(moons=False),self.seed(skills=False)):
            with self.assertRaises(DataError):self.apply(state,first)
        requirements=self.tables["actions"][first]["requirements"]["requirements"]
        self.assertEqual({r["skill_id"]:r["minimum_level"] for r in requirements if r["kind"]=="skill"},
                         {"skill.thieving":66,"skill.fletching":52,"skill.runecraft":52})
        self.assertTrue(all(not r.get("boostable",False) for r in requirements))

    def test_dog_robe_and_knife_inputs_cannot_be_skipped(self):
        for missing,action in ((self.seed(bone=False),Q+".give_bones_or_meat_to_dog_no_puzzle_wrap"),
                               (self.seed(robes=False),Q+".enter_twilight_temple")):
            with self.assertRaises(DataError):self.apply(missing,action)
        self.assertEqual(self.tables["actions"][Q+".give_bones_or_meat_to_dog_no_puzzle_wrap"]["consumes"],
                         [{"item_id":"item.bones","quantity":1}])
        self.assertEqual(self.tables["actions"][SUPPLY]["effects"],
                         [{"kind":"item","item_id":"item.knife","quantity":1}])

    def test_canvas_beer_and_sun_essence_are_debited(self):
        actions=self.tables["actions"]
        self.assertEqual(actions[Q+".use_canvas_piece_on_picture"]["consumes"],
                         [{"item_id":"item.final_dawn_canvas_fragment","quantity":2}])
        self.assertEqual(actions[Q+".place_steamforged_brew"]["consumes"],
                         [{"item_id":"item.final_dawn_steamforge_brew","quantity":1}])
        six=[a for a in actions.values() if a.get("activity_id")==Q and
             a["id"].startswith(Q+".solve_sun_puzzle") and a["id"].endswith("craft")]
        self.assertEqual(len(six),6)
        self.assertTrue(all(a["consumes"]==[{"item_id":"item.final_dawn_sun_essence","quantity":1}]
                            for a in six))

    def test_combat_and_rune_puzzles_require_confirmed_outcomes(self):
        for slug in ("fight_enforcer","defeat_cultists","defeat_final_cultists","fight_ennius",
                     "defeat_final_boss","solve_sun_puzzle1_step1_craft","place_roots"):
            self.assertIn("planned_outcome",self.tables["actions"][Q+"."+slug])
        with self.assertRaises(DataError):self.apply(self.seed(),Q+".defeat_final_boss")

    def test_combat_lamp_eligibility_and_reward_registry(self):
        reward=self.tables["xp_rewards"][LAMP]
        self.assertEqual(reward["minimum_level"],40)
        self.assertEqual(reward["amount"]["xp_tenths"],550000)
        self.assertTrue(reward["retainable"])
        self.assertEqual(set(reward["eligible_skills"]),{
            "skill.attack","skill.strength","skill.defence","skill.ranged",
            "skill.magic","skill.hitpoints","skill.prayer"})
        package=next(x for x in read_json(ROOT/"data/raw/build-242/reward-registry.json")["entries"]
                     if x["id"]=="review.quest.the_final_dawn.xp_package")
        self.assertEqual(package["status"],"collected")
        self.assertEqual(package["producer_action_id"],Q+".complete")

    def test_graph_is_connected_to_previous_heart_quest(self):
        network=defaultdict(set)
        for edge in self.tables["travel_edges"].values():
            network[edge["from_location_id"]].add(edge["to_location_id"])
        start="location.heart.talk_to_servius"
        goal=self.tables["actions"][Q+".complete"]["start_location_id"]
        seen={start};queue=deque([start])
        while queue:
            for dest in network[queue.popleft()]:
                if dest not in seen: seen.add(dest);queue.append(dest)
        self.assertIn(goal,seen)

    def test_alternative_helper_navigation_is_not_mandatory(self):
        for symbol in ("go_to_temple_from_salvager","go_to_temple_from_gorge",
                       "defeat_final_boss_sidebar","go_to_north_of_final_area_agility_shortcut"):
            self.assertNotIn(Q+"."+symbol,self.tables["actions"])


if __name__=="__main__": unittest.main()
