"""Strict local JSON loading and structural validation, not gameplay validation."""

import json
import math
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker
from jsonschema.exceptions import SchemaError
from referencing import Registry, Resource
from referencing.exceptions import NoSuchResource, Unresolvable

SCHEMA_NAMES = ("common", "manifest", "catalog", "profile", "solution")
SCHEMA_VERSION = "0.1.0"


class DataError(ValueError):
    """A local input failed loading or validation."""


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise DataError(f"Duplicate JSON key: {key}")
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise DataError(f"Non-finite JSON number: {value}")


def _finite_float(value: str) -> float:
    number = float(value)
    if not math.isfinite(number):
        raise DataError(f"Non-finite JSON number: {value}")
    return number


def read_json(path: Path) -> Any:
    try:
        return json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=_unique_object,
            parse_constant=_reject_constant,
            parse_float=_finite_float,
        )
    except (OSError, UnicodeError, ValueError) as exc:
        raise DataError(f"{path}: {exc}") from exc


def _deny_remote_reference(uri: str) -> Resource:
    # Unknown references must fail, never fall back to HTTP retrieval.
    raise NoSuchResource(ref=uri)


class Contracts:
    """Load the five committed schemas into an offline reference registry."""

    def __init__(self, directory: Path):
        self.schemas = {}
        registry: Registry = Registry(retrieve=_deny_remote_reference)
        for name in SCHEMA_NAMES:
            path = directory / f"{name}.schema.json"
            value = read_json(path)
            try:
                Draft202012Validator.check_schema(value)
                expected_id = f"urn:quest-optimizer:{name}:{SCHEMA_VERSION}"
                if value.get("$id") != expected_id:
                    raise DataError(f"{path}: expected schema ID {expected_id}")
                registry = registry.with_resource(expected_id, Resource.from_contents(value))
            except (SchemaError, ValueError, TypeError, KeyError) as exc:
                raise DataError(f"{path}: invalid schema: {exc}") from exc
            self.schemas[name] = value
        self.registry = registry

    def validate(self, name: str, value: Any) -> None:
        validator = Draft202012Validator(
            self.schemas[name], registry=self.registry, format_checker=FormatChecker()
        )
        try:
            errors = list(validator.iter_errors(value))
        except Unresolvable as exc:
            raise DataError(f"Unresolvable local schema reference: {exc}") from exc
        if errors:
            messages = []
            for error in sorted(errors, key=lambda e: str(list(e.absolute_path)))[:10]:
                location = ".".join(str(part) for part in error.absolute_path) or "<root>"
                messages.append(f"{location}: {error.message}")
            raise DataError(f"{name} validation failed:\n" + "\n".join(messages))


def _collection_path(directory: Path, value: str) -> Path:
    candidate = Path(value)
    if candidate.is_absolute() or candidate.drive or ":" in value or "\\" in value:
        raise DataError(f"Collection path must be relative with forward slashes: {value}")
    resolved = (directory / candidate).resolve()
    if not resolved.is_relative_to(directory) or resolved.suffix != ".json":
        raise DataError(f"Collection path must be a JSON file inside {directory}: {value}")
    return resolved


def load_catalog(manifest_path: Path, contracts: Contracts, *, release: bool = False) -> dict:
    manifest_path = manifest_path.resolve()
    manifest = read_json(manifest_path)
    contracts.validate("manifest", manifest)
    catalog = {key: value for key, value in manifest.items() if key != "collections"}
    loaded_paths: set[Path] = set()
    for name, files in manifest["collections"].items():
        records = []
        for filename in files:
            path = _collection_path(manifest_path.parent, filename)
            if path in loaded_paths:
                raise DataError(f"Collection file listed more than once: {path}")
            loaded_paths.add(path)
            values = read_json(path)
            if not isinstance(values, list):
                raise DataError(f"{path}: expected a JSON array of records")
            records.extend(values)
        catalog[name] = records
    contracts.validate("catalog", catalog)

    seen: set[str] = set()
    source_ids = {source["id"] for source in catalog["sources"]}
    for name in manifest["collections"]:
        for record in catalog[name]:
            record_id = record["id"]
            if record_id in seen:
                raise DataError(f"Duplicate entity ID: {record_id}")
            seen.add(record_id)
            for source_id in record.get("evidence", {}).get("source_ids", []):
                if source_id not in source_ids:
                    raise DataError(f"{record_id}: unknown provenance source {source_id}")

    if release:
        if catalog["status"] != "reviewed" or catalog["coverage_status"] != "complete":
            raise DataError("Release blocked: catalog must be reviewed with complete coverage")
        # Do not let structural validation stand in for gameplay/coverage verification.
        raise DataError("Release blocked: semantic validation and coverage audit are not implemented")
    return catalog
