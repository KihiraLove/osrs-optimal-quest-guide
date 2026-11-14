"""Focused draft replay for the Dragon Slayer I catalog batch."""
from copy import deepcopy
from pathlib import Path
import unittest

from quest_optimizer.data import Contracts, DataError, load_catalog, read_json
from quest_optimizer.semantics import CatalogValidator
from quest_optimizer.transitions import RouteState


ROOT = Path(__file__).resolve().parents[2]


class DragonSlayerITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        contracts = Contracts(ROOT / "schemas")
        catalog = load_catalog(ROOT / "data/manifest.json", contracts)
        cls.tables = CatalogValidator(catalog, contracts).tables
        cls.profile = read_json(ROOT / "data/profiles/main-baseline.json")

    def state(self, quest_points=32):
        initial = deepcopy(self.profile["initial_state"])
        initial["location_id"] = "location.varrock.grand_exchange"
        initial["counters"]["token.quest_points"] = quest_points
        initial["inventory"]["item.coins"] = 30000
        return RouteState(self.tables, self.profile["policies"], initial)

    def perform(self, state, record_id):
        collection = "travel_edges" if record_id.startswith("travel.") else "actions"
        record = self.tables[collection][record_id]
        step = {
            "kind": "travel" if collection == "travel_edges" else "action",
            "edge_id" if collection == "travel_edges" else "action_id": record_id,
            "modeled_seconds": record["duration"]["expected_seconds"],
        }
        if "planned_outcome" in record:
            step["planned_outcome"] = record["planned_outcome"]
        return state.apply(step)

    def relocate(self, state, location):
        # Only the inter-region approach is seeded; local dungeon/ship/shortcut
        # transitions below are replayed as real catalog edges.
        snapshot = state.snapshot()
        snapshot["location_id"] = location
        return RouteState(self.tables, self.profile["policies"], snapshot)

    def test_quest_gate_and_full_stage_order(self):
        with self.assertRaises(DataError):
            self.perform(
                self.relocate(self.state(31), "location.varrock.champions_guild_door"),
                "quest.dragon_slayer_i.start",
            )

        state = self.perform(self.state(), "supply.grand_exchange.purchase_dragon_slayer_i_supplies")
        ordered = [
            ("quest.dragon_slayer_i.start", "location.varrock.champions_guild_door"),
            ("quest.dragon_slayer_i.oziach_assignment", "location.edgeville.oziach"),
            ("quest.dragon_slayer_i.guildmaster_instructions", "location.varrock.champions_guild_door"),
            ("quest.dragon_slayer_i.get_shield", "location.lumbridge_castle.duke"),
            ("quest.dragon_slayer_i.consult_oracle", "location.ice_mountain.oracle"),
        ]
        for action, location in ordered:
            state = self.perform(self.relocate(state, location), action)
        state = self.relocate(state, "location.dwarven_mine.dragon_slayer_magic_door")
        with self.assertRaises(DataError):
            self.perform(state, "travel.dragon_slayer_i.thalzar_chest.out")
        state = self.perform(state, "quest.dragon_slayer_i.get_thalzar_map")
        self.assertEqual(state.snapshot()["inventory"]["item.dragon_slayer_map_thalzar"], 1)

        state = self.perform(state, "travel.dragon_slayer_i.thalzar_chest.back")
        state = self.perform(self.relocate(state, "location.port_sarim.wormbrain"), "quest.dragon_slayer_i.get_lozar_map")
        state = self.perform(self.relocate(state, "location.melzars_maze.entrance"), "quest.dragon_slayer_i.clear_melzars_maze")
        state = self.perform(state, "travel.dragon_slayer_i.melzar_chest_exit")
        state = self.perform(self.relocate(state, "location.port_sarim.wormbrain"), "quest.dragon_slayer_i.assemble_map")
        state = self.perform(self.relocate(state, "location.port_sarim.klarense"), "quest.dragon_slayer_i.buy_ship")
        state = self.perform(state, "travel.dragon_slayer_i.lady_lumbridge_hold.out")
        state = self.perform(state, "quest.dragon_slayer_i.repair_ship")
        state = self.perform(state, "travel.dragon_slayer_i.lady_lumbridge_hold.back")
        state = self.perform(self.relocate(state, "location.draynor.ned"), "quest.dragon_slayer_i.hire_ned")
        state = self.perform(self.relocate(state, "location.port_sarim.klarense"), "quest.dragon_slayer_i.sail_crandor")

        self.assertEqual(state.snapshot()["location_id"], "location.crandor.volcano_hole")
        state = self.perform(state, "travel.dragon_slayer_i.crandor_crater_wall.out")
        with self.assertRaises(DataError):
            self.perform(state, "travel.dragon_slayer_i.karamja_volcano_shortcut.out")
        state = self.perform(state, "quest.dragon_slayer_i.open_shortcut")
        state = self.perform(state, "travel.dragon_slayer_i.crandor_lair_wall.back")
        missing_shield = state.snapshot()
        missing_shield["inventory"].pop("item.anti_dragon_shield")
        with self.assertRaises(DataError):
            self.perform(
                RouteState(self.tables, self.profile["policies"], missing_shield),
                "quest.dragon_slayer_i.defeat_elvarg",
            )
        state = self.perform(state, "quest.dragon_slayer_i.defeat_elvarg")
        self.assertEqual(state.snapshot()["inventory"]["item.elvargs_head"], 1)
        state = self.perform(state, "travel.dragon_slayer_i.crandor_lair_wall.out")
        state = self.perform(state, "travel.dragon_slayer_i.karamja_volcano_shortcut.out")
        self.assertEqual(state.snapshot()["location_id"], "location.musa_point.volcano_entrance")
        state = self.perform(self.relocate(state, "location.edgeville.oziach"), "quest.dragon_slayer_i.complete")
        final = state.snapshot()
        self.assertEqual(final["counters"]["token.quest_points"], 34)
        self.assertEqual(final["xp_tenths"]["skill.strength"], 186500)
        self.assertEqual(final["xp_tenths"]["skill.defence"], 186500)
        self.assertTrue(final["flags"]["flag.quest.dragon_slayer_i.complete"])
        self.assertTrue(final["flags"]["flag.quest.dragon_slayer_i.shortcut_open"])
        self.assertNotIn("item.elvargs_head", final["inventory"])
        self.assertNotIn("item.lobster", final["inventory"])
        self.assertNotIn("item.dragon_slayer_map_melzar", final["inventory"])
        with self.assertRaises(DataError):
            self.perform(state, "quest.dragon_slayer_i.complete")


if __name__ == "__main__":
    unittest.main()
