"""Focused Recipe for Disaster: Freeing Sir Amik Varze route replay."""
from collections import deque
from copy import deepcopy
from pathlib import Path
import unittest

from quest_optimizer.data import Contracts, DataError, load_catalog, read_json
from quest_optimizer.semantics import CatalogValidator
from quest_optimizer.transitions import RouteState


ROOT = Path(__file__).resolve().parents[2]
PREFIX = "rfd.freeing_sir_amik_varze."
PREREQUISITES = (
    "rfd.another_cooks_quest.complete",
    "quest.family_crest.complete",
    "quest.heroes_quest.complete",
    "quest.shilo_village.complete",
    "quest.underground_pass.complete",
    "quest.waterfall_quest.complete",
    "quest.lost_city.complete",
    "quest.lost_city.descend_entrana",
    "quest.legends_quest.start",
)


class SirAmikVarzeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        contracts = Contracts(ROOT / "schemas")
        catalog = load_catalog(ROOT / "data/manifest.json", contracts)
        cls.tables = CatalogValidator(catalog, contracts).tables
        cls.profile = read_json(ROOT / "data/profiles/main-baseline.json")
        cls.connections = {}
        for edge_id, edge in cls.tables["travel_edges"].items():
            cls.connections.setdefault(edge["from_location_id"], []).append(
                (edge_id, edge["to_location_id"])
            )
        for edges in cls.connections.values():
            edges.sort(key=lambda pair: (not pair[0].startswith("travel.rfd_amik."), pair))

    def seed(self, *, legends_started=True, lost_city=True, ice_gloves=True):
        state = deepcopy(self.profile["initial_state"])
        state["location_id"] = "location.varrock.grand_exchange"
        state["xp_tenths"] = {skill: 10_000_000 for skill in state["xp_tenths"]}
        completed = set(PREREQUISITES)
        if not legends_started:
            completed.remove("quest.legends_quest.start")
        if not lost_city:
            completed.remove("quest.lost_city.complete")
        state["completed_action_ids"] = sorted(completed)
        state["counters"]["token.quest_points"] = 107
        state["inventory"].update({
            "item.coins": 50000,
            "item.machete": 1,
            "item.dramen_staff": 1,
            "item.anti_dragon_shield": 1,
            "item.lumbridge_teleport_tablet": 3,
            "item.air_rune": 120,
            "item.fire_rune": 150,
            "item.mind_rune": 100,
        })
        if ice_gloves:
            state["inventory"]["item.ice_gloves"] = 1
        state["flags"]["unlock.kharazi_jungle"] = legends_started
        state["flags"]["flag.quest.lost_city.complete"] = lost_city
        return RouteState(self.tables, self.profile["policies"], state)

    def step(self, state, record_id):
        is_edge = record_id.startswith("travel.")
        record = self.tables["travel_edges" if is_edge else "actions"][record_id]
        step = {
            "kind": "travel" if is_edge else "action",
            "edge_id" if is_edge else "action_id": record_id,
            "modeled_seconds": record["duration"]["expected_seconds"],
        }
        if "planned_outcome" in record:
            step["planned_outcome"] = record["planned_outcome"]
        return state.apply(step, record_id)

    def move(self, state, target):
        if state.location == target:
            return state
        queue = deque([(state, [])])
        visited = {state.location}
        while queue:
            path_state, path = queue.popleft()
            for edge_id, to_location in self.connections.get(path_state.location, []):
                if to_location in visited:
                    continue
                try:
                    next_state = self.step(path_state, edge_id)
                except DataError:
                    continue
                if to_location == target:
                    return next_state
                visited.add(to_location)
                queue.append((next_state, path + [edge_id]))
        self.fail(f"No valid travel from {state.location} to {target}")

    def act(self, state, name):
        action_id = name if name.startswith("supply.") else PREFIX + name
        state = self.move(state, self.tables["actions"][action_id]["start_location_id"])
        return self.step(state, action_id)

    def test_full_rescue_rewards_and_consumption(self):
        state = self.seed()
        before_cooking = state.snapshot()["xp_tenths"]["skill.cooking"]
        before_hp = state.snapshot()["xp_tenths"]["skill.hitpoints"]
        path = (
            "supply.rfd_amik.buy_ingredients",
            "inspect", "ask_cook", "make_milky_mix", "add_cornflour",
            "ask_wise_old_man", "pick_vanilla", "add_vanilla",
            "supply.bank.deposit_entrana_gear",
            "supply.rfd_amik.obtain_axe", "supply.rfd_amik.cut_branch",
            "make_cinnamon", "supply.bank.withdraw_entrana_gear",
            "enter_lair", "defeat_evil_chicken",
            "defeat_black_dragon", "add_egg_and_cinnamon", "flambe", "complete",
        )
        for name in path:
            with self.subTest(action=name):
                state = self.act(state, name)
        snapshot = state.snapshot()
        self.assertIn(PREFIX + "complete", snapshot["completed_action_ids"])
        self.assertEqual(snapshot["xp_tenths"]["skill.cooking"] - before_cooking, 40000)
        self.assertEqual(snapshot["xp_tenths"]["skill.hitpoints"] - before_hp, 40000)
        self.assertEqual(snapshot["counters"]["token.quest_points"], 108)
        self.assertTrue(snapshot["flags"]["unlock.rfd_amik.evil_chicken_lair"])
        self.assertEqual(snapshot["inventory"].get("item.rfd_amik.brulee_supreme", 0), 0)
        self.assertEqual(snapshot["inventory"].get("item.dramen_staff", 0), 1)
        self.assertEqual(snapshot["inventory"].get("item.raw_chicken", 0), 0)
        with self.assertRaises(DataError):
            self.step(state, PREFIX + "complete")

    def test_start_and_safe_flambé_gates(self):
        state = self.seed(legends_started=False)
        state = self.move(state, "location.rfd_amik.sir_amik")
        with self.assertRaises(DataError):
            self.step(state, PREFIX + "inspect")
        state = self.seed(lost_city=False)
        state = self.act(state, "supply.rfd_amik.buy_ingredients")
        with self.assertRaises(AssertionError):
            self.move(state, "location.rfd_amik.evil_chicken_shrine")

        state = self.seed(ice_gloves=False)
        state = self.move(state, "location.rfd_amik.evil_chicken_shrine")
        state = state.snapshot()
        state["completed_action_ids"] += [PREFIX + "add_egg_and_cinnamon"]
        state["inventory"]["item.rfd_amik.unflambeed_brulee"] = 1
        state["inventory"]["item.rfd_amik.dragon_token"] = 1
        state = RouteState(self.tables, self.profile["policies"], state)
        with self.assertRaises(DataError):
            self.step(state, PREFIX + "flambe")


if __name__ == "__main__":
    unittest.main()
