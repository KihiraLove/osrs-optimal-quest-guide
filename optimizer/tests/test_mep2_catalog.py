"""Focused ordered replay of Mourning's End Part II and its altar alternatives."""

from copy import deepcopy
from pathlib import Path
import unittest

from quest_optimizer.data import Contracts, DataError, load_catalog, read_json
from quest_optimizer.semantics import CatalogValidator
from quest_optimizer.transitions import RouteState


ROOT = Path(__file__).resolve().parents[2]
QUEST = "quest.mournings_end_part_ii"
OUTFIT = ("mep1_gas_mask", "mep1_clean_top", "mep1_repaired_trousers",
          "mep1_mourner_boots", "mep1_mourner_gloves", "mep1_mourner_cloak")


class MourningsEndIICatalogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        contracts = Contracts(ROOT / "schemas")
        cls.tables = CatalogValidator(load_catalog(ROOT / "data/manifest.json", contracts), contracts).tables
        cls.profile = read_json(ROOT / "data/profiles/main-baseline.json")
        cls.actions = read_json(ROOT / "data/catalog/mournings-end-part-ii/actions.json")

    def seed(self, *, completed_earlier=True, trade=True, catalytic=False):
        initial = deepcopy(self.profile["initial_state"])
        initial["completed_action_ids"] = (["quest.mournings_end_part_i.complete"] if completed_earlier else [])
        initial["inventory"]["item.coins"] = 200_000
        initial["inventory"]["item.mep1_teleport_crystal_four"] = 1
        for piece in OUTFIT:
            initial["inventory"]["item." + piece] = 1
        if catalytic:
            initial["inventory"]["item.catalytic_talisman"] = 1
            initial["inventory"]["item.rope"] = 1
            initial["inventory"]["item.chisel"] = 1
        initial["flags"]["unlock.mourner_hq_basement"] = True
        initial["counters"]["token.mep1_teleport_charges"] = 4
        initial["counters"]["token.quest_points"] = 120
        for skill in initial["xp_tenths"]:
            initial["xp_tenths"][skill] = 20_000_000
        policies = deepcopy(self.profile["policies"])
        policies["trade_enabled"] = trade
        return RouteState(self.tables, policies, initial)

    def do(self, state, action_id):
        action = self.tables["actions"][action_id]
        snap = state.snapshot()
        snap["location_id"] = action["start_location_id"]
        state = RouteState(self.tables, state.policies, snap)
        move = {"kind": "action", "action_id": action_id,
                "modeled_seconds": action["duration"]["expected_seconds"]}
        if action.get("planned_outcome"):
            move["planned_outcome"] = action["planned_outcome"]
        return state.apply(move)

    def replay(self, state=None, *, buy=True, until=None):
        state = state or self.seed()
        for action in self.actions:
            if action["id"] == "supply.mep2.buy_temple_supplies" and not buy:
                continue
            state = self.do(state, action["id"])
            if action["id"] == until:
                return state
        if until is not None:
            self.fail(f"Requested replay waypoint was not visited: {until}")
        return state

    def test_quest_route_and_fixed_rewards(self):
        state = self.replay()
        snap = state.snapshot()
        self.assertEqual(snap["counters"]["token.quest_points"], 122)
        self.assertEqual(snap["xp_tenths"]["skill.agility"], 20_600_000)
        self.assertEqual(snap["inventory"]["item.mep2_mourning_crystal_trinket"], 1)
        self.assertEqual(snap["inventory"].get("item.mep2_blackened_crystal", 0), 0)
        self.assertEqual(snap["inventory"].get("item.mep2_newly_made_crystal", 0), 0)
        self.assertEqual(snap["inventory"].get("item.mep2_charged_crystal", 0), 0)
        self.assertEqual(snap["inventory"].get("item.rope", 0), 0)
        for number in range(1, 6):
            self.assertTrue(snap["flags"][f"unlock.mep2_puzzle_{number}"])
        self.assertTrue(snap["flags"]["unlock.mep2_final_light_route"])
        self.assertTrue(snap["flags"]["unlock.mep2_temple_sealed"])
        self.assertTrue(snap["flags"]["unlock.mep2_dark_beasts"])
        with self.assertRaises(DataError):
            self.do(state, QUEST + ".complete")

    def test_start_requires_part_i_and_mourner_disguise(self):
        with self.assertRaises(DataError):
            self.do(self.seed(completed_earlier=False), QUEST + ".talk_to_arianwyn")
        state = self.replay(until="supply.mep2.buy_temple_supplies")
        snap = state.snapshot()
        snap["inventory"].pop("item.mep1_gas_mask")
        with self.assertRaises(DataError):
            self.do(RouteState(self.tables, state.policies, snap), QUEST + ".enter_mourner_hq")

    def test_crystal_tools_and_colours_guard_puzzles(self):
        state = self.replay(until=QUEST + ".go_to_middle_from_south")
        snap = state.snapshot()
        snap["inventory"].pop("item.chisel")
        with self.assertRaises(DataError):
            self.do(RouteState(self.tables, state.policies, snap), QUEST + ".use_chisel")
        state = self.replay(until=QUEST + ".puzzle4_pillar3_remove_cyan")
        snap = state.snapshot()
        snap["inventory"].pop("item.mep2_cyan_crystal")
        with self.assertRaises(DataError):
            self.do(RouteState(self.tables, state.policies, snap), QUEST + ".puzzle4_pillar3")

    def test_death_altar_requires_one_valid_entry_item(self):
        state = self.replay(until=QUEST + ".turn_key_mirror")
        snap = state.snapshot()
        snap["inventory"].pop("item.death_talisman")
        with self.assertRaises(DataError):
            self.do(RouteState(self.tables, state.policies, snap), QUEST + ".enter_death_altar_barrier")
        snap["inventory"]["item.catalytic_tiara"] = 1
        alternative = RouteState(self.tables, state.policies, snap)
        alternative = self.do(alternative, QUEST + ".enter_death_altar_barrier")
        self.assertTrue(alternative.snapshot()["flags"]["unlock.mep2_death_altar_access"])

    def test_ironman_can_use_preowned_catalytic_talisman(self):
        state = self.replay(self.seed(trade=False, catalytic=True), buy=False)
        self.assertTrue(state.snapshot()["flags"]["unlock.mep2_complete"])

    def test_two_lletya_return_edges_spend_crystal_charges(self):
        teleports = [edge for edge in self.tables["travel_edges"].values()
                     if edge["id"].startswith("travel.mep2.") and
                     edge["mode"] == "teleport_item"]
        self.assertEqual(len(teleports), 2)
        state = self.seed()
        for expected, edge in zip((3, 2), teleports):
            snap = state.snapshot()
            snap["location_id"] = edge["from_location_id"]
            state = RouteState(self.tables, state.policies, snap)
            state = state.apply({"kind": "travel", "edge_id": edge["id"],
                                 "modeled_seconds": edge["duration"]["expected_seconds"]})
            self.assertEqual(state.snapshot()["location_id"], edge["to_location_id"])
            self.assertEqual(state.snapshot()["counters"]["token.mep1_teleport_charges"], expected)


if __name__ == "__main__":
    unittest.main()
