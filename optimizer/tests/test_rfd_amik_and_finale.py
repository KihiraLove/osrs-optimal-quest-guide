"""Focused state/reward replay for the last two Recipe for Disaster stages."""

from pathlib import Path
import unittest

from quest_optimizer.data import Contracts, DataError, load_catalog, read_json
from quest_optimizer.semantics import CatalogValidator
from quest_optimizer.transitions import RouteState


ROOT = Path(__file__).resolve().parents[2]
AMIK = "rfd.freeing_sir_amik_varze"
FINALE = "rfd.defeating_the_culinaromancer"


class RfdAmikAndFinaleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        contracts = Contracts(ROOT / "schemas")
        cls.tables = CatalogValidator(load_catalog(ROOT / "data/manifest.json", contracts), contracts).tables
        cls.profile = read_json(ROOT / "data/profiles/main-baseline.json")
        cls.actions = read_json(ROOT / "data/catalog/rfd-amik-and-finale/actions.json")
        cls.edges = read_json(ROOT / "data/catalog/rfd-amik-and-finale/travel_edges.json")

    def seeded(self, *, bridge=True, points=175):
        start = read_json(ROOT / "data/profiles/main-baseline.json")["initial_state"]
        start["location_id"] = "location.rfd.frozen_sir_amik"
        start["completed_action_ids"] = [
            "rfd.another_cooks_quest.complete", "quest.family_crest.complete",
            "quest.waterfall_quest.complete", "quest.lost_city.complete",
            "quest.desert_treasure_i.complete", "quest.horror_from_the_deep.complete",
            *["rfd." + x + ".complete" for x in (
                "freeing_the_mountain_dwarf", "freeing_the_goblin_generals", "freeing_pirate_pete",
                "freeing_the_lumbridge_guide", "freeing_evil_dave", "freeing_skrach_uglogwee")]
        ]
        start["flags"] = {"flag.rfd.legends_started": bridge,
                          "flag.rfd.heroes_quest_complete": bridge,
                          "flag.rfd.shilo_village_complete": bridge,
                          "flag.rfd.underground_pass_complete": bridge,
                          "flag.rfd.king_awowogei_complete": bridge}
        start["counters"]["token.quest_points"] = points
        start["inventory"] = {"item.bucket_of_milk": 1, "item.rfd.pot_of_cream": 1,
                              "item.rfd.pot_of_cornflour": 1, "item.rfd.machete": 1,
                              "item.raw_chicken": 1, "item.pestle_and_mortar": 1,
                              "item.bronze_axe": 1, "item.ice_gloves": 1,
                              "item.dramen_staff": 1}
        start["xp_tenths"]["skill.woodcutting"] = self.tables["skills"]["skill.woodcutting"]["xp_thresholds_tenths"][35]
        return RouteState(self.tables, self.profile["policies"], start)

    def apply(self, state, record, *, travel=False):
        instruction = {"kind": "travel" if travel else "action",
                       "edge_id" if travel else "action_id": record["id"],
                       "modeled_seconds": record["duration"]["expected_seconds"]}
        if "planned_outcome" in record:
            instruction["planned_outcome"] = record["planned_outcome"]
        return state.apply(instruction)

    def at(self, state, location):
        """Seeded-stage replay: travel verification has independent edge tests."""
        snap = state.snapshot()
        snap["location_id"] = location
        return RouteState(self.tables, self.profile["policies"], snap)

    def do(self, state, suffix, prefix=AMIK):
        record = self.tables["actions"][prefix + "." + suffix]
        return self.apply(self.at(state, record["start_location_id"]), record)

    def amik(self, state):
        for suffix in ("inspect", "ask_cook", "mix_milk", "add_cornflour", "pick_vanilla",
                       "add_vanilla", "ask_wise_old_man", "kill_evil_chicken",
                       "kill_black_dragon", "add_egg", "cut_dramen_branch", "make_cinnamon",
                       "add_cinnamon", "flambe", "complete"):
            state = self.do(state, suffix)
        return state

    def test_sir_amik_reward_and_ingredient_consumption(self):
        original = self.seeded()
        done = self.amik(original)
        snap = done.snapshot()
        self.assertIn(AMIK + ".complete", snap["completed_action_ids"])
        self.assertEqual(snap["xp_tenths"]["skill.cooking"]-original.xp["skill.cooking"],40000)
        self.assertEqual(snap["xp_tenths"]["skill.hitpoints"]-original.xp["skill.hitpoints"],40000)
        self.assertEqual(snap["counters"]["token.quest_points"],176)
        self.assertTrue(snap["flags"]["unlock.rfd_evil_chicken_lair"])
        for ident in ("item.rfd.pot_of_cream", "item.rfd.pot_of_cornflour", "item.rfd.brulee_supreme",
                      "item.rfd.dragon_token", "item.rfd.evil_chicken_egg", "item.dramen_branch"):
            self.assertNotIn(ident, snap["inventory"])
        with self.assertRaises(DataError):
            self.do(done, "complete")

    def test_bridge_and_quest_point_gates(self):
        for state in (self.seeded(bridge=False), self.seeded(points=106)):
            with self.assertRaises(DataError):
                self.do(state, "inspect")

    def test_shrine_requires_dialogue_and_uses_normal_chicken(self):
        edge = next(e for e in self.edges if e["id"]=="travel.other.rfd_final.lair.entry")
        state = self.at(self.seeded(), edge["from_location_id"])
        with self.assertRaises(DataError):
            self.apply(state, edge, travel=True)
        state = self.do(state, "inspect")
        state = self.do(state, "ask_cook")
        state = self.do(state, "ask_wise_old_man")
        moved = self.apply(self.at(state, edge["from_location_id"]), edge, travel=True)
        self.assertEqual(moved.location, "location.rfd.evil_chicken")
        self.assertNotIn("item.raw_chicken",moved.snapshot()["inventory"])

    def test_finale_order_one_point_lamp_and_parent_no_duplicate(self):
        state = self.amik(self.seeded())
        state = self.do(state, "enter", FINALE)
        with self.assertRaises(DataError):
            self.do(state, "defeat_karamel", FINALE)
        for suffix in ("defeat_agrith_na_na", "defeat_flambeed", "defeat_karamel",
                       "defeat_dessourt", "defeat_gelatinnoth_mother", "defeat_culinaromancer",
                       "complete"):
            state = self.do(state, suffix, FINALE)
        snap = state.snapshot()
        self.assertEqual(snap["counters"]["token.quest_points"],177)
        self.assertTrue(snap["flags"]["flag.rfd.finale_complete"])
        self.assertTrue(snap["flags"]["unlock.rfd_barrows_gloves"])
        self.assertIn("reward.rfd.culinaromancer_lamp",str(snap))
        self.assertEqual(state.location,"location.lumbridge_castle.cook")
        parent = self.apply(state, self.tables["actions"]["quest.recipe_for_disaster.complete"])
        self.assertEqual(parent.snapshot()["counters"]["token.quest_points"],177)
        with self.assertRaises(DataError):
            self.do(state, "complete", FINALE)

    def test_lamp_eligible_above_fifty_and_retainable(self):
        reward = self.tables["xp_rewards"]["reward.rfd.culinaromancer_lamp"]
        self.assertEqual(reward["minimum_level"],51)
        self.assertEqual(reward["eligible_skills"],"all")
        self.assertEqual(reward["amount"]["xp_tenths"],200000)
        self.assertTrue(reward["retainable"])

    def test_portal_reentry_and_bidirectional_location_edges(self):
        forward = next(e for e in self.edges if e["id"]=="travel.other.rfd_final.arena.reenter")
        back = next(e for e in self.edges if e["id"]=="travel.other.rfd_final.arena.exit")
        state = self.amik(self.seeded())
        state = self.do(state, "enter", FINALE)
        state = self.do(state,"defeat_agrith_na_na",FINALE)
        state = self.apply(state,back,travel=True)
        self.assertEqual(state.location,"location.lumbridge_castle.cook")
        state = self.apply(state,forward,travel=True)
        state = self.do(state,"defeat_flambeed",FINALE)
        self.assertIn(FINALE+".defeat_flambeed",state.snapshot()["completed_action_ids"])
        for key in ("amik", "kharazi", "shrine", "dragon"):
            paths = [e for e in self.edges if "walk.rfd_final."+key in e["id"]]
            self.assertEqual(len(paths),2)
            self.assertEqual(paths[0]["from_location_id"],paths[1]["to_location_id"])


if __name__ == "__main__":
    unittest.main()
