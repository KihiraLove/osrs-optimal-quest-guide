"""Measure exact and bounded search on pinned local fixtures."""

from copy import deepcopy
from pathlib import Path
from time import perf_counter
import tracemalloc

from quest_optimizer.bounded_search import solve_bounded
from quest_optimizer.data import Contracts, DataError, load_catalog, read_json
from quest_optimizer.normalization import canonical_json
from quest_optimizer.search import solve_small
from quest_optimizer.semantics import CatalogValidator


ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "examples/build-242"


def measure(run):
    tracemalloc.start()
    start = perf_counter()
    try:
        solution, counters = run()
        result = {
            **counters, "inputs": solution["inputs"], "solver": solution["solver"], "objective": solution["objective"],
            "manual_training_xp_tenths_by_skill": solution["manual_training_xp_tenths_by_skill"],
            "route_ids": [step.get("action_id") or step.get("edge_id") or step["kind"] for step in solution["steps"]],
        }
    except DataError as exc:
        result = {"error": str(exc)}
    finally:
        result["wall_seconds"] = round(perf_counter() - start, 6)
        result["peak_traced_bytes"] = tracemalloc.get_traced_memory()[1]
        tracemalloc.stop()
    return result


def fixture_profile(case):
    profile = read_json(FIXTURES / case["base_profile"])
    profile["profile_id"] = f"profile.benchmark.{case['id']}"
    profile["goal_action_ids"].extend(case.get("add_goals", ()))
    for field in ("inventory", "xp_tenths"):
        profile["initial_state"][field].update(case.get(field, {}))
    profile["assumptions"] = ["Synthetic saved account for the " + case["id"] + " benchmark."]
    return profile


def main():
    contracts = Contracts(ROOT / "schemas")
    catalog = load_catalog(ROOT / "data/manifest.json", contracts)
    validator = CatalogValidator(catalog, contracts)
    results = {}
    synthetic = ROOT / "examples/synthetic"
    small = CatalogValidator(load_catalog(synthetic / "manifest.json", contracts), contracts)
    profile = read_json(synthetic / "profile.json")
    results["synthetic"] = {
        "exact": measure(lambda: (solve_small(small, profile, max_states=5000), {"max_states": 5000})),
        "bounded": measure(lambda: solve_bounded(small, profile)),
    }

    for case in read_json(FIXTURES / "search-benchmarks.json"):
        profile = fixture_profile(case)
        runs = {"bounded": measure(lambda: solve_bounded(validator, profile))}
        if baseline := case.get("exclude_for_baseline"):
            runs["restricted_baseline"] = measure(lambda: solve_bounded(validator, profile, excluded_actions=baseline))
        if budget := case.get("exact_state_budget"):
            runs["exact"] = measure(lambda: (solve_small(validator, profile, max_states=budget), {"max_states": budget}))
        if case.get("vary_durations"):
            for estimate in ("min_seconds", "max_seconds"):
                varied = deepcopy(catalog)
                for record in varied["actions"] + varied["travel_edges"]:
                    record["duration"]["expected_seconds"] = record["duration"][estimate]
                alternative = CatalogValidator(varied, contracts)
                runs[estimate] = measure(lambda: solve_bounded(alternative, profile))
        results[case["id"]] = runs
    print(canonical_json(results), end="")
    return int(any(
        "error" in run for case in results.values() for method, run in case.items() if method != "exact"
    ) or "error" in results["synthetic"]["exact"])


if __name__ == "__main__":
    raise SystemExit(main())
