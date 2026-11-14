"""Draft transition replay and skill/reward gates for My Arm's Big Adventure."""
from copy import deepcopy
from pathlib import Path
import unittest

from quest_optimizer.data import Contracts, DataError, load_catalog, read_json
from quest_optimizer.semantics import CatalogValidator
from quest_optimizer.transitions import RouteState


ROOT = Path(__file__).resolve().parents[2]


class MyArmsBigAdventureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        contracts = Contracts(ROOT / "schemas")
        catalog = load_catalog(ROOT / "data/manifest.json", contracts)
        cls.tables = CatalogValidator(catalog, contracts).tables
        cls.profile = read_json(ROOT / "data/profiles/main-baseline.json")

    def seeded(self, finished=("quest.eadgars_ruse.complete", "quest.the_feud.complete", "quest.jungle_potion.complete")):
        initial = deepcopy(self.profile["initial_state"])
        initial["location_id"] = "location.my_arm.cleanup_field"
        initial["inventory"]["item.coins"] = 40000
        initial["counters"]["token.quest_points"] = 100
        initial["completed_action_ids"] = list(finished)
        initial["flags"]["unlock.tai_bwo_wannai_cleanup"] = True
        for skill in ("woodcutting", "farming", "herblore"):
            initial["xp_tenths"]["skill." + skill] = 2000000
        return RouteState(self.tables, self.profile["policies"], initial)

    def at(self, state, location):
        snapshot = state.snapshot()
        snapshot["location_id"] = location
        return RouteState(self.tables, self.profile["policies"], snapshot)

    def step(self, state, action_id):
        travel = action_id.startswith("travel.")
        record = self.tables["travel_edges" if travel else "actions"][action_id]
        move = {
            "kind": "travel" if travel else "action",
            "edge_id" if travel else "action_id": action_id,
            "modeled_seconds": record["duration"]["expected_seconds"],
        }
        if "planned_outcome" in record:
            move["planned_outcome"] = record["planned_outcome"]
        return state.apply(move)

    def action_at(self, state, action_id):
        record = self.tables["actions"][action_id]
        return self.step(self.at(state, record["start_location_id"]), action_id)

    def test_favour_gate_and_quest_rewards(self):
        state = self.seeded()
        q = "quest.my_arms_big_adventure."
        with self.assertRaises(DataError):
            self.action_at(state, q + "start")
        state = self.action_at(state, "supply.tai_bwo_wannai.cleanup_favour_for_my_arm")
        self.assertTrue(state.snapshot()["flags"]["flag.tai_bwo_wannai.cleanup_favour_60"])
        state = self.action_at(state, q + "start")
        state = self.action_at(state, "supply.grand_exchange.purchase_my_arm_materials")
        with self.assertRaises(DataError):
            self.action_at(state, "supply.pollnivneach.collect_ugthanki_dung")
        state = self.action_at(state, "supply.pollnivneach.acquire_red_hot_sauce")
        state = self.action_at(state, "supply.pollnivneach.collect_ugthanki_dung")
        for name in ("ask_my_arm", "retrieve_lump", "deliver_lump", "get_manual",
                     "read_manual", "fertilise_patch", "plan_karamja_trip",
                     "sail_with_barnaby", "meet_on_karamja"):
            state = self.action_at(state, q + name)
        state = self.at(state, "location.my_arm.tai_bwo_meeting")
        state = self.step(state, "travel.my_arm.murcaily.out")
        state = self.action_at(state, q + "obtain_tubers")
        self.assertFalse(state.snapshot()["flags"].get("flag.tai_bwo_wannai.cleanup_favour_60", False))
        for name in ("return_from_karamja", "teach_planting", "defeat_baby_roc",
                     "defeat_giant_roc", "harvest_goutweed", "collect_burnt_meat"):
            state = self.action_at(state, q + name)
        before = state.snapshot()
        self.assertEqual(before["xp_tenths"]["skill.farming"], 2000000 + 3150)
        self.assertEqual(before["inventory"]["item.burnt_meat"], 29)
        state = self.action_at(state, q + "complete")
        final = state.snapshot()
        self.assertEqual(final["counters"]["token.quest_points"], 101)
        self.assertEqual(final["xp_tenths"]["skill.herblore"], 2000000 + 100000)
        self.assertEqual(final["xp_tenths"]["skill.farming"], 2000000 + 3150 + 50000)
        self.assertEqual(final["inventory"]["item.lobster"], 4)
        self.assertNotIn("item.ugthanki_dung", final["inventory"])
        self.assertNotIn("item.hardy_gout_tubers", final["inventory"])
        self.assertTrue(final["flags"]["unlock.troll_stronghold_disease_free_herb_patch"])
        self.assertTrue(final["flags"]["unlock.troll_stronghold_rocks_shortcut"])
        self.assertTrue(final["flags"]["unlock.nmz_giant_roc"])

    def test_requires_all_three_earlier_quests(self):
        finished = ("quest.eadgars_ruse.complete", "quest.jungle_potion.complete")
        state = self.seeded(finished)
        state = self.action_at(state, "supply.tai_bwo_wannai.cleanup_favour_for_my_arm")
        with self.assertRaises(DataError):
            self.action_at(state, "quest.my_arms_big_adventure.start")

    def test_farming_gate(self):
        state = self.seeded()
        snapshot = state.snapshot()
        snapshot["xp_tenths"]["skill.farming"] = 0
        state = RouteState(self.tables, self.profile["policies"], snapshot)
        state = self.action_at(state, "supply.tai_bwo_wannai.cleanup_favour_for_my_arm")
        with self.assertRaises(DataError):
            self.action_at(state, "quest.my_arms_big_adventure.start")


if __name__ == "__main__":
    unittest.main()
