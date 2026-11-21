"""Replay two Easy diaries against the committed build-242 catalog."""

from collections import defaultdict, deque
from pathlib import Path
import unittest

from quest_optimizer.data import Contracts, DataError, load_catalog, read_json
from quest_optimizer.reachability import unreachable_records
from quest_optimizer.semantics import CatalogValidator
from quest_optimizer.transitions import RouteState


ROOT = Path(__file__).resolve().parents[2]
LUMBRIDGE = "diary.lumbridge_draynor.easy"
VARROCK = "diary.varrock.easy"


def lumbridge_task(bit):
    return f"{LUMBRIDGE}.task.varp_1194_{bit}"


def varrock_task(bit):
    return f"{VARROCK}.task.varp_1176_{bit}"


class EasyDiaryRouteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        contracts = Contracts(ROOT / "schemas")
        cls.catalog = load_catalog(ROOT / "data/manifest.json", contracts)
        cls.tables = CatalogValidator(cls.catalog, contracts).tables
        cls.profile = read_json(ROOT / "data/profiles/main-baseline.json")
        cls.free_edges = defaultdict(list)
        for edge in cls.catalog["travel_edges"]:
            if (edge["mode"] in ("walk", "other") and not edge["consumes"] and not edge["effects"]
                    and edge["requirements"] == {"kind": "all", "requirements": []}
                    and "repeat_limit" not in edge):
                cls.free_edges[edge["from_location_id"]].append(edge)

    def travel_to(self, state, destination):
        queue = deque([(state.location, [])])
        seen = {state.location}
        while queue:
            location, path = queue.popleft()
            if location == destination:
                for edge in path:
                    state = state.apply({"kind": "travel", "edge_id": edge["id"],
                                         "modeled_seconds": edge["duration"]["expected_seconds"]})
                return state
            for edge in self.free_edges[location]:
                arrival = edge["to_location_id"]
                if arrival not in seen:
                    seen.add(arrival)
                    queue.append((arrival, [*path, edge]))
        self.fail(f"No free path from {state.location} to {destination}")

    def play(self, state, *record_ids):
        for record_id in record_ids:
            if record_id.startswith("travel."):
                record = self.tables["travel_edges"][record_id]
                state = self.travel_to(state, record["from_location_id"])
                step = {"kind": "travel", "edge_id": record_id}
            else:
                record = self.tables["actions"][record_id]
                state = self.travel_to(state, record["start_location_id"])
                step = {"kind": "action", "action_id": record_id}
                if "planned_outcome" in record:
                    step["planned_outcome"] = record["planned_outcome"]
            step["modeled_seconds"] = record["duration"]["expected_seconds"]
            state = state.apply(step)
        return state

    def train_to(self, state, skill, level, required_by):
        skill_id = "skill." + skill
        before = state.xp[skill_id]
        after = state.thresholds[skill_id][level - 1]
        return state.apply({"kind": "training", "skill_id": skill_id, "before_xp_tenths": before,
                            "gain_xp_tenths": after - before, "after_xp_tenths": after,
                            "resume_location_id": state.location, "required_by": [required_by]})

    def test_all_tasks_are_reachable_and_quest_goals_leave_claims_optional(self):
        unreachable = unreachable_records(self.catalog, self.profile)
        diary_actions = {row["id"] for row in self.catalog["actions"]
                         if row["id"].startswith((LUMBRIDGE, VARROCK, "claim." + LUMBRIDGE, "claim." + VARROCK))}
        self.assertEqual(len(diary_actions), 30)
        self.assertEqual(diary_actions.intersection(unreachable["actions"]), set())
        claims = {"claim." + tier for tier in (LUMBRIDGE, VARROCK)}
        milestones = {tier + ".complete" for tier in (LUMBRIDGE, VARROCK)}
        goals = set(self.profile["goal_action_ids"])
        self.assertEqual((claims | milestones).intersection(goals), set())
        without_claims = {**self.catalog, "actions": [
            row for row in self.catalog["actions"] if row["id"] not in claims | milestones
        ]}
        still_unreachable = unreachable_records(without_claims, self.profile)
        self.assertEqual(goals.intersection(still_unreachable["actions"]), goals.intersection(unreachable["actions"]))

    def test_task_progress_claims_and_two_level_gated_lamps(self):
        initial = {**self.profile["initial_state"], "completed_action_ids": [
            "quest.cooks_assistant.complete", "quest.rune_mysteries.complete", "quest.demon_slayer.complete",
            "quest.merlins_crystal.complete", "quest.shield_of_arrav.complete", "quest.priest_in_peril.complete",
            "miniquest.enter_the_abyss.collect_orb",
        ]}
        # The orb is held partway through Enter the Abyss. Other supplies come from the route.
        initial["inventory"] = {**initial["inventory"], "item.scrying_orb.empty": 1}
        state = RouteState(self.tables, self.profile["policies"], initial)
        with self.assertRaises(DataError):
            self.play(state, VARROCK + ".complete")
        with self.assertRaises(DataError):
            self.play(state, "claim." + LUMBRIDGE)

        state = self.play(state, "stronghold.security.claim_war", varrock_task(5), "stronghold.security.claim_famine",
                          "travel.walk.stronghold.pestilence", "stronghold.security.claim_pestilence",
                          "travel.walk.stronghold.pestilence_exit", "supply.grand_exchange.purchase_lumbridge_easy_supplies",
                          "supply.grand_exchange.purchase_varrock_easy_supplies")
        self.assertEqual(state.inventory["item.coins"], 8300)
        for skill, level, gate in (
            ("agility", 13, varrock_task(6)), ("crafting", 8, varrock_task(10)),
            ("fishing", 20, varrock_task(13)), ("mining", 15, varrock_task(3)),
            ("runecraft", 9, varrock_task(12)), ("thieving", 5, varrock_task(14)),
            ("woodcutting", 15, lumbridge_task(7)), ("firemaking", 15, lumbridge_task(7)),
        ):
            state = self.train_to(state, skill, level, gate)

        state = self.play(state, "miniquest.enter_the_abyss.visit_aubury", "miniquest.enter_the_abyss.visit_sedridor")
        self.assertTrue(state.flags["flag." + varrock_task(2)])
        self.assertTrue(state.flags["flag." + lumbridge_task(3)])
        with self.assertRaises(DataError):
            self.play(state, varrock_task(2))

        quiz_start = "museum.natural_history_quiz.start"
        plaques = sorted(record_id for record_id in self.tables["actions"]
                         if record_id.startswith("museum.natural_history_quiz.") and record_id != quiz_start)
        state = self.play(state, quiz_start, *plaques, "claim.museum.natural_history_quiz",
                          "museum.history.runes", "museum.history.silverlight", "museum.history.excalibur", "museum.history.soa")
        self.assertEqual(state.counters["token.museum.kudos"], 48)
        with self.assertRaises(DataError):
            self.play(state, varrock_task(11))
        state = self.play(state, "museum.history.salveknights", varrock_task(11))
        self.assertEqual(state.counters["token.museum.kudos"], 53)

        state = self.play(state, varrock_task(1), varrock_task(3), varrock_task(6), varrock_task(7), varrock_task(4),
                          varrock_task(8), varrock_task(9), varrock_task(10), "travel.altar.earth.enter", varrock_task(12),
                          "travel.altar.earth.exit", varrock_task(13), varrock_task(14), VARROCK + ".complete", "claim." + VARROCK)
        self.assertEqual(state.inventory["item.varrock_armour_1"], 1)
        self.assertEqual(state.inventory["item.coins"], 8150)
        self.assertEqual(state.inventory["item.plank"], 1)
        with self.assertRaises(DataError):
            self.play(state, "claim." + VARROCK)

        ham = "travel.walk.dorgeshuun.hamsurface_hamroom."
        state = self.play(state, ham + "out", ham + "back")
        self.assertTrue(state.flags["flag." + lumbridge_task(12)])
        with self.assertRaises(DataError):
            self.play(state, lumbridge_task(12))
        state = self.play(state, lumbridge_task(1), "supply.lumbridge.light_dorgeshuun_candle",
                          "supply.lumbridge_swamp_caves.attach_rope", "travel.tears_of_guthix.down")
        with self.assertRaises(DataError):
            self.play(state, "travel.tears_of_guthix.toward_juna")
        state = self.play(state, "travel.walk.easy_diaries.cavebug.out", lumbridge_task(2), "travel.walk.easy_diaries.cavebug.back",
                          "travel.tears_of_guthix.up", "travel.altar.water.enter", lumbridge_task(4),
                          "travel.altar.water.exit", lumbridge_task(5), lumbridge_task(6), lumbridge_task(7),
                          lumbridge_task(8), lumbridge_task(9), lumbridge_task(10), lumbridge_task(11),
                          LUMBRIDGE + ".complete", "claim." + LUMBRIDGE)
        self.assertEqual(state.inventory["item.explorers_ring_1"], 1)
        self.assertEqual(state.inventory["item.rune_essence"], 0)
        with self.assertRaises(DataError):
            self.play(state, "claim." + LUMBRIDGE)

        lamps = [f"reward.{tier}.antique_lamp" for tier in (LUMBRIDGE, VARROCK)]
        state = self.train_to(state, "magic", 29, lamps[0])
        start_xp = state.thresholds["skill.magic"][29]
        for reward in lamps:
            use = {"kind": "reward_use", "reward_id": reward, "instance_id": f"{reward}.instance.1",
                   "skill_id": "skill.magic", "gain_xp_tenths": 25000, "overrides_observed_skill_restriction": False}
            if reward == lamps[0]:
                with self.assertRaises(DataError):
                    state.apply(use)
                state = self.train_to(state, "magic", 30, reward)
            state = state.apply(use)
            with self.assertRaises(DataError):
                state.apply(use)
        self.assertEqual(state.xp["skill.magic"], start_xp + 50000)
        self.assertFalse({row["reward_id"] for row in state.snapshot()["held_rewards"]}.intersection(lamps))

    def test_zaff_stock_opens_after_the_claim_and_costs_carried_gp(self):
        initial = {**self.profile["initial_state"], "completed_action_ids": [VARROCK + ".complete"]}
        initial["inventory"] = {**initial["inventory"], "item.coins": 105000}
        state = RouteState(self.tables, self.profile["policies"], initial)
        purchase = "supply.varrock.zaff_easy_diary_battlestaves"
        with self.assertRaises(DataError):
            self.play(state, purchase)
        state = self.play(state, "claim." + VARROCK, purchase)
        self.assertEqual(state.inventory["item.coins"], 0)
        self.assertEqual(state.inventory["item.battlestaff"], 15)
        with self.assertRaisesRegex(DataError, "repeat limit"):
            self.play(state, purchase)
