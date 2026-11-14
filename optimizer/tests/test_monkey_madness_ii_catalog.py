"""Focused replay checks for Monkey Madness II and Duke's optional training."""

from copy import deepcopy
from pathlib import Path
import unittest

from quest_optimizer.data import Contracts, DataError, load_catalog, read_json
from quest_optimizer.semantics import CatalogValidator
from quest_optimizer.transitions import RouteState


ROOT = Path(__file__).resolve().parents[2]
QUEST = "quest.monkey_madness_ii"
REWARD = "reward.mm2.duke_combat_training"
SKILL_GATES = {"slayer": 69, "crafting": 70, "hunter": 60, "agility": 55,
               "thieving": 55, "firemaking": 60}
PREDECESSORS = ["quest.enlightened_journey.complete", "quest.the_eyes_of_glouphrie.complete",
                "rfd.freeing_king_awowogei.complete", "quest.troll_stronghold.complete"]


class MonkeyMadnessIICatalogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        contracts = Contracts(ROOT / "schemas")
        catalog = load_catalog(ROOT / "data/manifest.json", contracts)
        cls.tables = CatalogValidator(catalog, contracts).tables
        cls.profile = read_json(ROOT / "data/profiles/main-baseline.json")
        cls.actions = read_json(ROOT / "data/catalog/monkey-madness-ii/actions.json")

    def seed(self, *, predecessors=None, watchtower=True, balloon=True, daero=False,
             trade=True, ingredients=True, talisman=True):
        initial = deepcopy(self.profile["initial_state"])
        initial["completed_action_ids"] = PREDECESSORS.copy() if predecessors is None else predecessors
        initial["flags"].update({"unlock.mm2_watchtower_prereq": watchtower,
                                 "unlock.balloon.grand_tree": balloon,
                                 "flag.monkey_madness_i.daero_training_claimed": daero})
        initial["counters"]["token.quest_points"] = 100
        initial["inventory"]["item.coins"] = 500_000
        initial["inventory"]["item.mm_mamulet"] = 1
        initial["inventory"]["item.rfd_ninja_greegree"] = 1
        initial["inventory"]["item.sapphire_lantern"] = 1
        if talisman:
            initial["inventory"]["item.mm_monkey_talisman"] = 1
        if ingredients:
            for item in ("lemon", "grapes", "pestle_and_mortar", "logs"):
                initial["inventory"]["item." + item] = 1
        for skill_id in initial["xp_tenths"]:
            initial["xp_tenths"][skill_id] = 20_000_000
        policy = deepcopy(self.profile["policies"])
        policy["trade_enabled"] = trade
        return RouteState(self.tables, policy, initial)

    def do(self, state, action_id):
        action = self.tables["actions"][action_id]
        snap = state.snapshot()
        snap["location_id"] = action["start_location_id"]
        state = RouteState(self.tables, state.policies, snap)
        step = {"kind": "action", "action_id": action_id,
                "modeled_seconds": action["duration"]["expected_seconds"]}
        if "planned_outcome" in action:
            step["planned_outcome"] = action["planned_outcome"]
        return state.apply(step)

    def route(self, state=None, *, shops=False, until=None):
        state = state or self.seed()
        for action in self.actions:
            action_id = action["id"]
            if action_id.startswith("supply.mm2.") and not shops:
                continue
            if action_id in (QUEST + ".kruk_tank_route", QUEST + ".reenter_crash_site_without_nieve",
                             "claim.monkey_madness_ii.duke"):
                continue
            state = self.do(state, action_id)
            if until == action_id:
                return state
        if until:
            self.fail("Missing quest action: " + until)
        return state

    def test_full_route_rewards_and_unlocks(self):
        final = self.route(self.seed(trade=False))
        snap = final.snapshot()
        self.assertEqual(snap["counters"]["token.quest_points"], 104)
        self.assertEqual(snap["xp_tenths"]["skill.slayer"], 20_800_000)
        self.assertEqual(snap["xp_tenths"]["skill.agility"], 20_600_000)
        self.assertEqual(snap["xp_tenths"]["skill.thieving"], 20_500_000)
        self.assertEqual(snap["xp_tenths"]["skill.hunter"], 20_500_000)
        self.assertEqual(snap["inventory"]["item.mm2_royal_seed_pod"], 1)
        self.assertEqual(snap["inventory"].get("item.mm2_charged_satchel", 0), 0)
        for name in ("complete", "crash_site", "maniacal_monkeys", "ape_bank", "ape_glider",
                     "ape_tolerance", "greegree_reclaim", "glough_rematch"):
            self.assertTrue(snap["flags"]["unlock.mm2_" + name])
        self.assertFalse(snap["held_rewards"])
        with self.assertRaises(DataError):
            self.do(final, QUEST + ".complete")

    def test_prerequisites_and_balloon_route(self):
        for missing in PREDECESSORS:
            with self.subTest(quest=missing), self.assertRaises(DataError):
                self.do(self.seed(predecessors=[p for p in PREDECESSORS if p != missing]), QUEST + ".start")
        for opts in ({"watchtower": False}, {"balloon": False}):
            with self.subTest(opts=opts), self.assertRaises(DataError):
                self.do(self.seed(**opts), QUEST + ".start")

    def test_six_nonboostable_skills(self):
        req = self.tables["actions"][QUEST + ".start"]["requirements"]["requirements"]
        skills = [r for r in req if r["kind"] == "skill"]
        self.assertEqual({r["skill_id"]: r["minimum_level"] for r in skills},
                         {"skill." + k: v for k, v in SKILL_GATES.items()})
        self.assertTrue(all(not r["boostable"] for r in skills))
        for name in SKILL_GATES:
            initial = self.seed()
            snap = initial.snapshot()
            snap["xp_tenths"]["skill." + name] = 0
            with self.subTest(skill=name), self.assertRaises(DataError):
                self.do(RouteState(self.tables, initial.policies, snap), QUEST + ".start")

    def test_item_supply_and_lab_deconstruction(self):
        state = self.route(until=QUEST + ".reveal_spy_note")
        self.assertEqual(state.snapshot()["inventory"].get("item.lemon", 0), 0)
        self.assertEqual(state.snapshot()["inventory"].get("item.grapes", 0), 0)
        self.assertEqual(state.snapshot()["inventory"]["item.mm2_scrawled_note"], 1)
        state = self.route(until=QUEST + ".use_onyx_on_device")
        snap = state.snapshot()
        self.assertEqual(snap["inventory"].get("item.mm2_charged_onyx", 0), 0)
        self.assertEqual(snap["inventory"].get("item.mm2_deconstructed_onyx", 0), 0)
        self.assertTrue(snap["flags"]["unlock.mm2_onyx_device"])
        from_shop = self.route(self.seed(ingredients=False, talisman=False), shops=True)
        self.assertTrue(from_shop.snapshot()["flags"]["unlock.mm2_complete"])
        self.assertEqual(from_shop.snapshot()["inventory"]["item.coins"], 498_480)

    def test_kruk_agility_and_tank_alternatives(self):
        state = self.route(until=QUEST + ".enter_trapdoor")
        with self.assertRaises(DataError):
            self.do(state, QUEST + ".unlock_kruk_shortcut")
        agility = self.do(state, QUEST + ".kruk_agility_route")
        self.assertTrue(agility.snapshot()["flags"]["unlock.mm2_kruk_maze"])
        tank_seed = state.snapshot()
        tank_seed["inventory"]["item.rune_pickaxe"] = 1
        tank_seed["inventory"]["item.mm2_slash_weapon"] = 1
        tank = self.do(RouteState(self.tables, state.policies, tank_seed), QUEST + ".kruk_tank_route")
        tank = self.do(tank, QUEST + ".unlock_kruk_shortcut")
        tank = self.do(tank, QUEST + ".defeat_kruk")
        self.assertTrue(tank.snapshot()["flags"]["unlock.mm2_kruk"])
        self.assertEqual(tank.snapshot()["inventory"]["item.mm2_kruk_paw"], 1)

    def test_six_distinct_satchels_and_planted_charge_consumption(self):
        filled = self.route(until=QUEST + ".fill_airship_satchels")
        self.assertEqual(filled.snapshot()["inventory"]["item.mm2_charged_satchel"], 6)
        placements = [a for a in self.actions if a["id"].startswith(QUEST + ".plant_")]
        self.assertEqual(len(placements), 6)
        state = filled
        for index, action in enumerate(placements, start=1):
            state = self.do(state, action["id"])
            self.assertEqual(state.snapshot()["inventory"].get("item.mm2_charged_satchel", 0), 6 - index)
        state = self.do(state, QUEST + ".finish_airship_sabotage")
        self.assertTrue(state.snapshot()["flags"]["unlock.mm2_six_charges"])

    def test_gorilla_waves_and_three_glough_outcomes(self):
        for name in ("defend_four_gorilla_spawns", "kill_tortured_and_demonic",
                     "glough_phase_one", "glough_phase_two", "defeat_glough"):
            with self.subTest(stage=name):
                self.assertIn("planned_outcome", self.tables["actions"][QUEST + "." + name])
        state = self.route(until=QUEST + ".glough_phase_two")
        self.assertTrue(state.snapshot()["flags"]["unlock.mm2_glough_phase_two"])
        self.assertFalse(state.snapshot()["flags"].get("unlock.mm2_glough_final", False))

    def test_duke_claim_requires_daero_and_is_not_automatic(self):
        without = self.route(self.seed(daero=False))
        with self.assertRaises(DataError):
            self.do(without, "claim.monkey_madness_ii.duke")
        with_daero = self.route(self.seed(daero=True))
        claimed = self.do(with_daero, "claim.monkey_madness_ii.duke")
        self.assertEqual(claimed.snapshot()["held_rewards"][0]["remaining_picks"], 2)
        self.assertTrue(claimed.snapshot()["flags"]["unlock.mm2_heavy_ballista"])
        with self.assertRaises(DataError):
            claimed.apply({"kind": "reward_use", "reward_id": REWARD,
                           "instance_id": REWARD + ".instance.1", "skill_id": "skill.slayer",
                           "gain_xp_tenths": 500000, "overrides_observed_skill_restriction": False})
        for _ in range(2):
            claimed = claimed.apply({"kind": "reward_use", "reward_id": REWARD,
                                     "instance_id": REWARD + ".instance.1", "skill_id": "skill.ranged",
                                     "gain_xp_tenths": 500000,
                                     "overrides_observed_skill_restriction": False})
        self.assertEqual(claimed.snapshot()["xp_tenths"]["skill.ranged"], 21_000_000)
        self.assertFalse(claimed.snapshot()["held_rewards"])
        with self.assertRaises(DataError):
            self.do(claimed, "claim.monkey_madness_ii.duke")

    def test_reversible_travel_and_shared_bridges(self):
        edges = [x for x in self.tables["travel_edges"].values() if x["id"].startswith("travel.mm2.")]
        pairs = {(x["from_location_id"], x["to_location_id"]) for x in edges}
        self.assertGreaterEqual(len(edges), 125)
        self.assertTrue(all((b, a) in pairs for a, b in pairs))
        self.assertIn(("location.mm.daero", "location.mm2.tile_2465_3496_0"), pairs)
        self.assertIn(("location.mm.garkor", "location.mm2.tile_2807_2762_0"), pairs)


if __name__ == "__main__":
    unittest.main()
