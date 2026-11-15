"""November 2026 lamp rewards and Demon Slayer's separate Aris claim."""

from pathlib import Path
import unittest

from quest_optimizer.data import Contracts, DataError, load_catalog, read_json
from quest_optimizer.semantics import CatalogValidator
from quest_optimizer.transitions import RouteState


ROOT = Path(__file__).resolve().parents[2]
CLAIM = "claim.demon_slayer.aris"
ARIS_LAMP = "reward.demon_slayer.quest_month_combat_lamp"
PACKAGE = {
    "quest.black_knights_fortress": ("reward.black_knights_fortress.combat_lamp", 2, 10000),
    "quest.demon_slayer": (ARIS_LAMP, 2, 10000),
    "quest.ernest_the_chicken": ("reward.ernest_the_chicken.quest_month_lamp", 1, 5000),
    "quest.romeo_juliet": ("reward.romeo_juliet.quest_month_lamp", 1, 5000),
}


def leaves(req):
    if req["kind"] in ("all", "any"):
        return [r for child in req["requirements"] for r in leaves(child)]
    return [req]


class QuestMonthLampsRecoveryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        contracts = Contracts(ROOT / "schemas")
        cls.tables = CatalogValidator(load_catalog(ROOT / "data/manifest.json", contracts), contracts).tables
        cls.profile = read_json(ROOT / "data/profiles/main-baseline.json")

    def seed(self, action, *, dependencies=True, lamp_policy=None):
        initial = {**self.profile["initial_state"]}
        initial["xp_tenths"] = {k: 10_000_000 for k in initial["xp_tenths"]}
        reqs = leaves(action["requirements"])
        prereqs = [r["action_id"] for r in reqs if r["kind"] == "action_completed"]
        initial["completed_action_ids"] = prereqs if dependencies else prereqs[:-1]
        initial["inventory"] = {**initial["inventory"]}
        initial["flags"] = {**initial["flags"]}
        initial["counters"] = {**initial["counters"], "token.quest_points": 120}
        for r in reqs:
            if r["kind"] == "item":
                initial["inventory"][r["item_id"]] = r["quantity"]
            if r["kind"] == "flag":
                initial["flags"][r["token_id"]] = r["value"]
        initial["location_id"] = action["start_location_id"]
        policies = self.profile["policies"].copy()
        if lamp_policy is not None:
            policies["quest_lamp_skill_policy"] = lamp_policy
        return RouteState(self.tables, policies, initial)

    def do(self, state, action):
        step = {"kind": "action", "action_id": action["id"],
                "modeled_seconds": action["duration"]["expected_seconds"]}
        if "planned_outcome" in action:
            step["planned_outcome"] = action["planned_outcome"]
        return state.apply(step, action["id"])

    def use_lamp(self, state, instance, skill, *, override=False):
        return state.apply({"kind": "reward_use", "reward_id": ARIS_LAMP,
                            "instance_id": instance, "skill_id": skill,
                            "gain_xp_tenths": 10000,
                            "overrides_observed_skill_restriction": override})

    def test_publisher_lamp_quantities_and_completion_timing(self):
        changes = read_json(ROOT / "data/raw/build-242/quest-month-rewards.json")
        by_quest = {r["activity_id"]: r for r in changes["changes"]}
        for quest, (reward_id, quantity, amount) in PACKAGE.items():
            with self.subTest(quest=quest):
                observed = by_quest[quest]
                self.assertEqual(observed["lamp_observation"]["quantity"], quantity)
                self.assertEqual(observed["lamp_observation"]["xp_tenths_each"], amount)
                self.assertEqual(self.tables["xp_rewards"][reward_id]["amount"]["xp_tenths"], amount)
                self.assertEqual(observed["delivery"],
                                 "post_quest_claim" if quest == "quest.demon_slayer" else "completion")

    def test_three_preexisting_quest_completions_grant_lamps_once(self):
        for quest in ("quest.black_knights_fortress", "quest.ernest_the_chicken", "quest.romeo_juliet"):
            with self.subTest(quest=quest):
                action = self.tables["actions"][quest + ".complete"]
                reward_id, quantity, _ = PACKAGE[quest]
                self.assertIn({"kind":"xp_reward","reward_id":reward_id,"quantity":quantity},
                              action["effects"])
                state = self.do(self.seed(action), action)
                held = [r for r in state.snapshot()["held_rewards"] if r["reward_id"] == reward_id]
                self.assertEqual(len(held), quantity)
                with self.assertRaises(DataError):
                    self.do(state, action)

    def test_aris_claim_requires_finished_demon_slayer(self):
        action = self.tables["actions"][CLAIM]
        self.assertEqual(action["start_location_id"], "location.varrock.aris")
        self.assertEqual(action["repeat_limit"], 1)
        with self.assertRaises(DataError):
            self.do(self.seed(action, dependencies=False), action)
        finished = self.do(self.seed(action), action)
        instances = [r for r in finished.snapshot()["held_rewards"] if r["reward_id"] == ARIS_LAMP]
        self.assertEqual(len(instances), 2)
        with self.assertRaises(DataError):
            self.do(finished, action)

    def test_demon_slayer_completion_does_not_double_grant_lamps(self):
        completion = self.tables["actions"]["quest.demon_slayer.complete"]
        self.assertFalse(any(e["kind"] == "xp_reward" for e in completion["effects"]))
        claim = self.tables["actions"][CLAIM]
        self.assertEqual(claim["effects"], [
            {"kind":"xp_reward", "reward_id":ARIS_LAMP, "quantity":2}])

    def test_two_aris_lamps_can_be_spent_on_distinct_combat_skills(self):
        claimed = self.do(self.seed(self.tables["actions"][CLAIM]), self.tables["actions"][CLAIM])
        before = claimed.snapshot()["xp_tenths"]
        claimed = self.use_lamp(claimed, ARIS_LAMP + ".instance.1", "skill.attack")
        claimed = self.use_lamp(claimed, ARIS_LAMP + ".instance.2", "skill.prayer")
        snap = claimed.snapshot()
        self.assertEqual(snap["xp_tenths"]["skill.attack"] - before["skill.attack"], 10000)
        self.assertEqual(snap["xp_tenths"]["skill.prayer"] - before["skill.prayer"], 10000)
        self.assertFalse([r for r in snap["held_rewards"] if r["reward_id"] == ARIS_LAMP])
        with self.assertRaises(DataError):
            self.use_lamp(claimed, ARIS_LAMP + ".instance.1", "skill.attack")

    def test_combat_lamps_respect_the_profile_skill_policy(self):
        lamp = self.tables["xp_rewards"][ARIS_LAMP]
        self.assertEqual(set(lamp["eligible_skills"]), {
            "skill.attack", "skill.strength", "skill.defence", "skill.ranged",
            "skill.prayer", "skill.magic", "skill.hitpoints"})
        self.assertEqual(lamp["minimum_level"], 1)  # Provisional: review gap documented.
        self.assertTrue(lamp["retainable"])
        action = self.tables["actions"][CLAIM]
        instance = ARIS_LAMP + ".instance.1"
        strict = self.do(self.seed(action, lamp_policy="observed"), action)
        with self.assertRaisesRegex(DataError, "ineligible"):
            self.use_lamp(strict, instance, "skill.herblore", override=True)

        main = self.do(self.seed(action), action)
        before = main.snapshot()["xp_tenths"]["skill.herblore"]
        after = self.use_lamp(main, instance, "skill.herblore", override=True)
        self.assertEqual(after.snapshot()["xp_tenths"]["skill.herblore"], before + 10000)

    def test_reward_reviews_and_tracked_claims_reconciled(self):
        reviews = read_json(ROOT / "data/coverage/build-242/reward-reviews.json")
        by_id = {r["id"]: r for r in reviews}
        for quest in PACKAGE:
            key = "review." + quest + ".quest_month_xp"
            row = by_id[key]
            self.assertEqual(row["status"], "collected")
            expected_producer = CLAIM if quest == "quest.demon_slayer" else quest + ".complete"
            self.assertEqual(row["catalog_ids"], [expected_producer])
        self.assertEqual(by_id[CLAIM]["status"], "collected")
        self.assertEqual(by_id[CLAIM]["expected_effects"][CLAIM], self.tables["actions"][CLAIM]["effects"])
        registry = read_json(ROOT / "data/raw/build-242/reward-registry.json")
        entries = {r["id"]: r for r in registry["entries"]}
        for key, producer in ((CLAIM, CLAIM),
                              ("review.quest.black_knights_fortress.quest_month_lamp",
                               "quest.black_knights_fortress.complete")):
            self.assertEqual(entries[key]["status"], "collected")
            self.assertEqual(entries[key]["producer_action_id"], producer)

    def test_review_source_and_coverage_are_linked(self):
        coverage = read_json(ROOT / "data/coverage/build-242.json")
        review = read_json(ROOT / coverage["quest_collection"]["quest_month_lamps_recovery_review"])
        self.assertEqual(review["status"], "collected_draft_not_independently_reviewed")
        self.assertEqual(set(review["lamp_packages"]), set(PACKAGE))
        self.assertEqual(len(review["reward_review_ids"]), 6)


if __name__ == "__main__":
    unittest.main()
