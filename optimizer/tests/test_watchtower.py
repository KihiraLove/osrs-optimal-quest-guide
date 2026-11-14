"""End-to-end Watchtower quest, Ogre access and post-quest teleport tests."""

from collections import deque
from pathlib import Path
import unittest

from quest_optimizer.data import Contracts, DataError, load_catalog, read_json
from quest_optimizer.semantics import CatalogValidator
from quest_optimizer.transitions import RouteState


ROOT = Path(__file__).resolve().parents[2]
QUEST = "quest.watchtower."


class WatchtowerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        contracts = Contracts(ROOT / "schemas")
        cls.catalog = load_catalog(ROOT / "data/manifest.json", contracts)
        cls.tables = CatalogValidator(cls.catalog, contracts).tables
        cls.profile = read_json(ROOT / "data/profiles/main-baseline.json")
        cls.connections = {}
        for edge_id, edge in cls.tables["travel_edges"].items():
            cls.connections.setdefault(edge["from_location_id"], []).append((edge_id, edge["to_location_id"]))

    def seed(self, location="location.watchtower.trellis"):
        base = {**self.profile["initial_state"]}
        base["location_id"] = location
        base["xp_tenths"] = {key: 5000000 for key in base["xp_tenths"]}
        base["inventory"] = {**base["inventory"], **{
            "item.coins": 3000, "item.rope": 2, "item.watchtower_dragon_bones": 1,
            "item.gold_bar": 1, "item.death_rune": 1,
            "item.watchtower_guam_potion_unf": 1, "item.bat_bones": 1,
            "item.pestle_and_mortar": 1, "item.bronze_pickaxe": 1,
            "item.watchtower_light_source": 1,
            "item.earth_rune": 2, "item.law_rune": 2
        }}
        return RouteState(self.tables, self.profile["policies"], base)

    def transition(self, state, record_id):
        is_travel = record_id.startswith("travel.")
        record = self.tables["travel_edges" if is_travel else "actions"][record_id]
        step = {"kind": "travel" if is_travel else "action",
                "edge_id" if is_travel else "action_id": record_id,
                "modeled_seconds": record["duration"]["expected_seconds"]}
        if record.get("planned_outcome"):
            step["planned_outcome"] = record["planned_outcome"]
        return state.apply(step, record_id)

    def move(self, state, destination):
        start = state.snapshot()["location_id"]
        if start == destination:
            return state
        queue = deque([(start, ())])
        visited = {start}
        while queue:
            source, prefix = queue.popleft()
            for edge_id, target in sorted(self.connections.get(source, ())):
                if target in visited:
                    continue
                probe = RouteState(self.tables, self.profile["policies"], state.snapshot())
                try:
                    for edge in (*prefix, edge_id):
                        probe = self.transition(probe, edge)
                except DataError:
                    continue
                path = (*prefix, edge_id)
                if target == destination:
                    for edge in path:
                        state = self.transition(state, edge)
                    return state
                visited.add(target)
                queue.append((target, path))
        self.fail(f"Unreachable Watchtower route from {start} to {destination}")

    def act(self, state, short_name):
        aid = short_name if short_name.startswith("supply.") else QUEST + short_name
        state = self.move(state, self.tables["actions"][aid]["start_location_id"])
        return self.transition(state, aid)

    def test_entire_quest_route_relics_crystals_scroll_and_spell(self):
        state = self.seed()
        path = (
            "start", "search_bush", "wizard_relic_request", "og_request",
            "grew_request", "supply.watchtower.pick_jangerberries",
            "toban_bones", "gorad_fight", "toban_chest", "grew_relic",
            "og_relic", "wizard_relic", "open_city_gate",
            "steal_rock_cake", "rock_cake", "cross_bridge",
            "get_skavid_map", "learn_from_scared_skavid",
            "skavid_language_1", "skavid_language_2",
            "skavid_language_3", "skavid_language_4",
            "pay_eastern_gate", "mad_skavid", "collect_nightshade",
            "distract_guard_first", "enclave_scout", "brew_potion",
            "enchant_potion", "distract_guard_second",
            *(f"shaman_{n}" for n in range(1, 7)),
            "mine_dalgroth", "wizard_crystals",
            *(f"place_crystal_{n}" for n in range(1, 5)),
            "complete"
        )
        for short_name in path:
            state = self.act(state, short_name)

        snap = state.snapshot()
        self.assertEqual(snap["counters"]["token.quest_points"], 5)
        self.assertEqual(snap["inventory"]["item.coins"], 7980)
        self.assertEqual(snap["inventory"].get("item.rope", 0), 0)
        self.assertEqual(snap["inventory"].get("item.watchtower_cave_nightshade", 0), 0)
        self.assertEqual(snap["inventory"].get("item.watchtower_yellow_crystal", 0), 0)
        self.assertEqual(snap["inventory"].get("item.watchtower_fourth_crystal", 0), 0)
        self.assertEqual(snap["xp_tenths"]["skill.magic"], 5152500)
        self.assertTrue(snap["flags"]["unlock.watchtower_city"])
        self.assertTrue(snap["flags"]["unlock.watchtower_enclave"])
        self.assertFalse(snap["flags"].get("unlock.watchtower_teleport", False))
        with self.assertRaises(DataError):
            self.transition(state, "travel.watchtower.teleport.yanille")
        with self.assertRaises(DataError):
            self.transition(state, QUEST + "complete")

        state = self.act(state, "read_scroll")
        self.assertTrue(state.snapshot()["flags"]["unlock.watchtower_teleport"])
        self.assertEqual(state.snapshot()["inventory"].get("item.watchtower_teleport_scroll", 0), 0)
        with self.assertRaises(DataError):
            self.transition(state, QUEST + "read_scroll")

        state = self.move(state, "location.yanille.dragon_inn")
        state = self.transition(state, "travel.watchtower.teleport.yanille")
        self.assertEqual(state.snapshot()["location_id"], "location.watchtower.trellis")
        self.assertEqual(state.snapshot()["inventory"].get("item.earth_rune", 0), 0)
        self.assertEqual(state.snapshot()["inventory"].get("item.law_rune", 0), 0)
        self.assertEqual(state.snapshot()["xp_tenths"]["skill.magic"], 5153180)

    def test_required_magic_gate_precedes_quest_start(self):
        state = self.seed(location="location.watchtower.wizard")
        snapshot = state.snapshot()
        snapshot["xp_tenths"]["skill.magic"] = 0
        state = RouteState(self.tables, self.profile["policies"], snapshot)
        with self.assertRaises(DataError):
            self.transition(state, QUEST + "start")


if __name__ == "__main__":
    unittest.main()
