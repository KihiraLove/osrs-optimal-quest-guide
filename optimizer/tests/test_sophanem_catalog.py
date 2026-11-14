"""Seeded gameplay and graph checks for the two Sophanem quest routes."""

from collections import defaultdict, deque
from pathlib import Path
import unittest

from quest_optimizer.data import Contracts, DataError, load_catalog, read_json
from quest_optimizer.semantics import CatalogValidator
from quest_optimizer.transitions import RouteState


ROOT = Path(__file__).resolve().parents[2]


class SophanemQuestTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        contracts = Contracts(ROOT / "schemas")
        cls.catalog = load_catalog(ROOT / "data/manifest.json", contracts)
        cls.validator = CatalogValidator(cls.catalog, contracts)
        cls.baseline = read_json(ROOT / "data/profiles/main-baseline.json")
        cls.actions = read_json(ROOT / "data/catalog/sophanem-quests/actions.json")
        cls.new_edges = read_json(ROOT / "data/catalog/sophanem-quests/travel_edges.json")
        cls.walks = defaultdict(list)
        for edge in cls.validator.tables["travel_edges"].values():
            if edge["mode"] == "walk":
                cls.walks[edge["from_location_id"]].append(edge)

    def state(self, *, gertrude=True, ali=True, lamp=True):
        initial = read_json(ROOT / "data/profiles/main-baseline.json")["initial_state"]
        initial["location_id"] = "location.sophanem.wanderer"
        initial["inventory"].update({
            "item.pet_kitten": 1,
            "item.coins": 6000,
            "item.waterskin_4": 1,
            "item.tinderbox": 1,
            "item.willow_logs": 1,
            "item.bucket_of_sap": 1,
            "item.bag_of_salt": 1,
            "item.lit_candle": int(lamp),
        })
        if not lamp:
            del initial["inventory"]["item.lit_candle"]
        initial["completed_action_ids"] = (["quest.gertrudes_cat.complete"] if gertrude else []) + (
            ["quest.prince_ali_rescue.complete"] if ali else [])
        return RouteState(self.validator.tables, self.baseline["policies"], initial)

    def apply(self, state, record, *, travel=False):
        step = {"kind": "travel" if travel else "action",
                "edge_id" if travel else "action_id": record["id"],
                "modeled_seconds": record["duration"]["expected_seconds"]}
        if "planned_outcome" in record:
            step["planned_outcome"] = record["planned_outcome"]
        return state.apply(step)

    def walk_to(self, state, destination):
        if state.location == destination:
            return state
        search = deque([state])
        seen = {state.location}
        while search:
            position = search.popleft()
            for edge in self.walks[position.location]:
                end = edge["to_location_id"]
                if end in seen:
                    continue
                try:
                    advanced = self.apply(position, edge, travel=True)
                except DataError:
                    continue
                if end == destination:
                    return advanced
                seen.add(end)
                search.append(advanced)
        self.fail(f"No currently usable walk from {state.location} to {destination}")

    def test_sophanem_quest_chain_replays_and_prevents_duplicate_rewards(self):
        state = self.state()
        quest_actions = [action for action in self.actions if action["activity_id"] in
                         ("quest.icthlarins_little_helper", "quest.contact")]
        for record in quest_actions:
            state = self.walk_to(state, record["start_location_id"])
            try:
                state = self.apply(state, record)
            except DataError as error:
                self.fail(f"Could not complete {record['id']}: {error}")

        final = state.snapshot()
        self.assertEqual(final["counters"]["token.quest_points"], 4)
        self.assertEqual(final["xp_tenths"]["skill.thieving"], 115000)
        self.assertEqual(final["xp_tenths"]["skill.agility"], 40000)
        self.assertEqual(final["xp_tenths"]["skill.woodcutting"], 40000)
        self.assertEqual(final["inventory"]["item.icthlarin_catspeak_amulet"], 1)
        self.assertEqual(final["inventory"]["item.keris"], 1)
        self.assertNotIn("item.icthlarin_linen", final["inventory"])
        self.assertTrue(final["flags"]["unlock.sophanem_bank"])
        self.assertTrue(final["flags"]["flag.quest.contact.complete"])
        self.assertEqual(len(final["held_rewards"]), 1)
        self.assertEqual(final["held_rewards"][0]["remaining_picks"], 2)
        with self.assertRaises(DataError):
            self.apply(state, quest_actions[-1])
        instance = "reward.contact.combat_lamp.instance.1"
        for remaining in (1, 0):
            state = state.apply({"kind": "reward_use", "reward_id": "reward.contact.combat_lamp",
                                 "instance_id": instance, "skill_id": "skill.attack",
                                 "gain_xp_tenths": 70000,
                                 "overrides_observed_skill_restriction": False})
            self.assertEqual(len(state.snapshot()["held_rewards"]), int(bool(remaining)))
        self.assertEqual(state.snapshot()["xp_tenths"]["skill.attack"], 140000)
        with self.assertRaises(DataError):
            state.apply({"kind": "reward_use", "reward_id": "reward.contact.combat_lamp",
                         "instance_id": instance, "skill_id": "skill.attack",
                         "gain_xp_tenths": 70000, "overrides_observed_skill_restriction": False})

    def test_prerequisite_and_light_source_gates(self):
        start = self.validator.tables["actions"]["quest.icthlarins_little_helper.start"]
        with self.assertRaisesRegex(DataError, "required completed action"):
            self.apply(self.state(gertrude=False), start)
        contact = self.validator.tables["actions"]["quest.contact.start"]
        without_ali = self.state(ali=False).snapshot()
        without_ali["location_id"] = contact["start_location_id"]
        without_ali["completed_action_ids"].append("quest.icthlarins_little_helper.complete")
        with self.assertRaisesRegex(DataError, "required completed action"):
            self.apply(RouteState(self.validator.tables, self.baseline["policies"], without_ali), contact)
        enter = self.validator.tables["actions"]["quest.contact.enter_bank"]
        dark = self.state(lamp=False).snapshot()
        dark["location_id"] = enter["start_location_id"]
        dark["completed_action_ids"].extend(["quest.icthlarins_little_helper.complete",
                                             "quest.contact.start", "quest.contact.consult_jex"])
        with self.assertRaisesRegex(DataError, "required item"):
            self.apply(RouteState(self.validator.tables, self.baseline["policies"], dark), enter)

    def test_pyramid_and_chasm_have_two_way_exits(self):
        pairs = {(edge["from_location_id"], edge["to_location_id"]) for edge in self.new_edges}
        for start, end in pairs:
            self.assertIn((end, start), pairs)
        for place in ("location.sophanem.pyramid_west_room", "location.sophanem.pyramid_jars",
                      "location.sophanem.pyramid_east_room", "location.contact.scarab"):
            self.assertTrue(any(from_id == place for from_id, _ in pairs))


if __name__ == "__main__":
    unittest.main()
