"""Rag and Bone Man II's 27 unique bones and Enchanted Key's random sites."""

from pathlib import Path
from collections import defaultdict, deque
import unittest

from quest_optimizer.data import Contracts, DataError, load_catalog, read_json
from quest_optimizer.semantics import CatalogValidator
from quest_optimizer.transitions import RouteState


ROOT = Path(__file__).resolve().parents[2]
BONES = "quest.rag_and_bone_man_ii."
KEY = "miniquest.the_enchanted_key."


class BonesAndKeyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        contracts = Contracts(ROOT / "schemas")
        cls.tables = CatalogValidator(load_catalog(ROOT / "data/manifest.json", contracts), contracts).tables
        cls.profile = read_json(ROOT / "data/profiles/main-baseline.json")
        cls.bone_slugs = [
            "wolf", "bat", "rat", "baby_dragon", "ogre", "jogre", "zogre", "mogre",
            "dagannoth", "snake", "zombie", "werewolf", "moss_giant", "fire_giant",
            "ice_giant", "terrorbird", "ghoul", "troll", "seagull", "undead_cow",
            "experiment", "rabbit", "basilisk", "desert_lizard", "cave_goblin",
            "vulture", "jackal"
        ]
        cls.sites = [
            "south_rellekka", "south_ardougne", "west_ardougne", "gnome_stronghold",
            "body_altar", "falador", "mudskipper", "lumbridge_swamp",
            "al_kharid", "varrock_mine", "grand_exchange"
        ]

    def seed(self, **opts):
        initial = {**self.profile["initial_state"]}
        initial["location_id"] = "location.digsite.rag_and_bone_man"
        initial["xp_tenths"] = {skill: 10000000 for skill in initial["xp_tenths"]}
        initial["counters"] = {**initial["counters"], "token.quest_points": 100}
        initial["completed_action_ids"] = [
            "quest.rag_and_bone_man_i.complete", "miniquest.skippy_and_the_mogres.complete",
            "quest.creature_of_fenkenstrain.enter_memorial", "quest.zogre_flesh_eaters.start",
            "quest.horror_from_the_deep.complete", "quest.the_lost_tribe.complete",
            "quest.making_history.complete"
        ]
        initial["inventory"] = {**initial["inventory"], **{
            "item.coins": 15000, "item.pot": 27, "item.logs": 27,
            "item.tinderbox": 1, "item.enchanted_key": 1, "item.spade": 1,
            "item.rag_bone_ii.mirror_shield": 1, "item.rag_bone_ii.ice_cooler": 1,
            "item.fishing_explosive": 1, "item.bronze_axe": 1, "item.dusty_key": 1
        }}
        for key, val in opts.items():
            initial[key] = val
        return RouteState(self.tables, self.profile["policies"], initial)

    def step(self, state, action_id):
        record = self.tables["actions"][action_id]
        snap = state.snapshot()
        snap["location_id"] = record["start_location_id"]
        state = RouteState(self.tables, self.profile["policies"], snap)
        step = {"kind": "action", "action_id": action_id,
                "modeled_seconds": record["duration"]["expected_seconds"]}
        if "planned_outcome" in record:
            step["planned_outcome"] = record["planned_outcome"]
        return state.apply(step, action_id)

    def test_27_distinct_bones_clean_and_reward_once(self):
        state = self.step(self.seed(), BONES+"start")
        state = self.step(state, BONES+"buy_vinegar")
        with self.assertRaises(DataError):
            self.step(state, BONES+"complete")
        for slug in reversed(self.bone_slugs):
            state = self.step(state, BONES+"collect_"+slug)
            state = self.step(state, BONES+"polish_"+slug)
        snap = state.snapshot()
        self.assertEqual(snap["counters"]["token.rag_bone_ii.cleaned"], 27)
        self.assertEqual(snap["inventory"].get("item.logs", 0), 0)
        self.assertEqual(snap["inventory"].get("item.rag_vinegar", 0), 0)
        self.assertEqual(snap["inventory"]["item.pot"], 27)
        with self.assertRaises(DataError):
            self.step(state, BONES+"polish_jackal")
        state = self.step(state, BONES+"complete")
        snap = state.snapshot()
        self.assertEqual(snap["counters"]["token.quest_points"], 101)
        self.assertEqual(snap["xp_tenths"]["skill.prayer"], 10050000)
        self.assertEqual(snap["inventory"]["item.rag_bone_ii.bonesack"], 1)
        self.assertEqual(snap["inventory"]["item.rag_bone_ii.ram_skull_helm"], 1)
        with self.assertRaises(DataError):
            self.step(state, BONES+"complete")

    def test_bone_quest_prerequisite_and_specific_slayer_gates(self):
        snap = self.seed().snapshot()
        snap["completed_action_ids"].remove("quest.rag_and_bone_man_i.complete")
        with self.assertRaises(DataError):
            self.step(self.seed(**snap), BONES+"start")
        state = self.step(self.seed(), BONES+"start")
        snap = state.snapshot()
        snap["xp_tenths"]["skill.slayer"] = 0
        with self.assertRaises(DataError):
            self.step(self.seed(**snap), BONES+"collect_basilisk")
        with self.assertRaises(DataError):
            self.step(self.seed(**snap), BONES+"collect_mogre")
        self.step(self.seed(**snap), BONES+"collect_bat")

    def test_key_first_site_then_unordered_remaining_and_fixed_loot(self):
        state = self.seed()
        with self.assertRaises(DataError):
            self.step(state, KEY+"dig_falador")
        state = self.step(state, KEY+"dig_south_rellekka")
        for slug in reversed(self.sites[1:]):
            state = self.step(state, KEY+"dig_"+slug)
        snap = state.snapshot()
        expected = {"item.pure_essence": 263, "item.iron_ore": 60,
                    "item.mithril_ore": 30, "item.law_rune": 30,
                    "item.rag_bone_ii.bonesack": 0,
                    "item.saradomin_mjolnir": 1, "item.guthix_mjolnir": 1,
                    "item.zamorak_mjolnir": 1}
        for id, count in expected.items():
            self.assertEqual(snap["inventory"].get(id, 0), count, id)
        self.assertEqual(snap["counters"]["token.quest_points"], 100)
        self.assertTrue(all(KEY+"dig_"+slug in snap["completed_action_ids"] for slug in self.sites))
        with self.assertRaises(DataError):
            self.step(state, KEY+"dig_south_rellekka")

    def test_key_requires_making_history_and_a_spade(self):
        snap = self.seed().snapshot()
        snap["completed_action_ids"].remove("quest.making_history.complete")
        with self.assertRaises(DataError):
            self.step(self.seed(**snap), KEY+"dig_south_rellekka")

    def test_bat_trip_uses_real_travel_transitions_and_returns(self):
        state = self.step(self.seed(), BONES+"start")
        for edge_id in ("travel.bones_key.bat.out", "travel.bones_key.bat.back"):
            edge = self.tables["travel_edges"][edge_id]
            if edge_id.endswith(".back"):
                state = self.step(state, BONES+"collect_bat")
            state = state.apply({"kind": "travel", "edge_id": edge_id,
                                 "modeled_seconds": edge["duration"]["expected_seconds"]}, edge_id)
        snap = state.snapshot()
        self.assertEqual(snap["location_id"], "location.digsite.rag_and_bone_man")
        self.assertEqual(snap["inventory"]["item.rag_bat_bone"], 1)
        snap = self.seed().snapshot()
        snap["inventory"].pop("item.spade")
        with self.assertRaises(DataError):
            self.step(self.seed(**snap), KEY+"dig_south_rellekka")

    def test_all_new_waypoints_have_bidirectional_connections(self):
        adjacency = defaultdict(set)
        for edge in self.tables["travel_edges"].values():
            adjacency[edge["from_location_id"]].add(edge["to_location_id"])
        for id, location in self.tables["locations"].items():
            if not id.startswith("location.bones_key."):
                continue
            self.assertIn(id, adjacency, id)
            self.assertTrue(any(id in adjacency[neighbor] for neighbor in adjacency[id]), id)
        reached = {"location.digsite.rag_and_bone_man"}
        queue = deque(reached)
        while queue:
            for neighbor in adjacency[queue.popleft()]:
                if neighbor not in reached:
                    reached.add(neighbor)
                    queue.append(neighbor)
        for action in self.tables["actions"].values():
            if action.get("activity_id") in {"quest.rag_and_bone_man_ii", "miniquest.the_enchanted_key"}:
                self.assertIn(action["start_location_id"], reached, action["id"])


if __name__ == "__main__":
    unittest.main()
