"""Connected build-242 route replays for A Tail of Two Cats and Ratcatchers."""

from collections import defaultdict, deque
from pathlib import Path
import unittest

from quest_optimizer.data import Contracts, DataError, load_catalog, read_json
from quest_optimizer.semantics import CatalogValidator
from quest_optimizer.transitions import RouteState


ROOT = Path(__file__).resolve().parents[2]
BATCH = ROOT / "data/catalog/cat-quest-chain"


class CatQuestChainTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        contracts = Contracts(ROOT / "schemas")
        cls.validator = CatalogValidator(load_catalog(ROOT / "data/manifest.json", contracts), contracts)
        cls.profile = read_json(ROOT / "data/profiles/main-baseline.json")
        cls.batch = read_json(BATCH / "actions.json")
        cls.edges = read_json(BATCH / "travel_edges.json")
        cls.walks = defaultdict(list)
        for edge in cls.validator.tables["travel_edges"].values():
            if edge["mode"] in ("walk", "ship") or edge["id"].startswith("travel.other.keldagrim"):
                cls.walks[edge["from_location_id"]].append(edge)

    def seeded(self, *, giant_dwarf=True, have_charm=False):
        initial = read_json(ROOT / "data/profiles/main-baseline.json")["initial_state"]
        initial["location_id"] = "location.burthorpe.unferth"
        initial["completed_action_ids"] = ["quest.icthlarins_little_helper.complete",
                                           "quest.gertrudes_cat.complete"]
        initial["flags"]["unlock.sophanem_access"] = True
        initial["flags"]["flag.quest.icthlarins_little_helper.complete"] = True
        if giant_dwarf:
            initial["completed_action_ids"].extend(["quest.the_giant_dwarf.start",
                                                    "quest.the_giant_dwarf.speak_to_veldaban"])
            initial["flags"]["unlock.keldagrim.minecart_access"] = True
        initial["inventory"].update({
            "item.coins": 20000,
            "item.pet_kitten": 1,
            "item.icthlarin_catspeak_amulet": 1,
            "item.death_rune": 5,
            "item.chocolate_cake": 1,
            "item.logs": 1,
            "item.tinderbox": 2,
            "item.bucket_of_milk": 2,
            "item.shears": 1,
            "item.potato_seed": 4,
            "item.rake": 1,
            "item.seed_dibber": 1,
            "item.vial_of_water": 1,
            "item.desert_shirt": 1,
            "item.desert_robe": 1,
            "item.cheese": 4,
            "item.empty_vial": 1,
            "item.clean_kwuarm": 1,
            "item.red_spiders_eggs": 1,
            "item.clean_marrentill": 1,
            "item.unicorn_horn_dust": 1,
            "item.raw_sardine": 8,
            "item.pot_of_weeds": 1,
        })
        if have_charm:
            initial["inventory"]["item.snake_charm"] = 1
        return RouteState(self.validator.tables, self.profile["policies"], initial)

    def apply(self, state, record, travel=False):
        step = {"kind": "travel" if travel else "action",
                "edge_id" if travel else "action_id": record["id"],
                "modeled_seconds": record["duration"]["expected_seconds"]}
        if "planned_outcome" in record:
            step["planned_outcome"] = record["planned_outcome"]
        return state.apply(step)

    def walk_to(self, state, dest):
        if state.location == dest:
            return state
        todo = deque([state])
        seen = {state.location}
        while todo:
            item = todo.popleft()
            for edge in self.walks[item.location]:
                target = edge["to_location_id"]
                if target in seen:
                    continue
                try:
                    next_state = self.apply(item, edge, travel=True)
                except DataError:
                    continue
                if target == dest:
                    return next_state
                seen.add(target)
                todo.append(next_state)
        self.fail(f"No legal walking route from {state.location} to {dest}")

    def quest_steps(self, state, *, nurse=False, existing_charm=False):
        skipped = {"quest.a_tail_of_two_cats.obtain_doctor_hat" if nurse else
                   "quest.a_tail_of_two_cats.obtain_nurse_hat",
                   "quest.ratcatchers.purchase_snake_charm" if existing_charm else
                   "quest.ratcatchers.reuse_snake_charm"}
        quest_actions = [a for a in self.batch if a["activity_id"] in
                         ("quest.a_tail_of_two_cats", "quest.ratcatchers") and a["id"] not in skipped]
        for record in quest_actions:
            state = self.walk_to(state, record["start_location_id"])
            try:
                state = self.apply(state, record)
            except DataError as err:
                self.fail(f"Action {record['id']} failed: {err}")
        return state

    def test_both_quests_replay_with_doctor_and_paid_charm(self):
        state = self.quest_steps(self.seeded())
        final = state.snapshot()
        self.assertEqual(final["counters"]["token.quest_points"], 5)
        self.assertEqual(final["xp_tenths"]["skill.thieving"], 45000)
        self.assertEqual(final["inventory"]["item.tail_doctors_hat"], 1)
        self.assertEqual(final["inventory"]["item.tail_mouse_toy"], 1)
        self.assertEqual(final["inventory"]["item.rat_pole"], 1)
        self.assertEqual(len(final["held_rewards"]), 2)
        self.assertTrue(final["flags"]["unlock.rat_pits"])
        self.assertNotIn("item.poisoned_cheese", final["inventory"])
        self.assertNotIn("item.rat_antipoison", final["inventory"])
        with self.assertRaises(DataError):
            self.apply(state, self.validator.tables["actions"]["quest.ratcatchers.complete"])

    def test_nurse_hat_and_earlier_snake_charm_branches(self):
        state = self.quest_steps(self.seeded(have_charm=True), nurse=True, existing_charm=True)
        final = state.snapshot()
        self.assertEqual(final["inventory"]["item.tail_nurses_hat"], 1)
        self.assertNotIn("item.tail_doctors_hat", final["inventory"])
        self.assertEqual(final["inventory"]["item.snake_charm"], 1)
        self.assertNotIn("quest.ratcatchers.purchase_snake_charm", final["completed_action_ids"])

    def test_missing_keldagrim_and_poison_inputs_fail_at_their_stage(self):
        state = self.seeded(giant_dwarf=False).snapshot()
        state["location_id"] = "location.keldagrim.smokin_joe"
        state["completed_action_ids"].append("quest.ratcatchers.report_king_rat")
        joe = self.validator.tables["actions"]["quest.ratcatchers.meet_smokin_joe"]
        with self.assertRaisesRegex(DataError, "required completed action"):
            self.apply(RouteState(self.validator.tables, self.profile["policies"], state), joe)
        state["location_id"] = "location.varrock.hooknosed_jack"
        state["completed_action_ids"].append("quest.ratcatchers.meet_jack")
        poison = self.validator.tables["actions"]["quest.ratcatchers.make_rat_poison"]
        state["inventory"].pop("item.red_spiders_eggs")
        with self.assertRaisesRegex(DataError, "required|consumes"):
            self.apply(RouteState(self.validator.tables, self.profile["policies"], state), poison)

    def test_new_local_travel_edges_are_bidirectional(self):
        pairs = {(e["from_location_id"], e["to_location_id"])
                 for e in self.edges if e["mode"] in ("walk", "ship")}
        self.assertTrue(pairs)
        for a, b in pairs:
            self.assertIn((b, a), pairs)

    def test_rat_pits_grouping_teleports_unlock_and_share_cooldown(self):
        port = self.validator.tables["travel_edges"]["travel.other.rat_pits.port_sarim.from_burthorpe"]
        varrock = self.validator.tables["travel_edges"]["travel.other.rat_pits.varrock.from_burthorpe"]
        before = self.seeded()
        with self.assertRaises(DataError):
            self.apply(before, port, travel=True)

        done = self.quest_steps(before)
        state = done.snapshot()
        state["location_id"] = "location.burthorpe.unferth"
        after = RouteState(self.validator.tables, self.profile["policies"], state)
        landed = self.apply(after, port, travel=True)
        self.assertEqual(landed.location, "location.port_sarim.rat_pits_entrance")

        state = landed.snapshot()
        state["location_id"] = "location.burthorpe.unferth"
        still_cooling = RouteState(self.validator.tables, self.profile["policies"], state)
        with self.assertRaises(DataError):
            self.apply(still_cooling, varrock, travel=True)

    def test_minas_claim_follows_tail_and_only_awards_kudos_once(self):
        claim = self.validator.tables["actions"]["museum.history.robert"]
        before = self.seeded().snapshot()
        before["location_id"] = "location.varrock_museum.historian_minas"
        with self.assertRaises(DataError):
            self.apply(RouteState(self.validator.tables, self.profile["policies"], before), claim)

        state = self.quest_steps(self.seeded()).snapshot()
        state["location_id"] = "location.varrock_museum.historian_minas"
        claimed = self.apply(RouteState(self.validator.tables, self.profile["policies"], state), claim)
        self.assertEqual(claimed.snapshot()["counters"]["token.museum.kudos"], 5)
        with self.assertRaises(DataError):
            self.apply(claimed, claim)


if __name__ == "__main__":
    unittest.main()
