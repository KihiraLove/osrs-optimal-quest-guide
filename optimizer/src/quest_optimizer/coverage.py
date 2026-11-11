"""Reconcile the catalog with the independent local coverage ledger."""

from collections import Counter
from pathlib import Path

from .data import Contracts, local_path, read_json
from .errors import DataError
from .reachability import unreachable_records
from .semantics import CatalogValidator


INVENTORIES = ("journal", "diaries", "reward_reviews", "optional_activities")
STATUSES = {"expected", "collected", "reviewed", "excluded"}


def _object(value, context: str) -> dict:
    if not isinstance(value, dict):
        raise DataError(f"{context}: expected an object")
    return value


def _array(value, context: str) -> list:
    if not isinstance(value, list):
        raise DataError(f"{context}: expected an array")
    return value


def _text(value, context: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise DataError(f"{context}: expected nonempty text")
    return value


def _rows(value, context: str) -> dict[str, dict]:
    rows = {}
    for index, item in enumerate(_array(value, context)):
        row = _object(item, f"{context}[{index}]")
        record_id = _text(row.get("id"), f"{context}[{index}].id")
        if record_id in rows:
            raise DataError(f"{context}: duplicate ledger ID {record_id!r}")
        rows[record_id] = row
    return rows


def _check_evidence(value, sources: set[str], context: str) -> None:
    if isinstance(value, dict):
        references = value.get("source_ids", [])
        if "source_id" in value:
            references = [value["source_id"], *_array(references, context)]
        for source in _array(references, f"{context}.source_ids"):
            if _text(source, context) not in sources:
                raise DataError(f"{context}: unknown provenance source {source!r}")
        for key, child in value.items():
            if key not in ("source_id", "source_ids"):
                _check_evidence(child, sources, f"{context}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _check_evidence(child, sources, f"{context}[{index}]")


def _local_document(directory: Path, value, label: str) -> dict:
    path = local_path(directory, value, label=label)
    return _object(read_json(path), str(path))


class CoverageAudit:
    def __init__(self, catalog: dict):
        self.tables = {
            name: {row["id"]: row for row in rows}
            for name, rows in catalog.items() if isinstance(rows, list)
        }
        self.ids = {record_id for table in self.tables.values() for record_id in table}
        self.errors: list[str] = []
        self.pending: list[str] = []
        self.counts: dict[str, Counter] = {}
        self.covered_ids: set[str] = set()
        self.goals: set[str] = set()
        self.unreachable: dict[str, list[str]] | None = None

    def status(self, category: str, row: dict) -> str:
        record_id = row["id"]
        context = f"{category} {record_id}"
        status = row.get("status")
        if not isinstance(status, str) or status not in STATUSES:
            raise DataError(f"{context}: unknown coverage status {status!r}")
        self.counts.setdefault(category, Counter())[status] += 1
        if status == "excluded":
            _text(row.get("reason"), f"{context}.reason")
        elif status != "reviewed":
            self.pending.append(f"{context}: {status}")
        return status

    def row(self, category: str, row: dict, targets: dict | None = None) -> bool:
        record_id = row["id"]
        context = f"{category} {record_id}"
        status = self.status(category, row)
        if status == "excluded":
            if record_id in (self.ids if targets is None else targets):
                self.errors.append(f"{context}: excluded record is present in the catalog")
            return False
        if status == "expected":
            return False

        links = _array(row.get("catalog_ids", [record_id]), f"{context}.catalog_ids") if targets is None else [record_id]
        if not links:
            raise DataError(f"{context}.catalog_ids: expected at least one record ID")
        for link in links:
            _text(link, f"{context}.catalog_ids")
            if link not in (self.ids if targets is None else targets):
                self.errors.append(f"{context}: catalog record {link!r} is missing or has the wrong type")
            else:
                self.covered_ids.add(link)
        return record_id in (targets or {})

    def check_inventories(self, ledger: dict, entries: dict) -> None:
        skills = _rows(ledger.get("skills"), "skills")
        for row in skills.values():
            self.row("skills", row, self.tables["skills"])

        journal = _rows(entries["journal"], "journal")
        rewards = _rows(entries["reward_reviews"], "reward_reviews")
        client_ids = set()
        for record_id, row in journal.items():
            kind = row.get("kind")
            if kind not in ("quest", "subquest", "miniquest"):
                raise DataError(f"journal {record_id}: invalid journal kind {kind!r}")
            client_id = row.get("client_quest_id")
            if type(client_id) is not int or client_id < 0 or client_id in client_ids:
                raise DataError(f"journal {record_id}: invalid or duplicate client quest ID {client_id!r}")
            client_ids.add(client_id)
            goal = None
            if kind == "quest" and row.get("status") != "excluded":
                goal = _text(row.get("goal_action_id"), f"journal {record_id}.goal_action_id")
                if goal in self.goals:
                    raise DataError(f"journal {record_id}: duplicate goal action {goal!r}")
                self.goals.add(goal)
            if kind == "subquest":
                parent = _text(row.get("parent_id"), f"journal {record_id}.parent_id")
                if journal.get(parent, {}).get("kind") != "quest":
                    self.errors.append(f"journal {record_id}: expected a quest parent in the ledger")
            if self.row("journal", row, self.tables["activities"]):
                activity = self.tables["activities"][record_id]
                if activity["kind"] != kind or activity["parent_activity_id"] != row.get("parent_id"):
                    self.errors.append(f"journal {record_id}: activity kind or parent differs from the ledger")
                if goal is not None and goal not in activity["completion_action_ids"]:
                    self.errors.append(f"journal {record_id}: goal {goal!r} is missing from the completion actions")
            if row["status"] == "reviewed":
                review_id = row.get("completion_reward_review_id")
                review = rewards.get(review_id, {}) if isinstance(review_id, str) else {}
                if review.get("status") != "reviewed":
                    self.errors.append(f"journal {record_id}: missing reviewed completion reward entry")
                elif record_id in self.tables["activities"]:
                    linked = _array(review.get("catalog_ids", [review_id]), f"{review_id}.catalog_ids")
                    completion = self.tables["activities"][record_id]["completion_action_ids"]
                    if not any(action_id in linked for action_id in completion):
                        self.errors.append(f"journal {record_id}: reward review does not reference a completion action")

        diaries = _object(entries["diaries"], "diaries")
        diary_tiers = set()
        diary_tasks = set()
        diary_claims = set()
        for region in _rows(diaries.get("regions"), "diary regions").values():
            # The region is an inventory group and has no catalog record.
            self.status("diary_regions", region)
            for tier_id, tier in _rows(region.get("tiers"), region["id"]).items():
                if tier_id in diary_tiers:
                    raise DataError(f"diaries: duplicate diary tier {tier_id!r}")
                diary_tiers.add(tier_id)
                if self.row("diary_tiers", tier, self.tables["activities"]):
                    if self.tables["activities"][tier_id]["kind"] != "diary_tier":
                        self.errors.append(f"diary tier {tier_id}: expected a diary_tier activity")
                claim = _text(tier.get("reward_claim_id"), f"{tier_id}.reward_claim_id")
                if claim in diary_claims:
                    raise DataError(f"diaries: duplicate reward claim {claim!r}")
                diary_claims.add(claim)
                if tier["status"] == "reviewed":
                    reward = self.tables["actions"].get(claim, {})
                    if reward.get("kind") != "reward_claim" or reward.get("activity_id") != tier_id:
                        self.errors.append(f"diary tier {tier_id}: missing reward claim {claim!r}")
                    else:
                        self.covered_ids.add(claim)
                for task_id, task in _rows(tier.get("tasks"), tier_id).items():
                    if task_id in diary_tasks:
                        raise DataError(f"diaries: duplicate diary task {task_id!r}")
                    diary_tasks.add(task_id)
                    if self.row("diary_tasks", task, self.tables["actions"]):
                        action = self.tables["actions"][task_id]
                        if action["kind"] != "diary_task" or action["activity_id"] not in (None, tier_id):
                            self.errors.append(f"diary task {task_id}: action kind or tier differs from the ledger")

        for row in rewards.values():
            self.row("reward_reviews", row)
            if row["status"] not in ("collected", "reviewed"):
                continue
            for action_id, effects in _object(row.get("expected_effects", {}), row["id"]).items():
                actual = self.tables["actions"].get(action_id, {}).get("effects")
                if actual != _array(effects, f"{row['id']}.expected_effects.{action_id}"):
                    self.errors.append(f"reward review {row['id']}: effects differ for {action_id!r}")
        for row in _rows(entries["optional_activities"], "optional_activities").values():
            self.row("optional_activities", row)

        for record_id in self.tables["skills"].keys() - skills.keys():
            self.errors.append(f"skills {record_id}: absent from the independent inventory")
        for record_id, activity in self.tables["activities"].items():
            kind = activity["kind"]
            if kind in ("quest", "subquest", "miniquest"):
                expected_ids = journal
            elif kind == "diary_tier":
                expected_ids = diary_tiers
            else:
                expected_ids = self.covered_ids
            if record_id not in expected_ids:
                self.errors.append(f"activities {record_id}: absent from the independent inventory")
        for record_id, action in self.tables["actions"].items():
            if action["kind"] == "reward_claim" and record_id not in self.covered_ids:
                self.pending.append(f"reward claim {record_id}: missing reviewed inventory link")
            if action["kind"] == "diary_task" and record_id not in diary_tasks:
                self.errors.append(f"diary task {record_id}: absent from the independent inventory")

    def report(self, catalog: dict) -> dict:
        errors = sorted(set(self.errors))
        pending = sorted(set(self.pending))
        return {
            "dataset_id": catalog["dataset_id"],
            "dataset_version": catalog["dataset_version"],
            "release_ready": not errors and not pending,
            "coverage_counts": {category: dict(counts) for category, counts in self.counts.items()},
            "errors": errors,
            "pending": pending,
            "unreachable": self.unreachable,
        }


def audit_coverage(
    manifest_path: Path, catalog: dict, contracts: Contracts, *, manifest: dict | None = None,
) -> dict:
    manifest_path = manifest_path.resolve()
    root = manifest_path.parent
    if manifest is None:
        manifest = read_json(manifest_path)
    audit = CoverageAudit(catalog)
    if catalog["status"] != "reviewed" or catalog["coverage_status"] != "complete":
        audit.pending.append("catalog: release requires reviewed status and complete coverage")
    if not manifest.get("coverage_ledger"):
        audit.pending.append("manifest: missing independent coverage ledger")
        return audit.report(catalog)
    ledger_path = local_path(root, manifest["coverage_ledger"], label="Coverage ledger")
    ledger = _object(read_json(ledger_path), str(ledger_path))
    if type(ledger.get("ledger_version")) is not int or ledger["ledger_version"] != 1:
        raise DataError(f"{ledger_path}: unsupported coverage ledger version")
    for field in ("dataset_id", "dataset_version", "game_revision", "as_of"):
        if _text(ledger.get(field), f"{ledger_path}.{field}") != catalog[field]:
            audit.errors.append(f"coverage ledger: {field} differs from the catalog")
    sources = set(audit.tables["sources"])
    _check_evidence(ledger, sources, "coverage ledger")
    index = _object(ledger.get("entries"), "coverage ledger entries")
    entries = {
        category: read_json(local_path(ledger_path.parent, index.get(category), label=f"Coverage {category}"))
        for category in INVENTORIES
    }
    for category, entry in entries.items():
        _check_evidence(entry, sources, category)
    audit.check_inventories(ledger, entries)

    for review in _rows(ledger.get("open_reviews"), "open_reviews").values():
        audit.pending.append(f"{review['id']}: {_text(review.get('reason'), review['id'])}")
    if ledger.get("reconciliation"):
        reconciliation = _local_document(root, ledger["reconciliation"], "Reconciliation")
        if reconciliation.get("revision") != catalog["game_revision"]:
            audit.errors.append("reconciliation: game revision differs from the catalog")
        _check_evidence(reconciliation, sources, "reconciliation")
        for review in _rows(reconciliation.get("observations"), "reconciliation").values():
            reason = _text(review.get("reason"), review["id"])
            status = review.get("status")
            if status == "resolved":
                if "accepted" not in review:
                    audit.errors.append(f"{review['id']}: resolved conflict needs an accepted value")
            elif status in ("expected", "pending", "conflict", "unknown"):
                audit.pending.append(f"{review['id']}: {reason}")
            elif status != "excluded":
                raise DataError(f"{review['id']}: unknown reconciliation status {status!r}")
    else:
        audit.pending.append("coverage ledger: missing reconciliation file")

    attribution = ledger.get("attribution")
    notices = _array(ledger.get("license_notices", []), "license_notices")
    if not attribution:
        audit.pending.append("coverage ledger: missing attribution document")
    if any(source["kind"] == "licensed_dataset" for source in catalog["sources"]) and not notices:
        audit.pending.append("coverage ledger: missing local license notices")
    references = [(notice, ".txt") for notice in notices]
    if attribution:
        references.append((attribution, ".md"))
    for reference, suffix in references:
        path = local_path(root, reference, label="Attribution", suffix=suffix)
        try:
            _text(path.read_text(encoding="utf-8"), str(path))
        except (OSError, UnicodeError) as exc:
            raise DataError(f"{path}: {exc}") from exc
    for source in catalog["sources"]:
        if source["kind"] == "synthetic":
            audit.pending.append(f"source {source['id']}: synthetic provenance")
        for field in ("locator", "attribution", "license"):
            _text(source[field], f"source {source['id']}.{field}")
    for collection, table in audit.tables.items():
        if collection == "sources":
            continue
        for record_id, row in table.items():
            allowed = {"verified", "estimated"} if collection in ("actions", "travel_edges") else {"verified"}
            if row["evidence"]["status"] not in allowed:
                audit.pending.append(f"{collection} {record_id}: evidence requires review")

    if manifest.get("release_profile"):
        profile = _local_document(root, manifest["release_profile"], "Release profile")
        contracts.validate("profile", profile)
        CatalogValidator(catalog, contracts).validate_profile(profile)
        if profile["status"] != "reviewed" or not profile["members"]:
            audit.pending.append("release profile: expected a reviewed members account")
        if set(profile["goal_action_ids"]) != audit.goals:
            audit.errors.append("release profile: goals differ from the independent quest list")
        audit.unreachable = unreachable_records(catalog, profile)
        blocked_goals = set(audit.unreachable["actions"]) & audit.goals
        unreachable_locations = set(audit.unreachable["locations"])
        for goal in blocked_goals:
            audit.pending.append(f"quest goal {goal}: unreachable from the release profile")
            start = audit.tables["actions"][goal]["start_location_id"]
            if start in unreachable_locations:
                audit.pending.append(f"locations {start}: unreachable from the release profile")
    else:
        audit.pending.append("manifest: missing reviewed release profile")
    return audit.report(catalog)
