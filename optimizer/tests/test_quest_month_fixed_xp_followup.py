"""Quest Month fixed XP follow-up for four quest completion actions."""

from pathlib import Path
import unittest

from quest_optimizer.data import Contracts, DataError, load_catalog, read_json
from quest_optimizer.semantics import CatalogValidator
from quest_optimizer.transitions import RouteState


ROOT = Path(__file__).resolve().parents[2]
EXPECTED = {
    "quest.tale_of_the_righteous": {"skill.mining": 15000},
    "quest.the_corsair_curse": {"skill.firemaking": 12000},
    "quest.throne_of_miscellania": {
        "skill.woodcutting": 10000, "skill.mining": 10000,
        "skill.fishing": 10000, "skill.farming": 10000,
    },
    "quest.troll_stronghold": {"skill.agility": 20000},
}


def flatten(requirement):
    if requirement["kind"] in ("all", "any"):
        return [r for child in requirement["requirements"] for r in flatten(child)]
    return [requirement]


class QuestMonthFixedXpFollowupTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        contracts = Contracts(ROOT / "schemas")
        cls.tables = CatalogValidator(load_catalog(ROOT / "data/manifest.json", contracts), contracts).tables
        cls.profile = read_json(ROOT / "data/profiles/main-baseline.json")

    def seeded(self, action, *, predecessor=True, missing_flag=None):
        initial = {**self.profile["initial_state"]}
        initial["xp_tenths"] = {k: 10_000_000 for k in initial["xp_tenths"]}
        requirements = flatten(action["requirements"])
        predecessors = [r["action_id"] for r in requirements if r["kind"] == "action_completed"]
        initial["completed_action_ids"] = predecessors if predecessor else predecessors[:-1]
        initial["flags"] = {**initial["flags"]}
        for req in requirements:
            if req["kind"] == "flag":
                initial["flags"][req["token_id"]] = (
                    not req["value"] if req["token_id"] == missing_flag else req["value"]
                )
        initial["counters"] = {**initial["counters"], "token.quest_points": 100}
        initial["location_id"] = action["start_location_id"]
        return RouteState(self.tables, self.profile["policies"], initial)

    def apply(self, state, action):
        step = {"kind": "action", "action_id": action["id"],
                "modeled_seconds": action["duration"]["expected_seconds"]}
        if "planned_outcome" in action:
            step["planned_outcome"] = action["planned_outcome"]
        return state.apply(step, action["id"])

    def test_publisher_amounts_and_four_completion_producers(self):
        changes = read_json(ROOT / "data/raw/build-242/quest-month-rewards.json")
        by_quest = {c["activity_id"]: c for c in changes["changes"]}
        for quest, amounts in EXPECTED.items():
            with self.subTest(quest=quest):
                self.assertEqual(by_quest[quest]["delivery"], "completion")
                self.assertEqual(by_quest[quest]["fixed_xp_tenths"], amounts)
                action = self.tables["actions"][quest + ".complete"]
                self.assertEqual({e["skill_id"]: e["xp_tenths"] for e in action["effects"]
                                  if e["kind"] == "xp"}, amounts)
                self.assertEqual(action["repeat_limit"], 1)

    def test_seeded_rewards_are_once_only(self):
        for quest, amounts in EXPECTED.items():
            with self.subTest(quest=quest):
                action = self.tables["actions"][quest + ".complete"]
                state = self.seeded(action)
                start = state.snapshot()
                done = self.apply(state, action)
                finish = done.snapshot()
                self.assertEqual(finish["xp_tenths"], {
                    skill: xp + amounts.get(skill, 0)
                    for skill, xp in start["xp_tenths"].items()
                })
                self.assertEqual(finish["counters"]["token.quest_points"],
                                 start["counters"]["token.quest_points"] +
                                 next(e["delta"] for e in action["effects"]
                                      if e["kind"] == "counter" and e["token_id"] == "token.quest_points"))
                with self.assertRaises(DataError):
                    self.apply(done, action)

    def test_missing_quest_predecessors_cannot_collect_rewards(self):
        for quest in EXPECTED:
            action = self.tables["actions"][quest + ".complete"]
            with self.subTest(quest=quest):
                with self.assertRaises(DataError):
                    self.apply(self.seeded(action, predecessor=False), action)

    def test_throne_requires_all_three_completion_flags(self):
        action = self.tables["actions"]["quest.throne_of_miscellania.complete"]
        requirement_flags = [r["token_id"] for r in flatten(action["requirements"])
                             if r["kind"] == "flag"]
        self.assertEqual(len(requirement_flags), 3)
        for flag in requirement_flags:
            with self.subTest(flag=flag), self.assertRaises(DataError):
                self.apply(self.seeded(action, missing_flag=flag), action)

    def test_throne_exact_effects_review_matches_new_xp(self):
        action = self.tables["actions"]["quest.throne_of_miscellania.complete"]
        reviews = read_json(ROOT / "data/coverage/build-242/reward-reviews.json")
        completion = next(r for r in reviews
                          if r["id"] == "review.quest.throne_of_miscellania.completion_rewards")
        self.assertEqual(completion["expected_effects"][action["id"]], action["effects"])
        self.assertIn("source.jagex.quest_month_2026_11_03", completion["source_ids"])

    def test_reward_reviews_link_their_completion_producers(self):
        reviews = read_json(ROOT / "data/coverage/build-242/reward-reviews.json")
        by_id = {r["id"]: r for r in reviews}
        for quest in EXPECTED:
            row = by_id["review." + quest + ".quest_month_xp"]
            self.assertEqual(row["status"], "collected")
            self.assertEqual(row["catalog_ids"], [quest + ".complete"])
            self.assertEqual(row["delivery"], "completion")
            self.assertEqual(row["legacy_claim"], "review_if_already_completed")

    def test_review_link_and_amounts(self):
        coverage = read_json(ROOT / "data/coverage/build-242.json")
        path = ROOT / coverage["quest_collection"]["quest_month_fixed_xp_followup_review"]
        review = read_json(path)
        self.assertEqual(review["status"], "collected_draft_not_independently_reviewed")
        self.assertEqual(review["fixed_xp_tenths"], EXPECTED)


if __name__ == "__main__":
    unittest.main()
