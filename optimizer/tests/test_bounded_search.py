"""Compare bounded routes, saved incumbents and effectful travel outcomes."""

from contextlib import redirect_stdout
from io import StringIO
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from quest_optimizer.bounded_search import _unique_action_producers, solve_bounded
from quest_optimizer.cli import main
from quest_optimizer.data import Contracts, DataError, load_catalog, read_json
from quest_optimizer.replay import verify_solution
from quest_optimizer.search import solve_small
from quest_optimizer.semantics import CatalogValidator
from quest_optimizer.transitions import RouteState


ROOT = Path(__file__).resolve().parents[2]
EXAMPLE = ROOT / "examples/synthetic"


class BoundedSearchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.contracts = Contracts(ROOT / "schemas")

    def setUp(self):
        self.catalog = load_catalog(EXAMPLE / "manifest.json", self.contracts)
        self.profile = read_json(EXAMPLE / "profile.json")

    def validator(self):
        self.contracts.validate("catalog", self.catalog)
        validator = CatalogValidator(self.catalog, self.contracts)
        validator.validate_catalog()
        return validator

    def test_matches_exact_objective_and_is_repeatable(self):
        validator = self.validator()
        with patch("socket.socket", side_effect=AssertionError("Network forbidden")):
            solution, stats = solve_bounded(validator, self.profile, seed=19)
            self.assertEqual((solution, stats), solve_bounded(validator, self.profile, seed=19))
            exact = solve_small(validator, self.profile)
        self.assertEqual(solution["objective"], exact["objective"])
        self.assertEqual(solution["manual_training_xp_tenths_by_skill"], {"skill.example": 1000})
        self.assertEqual(solution["solver"]["primary_lower_bound_xp_tenths"], 500)
        self.assertIsNone(solution["solver"]["secondary_lower_bound_seconds"])
        self.assertEqual(stats["states_expanded"], 1)

    def test_longer_travel_preserves_item_and_is_replay_verified(self):
        [quest] = self.catalog["actions"]
        evidence = quest["evidence"]
        self.catalog["status"] = self.profile["status"] = "draft"
        self.catalog["coverage_status"] = "incomplete"
        self.catalog["items"] = [{
            "id": "item.permit", "name": "Permit", "tradeable": True, "stackable": False, "evidence": evidence,
        }]
        permit = [{"item_id": "item.permit", "quantity": 1}]
        self.profile["initial_state"]["inventory"] = {"item.permit": 1}
        self.catalog["locations"].append({
            **self.catalog["locations"][0], "id": "location.goal", "name": "Goal", "x": 1,
        })
        quest.update(start_location_id="location.goal", end_location_id="location.goal", consumes=permit)
        self.catalog["travel_edges"] = [
            {
                "id": f"travel.{mode}", "name": mode, "mode": "other",
                "from_location_id": "location.example", "to_location_id": "location.goal",
                "requirements": {"kind": "all", "requirements": []}, "consumes": items, "effects": [],
                "duration": dict.fromkeys(("min_seconds", "expected_seconds", "max_seconds"), seconds),
                "evidence": evidence,
            }
            for mode, items, seconds in (("fast", permit, 1), ("slow", [], 3))
        ]
        validator = self.validator()
        with self.assertRaisesRegex(DataError, "after expanding 1 states"):
            solve_bounded(validator, self.profile, max_expansions=1)
        solution, _ = solve_bounded(validator, self.profile)
        verify_solution(solution, self.profile, validator)
        self.assertEqual(solution["steps"][0]["edge_id"], "travel.slow")
        self.assertEqual(solution["objective"]["modeled_non_training_seconds"], 63)
        self.assertEqual(solution["solver"]["status"], "best_known")
        resumed, stats = solve_bounded(validator, self.profile, max_expansions=1, incumbent=solution)
        self.assertEqual(resumed["objective"], solution["objective"])
        self.assertEqual(stats["states_expanded"], 1)
        self.assertEqual(stats["termination"], "expansion_budget")

    def test_unreachable_goal_is_reported_before_search(self):
        self.catalog["actions"][0]["requirements"] = {
            "kind": "policy", "name": "allow_poh_services", "value": True,
        }
        with self.assertRaisesRegex(DataError, "reachability blocks goals: action.example"):
            solve_bounded(self.validator(), self.profile)

    def test_cli_persists_and_reuses_a_verified_incumbent(self):
        with TemporaryDirectory() as directory:
            incumbent = Path(directory) / "route.json"
            report = Path(directory) / "report.json"
            args = [
                "--schemas", str(ROOT / "schemas"), "solve-bounded", str(EXAMPLE / "manifest.json"),
                str(EXAMPLE / "profile.json"), "--incumbent", str(incumbent), "--report", str(report),
            ]
            for resumed in (False, True):
                output = StringIO()
                with redirect_stdout(output):
                    self.assertEqual(main(args), 0)
                self.assertEqual(json.loads(output.getvalue()), read_json(incumbent))
                stats = read_json(report)
                self.assertEqual(stats["resumed_from_incumbent"], resumed)
                self.assertGreater(stats["peak_traced_bytes"], 0)
            solution = read_json(incumbent)
            solution["objective"]["manual_training_xp_tenths"] = 0
            incumbent.write_text(json.dumps(solution), encoding="utf-8")
            with self.assertRaisesRegex(DataError, "objective.manual_training_xp_tenths"):
                solve_bounded(self.validator(), self.profile, incumbent=read_json(incumbent))

    def test_balloon_detour_beats_the_restricted_baseline(self):
        catalog = load_catalog(ROOT / "data/manifest.json", self.contracts)
        validator = CatalogValidator(catalog, self.contracts)
        profile = read_json(ROOT / "examples/build-242/balloon-travel-profile.json")
        profile["initial_state"]["xp_tenths"]["skill.firemaking"] = 352240
        profile["initial_state"]["inventory"]["item.oak_logs"] = 11
        detour = "transport.balloon.crafting_guild.unlock"
        solution, _ = solve_bounded(validator, profile)
        # Isolate a training-only baseline as the catalog gains new XP sources.
        xp_sources = tuple(
            action["id"] for action in catalog["actions"]
            if action["id"] not in profile["goal_action_ids"] and any(
                effect["kind"] == "xp_reward"
                or (effect["kind"] == "xp" and effect["skill_id"] == "skill.firemaking")
                for effect in action["effects"]
            )
        )
        baseline, _ = solve_bounded(validator, profile, excluded_actions=xp_sources)
        self.assertEqual(solution["steps"][0]["action_id"], detour)
        self.assertEqual(solution["manual_training_xp_tenths_by_skill"], {})
        self.assertEqual(baseline["manual_training_xp_tenths_by_skill"], {"skill.firemaking": 20000})
        self.assertGreater(solution["objective"]["modeled_non_training_seconds"],
                           baseline["objective"]["modeled_non_training_seconds"])

    def test_future_key_treasure_does_not_hide_current_lost_city_rune_supply(self):
        catalog = load_catalog(ROOT / "data/manifest.json", self.contracts)
        validator = CatalogValidator(catalog, self.contracts)
        profile = read_json(ROOT / "examples/build-242/lost-city-combat-profile.json")
        initial = RouteState(validator.tables, profile["policies"], profile["initial_state"])
        chosen = _unique_action_producers(initial)
        self.assertEqual(chosen[("item", "item.mind_rune")],
                         "supply.grand_exchange.purchase_lost_city_runes")
