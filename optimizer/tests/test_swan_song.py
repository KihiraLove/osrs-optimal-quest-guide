"""Full Swan Song route, prerequisites and Piscatoris boat unlock."""

from collections import deque
from pathlib import Path
import unittest

from quest_optimizer.data import Contracts, DataError, load_catalog, read_json
from quest_optimizer.semantics import CatalogValidator
from quest_optimizer.transitions import RouteState


ROOT = Path(__file__).resolve().parents[2]
QUEST = "quest.swan_song."


class SwanSongTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        contracts = Contracts(ROOT / "schemas")
        cls.catalog = load_catalog(ROOT / "data/manifest.json", contracts)
        cls.tables = CatalogValidator(cls.catalog, contracts).tables
        cls.profile = read_json(ROOT / "data/profiles/main-baseline.json")
        cls.connections = {}
        for edge_id, edge in cls.tables["travel_edges"].items():
            cls.connections.setdefault(edge["from_location_id"], []).append(
                (edge_id, edge["to_location_id"]))

    def seed(self, location="location.swan_song.herman_outside"):
        data = {**self.profile["initial_state"]}
        data["location_id"] = location
        data["xp_tenths"] = {key: 6000000 for key in data["xp_tenths"]}
        data["completed_action_ids"] = [
            "quest.one_small_favour.complete", "quest.garden_of_tranquillity.complete"]
        data["counters"] = {**data["counters"], "token.quest_points": 100}
        data["inventory"] = {**data["inventory"], **{
            "item.coins": 600,
            "item.swan_mist_rune": 10, "item.swan_lava_rune": 10,
            "item.swan_blood_rune": 5, "item.bones": 7,
            "item.pot": 1, "item.swan_pot_lid": 1,
            "item.iron_bar": 5, "item.logs": 1, "item.tinderbox": 1,
        }}
        return RouteState(self.tables, self.profile["policies"], data)

    def transition(self, state, record_id):
        travel = record_id.startswith("travel.")
        record = self.tables["travel_edges" if travel else "actions"][record_id]
        step = {"kind": "travel" if travel else "action",
                "edge_id" if travel else "action_id": record_id,
                "modeled_seconds": record["duration"]["expected_seconds"]}
        if record.get("planned_outcome"):
            step["planned_outcome"] = record["planned_outcome"]
        return state.apply(step, record_id)

    def move(self, state, target):
        source = state.snapshot()["location_id"]
        if source == target:
            return state
        queue = deque([(source, ())])
        seen = {source}
        while queue:
            position, prefix = queue.popleft()
            for edge, destination in sorted(self.connections.get(position, ())):
                if destination in seen:
                    continue
                probe = RouteState(self.tables, self.profile["policies"], state.snapshot())
                try:
                    for step in (*prefix, edge):
                        probe = self.transition(probe, step)
                except DataError:
                    continue
                path = (*prefix, edge)
                if destination == target:
                    for step in path:
                        state = self.transition(state, step)
                    return state
                seen.add(destination)
                queue.append((destination, path))
        self.fail(f"Swan Song stage unreachable: {source} -> {target}")

    def act(self, state, name):
        identifier = QUEST + name
        state = self.move(state, self.tables["actions"][identifier]["start_location_id"])
        return self.transition(state, identifier)

    def test_full_quest_route_colony_chores_bones_and_queen(self):
        state = self.seed()
        steps = (
            "start", "recruit_wise_old_man", "give_wise_old_man_runes",
            "meet_wise_old_man_at_colony", "repel_troll_wave", "open_colony_gate",
            "meet_herman_inside", "ask_franklin", "light_press", "press_iron_sheets",
            "repair_west_wall", "report_to_franklin", "ask_arnold",
            "fish_fresh_monkfish", "cook_fresh_monkfish", "feed_colony",
            "report_colony_tasks", "raise_an_army", "meet_frumscone",
            "ask_malignius", "ask_almost_master_crafter", "make_airtight_pot",
            "get_bone_seeds", "plant_bone_seeds", "defeat_queen", "complete"
        )
        for step in steps:
            state = self.act(state, step)
        result = state.snapshot()
        self.assertEqual(result["counters"]["token.quest_points"], 102)
        self.assertEqual(result["xp_tenths"]["skill.magic"], 6150000)
        self.assertEqual(result["xp_tenths"]["skill.prayer"], 6100000)
        self.assertEqual(result["xp_tenths"]["skill.fishing"], 6500000)
        for name in ("swan_mist_rune", "swan_lava_rune", "swan_blood_rune",
                     "swan_iron_sheet", "swan_raw_fresh_monkfish", "swan_cooked_fresh_monkfish",
                     "swan_airtight_pot", "swan_bone_seeds", "bones"):
            self.assertEqual(result["inventory"].get("item." + name, 0), 0, name)
        self.assertTrue(result["flags"]["unlock.piscatoris_colony"])
        self.assertTrue(result["flags"]["unlock.piscatoris_monkfish"])
        self.assertEqual(result["inventory"]["item.hammer"], 1)
        with self.assertRaises(DataError):
            self.transition(state, QUEST + "complete")

        # Free ferry travel is a distinct postquest option and costs no coin.
        checkpoint = result.copy()
        checkpoint["location_id"] = "location.swan_song.kathy_boat"
        postquest = RouteState(self.tables, self.profile["policies"], checkpoint)
        old_coins = postquest.snapshot()["inventory"]["item.coins"]
        postquest = self.transition(postquest, "travel.swan_song.kathy_ride_free.out")
        self.assertEqual(postquest.snapshot()["inventory"]["item.coins"], old_coins)
        self.assertEqual(postquest.snapshot()["location_id"], "location.swan_song.herman_outside")

    def test_start_quest_point_and_dependency_gates(self):
        state = self.seed()
        initial = state.snapshot()
        initial["counters"]["token.quest_points"] = 99
        with self.assertRaises(DataError):
            self.transition(RouteState(self.tables, self.profile["policies"], initial), QUEST + "start")
        initial = self.seed().snapshot()
        initial["completed_action_ids"] = ["quest.one_small_favour.complete"]
        with self.assertRaises(DataError):
            self.transition(RouteState(self.tables, self.profile["policies"], initial), QUEST + "start")

    def test_skill_and_boat_gate(self):
        state = self.seed("location.swan_song.kathy_boat")
        with self.assertRaises(DataError):
            self.transition(state, "travel.swan_song.kathy_ride_free.out")
        charged = self.transition(state, "travel.swan_song.kathy_ride_paid.out")
        self.assertEqual(charged.snapshot()["inventory"]["item.coins"], 550)
        state = self.seed("location.swan_song.wizards_basement")
        untrained = state.snapshot()
        untrained["xp_tenths"]["skill.magic"] = 0
        untrained["completed_action_ids"].append(QUEST + "raise_an_army")
        with self.assertRaises(DataError):
            self.transition(RouteState(self.tables, self.profile["policies"], untrained), QUEST + "meet_frumscone")


if __name__ == "__main__":
    unittest.main()
