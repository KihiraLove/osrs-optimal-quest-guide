"""Tests for Medium diary milestones, shared task credit and travel rewards."""

from pathlib import Path
import unittest

from quest_optimizer.data import Contracts, DataError, load_catalog, read_json
from quest_optimizer.reachability import unreachable_records
from quest_optimizer.semantics import CatalogValidator
from quest_optimizer.transitions import RouteState


ROOT = Path(__file__).resolve().parents[2]
LUMBRIDGE = "diary.lumbridge_draynor.medium"
VARROCK = "diary.varrock.medium"
LUM_CAST = f"{LUMBRIDGE}.task.varp_1194_17"
VAR_CAST = f"{VARROCK}.task.varp_1176_23"
VAR_BALLOON = f"{VARROCK}.task.varp_1176_27"
CABBAGE_CHARGES = "token.transport.explorers_ring_2.cabbage_charges"
CABBAGE = "travel.item.explorers_ring_2.cabbage."
GE_SPELL = "travel.spell.lumbridge.varrock_grand_exchange"
GE_TABLET = "travel.tablet.varrock.lumbridge_grand_exchange"


class MediumDiaryRouteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        contracts = Contracts(ROOT / "schemas")
        cls.catalog = load_catalog(ROOT / "data/manifest.json", contracts)
        cls.tables = CatalogValidator(cls.catalog, contracts).tables
        cls.profile = read_json(ROOT / "data/profiles/main-baseline.json")

    def seed(self, location, tier=None, *, missing=(), skills=None, items=None, flags=None, completed=()):
        initial = self.profile["initial_state"]
        registered = {**initial["flags"], **(flags or {})}
        if tier:
            for stage in (tier, tier.replace(".medium", ".easy")):
                for rule in self.tables["actions"][stage + ".complete"]["requirements"]["requirements"]:
                    if rule["token_id"] not in missing:
                        registered[rule["token_id"]] = True
        xp = {**initial["xp_tenths"]}
        for skill, level in (skills or {}).items():
            xp[skill] = self.tables["skills"][skill]["xp_thresholds_tenths"][level - 1]
        snapshot = {**initial, "location_id": location, "flags": registered,
                    "inventory": {**initial["inventory"], **(items or {})},
                    "xp_tenths": xp, "completed_action_ids": list(completed)}
        return RouteState(self.tables, self.profile["policies"], snapshot)

    def play(self, state, *ids):
        for record_id in ids:
            if record_id.startswith("travel."):
                record = self.tables["travel_edges"][record_id]
                step = {"kind": "travel", "edge_id": record_id}
            else:
                record = self.tables["actions"][record_id]
                step = {"kind": "action", "action_id": record_id}
                if record.get("planned_outcome"):
                    step["planned_outcome"] = record["planned_outcome"]
            step["modeled_seconds"] = record["duration"]["expected_seconds"]
            state = state.apply(step)
        return state

    def claim(self, state, tier):
        easy = tier.replace(".medium", ".easy")
        medium_claim = "claim." + tier
        state = self.play(state, tier + ".complete")
        with self.assertRaises(DataError):
            self.play(state, medium_claim)
        state = self.play(state, easy + ".complete", "claim." + easy, medium_claim)
        with self.assertRaisesRegex(DataError, "repeat limit"):
            self.play(state, medium_claim)
        return state

    def test_medium_tasks_and_claims_are_reachable_from_unseeded_lumbridge(self):
        unreachable = unreachable_records(self.catalog, self.profile)
        tasks = {record_id for record_id in self.tables["actions"]
                 if record_id.startswith((LUMBRIDGE + ".task.", VARROCK + ".task."))}
        claims = {"claim." + LUMBRIDGE, "claim." + VARROCK}
        milestones = {LUMBRIDGE + ".complete", VARROCK + ".complete"}
        self.assertEqual(len(tasks), 25)
        self.assertFalse((tasks | claims | milestones).intersection(unreachable["actions"]))
        self.assertFalse((claims | milestones).intersection(self.profile["goal_action_ids"]))

    def test_lumbridge_cast_counts_before_easy_and_claim_funds_three_shared_teleports(self):
        state = self.seed("location.al_kharid.bank_entrance", LUMBRIDGE, missing=("flag." + LUM_CAST,),
                          skills={"skill.magic": 39}, items={"item.law_rune": 1})
        state = self.play(state, LUM_CAST)
        self.assertTrue(state.flags["flag." + LUM_CAST])
        self.assertEqual(state.inventory["item.law_rune"], 0)
        with self.assertRaises(DataError):
            self.play(state, CABBAGE + "lumbridge")
        mikasi = "travel.walk.easy_diaries.lumbridge_diary_taskmaster_mikasi."
        state = self.claim(self.play(state, mikasi + "out"), LUMBRIDGE)
        self.assertEqual(state.inventory["item.explorers_ring_2"], 1)

        lamp = f"reward.{LUMBRIDGE}.antique_lamp"
        use = {"kind": "reward_use", "reward_id": lamp, "instance_id": lamp + ".instance.1",
               "skill_id": "skill.magic", "gain_xp_tenths": 75000, "overrides_observed_skill_restriction": False}
        with self.assertRaises(DataError):
            state.apply(use)
        before = state.xp["skill.magic"]
        level_40 = state.thresholds["skill.magic"][39]
        state = state.apply({"kind": "training", "skill_id": "skill.magic", "before_xp_tenths": before,
                             "gain_xp_tenths": level_40 - before, "after_xp_tenths": level_40,
                             "resume_location_id": state.location, "required_by": [lamp]}).apply(use)
        self.assertEqual(state.xp["skill.magic"], level_40 + 75000)

        to_draynor = (
            "travel.walk.medium_diaries.falador_farm_cabbage_teleport.back",
            "travel.walk.fairytale.south_falador_farm.back", "travel.walk.draynor.martin.back",
        )
        state = self.play(state, mikasi + "back", CABBAGE + "lumbridge")
        self.assertEqual(state.counters[CABBAGE_CHARGES], 2)
        state = self.play(state, *to_draynor, CABBAGE + "draynor")
        self.assertEqual(state.counters[CABBAGE_CHARGES], 1)
        state = self.play(state, *to_draynor, "travel.walk.port_sarim.draynor.back", CABBAGE + "port_sarim", *to_draynor)
        self.assertEqual(state.counters[CABBAGE_CHARGES], 0)
        with self.assertRaises(DataError):
            self.play(state, CABBAGE + "draynor")

    def test_varrock_balloon_and_spell_count_before_claim_and_unlock_both_ge_options(self):
        state = self.seed("location.balloon.entrana", VARROCK, missing=("flag." + VAR_BALLOON, "flag." + VAR_CAST),
                          skills={"skill.magic": 40, "skill.firemaking": 40},
                          items={"item.logs": 1, "item.willow_logs": 10, "item.law_rune": 2, "item.fire_rune": 2,
                                 "item.varrock_teleport_tablet": 1},
                          flags={"unlock.balloon.entrana": True, "unlock.balloon.taverley": True,
                                 "flag.travel.balloon_light_pack": True}, completed=("quest.enlightened_journey.complete",))
        state = self.play(state, "transport.balloon.varrock.unlock")
        self.assertFalse(state.flags.get("flag." + VAR_BALLOON))
        self.assertEqual(state.inventory["item.willow_logs"], 0)
        state = self.play(state, "travel.balloon.varrock.taverley", "travel.walk.taverley.varrock.out",
                          "travel.walk.lumbridge.varrock.back")
        self.assertTrue(state.flags["flag." + VAR_BALLOON])
        self.assertEqual(state.inventory["item.logs"], 0)
        for edge in (GE_SPELL, GE_TABLET):
            with self.assertRaises(DataError):
                self.play(state, edge)
        by_tablet = self.play(state, "travel.tablet.varrock.lumbridge")
        self.assertFalse(by_tablet.flags.get("flag." + VAR_CAST))
        before = state.xp["skill.magic"]
        state = self.play(state, "travel.spell.lumbridge.varrock")
        self.assertEqual(state.xp["skill.magic"], before + 350)
        self.assertTrue(state.flags["flag." + VAR_CAST])

        toby = "travel.walk.easy_diaries.varrock_diary_taskmaster_toby."
        state = self.claim(self.play(state, toby + "out"), VARROCK)
        self.assertEqual(state.inventory["item.varrock_armour_2"], 1)
        state = self.play(state, toby + "back", "travel.walk.lumbridge.varrock.back")
        by_tablet = self.play(state, GE_TABLET)
        by_spell = self.play(state, GE_SPELL)
        self.assertEqual(by_tablet.location, "location.varrock.grand_exchange")
        self.assertEqual(by_spell.location, by_tablet.location)
        self.assertEqual(by_tablet.inventory["item.varrock_teleport_tablet"], 0)
        self.assertEqual(by_spell.inventory["item.law_rune"], 0)
        self.assertEqual(by_spell.xp["skill.magic"], by_tablet.xp["skill.magic"] + 350)

    def test_mahogany_order_uses_twenty_logs_and_carried_coins(self):
        state = self.seed("location.varrock.grand_exchange", items={"item.coins": 32000})
        state = self.play(state, "supply.grand_exchange.varrock_medium_mahogany_logs",
                          "travel.walk.varrock.grand_exchange.back", "travel.walk.varrock.balloon.out",
                          "travel.walk.varrock.sawmill.out", f"{VARROCK}.task.varp_1176_25")
        self.assertEqual(state.inventory["item.coins"], 400)
        self.assertEqual(state.inventory["item.mahogany_logs"], 0)
        self.assertEqual(state.inventory["item.mahogany_plank"], 20)

    def test_zaff_shares_one_stock_window_between_tiers(self):
        easy_claim = "claim.diary.varrock.easy"
        medium_claim = "claim." + VARROCK
        easy_purchase = "supply.varrock.zaff_easy_diary_battlestaves"
        medium_purchase = "supply.varrock.zaff_medium_diary_battlestaves"
        state = self.seed("location.varrock.zaff", items={"item.coins": 315000}, completed=(easy_claim,))
        with self.assertRaises(DataError):
            self.play(state, medium_purchase)
        bought_easy = self.play(state, easy_purchase)
        for stock, initial in ((30, state.snapshot()), (None, bought_easy.snapshot())):
            initial["completed_action_ids"].append(medium_claim)
            initial["flags"]["flag.shop.zaff.medium_stock_unlocked"] = True
            upgraded = RouteState(self.tables, state.policies, initial)
            with self.assertRaises(DataError):
                self.play(upgraded, easy_purchase)
            if stock is None:
                with self.assertRaises(DataError):
                    self.play(upgraded, medium_purchase)
            else:
                bought_medium = self.play(upgraded, medium_purchase)
                self.assertEqual(bought_medium.inventory["item.battlestaff"], stock)
                self.assertEqual(bought_medium.inventory["item.coins"], 105000)
