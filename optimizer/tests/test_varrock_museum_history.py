"""Separate Varrock Museum history reports and retained antique lamps."""

from pathlib import Path
import unittest

from quest_optimizer.data import Contracts, DataError, load_catalog, read_json
from quest_optimizer.semantics import CatalogValidator
from quest_optimizer.transitions import RouteState


ROOT = Path(__file__).resolve().parents[2]
MUSEUM = "location.varrock_museum.historian_minas"
CLAIMS = {
    "museum.history.excalibur": "quest.merlins_crystal.complete",
    "museum.history.lathas": "quest.making_history.complete",
    "museum.history.salveknights": "quest.priest_in_peril.complete",
    "museum.history.soa": "quest.shield_of_arrav.complete",
}
LAMPS = {
    "museum.history.excalibur": "reward.museum.history.excalibur_lamp",
    "museum.history.lathas": "reward.museum.history.lathas_lamp",
    "museum.history.soa": "reward.museum.history.soa_lamp",
}


class VarrockMuseumHistoryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        contracts = Contracts(ROOT / "schemas")
        cls.tables = CatalogValidator(
            load_catalog(ROOT / "data/manifest.json", contracts), contracts
        ).tables
        cls.profile = read_json(ROOT / "data/profiles/main-baseline.json")

    def seed(self, completed=()):
        state = {**self.profile["initial_state"]}
        state["location_id"] = MUSEUM
        state["xp_tenths"] = {skill: 1000000 for skill in state["xp_tenths"]}
        state["completed_action_ids"] = list(completed)
        state["counters"] = {**state["counters"], "token.museum.kudos": 30}
        return RouteState(self.tables, self.profile["policies"], state)

    def claim(self, state, action_id):
        action = self.tables["actions"][action_id]
        return state.apply({
            "kind": "action", "action_id": action_id,
            "modeled_seconds": action["duration"]["expected_seconds"],
        }, action_id)

    def test_each_history_report_requires_its_own_quest(self):
        for action, prerequisite in CLAIMS.items():
            with self.subTest(action=action):
                with self.assertRaises(DataError):
                    self.claim(self.seed(), action)
                completed = self.claim(self.seed([prerequisite]), action)
                self.assertEqual(completed.snapshot()["counters"]["token.museum.kudos"], 35)
                with self.assertRaises(DataError):
                    self.claim(completed, action)

    def test_three_separate_lamps_are_paid_once_and_can_be_used(self):
        state = self.seed(CLAIMS.values())
        for action, reward_id in LAMPS.items():
            state = self.claim(state, action)
            self.assertIn(reward_id, {row["reward_id"] for row in state.snapshot()["held_rewards"]})
        self.assertEqual(state.snapshot()["counters"]["token.museum.kudos"], 45)
        self.assertEqual(len(state.snapshot()["held_rewards"]), 3)
        self.assertTrue(all(self.tables["xp_rewards"][reward]["minimum_level"] == 20
                            for reward in LAMPS.values()))
        for reward_id in LAMPS.values():
            held = next(row for row in state.snapshot()["held_rewards"] if row["reward_id"] == reward_id)
            state = state.apply({
                "kind": "reward_use", "reward_id": reward_id,
                "instance_id": held["instance_id"], "skill_id": "skill.herblore",
                "gain_xp_tenths": 10000, "overrides_observed_skill_restriction": False,
            }, reward_id)
        self.assertEqual(state.snapshot()["xp_tenths"]["skill.herblore"], 1030000)
        self.assertEqual(state.snapshot()["held_rewards"], [])

    def test_lamp_rejects_unqualified_base_skill(self):
        state = self.claim(self.seed([CLAIMS["museum.history.soa"]]), "museum.history.soa")
        snap = state.snapshot()
        snap["xp_tenths"]["skill.herblore"] = 0
        state = RouteState(self.tables, self.profile["policies"], snap)
        held = state.snapshot()["held_rewards"][0]
        with self.assertRaises(DataError):
            state.apply({
                "kind": "reward_use", "reward_id": held["reward_id"],
                "instance_id": held["instance_id"], "skill_id": "skill.herblore",
                "gain_xp_tenths": 10000, "overrides_observed_skill_restriction": False,
            })

    def test_priestly_warriors_have_two_independent_kudos_reports(self):
        first = "museum.history.salveknights"
        second = "museum.history.salveknights.in_aid"
        all_quests = [CLAIMS[first], "quest.in_aid_of_the_myreque.complete"]
        with self.assertRaises(DataError):
            self.claim(self.seed(all_quests), second)
        state = self.claim(self.seed([CLAIMS[first]]), first)
        with self.assertRaises(DataError):
            self.claim(state, second)
        state = self.claim(self.seed(all_quests), first)
        state = self.claim(state, second)
        self.assertEqual(state.snapshot()["counters"]["token.museum.kudos"], 40)
        self.assertEqual(state.snapshot()["held_rewards"], [])
        with self.assertRaises(DataError):
            self.claim(state, second)

    def test_rewards_and_ledger_match_catalog_without_ardougne_map_claim(self):
        optional = {row["id"]: row for row in read_json(
            ROOT / "data/coverage/build-242/optional-activities.json"
        )}
        registry = {row["id"]: row for row in read_json(
            ROOT / "data/raw/build-242/reward-registry.json"
        )["entries"]}
        for action, reward_id in LAMPS.items():
            self.assertEqual(optional[action]["status"], "collected")
            self.assertEqual(registry[action]["producer_action_id"], action)
            self.assertEqual(registry[action]["package"]["minimum_level"], 20)
            self.assertEqual(self.tables["actions"][action]["effects"][1]["reward_id"], reward_id)
        salve = optional["museum.history.salveknights"]
        self.assertEqual(salve["status"], "collected")
        self.assertEqual(salve["catalog_ids"], [
            "museum.history.salveknights", "museum.history.salveknights.in_aid"
        ])
        self.assertEqual(optional["museum.history.ardy"]["status"], "expected")
        self.assertNotIn("museum.history.ardy", self.tables["actions"])


if __name__ == "__main__":
    unittest.main()
