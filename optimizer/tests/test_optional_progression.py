"""Build 242 coverage and an isolated diary claim fixture."""

from pathlib import Path
import unittest

from quest_optimizer.bounded_search import solve_bounded
from quest_optimizer.data import Contracts, DataError, load_catalog, read_json
from quest_optimizer.replay import verify_solution
from quest_optimizer.semantics import CatalogValidator
from quest_optimizer.transitions import RouteState


ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data"
COVERAGE = DATA / "coverage/build-242"
RAW = DATA / "raw/build-242"
EXAMPLE = ROOT / "examples/synthetic"


class OptionalProgressionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.contracts = Contracts(ROOT / "schemas")
        cls.catalog = load_catalog(DATA / "manifest.json", cls.contracts)
        cls.review = read_json(RAW / "optional-progression-review.json")

    def test_diary_observations_cover_every_tracker_and_claim_in_the_ledger(self):
        index = read_json(RAW / "diaries/index.json")
        tiers = {
            row["id"]: row
            for file in index["files"]
            for row in read_json(RAW / "diaries" / file)
        }
        sources = {source["id"]: source for source in self.catalog["sources"]}
        self.assertEqual(index["source_revision"], sources["source.quest_helper.diaries"]["revision"])
        self.assertTrue(set(self.review["source_ids"]) <= sources.keys())
        ledger = read_json(COVERAGE / "diaries.json")
        self.assertCountEqual(tiers, [tier["id"] for region in ledger["regions"] for tier in region["tiers"]])
        for region in ledger["regions"]:
            previous_claim = None
            for tier in region["tiers"]:
                observation = tiers[tier["id"]]
                self.assertCountEqual([task["id"] for task in observation["tasks"]], [task["id"] for task in tier["tasks"]])
                for task in observation["tasks"]:
                    self.assertTrue(task["helper_symbols"], task["id"])
                    self.assertTrue(set(task["helper_symbols"]) <= observation["helper_definitions"].keys(), task["id"])
                claim = observation["claim"]
                self.assertEqual(claim["id"], tier["reward_claim_id"])
                self.assertEqual(claim["requires_tier_id"], tier["id"])
                self.assertEqual(claim["previous_tier_claim_id"], previous_claim)
                self.assertTrue(claim["helper_npc_candidates"])
                self.assertEqual(len(claim["lamps"]), 1)
                previous_claim = claim["id"]
        easy = tiers["diary.lumbridge_draynor.easy"]
        self.assertIn(
            {"kind": "skill", "skill_id": "skill.slayer", "minimum_level": 7, "boostable": True},
            easy["tasks"][1]["panel_requirement_candidates"],
        )
        self.assertIn("choppedLogs", easy["helper_definitions"])
        self.assertEqual(
            easy["helper_definitions"]["choppedLogs"][0]["helper_calls"][0]["operation"],
            "setInvalidateRequirement",
        )

    def test_optional_content_has_review_records_and_stays_out_of_quest_goals(self):
        journal = read_json(COVERAGE / "journal.json")
        miniquests = {row["id"]: row["status"] for row in journal if row["kind"] == "miniquest"}
        self.assertCountEqual(miniquests, [row["id"] for row in self.review["miniquests"]])
        seed = read_json(DATA / "profiles/main-baseline.json")
        self.assertTrue(all(goal.startswith("quest.") for goal in seed["goal_action_ids"]))
        self.assertEqual(
            {activity_id for activity_id, status in miniquests.items() if status == "collected"},
            {activity["id"] for activity in self.catalog["activities"] if activity["kind"] == "miniquest"},
        )
        self.assertTrue(all(
            claim["activity_id"] in miniquests for claim in self.review["miniquest_reward_stages"]
        ))

    def test_essence_mine_overlap_requires_the_actual_teleport(self):
        actions = {action["id"]: action for action in self.catalog["actions"]}
        previous = "miniquest.enter_the_abyss.collect_orb"
        for overlap in self.review["diary_review"]["essence_mine_overlaps"]:
            standalone = actions[overlap["task_id"]]
            shared = actions[overlap["miniquest_action_id"]]
            token = overlap["completion_flag_id"]
            effect = {"kind": "flag", "token_id": token, "value": True}
            self.assertEqual(standalone["kind"], "diary_task")
            self.assertEqual(standalone["start_location_id"], shared["start_location_id"])
            self.assertEqual(standalone["effects"], [effect])
            self.assertIn(effect, shared["effects"])
            self.assertIn(
                {"kind": "flag", "token_id": token, "value": False},
                standalone["requirements"]["requirements"],
            )
            self.assertIn(
                {"kind": "action_completed", "action_id": previous},
                shared["requirements"]["requirements"],
            )
            self.assertNotIn(effect, actions["quest.rune_mysteries.complete"]["effects"])
            self.assertNotIn(effect, actions["miniquest.enter_the_abyss.collect_orb"]["effects"])
            previous = shared["id"]
        completion = actions["miniquest.enter_the_abyss.complete"]
        self.assertIn({"kind": "xp", "skill_id": "skill.runecraft", "xp_tenths": 10000}, completion["effects"])
        self.assertTrue(all(effect["kind"] != "xp" for effect in actions[previous]["effects"]))
        self.assertIn(
            {"kind": "policy", "name": "allow_wilderness_travel", "value": True},
            actions["miniquest.enter_the_abyss.start"]["requirements"]["requirements"],
        )

    def test_stronghold_funds_the_starter_and_records_both_diary_tasks(self):
        profile = read_json(ROOT / "examples/build-242/stronghold-security-profile.json")
        review = read_json(RAW / "account-security.json")["stronghold"]
        validator = CatalogValidator(self.catalog, self.contracts)
        solution, _ = solve_bounded(validator, profile, beam_width=96, max_expansions=10000)
        final = verify_solution(solution, profile, validator)["final_state"]
        self.assertEqual(final["inventory"]["item.coins"], review["total_coins"])
        self.assertEqual(final["counters"], profile["initial_state"]["counters"])
        self.assertEqual(solution["manual_training_xp_tenths_by_skill"], {"skill.prayer": 503390})
        actions = [step["action_id"] for step in solution["steps"] if step["kind"] == "action"]
        easy, medium = [row["task_id"] for row in review["diary_links"]]
        self.assertLess(actions.index(easy), actions.index("stronghold.security.claim_famine"))
        self.assertLess(actions.index("stronghold.security.complete"), actions.index(medium))
        self.assertTrue(final["flags"]["flag." + easy])
        self.assertTrue(final["flags"]["flag." + medium])
        self.assertTrue(final["flags"]["flag.count_check.lamp_received"])
        entrance = "location.barbarian_village.stronghold_entrance"
        self.assertTrue(all(edge["mode"] == "walk" for edge in self.catalog["travel_edges"]
                            if edge["to_location_id"] == entrance))

    def test_count_check_claim_obeys_security_and_pays_xp_at_use(self):
        profile = read_json(ROOT / "examples/build-242/stronghold-security-profile.json")
        validator = CatalogValidator(self.catalog, self.contracts)
        action = validator.tables["actions"]["claim.count_check.lamp"]
        initial = profile["initial_state"]
        initial["location_id"] = action["start_location_id"]
        claim = {"kind": "action", "action_id": action["id"], "modeled_seconds": action["duration"]["expected_seconds"]}
        for policy in ("has_jagex_account", "has_bank_pin", "has_authenticator"):
            with self.subTest(policy=policy):
                policies = {**profile["policies"], policy: False}
                with self.assertRaisesRegex(DataError, "reward claim"):
                    RouteState(validator.tables, policies, initial).apply(claim)
        state = RouteState(validator.tables, profile["policies"], initial).apply(claim)
        with self.assertRaisesRegex(DataError, "repeat limit"):
            state.apply(claim)
        skill = "skill.crafting"
        reward = "reward.count_check.lamp"
        instance = reward + ".instance.1"
        self.assertEqual(state.reward_pick(instance, skill, "lamp"), 100)
        after = state.thresholds[skill][42]
        trained = state.apply({"kind": "training", "skill_id": skill, "before_xp_tenths": 0,
                               "gain_xp_tenths": after, "after_xp_tenths": after,
                               "resume_location_id": state.location, "required_by": [skill]})
        self.assertEqual(trained.reward_pick(instance, skill, "lamp"), 4300)
        spent = trained.apply({"kind": "reward_use", "reward_id": reward, "instance_id": instance,
                               "skill_id": skill, "gain_xp_tenths": 4300,
                               "overrides_observed_skill_restriction": False})
        self.assertEqual(spent.xp[skill], after + 4300)
        self.assertFalse(spent.held)
        initial["flags"]["flag.count_check.lamp_received"] = True
        with self.assertRaisesRegex(DataError, "reward claim"):
            RouteState(validator.tables, profile["policies"], initial).apply(claim)

    def test_solver_uses_count_check_lamp_to_avoid_manual_magic_xp(self):
        profile = read_json(ROOT / "examples/build-242/lost-city-combat-profile.json")
        validator = CatalogValidator(self.catalog, self.contracts)
        action = validator.tables["actions"]["quest.lost_city.get_dungeon_axe"]
        reward = "reward.count_check.lamp"
        profile["goal_action_ids"] = [action["id"]]
        initial = profile["initial_state"]
        initial.update(
            location_id=action["start_location_id"],
            completed_action_ids=["quest.lost_city.descend_entrana", "claim.count_check.lamp"],
            inventory={cost["item_id"]: cost["quantity"] for cost in action["consumes"]},
            held_rewards=[{"reward_id": reward, "instance_id": reward + ".instance.1", "remaining_picks": 1}],
        )
        initial["inventory"]["item.lumbridge_teleport_tablet"] = 1
        initial["flags"]["flag.count_check.lamp_received"] = True
        initial["xp_tenths"]["skill.magic"] -= 1200
        solution, _ = solve_bounded(validator, profile)
        verify_solution(solution, profile, validator)
        [use] = [step for step in solution["steps"] if step["kind"] == "reward_use"]
        self.assertEqual((use["reward_id"], use["skill_id"], use["gain_xp_tenths"]), (reward, "skill.magic", 1200))
        self.assertEqual(solution["objective"]["counted_manual_training_xp_tenths"], 0)


