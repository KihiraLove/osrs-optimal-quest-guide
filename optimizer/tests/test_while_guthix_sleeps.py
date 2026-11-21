"""Focused build-242 WGS quest route, distinct Kuradal claim and draft gaps."""

from collections import defaultdict, deque
from pathlib import Path
import unittest

from quest_optimizer.data import Contracts, DataError, load_catalog, read_json
from quest_optimizer.reachability import unreachable_records
from quest_optimizer.semantics import CatalogValidator
from quest_optimizer.transitions import RouteState


ROOT = Path(__file__).resolve().parents[2]
QUEST = "quest.while_guthix_sleeps"
CLAIM = "claim.while_guthix_sleeps.kuradal"
READ_NOTES = "claim.while_guthix_sleeps.read_duradels_notes"
REWARD = "reward.wgs.duradels_notes_slayer"
CHAROS = f"{QUEST}.dirty_shirt_charos"


class WhileGuthixSleepsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        contracts = Contracts(ROOT / "schemas")
        cls.catalog = load_catalog(ROOT / "data/manifest.json", contracts)
        cls.tables = CatalogValidator(cls.catalog, contracts).tables
        cls.profile = read_json(ROOT / "data/profiles/main-baseline.json")
        cls.stages = [record for record in cls.tables["actions"].values()
                      if record.get("activity_id") == QUEST and record["id"] != CHAROS]
        cls.batch_actions = read_json(ROOT / "data/catalog/while-guthix-sleeps/actions.json")

    def seed(self, *, points=180, predecessor=True, combat_levels=True, with_items=True):
        init = {**self.profile["initial_state"]}
        init["xp_tenths"] = {k: (12_000_000 if combat_levels else 0)
                             for k in init["xp_tenths"]}
        first = self.tables["actions"][QUEST + ".start"]
        prereqs = [r["action_id"] for r in first["requirements"]["requirements"]
                   if r["kind"] == "action_completed"]
        init["completed_action_ids"] = prereqs if predecessor else prereqs[:-1]
        init["counters"] = {**init["counters"], "token.quest_points": points}
        init["inventory"] = {**init["inventory"]}
        if with_items:
            init["inventory"].update({
                "item.coins": 1_000, "item.logs": 1, "item.knife": 1,
                "item.lantern_lens": 1, "item.seed_dibber": 1,
                "item.air_rune": 8, "item.astral_rune": 4, "item.cosmic_rune": 7,
                "item.fire_rune": 30, "item.bronze_med_helm": 1,
                "item.iron_chainbody": 1, "item.sapphire_lantern": 1,
                "item.legends.unpowered_orb": 1,
            })
        init["location_id"] = "location.wgs.start"
        return RouteState(self.tables, self.profile["policies"], init)

    def apply(self, state, aid):
        record = self.tables["actions"][aid]
        snap = state.snapshot()
        snap["location_id"] = record["start_location_id"]
        state = RouteState(self.tables, self.profile["policies"], snap)
        step = {"kind": "action", "action_id": aid,
                "modeled_seconds": record["duration"]["expected_seconds"]}
        if "planned_outcome" in record:
            step["planned_outcome"] = record["planned_outcome"]
        return state.apply(step, aid)

    def complete(self, state):
        for stage in self.stages:
            if stage["id"] == CLAIM:
                continue
            state = self.apply(state, stage["id"])
        return state

    def test_full_stage_replay_rewards_once(self):
        before = self.seed()
        state = self.complete(before)
        snap = state.snapshot()
        self.assertIn(QUEST + ".complete", snap["completed_action_ids"])
        self.assertEqual(snap["counters"]["token.quest_points"], 185)
        for skill,amount in (("thieving",800_000),("farming",750_000),
                             ("herblore",750_000),("hunter",500_000)):
            self.assertEqual(snap["xp_tenths"]["skill." + skill],12_000_000 + amount)
        self.assertTrue(snap["flags"]["unlock.wgs.tormented_demons"])
        self.assertNotIn(CLAIM,snap["completed_action_ids"])
        with self.assertRaises(DataError):
            self.apply(state,QUEST + ".complete")

    def test_kuradal_claim_is_separate_and_repeat_protected(self):
        with self.assertRaises(DataError):
            self.apply(self.seed(), CLAIM)
        finished = self.complete(self.seed())
        with self.assertRaises(DataError):
            self.apply(finished, READ_NOTES)
        notes = self.apply(finished, CLAIM)
        self.assertEqual(notes.snapshot()["inventory"]["item.wgs_duradels_notes"],1)
        self.assertEqual(notes.snapshot()["xp_tenths"]["skill.slayer"],
                         finished.snapshot()["xp_tenths"]["skill.slayer"])
        with self.assertRaises(DataError):
            self.apply(notes, CLAIM)
        for level in (1, 62, 99):
            with self.subTest(level=level):
                initial = notes.snapshot()
                initial["xp_tenths"]["skill.slayer"] = self.tables["skills"]["skill.slayer"][
                    "xp_thresholds_tenths"
                ][level - 1]
                state = RouteState(self.tables, self.profile["policies"], initial)
                state = self.apply(state, READ_NOTES)
                self.assertNotIn("item.wgs_duradels_notes", state.snapshot()["inventory"])
                xp = 150 * level
                use = {
                    "kind": "reward_use", "instance_id": f"{REWARD}.instance.1", "reward_id": REWARD,
                    "skill_id": "skill.slayer", "gain_xp_tenths": xp,
                    "overrides_observed_skill_restriction": False,
                }
                state = state.apply(use, "read_notes")
                snapshot = state.snapshot()
                self.assertEqual(snapshot["xp_tenths"]["skill.slayer"], initial["xp_tenths"]["skill.slayer"] + xp)
                self.assertTrue(snapshot["flags"]["unlock.wgs.demonbane_crafting"])
                with self.assertRaises(DataError):
                    self.apply(state, READ_NOTES)

    def test_all_quest_prerequisites_and_base_level_gates(self):
        first = self.tables["actions"][QUEST + ".start"]
        requirements = first["requirements"]["requirements"]
        self.assertEqual({r["skill_id"]:r["minimum_level"] for r in requirements
                          if r["kind"] == "skill"},
                         {"skill.thieving":72,"skill.magic":67,"skill.agility":66,
                          "skill.herblore":65,"skill.farming":65,"skill.hunter":62})
        self.assertEqual(sum(r["kind"] == "action_completed" for r in requirements), 10)
        self.assertTrue(all(not r["boostable"] for r in requirements
                            if r["kind"] == "skill"))
        for state in (self.seed(points=179),self.seed(predecessor=False),
                      self.seed(combat_levels=False)):
            with self.assertRaises(DataError):
                self.apply(state,QUEST + ".start")

    def test_warriors_guild_accepts_asymmetric_base_levels(self):
        for attack, strength, allowed in (
            (32, 98, True), (90, 40, True), (99, 1, True), (1, 99, True),
            (90, 39, False), (98, 1, False),
        ):
            with self.subTest(attack=attack, strength=strength):
                initial = self.seed().snapshot()
                for name, level in (("attack", attack), ("strength", strength)):
                    skill = f"skill.{name}"
                    initial["xp_tenths"][skill] = self.tables["skills"][skill]["xp_thresholds_tenths"][level - 1]
                state = RouteState(self.tables, self.profile["policies"], initial)
                if allowed:
                    self.apply(state, f"{QUEST}.start")
                else:
                    with self.assertRaises(DataError):
                        self.apply(state, f"{QUEST}.start")

    def test_launderer_accepts_activated_ring_instead_of_coins(self):
        initial = self.seed().snapshot()
        initial["inventory"].pop("item.coins")
        initial["inventory"]["item.ring_of_charos_a"] = 1
        state = RouteState(self.tables, self.profile["policies"], initial)
        for slug in ("start", "thaerisk", "assassins", "thaerisk_briefing"):
            state = self.apply(state, f"{QUEST}.{slug}")
        state = self.apply(state, CHAROS)
        state = self.apply(state, f"{QUEST}.hunter_expert")
        self.assertEqual(state.snapshot()["inventory"]["item.ring_of_charos_a"], 1)
        self.assertNotIn("item.coins", state.snapshot()["inventory"])
        with self.assertRaises(DataError):
            self.apply(state, f"{QUEST}.dirty_shirt")

    def test_broav_lens_and_spell_supply_debits(self):
        actions = self.tables["actions"]
        trap = actions[QUEST + ".broav_trap"]
        self.assertIn({"item_id":"item.logs","quantity":1},trap["consumes"])
        self.assertEqual(actions[QUEST + ".dirty_shirt"]["consumes"],
                         [{"item_id":"item.coins","quantity":500}])
        self.assertEqual(actions[QUEST + ".buy_pink_dye"]["consumes"],
                         [{"item_id":"item.lantern_lens","quantity":1},
                          {"item_id":"item.coins","quantity":20}])
        self.assertEqual({x["item_id"]:x["quantity"] for x in
                          actions[QUEST + ".contact_slayer_masters"]["consumes"]},
                         {"item.air_rune":8,"item.astral_rune":4,"item.cosmic_rune":4})
        self.assertEqual({x["item_id"]:x["quantity"] for x in
                          actions[QUEST + ".charge_orb"]["consumes"]},
                         {"item.legends.unpowered_orb":1,"item.fire_rune":30,"item.cosmic_rune":3})

    def test_items_are_received_and_used_in_order(self):
        snap = self.complete(self.seed()).snapshot()
        for consumed in ("item.wgs_broav_fungus","item.wgs_scrying_orb",
                         "item.wgs_enriched_seed","item.wgs_enriched_snapdragon",
                         "item.wgs_truth_serum","item.wgs_lobster","item.wgs_restore",
                         "item.wgs_charged_orb","item.wgs_teleorb","item.wgs_filled_pouch"):
            self.assertEqual(snap["inventory"].get(consumed,0),0,consumed)
        self.assertEqual(snap["inventory"].get("item.coins",0),480)

    def test_puzzles_and_encounters_have_success_conditions(self):
        for slug in ("assassins","broav_caught","solve_rune_door","search_library",
                     "disarm_movario_chest","shadow_agent","draw_surok",
                     "cross_catacombs","defeat_surok","squall_disguise",
                     "fire_brazier","water_recess","balance_elemental",
                     "tormented_demons"):
            self.assertIn("planned_outcome",self.tables["actions"][QUEST + "." + slug])
        with self.assertRaises(DataError):
            self.apply(self.seed(), QUEST + ".balance_elemental")

    def test_coverage_and_registry_match_producers(self):
        coverage = ROOT / "data/coverage/build-242"
        ledger = read_json(coverage / "journal.json")
        self.assertEqual(next(row for row in ledger if row["id"] == QUEST)["status"], "collected")
        registry = read_json(ROOT / "data/raw/build-242/reward-registry.json")
        entries = {row["id"]: row for row in registry["entries"]}
        claim = entries[CLAIM]
        self.assertEqual(claim["status"], "collected")
        self.assertEqual(claim["producer_action_id"], CLAIM)
        self.assertEqual(claim["read_action_id"], READ_NOTES)
        self.assertEqual(claim["items"], [{"item_id": "item.wgs_duradels_notes", "quantity": 1}])
        self.assertEqual([row["id"] for row in entries.values() if row.get("xp_reward_id") == REWARD], [READ_NOTES])
        reading = entries[READ_NOTES]
        read_action = self.tables["actions"][READ_NOTES]
        self.assertEqual(reading["producer_action_id"], READ_NOTES)
        self.assertEqual(reading["requires"], read_action["requirements"])
        self.assertEqual(reading["consumes"], read_action["consumes"])
        self.assertEqual(reading["repeat_limit"], read_action["repeat_limit"])
        self.assertEqual(reading["package"]["amount"], {"kind": "per_skill_level", "xp_tenths_per_level": 150})
        self.assertFalse(reading["package"]["retainable"])

        reviews = {row["id"]: row for row in read_json(coverage / "reward-reviews.json")}
        completion = reviews[f"review.{QUEST}.completion_rewards"]
        completion_id = f"{QUEST}.complete"
        self.assertEqual(completion["expected_effects"][completion_id], self.tables["actions"][completion_id]["effects"])
        notes = reviews[f"review.{READ_NOTES}"]
        self.assertEqual(notes["catalog_ids"], [CLAIM, READ_NOTES, REWARD])
        self.assertEqual(notes["expected_effects"], {
            CLAIM: self.tables["actions"][CLAIM]["effects"],
            READ_NOTES: read_action["effects"],
        })

    def test_travel_graph_connects_taverley_to_shilo_and_returns(self):
        graph=defaultdict(set)
        for edge in self.tables["travel_edges"].values():
            graph[edge["from_location_id"]].add(edge["to_location_id"])
        origin="location.grim.sylas"
        seen={origin}
        queue=deque([origin])
        while queue:
            for nxt in graph[queue.popleft()]:
                if nxt not in seen:
                    seen.add(nxt)
                    queue.append(nxt)
        self.assertIn(self.tables["actions"][QUEST+".complete"]["start_location_id"],seen)
        self.assertIn(self.tables["actions"][CLAIM]["start_location_id"],seen)
        self.assertIn(origin,graph["location.wgs.start"])

    def test_every_stage_is_reachable_from_the_main_baseline(self):
        unreachable = unreachable_records(self.catalog, self.profile)
        new_ids = {record["id"] for record in self.batch_actions}
        new_ids.add("miniquest.the_fractured_archive.start")
        self.assertEqual(new_ids.intersection(unreachable["actions"]), set())


if __name__ == "__main__":
    unittest.main()
