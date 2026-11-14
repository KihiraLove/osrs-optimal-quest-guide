"""Once-only lamp producers for Client of Kourend, Dream Mentor and Brain Robbery."""

from pathlib import Path
import unittest

from quest_optimizer.data import Contracts, DataError, load_catalog, read_json
from quest_optimizer.semantics import CatalogValidator
from quest_optimizer.transitions import RouteState


ROOT = Path(__file__).resolve().parents[2]
PACKAGES = {
    "review.quest.client_of_kourend.xp_package": (
        "quest.client_of_kourend.complete", "reward.client_of_kourend.antique_lamp", 2, 5000, 1),
    "review.quest.dream_mentor.xp_package": (
        "quest.dream_mentor.complete", "reward.dream_mentor.dreamy_lamp", 1, 150000, 1),
    "review.quest.the_great_brain_robbery.xp_package": (
        "quest.the_great_brain_robbery.complete", "reward.the_great_brain_robbery.blessed_lamp", 1, 50000, 30),
}


def flatten(req):
    if req["kind"] in ("all", "any"):
        return [r for child in req["requirements"] for r in flatten(child)]
    return [req]


class ExistingLampPackageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        contracts = Contracts(ROOT / "schemas")
        cls.tables = CatalogValidator(load_catalog(ROOT / "data/manifest.json", contracts), contracts).tables
        cls.profile = read_json(ROOT / "data/profiles/main-baseline.json")

    def seeded(self, action, *, prerequisites=True):
        init = {**self.profile["initial_state"]}
        init["xp_tenths"] = {k: 10_000_000 for k in init["xp_tenths"]}
        reqs = flatten(action["requirements"])
        ids = [r["action_id"] for r in reqs if r["kind"] == "action_completed"]
        init["completed_action_ids"] = ids if prerequisites else ids[:-1]
        init["counters"] = {**init["counters"], "token.quest_points": 180}
        init["inventory"] = {**init["inventory"]}
        init["flags"] = {**init["flags"]}
        for r in reqs:
            if r["kind"] == "item":
                init["inventory"][r["item_id"]] = r["quantity"]
            elif r["kind"] == "flag":
                init["flags"][r["token_id"]] = r["value"]
            elif r["kind"] == "counter":
                init["counters"][r["token_id"]] = max(init["counters"].get(r["token_id"], 0), r["minimum"])
        init["location_id"] = action["start_location_id"]
        return RouteState(self.tables, self.profile["policies"], init)

    def do(self, state, action):
        step = {"kind": "action", "action_id": action["id"],
                "modeled_seconds": action["duration"]["expected_seconds"]}
        if "planned_outcome" in action:
            step["planned_outcome"] = action["planned_outcome"]
        return state.apply(step, action["id"])

    def use(self, state, reward_id, instance, skill, amount):
        return state.apply({"kind": "reward_use", "reward_id": reward_id,
                            "instance_id": reward_id + ".instance." + str(instance),
                            "skill_id": skill, "gain_xp_tenths": amount,
                            "overrides_observed_skill_restriction": False})

    def test_package_registry_matches_existing_catalog_records(self):
        registry = read_json(ROOT / "data/raw/build-242/reward-registry.json")
        entries = {e["id"]: e for e in registry["entries"]}
        for key, (producer, reward_id, quantity, amount, level) in PACKAGES.items():
            with self.subTest(package=key):
                row = entries[key]
                self.assertEqual(row["status"], "collected")
                self.assertEqual(row["delivery"], "completion")
                self.assertEqual(row["producer_action_id"], producer)
                self.assertEqual(row["package"]["quantity"], quantity)
                self.assertEqual(row["package"]["minimum_level"], level)
                self.assertTrue(row["package"]["retainable"])
                reward = self.tables["xp_rewards"][reward_id]
                self.assertEqual(reward["amount"]["xp_tenths"], amount)
                self.assertEqual(reward["minimum_level"], level)
                self.assertIn({"kind":"xp_reward", "reward_id":reward_id, "quantity":quantity},
                              self.tables["actions"][producer]["effects"])

    def test_completion_route_grants_lamps_once(self):
        for key, (producer, reward_id, quantity, _amount, _level) in PACKAGES.items():
            with self.subTest(package=key):
                action = self.tables["actions"][producer]
                completed = self.do(self.seeded(action), action)
                held = [r for r in completed.snapshot()["held_rewards"] if r["reward_id"] == reward_id]
                self.assertEqual(len(held), quantity)
                with self.assertRaises(DataError):
                    self.do(completed, action)

    def test_missing_quest_requirements_block_reward(self):
        for key, (producer, _rid, _n, _amount, _level) in PACKAGES.items():
            with self.subTest(package=key):
                action = self.tables["actions"][producer]
                with self.assertRaises(DataError):
                    self.do(self.seeded(action, prerequisites=False), action)

    def test_two_client_lamps_can_be_used_separately(self):
        producer, reward, _n, amount, _level = PACKAGES["review.quest.client_of_kourend.xp_package"]
        action = self.tables["actions"][producer]
        state = self.do(self.seeded(action), action)
        base = state.snapshot()["xp_tenths"]
        state = self.use(state, reward, 1, "skill.herblore", amount)
        self.assertEqual(len([r for r in state.snapshot()["held_rewards"] if r["reward_id"] == reward]), 1)
        state = self.use(state, reward, 2, "skill.farming", amount)
        self.assertEqual(state.snapshot()["xp_tenths"]["skill.herblore"] - base["skill.herblore"], amount)
        self.assertEqual(state.snapshot()["xp_tenths"]["skill.farming"] - base["skill.farming"], amount)
        self.assertFalse([r for r in state.snapshot()["held_rewards"] if r["reward_id"] == reward])

    def test_dream_mentor_lamp_is_one_physical_reward(self):
        producer, reward, _n, amount, _level = PACKAGES["review.quest.dream_mentor.xp_package"]
        action = self.tables["actions"][producer]
        self.assertEqual(sum(e["quantity"] for e in action["effects"]
                             if e["kind"] == "xp_reward" and e["reward_id"] == reward), 1)
        state = self.do(self.seeded(action), action)
        self.assertEqual(len([r for r in state.snapshot()["held_rewards"] if r["reward_id"] == reward]), 1)
        with self.assertRaises(DataError):
            self.use(state, reward, 1, "skill.attack", amount)
        with self.assertRaises(DataError):
            self.use(state, reward, 1, "skill.prayer", amount)
        state = self.use(state, reward, 1, "skill.magic", amount)
        self.assertFalse([r for r in state.snapshot()["held_rewards"] if r["reward_id"] == reward])
        registry = read_json(ROOT / "data/raw/build-242/reward-registry.json")
        older = next(e for e in registry["entries"] if e["id"] == "review.quest.dream_mentor.dreamy_lamp")
        self.assertEqual(older["status"], "collected")
        self.assertEqual(older["producer_action_id"], producer)

    def test_brain_robbery_blessed_lamp_use_and_retention(self):
        producer, reward, _n, amount, _level = PACKAGES["review.quest.the_great_brain_robbery.xp_package"]
        action = self.tables["actions"][producer]
        state = self.do(self.seeded(action), action)
        initial = state.snapshot()["xp_tenths"]["skill.crafting"]
        state = self.use(state, reward, 1, "skill.crafting", amount)
        self.assertEqual(state.snapshot()["xp_tenths"]["skill.crafting"], initial + amount)
        with self.assertRaises(DataError):
            self.use(state, reward, 1, "skill.crafting", amount)

    def test_raw_review_link_matches_registry(self):
        coverage = read_json(ROOT / "data/coverage/build-242.json")
        review = read_json(ROOT / coverage["quest_collection"]["existing_lamp_package_reconciliation_review"])
        self.assertEqual(review["status"], "collected_draft_not_independently_reviewed")
        self.assertEqual(set(review["packages"]), set(PACKAGES))


if __name__ == "__main__":
    unittest.main()
