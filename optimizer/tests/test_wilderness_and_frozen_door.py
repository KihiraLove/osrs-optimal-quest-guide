"""Seeded route replays for Mage Arena II and The Frozen Door."""

from copy import deepcopy
from pathlib import Path
import unittest

from quest_optimizer.data import Contracts, DataError, load_catalog, read_json
from quest_optimizer.semantics import CatalogValidator
from quest_optimizer.transitions import RouteState

ROOT = Path(__file__).resolve().parents[2]
MAGE = "miniquest.mage_arena_ii"
DOOR = "miniquest.the_frozen_door"


class WildernessAndFrozenDoorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        contracts = Contracts(ROOT / "schemas")
        cls.tables = CatalogValidator(load_catalog(ROOT / "data/manifest.json", contracts), contracts).tables
        cls.profile = read_json(ROOT / "data/profiles/main-baseline.json")

    def seed(self, completed=(), *, magic_xp=50000000):
        initial = deepcopy(self.profile["initial_state"])
        initial["completed_action_ids"] = list(completed)
        initial["inventory"]["item.coins"] = 1000000
        for skill in initial["xp_tenths"]:
            initial["xp_tenths"][skill] = 50000000
        initial["xp_tenths"]["skill.magic"] = magic_xp
        return RouteState(self.tables, self.profile["policies"], initial)

    def at(self, state, location):
        snap = state.snapshot()
        snap["location_id"] = location
        return RouteState(self.tables, self.profile["policies"], snap)

    def do(self, state, action_id):
        action = self.tables["actions"][action_id]
        state = self.at(state, action["start_location_id"])
        step = {"kind": "action", "action_id": action_id,
                "modeled_seconds": action["duration"]["expected_seconds"]}
        if action.get("planned_outcome"):
            step["planned_outcome"] = action["planned_outcome"]
        return state.apply(step)

    def travel(self, state, edge_id):
        edge = self.tables["travel_edges"][edge_id]
        return state.apply({"kind": "travel", "edge_id": edge_id,
                            "modeled_seconds": edge["duration"]["expected_seconds"]})

    def prepared_mage(self):
        state = self.seed(["miniquest.mage_arena_i.complete",
                           "claim.mage_arena_i.saradomin_staff"])
        snap = state.snapshot()
        snap["inventory"]["item.mage_arena_saradomin_staff"] = 1
        snap["inventory"]["item.mage_arena_saradomin_cape"] = 1
        state = RouteState(self.tables, self.profile["policies"], snap)
        state = self.do(state, "supply.maii.ge_runes")
        state = self.do(state, "supply.maii.buy_staves_after_saradomin")
        for god in ("saradomin", "zamorak", "guthix"):
            state = self.do(state, f"train.maii.{god}_outside")
        return state

    def test_mage_arena_ii_full_replay_and_exclusive_cape(self):
        state = self.prepared_mage()
        snap = state.snapshot()
        self.assertTrue(all(snap["flags"][f"unlock.maii.{god}_outside"]
                            for god in ("saradomin", "zamorak", "guthix")))
        self.assertEqual(snap["xp_tenths"]["skill.magic"], 50105000)
        state = self.do(state, MAGE + ".start")
        snap = state.snapshot()
        self.assertEqual(snap["inventory"].pop("item.maii_enchanted_symbol"), 1)
        with self.assertRaises(DataError):
            self.do(RouteState(self.tables, state.policies, snap), MAGE + ".track_zachariah")
        for boss in ("zachariah", "porazdir", "derwen"):
            state = self.do(state, f"{MAGE}.track_{boss}")
            state = self.do(state, f"{MAGE}.defeat_{boss}")
            state = self.do(state, f"{MAGE}.deliver_{boss}")
        state = self.do(state, MAGE + ".complete")
        self.assertTrue(state.snapshot()["flags"]["unlock.mage_arena_ii_imbued_capes"])
        state = self.do(state, "claim.maii.saradomin_imbued_cape")
        snap = state.snapshot()
        self.assertEqual(snap["inventory"]["item.maii_imbued_saradomin_cape"], 1)
        self.assertEqual(snap["inventory"].get("item.mage_arena_saradomin_cape", 0), 0)
        self.assertTrue(snap["flags"]["flag.maii.imbued_cape_claimed"])
        with self.assertRaises(DataError):
            self.do(state, "claim.maii.guthix_imbued_cape")
        with self.assertRaises(DataError):
            self.do(state, MAGE + ".complete")

    def test_mage_requires_spell_training_and_75_magic(self):
        with self.assertRaises(DataError):
            self.do(self.seed(), MAGE + ".start")
        state = self.prepared_mage()
        snap = state.snapshot()
        snap["xp_tenths"]["skill.magic"] = 0
        with self.assertRaises(DataError):
            self.do(RouteState(self.tables, self.profile["policies"], snap), MAGE + ".start")
        state = self.seed(["miniquest.mage_arena_i.complete"])
        with self.assertRaises(DataError):
            self.do(state, MAGE + ".start")

    def test_mage_arena_access_uses_the_pool_and_wilderness_lever(self):
        pool = "location.mage_arena.sparkling_pool"
        chamber = "travel.other.mage_arena_i.enter_statue_chamber"
        with self.assertRaises(DataError):
            self.travel(self.at(self.seed(), pool), chamber)
        earlier = ["miniquest.mage_arena_i.complete"]
        state = self.travel(self.at(self.seed(earlier), pool), chamber)
        self.assertEqual(state.location, "location.mage_arena.god_statues")

        lever = "location.wilderness.mage_arena_bank_lever"
        edge = "travel.combat_miniquests.maii.training.out"
        with self.assertRaises(DataError):
            self.travel(self.at(self.seed(), lever), edge)
        state = self.at(self.seed(earlier), lever)
        policies = {**state.policies, "allow_wilderness_travel": False}
        with self.assertRaises(DataError):
            self.travel(RouteState(self.tables, policies, state.snapshot()), edge)
        self.assertEqual(self.travel(state, edge).location, "location.wilderness.kolodion_duel")

    def test_frozen_door_four_generals_consumed_key_and_unlock(self):
        state = self.seed(["quest.troll_stronghold.complete"])
        state = self.do(state, DOOR + ".start")
        state = self.do(state, "supply.frozen_door.ge_boss_gear")
        for god in ("armadyl", "bandos", "saradomin", "zamorak"):
            state = self.do(state, f"{DOOR}.defeat_{god}_followers")
            state = self.do(state, f"{DOOR}.defeat_{god}_general")
            self.assertEqual(state.snapshot()["inventory"][f"item.frozen_key_piece_{god}"], 1)
        state = self.do(state, DOOR + ".assemble_key")
        self.assertEqual(state.snapshot()["inventory"]["item.frozen_key"], 1)
        state = self.do(state, DOOR + ".open_door")
        state = self.do(state, DOOR + ".complete")
        snap = state.snapshot()
        self.assertTrue(snap["flags"]["unlock.frozen_door.ancient_prison"])
        self.assertEqual(snap["inventory"].get("item.frozen_key", 0), 0)
        self.assertIn(DOOR + ".complete", snap["completed_action_ids"])
        with self.assertRaises(DataError):
            self.do(state, DOOR + ".open_door")

    def test_frozen_door_skill_and_key_piece_gates(self):
        state = self.seed(["quest.troll_stronghold.complete"])
        state = self.do(state, DOOR + ".start")
        state = self.do(state, "supply.frozen_door.ge_boss_gear")
        with self.assertRaises(DataError):
            self.do(state, DOOR + ".assemble_key")
        poor = state.snapshot()
        poor["xp_tenths"]["skill.ranged"] = 0
        with self.assertRaises(DataError):
            self.do(RouteState(self.tables, self.profile["policies"], poor),
                    DOOR + ".defeat_armadyl_followers")
        with self.assertRaises(DataError):
            self.do(self.seed(), DOOR + ".start")

    def test_return_travel_and_permanent_prison_gate(self):
        state = self.seed(["quest.troll_stronghold.complete"])
        state = self.at(state, "location.frozen_door.gwd_main")
        state = self.travel(state, "travel.combat_miniquests.frozen.armadyl.out")
        self.assertEqual(state.snapshot()["location_id"], "location.frozen_door.armadyl_camp")
        state = self.travel(state, "travel.combat_miniquests.frozen.armadyl.back")
        self.assertEqual(state.snapshot()["location_id"], "location.frozen_door.gwd_main")
        state = self.at(state, "location.frozen_door.ancient_gate")
        with self.assertRaises(DataError):
            self.travel(state, "travel.combat_miniquests.frozen.prison.out")
        snap = state.snapshot()
        snap["flags"]["unlock.frozen_door.ancient_prison"] = True
        state = RouteState(self.tables, self.profile["policies"], snap)
        state = self.travel(state, "travel.combat_miniquests.frozen.prison.out")
        self.assertEqual(state.snapshot()["location_id"], "location.frozen_door.ancient_prison")
        state = self.travel(state, "travel.combat_miniquests.frozen.prison.back")
        self.assertEqual(state.snapshot()["location_id"], "location.frozen_door.ancient_gate")


if __name__ == "__main__":
    unittest.main()
