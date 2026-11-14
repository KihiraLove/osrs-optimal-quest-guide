"""Connected build-242 route replay for Land of the Goblins and Hopespear's Will."""

from collections import defaultdict, deque
from pathlib import Path
import unittest

from quest_optimizer.data import Contracts, DataError, load_catalog, read_json
from quest_optimizer.semantics import CatalogValidator
from quest_optimizer.transitions import RouteState


ROOT = Path(__file__).resolve().parents[2]
LAND = "quest.land_of_the_goblins"
HOPE = "miniquest.hopespears_will"
PRIESTS = ("snothead", "snailfeet", "mosschin", "redeyes", "strongbones")


class GoblinChainTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        contracts = Contracts(ROOT / "schemas")
        cls.tables = CatalogValidator(load_catalog(ROOT / "data/manifest.json", contracts), contracts).tables
        cls.profile = read_json(ROOT / "data/profiles/main-baseline.json")
        cls.actions = read_json(ROOT / "data/catalog/goblin-chain/actions.json")
        cls.edges = read_json(ROOT / "data/catalog/goblin-chain/travel_edges.json")
        cls.travel = defaultdict(list)
        for edge in cls.tables["travel_edges"].values():
            if edge["mode"] in ("walk", "ship", "other", "lever", "fairy_ring", "teleport"):
                cls.travel[edge["from_location_id"]].append(edge)

    def seed(self, *, level_ok=True, have_bait=True):
        initial = self.profile["initial_state"].copy()
        initial["location_id"] = "location.goblin.grubfoot"
        initial["inventory"] = {"item.lit_candle": 1, "item.toadflax_potion_unf": 1,
                                "item.pestle_and_mortar": 1, "item.empty_vial": 1,
                                "item.fishing_rod": 1, "item.raw_slimy_eel": 1,
                                "item.yellow_dye": 1, "item.purple_dye": 1,
                                "item.orange_dye": 1, "item.blue_dye": 1,
                                "item.coins": 100, "item.dramen_staff": 1,
                                "item.ghostspeak_amulet": 1, "item.ring_of_visibility": 1}
        if not have_bait:
            initial["inventory"].pop("item.raw_slimy_eel")
        initial["completed_action_ids"] = [
            "quest.another_slice_of_ham.complete", "quest.fishing_contest.complete",
            "quest.desert_treasure_i.complete", "quest.fairytale_ii_cure_a_queen.complete",
            "quest.the_restless_ghost.complete"
        ]
        initial["flags"] = {"unlock.fairy_rings": True, "unlock.dorgeshuun.guided_tunnels": True}
        for skill, minimum in (("agility", 38), ("fishing", 40), ("thieving", 45),
                               ("herblore", 48), ("prayer", 50)):
            lvl = minimum - (1 if not level_ok and skill == "herblore" else 0)
            initial["xp_tenths"]["skill." + skill] = self.tables["skills"]["skill." + skill]["xp_thresholds_tenths"][lvl - 1]
        return RouteState(self.tables, self.profile["policies"], initial)

    def apply(self, state, record, *, travel=False):
        event = {"kind": "travel" if travel else "action",
                 "edge_id" if travel else "action_id": record["id"],
                 "modeled_seconds": record["duration"]["expected_seconds"]}
        if "planned_outcome" in record:
            event["planned_outcome"] = record["planned_outcome"]
        return state.apply(event)

    def walk_to(self, state, location):
        if state.location == location:
            return state
        todo = deque([state])
        visited = {state.location}
        while todo:
            current = todo.popleft()
            for edge in self.travel[current.location]:
                dest = edge["to_location_id"]
                if dest in visited:
                    continue
                try:
                    changed = self.apply(current, edge, travel=True)
                except DataError:
                    continue
                if dest == location:
                    return changed
                visited.add(dest)
                todo.append(changed)
        self.fail(f"Unreachable from {state.location} to {location}; {len(visited)} nodes")

    def do(self, state, ident):
        action = self.tables["actions"][ident]
        return self.apply(self.walk_to(state, action["start_location_id"]), action)

    def land(self, state):
        for action in self.actions:
            if action["activity_id"] == LAND:
                state = self.do(state, action["id"])
        return state

    def hopespear(self, state):
        for action in self.actions:
            if action["activity_id"] == HOPE:
                state = self.do(state, action["id"])
        return state

    def test_complete_both_quests_and_rewards(self):
        seed = self.seed()
        land = self.land(seed)
        land_snap = land.snapshot()
        self.assertIn(LAND + ".complete", land_snap["completed_action_ids"])
        self.assertEqual(land_snap["counters"]["token.quest_points"] - seed.counters["token.quest_points"], 2)
        self.assertEqual(land_snap["xp_tenths"]["skill.herblore"] - seed.xp["skill.herblore"], 80550)
        for skill in ("agility", "fishing", "thieving"):
            self.assertEqual(land_snap["xp_tenths"]["skill." + skill] - seed.xp["skill." + skill], 80000)
        self.assertTrue(land_snap["flags"]["unlock.yubiusk_blq"])
        self.assertTrue(land_snap["flags"]["unlock.goblin_potion_recipe"])
        self.assertTrue(land_snap["flags"]["unlock.plain_of_mud_sphere_shop"])
        for colour in ("black", "white", "yellow", "purple", "orange", "blue"):
            self.assertNotIn("item.goblin_key_" + colour, land_snap["inventory"])

        done = self.hopespear(land)
        outcome = done.snapshot()
        self.assertIn(HOPE + ".complete", outcome["completed_action_ids"])
        self.assertEqual(outcome["xp_tenths"]["skill.prayer"] - land.xp["skill.prayer"], 387500)
        self.assertEqual(outcome["counters"]["token.quest_points"], land_snap["counters"]["token.quest_points"])
        for name in PRIESTS:
            self.assertNotIn("item.hopespear_bone_" + name, outcome["inventory"])
        with self.assertRaises(DataError):
            self.do(done, HOPE + ".complete")

    def test_skill_gate_and_missing_quest_bait(self):
        start = self.tables["actions"][LAND + ".start"]
        with self.assertRaises(DataError):
            self.apply(self.seed(level_ok=False), start)
        missing_bait = self.seed(have_bait=False)
        fish = self.tables["actions"][LAND + ".fish_whitefish"]
        state = missing_bait.snapshot()
        state["location_id"] = fish["start_location_id"]
        state["completed_action_ids"].append(LAND + ".ask_aggie")
        with self.assertRaises(DataError):
            self.apply(RouteState(self.tables, self.profile["policies"], state), fish)

    def test_hopespear_prayer_and_potion_requirements(self):
        entry = self.tables["actions"][HOPE + ".enter_temple"]
        state = self.seed().snapshot()
        state["location_id"] = entry["start_location_id"]
        state["completed_action_ids"].append(LAND + ".complete")
        state["inventory"]["item.goblin_potion_1"] = 1
        state["xp_tenths"]["skill.prayer"] = self.tables["skills"]["skill.prayer"]["xp_thresholds_tenths"][48]
        with self.assertRaises(DataError):
            self.apply(RouteState(self.tables, self.profile["policies"], state), entry)
        state["xp_tenths"]["skill.prayer"] = self.tables["skills"]["skill.prayer"]["xp_thresholds_tenths"][49]
        state["inventory"].pop("item.goblin_potion_1")
        with self.assertRaises(DataError):
            self.apply(RouteState(self.tables, self.profile["policies"], state), entry)

    def test_no_fairy_ring_blq_before_quest(self):
        ring = next(e for e in self.edges if e["mode"] == "fairy_ring" and
                    e["from_location_id"] == "location.zanaris.fairy_ring")
        state = self.seed().snapshot()
        state["location_id"] = "location.zanaris.fairy_ring"
        with self.assertRaises(DataError):
            self.apply(RouteState(self.tables, self.profile["policies"], state), ring, travel=True)
        state["flags"]["unlock.yubiusk_blq"] = True
        moved = self.apply(RouteState(self.tables, self.profile["policies"], state), ring, travel=True)
        self.assertEqual(moved.location, "location.goblin.fairy_ring_blq")

    def test_local_walk_edges_have_return_paths(self):
        pairs = {(e["from_location_id"], e["to_location_id"])
                 for e in self.edges if e["mode"] == "walk"}
        for a, b in pairs:
            self.assertIn((b, a), pairs)
        # Temple re-entry and the Yu'biusk machine are one-way gateways.
        self.assertFalse(any(e["from_location_id"] == "location.goblin.cave_guards" and
                             e["to_location_id"] == "location.goblin.temple" for e in self.edges))
        self.assertFalse(any(e["from_location_id"] == "location.goblin.yubiusk" and
                             e["to_location_id"] == "location.goblin.oldak_machine" for e in self.edges))


if __name__ == "__main__":
    unittest.main()
