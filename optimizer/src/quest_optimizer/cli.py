"""Command-line entry point for local JSON validation."""

import argparse
from pathlib import Path
import sys

from .data import Contracts, DataError, load_catalog, read_json
from .semantics import CatalogValidator


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate local quest optimizer JSON (no solver yet)")
    parser.add_argument("--schemas", type=Path, default=Path("schemas"), help="Local schema directory")
    commands = parser.add_subparsers(dest="command", required=True)
    catalog_parser = commands.add_parser("validate-data", help="Check catalog structure and semantics")
    catalog_parser.add_argument("manifest", type=Path)
    catalog_parser.add_argument("--release", action="store_true", help="Require production release gates")
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
                print(f"Valid {args.kind} structure and references.")
            else:
                print(f"Valid {args.kind} structure.")
    except DataError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    return 0
