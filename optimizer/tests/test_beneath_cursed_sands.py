"""Build-242 connected replay for Beneath Cursed Sands and its AKP unlock."""

from collections import defaultdict, deque
from pathlib import Path
import unittest

from quest_optimizer.data import Contracts, DataError, load_catalog, read_json
from quest_optimizer.semantics import CatalogValidator
from quest_optimizer.transitions import RouteState


ROOT = Path(__file__).resolve().parents[2]
BATCH = ROOT / "data/catalog/beneath-cursed-sands"
QUEST = "quest.beneath_cursed_sands"


class BeneathCursedSandsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        contracts = Contracts(ROOT / "schemas")
        cls.validator = CatalogValidator(load_catalog(ROOT / "data/manifest.json", contracts), contracts)
        cls.profile = read_json(ROOT / "data/profiles/main-baseline.json")
        cls.batch = read_json(BATCH / "actions.json")
        cls.new_edges = read_json(BATCH / "travel_edges.json")
        cls.walks = defaultdict(list)
        for edge in cls.validator.tables["travel_edges"].values():
            if edge["mode"] == "walk":
                cls.walks[edge["from_location_id"]].append(edge)

    def seeded(self, *, contact=True, level_ok=True, carry_tools=False):
        initial = read_json(ROOT / "data/profiles/main-baseline.json")["initial_state"]
        initial["location_id"] = "location.bcs.jamila"
        if contact:
            initial["completed_action_ids"] = ["quest.contact.complete", "quest.icthlarins_little_helper.complete"]
            initial["flags"]["flag.quest.contact.complete"] = True
            initial["flags"]["unlock.sophanem_access"] = True
        for skill, level in (("agility", 62), ("crafting", 55), ("firemaking", 55)):
            threshold = self.validator.tables["skills"]["skill." + skill]["xp_thresholds_tenths"][level - 1]
            initial["xp_tenths"]["skill." + skill] = threshold - (10 if not level_ok and skill == "agility" else 0)
        initial["inventory"].update({"item.coal": 1, "item.iron_bar": 1,
                                     "item.cooked_meat": 1, "item.coins": 2000})
        if carry_tools:
            initial["inventory"].update({"item.tinderbox": 1, "item.spade": 1})
        return RouteState(self.validator.tables, self.profile["policies"], initial)

    def apply(self, state, record, *, travel=False):
        step = {"kind": "travel" if travel else "action",
                "edge_id" if travel else "action_id": record["id"],
                "modeled_seconds": record["duration"]["expected_seconds"]}
        if "planned_outcome" in record:
            step["planned_outcome"] = record["planned_outcome"]
        return state.apply(step)

    def walk_to(self, state, dest):
        if state.location == dest:
            return state
        todo = deque([state])
        seen = {state.location}
        while todo:
            at = todo.popleft()
            for edge in self.walks[at.location]:
                target = edge["to_location_id"]
                if target in seen:
                    continue
                try:
                    next_state = self.apply(at, edge, travel=True)
                except DataError:
                    continue
                if target == dest:
                    return next_state
                seen.add(target)
                todo.append(next_state)
        self.fail(f"No walk connected {state.location} to {dest}")

    def complete_quest(self, state, *, with_camp_tools=False):
        for record in self.batch:
            if record["activity_id"] != QUEST:
                continue
            state = self.walk_to(state, record["start_location_id"])
            try:
                state = self.apply(state, record)
            except DataError as error:
                self.fail(f"Transition {record['id']} failed: {error}")
            if with_camp_tools and record["id"] == QUEST + ".maisa_ullek_briefing":
                for id in ("supply.bcs.camp_tinderbox", "supply.bcs.camp_spade"):
                    state = self.apply(state, self.validator.tables["actions"][id])
        return state

    def test_full_staged_route_with_camp_tools_and_quest_rewards(self):
        original = self.seeded()
        state = self.complete_quest(original, with_camp_tools=True)
        result = state.snapshot()
        self.assertIn(QUEST + ".complete", result["completed_action_ids"])
        self.assertEqual(result["xp_tenths"]["skill.agility"] - original.xp["skill.agility"], 500000)
        self.assertEqual(result["counters"]["token.quest_points"] - original.counters["token.quest_points"], 2)
        self.assertEqual(result["inventory"]["item.keris_partisan"], 1)
        self.assertEqual(result["inventory"]["item.circlet_of_water"], 1)
        self.assertTrue(result["flags"]["unlock.necropolis_akp"])
        self.assertTrue(result["flags"]["unlock.tombs_of_amascut"])
        for spent in ("item.coal", "item.iron_bar", "item.cooked_meat", "item.bcs_cure_crate"):
            self.assertNotIn(spent, result["inventory"])
        with self.assertRaises(DataError):
            self.apply(state, self.validator.tables["actions"][QUEST + ".complete"])

    def test_contact_and_unboostable_skill_gates(self):
        start = self.validator.tables["actions"][QUEST + ".start"]
        with self.assertRaises(DataError):
            self.apply(self.seeded(contact=False), start)
        with self.assertRaises(DataError):
            self.apply(self.seeded(level_ok=False), start)
        self.apply(self.seeded(), start)

    def test_missing_furnace_ingredients_block_stages(self):
        furnace = self.validator.tables["actions"][QUEST + ".ignite_furnace"]
        state = self.seeded(carry_tools=True).snapshot()
        state["location_id"] = "location.bcs.ullek_furnace"
        state["completed_action_ids"].append(QUEST + ".enter_ullek")
        state["inventory"].pop("item.coal")
        with self.assertRaises(DataError):
            self.apply(RouteState(self.validator.tables, self.profile["policies"], state), furnace)

        mould = self.validator.tables["actions"][QUEST + ".forge_emblem"]
        state["completed_action_ids"].append(QUEST + ".open_chest")
        state["inventory"]["item.bcs_scarab_mould"] = 1
        state["inventory"].pop("item.iron_bar")
        with self.assertRaises(DataError):
            self.apply(RouteState(self.validator.tables, self.profile["policies"], state), mould)

    def test_akp_fairy_ring_requires_necropolis_and_normal_ring_access(self):
        edge = self.validator.tables["travel_edges"]["travel.fairy_ring.bcs.to_akp"]
        state = self.seeded().snapshot()
        state["location_id"] = "location.zanaris.fairy_ring"
        state["inventory"]["item.dramen_staff"] = 1
        state["flags"]["unlock.fairy_rings"] = True
        with self.assertRaises(DataError):
            self.apply(RouteState(self.validator.tables, self.profile["policies"], state), edge, travel=True)
        state["completed_action_ids"].append(QUEST + ".meet_maisa")
        state["flags"]["unlock.necropolis_akp"] = True
        moved = self.apply(RouteState(self.validator.tables, self.profile["policies"], state), edge, travel=True)
        self.assertEqual(moved.location, "location.fairy_ring.akp")

    def test_bcs_local_passages_reversible(self):
        pairs = {(edge["from_location_id"], edge["to_location_id"])
                 for edge in self.new_edges if edge["mode"] == "walk"}
        for a, b in pairs:
            self.assertIn((b, a), pairs)

    def test_planned_lever_run_fits_one_minute(self):
        between = next(edge for edge in self.new_edges
                       if edge["from_location_id"] == "location.bcs.first_lever"
                       and edge["to_location_id"] == "location.bcs.second_lever")
        second = self.validator.tables["actions"][QUEST + ".pull_second_lever"]
        self.assertLessEqual(between["duration"]["expected_seconds"]
                             + second["duration"]["expected_seconds"], 60)


if __name__ == "__main__":
    unittest.main()
