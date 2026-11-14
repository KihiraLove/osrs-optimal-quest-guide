"""Focused staged replay, start gating, and reward tests for Legends' Quest."""

from collections import defaultdict, deque
from pathlib import Path
import unittest

from quest_optimizer.data import Contracts, DataError, load_catalog, read_json
from quest_optimizer.semantics import CatalogValidator
from quest_optimizer.transitions import RouteState


ROOT = Path(__file__).resolve().parents[2]
QUEST = "quest.legends_quest"


class LegendsQuestTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        contracts = Contracts(ROOT / "schemas")
        cls.tables = CatalogValidator(load_catalog(ROOT / "data/manifest.json", contracts), contracts).tables
        cls.profile = read_json(ROOT / "data/profiles/main-baseline.json")
        cls.actions = read_json(ROOT / "data/catalog/legends-quest/actions.json")
        cls.travel = defaultdict(list)
        for edge in cls.tables["travel_edges"].values():
            cls.travel[edge["from_location_id"]].append(edge)

    def seeded(self, *, quest_points=107, bridges=True, skills=True, supplies=True):
        state = read_json(ROOT / "data/profiles/main-baseline.json")["initial_state"]
        state["location_id"] = "location.legends.radimus"
        state["completed_action_ids"] = ["quest.family_crest.complete", "quest.waterfall_quest.complete"]
        state["counters"]["token.quest_points"] = quest_points
        state["flags"] = {"flag.rfd.heroes_quest_complete": bridges,
                          "flag.rfd.shilo_village_complete": bridges,
                          "flag.rfd.underground_pass_complete": bridges}
        if skills:
            for skill, level in (("agility", 50), ("crafting", 50), ("herblore", 45),
                                 ("magic", 56), ("mining", 52), ("prayer", 42),
                                 ("smithing", 50), ("strength", 50), ("thieving", 50),
                                 ("woodcutting", 50)):
                state["xp_tenths"]["skill." + skill] = self.tables["skills"]["skill." + skill]["xp_thresholds_tenths"][level-1]
        if supplies:
            state["inventory"] = {"item.papyrus": 3, "item.charcoal": 1, "item.rfd.machete": 1,
                                  "item.coins": 300,
                                  "item.legends.rune_axe": 1, "item.lockpick": 1, "item.rune_pickaxe": 1,
                                  "item.legends.soul_rune": 1, "item.mind_rune": 1, "item.earth_rune": 1,
                                  "item.law_rune": 2, "item.sapphire": 1, "item.emerald": 1,
                                  "item.ruby": 1, "item.diamond": 1, "item.opal": 1,
                                  "item.legends.jade": 1, "item.legends.red_topaz": 1,
                                  "item.gold_bar": 2, "item.hammer": 1, "item.vial_of_water": 1,
                                  "item.legends.unpowered_orb": 1, "item.rope": 1}
        return RouteState(self.tables, self.profile["policies"], state)

    @staticmethod
    def apply(state, record, *, travel=False):
        step = {"kind": "travel" if travel else "action",
                "edge_id" if travel else "action_id": record["id"],
                "modeled_seconds": record["duration"]["expected_seconds"]}
        if "planned_outcome" in record:
            step["planned_outcome"] = record["planned_outcome"]
        return state.apply(step)

    def at(self, state, location):
        snapshot = state.snapshot()
        snapshot["location_id"] = location
        return RouteState(self.tables, self.profile["policies"], snapshot)

    def do(self, state, suffix):
        record = self.tables["actions"][QUEST + "." + suffix]
        return self.apply(self.at(state, record["start_location_id"]), record)

    def arrive(self, state, target):
        if state.location == target:
            return state
        todo = deque([state])
        seen = {state.location}
        while todo:
            current = todo.popleft()
            for edge in self.travel[current.location]:
                if edge["to_location_id"] in seen:
                    continue
                try:
                    progressed = self.apply(current, edge, travel=True)
                except DataError:
                    continue
                if progressed.location == target:
                    return progressed
                seen.add(progressed.location)
                todo.append(progressed)
        self.fail(f"No viable route from {state.location} to {target} (reachable: {len(seen)})")

    def full_route(self, state):
        for record in self.actions:
            state = self.apply(self.arrive(state, record["start_location_id"]), record)
        return state

    def test_rewards_and_consumed_quest_items(self):
        start = self.seeded()
        done = self.full_route(start)
        snap = done.snapshot()
        self.assertEqual(snap["counters"]["token.quest_points"], 111)
        self.assertTrue(snap["flags"]["unlock.legends_guild"])
        self.assertTrue(snap["flags"]["flag.rfd.legends_started"])
        self.assertTrue(snap["flags"]["flag.quest.legends_quest.complete"])
        self.assertIn("reward.legends_quest.lamp", str(snap))
        self.assertNotIn("item.gold_bar", snap["inventory"])
        self.assertNotIn("item.papyrus", snap["inventory"])
        self.assertNotIn("item.legends.yommi_seeds", snap["inventory"])
        with self.assertRaises(DataError):
            self.do(done, "complete")

    def test_prerequisite_gates_and_started_flag(self):
        for state in (self.seeded(quest_points=106), self.seeded(bridges=False)):
            with self.assertRaises(DataError):
                self.do(state, "start")
        start = self.do(self.seeded(skills=False), "start")
        self.assertTrue(start.snapshot()["flags"]["flag.rfd.legends_started"])
        self.assertNotIn("quest.legends_quest.complete", start.snapshot()["completed_action_ids"])
        with self.assertRaises(DataError):
            self.do(start, "investigate_fire")

    def test_cave_and_viyeldi_entry_gates(self):
        state = self.seeded()
        cave_edge = self.tables["travel_edges"]["travel.other.legends.cave_entrance.to.fire_wall"]
        inner = self.apply(self.at(state, cave_edge["from_location_id"]), cave_edge, travel=True)
        self.assertEqual(inner.location, "location.legends.fire_wall")
        winch_edge = self.tables["travel_edges"]["travel.other.legends.winch.to.crystal_furnace"]
        with self.assertRaises(DataError):
            self.apply(self.at(state, winch_edge["from_location_id"]), winch_edge, travel=True)

    def test_reward_definition_four_reclaimable_lamps(self):
        reward = self.tables["xp_rewards"]["reward.legends_quest.lamp"]
        self.assertEqual(reward["amount"]["xp_tenths"], 300000)
        self.assertEqual(reward["selection_count"], 1)
        self.assertEqual(len(reward["eligible_skills"]), 12)
        self.assertTrue(reward["retainable"])
        self.assertFalse(reward["distinct_skills"])


if __name__ == "__main__":
    unittest.main()
