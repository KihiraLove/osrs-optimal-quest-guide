"""Fractured Archive: one mandatory first/final boss, three exclusive choices."""

from collections import defaultdict, deque
from itertools import product
from pathlib import Path
import unittest

from quest_optimizer.data import Contracts, DataError, load_catalog, read_json
from quest_optimizer.semantics import CatalogValidator
from quest_optimizer.transitions import RouteState


ROOT = Path(__file__).resolve().parents[2]
PREFIX = "miniquest.the_fractured_archive"


class FracturedArchiveTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        contracts = Contracts(ROOT / "schemas")
        cls.tables = CatalogValidator(load_catalog(ROOT / "data/manifest.json", contracts), contracts).tables
        cls.policies = read_json(ROOT / "data/profiles/main-baseline.json")["policies"]
        cls.adj = defaultdict(list)
        for edge in cls.tables["travel_edges"].values():
            cls.adj[edge["from_location_id"]].append(edge)

    def seeded(self, *, wgs=True, lantern=True):
        raw = read_json(ROOT / "data/profiles/main-baseline.json")["initial_state"]
        raw["location_id"] = "location.tears_of_guthix.light_creature"
        raw["inventory"] = {"item.sapphire_lantern": 1} if lantern else {}
        raw["flags"] = {"flag.archive.while_guthix_sleeps_complete_external": True} if wgs else {}
        return RouteState(self.tables, self.policies, raw)

    @staticmethod
    def apply(state, record, travel=False):
        step = {
            "kind": "travel" if travel else "action",
            "edge_id" if travel else "action_id": record["id"],
            "modeled_seconds": record["duration"]["expected_seconds"],
        }
        if record.get("planned_outcome"):
            step["planned_outcome"] = record["planned_outcome"]
        return state.apply(step)

    def travel(self, state, destination):
        if state.location == destination:
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
                    after = self.apply(current, edge, travel=True)
                except DataError:
                    continue
                if nxt == destination:
                    return after
                visited.add(nxt)
                queue.append(after)
        self.fail(f"No reachable route from {state.location} to {destination}")

    def step(self, state, suffix):
        action = self.tables["actions"][f"{PREFIX}.{suffix}"]
        return self.apply(self.travel(state, action["start_location_id"]), action)

    def at(self, state, suffix):
        action = self.tables["actions"][f"{PREFIX}.{suffix}"]
        raw = state.snapshot()
        raw["location_id"] = action["start_location_id"]
        return self.apply(RouteState(self.tables, self.policies, raw), action)

    def test_all_eight_exclusive_boss_routes_and_return(self):
        for second, third, fourth in product(("ezekiel", "bork"), ("moia", "dreadnoth"), ("xarth", "dagonhai")):
            with self.subTest(second=second, third=third, fourth=fourth):
                state = self.seeded()
                initial = state.snapshot()
                state = self.step(state, "start")
                self.assertTrue(state.flags["unlock.archive.raid_access"])
                self.assertFalse(state.flags.get("flag.miniquest.the_fractured_archive.complete", False))
                for suffix in ("begin_first_raid", "guardian", second, third, "quartermaster", fourth, "ocellus", "complete"):
                    state = self.step(state, suffix)
                self.assertTrue(state.flags["flag.miniquest.the_fractured_archive.complete"])
                self.assertEqual(state.location, "location.archive.ocellus")
                self.assertEqual(state.counters["token.quest_points"], initial["counters"]["token.quest_points"])
                self.assertEqual(state.xp, initial["xp_tenths"])
                self.assertEqual(state.inventory, initial["inventory"])
                self.assertEqual(len([s for s in (second, third, fourth) if s]), 3)
                with self.assertRaises(DataError):
                    self.at(state, "complete")
                state = self.travel(state, "location.archive.reward_room")
                state = self.travel(state, "location.tears_of_guthix.light_creature")
                self.assertEqual(state.location, "location.tears_of_guthix.light_creature")

    def test_access_requires_wgs_and_sapphire_lantern(self):
        for state in (self.seeded(wgs=False), self.seeded(lantern=False)):
            with self.subTest(flags=state.flags, inventory=state.inventory):
                with self.assertRaises(DataError):
                    self.at(state, "start")
                edge = self.tables["travel_edges"]["travel.archive.light_creature_to_chasm"]
                with self.assertRaises(DataError):
                    self.apply(state, edge, travel=True)

    def test_boss_order_and_exclusivity(self):
        state = self.seeded()
        with self.assertRaises(DataError):
            self.at(state, "guardian")
        state = self.step(state, "start")
        with self.assertRaises(DataError):
            self.at(state, "guardian")
        state = self.step(self.step(state, "begin_first_raid"), "guardian")
        with self.assertRaises(DataError):
            self.at(state, "moia")
        state = self.step(state, "ezekiel")
        with self.assertRaises(DataError):
            self.at(state, "bork")
        state = self.step(state, "moia")
        with self.assertRaises(DataError):
            self.at(state, "dreadnoth")
        with self.assertRaises(DataError):
            self.at(state, "xarth")
        state = self.step(state, "quartermaster")
        state = self.step(state, "xarth")
        with self.assertRaises(DataError):
            self.at(state, "dagonhai")
        with self.assertRaises(DataError):
            self.at(state, "complete")

    def test_fixed_rewards_review_is_intentionally_item_free(self):
        reviews = read_json(ROOT / "data/coverage/build-242/reward-reviews.json")
        review = next(entry for entry in reviews if entry["id"] == f"review.{PREFIX}.completion_rewards")
        self.assertEqual(review["expected_effects"][f"{PREFIX}.complete"], [
            {"kind": "flag", "token_id": "flag.miniquest.the_fractured_archive.complete", "value": True},
        ])
        journal = read_json(ROOT / "data/coverage/build-242/journal.json")
        entry = next(entry for entry in journal if entry["id"] == PREFIX)
        self.assertEqual(entry["status"], "collected")


if __name__ == "__main__":
    unittest.main()
