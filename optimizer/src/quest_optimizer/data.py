"""Offline JSON loading and validation."""

import json
import math
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker
from jsonschema.exceptions import SchemaError, ValidationError
from jsonschema.validators import extend
from referencing import Registry, Resource
from referencing.exceptions import NoSuchResource, Unresolvable

from .errors import DataError
from .semantics import CatalogValidator

SCHEMA_NAMES = ("common", "manifest", "catalog", "profile", "solution")
SCHEMA_VERSION = "0.1.0"
LocalValidator = extend(
    Draft202012Validator,
    type_checker=Draft202012Validator.TYPE_CHECKER.redefine(
        "integer", lambda checker, value: type(value) is int
    ),
)


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


def _field_errors(error: ValidationError):
    """Report errors from the selected tagged branch instead of the entire object."""
    if error.validator == "oneOf" and isinstance(error.instance, dict):
        kind = error.instance.get("kind")
        for index, variant in enumerate(error.validator_value):
            if not isinstance(variant, dict):
                continue
            tag = variant.get("properties", {}).get("kind", {})
            if not isinstance(tag, dict) or kind is None:
                continue
            if kind == tag.get("const") or kind in tag.get("enum", []):
                details = [child for child in error.context if child.schema_path and child.schema_path[0] == index]
                if details:
                    for child in details:
                        yield from _field_errors(child)
                    return
    yield error


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
                if not isinstance(value, dict) or value.get("$id") != expected_id:
                    raise DataError(f"{path}: expected schema ID {expected_id}")
                registry = registry.with_resource(expected_id, Resource.from_contents(value))
            except (SchemaError, ValueError, TypeError, KeyError) as exc:
                raise DataError(f"{path}: invalid schema: {exc}") from exc
            self.schemas[name] = value
        self.registry = registry
        policies = self.schemas["common"].get("$defs", {}).get("policies", {}).get("properties")
        if policies is None:
            raise DataError(f"{directory / 'common.schema.json'}: missing policy definitions")
        self.policy_validators = {
            name: LocalValidator(schema, registry=registry) for name, schema in policies.items()
        }

    def validate(
        self, name: str, value: Any, *, origins: dict[str, list[Path]] | None = None
    ) -> None:
        validator = LocalValidator(
            self.schemas[name], registry=self.registry, format_checker=FormatChecker()
        )
        try:
            errors = [detail for error in validator.iter_errors(value) for detail in _field_errors(error)]
        except Unresolvable as exc:
            raise DataError(f"Unresolvable local schema reference: {exc}") from exc
        if errors:
            messages = []
            for error in sorted(errors, key=lambda e: str(list(e.absolute_path)))[:10]:
                path = list(error.absolute_path)
                location = ".".join(str(part) for part in path) or "<root>"
                if origins is not None and len(path) >= 2 and path[0] in origins and isinstance(path[1], int):
                    collection, index = path[:2]
                    record = value[collection][index]
                    record_id = record.get("id") if isinstance(record, dict) else None
                    location += f" ({origins[collection][index]}"
                    if record_id is not None:
                        location += f", record {record_id!r}"
                    location += ")"
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
    origins: dict[str, list[Path]] = {}
    for name, files in manifest["collections"].items():
        records = []
        origins[name] = []
        for filename in files:
            path = _collection_path(manifest_path.parent, filename)
            if path in loaded_paths:
                raise DataError(f"Collection file listed more than once: {path}")
            loaded_paths.add(path)
            values = read_json(path)
            if not isinstance(values, list):
                raise DataError(f"{path}: expected a JSON array of records")
            records.extend(values)
            origins[name].extend([path] * len(values))
        catalog[name] = records
    contracts.validate("catalog", catalog, origins=origins)
    CatalogValidator(catalog, contracts, origins).validate_catalog()

    if release:
        if catalog["status"] != "reviewed" or catalog["coverage_status"] != "complete":
            raise DataError("Release blocked: catalog must be reviewed with complete coverage")
        raise DataError("Release blocked: independent coverage audit is pending (issue #9)")
    return catalog
