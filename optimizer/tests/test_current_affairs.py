"""Current Affairs council forms, mayoral fish, Sailing charting and rewards."""

from collections import defaultdict, deque
from pathlib import Path
import unittest

from quest_optimizer.data import Contracts, DataError, load_catalog, read_json
from quest_optimizer.semantics import CatalogValidator
from quest_optimizer.transitions import RouteState


ROOT = Path(__file__).resolve().parents[2]


class CurrentAffairsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        contracts = Contracts(ROOT / "schemas")
        cls.tables = CatalogValidator(load_catalog(ROOT / "data/manifest.json", contracts), contracts).tables
        cls.profile = read_json(ROOT / "data/profiles/main-baseline.json")
        cls.actions = read_json(ROOT / "data/catalog/current-affairs/actions.json")
        cls.edges = read_json(ROOT / "data/catalog/current-affairs/travel_edges.json")
        cls.adj = defaultdict(list)
        for edge in cls.tables["travel_edges"].values():
            cls.adj[edge["from_location_id"]].append(edge)

    def seeded(self, *, sailing=22, fishing=10, coins=50, prior=True, raft=True):
        state = read_json(ROOT / "data/profiles/main-baseline.json")["initial_state"]
        state["location_id"] = "location.catherby.charter_dock"
        state["inventory"] = {"item.coins": coins, "item.prying.captains_log": 1}
        state["xp_tenths"]["skill.sailing"] = self.tables["skills"]["skill.sailing"]["xp_thresholds_tenths"][sailing - 1]
        state["xp_tenths"]["skill.fishing"] = self.tables["skills"]["skill.fishing"]["xp_thresholds_tenths"][fishing - 1]
        if prior:
            state["flags"]["flag.quest.pandemonium.complete"] = True
        if raft:
            state["flags"]["unlock.pandemonium.raft"] = True
            state["flags"]["unlock.pandemonium.captains_log"] = True
        return RouteState(self.tables, self.profile["policies"], state)

    @staticmethod
    def apply(state, record, *, travel=False):
        instruction = {"kind": "travel" if travel else "action",
                       "edge_id" if travel else "action_id": record["id"],
                       "modeled_seconds": record["duration"]["expected_seconds"]}
        if "planned_outcome" in record:
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
                if edge["to_location_id"] in visited:
                    continue
                try:
                    moved = self.apply(current, edge, travel=True)
                except DataError:
                    continue
                if moved.location == target:
                    return moved
                visited.add(moved.location)
                queue.append(moved)
        self.fail(f"Unreachable {target} from {state.location} after {len(visited)} waypoints")

    def step(self, state, ident):
        action = self.tables["actions"][ident]
        return self.apply(self.arrive(state, action["start_location_id"]), action)

    def at_action(self, state, ident):
        action = self.tables["actions"][ident]
        raw = state.snapshot()
        raw["location_id"] = action["start_location_id"]
        return self.apply(RouteState(self.tables, self.profile["policies"], raw), action)

    def at_edge(self, state, edge):
        raw = state.snapshot()
        raw["location_id"] = edge["from_location_id"]
        return self.apply(RouteState(self.tables, self.profile["policies"], raw), edge, travel=True)

    def replay(self, state):
        milestones = {}
        for action in self.actions:
            state = self.step(state, action["id"])
            if action["id"] in ("quest.current_affairs.file_cr4p", "quest.current_affairs.catch_mayor",
                                "quest.current_affairs.file_signed_form", "quest.current_affairs.get_current_duck",
                                "quest.current_affairs.release_duck", "quest.current_affairs.collect_duck"):
                milestones[action["id"]] = state.snapshot()
        return state, milestones

    def test_full_route_with_fish_mayor_and_exact_rewards(self):
        before = self.seeded()
        state, milestones = self.replay(before)
        snap = state.snapshot()
        self.assertEqual(snap["counters"]["token.quest_points"], before.counters["token.quest_points"] + 1)
        self.assertEqual(snap["xp_tenths"]["skill.sailing"] - before.xp["skill.sailing"], 14000)
        self.assertEqual(snap["xp_tenths"]["skill.fishing"] - before.xp["skill.fishing"], 10000)
        self.assertEqual(snap["inventory"]["item.prying.oak_sawmill_coupon"], 25)
        self.assertEqual(snap["inventory"]["item.current.mayor_catherby"], 1)
        self.assertEqual(snap["inventory"]["item.current.current_duck"], 1)
        self.assertEqual(snap["inventory"]["item.current.tiny_net"], 1)
        self.assertEqual(snap["inventory"]["item.prying.captains_log"], 1)
        self.assertNotIn("item.coins", snap["inventory"])
        for consumed in ("item.charcoal", "item.current.form_cr4p", "item.current.form_7r45h",
                         "item.current.signed_form_7r45h", "item.current.mayoral_fishbowl"):
            self.assertNotIn(consumed, snap["inventory"])
        self.assertTrue(snap["flags"]["unlock.current.sea_charting"])
        self.assertTrue(snap["flags"]["flag.quest.current_affairs.complete"])
        self.assertTrue(milestones["quest.current_affairs.file_cr4p"]["flags"]["flag.current.cr4p"])
        self.assertTrue(milestones["quest.current_affairs.file_signed_form"]["flags"]["flag.current.bylaw"])
        self.assertEqual(milestones["quest.current_affairs.catch_mayor"]["inventory"]["item.current.mayor_catherby"], 1)
        self.assertEqual(milestones["quest.current_affairs.get_current_duck"]["inventory"]["item.current.current_duck"], 1)
        self.assertNotIn("item.current.current_duck", milestones["quest.current_affairs.release_duck"]["inventory"])
        self.assertEqual(milestones["quest.current_affairs.collect_duck"]["inventory"]["item.current.current_duck"], 1)
        with self.assertRaises(DataError):
            self.at_action(state, "quest.current_affairs.complete")

    def test_level_quest_and_coin_gates(self):
        for prior in (False, True):
            for sailing, fishing in ((21, 10), (22, 9)):
                with self.assertRaises(DataError):
                    self.at_action(self.seeded(sailing=sailing, fishing=fishing, prior=prior),
                                   "quest.current_affairs.start")
        with self.assertRaises(DataError):
            self.at_action(self.seeded(prior=False), "quest.current_affairs.start")
        state = self.seeded(coins=49)
        for action in self.actions:
            if action["id"] == "quest.current_affairs.buy_mayoral_gear":
                break
            state = self.step(state, action["id"])
        with self.assertRaises(DataError):
            self.step(state, "quest.current_affairs.buy_mayoral_gear")

    def test_boat_and_charting_sequence_gates(self):
        boat = next(e for e in self.edges if e["from_location_id"] == "location.current.catherby_sailing_dock"
                    and e["to_location_id"] == "location.current.western_water_obelisk_ripple")
        with self.assertRaises(DataError):
            self.at_edge(self.seeded(raft=False), boat)
        with self.assertRaises(DataError):
            self.at_action(self.seeded(), "quest.current_affairs.release_duck")
        with self.assertRaises(DataError):
            self.at_action(self.seeded(), "quest.current_affairs.complete")


if __name__ == "__main__":
    unittest.main()
