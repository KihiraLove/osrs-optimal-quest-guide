"""Troubled Tortugans materials, two gryphons, sailing gates, and one-time rewards."""

from collections import defaultdict, deque
from pathlib import Path
import unittest

from quest_optimizer.data import Contracts, DataError, load_catalog, read_json
from quest_optimizer.semantics import CatalogValidator
from quest_optimizer.transitions import RouteState


ROOT = Path(__file__).resolve().parents[2]
PREFIX = "quest.troubled_tortugans"


class TroubledTortugansTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        contracts = Contracts(ROOT / "schemas")
        cls.tables = CatalogValidator(load_catalog(ROOT / "data/manifest.json", contracts), contracts).tables
        cls.profile = read_json(ROOT / "data/profiles/main-baseline.json")
        cls.actions = read_json(ROOT / "data/catalog/troubled-tortugans/actions.json")
        cls.edges = read_json(ROOT / "data/catalog/troubled-tortugans/travel_edges.json")
        cls.adj = defaultdict(list)
        for edge in cls.tables["travel_edges"].values():
            cls.adj[edge["from_location_id"]].append(edge)

    def seeded(self, *, levels=None, boat=True):
        state = read_json(ROOT / "data/profiles/main-baseline.json")["initial_state"]
        state["location_id"] = "location.port_sarim.charter_dock"
        state["inventory"] = {"item.prying.captains_log": 1}
        for skill_id, target in (levels or {
            "sailing": 45, "slayer": 51, "hunter": 45,
            "construction": 48, "woodcutting": 40, "crafting": 34,
        }).items():
            state["xp_tenths"][f"skill.{skill_id}"] = self.tables["skills"][f"skill.{skill_id}"]["xp_thresholds_tenths"][target - 1]
        if boat:
            state["flags"]["unlock.pandemonium.raft"] = True
            state["flags"]["unlock.pandemonium.captains_log"] = True
        return RouteState(self.tables, self.profile["policies"], state)

    @staticmethod
    def apply(state, record, travel=False):
        instruction = {"kind": "travel" if travel else "action",
                       "edge_id" if travel else "action_id": record["id"],
                       "modeled_seconds": record["duration"]["expected_seconds"]}
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
                    moved = self.apply(current, edge, travel=True)
                except DataError:
                    continue
                if nxt == target:
                    return moved
                visited.add(nxt)
                queue.append(moved)
        self.fail(f"Could not reach {target} from {state.location} (searched {len(visited)} locations)")

    def step(self, state, ident):
        action = self.tables["actions"][PREFIX + "." + ident]
        return self.apply(self.arrive(state, action["start_location_id"]), action)

    def at_action(self, state, ident):
        record = self.tables["actions"][PREFIX + "." + ident]
        raw = state.snapshot()
        raw["location_id"] = record["start_location_id"]
        return self.apply(RouteState(self.tables, self.profile["policies"], raw), record)

    def at_edge(self, state, target):
        record = next(e for e in self.edges if e["to_location_id"] == target and e["mode"] == "ship")
        raw = state.snapshot()
        raw["location_id"] = record["from_location_id"]
        return self.apply(RouteState(self.tables, self.profile["policies"], raw), record, travel=True)

    def test_complete_connected_route_and_exact_materials_rewards(self):
        original = self.seeded()
        state = original
        milestones = {}
        for action in self.actions:
            state = self.step(state, action["id"].split(PREFIX + ".", 1)[1])
            milestones[action["id"]] = state.snapshot()
        last = state.snapshot()
        self.assertEqual(last["counters"]["token.quest_points"] - original.counters["token.quest_points"], 1)
        for skill, amount in (("sailing", 100000), ("slayer", 80000),
                              ("construction", 4800), ("woodcutting", 9200)):
            self.assertEqual(last["xp_tenths"][f"skill.{skill}"] - original.xp[f"skill.{skill}"], amount)
        for item_id in ("item.seaweed", "item.tortugans.palm_leaf", "item.tortugans.bandages",
                        "item.tortugans.scute", "item.tortugans.shell", "item.tortugans.jatoba_logs",
                        "item.tortugans.repair_list"):
            self.assertNotIn(item_id, last["inventory"])
        for item_id in ("item.bronze_axe", "item.hammer", "item.saw", "item.tortugans.shield"):
            self.assertEqual(last["inventory"][item_id], 1)
        for token in ("unlock.tortugans.great_conch_dock", "flag.tortugans.repairs_complete",
                      "flag.tortugans.cave_cleared", "flag.tortugans.shield_equipped",
                      "unlock.tortugans.little_pearl", "unlock.tortugans.gryphon_combat",
                      "unlock.tortugans.great_conch_facilities", "flag.quest.troubled_tortugans.complete"):
            self.assertTrue(last["flags"][token], token)
        self.assertEqual(milestones[PREFIX + ".gather_scutes"]["inventory"]["item.tortugans.scute"], 6)
        self.assertEqual(milestones[PREFIX + ".gather_shells"]["inventory"]["item.tortugans.shell"], 6)
        self.assertEqual(milestones[PREFIX + ".cut_jatoba"]["inventory"]["item.tortugans.jatoba_logs"], 10)
        self.assertNotIn("flag.quest.troubled_tortugans.complete",
                         milestones[PREFIX + ".speak_korel"]["flags"])
        with self.assertRaises(DataError):
            self.at_action(state, "complete")

    def test_all_six_base_level_and_boat_gates(self):
        required = {"sailing":45,"slayer":51,"hunter":45,"construction":48,"woodcutting":40,"crafting":34}
        for skill, level in required.items():
            levels = required.copy()
            levels[skill] = level - 1
            with self.subTest(skill=skill), self.assertRaises(DataError):
                self.at_action(self.seeded(levels=levels), "start")
        with self.assertRaises(DataError):
            self.at_edge(self.seeded(boat=False), "location.tortugans.remote_injured")
        with self.assertRaises(DataError):
            self.at_action(self.seeded(), "complete")

    def test_repairs_require_materials_and_gryphon_requires_shield(self):
        state = self.seeded()
        for action in self.actions:
            key = action["id"].split(PREFIX + ".", 1)[1]
            if key == "repair_krill_wall":
                raw = state.snapshot()
                raw["inventory"]["item.tortugans.scute"] = 1
                with self.assertRaises(DataError):
                    self.at_action(RouteState(self.tables, self.profile["policies"], raw), key)
            if key == "equip_shield":
                with self.assertRaises(DataError):
                    self.at_action(state, "defeat_shellbane")
                with self.assertRaises(DataError):
                    self.at_edge(state, "location.tortugans.pearl_dock")
            state = self.step(state, key)


if __name__ == "__main__":
    unittest.main()
