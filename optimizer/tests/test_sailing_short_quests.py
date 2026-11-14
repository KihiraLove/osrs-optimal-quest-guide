"""Prying Times cargo flow and Crab Quest island route/reward replay."""

from collections import defaultdict, deque
from pathlib import Path
import unittest

from quest_optimizer.data import Contracts, DataError, load_catalog, read_json
from quest_optimizer.semantics import CatalogValidator
from quest_optimizer.transitions import RouteState


ROOT = Path(__file__).resolve().parents[2]


class SailingShortQuestTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        contracts = Contracts(ROOT / "schemas")
        cls.tables = CatalogValidator(load_catalog(ROOT / "data/manifest.json", contracts), contracts).tables
        cls.profile = read_json(ROOT / "data/profiles/main-baseline.json")
        cls.actions = read_json(ROOT / "data/catalog/sailing-short-quests/actions.json")
        cls.edges = read_json(ROOT / "data/catalog/sailing-short-quests/travel_edges.json")
        cls.by_quest = {quest: [a for a in cls.actions if a["activity_id"] == quest]
                        for quest in ("quest.prying_times", "quest.crab_quest")}
        cls.adj = defaultdict(list)
        for edge in cls.tables["travel_edges"].values():
            cls.adj[edge["from_location_id"]].append(edge)

    def seeded(self, quest, *, sailing=None, other=None, tool=True):
        state = read_json(ROOT / "data/profiles/main-baseline.json")["initial_state"]
        state["location_id"] = "location.prying.steve" if quest == "prying" else "location.prying.pandemonium_dock"
        state["inventory"] = {}
        for skill, required in (("sailing", sailing if sailing is not None else (12 if quest == "prying" else 40)),
                                ("smithing", other if other is not None else 30)) if quest == "prying" else (
                                    ("sailing", sailing if sailing is not None else 40),
                                    ("fishing", other if other is not None else 30)):
            state["xp_tenths"]["skill." + skill] = self.tables["skills"]["skill." + skill]["xp_thresholds_tenths"][required - 1]
        if tool and quest == "prying":
            state["inventory"] = {"item.prying.captains_log": 1, "item.steel_bar": 1,
                                  "item.redberry_pie": 1, "item.hammer": 1}
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
        self.fail(f"Unreachable {target} from {state.location} after exploring {len(visited)} nodes")

    def do(self, state, action_id):
        record = self.tables["actions"][action_id]
        return self.apply(self.arrive(state, record["start_location_id"]), record)

    def at_action(self, state, action_id):
        """Isolate action preconditions from ship route prerequisites."""
        record = self.tables["actions"][action_id]
        initial = state.snapshot()
        initial["location_id"] = record["start_location_id"]
        return self.apply(RouteState(self.tables, self.profile["policies"], initial), record)

    def replay_quest(self, state, quest):
        for record in self.by_quest[quest]:
            state = self.do(state, record["id"])
        return state

    def test_prying_cargo_crowbar_and_rewards(self):
        before = self.seeded("prying")
        done = self.replay_quest(before, "quest.prying_times")
        snap = done.snapshot()
        self.assertEqual(snap["counters"]["token.quest_points"], before.counters["token.quest_points"] + 1)
        self.assertEqual(snap["xp_tenths"]["skill.sailing"] - before.xp["skill.sailing"], 8000)
        self.assertEqual(snap["xp_tenths"]["skill.smithing"] - before.xp["skill.smithing"], 10000)
        self.assertEqual(snap["inventory"]["item.prying.oak_sawmill_coupon"], 25)
        self.assertEqual(snap["inventory"]["item.prying.crowbar"], 1)
        for consumed in ("item.steel_bar", "item.redberry_pie", "item.prying.looty_crate", "item.prying.fish_bladder_stout"):
            self.assertNotIn(consumed, snap["inventory"])
        self.assertTrue(snap["flags"]["unlock.prying.crowbars"])
        self.assertTrue(snap["flags"]["unlock.prying.forgotten_drinks"])
        self.assertNotIn("quest.prying_times.fight_troll", snap["completed_action_ids"])
        with self.assertRaises(DataError):
            self.do(done, "quest.prying_times.complete")

    def test_crab_nine_shells_six_leaders_and_rewards(self):
        before = self.seeded("crab")
        done = self.replay_quest(before, "quest.crab_quest")
        snap = done.snapshot()
        self.assertEqual(snap["counters"]["token.quest_points"], before.counters["token.quest_points"] + 1)
        self.assertEqual(snap["xp_tenths"]["skill.sailing"] - before.xp["skill.sailing"], 100000)
        self.assertEqual(snap["xp_tenths"]["skill.fishing"] - before.xp["skill.fishing"], 30000)
        self.assertTrue(snap["flags"]["flag.crab.six_leaders_recruited"])
        self.assertTrue(snap["flags"]["unlock.crab.shell_music"])
        self.assertEqual(snap["inventory"]["item.crab.shell_collection"], 1)
        for item in ("item.crab.loose_shell", "item.crab.instrument", "item.crab.sea_soaked_bowstring",
                     "item.crab.battered_barrel", "item.crab.weathered_rosewood_plank"):
            self.assertNotIn(item, snap["inventory"])
        with self.assertRaises(DataError):
            self.do(done, "quest.crab_quest.complete")

    def test_skill_item_and_ship_gates(self):
        for state in (self.seeded("prying", sailing=11), self.seeded("prying", other=29),
                      self.seeded("prying", tool=False)):
            with self.assertRaises(DataError):
                self.do(state, "quest.prying_times.start")
        for state in (self.seeded("crab", sailing=39), self.seeded("crab", other=29)):
            with self.assertRaises(DataError):
                self.at_action(state, "quest.crab_quest.start")
        ship = next(x for x in self.edges if x["from_location_id"] == "location.prying.pandemonium_dock"
                    and x["to_location_id"] == "location.crab.bottle")
        with self.assertRaises(DataError):
            self.apply(self.seeded("prying", sailing=12), ship, travel=True)

    def test_late_gates_are_not_free(self):
        state = self.seeded("prying")
        with self.assertRaises(DataError):
            self.at_action(state, "quest.prying_times.test_sealed_crate")
        state = self.seeded("crab")
        with self.assertRaises(DataError):
            self.at_action(state, "quest.crab_quest.ceremony")


if __name__ == "__main__":
    unittest.main()
