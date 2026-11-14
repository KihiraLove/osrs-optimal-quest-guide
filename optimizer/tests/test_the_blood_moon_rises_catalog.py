"""Seeded quest-route and reward checks for The Blood Moon Rises."""

from copy import deepcopy
from pathlib import Path
import unittest

from quest_optimizer.data import Contracts, DataError, load_catalog, read_json
from quest_optimizer.semantics import CatalogValidator
from quest_optimizer.transitions import RouteState


ROOT = Path(__file__).resolve().parents[2]
QUEST = "quest.the_blood_moon_rises"
SKILL_GATES = {
    "slayer": 74, "woodcutting": 74, "smithing": 72, "cooking": 72,
    "fletching": 70, "mining": 66, "hunter": 65, "crafting": 64,
    "herblore": 64, "magic": 57,
}


class TheBloodMoonRisesCatalogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        contracts = Contracts(ROOT / "schemas")
        catalog = load_catalog(ROOT / "data/manifest.json", contracts)
        cls.tables = CatalogValidator(catalog, contracts).tables
        cls.profile = read_json(ROOT / "data/profiles/main-baseline.json")
        cls.actions = read_json(ROOT / "data/catalog/the-blood-moon-rises/actions.json")

    def seed(self, *, sins=True, theatre=True, flail=True, trade=True):
        initial = deepcopy(self.profile["initial_state"])
        initial["completed_action_ids"] = ["quest.sins_of_the_father.complete"] if sins else []
        if theatre:
            initial["completed_action_ids"].append("quest.a_night_at_the_theatre.complete")
        initial["counters"]["token.quest_points"] = 100
        initial["inventory"]["item.coins"] = 500_000
        if flail:
            initial["inventory"]["item.blisterwood_flail"] = 1
        for name in initial["xp_tenths"]:
            initial["xp_tenths"][name] = 20_000_000
        policies = deepcopy(self.profile["policies"])
        policies["trade_enabled"] = trade
        return RouteState(self.tables, policies, initial)

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

    def route(self, state=None, *, include_replacement=False, until=None):
        state = state or self.seed()
        for action in self.actions:
            if not include_replacement and action["id"].startswith("supply.bmr."):
                continue
            state = self.do(state, action["id"])
            if action["id"] == until:
                return state
        if until:
            self.fail("No route action " + until)
        return state

    def test_full_route_and_permanent_unlocks(self):
        final = self.route()
        snap = final.snapshot()
        self.assertEqual(snap["counters"]["token.quest_points"], 104)
        self.assertEqual(snap["inventory"].get("item.blisterwood_flail", 0), 0)
        self.assertEqual(snap["inventory"]["item.hallowed_flail"], 1)
        self.assertEqual(snap["inventory"]["item.sunspear"], 1)
        for suffix in ("started", "paterdomus", "escape_key", "sangvesti", "drakan_first",
                       "efaritay", "safalaan_fed", "hallowed_flail", "stakes", "portals",
                       "drakan_second", "tob", "wyrd", "drakan_third", "vyre_tolerance",
                       "drakan_fourth", "complete", "vampyrium", "maggot_king", "bloodwood",
                       "leechfin", "venator", "pub", "ivan_paterdomus"):
            with self.subTest(unlock=suffix):
                self.assertTrue(snap["flags"]["unlock.bmr_" + suffix])
        self.assertEqual(len(snap["held_rewards"]), 1)
        self.assertEqual(snap["held_rewards"][0]["remaining_picks"], 6)
        self.assertEqual(snap["held_rewards"][0]["reward_id"], "reward.bmr.tome_of_experience")
        with self.assertRaises(DataError):
            self.do(final, QUEST + ".complete")

    def test_both_prerequisite_quest_completions_are_required(self):
        for sins, theatre in ((False, True), (True, False), (False, False)):
            with self.subTest(sins=sins, theatre=theatre), self.assertRaises(DataError):
                self.do(self.seed(sins=sins, theatre=theatre), QUEST + ".start")

    def test_ten_nonboostable_skill_gates(self):
        start = self.tables["actions"][QUEST + ".start"]
        gate_rows = [r for r in start["requirements"]["requirements"] if r["kind"] == "skill"]
        self.assertEqual({r["skill_id"]: r["minimum_level"] for r in gate_rows},
                         {"skill." + k: v for k, v in SKILL_GATES.items()})
        self.assertTrue(all(not r["boostable"] for r in gate_rows))
        for name in SKILL_GATES:
            state = self.seed()
            snap = state.snapshot()
            snap["xp_tenths"]["skill." + name] = 0
            with self.subTest(skill=name), self.assertRaises(DataError):
                self.do(RouteState(self.tables, state.policies, snap), QUEST + ".start")

    def test_ironman_route_and_optional_lost_flail_replacement(self):
        iron = self.route(self.seed(trade=False))
        self.assertTrue(iron.snapshot()["flags"]["unlock.bmr_complete"])
        replacement = self.route(self.seed(flail=False), include_replacement=True)
        self.assertTrue(replacement.snapshot()["flags"]["unlock.bmr_complete"])
        self.assertEqual(replacement.snapshot()["inventory"]["item.coins"], 460_000)
        without = self.route(self.seed(flail=False), until=QUEST + ".return_to_vanescula_ready_to_leave")
        with self.assertRaises(DataError):
            self.do(without, QUEST + ".fight_drakan1")

    def test_key_stew_flail_and_stakes_are_concrete_consumed_inputs(self):
        state = self.route(until=QUEST + ".pickup_loop_half_of_key")
        state = self.do(state, QUEST + ".assemble_solid_key")
        self.assertEqual(state.snapshot()["inventory"].get("item.bmr_tooth_half", 0), 0)
        self.assertEqual(state.snapshot()["inventory"].get("item.bmr_loop_half", 0), 0)
        self.assertEqual(state.snapshot()["inventory"]["item.bmr_solid_key"], 1)
        state = self.route(until=QUEST + ".create_hallowed_flail")
        self.assertEqual(state.snapshot()["inventory"]["item.hallowed_flail"], 1)
        self.assertEqual(state.snapshot()["inventory"].get("item.bmr_hallowed_marks", 0), 0)
        state = self.route(until=QUEST + ".return_to_ivan")
        self.assertEqual(state.snapshot()["inventory"].get("item.bmr_blisterwood_stakes", 0), 0)
        self.assertTrue(state.snapshot()["flags"]["unlock.bmr_stakes"])

    def test_four_drakan_fights_and_theatre_encounters(self):
        checkpoints = ["fight_drakan1", "fight_drakan2", "fight_drakan_third",
                       "go_to_fight_drakan4"]
        self.assertEqual(len([a for a in self.actions if any(
            a["id"] == QUEST + "." + x for x in checkpoints)]), 4)
        for suffix in checkpoints + ["fight_wyrd", "defeat_nylocas_waves",
                                     "defeat_maiden", "defeat_nylocas_vasilias"]:
            with self.subTest(encounter=suffix):
                action = self.tables["actions"][QUEST + "." + suffix]
                self.assertIn("planned_outcome", action)
        after_third = self.route(until=QUEST + ".fight_drakan_third")
        self.assertTrue(after_third.snapshot()["flags"]["unlock.bmr_vyre_tolerance"])
        self.assertFalse(after_third.snapshot()["flags"].get("unlock.bmr_complete", False))

    def test_six_chapter_tome_allows_repeated_skill(self):
        reward = self.tables["xp_rewards"]["reward.bmr.tome_of_experience"]
        self.assertEqual(reward["minimum_level"], 70)
        self.assertEqual(reward["selection_count"], 6)
        self.assertEqual(reward["amount"]["xp_tenths"], 300_000)
        self.assertFalse(reward["distinct_skills"])
        final = self.route()
        for chapter in range(6):
            final = final.apply({"kind": "reward_use", "reward_id": reward["id"],
                                 "instance_id": reward["id"] + ".instance.1",
                                 "skill_id": "skill.slayer", "gain_xp_tenths": 300_000,
                                 "overrides_observed_skill_restriction": False})
            self.assertEqual(final.snapshot()["xp_tenths"]["skill.slayer"],
                             20_000_000 + (chapter + 1) * 300_000)
        self.assertFalse(final.snapshot()["held_rewards"])

    def test_reversible_intra_quest_travel(self):
        edges = [e for e in self.tables["travel_edges"].values()
                 if e["id"].startswith("travel.bmr.")]
        self.assertGreater(len(edges), 200)
        pairs = {(e["from_location_id"], e["to_location_id"]) for e in edges}
        self.assertTrue(all((b, a) in pairs for a, b in pairs))


if __name__ == "__main__":
    unittest.main()
