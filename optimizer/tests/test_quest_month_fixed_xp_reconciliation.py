"""Pinned November Quest Month XP on six existing quest completion actions."""

from pathlib import Path
import unittest

from quest_optimizer.data import Contracts, DataError, load_catalog, read_json
from quest_optimizer.semantics import CatalogValidator
from quest_optimizer.transitions import RouteState


ROOT = Path(__file__).resolve().parents[2]
EXPECTED = {
    "quest.clock_tower": {"skill.firemaking": 10000},
    "quest.lost_city": {"skill.woodcutting": 15000, "skill.crafting": 15000},
    "quest.merlins_crystal": {"skill.firemaking": 10000},
    "quest.pirates_treasure": {"skill.cooking": 8000},
    "quest.rune_mysteries": {"skill.runecraft": 5000},
    "quest.sheep_herder": {"skill.hunter": 10000},
}


class QuestMonthFixedXpReconciliationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        contracts = Contracts(ROOT / "schemas")
        cls.tables = CatalogValidator(load_catalog(ROOT / "data/manifest.json", contracts), contracts).tables
        cls.profile = read_json(ROOT / "data/profiles/main-baseline.json")

    def seeded(self, action, *, include_predecessors=True, include_supplies=True):
        initial = {**self.profile["initial_state"]}
        initial["xp_tenths"] = {k: 10_000_000 for k in initial["xp_tenths"]}
        req = action["requirements"]["requirements"]
        prerequisites = [r["action_id"] for r in req if r["kind"] == "action_completed"]
        initial["completed_action_ids"] = prerequisites if include_predecessors else prerequisites[:-1]
        initial["inventory"] = {**initial["inventory"]}
        if include_supplies:
            initial["inventory"].update({r["item_id"]: r["quantity"] for r in req if r["kind"] == "item"})
        initial["counters"] = {**initial["counters"], "token.quest_points": 100}
        initial["location_id"] = action["start_location_id"]
        return RouteState(self.tables, self.profile["policies"], initial)

    def apply(self, state, action):
        step = {"kind": "action", "action_id": action["id"],
                "modeled_seconds": action["duration"]["expected_seconds"]}
        if "planned_outcome" in action:
            step["planned_outcome"] = action["planned_outcome"]
        return state.apply(step, action["id"])

    def test_pinned_publisher_amounts_match_completion_effects(self):
        publisher = read_json(ROOT / "data/raw/build-242/quest-month-rewards.json")
        observations = {r["activity_id"]: r for r in publisher["changes"]}
        for quest, xp in EXPECTED.items():
            with self.subTest(quest=quest):
                self.assertEqual(observations[quest]["delivery"], "completion")
                self.assertEqual(observations[quest]["fixed_xp_tenths"], xp)
                action = self.tables["actions"][quest + ".complete"]
                actual = {e["skill_id"]: e["xp_tenths"] for e in action["effects"]
                          if e["kind"] == "xp"}
                self.assertEqual(actual, xp)
                self.assertEqual(action["repeat_limit"], 1)

    def test_six_seeded_completions_award_xp_once(self):
        for quest, expected in EXPECTED.items():
            with self.subTest(quest=quest):
                action = self.tables["actions"][quest + ".complete"]
                start = self.seeded(action)
                before = start.snapshot()
                end = self.apply(start, action)
                after = end.snapshot()
                self.assertEqual(after["xp_tenths"], {
                    skill: xp + expected.get(skill, 0)
                    for skill, xp in before["xp_tenths"].items()
                })
                self.assertIn(action["id"], after["completed_action_ids"])
                with self.assertRaises(DataError):
                    self.apply(end, action)

    def test_merlins_crystal_is_one_thousand_firemaking_xp(self):
        action = self.tables["actions"]["quest.merlins_crystal.complete"]
        xp = [e for e in action["effects"] if e["kind"] == "xp"]
        self.assertEqual(xp, [{"kind": "xp", "skill_id": "skill.firemaking", "xp_tenths": 10000}])
        self.assertEqual([e["delta"] for e in action["effects"]
                          if e["kind"] == "counter" and e["token_id"] == "token.quest_points"], [6])
        reviews = read_json(ROOT / "data/coverage/build-242/reward-reviews.json")
        completion = next(r for r in reviews
                          if r["id"] == "review.quest.merlins_crystal.completion_rewards")
        self.assertEqual(completion["expected_effects"][action["id"]], action["effects"])

    def test_completion_predecessors_and_quest_items_still_required(self):
        for quest in EXPECTED:
            action = self.tables["actions"][quest + ".complete"]
            with self.subTest(quest=quest):
                with self.assertRaises(DataError):
                    self.apply(self.seeded(action, include_predecessors=False), action)
                if any(r["kind"] == "item" for r in action["requirements"]["requirements"]):
                    with self.assertRaises(DataError):
                        self.apply(self.seeded(action, include_supplies=False), action)

    def test_reward_reviews_link_their_completion_producers(self):
        reviews = read_json(ROOT / "data/coverage/build-242/reward-reviews.json")
        by_id = {r["id"]: r for r in reviews}
        for quest in EXPECTED:
            review = by_id["review." + quest + ".quest_month_xp"]
            self.assertEqual(review["status"], "collected")
            self.assertEqual(review["catalog_ids"], [quest + ".complete"])
            self.assertEqual(review["delivery"], "completion")
            self.assertEqual(review["legacy_claim"], "review_if_already_completed")

    def test_reconciliation_review_is_linked_to_coverage(self):
        coverage = read_json(ROOT / "data/coverage/build-242.json")
        path = ROOT / coverage["quest_collection"]["quest_month_fixed_xp_reconciliation_review"]
        raw = read_json(path)
        self.assertEqual(raw["fixed_xp_tenths"], EXPECTED)
        self.assertEqual(raw["status"], "collected_draft_not_independently_reviewed")


if __name__ == "__main__":
    unittest.main()
