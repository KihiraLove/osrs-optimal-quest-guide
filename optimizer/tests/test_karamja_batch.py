"""Seeded full-route progression checks for the Karamja quest batch."""

from collections import deque
from pathlib import Path
import unittest

from quest_optimizer.data import Contracts, DataError, load_catalog, read_json
from quest_optimizer.semantics import CatalogValidator
from quest_optimizer.transitions import RouteState


ROOT = Path(__file__).resolve().parents[2]


class KaramjaBatchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = load_catalog(ROOT / "data/manifest.json", Contracts(ROOT / "schemas"))
        cls.validator = CatalogValidator(cls.catalog, Contracts(ROOT / "schemas"))
        cls.baseline = read_json(ROOT / "data/profiles/main-baseline.json")

    def initial(self, inventory):
        state = {**self.baseline["initial_state"]}
        state["location_id"] = "location.tai_bwo_wannai.trufitus"
        state["completed_action_ids"] = ["quest.jungle_potion.complete"]
        state["inventory"] = {**state["inventory"], **inventory}
        state["xp_tenths"] = {skill: 5000000 for skill in state["xp_tenths"]}
        state["flags"] = {**state["flags"], "unlock.tai_bwo_wannai_cleanup": True}
        return RouteState(self.validator.tables, self.baseline["policies"], state)

    def step(self, state, record_id):
        kind = "travel" if record_id.startswith("travel.") else "action"
        record = self.validator.tables["travel_edges" if kind == "travel" else "actions"][record_id]
        data = {"kind": kind, "edge_id" if kind == "travel" else "action_id": record_id,
                "modeled_seconds": record["duration"]["expected_seconds"]}
        if "planned_outcome" in record:
            data["planned_outcome"] = record["planned_outcome"]
        return state.apply(data, record_id)

    def move_to(self, state, target):
        """Navigate actual catalog travel edges, never teleport the test state."""
        current = state.snapshot()["location_id"]
        if current == target:
            return state
        by_start = {}
        for key, edge in self.validator.tables["travel_edges"].items():
            by_start.setdefault(edge["from_location_id"], []).append((key, edge["to_location_id"]))
        todo = deque([(current, ())])
        visited = {current}
        while todo:
            where, steps = todo.popleft()
            for edge_id, destination in sorted(by_start.get(where, [])):
                if destination in visited:
                    continue
                # The prefix has already been tested; make a fresh state from the
                # real checkpoint and traverse it before allowing more edges.
                candidate = RouteState(self.validator.tables, self.baseline["policies"], state.snapshot())
                try:
                    for prefix in steps:
                        candidate = self.step(candidate, prefix)
                    candidate = self.step(candidate, edge_id)
                except DataError:
                    continue
                seq = (*steps, edge_id)
                if destination == target:
                    for edge in seq:
                        state = self.step(state, edge)
                    return state
                visited.add(destination)
                todo.append((destination, seq))
        self.fail(f"No legal travel path from {current} to {target}")

    def act(self, state, short_id, quest):
        key = f"quest.{quest}.{short_id}"
        record = self.validator.tables["actions"][key]
        state = self.move_to(state, record["start_location_id"])
        return self.step(state, key)

    def test_shilo_village_full_route_and_cart_gate(self):
        state = self.initial({
            "item.spade": 1, "item.lit_candle": 1, "item.rope": 1,
            "item.chisel": 1, "item.bronze_wire": 1, "item.bones": 3,
            "item.coins": 300,
        })
        # Cart must stay gated even if the player reaches the Brimhaven NPC.
        cart = {**state.snapshot(), "location_id": "location.shilo.hajedy_cart"}
        with self.assertRaises(DataError):
            self.step(RouteState(self.validator.tables, self.baseline["policies"], cart), "travel.cart.karamja.to_shilo")

        steps = (
            "meet_mosol", "start", "expose_fissure", "descend_fissure",
            "take_plaque", "read_tattered_scroll", "read_crumpled_scroll",
            "take_zadimus", "report_discovery", "bury_zadimus", "report_shard",
            "open_cairn", "search_bervirius", "craft_beads", "craft_key",
            "reveal_tomb", "open_tomb", "offer_bones", "defeat_nazastarool",
            "complete",
        )
        for step_id in steps:
            state = self.act(state, step_id, "shilo_village")
        snapshot = state.snapshot()
        self.assertTrue(snapshot["flags"]["unlock.shilo_village"])
        self.assertEqual(snapshot["counters"]["token.quest_points"], 3)
        self.assertEqual(snapshot["inventory"].get("item.bones", 0), 0)
        self.assertEqual(snapshot["inventory"].get("item.shilo_rashiliyia_corpse", 0), 0)
        self.assertEqual(snapshot["xp_tenths"]["skill.crafting"], 5038750)
        state = self.move_to(state, "location.shilo.hajedy_cart")
        state = self.step(state, "travel.cart.karamja.to_shilo")
        self.assertEqual(state.snapshot()["location_id"], "location.shilo.vigroy_cart")
        self.assertEqual(state.snapshot()["inventory"]["item.coins"], 100)
        with self.assertRaises(DataError):
            self.step(state, "quest.shilo_village.complete")

    def test_trio_claims_are_independent_one_time_dialogues(self):
        state = self.initial({
            "item.coins": 200, "item.small_fishing_net": 1,
            "item.pestle_and_mortar": 1, "item.iron_spear": 1,
            "item.agility_potion_4": 1, "item.tinderbox": 1,
            "item.logs": 2, "item.knife": 1,
        })
        for part in (
            "start", "catch_karambwanji", "learn_vessels", "replace_vessel",
            "bait_vessel", "help_tiadeche", "cook_poison_karambwan", "poison_spear",
            "arm_tamayu", "tamayu_hunt", "get_monkey", "skin_monkey",
            "collect_seaweed", "collect_banana", "buy_rum", "make_banana_rum",
            "kill_jogre", "burn_jogre_bones", "pasty_bones", "marinate_bones",
            "make_sandwich", "feed_tinsay", "get_manual", "teach_tiadeche",
        ):
            state = self.act(state, part, "tai_bwo_wannai_trio")
        # Completing the brothers' tasks does not yet award their post-quest XP.
        pre = state.snapshot()
        state = self.act(state, "complete", "tai_bwo_wannai_trio")
        mid = state.snapshot()
        for skill in ("skill.fishing", "skill.cooking", "skill.attack", "skill.strength"):
            self.assertEqual(mid["xp_tenths"][skill], pre["xp_tenths"][skill])
        self.assertEqual(mid["counters"]["token.quest_points"], 3)
        self.assertEqual(mid["inventory"]["item.coins"], 2170)
        for part in ("claim_combat", "claim_fishing", "claim_cooking"):
            state = self.act(state, part, "tai_bwo_wannai_trio")
        post = state.snapshot()
        self.assertEqual(post["xp_tenths"]["skill.attack"] - pre["xp_tenths"]["skill.attack"], 25000)
        self.assertEqual(post["xp_tenths"]["skill.strength"] - pre["xp_tenths"]["skill.strength"], 25000)
        self.assertEqual(post["xp_tenths"]["skill.cooking"] - pre["xp_tenths"]["skill.cooking"], 50000)
        self.assertEqual(post["xp_tenths"]["skill.fishing"] - pre["xp_tenths"]["skill.fishing"], 50000)
        self.assertTrue(post["flags"]["unlock.karambwan_fishing"])
        self.assertTrue(post["flags"]["unlock.karambwan_cooking"])
        self.assertEqual(post["inventory"].get("item.raw_karambwanji", 0), 0)
        with self.assertRaises(DataError):
            self.step(state, "quest.tai_bwo_wannai_trio.claim_cooking")


if __name__ == "__main__":
    unittest.main()
