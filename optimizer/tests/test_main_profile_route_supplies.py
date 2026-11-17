"""Replays for the previously blocked quest, funding and balloon routes."""

from collections import defaultdict, deque
from pathlib import Path
import unittest

from quest_optimizer.data import Contracts, DataError, load_catalog, read_json
from quest_optimizer.reachability import unreachable_records
from quest_optimizer.semantics import CatalogValidator
from quest_optimizer.transitions import RouteState


ROOT = Path(__file__).resolve().parents[2]
GE = "location.varrock.grand_exchange"
LAP = "supply.agility_pyramid.sell_course_top"
BALLOONS = {"crafting_guild": "oak_logs", "varrock": "willow_logs", "castle_wars": "yew_logs",
            "grand_tree": "magic_logs"}


class MainProfileRouteSuppliesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        contracts = Contracts(ROOT / "schemas")
        cls.catalog = load_catalog(ROOT / "data/manifest.json", contracts)
        cls.tables = CatalogValidator(cls.catalog, contracts).tables
        cls.profile = read_json(ROOT / "data/profiles/main-baseline.json")
        cls.free_edges = defaultdict(list)
        for edge in cls.tables["travel_edges"].values():
            if (edge["mode"] in ("walk", "other") and not edge["consumes"]
                    and not edge["effects"] and "repeat_limit" not in edge
                    and edge["requirements"] == {"kind": "all", "requirements": []}):
                cls.free_edges[edge["from_location_id"]].append(edge)

    def execute(self, state, *record_ids):
        for record_id in record_ids:
            if record_id.startswith("travel."):
                record = self.tables["travel_edges"][record_id]
                step = {"kind": "travel", "edge_id": record_id}
            else:
                record = self.tables["actions"][record_id]
                step = {"kind": "action", "action_id": record_id}
                if "planned_outcome" in record:
                    step["planned_outcome"] = record["planned_outcome"]
            step["modeled_seconds"] = record["duration"]["expected_seconds"]
            state = state.apply(step)
        return state

    def follow_free_path(self, state, destination):
        queue = deque([(state.location, [])])
        seen = {state.location}
        while queue:
            waypoint, route = queue.popleft()
            if waypoint == destination:
                return self.execute(state, *route)
            for edge in self.free_edges[waypoint]:
                arrival = edge["to_location_id"]
                if arrival not in seen:
                    seen.add(arrival)
                    queue.append((arrival, [*route, edge["id"]]))
        self.fail(f"No free path from {state.location} to {destination}")

    def stronghold_to_exchange(self, **prior_progress):
        initial = {**self.profile["initial_state"], **prior_progress}
        state = RouteState(self.tables, self.profile["policies"], initial)
        state = self.follow_free_path(state, "location.barbarian_village.stronghold_entrance")
        return self.execute(state,
                            "travel.walk.stronghold.war", "stronghold.security.claim_war",
                            "diary.varrock.easy.task.varp_1176_5", "travel.walk.stronghold.famine",
                            "stronghold.security.claim_famine", "travel.walk.stronghold.pestilence",
                            "stronghold.security.claim_pestilence", "travel.walk.stronghold.pestilence_exit",
                            "travel.walk.stronghold.ge.out")

    def train_to(self, state, skill, level, required_by):
        before = state.xp[skill]
        after = state.thresholds[skill][level - 1]
        return state.apply({"kind": "training", "skill_id": skill, "before_xp_tenths": before,
                            "gain_xp_tenths": after - before, "after_xp_tenths": after,
                            "resume_location_id": state.location, "required_by": [required_by]})

    def test_goals_and_balloon_network_are_reachable_from_the_main_profile(self):
        unreachable = unreachable_records(self.catalog, self.profile)
        goals = {"quest.imp_catcher.complete", "quest.monks_friend.complete", "miniquest.family_pest.complete",
                 "miniquest.mage_arena_ii.complete", LAP, *(f"transport.balloon.{stop}.unlock" for stop in BALLOONS)}
        self.assertFalse(goals.intersection(unreachable["actions"]))
        self.assertFalse([edge_id for edge_id in unreachable["travel_edges"] if edge_id.startswith("travel.balloon.")])

    def test_imp_catcher_and_monks_friend_with_earned_coins_and_public_travel(self):
        state = self.stronghold_to_exchange()
        self.assertEqual(state.inventory["item.coins"], 10000)
        state = self.execute(state, "supply.grand_exchange.purchase_imp_catcher_beads",
                             "supply.grand_exchange.purchase_monks_friend_supplies")
        self.assertEqual(state.inventory["item.coins"], 4750)
        state = self.follow_free_path(state, "location.wizards_tower.ground_ladder")
        state = self.execute(state, "travel.walk.wizards_tower.mizgog_stairs.out", "quest.imp_catcher.complete",
                             "travel.walk.wizards_tower.mizgog_stairs.back")
        self.assertEqual(state.inventory["item.amulet_of_accuracy"], 1)
        self.assertTrue(all(state.inventory[f"item.{color}_bead"] == 0 for color in ("black", "red", "white", "yellow")))

        state = self.follow_free_path(state, "location.ardougne_monastery.omad")
        state = self.execute(state, "quest.monks_friend.start", "travel.walk.kandarin.blanket_ladder.out",
                             "travel.walk.kandarin.blanket_cellar.out", "quest.monks_friend.take_blanket",
                             "travel.walk.kandarin.blanket_cellar.back", "travel.walk.kandarin.blanket_ladder.back",
                             "quest.monks_friend.return_blanket", "travel.walk.kandarin.cedric.out",
                             "quest.monks_friend.help_cedric", "travel.walk.kandarin.cedric.back",
                             "quest.monks_friend.complete")
        self.assertEqual(state.inventory["item.law_rune"], 8)
        self.assertEqual(state.inventory["item.jug_of_water"], 0)
        self.assertEqual(state.inventory["item.logs"], 0)
        self.assertEqual(state.counters["token.quest_points"], 3)

    def test_balloon_purchases_cover_discoveries_and_routine_fares(self):
        for stop, log_item in BALLOONS.items():
            with self.subTest(stop=stop):
                state = self.stronghold_to_exchange(
                    completed_action_ids=["quest.enlightened_journey.build_basket", "quest.enlightened_journey.complete"],
                    flags={**self.profile["initial_state"]["flags"], "unlock.balloon.entrana": True,
                           "unlock.balloon.taverley": True},
                )
                unlock = f"transport.balloon.{stop}.unlock"
                state = self.train_to(state, "skill.firemaking", 60, unlock)
                state = self.execute(state, f"supply.grand_exchange.purchase_balloon_{log_item}",
                                     "supply.grand_exchange.purchase_balloon_logs")
                state = self.follow_free_path(state, "location.port_sarim.deposit_box")
                state = self.execute(state, "supply.bank.deposit_entrana_gear", "travel.walk.port_sarim.deposit_box.back",
                                     "travel.ship.port_sarim.entrana", "supply.enlightened_journey.prepare_balloon_loadout")
                regular = f"travel.balloon.entrana.{stop}"
                with self.assertRaises(DataError):
                    self.execute(state, regular)
                fuel_before = state.inventory[f"item.{log_item}"]
                state = self.execute(state, unlock, f"travel.balloon.{stop}.entrana", regular)
                self.assertEqual(state.location, f"location.balloon.{stop}")
                self.assertEqual(state.inventory["item.logs"], 2)
                setup_logs = 3 if stop == "grand_tree" else 10
                self.assertEqual(state.inventory[f"item.{log_item}"], fuel_before - setup_logs - 1)

    def test_pyramid_proceeds_pay_both_miniquest_budgets(self):
        state = self.stronghold_to_exchange(
            completed_action_ids=["quest.family_crest.complete", "miniquest.mage_arena_i.complete"],
        )
        with self.assertRaises(DataError):
            self.execute(state, "supply.maii.ge_runes")
        state = self.train_to(state, "skill.agility", 30, LAP)
        state = self.train_to(state, "skill.magic", 75, "miniquest.mage_arena_ii.start")
        for _ in range(13):
            state = self.execute(state, "supply.grand_exchange.purchase_agility_pyramid_supplies")
            state = self.follow_free_path(state, "location.shantay_pass.north_gate")
            state = self.execute(state, "travel.walk.shantay.buy_and_use_pass", "travel.walk.sophanem.south_gate_wanderer.out",
                                 "travel.walk.desert.agility_pyramid.out")
            state = self.execute(state, *([LAP] * 8))
            self.assertEqual(state.inventory["item.lobster"], 0)
            state = self.execute(state, "travel.walk.desert.agility_pyramid.back", "travel.walk.sophanem.south_gate_wanderer.back",
                                 "travel.walk.shantay.leave_desert")
            self.assertEqual(state.inventory["item.waterskin_4"], 0)
            state = self.follow_free_path(state, GE)

        self.assertEqual(state.inventory["item.coins"], 1025235)
        state = self.execute(state, "supply.maii.ge_runes")
        for suffix in ("start", "talk_to_avan", "talk_to_caleb", "talk_to_johnathon", "complete"):
            action_id = f"miniquest.family_pest.{suffix}"
            state = self.follow_free_path(state, self.tables["actions"][action_id]["start_location_id"])
            state = self.execute(state, action_id)
        self.assertTrue(state.flags["unlock.family_pest_gauntlets"])

        state = self.follow_free_path(state, "location.ardougne.wilderness_lever")
        state = self.execute(state, "travel.other.mage_arena_i.ardougne_lever", "travel.other.mage_arena_i.cut_webs_to_bank",
                             "travel.other.mage_arena_i.enter_mage_bank", "travel.walk.mage_arena_i.leg_2.out",
                             "travel.other.mage_arena_i.enter_statue_chamber", "claim.mage_arena_i.saradomin_cape",
                             "travel.walk.mage_arena_i.leg_3.out", "claim.mage_arena_i.saradomin_staff",
                             "supply.maii.buy_staves_after_saradomin", "travel.walk.mage_arena_i.leg_3.back",
                             "travel.other.mage_arena_i.exit_statue_chamber", "travel.walk.mage_arena_i.leg_2.back",
                             "travel.other.mage_arena_i.exit_mage_bank", "travel.combat_miniquests.maii.training.out",
                             "train.maii.saradomin_outside", "train.maii.zamorak_outside", "train.maii.guthix_outside",
                             "travel.combat_miniquests.maii.training.back", "travel.other.mage_arena_i.enter_mage_bank",
                             "miniquest.mage_arena_ii.start")
        for boss in ("zachariah", "porazdir", "derwen"):
            state = self.execute(state, "travel.other.mage_arena_i.exit_mage_bank", f"travel.combat_miniquests.maii.{boss}.out",
                                 f"miniquest.mage_arena_ii.track_{boss}", f"miniquest.mage_arena_ii.defeat_{boss}",
                                 f"travel.combat_miniquests.maii.{boss}.back", "travel.other.mage_arena_i.enter_mage_bank",
                                 f"miniquest.mage_arena_ii.deliver_{boss}")
        state = self.execute(state, "miniquest.mage_arena_ii.complete")
        self.assertEqual(state.inventory["item.coins"], 25235)
        self.assertEqual(state.inventory["item.blood_rune"], 140)
        self.assertEqual(state.inventory["item.lobster"], 15)
        self.assertTrue(state.flags["unlock.mage_arena_ii_imbued_capes"])
