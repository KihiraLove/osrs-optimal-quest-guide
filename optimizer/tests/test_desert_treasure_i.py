"""Connected Desert Treasure I route and four independent diamond branches."""

from collections import defaultdict, deque
from pathlib import Path
import unittest

from quest_optimizer.data import Contracts, DataError, load_catalog, read_json
from quest_optimizer.semantics import CatalogValidator
from quest_optimizer.transitions import RouteState


ROOT = Path(__file__).resolve().parents[2]
QUEST = "quest.desert_treasure_i"
BATCH = ROOT / "data/catalog/desert-treasure-i"


class DesertTreasureITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        contracts = Contracts(ROOT / "schemas")
        cls.tables = CatalogValidator(load_catalog(ROOT / "data/manifest.json", contracts), contracts).tables
        cls.profile = read_json(ROOT / "data/profiles/main-baseline.json")
        cls.actions = {record["id"]: record for record in read_json(BATCH / "actions.json")}
        cls.edges = read_json(BATCH / "travel_edges.json")
        cls.walks = defaultdict(list)
        for edge in cls.tables["travel_edges"].values():
            if edge["mode"] in ("walk", "ship"):
                cls.walks[edge["from_location_id"]].append(edge)

    def seeded(self, *, missing_prereq=False, low_magic=False):
        raw = read_json(ROOT / "data/profiles/main-baseline.json")["initial_state"]
        raw["location_id"] = "location.varrock.grand_exchange"
        prereqs = ("the_dig_site", "temple_of_ikov", "the_tourist_trap",
                   "troll_stronghold", "priest_in_peril", "waterfall_quest", "death_plateau")
        raw["completed_action_ids"] = ["quest." + p + ".complete" for p in prereqs
                                       if not (missing_prereq and p == "temple_of_ikov")]
        raw["completed_action_ids"].extend(("quest.priest_in_peril.inspect_temple",
                                            "quest.priest_in_peril.obtain_golden_key",
                                            "quest.priest_in_peril.defeat_guardian",
                                            "quest.priest_in_peril.free_drezel"))
        for p in prereqs:
            token = "flag.quest." + p + ".complete"
            if token in self.tables["tokens"] and not (missing_prereq and p == "temple_of_ikov"):
                raw["flags"][token] = True
        raw["flags"]["unlock.morytania"] = True
        for name, level in (("magic", 50), ("firemaking", 50),
                            ("thieving", 53), ("slayer", 10)):
            threshold = self.tables["skills"]["skill." + name]["xp_thresholds_tenths"][level - 1]
            raw["xp_tenths"]["skill." + name] = threshold - (10 if low_magic and name == "magic" else 0)
        raw["inventory"].update({"item.coins": 300000})
        return RouteState(self.tables, self.profile["policies"], raw)

    def apply(self, state, record, *, travel=False):
        step = {"kind": "travel" if travel else "action",
                "edge_id" if travel else "action_id": record["id"],
                "modeled_seconds": record["duration"]["expected_seconds"]}
        if "planned_outcome" in record:
            step["planned_outcome"] = record["planned_outcome"]
        return state.apply(step)

    def walk_to(self, state, target):
        if state.location == target:
            return state
        todo = deque([state])
        visited = {state.location}
        while todo:
            current = todo.popleft()
            for edge in self.walks[current.location]:
                if edge["to_location_id"] in visited:
                    continue
                try:
                    moved = self.apply(current, edge, travel=True)
                except DataError:
                    continue
                if moved.location == target:
                    return moved
                visited.add(moved.location)
                todo.append(moved)
        self.fail(f"No connected walking route from {state.location} to {target}; "
                  f"reachable {len(visited)} nodes; hubs "
                  f"{sorted(x for x in visited if x in ('location.varrock.grand_exchange', 'location.burthorpe.dunstan', 'location.trollheim.climbing_rocks', 'location.bedabin_camp.al_shabim') or x.startswith('location.paterdomus'))}")

    def do(self, state, suffix):
        ident = suffix if suffix.startswith("supply.") else QUEST + "." + suffix
        record = self.tables["actions"][ident]
        state = self.walk_to(state, record["start_location_id"])
        return self.apply(state, record)

    def test_complete_quest_and_postquest_claims(self):
        state = self.seeded()
        initial = state.snapshot()
        for short in ("supply.grand_exchange.dt_essentials", "supply.slayer.shop_dt_mask",
                      "supply.burthorpe.dunstan_dt_boots",
                      "start", "expert", "expert_translation", "report_smith",
                      "bartender", "eblis", "offerings", "mirrors",
                      "rasolo", "cross", "visibility_ring", "shadow_entry",
                      "damis_phase_one", "defeat_damis",
                      "smoke_entry", "light_torch_1", "light_torch_2", "light_torch_3",
                      "light_torch_4", "warm_key", "open_fareed_gate", "defeat_fareed",
                      "troll_child", "ice_gate", "ice_guards", "ice_cave",
                      "defeat_kamil", "ice_ledge", "ice_upper_gate", "thaw_trolls", "ice_diamond",
                      "malak", "draynor_sewer", "silver_pot",
                      "supply.bank.deposit_entrana_gear", "bless_pot", "blood_pot",
                      "supply.dt_crush_garlic", "spice_blood_pot", "dessous_ritual",
                      "defeat_dessous", "blood_diamond",
                      "place_shadow", "place_smoke", "place_ice", "place_blood",
                      "enter_pyramid", "descend_first", "descend_second",
                      "descend_third", "meet_azzanadra", "complete",
                      "buy_ancient_staff", "claim_ancient_signet"):
            try:
                state = self.do(state, short)
            except DataError as error:
                self.fail(f"Failed {short}: {error}")
        snapshot = state.snapshot()
        self.assertEqual(snapshot["xp_tenths"]["skill.magic"] - initial["xp_tenths"]["skill.magic"],
                         200000)
        self.assertEqual(snapshot["counters"]["token.quest_points"] - initial["counters"]["token.quest_points"], 3)
        self.assertTrue(snapshot["flags"]["unlock.ancient_magicks"])
        self.assertTrue(snapshot["flags"]["unlock.ancient_pyramid"])
        self.assertEqual(snapshot["inventory"]["item.ring_of_visibility"], 1)
        self.assertEqual(snapshot["inventory"]["item.ancient_staff"], 1)
        self.assertEqual(snapshot["inventory"]["item.ancient_signet"], 1)
        for short in ("smoke_diamond", "shadow_diamond", "ice_diamond", "blood_diamond"):
            self.assertNotIn("item." + short, snapshot["inventory"])
        with self.assertRaises(DataError):
            self.do(state, "complete")
        with self.assertRaises(DataError):
            self.do(state, "buy_ancient_staff")

    def test_quest_start_gates_versus_later_gates(self):
        start = self.actions[QUEST + ".start"]
        for kwargs in ({"missing_prereq": True}, {"low_magic": True}):
            state = self.seeded(**kwargs).snapshot()
            state["location_id"] = start["start_location_id"]
            with self.assertRaises(DataError):
                self.apply(RouteState(self.tables, self.profile["policies"], state), start)
        state = self.seeded().snapshot()
        state["location_id"] = start["start_location_id"]
        self.apply(RouteState(self.tables, self.profile["policies"], state), start)

    def test_thieving_firemaking_and_smoke_protection_are_later_gates(self):
        chest = self.actions[QUEST + ".cross"]
        state = self.seeded().snapshot()
        state["location_id"] = chest["start_location_id"]
        state["completed_action_ids"].append(QUEST + ".rasolo")
        state["inventory"]["item.lockpick"] = 30
        state["xp_tenths"]["skill.thieving"] = 0
        with self.assertRaises(DataError):
            self.apply(RouteState(self.tables, self.profile["policies"], state), chest)

        entry = self.actions[QUEST + ".smoke_entry"]
        state = self.seeded().snapshot()
        state["location_id"] = entry["start_location_id"]
        state["completed_action_ids"].append(QUEST + ".mirrors")
        with self.assertRaises(DataError):
            self.apply(RouteState(self.tables, self.profile["policies"], state), entry)
        state["inventory"]["item.gas_mask"] = 1
        self.apply(RouteState(self.tables, self.profile["policies"], state), entry)

        torch = self.actions[QUEST + ".light_torch_1"]
        state["location_id"] = torch["start_location_id"]
        state["completed_action_ids"].append(QUEST + ".smoke_entry")
        state["xp_tenths"]["skill.firemaking"] = 0
        with self.assertRaises(DataError):
            self.apply(RouteState(self.tables, self.profile["policies"], state), torch)

    def test_smoke_torch_run_is_within_five_minutes(self):
        travel_seconds = 0
        targets = ["torch_1", "torch_2", "torch_3", "torch_4", "warm_chest"]
        for a, b in zip(targets, targets[1:]):
            start, end = "location.dt." + a, "location.dt." + b
            edge = next(e for e in self.edges if e["from_location_id"] == start
                        and e["to_location_id"] == end)
            travel_seconds += edge["duration"]["expected_seconds"]
        interaction_seconds = sum(self.actions[QUEST + ".light_torch_" + str(i)]
                                  ["duration"]["expected_seconds"] for i in (2, 3, 4))
        interaction_seconds += self.actions[QUEST + ".warm_key"]["duration"]["expected_seconds"]
        self.assertLess(travel_seconds + interaction_seconds, 300)

    def test_diamonds_are_independent_but_pyramid_needs_all_four(self):
        for color in ("blood", "smoke", "ice", "shadow"):
            requirements = self.actions[QUEST + ".place_" + color]["requirements"]["requirements"]
            self.assertEqual([r["action_id"] for r in requirements if r["kind"] == "action_completed"],
                             [QUEST + ".mirrors"])
        entry = self.actions[QUEST + ".enter_pyramid"]
        actions = {r["action_id"] for r in entry["requirements"]["requirements"]}
        self.assertEqual(actions, {QUEST + ".place_" + p for p in ("blood", "smoke", "ice", "shadow")})

    def test_new_passages_are_reversible(self):
        pairs = {(r["from_location_id"], r["to_location_id"]) for r in self.edges}
        for a, b in pairs:
            self.assertIn((b, a), pairs)


if __name__ == "__main__":
    unittest.main()
