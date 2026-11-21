"""Replay planting, travel, and harvest gates for the two Hard diary crops."""

from pathlib import Path
import unittest

from quest_optimizer.data import Contracts, DataError, load_catalog, read_json
from quest_optimizer.semantics import CatalogValidator
from quest_optimizer.transitions import RouteState


ROOT = Path(__file__).resolve().parents[2]
BELLADONNA = "diary.lumbridge_draynor.hard.task.varp_1195_0"
BELLADONNA_GROWTH = "cooldown.farming.draynor_belladonna"
YEW_ROOTS = "diary.varrock.hard.task.varp_1177_4"
YEW_GROWTH = "cooldown.farming.varrock_palace_yew"


class HardDiaryFarmingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        contracts = Contracts(ROOT / "schemas")
        catalog = load_catalog(ROOT / "data/manifest.json", contracts)
        cls.tables = CatalogValidator(catalog, contracts).tables
        cls.profile = read_json(ROOT / "data/profiles/main-baseline.json")

    def at_patch(self, action_id, farming_level, inventory):
        initial = self.profile["initial_state"]
        skills = self.tables["skills"]
        state = {
            **initial,
            "location_id": self.tables["actions"][action_id]["start_location_id"],
            "inventory": inventory,
            "xp_tenths": {
                **initial["xp_tenths"],
                "skill.farming": skills["skill.farming"]["xp_thresholds_tenths"][farming_level - 1],
                "skill.woodcutting": skills["skill.woodcutting"]["xp_thresholds_tenths"][59],
            },
        }
        return RouteState(self.tables, self.profile["policies"], state)

    def apply_record(self, state, record_id):
        if record_id.startswith("travel."):
            step = {"kind": "travel", "edge_id": record_id}
            record = self.tables["travel_edges"][record_id]
        else:
            step = {"kind": "action", "action_id": record_id}
            record = self.tables["actions"][record_id]
            if "planned_outcome" in record:
                step["planned_outcome"] = record["planned_outcome"]
        step["modeled_seconds"] = record["duration"]["expected_seconds"]
        return state.apply(step)

    def test_belladonna_growth_advances_while_away_from_the_patch(self):
        inventory = {"item.belladonna_seed": 1, "item.rake": 1, "item.seed_dibber": 1, "item.leather_gloves": 1}
        start = self.at_patch(BELLADONNA, 63, inventory)
        with self.assertRaises(DataError):
            self.apply_record(start, BELLADONNA)
        planted = self.apply_record(start, "supply.farming.plant_draynor_belladonna")
        ready_at = planted.cooldowns[BELLADONNA_GROWTH]
        self.assertEqual(ready_at - planted.elapsed, 19_200)
        self.assertEqual(planted.xp["skill.farming"] - start.xp["skill.farming"], 910)
        self.assertNotIn("item.belladonna_seed", planted.snapshot()["inventory"])
        with self.assertRaises(DataError):
            self.apply_record(planted, BELLADONNA)

        patch_path = "travel.walk.hard_diaries.belladonna_patch."
        away = self.apply_record(planted, patch_path + "back")
        back = self.tables["travel_edges"][patch_path + "out"]
        remaining = ready_at - away.elapsed - back["duration"]["expected_seconds"]
        ready = self.apply_record(away.apply({"kind": "wait", "modeled_seconds": remaining}), back["id"])
        self.assertEqual(ready.elapsed, ready_at)
        without_gloves = ready.snapshot()
        del without_gloves["inventory"]["item.leather_gloves"]
        with self.assertRaises(DataError):
            self.apply_record(RouteState(self.tables, self.profile["policies"], without_gloves), BELLADONNA)
        harvested = self.apply_record(ready, BELLADONNA)
        self.assertTrue(harvested.flags["flag." + BELLADONNA])
        self.assertEqual(harvested.inventory["item.nightshade"], 3)
        self.assertEqual(harvested.xp["skill.farming"] - ready.xp["skill.farming"], 5_120)
        with self.assertRaisesRegex(DataError, "repeat limit"):
            self.apply_record(harvested, BELLADONNA)

    def test_yew_planting_and_root_harvest_have_separate_farming_gates(self):
        inventory = {"item.yew_sapling": 1, "item.cactus_spine": 10, "item.rake": 1, "item.spade": 1, "item.bronze_axe": 1}
        start = self.at_patch(YEW_ROOTS, 60, inventory)
        planted = self.apply_record(start, "supply.farming.plant_varrock_yew")
        ready_at = planted.cooldowns[YEW_GROWTH]
        self.assertEqual(ready_at - planted.elapsed, 24_000)
        self.assertNotIn("item.yew_sapling", planted.snapshot()["inventory"])
        self.assertNotIn("item.cactus_spine", planted.snapshot()["inventory"])
        check = "supply.farming.check_varrock_yew"
        almost_grown = planted.apply({"kind": "wait", "modeled_seconds": ready_at - planted.elapsed - 1})
        with self.assertRaises(DataError):
            self.apply_record(almost_grown, check)
        grown = almost_grown.apply({"kind": "wait", "modeled_seconds": 1})
        checked = self.apply_record(grown, check)
        self.assertEqual(checked.xp["skill.farming"] - start.xp["skill.farming"], 71_509)
        with self.assertRaises(DataError):
            self.apply_record(checked, YEW_ROOTS)
        skill = "skill.farming"
        before = checked.xp[skill]
        target = checked.thresholds[skill][67]
        ready = checked.apply({"kind": "training", "skill_id": skill, "before_xp_tenths": before,
                               "after_xp_tenths": target, "gain_xp_tenths": target - before,
                               "resume_location_id": checked.location, "required_by": [YEW_ROOTS]})
        harvested = self.apply_record(ready, YEW_ROOTS)
        self.assertTrue(harvested.flags["flag." + YEW_ROOTS])
        self.assertEqual(harvested.inventory["item.yew_roots"], 2)
        self.assertEqual(harvested.inventory["item.yew_logs"], 1)
        self.assertEqual(harvested.xp["skill.woodcutting"] - start.xp["skill.woodcutting"], 1_750)
        with self.assertRaisesRegex(DataError, "repeat limit"):
            self.apply_record(harvested, YEW_ROOTS)
