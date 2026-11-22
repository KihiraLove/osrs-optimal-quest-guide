"""Replay Camdozaal relic searches, first donations and the Bone Voyage gate."""

from copy import deepcopy
from pathlib import Path
import unittest

from quest_optimizer.data import Contracts, DataError, load_catalog, read_json
from quest_optimizer.semantics import CatalogValidator
from quest_optimizer.transitions import RouteState


ROOT = Path(__file__).resolve().parents[2]
QUEST = "quest.below_ice_mountain.complete"
RELICS = ("globe", "ledger", "astroscope", "treatise", "carcanet")
KUDOS = "token.museum.kudos"


class CamdozaalRelicTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        contracts = Contracts(ROOT / "schemas")
        catalog = load_catalog(ROOT / "data/manifest.json", contracts)
        cls.tables = CatalogValidator(catalog, contracts).tables
        cls.profile = read_json(ROOT / "examples/build-242/museum-quiz-profile.json")

    def seed(self, *, quest=True, mining=14, smithing=14, tools=("bronze_pickaxe", "hammer")):
        initial = deepcopy(self.profile["initial_state"])
        initial["location_id"] = "location.arrav.dov_mine"
        initial["counters"][KUDOS] = 95
        initial["inventory"] = {"item." + tool: 1 for tool in tools}
        if quest:
            initial["flags"]["flag." + QUEST] = True
            initial["completed_action_ids"].append(QUEST)
        for skill, level in (("skill.mining", mining), ("skill.smithing", smithing)):
            initial["xp_tenths"][skill] = self.tables["skills"][skill]["xp_thresholds_tenths"][level - 1]
        return RouteState(self.tables, self.profile["policies"], initial)

    def follow(self, state, *ids):
        for record_id in ids:
            if record_id.startswith("travel."):
                record = self.tables["travel_edges"][record_id]
                step = {"kind": "travel", "edge_id": record_id}
            else:
                record = self.tables["actions"][record_id]
                step = {"kind": "action", "action_id": record_id}
                if "planned_outcome" in record:
                    step["planned_outcome"] = record["planned_outcome"]
            state = state.apply({**step, "modeled_seconds": record["duration"]["expected_seconds"]})
        return state

    def test_search_requires_access_skills_tools_and_observed_drop(self):
        search = "supply.camdozaal.ancient_globe"
        for setup in ({"quest": False}, {"mining": 13}, {"smithing": 13},
                      {"tools": ("hammer",)}, {"tools": ("bronze_pickaxe",)},
                      {"mining": 40, "tools": ("rune_pickaxe", "hammer")}):
            with self.subTest(setup=setup), self.assertRaises(DataError):
                self.follow(self.seed(**setup), search)
        state = self.seed(mining=41, tools=("rune_pickaxe", "hammer"))
        with self.assertRaisesRegex(DataError, "planned_outcome"):
            state.apply({"kind": "action", "action_id": search,
                         "modeled_seconds": self.tables["actions"][search]["duration"]["expected_seconds"]})
        found = self.follow(state, search)
        self.assertEqual(found.inventory["item.camdozaal.ancient_globe"], 1)
        self.assertEqual(found.inventory["item.hammer"], 1)
        self.assertEqual(found.inventory["item.rune_pickaxe"], 1)
        with self.assertRaises(DataError):
            self.follow(found, "travel.arrav.ramarno_mine_out", search)

    def test_five_unique_hand_ins_open_bone_voyage_and_survive_resume(self):
        start = state = self.seed()
        for i, name in enumerate(RELICS):
            if i:
                state = self.follow(state, "travel.arrav.ramarno_mine_out")
            state = self.follow(state, "supply.camdozaal.ancient_" + name)
        self.assertEqual(state.xp["skill.mining"] - start.xp["skill.mining"], 5 * 320)
        self.assertEqual(state.xp["skill.smithing"] - start.xp["skill.smithing"], 5 * 300)
        state = self.follow(state, "travel.arrav.camdozaal_ramarno_back", "travel.camdozaal.exit",
                            "travel.walk.camdozaal_approach.digwillow_camdoor.back",
                            "travel.walk.camdozaal_approach.digwillow_white_tree.out",
                            "travel.walk.garden.deadtree_nulodion.out", "travel.walk.ice_mountain.nulodion.back",
                            "travel.walk.taverley.doric.back", "travel.walk.taverley.kaqemeex.back",
                            "travel.walk.taverley.varrock.out", "travel.walk.varrock.museum.out")
        snapshot = state.snapshot()
        del snapshot["inventory"]["item.camdozaal.ancient_ledger"]
        missing = RouteState(self.tables, self.profile["policies"], snapshot)
        with self.assertRaisesRegex(DataError, "consumes"):
            self.follow(missing, "museum.camdozaal.ancient_ledger")

        for i, name in enumerate(RELICS, 1):
            with self.assertRaises(DataError):
                self.follow(state, "quest.bone_voyage.start")
            state = self.follow(state, "museum.camdozaal.ancient_" + name)
            self.assertEqual(state.inventory["item.camdozaal.ancient_" + name], 0)
            self.assertEqual(state.counters[KUDOS], 95 + i)
            self.assertEqual(state.inventory["item.coins"], 200 * i)
        self.assertEqual(self.follow(state, "quest.bone_voyage.start").counters[KUDOS], 100)

        snapshot = state.snapshot()
        snapshot["inventory"]["item.camdozaal.ancient_globe"] = 1
        resumed = RouteState(self.tables, self.profile["policies"], snapshot)
        with self.assertRaisesRegex(DataError, "repeat limit"):
            self.follow(resumed, "museum.camdozaal.ancient_globe")
