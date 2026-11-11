"""Command-line entry point for offline quest planning."""

import argparse
from pathlib import Path
import sys
from tempfile import NamedTemporaryFile
from time import perf_counter
import tracemalloc

from .bounded_search import solve_bounded
from .coverage import audit_coverage
from .data import Contracts, DataError, load_catalog, read_json
from .normalization import canonical_json, catalog_diff, normalize_catalog
from .replay import verify_solution
from .search import solve_small
from .semantics import CatalogValidator


def _write_incumbent(path: Path, solution: dict) -> None:
    with NamedTemporaryFile(dir=path.parent, encoding="utf-8", mode="w", delete=False) as stream:
        temporary = Path(stream.name)
        try:
            stream.write(canonical_json(solution))
            stream.close()
            temporary.replace(path)
        finally:
            temporary.unlink(missing_ok=True)


def _bounded_command(args, contracts) -> dict:
    validator = CatalogValidator(load_catalog(args.manifest, contracts), contracts)
    profile = read_json(args.profile)
    if args.incumbent and args.report and args.incumbent.resolve() == args.report.resolve():
        raise DataError("The incumbent and report paths must be different")
    incumbent = read_json(args.incumbent) if args.incumbent and args.incumbent.exists() else None
    if args.report:
        tracemalloc.start()
    start = perf_counter()
    try:
        solution, report = solve_bounded(
            validator, profile, beam_width=args.beam_width, max_expansions=args.max_expansions,
            seed=args.seed, excluded_actions=args.exclude_action, incumbent=incumbent,
        )
        elapsed = perf_counter() - start
        peak = tracemalloc.get_traced_memory()[1] if args.report else None
    finally:
        if args.report:
            tracemalloc.stop()

    def objective(route):
        values = route["objective"]
        return tuple(values[key] for key in values["order"] if key != "stable_step_ids")

    try:
        if args.incumbent and (incumbent is None or objective(solution) < objective(incumbent)):
            _write_incumbent(args.incumbent, solution)
        if args.report:
            report.update(
                wall_seconds=round(elapsed, 6), peak_traced_bytes=peak, inputs=solution["inputs"],
                objective=solution["objective"], solver=solution["solver"],
                resumed_from_incumbent=incumbent is not None,
            )
            args.report.write_text(canonical_json(report), encoding="utf-8")
    except OSError as exc:
        raise DataError(f"Could not write search output: {exc}") from exc
    return solution


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Plan and verify quest routes using local JSON")
    parser.add_argument("--schemas", type=Path, default=Path("schemas"), help="Local schema directory")
    commands = parser.add_subparsers(dest="command", required=True)
    catalog_parser = commands.add_parser("validate-data", help="Check catalog structure and semantics")
    catalog_parser.add_argument("manifest", type=Path)
    catalog_parser.add_argument("--release", action="store_true", help="Require production release gates")
    audit_parser = commands.add_parser("audit-data", help="Report coverage, review and reachability gaps as JSON")
    audit_parser.add_argument("manifest", type=Path)
    normalize_parser = commands.add_parser("normalize-data", help="Write canonical catalog JSON to stdout")
    normalize_parser.add_argument("manifest", type=Path)
    normalize_parser.add_argument("--skills", type=Path, help="Adapt the local RuneLite skill observations")
    normalize_parser.add_argument("--observations", type=Path, action="append", default=[], metavar="BATCH")
    diff_parser = commands.add_parser("diff-data", help="Report catalog changes by record and field as JSON")
    diff_parser.add_argument("before", type=Path)
    diff_parser.add_argument("after", type=Path)
    replay_parser = commands.add_parser("replay", help="Verify a route from its catalog and starting profile")
    replay_parser.add_argument("solution", type=Path)
    replay_parser.add_argument("--catalog", required=True, type=Path, metavar="MANIFEST")
    replay_parser.add_argument("--profile", required=True, type=Path)
    replay_parser.add_argument("--release", action="store_true", help="Require the catalog release audit")
    solve_parser = commands.add_parser("solve-small", help="Find an exact route for a small finite instance")
    solve_parser.add_argument("manifest", type=Path)
    solve_parser.add_argument("profile", type=Path)
    solve_parser.add_argument("--max-states", type=int, default=50_000)
    bounded_parser = commands.add_parser("solve-bounded", help="Find a replay-verified route using bounded beam search")
    bounded_parser.add_argument("manifest", type=Path)
    bounded_parser.add_argument("profile", type=Path)
    bounded_parser.add_argument("--beam-width", type=int, default=32)
    bounded_parser.add_argument("--max-expansions", type=int, default=20_000)
    bounded_parser.add_argument("--seed", type=int, default=0)
    bounded_parser.add_argument("--exclude-action", action="append", default=[], metavar="ID")
    bounded_parser.add_argument("--incumbent", type=Path, help="Read and update a saved best route")
    bounded_parser.add_argument("--report", type=Path, help="Write search counters, runtime and traced peak memory")
    document_parser = commands.add_parser("validate-json", help="Check a profile or solution, optionally against its inputs")
    document_parser.add_argument("kind", choices=("profile", "solution"))
    document_parser.add_argument("path", type=Path)
    document_parser.add_argument("--catalog", type=Path, metavar="MANIFEST", help="Check catalog references")
    document_parser.add_argument("--profile", type=Path, help="Check a solution against this profile")
    args = parser.parse_args(argv)
    if args.command == "validate-json":
        if args.kind == "profile" and args.profile:
            document_parser.error("--profile applies to solutions only")
        if args.kind == "solution" and bool(args.catalog) != bool(args.profile):
            document_parser.error("checking solution references requires both --catalog and --profile")
    try:
        contracts = Contracts(args.schemas)
        if args.command == "validate-data":
            catalog = load_catalog(args.manifest, contracts, release=args.release)
            print(f"Valid catalog structure and semantics: {catalog['dataset_id']} "
                  f"({catalog['status']}), {len(catalog['actions'])} actions.")
            if args.release:
                print("Coverage and release profile audit passed.")
        elif args.command == "audit-data":
            catalog = load_catalog(args.manifest, contracts)
            report = audit_coverage(args.manifest, catalog, contracts)
            sys.stdout.write(canonical_json(report))
            return 2 if report["errors"] else 0
        elif args.command == "normalize-data":
            catalog = load_catalog(args.manifest, contracts)
            result = normalize_catalog(catalog, contracts, args.observations, skills=args.skills)
            sys.stdout.write(canonical_json(result))
        elif args.command == "diff-data":
            before = load_catalog(args.before, contracts)
            after = load_catalog(args.after, contracts)
            sys.stdout.write(canonical_json(catalog_diff(before, after)))
        elif args.command == "replay":
            catalog = load_catalog(args.catalog, contracts, release=args.release)
            validator = CatalogValidator(catalog, contracts)
            report = verify_solution(
                read_json(args.solution), read_json(args.profile), validator, release_ready=args.release,
            )
            sys.stdout.write(canonical_json(report))
        elif args.command == "solve-small":
            validator = CatalogValidator(load_catalog(args.manifest, contracts), contracts)
            solution = solve_small(validator, read_json(args.profile), max_states=args.max_states)
            sys.stdout.write(canonical_json(solution))
        elif args.command == "solve-bounded":
            sys.stdout.write(canonical_json(_bounded_command(args, contracts)))
        else:
            document = read_json(args.path)
            contracts.validate(args.kind, document)
            if args.catalog:
                validator = CatalogValidator(load_catalog(args.catalog, contracts), contracts)
                if args.kind == "profile":
                    validator.validate_profile(document, args.path)
                else:
                    profile = read_json(args.profile)
                    contracts.validate("profile", profile)
                    validator.validate_profile(profile, args.profile)
                    validator.validate_solution(document, profile, args.path)
                if args.kind == "solution":
                    print("Valid solution structure, references and reward trace.")
                else:
                    print("Valid profile structure and references.")
            else:
                print(f"Valid {args.kind} structure.")
    except DataError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    return 0
