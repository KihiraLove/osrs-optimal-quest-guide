"""Fallen From Grace: connected Sailing, local supplies, fight and timed unlocks."""

from collections import defaultdict, deque
from pathlib import Path
import unittest

from quest_optimizer.data import Contracts, DataError, load_catalog, read_json
from quest_optimizer.semantics import CatalogValidator
from quest_optimizer.transitions import RouteState


ROOT = Path(__file__).resolve().parents[2]
PREFIX = "quest.fallen_from_grace"


class FallenFromGraceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        contracts = Contracts(ROOT / "schemas")
        cls.tables = CatalogValidator(load_catalog(ROOT / "data/manifest.json", contracts), contracts).tables
        cls.profile = read_json(ROOT / "data/profiles/main-baseline.json")
        cls.actions = read_json(ROOT / "data/catalog/fallen-from-grace/actions.json")
        cls.edges = read_json(ROOT / "data/catalog/fallen-from-grace/travel_edges.json")
        cls.adj = defaultdict(list)
        for edge in cls.edges:
            cls.adj[edge["from_location_id"]].append(edge)

    def seeded(self, *, overrides=None, pandemonium=True, boat=True):
        raw = read_json(ROOT / "data/profiles/main-baseline.json")["initial_state"]
        raw["location_id"] = "location.port_sarim.charter_dock"
        raw["inventory"] = {}
        levels = {"sailing": 62, "crafting": 60, "runecraft": 47, "mining": 53}
        levels.update(overrides or {})
        for skill, level in levels.items():
            raw["xp_tenths"][f"skill.{skill}"] = self.tables["skills"][f"skill.{skill}"]["xp_thresholds_tenths"][level - 1]
        if pandemonium:
            raw["flags"]["flag.quest.pandemonium.complete"] = True
        if boat:
            raw["flags"]["unlock.pandemonium.raft"] = True
            raw["flags"]["unlock.pandemonium.captains_log"] = True
        return RouteState(self.tables, self.profile["policies"], raw)

    @staticmethod
    def apply(state, record, *, travel=False):
        instruction = {
            "kind": "travel" if travel else "action",
            "edge_id" if travel else "action_id": record["id"],
            "modeled_seconds": record["duration"]["expected_seconds"],
        }
        if record.get("planned_outcome"):
            instruction["planned_outcome"] = record["planned_outcome"]
        return state.apply(instruction)

    def arrive(self, state, target):
        if state.location == target:
            return state
        queue = deque([state])
        visited = {state.location}
        while queue:
            current = queue.popleft()
            for edge in self.adj[current.location]:
                nxt = edge["to_location_id"]
                if nxt in visited:
                    continue
                try:
                    advanced = self.apply(current, edge, travel=True)
                except DataError:
                    continue
                if nxt == target:
                    return advanced
                visited.add(nxt)
                queue.append(advanced)
        self.fail(f"No connected travel from {state.location} to {target}; visited {len(visited)} locations")

    def step(self, state, slug):
        action = self.tables["actions"][f"{PREFIX}.{slug}"]
        return self.apply(self.arrive(state, action["start_location_id"]), action)

    def stage_at(self, state, slug):
        action = self.tables["actions"][f"{PREFIX}.{slug}"]
        raw = state.snapshot()
        raw["location_id"] = action["start_location_id"]
        return self.apply(RouteState(self.tables, self.profile["policies"], raw), action)

    def replay(self, *, shortcut=False):
        state = self.seeded(overrides={"agility": 54} if shortcut else None)
        checkpoints = {}
        for action in self.actions:
            slug = action["id"][len(PREFIX) + 1:]
            if slug in ("take_hammer", "clear_shortcut") and not (shortcut and slug == "clear_shortcut"):
                continue
            state = self.step(state, slug)
            if slug in ("report_to_cormac", "unlock_mortimer", "repair_golem",
                        "clear_shortcut", "defeat_mad_angel", "complete"):
                checkpoints[slug] = state.snapshot()
        return state, checkpoints

    def test_connected_route_reaches_completion_and_rewards_once(self):
        start = self.seeded()
        state, points = self.replay()
        done = state.snapshot()
        self.assertEqual(done["counters"]["token.quest_points"] - start.counters["token.quest_points"], 2)
        self.assertEqual(done["xp_tenths"]["skill.crafting"] - start.xp["skill.crafting"], 100000)
        self.assertEqual(done["xp_tenths"]["skill.sailing"] - start.xp["skill.sailing"], 125000)
        self.assertEqual(done["xp_tenths"]["skill.mining"] - start.xp["skill.mining"], 50000)
        self.assertEqual(done["xp_tenths"]["skill.runecraft"] - start.xp["skill.runecraft"], 50000)
        self.assertTrue(points["report_to_cormac"]["flags"]["unlock.grace.cavern"])
        self.assertTrue(points["unlock_mortimer"]["flags"]["unlock.grace.mortimer"])
        self.assertNotIn("flag.quest.fallen_from_grace.complete", points["unlock_mortimer"]["flags"])
        self.assertTrue(points["repair_golem"]["flags"]["unlock.grace.golem_door"])
        self.assertTrue(points["defeat_mad_angel"]["flags"]["flag.grace.angel_defeated"])
        self.assertEqual(points["defeat_mad_angel"]["inventory"]["item.grace.sunstone_crystal"], 1)
        self.assertNotIn("unlock.grace.mad_angel_repeat", points["defeat_mad_angel"]["flags"])
        for key in ("flag.quest.fallen_from_grace.complete", "unlock.grace.mad_angel_repeat",
                    "unlock.grace.golem_crafting", "unlock.grace.wyrmscraig_teleports"):
            self.assertTrue(done["flags"][key])
        self.assertEqual(done["inventory"]["item.grace.dull_core"], 1)
        self.assertNotIn("item.grace.sunstone_core", done["inventory"])
        self.assertNotIn("item.grace.cathedral_key", done["inventory"])
        with self.assertRaises(DataError):
            self.stage_at(state, "complete")

    def test_optional_agility_shortcut_not_required(self):
        normal, points = self.replay()
        self.assertNotIn("unlock.grace.shortcut", normal.flags)
        faster, points2 = self.replay(shortcut=True)
        self.assertTrue(points2["clear_shortcut"]["flags"]["unlock.grace.shortcut"])
        self.assertTrue(faster.flags["flag.quest.fallen_from_grace.complete"])
        self.assertEqual(normal.counters["token.quest_points"], faster.counters["token.quest_points"])

    def test_start_gates_cannot_be_skipped(self):
        for field, level in (("sailing", 61), ("crafting", 59), ("runecraft", 46), ("mining", 52)):
            with self.subTest(field=field):
                state = self.seeded(overrides={field: level})
                with self.assertRaises(DataError):
                    self.stage_at(state, "start")
        state = self.seeded(pandemonium=False)
        with self.assertRaises(DataError):
            self.stage_at(state, "start")
        state = self.seeded(boat=False)
        ship_edge = next(e for e in self.edges if e["from_location_id"] == "location.port_sarim.charter_dock"
                         and e["to_location_id"] == "location.grace.dock")
        with self.assertRaises(DataError):
            self.apply(state, ship_edge, travel=True)

    def test_supplies_and_stage_order_are_enforced(self):
        state = self.seeded()
        state = self.step(state, "pass_ffion")
        state = self.step(state, "start")
        state = self.step(state, "talk_muriel")
        state = self.step(state, "inspect_monolith")
        with self.assertRaises(DataError):
            self.stage_at(state, "mine_sunstone")
        state = self.step(state, "take_pickaxe")
        state = self.step(state, "mine_sunstone")
        with self.assertRaises(DataError):
            self.stage_at(state, "refine_sunstone")
        state = self.step(state, "take_chisel")
        state = self.step(state, "refine_sunstone")
        self.assertEqual(state.inventory["item.grace.sunstone_chunk"], 0)
        with self.assertRaises(DataError):
            self.stage_at(state, "repair_golem")


if __name__ == "__main__":
    unittest.main()
