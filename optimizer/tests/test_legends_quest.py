"""Focused Legends' Quest long-path replay and Radimus reward gates."""
from collections import deque
from copy import deepcopy
from pathlib import Path
import unittest

from quest_optimizer.data import Contracts, DataError, load_catalog, read_json
from quest_optimizer.semantics import CatalogValidator
from quest_optimizer.transitions import RouteState


ROOT = Path(__file__).resolve().parents[2]
PREFIX = "quest.legends_quest."
PREVIOUS = (
    "quest.family_crest.complete",
    "quest.heroes_quest.complete",
    "quest.shilo_village.complete",
    "quest.underground_pass.complete",
    "quest.waterfall_quest.complete",
)


class LegendsQuestTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        contracts = Contracts(ROOT / "schemas")
        catalog = load_catalog(ROOT / "data/manifest.json", contracts)
        cls.tables = CatalogValidator(catalog, contracts).tables
        cls.profile = read_json(ROOT / "data/profiles/main-baseline.json")
        cls.connections = {}
        for eid, edge in cls.tables["travel_edges"].items():
            cls.connections.setdefault(edge["from_location_id"], []).append(
                (eid, edge["to_location_id"])
            )
        for edges in cls.connections.values():
            edges.sort(key=lambda item: (not item[0].startswith("travel.legends."), item))

    def seed(self, location="location.varrock.grand_exchange", qp=107):
        state = deepcopy(self.profile["initial_state"])
        state["location_id"] = location
        state["xp_tenths"] = {skill: 10_000_000 for skill in state["xp_tenths"]}
        state["completed_action_ids"] = list(PREVIOUS)
        state["counters"]["token.quest_points"] = qp
        state["inventory"]["item.coins"] = 60_000
        return RouteState(self.tables, self.profile["policies"], state)

    def step(self, state, record_id):
        is_edge = record_id.startswith("travel.")
        record = self.tables["travel_edges" if is_edge else "actions"][record_id]
        step = {
            "kind": "travel" if is_edge else "action",
            "edge_id" if is_edge else "action_id": record_id,
            "modeled_seconds": record["duration"]["expected_seconds"],
        }
        if record.get("planned_outcome"):
            step["planned_outcome"] = record["planned_outcome"]
        return state.apply(step, record_id)

    def move(self, state, target):
        if state.location == target:
            return state
        queue = deque([state])
        visited = {state.location}
        while queue:
            path_state = queue.popleft()
            for eid, location in self.connections.get(path_state.location, []):
                if location in visited:
                    continue
                try:
                    next_state = self.step(path_state, eid)
                except DataError:
                    continue
                if location == target:
                    return next_state
                visited.add(location)
                queue.append(next_state)
        self.fail(f"Travel graph has no usable route from {state.location} to {target}")

    def act(self, state, name):
        aid = name if name.startswith("supply.") else PREFIX + name
        state = self.move(state, self.tables["actions"][aid]["start_location_id"])
        return self.step(state, aid)

    def test_full_route_and_single_four_pick_reward(self):
        state = self.seed()
        path = (
            "supply.legends_quest.buy_kit",
            "start", "map_west", "map_middle", "map_east", "get_bullroarer",
            "meet_gujuo", "inspect_firewall", "receive_bowl_sketch",
            "smith_gold_bowl", "bless_bowl", "fill_pure_water",
            "pass_cave_gates", "solve_rune_gem_puzzle", "free_ungadulu",
            "refill_pure_water", "germinate_yommi",
            "supply.legends_quest.collect_ardrigal",
            "supply.legends_quest.collect_snake_weed",
            "make_bravery_potion", "descend_to_source",
            "defeat_undead_guardians", "forge_heart", "open_barrier",
            "meet_echned", "get_holy_force", "return_to_source",
            "restore_source", "fill_restored_water", "carve_yommi_totem",
            "defeat_final_demon", "return_with_totem", "choose_xp",
        )
        for name in path:
            with self.subTest(stage=name):
                state = self.act(state, name)

        reward_id = "reward.legends_quest.radimus_xp_choices"
        instance_id = reward_id + ".instance.1"
        self.assertEqual(state.snapshot()["held_rewards"][0]["remaining_picks"], 4)
        with self.assertRaises(DataError):
            self.step(state, PREFIX + "complete")
        before = state.snapshot()["xp_tenths"]["skill.agility"]
        for _ in range(4):
            state = state.apply({
                "kind": "reward_use", "instance_id": instance_id,
                "reward_id": reward_id, "skill_id": "skill.agility",
                "gain_xp_tenths": 300000,
                "overrides_observed_skill_restriction": False,
            }, "radimus_pick")
        self.assertEqual(state.snapshot()["xp_tenths"]["skill.agility"] - before, 1200000)
        self.assertEqual(state.snapshot()["held_rewards"], [])
        state = self.act(state, "complete")
        snap = state.snapshot()
        self.assertEqual(snap["counters"]["token.quest_points"], 111)
        self.assertTrue(snap["flags"]["unlock.legends_guild"])
        self.assertTrue(snap["flags"]["flag.quest.legends_quest.complete"])
        self.assertEqual(snap["inventory"].get("item.unpowered_orb", 0), 0)
        self.assertEqual(snap["inventory"].get("item.water_rune", 0), 6)
        self.assertEqual(snap["inventory"].get("item.cosmic_rune", 0), 0)
        with self.assertRaises(DataError):
            self.step(state, PREFIX + "choose_xp")
        with self.assertRaises(DataError):
            self.step(state, PREFIX + "complete")

    def test_start_requires_107_qp(self):
        state = self.seed(location="location.legends.radimus", qp=106)
        with self.assertRaises(DataError):
            self.step(state, PREFIX + "start")

    def test_cave_and_reward_cannot_be_skipped(self):
        state = self.seed(location="location.legends.guild_hall")
        with self.assertRaises(DataError):
            self.step(state, PREFIX + "choose_xp")
        state = self.seed(location="location.legends.winch")
        with self.assertRaises(DataError):
            self.step(state, PREFIX + "descend_to_source")


if __name__ == "__main__":
    unittest.main()
