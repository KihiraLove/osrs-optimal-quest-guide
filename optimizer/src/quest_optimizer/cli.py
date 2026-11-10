"""Command-line entry point for the validation scaffold."""

import argparse
from pathlib import Path
import sys

from .data import Contracts, DataError, load_catalog, read_json


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate local quest optimizer JSON (no solver yet)")
    parser.add_argument("--schemas", type=Path, default=Path("schemas"), help="Local schema directory")
    commands = parser.add_subparsers(dest="command", required=True)
    catalog_parser = commands.add_parser("validate-data", help="Validate manifest and local collections")
    catalog_parser.add_argument("manifest", type=Path)
    catalog_parser.add_argument("--release", action="store_true", help="Require production release gates")
    document_parser = commands.add_parser("validate-json", help="Check profile or solution structure only")
    document_parser.add_argument("kind", choices=("profile", "solution"))
    document_parser.add_argument("path", type=Path)
    args = parser.parse_args(argv)
    try:
        contracts = Contracts(args.schemas)
        if args.command == "validate-data":
            catalog = load_catalog(args.manifest, contracts, release=args.release)
            print(f"Valid structure: {catalog['dataset_id']} ({catalog['status']}); "
                  f"{len(catalog['actions'])} actions. Gameplay and completeness are not verified.")
        else:
            contracts.validate(args.kind, read_json(args.path))
            print(f"Valid {args.kind} structure. Gameplay and route replay are not verified.")
    except DataError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    return 0
