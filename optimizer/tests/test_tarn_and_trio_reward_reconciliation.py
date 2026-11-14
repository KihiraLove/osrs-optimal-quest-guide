"""Focused reward replays for Tarn's diary and Tai Bwo Wannai Trio."""

from pathlib import Path
import unittest

from quest_optimizer.data import Contracts, DataError, load_catalog, read_json
from quest_optimizer.semantics import CatalogValidator
from quest_optimizer.transitions import RouteState


ROOT = Path(__file__).resolve().parents[2]
TARN = "miniquest.lair_of_tarn_razorlor.complete"
TRIO = "quest.tai_bwo_wannai_trio.complete"
CLAIMS = (
    "quest.tai_bwo_wannai_trio.claim_fishing",
    "quest.tai_bwo_wannai_trio.claim_cooking",
    "quest.tai_bwo_wannai_trio.claim_combat",
)
EXPECTED = {
    "skill.fishing": 50000,
    "skill.cooking": 50000,
    "skill.attack": 25000,
    "skill.strength": 25000,
}


class TarnAndTrioRewardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        contracts = Contracts(ROOT / "schemas")
        cls.tables = CatalogValidator(load_catalog(ROOT / "data/manifest.json", contracts), contracts).tables
        cls.profile = read_json(ROOT / "data/profiles/main-baseline.json")

    def state(self, location, completed):
        init = {**self.profile["initial_state"]}
        init["xp_tenths"] = {key: 10_000_000 for key in init["xp_tenths"]}
        init["completed_action_ids"] = list(completed)
        init["location_id"] = location
        return RouteState(self.tables, self.profile["policies"], init)

    def perform(self, state, action_id):
        action = self.tables["actions"][action_id]
        return state.apply({"kind": "action", "action_id": action_id,
                            "modeled_seconds": action["duration"]["expected_seconds"]})

    def travel(self, state, edge_id):
        edge = self.tables["travel_edges"][edge_id]
        return state.apply({"kind": "travel", "edge_id": edge_id,
                            "modeled_seconds": edge["duration"]["expected_seconds"]})

    def test_registry_links_only_real_reward_producers(self):
        rows = {row["id"]: row for row in
                read_json(ROOT / "data/raw/build-242/reward-registry.json")["entries"]}
        tarn = rows["review.miniquest.lair_of_tarn_razorlor.diary"]
        self.assertEqual((tarn["status"], tarn["delivery"], tarn["producer_action_id"]),
                         ("collected", "completion", TARN))
        self.assertEqual(tarn["package"]["fixed_xp_tenths"], {"skill.slayer": 50000})

        trio = rows["review.quest.tai_bwo_wannai_trio.training"]
        self.assertEqual(trio["status"], "collected")
        self.assertEqual(trio["delivery"], "post_quest_claim")
        self.assertIsNone(trio["producer_action_id"])
        self.assertEqual(tuple(trio["producer_action_ids"]), CLAIMS)
        self.assertEqual(trio["package"]["fixed_xp_tenths"], EXPECTED)
        self.assertFalse(any(e["kind"] == "xp" for e in self.tables["actions"][TRIO]["effects"]))
        for action_id in CLAIMS:
            self.assertEqual(self.tables["actions"][action_id]["repeat_limit"], 1)
            self.assertIn({"kind": "action_completed", "action_id": TRIO},
                          self.tables["actions"][action_id]["requirements"]["requirements"])

    def test_tarn_reading_diary_grants_one_reward(self):
        action = self.tables["actions"][TARN]
        self.assertIn("Read", action["name"])
        self.assertIn({"kind": "xp", "skill_id": "skill.slayer", "xp_tenths": 50000},
                      action["effects"])
        with self.assertRaises(DataError):
            self.perform(self.state(action["start_location_id"], []), TARN)

        state = self.state(action["start_location_id"],
                           ["miniquest.lair_of_tarn_razorlor.fight_tarn"])
        before = state.snapshot()
        state = self.perform(state, TARN)
        after = state.snapshot()
        self.assertEqual(after["xp_tenths"]["skill.slayer"] - before["xp_tenths"]["skill.slayer"], 50000)
        self.assertEqual(after["inventory"]["item.tarns_diary"], 1)
        with self.assertRaises(DataError):
            self.perform(state, TARN)

    def test_each_trio_claim_requires_quest_completion(self):
        for action_id in CLAIMS:
            with self.subTest(action_id=action_id):
                location = self.tables["actions"][action_id]["start_location_id"]
                with self.assertRaises(DataError):
                    self.perform(self.state(location, []), action_id)

    def test_trio_claim_route_awards_every_skill_once(self):
        state = self.state("location.trio.tiadeche_home", [TRIO])
        before = state.snapshot()
        state = self.perform(state, CLAIMS[0])
        self.assertTrue(state.snapshot()["flags"]["unlock.karambwan_fishing"])
        with self.assertRaises(DataError):
            self.perform(state, CLAIMS[0])

        state = self.travel(state, "travel.karamja.trio_tiadeche_home.back")
        state = self.travel(state, "travel.karamja.trio_tinsay_home.out")
        state = self.perform(state, CLAIMS[1])
        self.assertTrue(state.snapshot()["flags"]["unlock.karambwan_cooking"])
        with self.assertRaises(DataError):
            self.perform(state, CLAIMS[1])

        state = self.travel(state, "travel.karamja.trio_tinsay_home.back")
        state = self.travel(state, "travel.karamja.trio_tamayu_home.out")
        state = self.perform(state, CLAIMS[2])
        with self.assertRaises(DataError):
            self.perform(state, CLAIMS[2])
        after = state.snapshot()
        for skill_id, amount in EXPECTED.items():
            self.assertEqual(after["xp_tenths"][skill_id] - before["xp_tenths"][skill_id], amount)
        self.assertEqual(after["inventory"]["item.karambwan_poisoned_rune_spear"], 1)

    def test_batch_review_is_registered(self):
        coverage = read_json(ROOT / "data/coverage/build-242.json")
        review = read_json(ROOT / coverage["quest_collection"]["tarn_and_trio_rewards_review"])
        self.assertEqual(review["status"], "collected_draft_not_independently_reviewed")
        self.assertEqual(review["trio"]["prerequisite_action_id"], TRIO)
        self.assertEqual({claim["producer_action_id"] for claim in review["trio"]["post_quest_claims"]},
                         set(CLAIMS))


if __name__ == "__main__":
    unittest.main()
