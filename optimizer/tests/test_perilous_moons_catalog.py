"""Replay the Cam Torum camps, ritual and three Moon bosses."""

from copy import deepcopy
from pathlib import Path
import unittest

from quest_optimizer.data import Contracts, DataError, load_catalog, read_json
from quest_optimizer.semantics import CatalogValidator
from quest_optimizer.transitions import RouteState


ROOT = Path(__file__).resolve().parents[2]
QUEST = "quest.perilous_moons"
LEVELS = {"slayer": 48, "hunter": 20, "fishing": 20, "runecraft": 20, "construction": 10}


class PerilousMoonsCatalogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        contracts = Contracts(ROOT / "schemas")
        cls.tables = CatalogValidator(load_catalog(ROOT / "data/manifest.json", contracts), contracts).tables
        cls.profile = read_json(ROOT / "data/profiles/main-baseline.json")
        cls.actions = read_json(ROOT / "data/catalog/perilous-moons/actions.json")

    def state(self, *, twilight=True, trade=False):
        initial = deepcopy(self.profile["initial_state"])
        initial["completed_action_ids"] = ["quest.twilights_promise.complete"] if twilight else []
        initial["counters"]["token.quest_points"] = 80
        for name in initial["xp_tenths"]:
            initial["xp_tenths"][name] = 20_000_000
        policies = deepcopy(self.profile["policies"])
        policies["trade_enabled"] = trade
        return RouteState(self.tables, policies, initial)

    def do(self, state, id):
        action = self.tables["actions"][id]
        snap = state.snapshot()
        snap["location_id"] = action["start_location_id"]
        state = RouteState(self.tables, state.policies, snap)
        transition = {"kind": "action", "action_id": id,
                      "modeled_seconds": action["duration"]["expected_seconds"]}
        if action.get("planned_outcome"):
            transition["planned_outcome"] = action["planned_outcome"]
        return state.apply(transition)

    def route(self, state=None, *, until=None):
        state = state or self.state()
        for action in self.actions:
            state = self.do(state, action["id"])
            if action["id"] == until:
                return state
        if until:
            self.fail("Missing action: " + until)
        return state

    def test_full_no_trade_route_and_rewards(self):
        state = self.route()
        snap = state.snapshot()
        self.assertEqual(snap["counters"]["token.quest_points"], 82)
        self.assertEqual(snap["xp_tenths"]["skill.slayer"], 20_400_000)
        for name in ("runecraft", "hunter", "fishing"):
            self.assertEqual(snap["xp_tenths"]["skill." + name], 20_050_000)
        for name in ("complete", "moons_repeatable", "lunar_chest_credit", "lesser_nagua_task",
                     "prison_camp", "earth_camp", "stream_camp", "blue_moon", "blood_moon", "eclipse_moon"):
            self.assertTrue(snap["flags"]["unlock.pm_" + name], name)
        self.assertEqual(snap["inventory"].get("item.pm_building_supplies", 0), 0)
        self.assertEqual(snap["inventory"].get("item.pm_moonlight_grub", 0), 0)
        self.assertEqual(snap["inventory"].get("item.pm_bream_scales", 0), 0)
        self.assertEqual(snap["inventory"].get("item.pm_moss_lizard", 0), 0)
        with self.assertRaises(DataError):
            self.do(state, QUEST + ".complete")

    def test_twilight_promise_must_be_completed(self):
        with self.assertRaises(DataError):
            self.do(self.state(twilight=False), QUEST + ".start")

    def test_all_five_unboostable_skill_requirements(self):
        for name in LEVELS:
            state = self.state()
            snap = state.snapshot()
            snap["xp_tenths"]["skill." + name] = 0
            with self.subTest(skill=name), self.assertRaises(DataError):
                self.do(RouteState(self.tables, state.policies, snap), QUEST + ".start")

    def test_ritual_consumes_earned_dungeon_resources(self):
        state = self.route(until=QUEST + ".leave_earthbound_with_lizard")
        self.assertEqual(state.snapshot()["inventory"]["item.pm_moss_lizard"], 1)
        snap = state.snapshot()
        snap["inventory"]["item.pm_bream_scales"] = 0
        with self.assertRaises(DataError):
            self.do(RouteState(self.tables, state.policies, snap), QUEST + ".talk_to_eyatlalli_with_items")
        state = self.do(state, QUEST + ".talk_to_eyatlalli_with_items")
        self.assertTrue(state.snapshot()["flags"]["unlock.pm_ritual_solved"])

    def test_each_boss_required_at_final_dialogue(self):
        state = self.route(until=QUEST + ".fight_eclipse_moon")
        for missing in ("blue_moon", "blood_moon", "eclipse_moon"):
            snap = state.snapshot()
            snap["flags"]["unlock.pm_" + missing] = False
            with self.subTest(missing=missing), self.assertRaises(DataError):
                self.do(RouteState(self.tables, state.policies, snap), QUEST + ".talk_to_jessamine_end")

    def test_directed_dungeon_links_have_return_edges(self):
        edges = [e for e in self.tables["travel_edges"].values() if e["id"].startswith("travel.pm.")]
        self.assertGreaterEqual(len(edges), 90)
        pairs = {(e["from_location_id"], e["to_location_id"]) for e in edges}
        self.assertTrue(all((b, a) in pairs for a, b in pairs))


if __name__ == "__main__":
    unittest.main()
