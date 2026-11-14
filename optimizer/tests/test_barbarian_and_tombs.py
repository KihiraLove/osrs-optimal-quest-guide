"""Connected route replay and reward checks for Otto and Maisa miniquests."""

from collections import defaultdict, deque
from pathlib import Path
import unittest

from quest_optimizer.data import Contracts, DataError, load_catalog, read_json
from quest_optimizer.semantics import CatalogValidator
from quest_optimizer.transitions import RouteState


ROOT = Path(__file__).resolve().parents[2]
BARB = "miniquest.barbarian_training"
TOMBS = "miniquest.into_the_tombs"
PATHS = ("apmeken", "crondis", "het", "scabaras")


class BarbarianAndTombsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        contracts = Contracts(ROOT / "schemas")
        cls.tables = CatalogValidator(load_catalog(ROOT / "data/manifest.json", contracts), contracts).tables
        cls.profile = read_json(ROOT / "data/profiles/main-baseline.json")
        cls.actions = read_json(ROOT / "data/catalog/barbarian-and-tombs/actions.json")
        cls.new_edges = read_json(ROOT / "data/catalog/barbarian-and-tombs/travel_edges.json")
        cls.travel = defaultdict(list)
        for edge in cls.tables["travel_edges"].values():
            if edge["mode"] in ("walk", "other", "ship", "lever", "fairy_ring", "teleport"):
                cls.travel[edge["from_location_id"]].append(edge)

    def seeded_barbarian(self, *, tamayu=True, missing_chewed_setup=False, fishing_level=55):
        start = read_json(ROOT / "data/profiles/main-baseline.json")["initial_state"]
        start["location_id"] = "location.bt.otto"
        start["completed_action_ids"] = ["quest.druidic_ritual.complete"]
        start["flags"] = {"flag.barbarian.tamayu_combat_claimed": tamayu}
        start["inventory"] = {"item.shortbow": 1, "item.knife": 1, "item.feather": 1,
                              "item.oak_logs": 1, "item.logs": 3, "item.bronze_bar": 2,
                              "item.bronze_axe": 1, "item.hammer": 1, "item.tinderbox": 1,
                              "item.potato_seed": 3, "item.oak_sapling": 1, "item.spade": 1,
                              "item.attack_potion_2": 1}
        if missing_chewed_setup:
            start["inventory"].pop("item.tinderbox")
        for skill, lv in (("fishing", fishing_level), ("agility", 15), ("strength", 35),
                          ("firemaking", 35), ("farming", 15), ("crafting", 11),
                          ("smithing", 5), ("herblore", 4)):
            start["xp_tenths"]["skill." + skill] = self.tables["skills"]["skill." + skill]["xp_thresholds_tenths"][lv - 1]
        return RouteState(self.tables, self.profile["policies"], start)

    def seeded_tombs(self):
        start = read_json(ROOT / "data/profiles/main-baseline.json")["initial_state"]
        start["location_id"] = "location.bcs.jaltevas_pyramid"
        start["completed_action_ids"] = ["quest.beneath_cursed_sands.complete"]
        start["flags"] = {"unlock.necropolis_akp": True}
        start["inventory"] = {}
        return RouteState(self.tables, self.profile["policies"], start)

    def apply(self, state, record, *, traveling=False):
        instruction = {"kind": "travel" if traveling else "action",
                       "edge_id" if traveling else "action_id": record["id"],
                       "modeled_seconds": record["duration"]["expected_seconds"]}
        if "planned_outcome" in record:
            instruction["planned_outcome"] = record["planned_outcome"]
        return state.apply(instruction)

    def arrive(self, state, target):
        if state.location == target:
            return state
        todo = deque([state])
        seen = {state.location}
        while todo:
            current = todo.popleft()
            for edge in self.travel[current.location]:
                if edge["to_location_id"] in seen:
                    continue
                try:
                    progressed = self.apply(current, edge, traveling=True)
                except DataError:
                    continue
                if progressed.location == target:
                    return progressed
                seen.add(progressed.location)
                todo.append(progressed)
        self.fail(f"No route from {state.location} to {target} through {len(seen)} reachable nodes")

    def do(self, state, ident):
        action = self.tables["actions"][ident]
        return self.apply(self.arrive(state, action["start_location_id"]), action)

    def barbarian(self, state):
        for action in self.actions:
            if action["activity_id"] == BARB:
                state = self.do(state, action["id"])
        return state

    def tombs(self, state, path_order=PATHS):
        state = self.do(state, TOMBS + ".start")
        state = self.do(state, TOMBS + ".entry_raid")
        for path in path_order:
            for key in ("enter_", "puzzle_", "defeat_"):
                state = self.do(state, TOMBS + "." + key + path)
        for key in ("enter_wardens", "wardens_orbs", "wardens_combat", "wardens_final",
                    "chest", "complete"):
            state = self.do(state, TOMBS + "." + key)
        return state

    def test_complete_training_and_individual_unlocks(self):
        original = self.seeded_barbarian()
        completed = self.barbarian(original)
        snap = completed.snapshot()
        self.assertIn(BARB + ".complete", snap["completed_action_ids"])
        for suffix in ("rod_fishing", "barehand_fishing", "bow_firemaking", "pyre_ships",
                       "seed_planting", "pot_smashing", "spears", "hastae", "herblore"):
            self.assertTrue(snap["flags"]["flag.barbarian." + suffix])
        self.assertTrue(snap["flags"]["unlock.ancient_cavern"])
        self.assertEqual(snap["xp_tenths"]["skill.smithing"] - original.xp["skill.smithing"], 500)
        self.assertEqual(snap["counters"]["token.quest_points"], original.counters["token.quest_points"])
        self.assertNotIn("item.chewed_bones", snap["inventory"])
        with self.assertRaises(DataError):
            self.do(completed, BARB + ".complete")

    def test_tamayu_and_fishing_gate(self):
        action = self.tables["actions"][BARB + ".learn_spears"]
        state = self.seeded_barbarian(tamayu=False).snapshot()
        state["completed_action_ids"].extend([BARB + ".report_rod", BARB + ".report_hand"])
        with self.assertRaises(DataError):
            self.apply(RouteState(self.tables, self.profile["policies"], state), action)
        fish = self.tables["actions"][BARB + ".catch_tuna"]
        state = self.seeded_barbarian(fishing_level=54).snapshot()
        state["completed_action_ids"].append(BARB + ".learn_hand")
        state["location_id"] = fish["start_location_id"]
        with self.assertRaises(DataError):
            self.apply(RouteState(self.tables, self.profile["policies"], state), fish)

    def test_cavern_gate_and_one_way_escape(self):
        whirlpool = next(e for e in self.new_edges if e["from_location_id"] == "location.bt.whirlpool"
                         and e["to_location_id"] == "location.bt.ancient_lower")
        start = self.seeded_barbarian().snapshot()
        start["location_id"] = "location.bt.whirlpool"
        with self.assertRaises(DataError):
            self.apply(RouteState(self.tables, self.profile["policies"], start), whirlpool, traveling=True)
        start["flags"]["unlock.ancient_cavern"] = True
        with self.assertRaises(DataError):
            self.apply(RouteState(self.tables, self.profile["policies"], start), whirlpool, traveling=True)
        start["completed_action_ids"].append(BARB + ".learn_pyre")
        entered = self.apply(RouteState(self.tables, self.profile["policies"], start), whirlpool, traveling=True)
        self.assertEqual(entered.location, "location.bt.ancient_lower")
        self.assertFalse(any(e["from_location_id"] == "location.bt.ancient_lower" and
                             e["to_location_id"] == "location.bt.whirlpool" for e in self.new_edges))

    def test_complete_tombs_with_all_guardians_and_single_lamp(self):
        done = self.tombs(self.seeded_tombs())
        snapshot = done.snapshot()
        self.assertIn(TOMBS + ".complete", snapshot["completed_action_ids"])
        self.assertEqual(len(snapshot["held_rewards"]), 1)
        self.assertEqual(snapshot["held_rewards"][0]["reward_id"], "reward.into_the_tombs.combat_lamp")
        self.assertTrue(snapshot["flags"]["unlock.toa_repeatable_raids"])
        self.assertTrue(snapshot["flags"]["unlock.toa_ancient_key"])
        with self.assertRaises(DataError):
            self.do(done, TOMBS + ".complete")

    def test_tombs_paths_independent_but_wardens_require_all(self):
        state = self.seeded_tombs()
        state = self.do(state, TOMBS + ".start")
        state = self.do(state, TOMBS + ".entry_raid")
        for path in reversed(PATHS[1:]):
            for verb in ("enter_", "puzzle_", "defeat_"):
                state = self.do(state, TOMBS + "." + verb + path)
        with self.assertRaises(DataError):
            self.apply(state, self.tables["actions"][TOMBS + ".enter_wardens"])
        for verb in ("enter_", "puzzle_", "defeat_"):
            state = self.do(state, TOMBS + "." + verb + PATHS[0])
        state = self.do(state, TOMBS + ".enter_wardens")
        self.assertEqual(state.location, "location.bt.toa_warden")

    def test_barbarian_cave_walks_reversible_except_drop_and_raft(self):
        pairs = {(e["from_location_id"], e["to_location_id"])
                 for e in self.new_edges if e["mode"] == "walk"}
        for x, y in pairs:
            self.assertIn((y, x), pairs)


if __name__ == "__main__":
    unittest.main()
