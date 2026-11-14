"""Graph-navigated Enakhra's Lament replay and Camulet charge constraints."""

from collections import deque
from pathlib import Path
import unittest

from quest_optimizer.data import Contracts, DataError, load_catalog, read_json
from quest_optimizer.semantics import CatalogValidator
from quest_optimizer.transitions import RouteState


ROOT = Path(__file__).resolve().parents[2]
QUEST = "quest.enakhras_lament."


class EnakhrasLamentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        contracts = Contracts(ROOT / "schemas")
        catalog = load_catalog(ROOT / "data/manifest.json", contracts)
        cls.tables = CatalogValidator(catalog, contracts).tables
        cls.profile = read_json(ROOT / "data/profiles/main-baseline.json")
        cls.connections = {}
        for edge_id, edge in cls.tables["travel_edges"].items():
            cls.connections.setdefault(edge["from_location_id"], []).append((edge_id, edge["to_location_id"]))

    def seed(self, location="location.enakhra.lazim"):
        data = {**self.profile["initial_state"]}
        data["location_id"] = location
        data["xp_tenths"] = {key: 5000000 for key in data["xp_tenths"]}
        data["inventory"] = {**data["inventory"], **{
            "item.sandstone_10kg": 5, "item.sandstone_2kg": 1,
            "item.granite_5kg": 2, "item.soft_clay": 2,
            "item.bread": 1, "item.chisel": 1, "item.tinderbox": 1,
            "item.lit_candle": 1, "item.coal": 1,
            "item.logs": 1, "item.oak_logs": 1, "item.willow_logs": 1, "item.maple_logs": 1,
            "item.air_rune": 7, "item.fire_rune": 4,
            "item.earth_rune": 2, "item.chaos_rune": 3
        }}
        return RouteState(self.tables, self.profile["policies"], data)

    def transition(self, state, key):
        is_edge = key.startswith("travel.")
        record = self.tables["travel_edges" if is_edge else "actions"][key]
        step = {"kind": "travel" if is_edge else "action",
                "edge_id" if is_edge else "action_id": key,
                "modeled_seconds": record["duration"]["expected_seconds"]}
        if record.get("planned_outcome"):
            step["planned_outcome"] = record["planned_outcome"]
        return state.apply(step, key)

    def move(self, state, target):
        current = state.snapshot()["location_id"]
        if current == target:
            return state
        queue = deque([(current, ())])
        seen = {current}
        while queue:
            source, prefix = queue.popleft()
            for edge, destination in sorted(self.connections.get(source, ())):
                if destination in seen:
                    continue
                probe = RouteState(self.tables, self.profile["policies"], state.snapshot())
                try:
                    for part in (*prefix, edge):
                        probe = self.transition(probe, part)
                except DataError:
                    continue
                path = (*prefix, edge)
                if destination == target:
                    for part in path:
                        state = self.transition(state, part)
                    return state
                seen.add(destination)
                queue.append((destination, path))
        self.fail(f"Could not travel from {current} to {target}")

    def act(self, state, name):
        aid = name if name.startswith("supply.") else QUEST + name
        record = self.tables["actions"][aid]
        state = self.move(state, record["start_location_id"])
        return self.transition(state, aid)

    def test_stone_temples_four_puzzles_and_camulet_charges(self):
        state = self.seed()
        ordered = (
            "start", "give_base_sandstone", "chisel_base", "place_base",
            "give_body_sandstone", "chisel_body", "place_body", "ask_head",
            "chisel_first_head", "place_first_head", "enter_temple",
            "meet_lazim_below", "chisel_four_limbs", "recover_stone_head",
            "sigil_m", "sigil_z", "sigil_k", "sigil_r",
            "place_four_sigils", "mould_head", "chisel_second_head", "fit_head",
            "feed_pentyn", "clear_furnace", "thaw_fountain",
            "light_brazier_logs", "light_brazier_oak", "light_brazier_willow",
            "light_brazier_maple", "light_brazier_candle", "light_brazier_coal",
            "finish_four_puzzles", "pass_barrier", "crumble_boneguard",
            "protect_and_talk", "collect_wall_rubble", "repair_wall", "complete"
        )
        for stage in ordered:
            state = self.act(state, stage)
        snapshot = state.snapshot()
        self.assertEqual(snapshot["counters"]["token.quest_points"], 3)
        self.assertEqual(snapshot["counters"]["charge.enakhra_camulet"], 4)
        self.assertEqual(snapshot["inventory"]["item.camulet"], 1)
        for item in ("sandstone_10kg", "sandstone_2kg", "granite_5kg",
                     "air_rune", "fire_rune", "earth_rune", "chaos_rune"):
            self.assertEqual(snapshot["inventory"].get("item." + item, 0), 0, item)
        self.assertEqual(snapshot["xp_tenths"]["skill.magic"], 5070605)
        for skill_name in ("crafting", "mining", "firemaking"):
            self.assertEqual(snapshot["xp_tenths"]["skill." + skill_name], 5070000)
        with self.assertRaises(DataError):
            self.transition(state, QUEST + "complete")

        state = self.act(state, "make_camel_mask")
        self.assertEqual(state.snapshot()["inventory"]["item.camel_mask"], 1)
        with self.assertRaises(DataError):
            self.transition(state, QUEST + "make_camel_mask")

        state = self.move(state, "location.al_kharid.bank_entrance")
        first = self.transition(state, "travel.enakhra.camulet.al_kharid")
        self.assertEqual(first.snapshot()["location_id"], "location.enakhra.bottom_lazim")
        self.assertEqual(first.snapshot()["counters"]["charge.enakhra_camulet"], 3)

        # A charge counter spans all origins, including when external travel puts
        # the player back at an available casting waypoint.
        for _ in range(3):
            checkpoint = first.snapshot()
            checkpoint["location_id"] = "location.al_kharid.bank_entrance"
            first = RouteState(self.tables, self.profile["policies"], checkpoint)
            first = self.transition(first, "travel.enakhra.camulet.al_kharid")
        self.assertEqual(first.snapshot()["counters"].get("charge.enakhra_camulet", 0), 0)
        checkpoint = first.snapshot()
        checkpoint["location_id"] = "location.al_kharid.bank_entrance"
        empty = RouteState(self.tables, self.profile["policies"], checkpoint)
        with self.assertRaises(DataError):
            self.transition(empty, "travel.enakhra.camulet.al_kharid")

        funded = first.snapshot()
        funded["inventory"]["item.coins"] = 1000100
        upgraded = RouteState(self.tables, self.profile["policies"], funded)
        upgraded = self.act(upgraded, "upgrade_camulet")
        self.assertEqual(upgraded.snapshot()["inventory"]["item.coins"], 100)
        self.assertTrue(upgraded.snapshot()["flags"]["unlock.enakhra_camulet_unlimited"])
        with self.assertRaises(DataError):
            self.transition(upgraded, QUEST + "upgrade_camulet")
        checkpoint = upgraded.snapshot()
        checkpoint["location_id"] = "location.al_kharid.bank_entrance"
        from_bank = RouteState(self.tables, self.profile["policies"], checkpoint)
        from_bank = self.transition(from_bank, "travel.enakhra.camulet_unlimited.al_kharid")
        self.assertEqual(from_bank.snapshot()["location_id"], "location.enakhra.bottom_lazim")
        self.assertEqual(from_bank.snapshot()["counters"].get("charge.enakhra_camulet", 0), 0)

    def test_skill_gate_rejects_untrained_start(self):
        state = self.seed()
        snapshot = state.snapshot()
        snapshot["xp_tenths"]["skill.crafting"] = 0
        state = RouteState(self.tables, self.profile["policies"], snapshot)
        with self.assertRaises(DataError):
            self.transition(state, QUEST + "start")


if __name__ == "__main__":
    unittest.main()
