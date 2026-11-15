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
        start["flags"]["flag.rfd.legends_started"] = bridge
        start["flags"]["unlock.culinaromancers_chest"] = True
        if bridge:
            start["completed_action_ids"].extend([
                "quest.legends_quest.start", "quest.heroes_quest.complete",
                "quest.shilo_village.complete", "quest.underground_pass.complete",
                "rfd.freeing_king_awowogei.complete",
            ])
        start["counters"]["token.quest_points"] = points
        start["inventory"] = {"item.bucket_of_milk": 1, "item.rfd.pot_of_cream": 1,
                              "item.rfd.pot_of_cornflour": 1, "item.rfd.machete": 1,
                              "item.raw_chicken": 1, "item.pestle_and_mortar": 1,
                              "item.bronze_axe": 1, "item.ice_gloves": 1,
                              "item.dramen_staff": 1, "item.dramen_branch": 1}
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
                       "kill_black_dragon", "add_egg", "make_cinnamon",
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

    def test_spare_dramen_branch_can_be_cut_during_lost_city(self):
        cut_branch = self.tables["actions"]["quest.lost_city.cut_branch"]
        initial = self.seeded().snapshot()
        initial["location_id"] = cut_branch["start_location_id"]
        initial["completed_action_ids"].remove("quest.lost_city.complete")
        initial["completed_action_ids"].append("quest.lost_city.descend_entrana")
        initial["flags"]["flag.quest.lost_city.tree_spirit_defeated"] = True
        del initial["inventory"]["item.dramen_branch"]
        state = RouteState(self.tables, self.profile["policies"], initial)
        state = self.apply(self.apply(state, cut_branch), cut_branch)
        self.assertEqual(state.inventory["item.dramen_branch"], 2)

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
        self.assertEqual(snap["held_rewards"], [{
            "instance_id": "reward.rfd.culinaromancer_lamp.instance.1",
            "reward_id": "reward.rfd.culinaromancer_lamp",
            "remaining_picks": 1,
        }])
        self.assertEqual(state.location, "location.lumbridge_castle.cook")
        parent = self.apply(state, self.tables["actions"]["quest.recipe_for_disaster.complete"])
        self.assertEqual(parent.snapshot()["counters"]["token.quest_points"], 177)
        self.assertEqual(parent.snapshot()["held_rewards"], snap["held_rewards"])
        with self.assertRaises(DataError):
            self.do(state, "complete", FINALE)

    def test_finale_entry_requires_175_points_and_completed_prerequisites(self):
        ready = self.amik(self.seeded(points=174))
        self.assertEqual(ready.snapshot()["counters"]["token.quest_points"], 175)
        self.assertEqual(self.do(ready, "enter", FINALE).location, "location.rfd.culinaromancer_arena")

        snapshot = ready.snapshot()
        snapshot["counters"]["token.quest_points"] = 174
        with self.assertRaises(DataError):
            self.do(RouteState(self.tables, self.profile["policies"], snapshot), "enter", FINALE)

        for prerequisite in (AMIK + ".complete", "quest.desert_treasure_i.complete",
                             "quest.horror_from_the_deep.complete"):
            with self.subTest(prerequisite=prerequisite):
                snapshot = ready.snapshot()
                snapshot["completed_action_ids"].remove(prerequisite)
                with self.assertRaises(DataError):
                    self.do(RouteState(self.tables, self.profile["policies"], snapshot), "enter", FINALE)

    def test_bankable_lamp_can_be_redeemed_at_level_50_once(self):
        reward_id = "reward.rfd.culinaromancer_lamp"
        reward = self.tables["xp_rewards"][reward_id]
        self.assertEqual(reward["eligible_skills"], "all")
        self.assertTrue(reward["retainable"])

        skill = "skill.agility"
        thresholds = self.tables["skills"][skill]["xp_thresholds_tenths"]
        snapshot = self.seeded().snapshot()
        snapshot["held_rewards"] = [{
            "instance_id": reward_id + ".instance.1", "reward_id": reward_id, "remaining_picks": 1,
        }]
        redemption = {
            "kind": "reward_use", "instance_id": reward_id + ".instance.1", "reward_id": reward_id,
            "skill_id": skill, "gain_xp_tenths": 200000, "overrides_observed_skill_restriction": False,
        }
        snapshot["xp_tenths"][skill] = thresholds[49] - 1
        with self.assertRaises(DataError):
            RouteState(self.tables, self.profile["policies"], snapshot).apply(redemption)
        snapshot["xp_tenths"][skill] = thresholds[49]
        redeemed = RouteState(self.tables, self.profile["policies"], snapshot).apply(redemption)
        self.assertEqual(redeemed.snapshot()["xp_tenths"][skill], thresholds[49] + 200000)
        self.assertEqual(redeemed.snapshot()["held_rewards"], [])
        with self.assertRaises(DataError):
            redeemed.apply(redemption)

    def test_portal_reentry_and_bidirectional_location_edges(self):
        forward = next(e for e in self.edges if e["id"]=="travel.other.rfd_final.arena.reenter")
        back = next(e for e in self.edges if e["id"]=="travel.other.rfd_final.arena.exit")
        state = self.amik(self.seeded())
        state = self.do(state, "enter", FINALE)
        state = self.do(state,"defeat_agrith_na_na",FINALE)
        state = self.apply(state,back,travel=True)
        self.assertEqual(state.location,"location.lumbridge_castle.cook")
        chest_out = self.tables["travel_edges"]["travel.other.rfd.culinaromancers_chest.out"]
        chest_back = self.tables["travel_edges"]["travel.other.rfd.culinaromancers_chest.back"]
        locked = state.snapshot()
        locked["flags"].pop("unlock.culinaromancers_chest")
        with self.assertRaises(DataError):
            self.apply(RouteState(self.tables, self.profile["policies"], locked), chest_out, travel=True)
        state = self.apply(state, chest_out, travel=True)
        self.assertEqual(self.tables["locations"][state.location]["bank_access"], "full")
        state = self.apply(state, chest_back, travel=True)
        state = self.apply(state,forward,travel=True)
        state = self.do(state,"defeat_flambeed",FINALE)
        self.assertIn(FINALE+".defeat_flambeed",state.snapshot()["completed_action_ids"])
        for key in ("amik", "kharazi", "shrine", "dragon"):
            paths = [e for e in self.edges if "walk.rfd_final."+key in e["id"]]
            self.assertEqual(len(paths),2)
            self.assertEqual(paths[0]["from_location_id"],paths[1]["to_location_id"])


if __name__ == "__main__":
    unittest.main()
