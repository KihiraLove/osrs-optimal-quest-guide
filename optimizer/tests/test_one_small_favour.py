"""Full forward/backward route replay for the One Small Favour data slice."""

from collections import deque
from pathlib import Path
import unittest

from quest_optimizer.data import Contracts, DataError, load_catalog, read_json
from quest_optimizer.semantics import CatalogValidator
from quest_optimizer.transitions import RouteState


ROOT = Path(__file__).resolve().parents[2]
QUEST = "quest.one_small_favour."


class OneSmallFavourTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.contracts = Contracts(ROOT / "schemas")
        cls.catalog = load_catalog(ROOT / "data/manifest.json", cls.contracts)
        cls.validator = CatalogValidator(cls.catalog, cls.contracts)
        cls.profile = read_json(ROOT / "data/profiles/main-baseline.json")
        cls.legs = {}
        for edge_id, edge in cls.validator.tables["travel_edges"].items():
            cls.legs.setdefault(edge["from_location_id"], []).append((edge_id, edge["to_location_id"]))

    def seed(self):
        seed = {**self.profile["initial_state"]}
        seed["location_id"] = "location.osf.yanni"
        seed["completed_action_ids"] = [
            "quest.rune_mysteries.complete", "quest.druidic_ritual.complete",
            "quest.shilo_village.complete",
        ]
        seed["flags"] = {**seed["flags"], "unlock.shilo_village": True}
        seed["xp_tenths"] = {key: 5000000 for key in seed["xp_tenths"]}
        seed["inventory"] = {**seed["inventory"], **{
            "item.coins": 3000, "item.steel_bar": 4, "item.bronze_bar": 1,
            "item.iron_bar": 1, "item.osf_guam_leaf": 2,
            "item.osf_marrentill": 1, "item.osf_harralander": 1,
            "item.osf_empty_cup": 1, "item.bowl_of_water": 1,
            "item.logs": 1, "item.tinderbox": 1,
            "item.opal": 2, "item.sapphire": 2, "item.osf_jade": 2,
            "item.osf_red_topaz": 2, "item.chisel": 1,
            "item.hammer": 1, "item.pot": 1,
        }}
        return RouteState(self.validator.tables, self.profile["policies"], seed)

    def transition(self, state, key):
        is_edge = key.startswith("travel.")
        rec = self.validator.tables["travel_edges" if is_edge else "actions"][key]
        step = {"kind": "travel" if is_edge else "action",
                "edge_id" if is_edge else "action_id": key,
                "modeled_seconds": rec["duration"]["expected_seconds"]}
        if rec.get("planned_outcome"):
            step["planned_outcome"] = rec["planned_outcome"]
        return state.apply(step, key)

    def move(self, state, target):
        current = state.snapshot()["location_id"]
        if current == target:
            return state
        queue = deque([(current, ())])
        seen = {current}
        while queue:
            loc, path = queue.popleft()
            for edge, dest in sorted(self.legs.get(loc, ())):
                if dest in seen:
                    continue
                candidate = RouteState(self.validator.tables, self.profile["policies"], state.snapshot())
                try:
                    for part in (*path, edge):
                        candidate = self.transition(candidate, part)
                except DataError:
                    continue
                steps = (*path, edge)
                if dest == target:
                    for part in steps:
                        state = self.transition(state, part)
                    return state
                seen.add(dest)
                queue.append((dest, steps))
        self.fail(f"No legal public travel path from {current} to {target}")

    def act(self, state, key):
        aid = (QUEST + key) if not key.startswith("supply.") else key
        record = self.validator.tables["actions"][aid]
        state = self.move(state, record["start_location_id"])
        return self.transition(state, aid)

    def test_full_favour_chain_travel_rewards_and_repeated_use(self):
        state = self.seed()
        sequence = (
            "start", "forester_request", "brian_request", "aggie_request",
            "johanhus_request", "fred_request", "seth_request", "horvik_request",
            "apothecary_request", "tassie_request", "hammerspike_request",
            "sanfew_request", "supply.one_small_favour.heat_water",
            "brew_guthix_rest", "bleemadge_request", "arhein_request",
            "phantuwti_request", "investigate_petra", "cromperty_request",
            "tindel_request", "rantz_request", "gnormadium_request",
            "repair_glider_lights", "rantz_mattress", "tindel_oxide",
            "cromperty_scroll", "supply.one_small_favour.collect_pigeon_cages",
            "defeat_slagilith", "free_petra", "phantuwti_vane",
            "dismantle_vane", "smith_vane", "repair_vane",
            "collect_weather_report", "arhein_rope", "bleemadge_agreement",
            "sanfew_consent", "hammerspike_gang", "hammerspike_approval",
            "tassie_teaches", "make_pot_lid", "seal_pot",
            "apothecary_tincture", "horvik_cages", "seth_chickens",
            "johanhus_releases", "aggie_testimony", "brian_sharpened",
            "forester_logs", "complete",
        )
        for key in sequence:
            state = self.act(state, key)

        snap = state.snapshot()
        self.assertEqual(snap["counters"]["token.quest_points"], 3)
        self.assertEqual(snap["inventory"].get("item.osf_key_ring"), 1)
        self.assertEqual(snap["inventory"].get("item.steel_bar", 0), 0)
        self.assertEqual(snap["inventory"].get("item.osf_pigeon_cage", 0), 0)
        self.assertTrue(snap["flags"]["unlock.osf_guthix_rest"])
        self.assertTrue(snap["flags"]["unlock.osf_pot_lids"])
        self.assertTrue(snap["flags"]["unlock.osf_feldip_glider"])
        self.assertEqual(len(snap["held_rewards"]), 2)
        self.assertEqual(snap["xp_tenths"]["skill.herblore"], 5000000)
        with self.assertRaises(DataError):
            self.transition(state, QUEST + "complete")

        for number in (1, 2):
            state = state.apply({
                "kind": "reward_use", "reward_id": "reward.one_small_favour.lamp",
                "instance_id": f"reward.one_small_favour.lamp.instance.{number}",
                "skill_id": "skill.herblore", "gain_xp_tenths": 100000,
                "overrides_observed_skill_restriction": False,
            })
        self.assertEqual(state.snapshot()["held_rewards"], [])
        self.assertEqual(state.snapshot()["xp_tenths"]["skill.herblore"], 5200000)
        with self.assertRaises(DataError):
            state.apply({"kind": "reward_use", "reward_id": "reward.one_small_favour.lamp",
                         "instance_id": "reward.one_small_favour.lamp.instance.1",
                         "skill_id": "skill.herblore", "gain_xp_tenths": 100000,
                         "overrides_observed_skill_restriction": False})


if __name__ == "__main__":
    unittest.main()
