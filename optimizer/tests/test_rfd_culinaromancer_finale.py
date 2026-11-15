"""Six-stage Recipe for Disaster finale, supplies, prerequisites and XP lamp."""
from collections import deque
from copy import deepcopy
from pathlib import Path
import unittest

from quest_optimizer.data import Contracts, DataError, load_catalog, read_json
from quest_optimizer.semantics import CatalogValidator
from quest_optimizer.transitions import RouteState


ROOT = Path(__file__).resolve().parents[2]
PREFIX = "rfd.defeating_the_culinaromancer."
BOSSES = ("agrith", "flambeed", "karamel", "dessourt", "gelatinnoth_mother", "culinaromancer")
PREREQUISITES = (
    "rfd.another_cooks_quest.complete", "rfd.freeing_the_mountain_dwarf.complete",
    "rfd.freeing_the_goblin_generals.complete", "rfd.freeing_pirate_pete.complete",
    "rfd.freeing_the_lumbridge_guide.complete", "rfd.freeing_evil_dave.complete",
    "rfd.freeing_skrach_uglogwee.complete", "rfd.freeing_king_awowogei.complete",
    "quest.horror_from_the_deep.complete",
)
UPSTREAM_FLAGS = (
    "flag.rfd.sir_amik_varze_catalog_complete",
    "flag.quest.desert_treasure_i_catalog_complete",
)


class CulinaromancerFinaleTests(unittest.TestCase):
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
            edges.sort(key=lambda entry: (not entry[0].startswith("travel.rfd.finale."), entry))

    def seed(self, *, location="location.varrock.grand_exchange", qp=175,
             flags=UPSTREAM_FLAGS):
        initial = deepcopy(self.profile["initial_state"])
        initial["location_id"] = location
        initial["xp_tenths"] = {skill: 10_000_000 for skill in initial["xp_tenths"]}
        initial["completed_action_ids"] = list(PREREQUISITES)
        initial["counters"]["token.quest_points"] = qp
        initial["flags"].update({flag: True for flag in flags})
        initial["inventory"]["item.coins"] = 40_000
        # Ice gloves have an existing upstream producer in Heroes' Quest.
        initial["inventory"]["item.ice_gloves"] = 1
        return RouteState(self.tables, self.profile["policies"], initial)

    def step(self, state, record_id):
        travel = record_id.startswith("travel.")
        record = self.tables["travel_edges" if travel else "actions"][record_id]
        step = {
            "kind": "travel" if travel else "action",
            "edge_id" if travel else "action_id": record_id,
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
            current = queue.popleft()
            for eid, destination in self.connections.get(current.location, ()):
                if destination in visited:
                    continue
                try:
                    next_state = self.step(current, eid)
                except DataError:
                    continue
                if destination == target:
                    return next_state
                visited.add(destination)
                queue.append(next_state)
        self.fail(f"No legal path from {state.location} to {target}")

    def test_full_six_fight_route_parent_and_lamp(self):
        state = self.seed()
        state = self.step(state, "supply.rfd_finale.buy_restores")
        state = self.move(state, "location.rfd.finale_portal")
        state = self.step(state, PREFIX + "prepare")
        for boss in BOSSES:
            with self.subTest(boss=boss):
                state = self.step(state, "travel.rfd.finale.enter_" + boss)
                action = "complete" if boss == "culinaromancer" else "defeat_" + boss
                state = self.step(state, PREFIX + action)
                self.assertEqual(state.location, "location.rfd.finale_portal")
                self.assertTrue(state.snapshot()["flags"]["flag.rfd.finale." + boss + "_defeated"])
                with self.assertRaises(DataError):
                    self.step(state, "travel.rfd.finale.enter_" + boss)

        snap = state.snapshot()
        self.assertEqual(snap["counters"]["token.quest_points"], 176)
        self.assertTrue(snap["flags"]["flag.rfd.finale_complete"])
        self.assertTrue(snap["flags"]["unlock.rfd_barrows_gloves_purchase"])
        self.assertEqual(snap["inventory"]["item.super_restore_4"], 1)
        self.assertEqual(snap["inventory"]["item.ice_gloves"], 1)
        reward_id = "reward.rfd.culinaromancer_antique_lamp"
        instance_id = reward_id + ".instance.1"
        self.assertEqual(snap["held_rewards"], [
            {"instance_id": instance_id, "reward_id": reward_id, "remaining_picks": 1}
        ])

        state = self.move(state, "location.lumbridge_castle.cook")
        state = self.step(state, "quest.recipe_for_disaster.complete")
        self.assertEqual(state.snapshot()["counters"]["token.quest_points"], 176)
        before = state.snapshot()["xp_tenths"]["skill.herblore"]
        state = state.apply({
            "kind": "reward_use", "instance_id": instance_id,
            "reward_id": reward_id, "skill_id": "skill.herblore",
            "gain_xp_tenths": 200000,
            "overrides_observed_skill_restriction": False,
        }, "use_antique_lamp")
        self.assertEqual(state.snapshot()["xp_tenths"]["skill.herblore"] - before, 200000)
        self.assertEqual(state.snapshot()["held_rewards"], [])
        with self.assertRaises(DataError):
            self.step(state, "quest.recipe_for_disaster.complete")
        with self.assertRaises(DataError):
            state.apply({
                "kind": "reward_use", "instance_id": instance_id,
                "reward_id": reward_id, "skill_id": "skill.herblore",
                "gain_xp_tenths": 200000,
                "overrides_observed_skill_restriction": False,
            }, "double_spend")

    def test_175_points_and_two_upstream_gates(self):
        for qp, flags in ((174, UPSTREAM_FLAGS), (175, UPSTREAM_FLAGS[:1]),
                          (175, UPSTREAM_FLAGS[1:])):
            with self.subTest(qp=qp, flags=flags):
                state = self.seed(location="location.rfd.finale_portal", qp=qp, flags=flags)
                with self.assertRaises(DataError):
                    self.step(state, PREFIX + "prepare")

    def test_preparation_and_flame_glove_requirements(self):
        state = self.seed(location="location.rfd.finale_portal")
        with self.assertRaises(DataError):
            self.step(state, "travel.rfd.finale.enter_agrith")
        snapshot = state.snapshot()
        snapshot["location_id"] = "location.rfd.finale_arena"
        snapshot["completed_action_ids"].extend([PREFIX + "prepare", PREFIX + "defeat_agrith"])
        snapshot["inventory"].pop("item.ice_gloves")
        state = RouteState(self.tables, self.profile["policies"], snapshot)
        with self.assertRaises(DataError):
            self.step(state, PREFIX + "defeat_flambeed")

    def test_lamp_level_restriction(self):
        state = self.seed(location="location.lumbridge_castle.cook")
        snapshot = state.snapshot()
        snapshot["xp_tenths"]["skill.agility"] = 0
        reward = "reward.rfd.culinaromancer_antique_lamp"
        snapshot["held_rewards"] = [{
            "instance_id": reward + ".instance.1", "reward_id": reward,
            "remaining_picks": 1,
        }]
        state = RouteState(self.tables, self.profile["policies"], snapshot)
        with self.assertRaises(DataError):
            state.apply({
                "kind": "reward_use", "instance_id": reward + ".instance.1",
                "reward_id": reward, "skill_id": "skill.agility",
                "gain_xp_tenths": 200000,
                "overrides_observed_skill_restriction": False,
            }, "under_level_50")


if __name__ == "__main__":
    unittest.main()