class DiaryDetourFixtureTests(unittest.TestCase):
    """Use synthetic values until a complete diary tier is reviewed for admission."""

    def setUp(self):
        self.contracts = Contracts(ROOT / "schemas")
        catalog = load_catalog(EXAMPLE / "manifest.json", self.contracts)
        [quest] = catalog["actions"]
        evidence = quest["evidence"]
        self.task = {
            **quest, "id": "diary.fixture.task", "name": "Finish one diary task",
            "activity_id": "diary.fixture", "kind": "diary_task",
            "requirements": {"kind": "all", "requirements": []}, "effects": [],
        }
        self.tier = {
            **self.task, "id": "diary.fixture.complete", "name": "Record completed tier", "kind": "other",
            "requirements": {"kind": "action_completed", "action_id": self.task["id"]},
        }
        self.lamp = {
            "id": "reward.fixture.diary_lamp", "name": "Diary lamp", "kind": "other_lamp",
            "eligible_skills": ["skill.example"], "minimum_level": 1, "selection_count": 1,
            "distinct_skills": False, "retainable": True, "amount": {"kind": "fixed", "xp_tenths": 1000},
            "observed_restrictions": "Synthetic lamp for the example skill.", "evidence": evidence,
        }
        self.claim = {
            **self.task, "id": "claim.diary.fixture", "name": "Claim from taskmaster", "kind": "reward_claim",
            "requirements": {"kind": "action_completed", "action_id": self.tier["id"]},
            "effects": [{"kind": "xp_reward", "reward_id": self.lamp["id"], "quantity": 1}],
        }
        catalog["activities"].append({
            "id": "diary.fixture", "name": "Example diary tier", "kind": "diary_tier",
            "parent_activity_id": None, "completion_action_ids": [self.tier["id"]], "evidence": evidence,
        })
        catalog["xp_rewards"].append(self.lamp)
        catalog["actions"].extend([self.task, self.tier, self.claim])
        self.contracts.validate("catalog", catalog)
        self.validator = CatalogValidator(catalog, self.contracts)
        self.validator.validate_catalog()
        self.profile = read_json(EXAMPLE / "profile.json")
        self.solution = read_json(EXAMPLE / "solution.json")

    def test_optional_diary_claim_can_replace_manual_xp(self):
        self.validator.validate_solution(self.solution, self.profile)
        [goal] = self.profile["goal_action_ids"]
        actions = [self.task, self.tier, self.claim]
        detour = [
            {"step_id": f"step.diary_{index}", "kind": "action", "action_id": row["id"],
             "modeled_seconds": 60, "explanation": row["name"]}
            for index, row in enumerate(actions)
        ]
        detour.append({
            "step_id": "step.diary_lamp", "kind": "reward_use", "reward_id": self.lamp["id"],
            "instance_id": self.lamp["id"] + ".instance.1", "skill_id": "skill.example",
            "gain_xp_tenths": 1000, "overrides_observed_skill_restriction": False,
            "explanation": "Use the claimed lamp to meet the quest's level gate.",
        })
        self.solution["steps"][:1] = detour
        self.solution["manual_training_xp_tenths_by_skill"] = {}
        self.solution["objective"].update(manual_training_xp_tenths=0, modeled_non_training_seconds=240)
        self.solution["final_state"].update(
            completed_action_ids=[row["id"] for row in actions] + [goal], modeled_elapsed_seconds=240,
        )
        self.contracts.validate("solution", self.solution)
        self.validator.validate_solution(self.solution, self.profile)

        self.solution["steps"][1], self.solution["steps"][2] = self.solution["steps"][2], self.solution["steps"][1]
        with self.assertRaisesRegex(DataError, "claim precedes a required completed action"):
            self.validator.validate_solution(self.solution, self.profile)

    def test_bounded_search_finds_the_diary_detour(self):
        with_claim, _ = solve_bounded(self.validator, self.profile)
        baseline, _ = solve_bounded(self.validator, self.profile, excluded_actions=(self.claim["id"],))
        self.assertEqual(with_claim["manual_training_xp_tenths_by_skill"], {})
        self.assertEqual(baseline["manual_training_xp_tenths_by_skill"], {"skill.example": 1000})
        self.assertEqual([step.get("action_id") or step["kind"] for step in with_claim["steps"]], [
            self.task["id"], self.tier["id"], self.claim["id"], "reward_use", "action.example",
        ])
