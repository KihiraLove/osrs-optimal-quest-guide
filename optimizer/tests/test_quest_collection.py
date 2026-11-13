"""Checks against the independent build 242 journal and source observations."""

from collections import defaultdict
from pathlib import Path
import unittest

from quest_optimizer.bounded_search import solve_bounded
from quest_optimizer.data import Contracts, DataError, load_catalog, read_json
from quest_optimizer.replay import verify_solution
from quest_optimizer.semantics import CatalogValidator
from quest_optimizer.transitions import RouteState


ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data"
RAW = DATA / "raw/build-242"


class QuestCollectionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.contracts = Contracts(ROOT / "schemas")
        cls.catalog = load_catalog(DATA / "manifest.json", cls.contracts)
        cls.journal = read_json(DATA / "coverage/build-242/journal.json")
        cls.observation_index = read_json(RAW / "quest-helper/index.json")
        cls.observations = defaultdict(list)
        for file in cls.observation_index["files"]:
            for observation in read_json(RAW / "quest-helper" / file):
                cls.observations[observation["activity_id"]].append(observation)
        cls.rfd = read_json(RAW / "recipe-for-disaster-review.json")

    def test_inventory_distinguishes_observed_and_collected_quests(self):
        journal_ids = {row["id"] for row in self.journal}
        missing = set(self.observation_index["missing_helper_activity_ids"])
        self.assertEqual(len(self.observations), self.observation_index["observed_activity_count"])
        self.assertEqual(journal_ids - self.observations.keys(), missing | {"quest.recipe_for_disaster"})
        self.assertEqual(
            {row["id"] for row in self.journal if row["status"] == "collected"},
            {row["id"] for row in self.catalog["activities"] if row["kind"] in ("quest", "subquest", "miniquest")},
        )
        variants = {row["helper_symbol"] for row in self.observations["quest.shield_of_arrav"]}
        self.assertEqual(variants, {"SHIELD_OF_ARRAV_BLACK_ARM_GANG", "SHIELD_OF_ARRAV_PHOENIX_GANG"})

    def test_plague_city_unlocks_travel_separately_and_biohazard_preserves_samples(self):
        validator = CatalogValidator(self.catalog, self.contracts)
        baseline = read_json(DATA / "profiles/main-baseline.json")
        initial = baseline["initial_state"]
        initial["location_id"] = "location.ardougne.edmond"
        initial["inventory"].update({
            "item.coins": 30,
            "item.dwellberries": 1,
            "item.rope": 1,
            "item.bucket_of_milk": 1,
            "item.chocolate_dust": 1,
            "item.snape_grass": 1,
            "item.law_rune": 2,
        })
        initial["xp_tenths"]["skill.magic"] = 1200000
        policies = baseline["policies"]
        state = RouteState(validator.tables, policies, initial)

        def apply_ids(state, ids):
            for record_id in ids:
                travel = record_id.startswith("travel.")
                record = validator.tables["travel_edges" if travel else "actions"][record_id]
                step = {
                    "kind": "travel" if travel else "action",
                    "edge_id" if travel else "action_id": record_id,
                    "modeled_seconds": record["duration"]["expected_seconds"],
                }
                if "planned_outcome" in record:
                    step["planned_outcome"] = record["planned_outcome"]
                state = state.apply(step, record_id)
            return state

        state = apply_ids(state, (
            "quest.plague_city.start",
            "quest.plague_city.make_gas_mask",
            "quest.plague_city.dig_into_sewer",
            "quest.plague_city.open_sewer_grille",
            "quest.plague_city.find_elena",
            "travel.walk.west_ardougne.plague_house.back",
            "travel.walk.west_ardougne.bravek.out",
            "quest.plague_city.obtain_warrant",
            "travel.walk.west_ardougne.bravek.back",
            "travel.walk.west_ardougne.plague_house.out",
            "quest.plague_city.rescue_elena",
            "travel.walk.west_ardougne.plague_house.back",
            "quest.plague_city.leave_west_ardougne",
            "quest.plague_city.complete",
        ))
        self.assertEqual(state.snapshot()["inventory"]["item.ardougne_teleport_scroll"], 1)
        varrock = {**state.snapshot(), "location_id": "location.varrock.square"}
        with self.assertRaisesRegex(DataError, "flag"):
            apply_ids(RouteState(validator.tables, policies, varrock), ("travel.spell.varrock.ardougne",))

        state = apply_ids(state, (
            "quest.plague_city.read_ardougne_teleport_scroll",
            "travel.walk.ardougne.elena.out",
            "quest.biohazard.start",
            "travel.walk.ardougne.jerico.out",
            "quest.biohazard.collect_birds",
            "travel.walk.ardougne.biohazard_watchtower.out",
        ))
        with self.assertRaisesRegex(DataError, "flag"):
            apply_ids(state, ("travel.walk.ardougne.main_gate.out",))
        state = apply_ids(state, (
            "quest.biohazard.distract_watchtower",
            "travel.walk.ardougne.omart.out",
            "quest.biohazard.cross_wall",
            "travel.walk.west_ardougne.mourner_hq.out",
            "quest.biohazard.spoil_stew",
            "travel.walk.west_ardougne.sarah.out",
            "quest.biohazard.collect_medical_gown",
            "travel.walk.west_ardougne.sarah.back",
            "quest.biohazard.recover_distillator",
            "travel.walk.west_ardougne.mourner_hq.back",
            "quest.biohazard.leave_west_ardougne",
            "travel.walk.ardougne.elena_wall.out",
            "quest.biohazard.reach_chemist",
            "quest.biohazard.smuggle_reagents",
        ))
        with self.assertRaisesRegex(DataError, "required"):
            apply_ids(state, ("quest.biohazard.test_sample",))
        state = apply_ids(state, (
            "travel.walk.varrock.asyff.out",
            "quest.biohazard.claim_priest_gown",
            "travel.walk.varrock.asyff.back",
            "quest.biohazard.test_sample",
            "travel.walk.varrock.guidor.out",
            "travel.walk.varrock.aubury.back",
            "travel.spell.varrock.ardougne",
            "travel.walk.ardougne.edmond.out",
            "travel.walk.ardougne.elena.out",
            "quest.biohazard.report_to_elena",
            "travel.walk.ardougne.elena_wall.back",
            "travel.walk.ardougne.castle.out",
            "travel.walk.ardougne.king_lathas.out",
            "quest.biohazard.complete",
            "travel.walk.ardougne.king_lathas.back",
            "travel.walk.ardougne.castle.back",
            "travel.walk.ardougne.omart.back",
            "travel.walk.ardougne.main_gate.out",
        ))
        final = state.snapshot()
        self.assertEqual(final["location_id"], "location.west_ardougne.manhole")
        self.assertEqual(final["counters"]["token.quest_points"], 5)
        self.assertEqual(final["xp_tenths"]["skill.mining"], 24250)
        self.assertEqual(final["xp_tenths"]["skill.thieving"], 12500)
        self.assertEqual(final["xp_tenths"]["skill.magic"], 1200610)
        self.assertNotIn("item.coins", final["inventory"])
        self.assertNotIn("item.ardougne_teleport_scroll", final["inventory"])
        self.assertTrue(final["flags"]["unlock.ardougne_combat_training_camp"])

    def test_morytania_essence_loads_and_lumbridge_guide_gates(self):
        validator = CatalogValidator(self.catalog, self.contracts)
        profile = read_json(DATA / "profiles/main-baseline.json")
        initial = profile["initial_state"]
        initial["location_id"] = "location.varrock.east_bank"
        banked = "token.bank.priest_in_peril_essence"
        initial["counters"][banked] = 50

        def apply_action(state, action_id):
            record = validator.tables["actions"][action_id]
            return state.apply({
                "kind": "action",
                "action_id": action_id,
                "modeled_seconds": record["duration"]["expected_seconds"],
            })

        def route_state(snapshot):
            return RouteState(validator.tables, profile["policies"], snapshot)

        first = "supply.varrock.withdraw_priest_in_peril_essence"
        second = "supply.varrock.withdraw_priest_in_peril_second_load"
        deliver = "quest.priest_in_peril.deliver_first_essence"
        complete = "quest.priest_in_peril.complete"
        state = apply_action(route_state(initial), first)
        self.assertEqual(state.snapshot()["inventory"]["item.pure_essence"], 25)
        self.assertEqual(state.snapshot()["counters"][banked], 25)
        with self.assertRaisesRegex(DataError, "required completed action"):
            apply_action(state, second)

        drezel = state.snapshot()
        drezel["location_id"] = "location.paterdomus.drezel"
        drezel["completed_action_ids"].append("quest.priest_in_peril.free_drezel")
        with self.assertRaisesRegex(DataError, "required"):
            apply_action(route_state(drezel), complete)
        first_delivery = apply_action(route_state(drezel), deliver).snapshot()
        self.assertNotIn("unlock.morytania", first_delivery["flags"])
        second_load = {**first_delivery, "location_id": initial["location_id"]}
        loaded = apply_action(route_state(second_load), second).snapshot()
        loaded["location_id"] = drezel["location_id"]
        finished = apply_action(route_state(loaded), complete).snapshot()
        self.assertEqual(finished["xp_tenths"]["skill.prayer"], 14060)
        self.assertNotIn("item.pure_essence", finished["inventory"])
        self.assertTrue(finished["flags"]["unlock.morytania"])

        inspect = "rfd.freeing_the_lumbridge_guide.inspect"
        guide = route_state(initial).snapshot()
        guide["location_id"] = "location.rfd.frozen_lumbridge_guide"
        guide["completed_action_ids"] = [
            "rfd.another_cooks_quest.complete", "quest.big_chompy_bird_hunting.complete",
            "quest.biohazard.complete", "quest.demon_slayer.complete", "quest.murder_mystery.complete",
            "quest.witchs_house.complete",
        ]
        guide["xp_tenths"]["skill.cooking"] = 372240
        with self.assertRaisesRegex(DataError, "required completed action"):
            apply_action(route_state(guide), inspect)
        guide["completed_action_ids"].append("quest.nature_spirit.complete")
        guide["xp_tenths"]["skill.cooking"] -= 1
        with self.assertRaisesRegex(DataError, "skill|threshold"):
            apply_action(route_state(guide), inspect)
        guide["xp_tenths"]["skill.cooking"] += 1
        self.assertIn(inspect, apply_action(route_state(guide), inspect).completed)

    def test_evil_dave_replays_both_pet_forms_and_requires_an_approved_stew(self):
        quest = "rfd.freeing_evil_dave"
        validator = CatalogValidator(self.catalog, self.contracts)
        for cat, hunt, hell_form, gp in (
            ("item.pet_kitten", "hunt_with_kitten", "item.hell_kitten", 1362),
            ("item.adult_cat", "hunt_with_adult_cat", "item.hellcat", 1320),
        ):
            with self.subTest(cat=cat):
                profile = read_json(ROOT / "examples/build-242/rfd-evil-dave-profile.json")
                initial = profile["initial_state"]
                del initial["inventory"]["item.pet_kitten"]
                initial["inventory"].update({cat: 1, "item.coins": gp})
                if cat == "item.pet_kitten":
                    solution = read_json(ROOT / "examples/build-242/rfd-evil-dave-solution.json")
                else:
                    solution, _ = solve_bounded(validator, profile, beam_width=96, max_expansions=30000)
                report = verify_solution(solution, profile, validator)
                final = report["final_state"]
                self.assertEqual(report["manual_training_xp_tenths_by_skill"], {})
                self.assertEqual(final["counters"], {"token.quest_points": 10})
                self.assertEqual(final["inventory"], {hell_form: 1})
                self.assertEqual(final["xp_tenths"]["skill.cooking"] - initial["xp_tenths"]["skill.cooking"], 70000)
                self.assertEqual(final["xp_tenths"]["skill.magic"] - initial["xp_tenths"]["skill.magic"], 410)
                self.assertTrue(final["flags"]["unlock.spicy_stew_boosts"])
                self.assertTrue(final["flags"]["unlock.hell_rat_behemoths"])

                steps = solution["steps"]
                [hunt_step] = [step for step in steps if "planned_outcome" in step]
                self.assertEqual(hunt_step["action_id"], f"{quest}.{hunt}")
                self.assertIn("travel.spell.doris_cellar.lumbridge", {step.get("edge_id") for step in steps})
                without_tasting = {**solution, "steps": [
                    step for step in steps if step.get("action_id") != f"{quest}.confirm_recipe"
                ]}
                with self.assertRaisesRegex(DataError, "required completed action"):
                    verify_solution(without_tasting, profile, validator)

    def test_shadow_of_the_storm_replays_darklight_and_the_immediate_combat_choice(self):
        quest = "quest.shadow_of_the_storm"
        profile = read_json(ROOT / "examples/build-242/shadow-of-the-storm-profile.json")
        validator = CatalogValidator(self.catalog, self.contracts)
        solution, _ = solve_bounded(validator, profile, beam_width=128, max_expansions=40000)
        report = verify_solution(solution, profile, validator)
        final = report["final_state"]
        self.assertEqual(report["manual_training_xp_tenths_by_skill"], {})
        self.assertEqual(final["counters"]["token.quest_points"], 6)
        self.assertEqual(final["held_rewards"], [])
        self.assertEqual(final["inventory"]["item.darklight"], 1)
        self.assertEqual(final["inventory"]["item.demonic_sigil"], 1)
        self.assertNotIn("item.dyed_silverlight", final["inventory"])
        self.assertEqual(final["action_counts"]["supply.uzer.gather_black_mushroom"], 2)

        steps = solution["steps"]
        complete, choice = steps[-2:]
        self.assertEqual(complete["action_id"], f"{quest}.complete")
        self.assertEqual(choice["reward_id"], "reward.shadow_of_the_storm.combat_choice")
        self.assertEqual(choice["gain_xp_tenths"], 100000)
        [fight] = [step for step in steps if "planned_outcome" in step]
        self.assertEqual(fight["action_id"], f"{quest}.defeat_agrith_naar")

        state = RouteState(validator.tables, profile["policies"], profile["initial_state"])
        for step in steps[:-1]:
            state = state.apply(step)
        with self.assertRaisesRegex(DataError, "resolve immediate reward before proceeding"):
            state.apply({"kind": "wait", "modeled_seconds": 1})
        with self.assertRaisesRegex(DataError, "ineligible"):
            state.apply({**choice, "skill_id": "skill.prayer"})
        ranged = state.apply({**choice, "skill_id": "skill.ranged"}).snapshot()
        self.assertEqual(ranged["xp_tenths"]["skill.ranged"], 100000)

    def test_the_golem_replays_reprogramming_gems_and_carpet_unlock(self):
        profile = read_json(ROOT / "examples/build-242/the-golem-profile.json")
        validator = CatalogValidator(self.catalog, self.contracts)
        solution = read_json(ROOT / "examples/build-242/the-golem-solution.json")
        report = verify_solution(solution, profile, validator)
        final = report["final_state"]
        self.assertEqual(report["manual_training_xp_tenths_by_skill"], {})
        self.assertEqual(final["counters"]["token.quest_points"], 2)
        for skill in ("skill.crafting", "skill.thieving"):
            self.assertEqual(final["xp_tenths"][skill] - profile["initial_state"]["xp_tenths"][skill], 10000)
        self.assertEqual(final["inventory"]["item.strange_implement"], 1)
        self.assertEqual(final["inventory"]["item.coins"], 200)
        self.assertNotIn("item.golem_program", final["inventory"])

        steps = solution["steps"]
        gem_claim = next(step for step in steps if step.get("action_id") == "claim.the_golem.throne_gems")
        state = RouteState(validator.tables, profile["policies"], profile["initial_state"])
        for step in steps[:steps.index(gem_claim)]:
            state = state.apply(step)
        before_claim = state.snapshot()
        self.assertEqual(before_claim["counters"]["token.quest_points"], 1)
        inventory = state.apply(gem_claim).snapshot()["inventory"]
        for gem in ("item.ruby", "item.emerald", "item.sapphire"):
            self.assertNotIn(gem, before_claim["inventory"])
            self.assertEqual(inventory[gem], 2)
        with self.assertRaisesRegex(DataError, "repeat limit"):
            state.apply(gem_claim).apply(gem_claim)

        for direction in ("shantay.uzer", "uzer.shantay"):
            edge_id = f"travel.carpet.{direction}"
            edge = validator.tables["travel_edges"][edge_id]
            ride = {"kind": "travel", "edge_id": edge_id, "modeled_seconds": edge["duration"]["expected_seconds"]}
            origin = edge["from_location_id"]
            locked = {**before_claim, "location_id": origin}
            with self.assertRaisesRegex(DataError, "flag or counter threshold has not been reached"):
                RouteState(validator.tables, profile["policies"], locked).apply(ride)
            unlocked = {**final, "location_id": origin}
            arrival = RouteState(validator.tables, profile["policies"], unlocked).apply(ride).snapshot()
            self.assertEqual(arrival["location_id"], edge["to_location_id"])
            self.assertNotIn("item.coins", arrival["inventory"])

    def test_demon_slayer_replays_keys_and_silverlight_without_the_separate_claim(self):
        quest = "quest.demon_slayer"
        profile = read_json(ROOT / "examples/build-242/demon-slayer-profile.json")
        validator = CatalogValidator(self.catalog, self.contracts)
        solution, _ = solve_bounded(validator, profile, beam_width=96)
        report = verify_solution(solution, profile, validator)
        self.assertEqual(report["manual_training_xp_tenths_by_skill"], {})
        inventory = report["final_state"]["inventory"]
        self.assertEqual(inventory["item.silverlight"], 1)
        self.assertFalse(inventory.keys() - {"item.silverlight", "item.bucket", "item.bucket_of_water"})
        self.assertEqual(report["final_state"]["counters"]["token.quest_points"], 4)
        self.assertEqual(report["final_state"]["held_rewards"], [])

        state = RouteState(validator.tables, profile["policies"], profile["initial_state"])
        for step in solution["steps"]:
            if step.get("action_id") == f"{quest}.get_traiborn_key":
                snapshot = state.snapshot()
                self.assertEqual(snapshot["inventory"]["item.bones"], 25)
                short = {**snapshot, "inventory": {**snapshot["inventory"], "item.bones": 24}}
                with self.assertRaisesRegex(DataError, "consumes 25 of 'item.bones'"):
                    RouteState(validator.tables, profile["policies"], short).apply(step)
            state = state.apply(step)
            if step.get("action_id") == f"{quest}.receive_silverlight":
                snapshot = state.snapshot()
                inventory = snapshot["inventory"]
                self.assertEqual(inventory["item.silverlight"], 1)
                self.assertFalse(inventory.keys() - {"item.silverlight", "item.bucket", "item.bucket_of_water"})
                self.assertEqual(snapshot["counters"]["token.quest_points"], 1)

        edges = {step["edge_id"] for step in solution["steps"] if step["kind"] == "travel"}
        self.assertTrue({
            "travel.walk.varrock.sewer_manhole.out",
            "travel.walk.varrock.sewer_manhole.back",
            "travel.walk.wizards_tower.traiborn_stairs.out",
        } <= edges)

    def test_gertrudes_cat_replays_the_quest_bundle_and_pet_reward(self):
        quest = "quest.gertrudes_cat"
        profile = read_json(ROOT / "examples/build-242/gertrudes-cat-profile.json")
        validator = CatalogValidator(self.catalog, self.contracts)
        solution, _ = solve_bounded(validator, profile, beam_width=96)
        state = verify_solution(solution, profile, validator)["final_state"]
        self.assertEqual(solution["manual_training_xp_tenths_by_skill"], {})
        self.assertEqual(state["counters"]["token.quest_points"], 2)
        self.assertEqual(state["inventory"], {"item.chocolate_cake": 1, "item.pet_kitten": 1, "item.stew": 1})
        self.assertEqual(state["held_rewards"], [])
        self.assertTrue(state["flags"]["unlock.raise_cats"])
        [source] = self.observations[quest]
        expected_xp = profile["initial_state"]["xp_tenths"].copy()
        for effect in source["declared_xp"]["observations"]:
            expected_xp[effect["skill_id"]] += effect["xp_tenths"]
        self.assertEqual(state["xp_tenths"], expected_xp)

        steps = solution["steps"]
        edges = [step["edge_id"] for step in steps if step["kind"] == "travel"]
        self.assertEqual(edges.count("travel.walk.varrock.lumberyard_ladder.out"), 2)
        self.assertEqual(edges.count("travel.walk.varrock.lumberyard_ladder.back"), 2)
        self.assertIn("travel.walk.varrock.lumberyard_fence.out", edges)
        self.assertEqual([step["action_id"] for step in steps if "planned_outcome" in step], [
            f"{quest}.find_fluffs_kitten",
        ])

        handover = next(step for step in steps if step.get("action_id") == f"{quest}.return_fluffs_kitten")
        initial = profile["initial_state"]
        before_handover = RouteState(validator.tables, profile["policies"], initial)
        for step in steps[:steps.index(handover)]:
            before_handover = before_handover.apply(step)
        self.assertEqual(before_handover.snapshot()["inventory"], {"item.fluffs_kitten": 1})
        with_pet = {**before_handover.snapshot(), "inventory": {"item.pet_kitten": 1}}
        with self.assertRaisesRegex(DataError, "consumes 1 of 'item.fluffs_kitten'"):
            RouteState(validator.tables, profile["policies"], with_pet).apply(handover)

        without_milk = {**solution, "steps": [step for step in steps if step.get("action_id") != f"{quest}.give_milk"]}
        with self.assertRaisesRegex(DataError, "required completed action"):
            verify_solution(without_milk, profile, validator)

    def test_restless_ghost_replays_from_lumbridge_with_no_manual_xp(self):
        quest = "quest.the_restless_ghost"
        [source] = self.observations[quest]
        review = read_json(RAW / "restless-ghost-review.json")
        profile = read_json(ROOT / "examples/build-242/restless-ghost-profile.json")
        validator = CatalogValidator(self.catalog, self.contracts)
        solution, _ = solve_bounded(validator, profile, max_expansions=4000)
        verify_solution(solution, profile, validator)
        self.assertEqual(solution["manual_training_xp_tenths_by_skill"], {})
        self.assertEqual([step["action_id"] for step in solution["steps"] if step["kind"] == "action"], review["stages"])
        expected_xp = profile["initial_state"]["xp_tenths"].copy()
        for reward in source["declared_xp"]["observations"]:
            expected_xp[reward["skill_id"]] += reward["xp_tenths"]
        state = solution["final_state"]
        self.assertEqual(state["xp_tenths"], expected_xp)
        self.assertEqual(state["inventory"], {"item.ghostspeak_amulet": 1})
        self.assertEqual(state["counters"]["token.quest_points"], 1)
        ladders = {step.get("edge_id") for step in solution["steps"]}
        self.assertTrue({
            "travel.walk.wizards_tower.basement_ladder.out", "travel.walk.wizards_tower.basement_ladder.back",
        } <= ladders)

        for stage in ("get_amulet", "take_skull"):
            with self.subTest(stage=stage):
                skipped = {**solution, "steps": [
                    step for step in solution["steps"] if step.get("action_id") != f"{quest}.{stage}"
                ]}
                with self.assertRaisesRegex(DataError, r"steps\.\d+ .* required completed action"):
                    verify_solution(skipped, profile, validator)

    def test_lost_city_preparation_replays_from_lumbridge_through_entrana(self):
        profile = read_json(ROOT / "examples/build-242/lost-city-preparation-profile.json")
        validator = CatalogValidator(self.catalog, self.contracts)
        solution, _ = solve_bounded(validator, profile, max_expansions=4000)
        verify_solution(solution, profile, validator)
        self.assertEqual(solution["manual_training_xp_tenths_by_skill"], {"skill.prayer": 503390})
        self.assertEqual(solution["objective"]["counted_manual_training_xp_tenths"], 0)
        required_actions = [
            "quest.lost_city.start", "quest.lost_city.find_shamus",
            "supply.bank.deposit_entrana_gear", "quest.lost_city.descend_entrana",
        ]
        steps = solution["steps"]
        self.assertEqual([step["action_id"] for step in steps if step.get("action_id") in required_actions],
                         required_actions)
        state = solution["final_state"]
        self.assertEqual(state["counters"]["token.quest_points"], 1)
        self.assertEqual(state["location_id"], "location.entrana_dungeon.zombies")
        self.assertEqual(state["bank_inventory"], dict.fromkeys((
            "item.bronze_axe", "item.bronze_dagger", "item.bronze_pickaxe", "item.bronze_shortsword",
            "item.shortbow", "item.wooden_shield",
        ), 1))
        deposit_id = "supply.bank.deposit_entrana_gear"
        deposit_index = next(i for i, step in enumerate(steps) if step.get("action_id") == deposit_id)
        before_deposit = RouteState(validator.tables, profile["policies"], profile["initial_state"])
        for step in steps[:deposit_index]:
            before_deposit = before_deposit.apply(step)
        self.assertEqual(state["inventory"], {
            item_id: quantity for item_id, quantity in before_deposit.snapshot()["inventory"].items()
            if item_id not in state["bank_inventory"]
        })
        without_deposit = {**solution, "steps": [
            step for step in steps if step.get("action_id") != deposit_id
        ]}
        with self.assertRaisesRegex(DataError, "loadout fails a restriction"):
            verify_solution(without_deposit, profile, validator)

    def test_lost_city_post_combat_route_awards_xp_and_zanaris_access(self):
        profile = read_json(ROOT / "examples/build-242/lost-city-completion-profile.json")
        validator = CatalogValidator(self.catalog, self.contracts)
        reward = next(row for row in read_json(RAW / "quest-month-rewards.json")["changes"]
                      if row["activity_id"] == "quest.lost_city")
        initial = profile["initial_state"]
        for spell_available in (True, False):
            with self.subTest(spell_available=spell_available):
                initial["flags"]["flag.spellbook.standard"] = spell_available
                solution, _ = solve_bounded(validator, profile, max_expansions=4000)
                verify_solution(solution, profile, validator)
                self.assertEqual(solution["manual_training_xp_tenths_by_skill"], {})
                self.assertEqual([step["action_id"] for step in solution["steps"] if step["kind"] == "action"], [
                    "quest.lost_city.cut_branch", "quest.lost_city.make_staff", "quest.lost_city.complete",
                ])
                escape = "spell" if spell_available else "tablet"
                self.assertIn(f"travel.{escape}.entrana_dungeon.lumbridge",
                              {step.get("edge_id") for step in solution["steps"]})
                state = solution["final_state"]
                expected_xp = initial["xp_tenths"].copy()
                for skill_id, xp_tenths in reward["fixed_xp_tenths"].items():
                    expected_xp[skill_id] += xp_tenths
                expected_inventory = {"item.bronze_axe": 1, "item.knife": 1, "item.dramen_staff": 1}
                if spell_available:
                    expected_xp["skill.magic"] += 410
                    expected_inventory["item.lumbridge_teleport_tablet"] = 1
                else:
                    expected_inventory.update({"item.air_rune": 3, "item.earth_rune": 1, "item.law_rune": 1})
                self.assertEqual(state["xp_tenths"], expected_xp)
                self.assertEqual(state["inventory"], expected_inventory)
                self.assertEqual(state["counters"]["token.quest_points"], 3)
                self.assertTrue(state["flags"]["flag.quest.lost_city.complete"])

    def test_lost_city_replays_the_funded_conditional_combat_route(self):
        profile = read_json(ROOT / "examples/build-242/lost-city-combat-profile.json")
        scenario = read_json(RAW / "lost-city-combat.json")
        validator = CatalogValidator(self.catalog, self.contracts)
        solution, _ = solve_bounded(validator, profile, beam_width=256, max_expansions=20000)
        state = verify_solution(solution, profile, validator)["final_state"]
        combat_steps = [step for step in solution["steps"] if "planned_outcome" in step]
        self.assertEqual([step["action_id"] for step in combat_steps], [
            "quest.lost_city.get_dungeon_axe", "quest.lost_city.defeat_tree_spirit",
        ])
        expected_xp = profile["initial_state"]["xp_tenths"]["skill.magic"]
        for step, encounter in zip(combat_steps, scenario["scenarios"], strict=True):
            action = validator.tables["actions"][step["action_id"]]
            self.assertEqual(step["planned_outcome"], action["planned_outcome"])
            self.assertEqual({cost["item_id"]: cost["quantity"] for cost in action["consumes"]}, {
                item_id: per_cast * encounter["cast_reserve"]
                for item_id, per_cast in scenario["fire_strike"]["runes_per_cast"].items()
            })
            expected_xp += encounter["credited_magic_xp_tenths"]
        edges = [validator.tables["travel_edges"][step["edge_id"]] for step in solution["steps"] if step["kind"] == "travel"]
        expected_xp += sum(
            effect["xp_tenths"] for edge in edges for effect in edge["effects"]
            if effect["kind"] == "xp" and effect["skill_id"] == "skill.magic"
        )
        self.assertEqual(state["xp_tenths"]["skill.magic"], expected_xp)
        self.assertTrue(state["flags"]["flag.quest.lost_city.tree_spirit_defeated"])
        self.assertTrue(state["flags"]["flag.quest.lost_city.complete"])
        self.assertEqual(state["counters"]["token.quest_points"], 4)
        self.assertEqual(state["counters"]["token.bank_coins"], 25)
        required_purchases = {
            "supply.grand_exchange.purchase_lost_city_runes", "supply.grand_exchange.purchase_knife",
            "supply.grand_exchange.purchase_lumbridge_tablet",
        }
        action_ids = [step.get("action_id") for step in solution["steps"]]
        self.assertTrue(required_purchases <= set(action_ids))
        self.assertLess(action_ids.index("stronghold.security.claim_famine"),
                        min(action_ids.index(purchase) for purchase in required_purchases))
        self.assertIn("travel.tablet.entrana_dungeon.lumbridge", {edge["id"] for edge in edges})
        self.assertEqual(state["inventory"]["item.mind_rune"], 15)
        self.assertNotIn("item.lumbridge_teleport_tablet", state["inventory"])
        self.assertEqual(state["inventory"]["item.dramen_staff"], 1)
        self.assertEqual(solution["objective"]["counted_manual_training_xp_tenths"], 0)
        del combat_steps[0]["planned_outcome"]
        with self.assertRaisesRegex(DataError, "planned_outcome"):
            verify_solution(solution, profile, validator)

    def test_lost_city_axe_encounter_preserves_the_escape_reserve(self):
        profile = read_json(ROOT / "examples/build-242/lost-city-combat-profile.json")
        validator = CatalogValidator(self.catalog, self.contracts)
        action = validator.tables["actions"]["quest.lost_city.get_dungeon_axe"]
        initial = profile["initial_state"]
        initial.update(
            location_id=action["start_location_id"],
            completed_action_ids=["quest.lost_city.descend_entrana"],
            inventory={cost["item_id"]: cost["quantity"] for cost in action["consumes"]},
        )
        step = {
            "kind": "action", "action_id": action["id"], "planned_outcome": action["planned_outcome"],
            "modeled_seconds": action["duration"]["expected_seconds"],
        }
        state = RouteState(validator.tables, profile["policies"], initial)
        with self.assertRaisesRegex(DataError, "required items"):
            state.apply(step)
        initial["inventory"]["item.lumbridge_teleport_tablet"] = 1
        state = RouteState(validator.tables, profile["policies"], initial)
        self.assertEqual(state.apply(step).snapshot()["inventory"], {
            "item.bronze_axe": 1, "item.lumbridge_teleport_tablet": 1,
        })

    def test_lost_city_completion_requires_combat_or_saved_progress(self):
        profile = read_json(ROOT / "examples/build-242/lost-city-completion-profile.json")
        del profile["initial_state"]["flags"]["flag.quest.lost_city.tree_spirit_defeated"]
        validator = CatalogValidator(self.catalog, self.contracts)
        with self.assertRaisesRegex(DataError, r"Catalog reachability blocks goals: quest\.lost_city\.complete"):
            solve_bounded(validator, profile, max_expansions=4000)

    def test_rfd_preserves_each_stage_and_awards_points_once(self):
        stages = self.rfd["stages"]
        self.assertCountEqual(
            [stage["activity_id"] for stage in stages],
            [row["id"] for row in self.journal if row.get("parent_id") == "quest.recipe_for_disaster"],
        )
        self.assertEqual(sum(stage["completion_rewards"]["quest_points"] for stage in stages), 10)
        self.assertEqual(self.rfd["parent_goal"]["completion_effects"], [])
        for stage in stages:
            source = self.observations[stage["activity_id"]][0]
            fixed_xp = {
                award["skill_id"]: award["xp_tenths"]
                for award in source["declared_xp"].get("observations", [])
            }
            self.assertEqual(stage["completion_rewards"]["fixed_xp_tenths"], fixed_xp)
        finale = stages[-1]
        self.assertEqual(finale["completion_action_id"], self.rfd["parent_goal"]["requires_action_id"])
        self.assertEqual(finale["completion_rewards"]["choice_reward"]["xp_tenths"], 200000)
        self.assertIsNone(finale["completion_rewards"]["choice_reward"]["minimum_level"])
        requirements = finale["progression_requirements"]["requirements"]
        self.assertIn({"kind": "counter", "token_id": "token.quest_points", "minimum": 175}, requirements)
        previous_completions = {stage["completion_action_id"] for stage in stages[:-1]}
        self.assertTrue(previous_completions <= {rule.get("action_id") for rule in requirements})

    def test_rfd_opening_and_goblin_rescue_replay_with_separate_rewards(self):
        profile = read_json(ROOT / "examples/build-242/rfd-opening-goblins-profile.json")
        validator = CatalogValidator(self.catalog, self.contracts)
        solution, _ = solve_bounded(validator, profile, beam_width=96)
        state = verify_solution(solution, profile, validator)["final_state"]
        self.assertEqual(solution["manual_training_xp_tenths_by_skill"], {})
        self.assertEqual(state["inventory"], {"item.bucket": 1, "item.gnome_spice": 1, "item.knife": 1})
        self.assertEqual(state["flags"], {
            "flag.rfd.goblin_kitchen_charred": True, "unlock.culinaromancers_chest": True,
        })
        self.assertNotIn("quest.recipe_for_disaster.complete", state["completed_action_ids"])

        initial = profile["initial_state"]
        expected_points = initial["counters"]["token.quest_points"]
        expected_xp = initial["xp_tenths"].copy()
        stage_ids = {"rfd.another_cooks_quest", "rfd.freeing_the_goblin_generals"}
        for stage in self.rfd["stages"]:
            if stage["activity_id"] not in stage_ids:
                continue
            rewards = stage["completion_rewards"]
            expected_points += rewards["quest_points"]
            for skill, xp in rewards["fixed_xp_tenths"].items():
                expected_xp[skill] += xp
        self.assertEqual(state["counters"]["token.quest_points"], expected_points)
        self.assertEqual(state["xp_tenths"], expected_xp)

        edges = {step.get("edge_id") for step in solution["steps"]}
        self.assertIn("travel.walk.rfd.goblin_kitchen.out", edges)
        self.assertIn("travel.walk.rfd.charred_goblin_kitchen.back", edges)
        without_banquet = {**solution, "steps": [
            step for step in solution["steps"] if step.get("action_id") != "rfd.another_cooks_quest.complete"
        ]}
        with self.assertRaises(DataError):
            verify_solution(without_banquet, profile, validator)

    def test_fishing_contest_and_mountain_dwarf_replay(self):
        profile = read_json(ROOT / "examples/build-242/rfd-mountain-dwarf-profile.json")
        validator = CatalogValidator(self.catalog, self.contracts)
        solution, _ = solve_bounded(validator, profile, beam_width=128, max_expansions=40000)
        state = verify_solution(solution, profile, validator)["final_state"]
        self.assertEqual(solution["manual_training_xp_tenths_by_skill"], {})
        self.assertEqual(state["counters"]["token.quest_points"], 5)
        self.assertTrue(state["flags"]["unlock.white_wolf_mountain_tunnel"])
        self.assertNotIn("item.coins", state["inventory"])
        self.assertNotIn("item.hot_dwarven_rock_cake", state["inventory"])
        self.assertNotIn("item.cooled_dwarven_rock_cake", state["inventory"])
        self.assertEqual(state["inventory"]["item.fishing_rod"], 1)
        self.assertEqual(state["inventory"]["item.spade"], 1)

        initial = profile["initial_state"]
        expected_xp = initial["xp_tenths"].copy()
        expected_xp["skill.fishing"] += 24370
        expected_xp["skill.cooking"] += 10000
        expected_xp["skill.slayer"] += 10000
        expected_xp["skill.attack"] += 800
        self.assertEqual(state["xp_tenths"], expected_xp)

        edges = {step.get("edge_id") for step in solution["steps"]}
        self.assertIn("travel.walk.white_wolf_mountain.tunnel_west.out", edges)
        self.assertIn("travel.walk.white_wolf_mountain.tunnel_east.out", edges)
        tunnel = validator.tables["travel_edges"]["travel.walk.white_wolf_mountain.tunnel_west.out"]
        step = {"kind": "travel", "edge_id": tunnel["id"], "modeled_seconds": tunnel["duration"]["expected_seconds"]}
        with self.assertRaisesRegex(DataError, "required completed action"):
            RouteState(validator.tables, profile["policies"], initial).apply(step)

        self.assertEqual([step["action_id"] for step in solution["steps"] if "planned_outcome" in step], [
            "quest.fishing_contest.catch_carp", "rfd.freeing_the_mountain_dwarf.cool_with_icefiend",
        ])
        fight = next(step for step in solution["steps"] if step.get("action_id") == "rfd.freeing_the_mountain_dwarf.cool_with_icefiend")
        del fight["planned_outcome"]
        with self.assertRaisesRegex(DataError, "planned_outcome"):
            verify_solution(solution, profile, validator)

    def test_mountain_dwarf_ice_gloves_cool_the_cake_on_pickup(self):
        profile = read_json(ROOT / "examples/build-242/rfd-mountain-dwarf-profile.json")
        validator = CatalogValidator(self.catalog, self.contracts)
        dwarf = "rfd.freeing_the_mountain_dwarf"
        ice_pickup = validator.tables["actions"][f"{dwarf}.pick_up_with_ice_gloves"]
        leather_pickup = validator.tables["actions"][f"{dwarf}.pick_up_with_leather_gloves"]
        initial = profile["initial_state"]
        initial.update(location_id=ice_pickup["start_location_id"], completed_action_ids=[f"{dwarf}.serve_rohak"])
        initial["inventory"]["item.ice_gloves"] = 1
        initial["inventory"]["item.coins"] = 200
        for item in ice_pickup["consumes"]:
            if item["item_id"] != "item.coins":
                initial["inventory"][item["item_id"]] = 2
        state = RouteState(validator.tables, profile["policies"], initial)
        chilled = state.apply({
            "kind": "action", "action_id": ice_pickup["id"],
            "modeled_seconds": ice_pickup["duration"]["expected_seconds"],
        })
        self.assertEqual(chilled.inventory["item.ice_gloves"], 1)
        self.assertEqual(chilled.inventory["item.cooled_dwarven_rock_cake"], 1)
        self.assertEqual(chilled.inventory["item.hot_dwarven_rock_cake"], 0)
        with self.assertRaisesRegex(DataError, "flag"):
            chilled.apply({
                "kind": "action", "action_id": leather_pickup["id"],
                "modeled_seconds": leather_pickup["duration"]["expected_seconds"],
            })

    def test_big_chompy_replays_hunt_gear_and_completion_xp(self):
        quest = "quest.big_chompy_bird_hunting"
        profile = read_json(ROOT / "examples/build-242/big-chompy-bird-hunting-profile.json")
        review = read_json(RAW / "big-chompy-bird-hunting-review.json")
        validator = CatalogValidator(self.catalog, self.contracts)
        solution = read_json(ROOT / "examples/build-242/big-chompy-bird-hunting-solution.json")
        state = verify_solution(solution, profile, validator)["final_state"]
        self.assertEqual(solution["manual_training_xp_tenths_by_skill"], {})
        self.assertEqual(state["counters"]["token.quest_points"], 4)
        self.assertEqual(state["inventory"], {"item.ogre_bow": 1, "item.ogre_bellows_one_load": 1})
        self.assertTrue(state["flags"]["unlock.chompy_hunting"])
        self.assertTrue(state["flags"]["unlock.ogre_arrow_fletching"])
        self.assertEqual(RouteState(validator.tables, profile["policies"], state).level("skill.cooking"), 31)

        [source] = self.observations[quest]
        expected_xp = profile["initial_state"]["xp_tenths"].copy()
        for effect in source["declared_xp"]["observations"]:
            expected_xp[effect["skill_id"]] += effect["xp_tenths"]
        for skill, xp in review["hunt"]["incidental_xp_tenths"].items():
            expected_xp[skill] += xp
        expected_xp["skill.magic"] += 410
        self.assertEqual(state["xp_tenths"], expected_xp)

        steps = solution["steps"]
        self.assertEqual([step["action_id"] for step in steps if "planned_outcome" in step], [
            f"{quest}.hand_over_arrows", f"{quest}.watch_demonstration", f"{quest}.hunt_chompy",
            f"{quest}.season_and_roast",
        ])
        action_ids = {step.get("action_id") for step in steps}
        self.assertTrue({
            "supply.feldip.gather_onion_and_tomato", "supply.feldip.gather_cabbage_and_doogle",
            "supply.feldip.gather_potato_and_equa",
        } <= action_ids)

        hunt = validator.tables["actions"][f"{quest}.hunt_chompy"]
        self.assertIn({"item_id": "item.ogre_arrow", "quantity": review["hunt"]["arrow_reserve"]}, hunt["consumes"])
        roast = validator.tables["actions"][f"{quest}.season_and_roast"]
        expected_ingredients = {item for pair in review["seasoning_requests"].values() for item in pair}
        self.assertEqual({cost["item_id"] for cost in roast["consumes"]}, expected_ingredients | {"item.raw_chompy"})

        for missing in (f"{quest}.watch_demonstration", "supply.feldip.gather_cabbage_and_doogle"):
            with self.subTest(missing=missing):
                skipped = {**solution, "steps": [step for step in steps if step.get("action_id") != missing]}
                with self.assertRaises(DataError):
                    verify_solution(skipped, profile, validator)

    def test_feldip_fairy_ring_requires_access_and_staff(self):
        profile = read_json(ROOT / "examples/build-242/big-chompy-bird-hunting-profile.json")
        validator = CatalogValidator(self.catalog, self.contracts)
        edge = validator.tables["travel_edges"]["travel.fairy_ring.zanaris.aks"]
        step = {"kind": "travel", "edge_id": edge["id"], "modeled_seconds": edge["duration"]["expected_seconds"]}
        initial = profile["initial_state"]
        initial["location_id"] = edge["from_location_id"]
        initial["inventory"]["item.dramen_staff"] = 1
        with self.assertRaisesRegex(DataError, "flag"):
            RouteState(validator.tables, profile["policies"], initial).apply(step)
        initial["flags"]["unlock.fairy_rings"] = True
        arrived = RouteState(validator.tables, profile["policies"], initial).apply(step)
        self.assertEqual(arrived.location, "location.fairy_ring.aks")
        self.assertEqual(arrived.inventory["item.dramen_staff"], 1)
        del initial["inventory"]["item.dramen_staff"]
        with self.assertRaisesRegex(DataError, "required items"):
            RouteState(validator.tables, profile["policies"], initial).apply(step)

    def test_skrach_replays_the_signal_ride_and_player_cooked_jubbly(self):
        quest = "rfd.freeing_skrach_uglogwee"
        examples = ROOT / "examples/build-242"
        profile = read_json(examples / "rfd-skrach-uglogwee-profile.json")
        solution = read_json(examples / "rfd-skrach-uglogwee-solution.json")
        review = read_json(RAW / "skrach-uglogwee-review.json")
        validator = CatalogValidator(self.catalog, self.contracts)
        state = verify_solution(solution, profile, validator)["final_state"]
        self.assertEqual(solution["manual_training_xp_tenths_by_skill"], {})
        self.assertEqual(state["counters"]["token.quest_points"], 7)
        self.assertEqual(state["inventory"], {
            "item.ogre_bow": 1, "item.ogre_bellows_two_loads": 1, "item.iron_spit": 1,
            "item.bronze_axe": 1, "item.bronze_pickaxe": 1, "item.tinderbox": 1,
        })
        self.assertTrue(state["flags"]["unlock.ogre_boat"])
        self.assertTrue(state["flags"]["unlock.jubbly_hunting"])

        initial = profile["initial_state"]
        [source] = self.observations[quest]
        expected_xp = initial["xp_tenths"].copy()
        for effect in source["declared_xp"]["observations"]:
            expected_xp[effect["skill_id"]] += effect["xp_tenths"]
        for award in review["incidental_xp_tenths"].values():
            for skill, xp in award.items():
                expected_xp[skill] += xp
        expected_xp["skill.ranged"] += review["hunt"]["credited_ranged_xp_tenths"]
        expected_xp["skill.magic"] += 820
        self.assertEqual(state["xp_tenths"], expected_xp)

        steps = solution["steps"]
        edges = [step.get("edge_id") for step in steps if step["kind"] == "travel"]
        self.assertEqual(edges.count("travel.ship.ardougne.brimhaven.out"), 1)
        self.assertEqual([step["action_id"] for step in steps if "planned_outcome" in step], [
            f"{quest}.signal_boat", f"{quest}.hunt_jubbly", f"{quest}.cook_jubbly",
        ])
        ride = next(step for step in steps if step.get("action_id") == f"{quest}.ride_back")
        before_ride = RouteState(validator.tables, profile["policies"], initial)
        for step in steps[:steps.index(ride)]:
            before_ride = before_ride.apply(step)
        self.assertFalse(before_ride.flags.get("unlock.ogre_boat", False))
        self.assertEqual(before_ride.apply(ride).location, "location.feldip_hills.rantz_coast")

        without_signal = {**solution, "steps": [step for step in steps if step.get("action_id") != f"{quest}.signal_boat"]}
        with self.assertRaisesRegex(DataError, "required completed action"):
            verify_solution(without_signal, profile, validator)
        initial.update(location_id="location.rfd.frozen_skrach_uglogwee", completed_action_ids=[f"{quest}.inspect"])
        initial["inventory"]["item.cooked_jubbly"] = 1
        with self.assertRaisesRegex(DataError, "required completed action"):
            RouteState(validator.tables, profile["policies"], initial).apply(steps[-1])

    def test_skrach_balloon_bait_accounts_for_each_bellows_charge_state(self):
        quest = "rfd.freeing_skrach_uglogwee"
        profile = read_json(ROOT / "examples/build-242/rfd-skrach-uglogwee-profile.json")
        validator = CatalogValidator(self.catalog, self.contracts)
        for variant, before, after in (
            ("empty_bellows", "ogre_bellows", "ogre_bellows_one_load"),
            ("one_load", "ogre_bellows_one_load", "ogre_bellows_two_loads"),
            ("two_loads", "ogre_bellows_two_loads", "ogre_bellows"),
            ("three_loads", "ogre_bellows_three_loads", "ogre_bellows_one_load"),
        ):
            with self.subTest(variant=variant):
                action = validator.tables["actions"][f"{quest}.prepare_balloon_with_{variant}"]
                initial = {**profile["initial_state"], "location_id": action["start_location_id"],
                           "completed_action_ids": [f"{quest}.learn_balloon_bait"],
                           "inventory": {f"item.{before}": 1, "item.swamp_rock": 1, "item.ball_of_wool": 1}}
                state = RouteState(validator.tables, profile["policies"], initial).apply({
                    "kind": "action", "action_id": action["id"],
                    "modeled_seconds": action["duration"]["expected_seconds"],
                })
                self.assertEqual(state.snapshot()["inventory"], {f"item.{after}": 1, "item.balloon_toad": 1})

    def test_rfd_parent_records_only_saved_finale_completion(self):
        profile = read_json(ROOT / "examples/build-242/rfd-opening-goblins-profile.json")
        validator = CatalogValidator(self.catalog, self.contracts)
        initial = profile["initial_state"]
        initial["completed_action_ids"] += [
            "rfd.another_cooks_quest.complete", "rfd.freeing_the_goblin_generals.complete",
        ]
        step = {"kind": "action", "action_id": "quest.recipe_for_disaster.complete", "modeled_seconds": 0}
        with self.assertRaises(DataError):
            RouteState(validator.tables, profile["policies"], initial).apply(step)
        initial["flags"]["flag.rfd.finale_complete"] = True
        state = RouteState(validator.tables, profile["policies"], initial).apply(step).snapshot()
        self.assertIn(step["action_id"], state["completed_action_ids"])
        for field in ("xp_tenths", "inventory", "counters", "held_rewards"):
            self.assertEqual(state[field], initial[field])

    def test_pirate_pete_preserves_account_specific_or_observation(self):
        [source] = self.observations["rfd.freeing_pirate_pete"]
        [ironman] = [
            row["observation"]
            for row in source["general_requirements"]["observations"]
            if row["guards"] == ["ironman"]
        ]
        self.assertEqual(ironman["kind"], "or")
        self.assertEqual({rule["kind"] for rule in ironman["requirements"]}, {"quest", "skill"})
        stage = next(stage for stage in self.rfd["stages"] if stage["activity_id"] == "rfd.freeing_pirate_pete")
        self.assertEqual(stage["skill_checks"], [
            {"kind": "skill", "skill_id": "skill.cooking", "minimum_level": 31, "boostable": False},
        ])

    def test_pirate_pete_replays_gear_ballast_and_fishcake_rewards(self):
        pete = "rfd.freeing_pirate_pete"
        profile = read_json(ROOT / "examples/build-242/rfd-pirate-pete-profile.json")
        review = read_json(RAW / "pirate-pete-review.json")
        validator = CatalogValidator(self.catalog, self.contracts)
        solution, _ = solve_bounded(validator, profile, beam_width=128, max_expansions=40000)
        state = verify_solution(solution, profile, validator)["final_state"]
        self.assertEqual(solution["manual_training_xp_tenths_by_skill"], {})
        self.assertEqual(state["counters"]["token.quest_points"], 5)
        self.assertEqual(state["counters"].get("token.mogre_camp.ballast", 0), 0)
        self.assertTrue(state["flags"]["unlock.mogre_camp"])
        self.assertTrue(state["flags"]["unlock.mogre_camp.crab_pen"])
        self.assertEqual(state["inventory"], {
            "item.bronze_shortsword": 1, "item.diving_apparatus": 1, "item.fishbowl_helmet": 1,
            "item.knife": 1, "item.needle": 1, "item.pestle_and_mortar": 1, "item.shrimps": 6,
        })

        [source] = self.observations[pete]
        expected_xp = profile["initial_state"]["xp_tenths"].copy()
        for effect in source["declared_xp"]["observations"]:
            expected_xp[effect["skill_id"]] += effect["xp_tenths"]
        expected_xp["skill.cooking"] += review["fishcake"]["success_xp_tenths"]
        expected_xp["skill.attack"] += review["dive"]["credit_damage_xp"]["skill.attack"]
        expected_xp["skill.magic"] += 820
        self.assertEqual(state["xp_tenths"], expected_xp)

        steps = solution["steps"]
        gear = next(i for i, step in enumerate(steps) if step.get("action_id") == f"{pete}.get_diving_gear")
        dive = next(i for i, step in enumerate(steps) if step.get("action_id") == f"{pete}.dive")
        self.assertLess(gear, dive)
        self.assertEqual([step["action_id"] for step in steps if "planned_outcome" in step], [
            f"{pete}.dive", f"{pete}.collect_hides", f"{pete}.collect_crab_meat", f"{pete}.cook_fishcake",
        ])
        edges = {step.get("edge_id") for step in steps}
        self.assertTrue({
            "travel.other.lumbridge.fishing_trawler", "travel.other.mogre_camp.climb_anchor",
            "travel.spell.port_khazard.lumbridge",
        } <= edges)

        ballast = [i for i, step in enumerate(steps) if step.get("action_id") == f"{pete}.collect_ballast"]
        self.assertEqual(len(ballast), 2)
        for index, blocked in zip(ballast, ("enter_mudskipper_cave", "enter_crab_pen"), strict=True):
            with self.subTest(blocked=blocked):
                skipped = {**solution, "steps": steps[:index] + steps[index + 1:]}
                with self.assertRaisesRegex(DataError, "counter threshold"):
                    verify_solution(skipped, profile, validator)

        cook = next(step for step in steps if step.get("action_id") == f"{pete}.cook_fishcake")
        del cook["planned_outcome"]
        with self.assertRaisesRegex(DataError, "planned_outcome"):
            verify_solution(solution, profile, validator)

    def test_publisher_reward_delta_and_separate_claim(self):
        rewards = read_json(RAW / "quest-month-rewards.json")["changes"]
        by_activity = {change["activity_id"]: change for change in rewards}
        self.assertEqual(len(by_activity), 18)
        self.assertEqual(by_activity["quest.demon_slayer"]["claim_id"], "claim.demon_slayer.aris")
        rune_actions = [row for row in self.catalog["actions"] if row["activity_id"] == "quest.rune_mysteries"]
        xp_effects = [
            (row["id"], effect["xp_tenths"])
            for row in rune_actions for effect in row["effects"] if effect["kind"] == "xp"
        ]
        expected = by_activity["quest.rune_mysteries"]["fixed_xp_tenths"]["skill.runecraft"]
        self.assertEqual(xp_effects, [("quest.rune_mysteries.complete", expected)])

    def test_cooks_assistant_fixture_has_supplies_and_completion_effects(self):
        profile = read_json(ROOT / "examples/build-242/cooks-assistant-profile.json")
        self.contracts.validate("profile", profile)
        CatalogValidator(self.catalog, self.contracts).validate_profile(profile)
        [goal_id] = profile["goal_action_ids"]
        action = next(row for row in self.catalog["actions"] if row["id"] == goal_id)
        self.assertEqual(action["start_location_id"], profile["initial_state"]["location_id"])
        self.assertEqual({item["item_id"]: item["quantity"] for item in action["consumes"]},
                         profile["initial_state"]["inventory"])
        self.assertIn({"kind": "xp", "skill_id": "skill.cooking", "xp_tenths": 3000}, action["effects"])
        self.assertIn({"kind": "counter", "token_id": "token.quest_points", "delta": 1}, action["effects"])

    def test_reward_registry_tracks_claims_separately_from_completion(self):
        registry = read_json(RAW / "reward-registry.json")
        entries = registry["entries"]
        exclusions = registry["exclusions"]
        known_sources = {source["id"] for source in self.catalog["sources"]}
        records = entries + exclusions
        self.assertEqual(len({row["id"] for row in records}), len(records))
        self.assertTrue({source for row in records for source in row["source_ids"]} <= known_sources)
        claims = [row for row in entries if row["delivery"] == "post_quest_claim"]
        self.assertEqual(len({row["producer_action_id"] for row in claims}), len(claims))
        for claim in claims:
            self.assertIn({
                "kind": "action_completed", "action_id": claim["activity_id"] + ".complete",
            }, claim["requires"]["requirements"])
            self.assertEqual(claim["repeat_limit"], 1)
        aris = next(claim for claim in claims if claim["id"] == "claim.demon_slayer.aris")
        self.assertEqual(aris["claim_location"]["tile"], [3204, 3424, 0])
        self.assertEqual(aris["package"]["quantity"], 2)
        self.assertEqual(aris["package"]["amount"], {"kind": "fixed", "xp_tenths": 10000})
        self.assertIsNone(aris["package"]["minimum_level"])
        self.assertTrue(all(row["status"] == "excluded" and row["reason"] for row in exclusions))

    def test_catalog_lamp_is_spendable_after_veos_awards_it(self):
        reward_id = "reward.x_marks_the_spot.ancient_lamp"
        producers = [
            action for action in self.catalog["actions"]
            if any(effect.get("reward_id") == reward_id for effect in action["effects"])
        ]
        [completion] = producers
        self.assertEqual(completion["id"], "quest.x_marks_the_spot.complete")
        profile = read_json(ROOT / "examples/build-242/cooks-assistant-profile.json")
        profile["profile_id"] = "profile.fixture.veos"
        profile["goal_action_ids"] = [completion["id"]]
        profile["initial_state"].update(
            location_id=completion["start_location_id"],
            inventory={"item.ancient_casket.x_marks_the_spot": 1},
            completed_action_ids=[
                action["id"] for action in self.catalog["actions"]
                if action["activity_id"] == completion["activity_id"] and action != completion
            ],
        )
        solution = read_json(ROOT / "examples/synthetic/solution.json")
        solution["inputs"].update(
            dataset_id=profile["dataset_id"], dataset_version=profile["dataset_version"],
            profile_id=profile["profile_id"],
        )
        solution["policies"] = profile["policies"]
        solution["objective"].update(manual_training_xp_tenths=0, modeled_non_training_seconds=20)
        solution["manual_training_xp_tenths_by_skill"] = {}
        solution["steps"] = [
            {"step_id": "step.veos", "kind": "action", "action_id": completion["id"],
             "modeled_seconds": 20, "explanation": "Complete the quest and receive one lamp."},
            {"step_id": "step.spend", "kind": "reward_use", "reward_id": reward_id,
             "instance_id": reward_id + ".instance.1", "skill_id": "skill.agility",
             "gain_xp_tenths": 3000, "overrides_observed_skill_restriction": False,
             "explanation": "Use the whole lamp on Agility."},
        ]
        state = profile["initial_state"]
        solution["final_state"] = {
            **state, "xp_tenths": {**state["xp_tenths"], "skill.agility": 3000},
            "completed_action_ids": state["completed_action_ids"] + [completion["id"]],
            "inventory": {"item.coins": 200}, "counters": {"token.quest_points": 1},
            "modeled_elapsed_seconds": 20,
        }
        validator = CatalogValidator(self.catalog, self.contracts)
        self.contracts.validate("profile", profile)
        validator.validate_profile(profile)
        self.contracts.validate("solution", solution)
        validator.validate_solution(solution, profile)
