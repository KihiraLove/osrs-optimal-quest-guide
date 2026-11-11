"""Convert local observations to canonical catalog records and compare snapshots."""

import json
from pathlib import Path
import re

from .data import Contracts, read_json
from .errors import DataError
from .semantics import CatalogValidator


def canonical_json(value) -> str:
    return json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n"


class ObservationError(DataError):
    def __init__(self, reviews: list[dict]):
        super().__init__(canonical_json({"review_queue": sorted(reviews, key=canonical_json)}).rstrip())


def _skill_observations(raw: dict) -> dict:
    try:
        thresholds = raw["base_level_thresholds_tenths"]
        rows = [
            {
                "id": skill["id"],
                "name": skill["name"],
                "xp_thresholds_tenths": thresholds,
                "evidence": {
                    "source_ids": raw["source_ids"],
                    "status": "verified",
                    "note": "Roster and effective level thresholds calculated from the pinned RuneLite API.",
                },
            }
            for skill in raw["skill_index"]
        ]
        return {"batch_version": 1, "game_revision": raw["game_revision"], "collections": {"skills": rows}}
    except (KeyError, TypeError) as exc:
        raise DataError(f"Malformed skill observations: {exc}") from exc


def _normalize_fields(value, aliases: dict[str, str]):
    if isinstance(value, list):
        return [_normalize_fields(item, aliases) for item in value]
    if not isinstance(value, dict):
        return value
    result = {}
    for key, child in value.items():
        if isinstance(child, str) and (key == "id" or key.endswith("_id") or key == "option"):
            result[key] = aliases.get(child, child)
        elif isinstance(child, list) and (key.endswith("_ids") or key in ("options", "eligible_skills")):
            result[key] = [aliases.get(entry, entry) if isinstance(entry, str) else entry for entry in child]
        else:
            result[key] = _normalize_fields(child, aliases)
    if "xp" in result:
        xp = result.pop("xp")
        if type(xp) not in (int, str) or not re.fullmatch(r"[0-9]+(?:\.[0-9]0*)?", str(xp)):
            raise DataError("xp must be an exact nonnegative whole or tenth XP amount")
        whole, _, fraction = str(xp).partition(".")
        try:
            amount = int(whole) * 10 + int((fraction or "0")[0])
        except ValueError as exc:
            raise DataError("xp amount exceeds the integer input limit") from exc
        if "xp_tenths" in result and (type(result["xp_tenths"]) is not int or result["xp_tenths"] != amount):
            raise DataError("xp and xp_tenths disagree")
        result["xp_tenths"] = amount
    return result


def _normalize_record(collection: str, row: dict, aliases: dict[str, str]) -> dict:
    record = _normalize_fields(row, aliases)
    if collection == "locations" and "tile" in record:
        tile = record.pop("tile")
        if not isinstance(tile, list) or len(tile) != 3 or any(type(part) is not int for part in tile):
            raise DataError("tile must contain three integers for x, y and plane")
        for key, number in zip(("x", "y", "plane"), tile):
            if key in record and (type(record[key]) is not int or record[key] != number):
                raise DataError(f"tile and {key} disagree")
            record[key] = number
    return record


def _validate_batch(batch, revision: str | None, origin: Path) -> None:
    if not isinstance(batch, dict) or type(batch.get("batch_version")) is not int or batch["batch_version"] != 1:
        raise DataError(f"{origin}: expected observation batch version 1")
    if set(batch) - {"batch_version", "game_revision", "aliases", "collections"}:
        raise DataError(f"{origin}: unexpected observation batch fields")
    if "game_revision" not in batch or batch["game_revision"] != revision:
        raise DataError(f"{origin}: observations belong to a different game revision")
    aliases = batch.get("aliases", {})
    if not isinstance(aliases, dict) or any(not isinstance(value, str) or not value.strip() for value in aliases.values()):
        raise DataError(f"{origin}: expected aliases from source identifiers to canonical IDs")
    if aliases.keys() & set(aliases.values()):
        raise DataError(f"{origin}: alias targets must be canonical IDs")
    if not isinstance(batch.get("collections"), dict):
        raise DataError(f"{origin}: expected an object of observation collections")


EVIDENCE_STATUSES = ("verified", "estimated", "synthetic", "unverified")


def _evidence(value, origin: str) -> dict:
    if not isinstance(value, dict) or set(value) != {"source_ids", "note", "status"}:
        raise DataError(f"{origin}: expected source_ids, note and status evidence")
    source_ids = value["source_ids"]
    if not isinstance(source_ids, list) or not source_ids or any(not isinstance(item, str) for item in source_ids):
        raise DataError(f"{origin}: expected at least one evidence source ID")
    if len(set(source_ids)) != len(source_ids):
        raise DataError(f"{origin}: duplicate evidence source ID")
    if not isinstance(value["note"], str) or not value["note"].strip():
        raise DataError(f"{origin}: expected an evidence note")
    if value["status"] not in EVIDENCE_STATUSES:
        raise DataError(f"{origin}: invalid evidence status")
    return value


