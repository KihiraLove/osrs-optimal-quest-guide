"""King's Ransom, separate antique lamp, and eight Knight Waves."""

from collections import deque
from pathlib import Path
import unittest

from quest_optimizer.data import Contracts, DataError, load_catalog, read_json
from quest_optimizer.semantics import CatalogValidator
from quest_optimizer.transitions import RouteState


ROOT = Path(__file__).resolve().parents[2]
QUEST = "quest.kings_ransom."
WAVES = "activity.knight_waves_training_grounds."


class KingsRansomTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        contracts = Contracts(ROOT / "schemas")
        cls.tables = CatalogValidator(load_catalog(ROOT / "data/manifest.json", contracts), contracts).tables
        cls.profile = read_json(ROOT / "data/profiles/main-baseline.json")
        cls.connections = {}
        for edge_id, edge in cls.tables["travel_edges"].items():
            cls.connections.setdefault(edge["from_location_id"], []).append((edge_id, edge["to_location_id"]))

    def seed(self, location="location.kings_ransom.gossip"):
        initial = {**self.profile["initial_state"]}
        initial["location_id"] = location
        initial["xp_tenths"] = {skill: 10000000 for skill in initial["xp_tenths"]}
        initial["counters"] = {**initial["counters"], "token.quest_points": 100}
        initial["completed_action_ids"] = [
            "quest.black_knights_fortress.complete", "quest.holy_grail.complete",
            "quest.murder_mystery.complete", "quest.one_small_favour.complete"]
        initial["inventory"] = {**initial["inventory"], **{
            "item.coins": 15000, "item.black_full_helm": 1,
            "item.black_platebody": 1, "item.black_platelegs": 1,
            "item.granite_5kg": 1, "item.bronze_med_helm": 1,
            "item.iron_chainbody": 1, "item.air_rune": 1, "item.law_rune": 1,
        }}
        return RouteState(self.tables, self.profile["policies"], initial)

    def transition(self, state, id):
        travel = id.startswith("travel.")
        record = self.tables["travel_edges" if travel else "actions"][id]
        step = {"kind": "travel" if travel else "action",
                "edge_id" if travel else "action_id": id,
                "modeled_seconds": record["duration"]["expected_seconds"]}
        if record.get("planned_outcome"):
            step["planned_outcome"] = record["planned_outcome"]
        return state.apply(step, id)

    def move(self, state, target):
        source = state.snapshot()["location_id"]
        if source == target:
            return state
        queue = deque([(source, ())])
        seen = {source}
        while queue:
            position, prefix = queue.popleft()
            for edge_id, dest in sorted(self.connections.get(position, ())):
                if dest in seen:
                    continue
                probe = RouteState(self.tables, self.profile["policies"], state.snapshot())
                try:
                    for edge in (*prefix, edge_id):
                        probe = self.transition(probe, edge)
                except DataError:
                    continue
                path = (*prefix, edge_id)
                if dest == target:
                    for edge in path:
                        state = self.transition(state, edge)
                    return state
                seen.add(dest)
                queue.append((dest, path))
        self.fail(f"Cannot navigate from {source} to {target}")

    def act(self, state, id):
        action = self.tables["actions"][id]
        return self.transition(self.move(state, action["start_location_id"]), id)

    def replay_quest(self):
        state = self.seed()
        route = (
            "start", "question_guard", "break_window", "collect_scrap",
            "collect_form", "search_bookcase", "deliver_evidence",
            "learn_about_anna", "visit_anna", "begin_trial", "handler_poison",
            "butler_dagger", "maid_night", "maid_thread", "return_to_anna",
            "enter_statue", "talk_merlin", "reach_vent", "grab_hair_clip",
            "unlock_prison_door", "climb_prison_stairs", "climb_upper_stairs",
            "take_holy_grail", "ask_cromperty", "enter_fortress",
            "push_hidden_wall", "descend_fortress", "animate_arthur",
            "disguise_arthur", "complete"
        )
        for name in route:
            state = self.act(state, QUEST+name)
        return state

    def test_quest_and_lamp_are_separate(self):
        state = self.replay_quest()
        result = state.snapshot()
        self.assertEqual(result["counters"]["token.quest_points"], 101)
        self.assertEqual(result["xp_tenths"]["skill.defence"], 10330000)
        self.assertEqual(result["xp_tenths"]["skill.magic"], 10050430)
        self.assertTrue(result["flags"]["unlock.kings_ransom_knight_waves"])
        self.assertFalse(result["flags"].get("unlock.piety_prayer", False))
        self.assertEqual(len(result["held_rewards"]), 1)
        self.assertEqual(result["inventory"].get("item.granite_5kg", 0), 0)
        self.assertEqual(result["inventory"].get("item.holy_grail", 0), 0)
        self.assertEqual(result["inventory"].get("item.bronze_med_helm", 0), 0)
        with self.assertRaises(DataError):
            self.transition(state, QUEST+"complete")

        state = state.apply({"kind": "reward_use",
                             "reward_id": "reward.kings_ransom.antique_lamp",
                             "instance_id": "reward.kings_ransom.antique_lamp.instance.1",
                             "skill_id": "skill.herblore", "gain_xp_tenths": 50000,
                             "overrides_observed_skill_restriction": False})
        self.assertEqual(state.snapshot()["xp_tenths"]["skill.herblore"], 10050000)
        self.assertEqual(state.snapshot()["held_rewards"], [])
        with self.assertRaises(DataError):
            state.apply({"kind": "reward_use",
                         "reward_id": "reward.kings_ransom.antique_lamp",
                         "instance_id": "reward.kings_ransom.antique_lamp.instance.1",
                         "skill_id": "skill.herblore", "gain_xp_tenths": 50000,
                         "overrides_observed_skill_restriction": False})

    def test_eight_waves_award_xp_once_and_unlock_prayers(self):
        state = self.replay_quest()
        with self.assertRaises(DataError):
            self.transition(state, WAVES+"complete")
        for name in ("start", "defeat_bedivere", "defeat_pelleas", "defeat_tristram",
                     "defeat_palomedes", "defeat_lucan", "defeat_gawain",
                     "defeat_kay", "defeat_lancelot", "complete"):
            state = self.act(state, WAVES+name)
        snap = state.snapshot()
        self.assertTrue(snap["flags"]["unlock.chivalry_prayer"])
        self.assertTrue(snap["flags"]["unlock.piety_prayer"])
        for name in ("attack", "strength", "hitpoints"):
            self.assertEqual(snap["xp_tenths"]["skill."+name], 10200000)
        self.assertEqual(snap["xp_tenths"]["skill.defence"], 10530000)
        self.assertEqual(snap["counters"]["token.quest_points"], 101)
        with self.assertRaises(DataError):
            self.transition(state, WAVES+"complete")

    def test_missing_prerequisite_and_magic_skill_fail(self):
        state = self.seed()
        initial = state.snapshot()
        initial["completed_action_ids"].remove("quest.one_small_favour.complete")
        with self.assertRaises(DataError):
            self.transition(RouteState(self.tables, self.profile["policies"], initial), QUEST+"start")
        initial = self.seed().snapshot()
        initial["xp_tenths"]["skill.defence"] = 0
        with self.assertRaises(DataError):
            self.transition(RouteState(self.tables, self.profile["policies"], initial), QUEST+"start")
        initial = self.seed("location.kings_ransom.prison_vent").snapshot()
        initial["xp_tenths"]["skill.magic"] = 0
        initial["completed_action_ids"].append(QUEST+"reach_vent")
        with self.assertRaises(DataError):
            self.transition(RouteState(self.tables, self.profile["policies"], initial), QUEST+"grab_hair_clip")


if __name__ == "__main__":
    unittest.main()
