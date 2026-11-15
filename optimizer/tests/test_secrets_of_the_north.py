"""Secrets of the North: a fully connected local quest route and reward review."""

from collections import defaultdict, deque
from pathlib import Path
import unittest

from quest_optimizer.data import Contracts, DataError, load_catalog, read_json
from quest_optimizer.semantics import CatalogValidator
from quest_optimizer.transitions import RouteState

ROOT = Path(__file__).resolve().parents[2]
PREFIX = "quest.secrets_of_the_north"


class SecretsOfTheNorthTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        contracts = Contracts(ROOT / "schemas")
        cls.tables = CatalogValidator(load_catalog(ROOT / "data/manifest.json", contracts), contracts).tables
        cls.profile = read_json(ROOT / "data/profiles/main-baseline.json")
        cls.actions = read_json(ROOT / "data/catalog/secrets-of-the-north/actions.json")
        cls.adj = defaultdict(list)
        for edge in cls.tables["travel_edges"].values():
            cls.adj[edge["from_location_id"]].append(edge)

    def seeded(self, *, skills=None, upstream=True, lockpick=False):
        raw = read_json(ROOT / "data/profiles/main-baseline.json")["initial_state"]
        raw["location_id"] = "location.burthorpe.harold"
        raw["inventory"] = {"item.coins": 200}
        raw["completed_action_ids"] = [
            "miniquest.the_generals_shadow.complete",
            "quest.devious_minds.complete",
            "quest.hazeel_cult.complete",
        ]
        if upstream:
            raw["completed_action_ids"].append("quest.making_friends_with_my_arm.complete")
            raw["flags"]["flag.quest.death_plateau.complete"] = True
        for name, level in {"agility":69,"thieving":64,"hunter":56,**(skills or {})}.items():
            raw["xp_tenths"]["skill." + name] = self.tables["skills"]["skill." + name]["xp_thresholds_tenths"][level - 1]
        if lockpick:
            raw["inventory"]["item.lockpick"] = 1
        return RouteState(self.tables, self.profile["policies"], raw)

    @staticmethod
    def apply(state, record, travel=False):
        result = {
            "kind": "travel" if travel else "action",
            "edge_id" if travel else "action_id": record["id"],
            "modeled_seconds": record["duration"]["expected_seconds"],
        }
        if record.get("planned_outcome"):
            result["planned_outcome"] = record["planned_outcome"]
        return state.apply(result)

    def travel(self, state, destination):
        if state.location == destination:
            return state
        q = deque([state])
        visited = {state.location}
        while q:
            current = q.popleft()
            for edge in self.adj[current.location]:
                nxt = edge["to_location_id"]
                if nxt in visited:
                    continue
                try:
                    after = self.apply(current, edge, travel=True)
                except DataError:
                    continue
                if nxt == destination:
                    return after
                visited.add(nxt)
                q.append(after)
        self.fail(f"No travel path from {state.location} to {destination}; {len(visited)} nodes visited")

    def step(self, state, suffix):
        action = self.tables["actions"][PREFIX + "." + suffix]
        return self.apply(self.travel(state, action["start_location_id"]), action)

    def at(self, state, suffix):
        action = self.tables["actions"][PREFIX + "." + suffix]
        raw = state.snapshot()
        raw["location_id"] = action["start_location_id"]
        return self.apply(RouteState(self.tables, self.profile["policies"], raw), action)

    def replay(self):
        start = self.seeded()
        state = self.step(start, "buy_lockpick")
        initial_coins = state.inventory["item.coins"]
        states = {}
        for record in self.actions:
            suffix = record["id"][len(PREFIX) + 1:]
            if suffix == "buy_lockpick":
                continue
            state = self.step(state, suffix)
            if suffix in ("pick_chest", "open_weiss", "fight_muspah", "complete", "bribe", "open_south_gate"):
                states[suffix] = state.snapshot()
        return start, state, states, initial_coins

    def test_replay_is_connected_and_rewards_paid_once(self):
        start, done, checkpoints, coins_before_bribe = self.replay()
        self.assertEqual(coins_before_bribe, 180)
        self.assertEqual(checkpoints["bribe"]["inventory"]["item.coins"], 80)
        self.assertTrue(checkpoints["pick_chest"]["inventory"]["item.secrets.scroll"])
        self.assertTrue(checkpoints["open_weiss"]["flags"]["unlock.secrets.weiss_opened"])
        self.assertNotIn("unlock.secrets.repeat", checkpoints["fight_muspah"]["flags"])
        self.assertTrue(checkpoints["open_south_gate"]["flags"]["unlock.secrets.crevice"])
        self.assertTrue(done.flags["flag.quest.secrets_of_the_north.complete"])
        self.assertTrue(done.flags["unlock.secrets.repeat"])
        self.assertTrue(done.flags["unlock.secrets.essence"])
        self.assertEqual(done.counters["token.quest_points"] - start.counters["token.quest_points"], 2)
        for name, amount in (("agility",600000),("thieving",500000),("hunter",400000)):
            self.assertEqual(done.xp["skill."+name] - start.xp["skill."+name], amount)
        self.assertEqual(done.inventory.get("item.secrets.icy_key", 0), 0)
        with self.assertRaises(DataError):
            self.at(done, "complete")

    def test_prerequisites_and_skills_enforced(self):
        with self.assertRaises(DataError):
            self.at(self.seeded(upstream=False), "start")
        for prerequisite in ("miniquest.the_generals_shadow.complete",
                             "quest.devious_minds.complete", "quest.hazeel_cult.complete"):
            with self.subTest(prerequisite=prerequisite):
                state = self.seeded()
                raw = state.snapshot()
                raw["completed_action_ids"].remove(prerequisite)
                with self.assertRaises(DataError):
                    self.at(RouteState(self.tables, self.profile["policies"], raw), "start")
        for name, level in (("agility",68),("thieving",63),("hunter",55)):
            with self.subTest(skill=name):
                with self.assertRaises(DataError):
                    self.at(self.seeded(skills={name:level}), "start")
        state = self.seeded()
        with self.assertRaises(DataError):
            self.at(state, "bribe")

    def test_items_and_puzzles_are_ordered(self):
        state = self.seeded(lockpick=True)
        for suffix in ("start","upstairs","bribe","track_barrel","track_boulder","track_bush",
                       "track_stump","track_east_boulder","track_east_bush","fight_evelot",
                       "enter_hazeel","board_raft","ask_hazeel","report_guard","ask_claus",
                       "search_shelves","open_wall"):
            state = self.step(state, suffix)
        raw = state.snapshot()
        raw["inventory"].pop("item.lockpick")
        with self.assertRaises(DataError):
            self.at(RouteState(self.tables, self.profile["policies"], raw), "pick_chest")
        state = self.step(state, "pick_chest")
        self.assertEqual(state.inventory["item.lockpick"], 1)
        self.assertEqual(state.inventory["item.secrets.scroll"], 1)
        with self.assertRaises(DataError):
            self.at(state, "complete")


if __name__ == "__main__":
    unittest.main()
