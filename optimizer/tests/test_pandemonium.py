"""Connected Pandemonium Sailing tutorial and downstream unlock replay tests."""

from collections import defaultdict, deque
from pathlib import Path
import unittest

from quest_optimizer.data import Contracts, DataError, load_catalog, read_json
from quest_optimizer.semantics import CatalogValidator
from quest_optimizer.transitions import RouteState


ROOT = Path(__file__).resolve().parents[2]


class PandemoniumTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        contracts = Contracts(ROOT / "schemas")
        cls.tables = CatalogValidator(load_catalog(ROOT / "data/manifest.json", contracts), contracts).tables
        cls.profile = read_json(ROOT / "data/profiles/main-baseline.json")
        cls.ordered = read_json(ROOT / "data/catalog/pandemonium/actions.json")
        cls.edges = read_json(ROOT / "data/catalog/pandemonium/travel_edges.json")
        cls.adj = defaultdict(list)
        for edge in cls.tables["travel_edges"].values():
            cls.adj[edge["from_location_id"]].append(edge)

    def fresh(self):
        state = read_json(ROOT / "data/profiles/main-baseline.json")["initial_state"]
        state["location_id"] = "location.port_sarim.charter_dock"
        state["inventory"] = {}
        return RouteState(self.tables, self.profile["policies"], state)

    @staticmethod
    def apply(state, record, *, is_travel=False):
        step = {"kind": "travel" if is_travel else "action",
                "edge_id" if is_travel else "action_id": record["id"],
                "modeled_seconds": record["duration"]["expected_seconds"]}
        if "planned_outcome" in record:
            step["planned_outcome"] = record["planned_outcome"]
        return state.apply(step)

    def arrive(self, state, dest):
        if state.location == dest:
            return state
        queue = deque([state])
        visited = {state.location}
        while queue:
            current = queue.popleft()
            for edge in self.adj[current.location]:
                if edge["to_location_id"] in visited:
                    continue
                try:
                    moved = self.apply(current, edge, is_travel=True)
                except DataError:
                    continue
                if moved.location == dest:
                    return moved
                visited.add(moved.location)
                queue.append(moved)
        self.fail(f"Unreachable Pandemonium stage at {dest} from {state.location}")

    def step(self, state, ident):
        action = self.tables["actions"][ident]
        return self.apply(self.arrive(state, action["start_location_id"]), action)

    def at_action(self, state, ident):
        """Check stage requirements independently of intervening sea travel."""
        action = self.tables["actions"][ident]
        initial = state.snapshot()
        initial["location_id"] = action["start_location_id"]
        return self.apply(RouteState(self.tables, self.profile["policies"], initial), action)

    def at_edge(self, state, edge):
        """Check route gates at the real edge origin without a prior journey."""
        initial = state.snapshot()
        initial["location_id"] = edge["from_location_id"]
        return self.apply(RouteState(self.tables, self.profile["policies"], initial), edge, is_travel=True)

    def test_connected_quest_replay_and_all_rewards(self):
        before = self.fresh()
        state = before
        checkpoints = {}
        for action in self.ordered:
            state = self.step(state, action["id"])
            if action["id"] in ("quest.pandemonium.exchange_cup", "quest.pandemonium.get_log",
                                "quest.pandemonium.deliver_cargo", "quest.pandemonium.complete"):
                checkpoints[action["id"]] = state.snapshot()

        snap = state.snapshot()
        self.assertEqual(snap["counters"]["token.quest_points"], before.counters["token.quest_points"] + 1)
        self.assertEqual(snap["xp_tenths"]["skill.sailing"] - before.xp["skill.sailing"], 4000)
        self.assertEqual(checkpoints["quest.pandemonium.deliver_cargo"]["xp_tenths"]["skill.sailing"]
                         - before.xp["skill.sailing"], 1000)
        self.assertEqual(checkpoints["quest.pandemonium.complete"]["xp_tenths"]["skill.sailing"]
                         - checkpoints["quest.pandemonium.deliver_cargo"]["xp_tenths"]["skill.sailing"], 3000)
        self.assertTrue(checkpoints["quest.pandemonium.exchange_cup"]["flags"]["unlock.pandemonium.raft"])
        self.assertEqual(checkpoints["quest.pandemonium.get_log"]["inventory"]["item.prying.captains_log"], 1)
        self.assertEqual(snap["inventory"]["item.pandemonium.wood_sawmill_coupon"], 25)
        self.assertEqual(snap["inventory"]["item.pandemonium.repair_kit"], 2)
        self.assertEqual(snap["inventory"]["item.pandemonium.spyglass"], 1)
        self.assertEqual(snap["inventory"]["item.hammer"], 1)
        self.assertEqual(snap["inventory"]["item.saw"], 1)
        self.assertEqual(snap["inventory"]["item.prying.captains_log"], 1)
        self.assertNotIn("item.pandemonium.old_cup", snap["inventory"])
        self.assertNotIn("item.pandemonium.port_task_cargo", snap["inventory"])
        for token in ("unlock.pandemonium.raft", "unlock.pandemonium.cargo_hold",
                      "unlock.pandemonium.captains_log", "unlock.pandemonium.port_task",
                      "unlock.pandemonium.sailing", "unlock.pandemonium.island_access",
                      "unlock.pandemonium.port_tasks", "flag.quest.pandemonium.complete"):
            self.assertTrue(snap["flags"][token])
        with self.assertRaises(DataError):
            self.at_action(state, "quest.pandemonium.complete")

    def test_no_early_raft_shipyard_or_shipwreck_shortcut(self):
        state = self.fresh()
        ship = next(e for e in self.edges if e["from_location_id"] == "location.prying.pandemonium_dock"
                    and e["to_location_id"] == "location.port_sarim.charter_dock")
        yard = next(e for e in self.edges if e["from_location_id"] == "location.pandemonium.junior_jim"
                    and e["to_location_id"] == "location.pandemonium.shipyard_crates")
        will = next(e for e in self.edges if e["to_location_id"] == "location.pandemonium.will_ship")
        with self.assertRaises(DataError):
            self.at_edge(state, ship)
        with self.assertRaises(DataError):
            self.at_edge(state, yard)
        with self.assertRaises(DataError):
            self.at_edge(state, will)
        started = self.step(state, "quest.pandemonium.start")
        self.assertEqual(self.at_edge(started, will).location, "location.pandemonium.will_ship")
        with self.assertRaises(DataError):
            self.at_action(state, "quest.pandemonium.complete")

    def test_no_outside_sailing_level_or_tools_required(self):
        start = self.fresh()
        self.assertEqual(start.level("skill.sailing"), 1)
        self.assertFalse(start.inventory)
        began = self.step(start, "quest.pandemonium.start")
        self.assertIn("quest.pandemonium.start", began.completed)
        self.assertNotIn("item.saw", began.inventory)
        self.assertNotIn("item.hammer", began.inventory)
        with self.assertRaises(DataError):
            self.at_action(began, "quest.pandemonium.accept_task")

    def test_raft_and_captains_log_produce_downstream_prerequisites(self):
        state = self.fresh()
        for action in self.ordered:
            state = self.step(state, action["id"])
        raw = state.snapshot()
        raw["xp_tenths"]["skill.sailing"] = self.tables["skills"]["skill.sailing"]["xp_thresholds_tenths"][11]
        raw["xp_tenths"]["skill.smithing"] = self.tables["skills"]["skill.smithing"]["xp_thresholds_tenths"][29]
        raw["location_id"] = "location.prying.steve"
        ready = RouteState(self.tables, self.profile["policies"], raw)
        self.assertIn("item.prying.captains_log", ready.inventory)
        prying = self.step(ready, "quest.prying_times.start")
        self.assertIn("quest.prying_times.start", prying.completed)


if __name__ == "__main__":
    unittest.main()
