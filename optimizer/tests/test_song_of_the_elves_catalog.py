"""Song of the Elves mandatory quest gates, supply consumption and completion replay."""

from copy import deepcopy
from pathlib import Path
import unittest

from quest_optimizer.data import Contracts, DataError, load_catalog, read_json
from quest_optimizer.semantics import CatalogValidator
from quest_optimizer.transitions import RouteState


ROOT = Path(__file__).resolve().parents[2]
QUEST = "quest.song_of_the_elves"
PREREQUISITES = ("quest.mournings_end_part_ii", "quest.making_history")
SKILLS = ("agility", "construction", "farming", "herblore", "hunter", "mining", "smithing", "woodcutting")


class SongOfTheElvesCatalogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        contracts = Contracts(ROOT / "schemas")
        cls.tables = CatalogValidator(load_catalog(ROOT / "data/manifest.json", contracts), contracts).tables
        cls.profile = read_json(ROOT / "data/profiles/main-baseline.json")
        cls.actions = read_json(ROOT / "data/catalog/song-of-the-elves/actions.json")

    def seed(self, *, earlier=PREREQUISITES, trade=True, own=False):
        initial = deepcopy(self.profile["initial_state"])
        initial["completed_action_ids"] = [q + ".complete" for q in earlier]
        initial["inventory"]["item.coins"] = 1_000_000
        initial["counters"]["token.quest_points"] = 150
        for name in initial["xp_tenths"]:
            initial["xp_tenths"][name] = 20_000_000
        if own:
            supply = next(x for x in self.actions if x["id"] == "supply.sote.purchase_required_gear")
            for effect in supply["effects"]:
                item_id = effect["item_id"]
                initial["inventory"][item_id] = initial["inventory"].get(item_id, 0) + effect["quantity"]
        policies = deepcopy(self.profile["policies"])
        policies["trade_enabled"] = trade
        return RouteState(self.tables, policies, initial)

    def do(self, state, action_id):
        action = self.tables["actions"][action_id]
        snap = state.snapshot()
        snap["location_id"] = action["start_location_id"]
        state = RouteState(self.tables, state.policies, snap)
        transition = {"kind": "action", "action_id": action_id,
                      "modeled_seconds": action["duration"]["expected_seconds"]}
        if action.get("planned_outcome"):
            transition["planned_outcome"] = action["planned_outcome"]
        return state.apply(transition)

    def route(self, state=None, *, buy=True, until=None):
        state = state or self.seed()
        for action in self.actions:
            if not buy and action["id"] == "supply.sote.purchase_required_gear":
                continue
            state = self.do(state, action["id"])
            if action["id"] == until:
                return state
        if until:
            self.fail("Unknown stage " + until)
        return state

    def test_entire_route_grants_eight_skill_rewards(self):
        state = self.route()
        snap = state.snapshot()
        self.assertEqual(snap["counters"]["token.quest_points"], 154)
        for name in SKILLS:
            self.assertEqual(snap["xp_tenths"]["skill." + name], 20_400_000, name)
        for name in ("complete", "prifddinas", "gauntlet", "zalcano", "seren_fragment_defeated"):
            self.assertTrue(snap["flags"]["unlock.sote_" + name])
        self.assertEqual(len(snap["held_rewards"]), 0)
        self.assertEqual(snap["inventory"].get("item.sote_runite_bar", 0), 0)
        self.assertEqual(snap["inventory"].get("item.limestone_brick", 0), 0)
        self.assertEqual(snap["inventory"].get("item.sote_cadantine_seed", 0), 0)
        with self.assertRaises(DataError):
            self.do(state, QUEST + ".complete")

    def test_both_predecessor_quests_are_mandatory(self):
        for missing in PREREQUISITES:
            state = self.seed(earlier=tuple(q for q in PREREQUISITES if q != missing))
            with self.subTest(missing=missing), self.assertRaises(DataError):
                self.do(state, QUEST + ".start")

    def test_all_eight_level_70_gates_are_nonboostable(self):
        for name in SKILLS:
            state = self.seed()
            snap = state.snapshot()
            snap["xp_tenths"]["skill." + name] = 0
            with self.subTest(skill=name), self.assertRaises(DataError):
                self.do(RouteState(self.tables, state.policies, snap), QUEST + ".start")

    def test_trade_disabled_with_owned_supplies(self):
        state = self.route(self.seed(trade=False, own=True), buy=False)
        self.assertTrue(state.snapshot()["flags"]["unlock.sote_complete"])

    def test_required_gear_and_combat_milestones(self):
        state = self.route(until=QUEST + ".talk_to_edmond_again")
        snap = state.snapshot()
        snap["inventory"]["item.red_dye"] = 0
        with self.assertRaises(DataError):
            self.do(RouteState(self.tables, state.policies, snap), QUEST + ".talk_to_edmond_with_outfit")
        state = self.route(until=QUEST + ".defeat_essyllt")
        self.assertTrue(state.snapshot()["flags"]["unlock.sote_essyllt_defeated"])

    def test_graph_has_return_legs_for_every_modelled_passage(self):
        edges = [edge for edge in self.tables["travel_edges"].values()
                 if edge["id"].startswith("travel.sote.")]
        self.assertGreaterEqual(len(edges), 270)
        graph = {(e["from_location_id"], e["to_location_id"]) for e in edges}
        self.assertTrue(all((target, source) in graph for source, target in graph))
        self.assertGreaterEqual(len(self.actions), 150)


if __name__ == "__main__":
    unittest.main()