def normalize_catalog(
    catalog: dict, contracts: Contracts, observations: list[Path], *, skills: Path | None = None,
) -> dict:
    """Apply explicit source adapters and surface disagreements for review."""
    tables = {
        name: {row["id"]: row for row in rows}
        for name, rows in catalog.items() if isinstance(rows, list)
    }
    batches = [(path, read_json(path)) for path in observations]
    if skills is not None:
        batches.append((skills, _skill_observations(read_json(skills))))
    reviews = []
    notes: dict[tuple[str, str], set[str]] = {}
    for path, batch in batches:
        _validate_batch(batch, catalog["game_revision"], path)
        for collection, rows in batch["collections"].items():
            if collection not in tables and collection != "combat_formulas":
                raise DataError(f"{path}: unknown observation collection {collection!r}")
            if not isinstance(rows, list):
                raise DataError(f"{path}: {collection} must be an array")
            table = tables.setdefault(collection, {})
            seen = set()
            for index, row in enumerate(rows):
                origin = f"{path.name} {collection}[{index}]"
                if not isinstance(row, dict):
                    raise DataError(f"{origin}: expected an observation object")
                unknown = row.get("unknown_fields", [])
                if not isinstance(unknown, list) or any(not isinstance(field, str) or not field.strip() for field in unknown):
                    raise DataError(f"{origin}: unknown_fields must be an array of field names")
                try:
                    record = _normalize_record(
                        collection, {key: value for key, value in row.items() if key != "unknown_fields"},
                        batch.get("aliases", {}),
                    )
                except DataError as exc:
                    reviews.append({"kind": "invalid", "origin": origin, "record_id": row.get("id"), "reason": str(exc)})
                    continue
                record_id = record.get("id")
                if not isinstance(record_id, str) or not record_id.strip():
                    raise DataError(f"{origin}: expected a record ID")
                if record_id in seen:
                    raise DataError(f"{origin}: duplicate observation ID {record_id!r}")
                seen.add(record_id)
                evidence = _evidence(record.get("evidence"), origin) if collection != "sources" else {}
                if unknown or evidence.get("status") == "unverified":
                    reviews.append({
                        "kind": "unknown", "origin": origin, "record_id": record_id,
                        "fields": sorted(set(unknown)), "evidence": evidence,
                    })
                    continue
                existing = table.get(record_id)
                if existing is None:
                    table[record_id] = record
                    continue
                ignored = {"evidence"} if collection != "sources" else set()
                changes = sorted(
                    key for key in (existing.keys() | record.keys()) - ignored
                    if key not in existing or key not in record or canonical_json(existing[key]) != canonical_json(record[key])
                )
                if changes:
                    reviews.append({
                        "kind": "conflict", "origin": origin, "record_id": record_id,
                        "fields": changes, "catalog": existing, "observation": record,
                    })
                    continue
                if collection != "sources":
                    old = existing["evidence"]
                    group = notes.setdefault((collection, record_id), {old["note"]})
                    group.add(evidence["note"])
                    table[record_id] = {**existing, "evidence": {
                        "source_ids": sorted(set(old["source_ids"]) | set(evidence["source_ids"])),
                        "status": max(old["status"], evidence["status"], key=EVIDENCE_STATUSES.index),
                        "note": " | ".join(sorted(group)),
                    }}
    if reviews:
        raise ObservationError(reviews)
    result = {name: value for name, value in catalog.items() if not isinstance(value, list)}
    result.update({name: [table[key] for key in sorted(table)] for name, table in tables.items()})
    contracts.validate("catalog", result)
    CatalogValidator(result, contracts).validate_catalog()
    return result


def catalog_diff(before: dict, after: dict) -> dict:
    changes = {}
    for collection in sorted(before.keys() | after.keys()):
        old, new = before.get(collection), after.get(collection)
        if not isinstance(old, list) and not isinstance(new, list):
            if old != new:
                changes[collection] = {"before": old, "after": new}
            continue
        old_rows = {row["id"]: row for row in old or []}
        new_rows = {row["id"]: row for row in new or []}
        added = sorted(new_rows.keys() - old_rows.keys())
        removed = sorted(old_rows.keys() - new_rows.keys())
        updated = {}
        for record_id in sorted(old_rows.keys() & new_rows.keys()):
            left, right = old_rows[record_id], new_rows[record_id]
            fields = {
                key: {"before": left.get(key), "after": right.get(key)}
                for key in sorted(left.keys() | right.keys())
                if key not in left or key not in right or left[key] != right[key]
            }
            if fields:
                updated[record_id] = fields
        if added or removed or updated:
            changes[collection] = {"added": added, "removed": removed, "changed": updated}
    return changes
