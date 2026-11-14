"""Three ghostly-robe variants, postquest museum claim and Khazard's ghost."""

from collections import defaultdict, deque
from pathlib import Path
import unittest

from quest_optimizer.data import Contracts, DataError, load_catalog, read_json
from quest_optimizer.semantics import CatalogValidator
from quest_optimizer.transitions import RouteState


ROOT = Path(__file__).resolve().parents[2]
BATCH = ROOT / "data/catalog/ghostly-miniquests"
CURSE = "miniquest.curse_of_the_empty_lord"
SHADOW = "miniquest.the_generals_shadow"
SEQUENCES = ("shipwreck", "wilderness", "desert")


class GhostlyMiniquestsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        contracts = Contracts(ROOT / "schemas")
        cls.tables = CatalogValidator(load_catalog(ROOT / "data/manifest.json", contracts), contracts).tables
        cls.profile = read_json(ROOT / "data/profiles/main-baseline.json")
        cls.actions = {r["id"]: r for r in read_json(BATCH / "actions.json")}
        cls.walks = defaultdict(list)
        for e in cls.tables["travel_edges"].values():
            if e["mode"] in ("walk", "ship", "other", "lever"):
                cls.walks[e["from_location_id"]].append(e)

    def seeded(self, *, with_ring=True, prayer_level=31):
        init = read_json(ROOT / "data/profiles/main-baseline.json")["initial_state"]
        init["location_id"] = "location.baxtorian_falls.glarials_tombstone"
        init["completed_action_ids"] = ["quest.the_restless_ghost.start", "quest.fight_arena.complete",
                                        "quest.priest_in_peril.complete",
                                        "quest.priest_in_peril.inspect_temple",
                                        "quest.priest_in_peril.defeat_guardian",
                                        "quest.priest_in_peril.obtain_golden_key",
                                        "quest.priest_in_peril.free_drezel"]
        init["flags"]["unlock.morytania"] = True
        if with_ring:
            init["completed_action_ids"].append("quest.desert_treasure_i.visibility_ring")
            init["inventory"]["item.ring_of_visibility"] = 1
        init["inventory"].update({"item.ghostspeak_amulet": 1, "item.knife": 1,
                                  "item.coins": 9000})
        init["xp_tenths"]["skill.prayer"] = self.tables["skills"]["skill.prayer"]["xp_thresholds_tenths"][prayer_level-1]
        return RouteState(self.tables, self.profile["policies"], init)

    def apply(self, state, record, travel=False):
        step = {"kind": "travel" if travel else "action",
                "edge_id" if travel else "action_id": record["id"],
                "modeled_seconds": record["duration"]["expected_seconds"]}
        if "planned_outcome" in record:
            step["planned_outcome"] = record["planned_outcome"]
        return state.apply(step)

    def to(self, state, target):
        if state.location == target:
            return state
        queue = deque([state])
        visited = {state.location}
        while queue:
            current = queue.popleft()
            for edge in self.walks[current.location]:
                if edge["to_location_id"] in visited:
                    continue
                try:
                    next_state = self.apply(current, edge, True)
                except DataError:
                    continue
                if next_state.location == target:
                    return next_state
                visited.add(next_state.location)
                queue.append(next_state)
        self.fail(f"No connected public route from {state.location} to {target} (visited {len(visited)})")

    def do(self, state, ident):
        record = self.tables["actions"][ident]
        return self.apply(self.to(state, record["start_location_id"]), record)

    def curse(self, state, sequence):
        state = self.do(state, CURSE + ".valdez")
        state = self.do(state, CURSE + ".clue_" + sequence)
        for ghost in ("rennard", "kharrim", "lennissa", "dhalak", "viggora"):
            if sequence == "shipwreck" and ghost == "lennissa":
                # The existing ferry honors Entrana's weapons restriction.
                state = self.do(state, "supply.bank.deposit_entrana_gear")
            state = self.do(state, CURSE + "." + ghost + "_" + sequence)
        return self.do(state, CURSE + ".complete")

    def test_three_ghostly_robe_clue_sequences(self):
        for sequence in SEQUENCES:
            with self.subTest(sequence=sequence):
                result = self.curse(self.seeded(), sequence)
                snap = result.snapshot()
                self.assertIn(CURSE + ".complete", snap["completed_action_ids"])
                self.assertEqual(snap["choices"]["choice.curse_of_the_empty_lord.sequence"], sequence)
                for piece in ("ghostly_robe_top", "ghostly_gloves", "ghostly_boots",
                              "ghostly_robe_bottom", "ghostly_hood", "ghostly_cloak"):
                    self.assertEqual(snap["inventory"]["item." + piece], 1)
                self.assertTrue(snap["flags"]["flag.miniquest.curse_of_the_empty_lord.complete"])
                with self.assertRaises(DataError):
                    self.do(result, CURSE + ".complete")

    def test_khazard_and_separate_museum_reward(self):
        state = self.curse(self.seeded(), "wilderness")
        state = self.do(state, "museum.history.empty_lord")
        self.assertEqual(state.snapshot()["counters"]["token.museum.kudos"], 10)
        self.assertEqual([r["reward_id"] for r in state.snapshot()["held_rewards"]],
                         ["reward.curse_of_the_empty_lord.museum_lamp"])
        with self.assertRaises(DataError):
            self.do(state, "museum.history.empty_lord")
        original = state.snapshot()
        for ident in ("start", "sin_seer", "show_note", "scout_shantay", "scout_falador",
                      "scout_karamja", "scout_gnome", "report_scouts", "enter_cave",
                      "enter_crack", "complete"):
            state = self.do(state, SHADOW + "." + ident)
        result = state.snapshot()
        self.assertEqual(result["xp_tenths"]["skill.slayer"] - original["xp_tenths"]["skill.slayer"], 20000)
        self.assertEqual(result["inventory"]["item.shadow_sword"], 1)
        self.assertTrue(result["flags"]["flag.miniquest.the_generals_shadow.complete"])
        self.assertNotIn("item.severed_leg", result["inventory"])
        with self.assertRaises(DataError):
            self.do(state, SHADOW + ".complete")

    def test_ring_and_prayer_gates_and_exclusive_choice(self):
        no_ring = self.seeded(with_ring=False).snapshot()
        no_ring["location_id"] = self.actions[CURSE + ".valdez"]["start_location_id"]
        with self.assertRaises(DataError):
            self.apply(RouteState(self.tables, self.profile["policies"], no_ring),
                       self.actions[CURSE + ".valdez"])
        state = self.seeded()
        state = self.do(state, CURSE + ".valdez")
        state = self.do(state, CURSE + ".clue_shipwreck")
        with self.assertRaises(DataError):
            self.do(state, CURSE + ".clue_desert")

        low_prayer = self.seeded(prayer_level=30).snapshot()
        low_prayer["location_id"] = self.actions[CURSE + ".dhalak_wilderness"]["start_location_id"]
        low_prayer["completed_action_ids"].append(CURSE + ".lennissa_wilderness")
        low_prayer.setdefault("choices", {})["choice.curse_of_the_empty_lord.sequence"] = "wilderness"
        with self.assertRaises(DataError):
            self.apply(RouteState(self.tables, self.profile["policies"], low_prayer),
                       self.actions[CURSE + ".dhalak_wilderness"])

    def test_khazard_scouters_are_order_independent(self):
        for place in ("scout_gnome", "scout_karamja", "scout_falador", "scout_shantay"):
            action = self.actions[SHADOW + "." + place]
            ordered = [r["action_id"] for r in action["requirements"]["requirements"]
                       if r["kind"] == "action_completed"]
            self.assertEqual(ordered, [SHADOW + ".show_note"])


if __name__ == "__main__":
    unittest.main()
