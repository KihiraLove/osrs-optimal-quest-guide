"""Collect diary task evidence from the pinned local Quest Helper checkout."""

import argparse
import json
from pathlib import Path
import re

from collect_quest_observations import (
    LITERAL_REFS, REQUIREMENT, ROOT, calls, check_checkout, general_requirements, literal_int,
    mask_quotes, method, rewards, rule, without_comments, write_json,
)


SOURCE_ID = "source.quest_helper.diaries"
ASSIGNMENT = re.compile(r"\b(\w+)\s*=\s*new\s+(\w+)\s*\(")
CALL = re.compile(
    r"\b(\w+)\)?\.(addStep|addSubSteps|setDisplayCondition|setLockingStep|"
    r"setInvalidateRequirement|addAlternates|isNotConsumed|showConditioned)\s*\("
)
PANEL = re.compile(r"\b(?:new\s+PanelDetails|PanelDetails\.lockedPanel)\s*\(")
POINT = re.compile(r"\bnew WorldPoint\(\s*(\d+),\s*(\d+),\s*([0-3])\s*\)")
LAMP = re.compile(r'"\s*([\d,]+)\s+Exp\.\s+Lamp\s+\(Any skill(?:\s+(?:over|above level)\s+(\d+))?\)"')


def symbols(expression: str) -> list[str]:
    return list(dict.fromkeys(re.findall(r"\b\w+\b", mask_quotes(expression))))


def line_number(source: str, offset: int) -> int:
    return source.count("\n", 0, offset) + 1


def inline_requirements(expression: str, quest_ids: dict[str, str]) -> list[dict]:
    return [rule(match[1], args, quest_ids) for match, args in calls(expression, REQUIREMENT)]


def collect_tier(tier: dict, checkout: Path, quest_ids: dict[str, str], previous_claim_id: str | None) -> dict:
    source = without_comments((checkout / tier["helper_path"]).read_text(encoding="utf-8"))
    masked = mask_quotes(source)
    definitions = {}
    links = {}
    for match, args in calls(source, ASSIGNMENT):
        symbol, constructor = match.groups()
        expression = ", ".join(args)
        refs = LITERAL_REFS.findall(expression)
        row = {"line": line_number(source, match.start()), "constructor": constructor}
        if constructor.endswith("Step"):
            row["tiles"] = [list(map(int, tile)) for tile in POINT.findall(mask_quotes(expression))]
            row["target_symbols"] = re.findall(r"\b(?:NpcID|ObjectID)\.\w+", mask_quotes(expression))
            checks = inline_requirements(expression, quest_ids)
            if checks:
                row["inline_requirements"] = checks
        elif constructor == "ItemRequirement":
            row["item_symbols"] = refs
            row["quantity"] = literal_int(args[2]) if len(args) > 2 else 1
            end = masked.find(";", match.end())
            if ".isNotConsumed(" in masked[match.end():end]:
                row["helper_marks_not_consumed"] = True
        elif constructor.endswith("Requirement") or constructor == "Conditions":
            row["observation"] = rule(constructor, args, quest_ids)
        else:
            continue
        definitions.setdefault(symbol, []).append(row)
        links.setdefault(symbol, set()).update(symbols(expression))

    task_bindings = {task["condition"]: set() for task in tier["tasks"]}
    task_checks = {task["condition"]: [] for task in tier["tasks"]}
    panel_links = {}
    for match, args in calls(source, CALL):
        owner, operation = match.groups()
        refs = symbols(", ".join(args))
        if operation == "addStep":
            guards = set(symbols(args[0]))
            for condition in task_bindings.keys() & guards:
                task_bindings[condition].update(symbols(args[-1]))
        elif operation in ("setDisplayCondition", "setLockingStep"):
            panel_links.setdefault(owner, set()).update(refs)
        if owner in definitions:
            links[owner].update(refs)
            definitions[owner][0].setdefault("helper_calls", []).append({
                "line": line_number(source, match.start()), "operation": operation,
                "argument_symbols": [symbols(arg) for arg in args],
            })

    for match, args in calls(source, PANEL):
        refs = set(symbols(", ".join(args)))
        owner = re.search(r"(\w+)\s*=\s*$", masked[max(0, match.start() - 150):match.start()])
        if owner:
            refs.update(panel_links.get(owner[1], ()))
        for condition in task_bindings.keys() & refs:
            task_bindings[condition].update(refs - {condition})
            task_checks[condition].extend(inline_requirements(", ".join(args), quest_ids))

    def related_steps_and_requirements(roots: set[str]) -> list[str]:
        candidates = definitions.keys() - task_bindings.keys()
        pending = list(roots & candidates)
        seen = set()
        while pending:
            symbol = pending.pop()
            if symbol in seen:
                continue
            seen.add(symbol)
            pending.extend((links[symbol] & candidates) - seen)
        return sorted(seen)

    tasks = []
    for task in tier["tasks"]:
        bindings = related_steps_and_requirements(task_bindings[task["condition"]])
        tasks.append({
            "id": task["id"],
            "helper_symbols": bindings,
            "panel_requirement_candidates": task_checks[task["condition"]],
            "registration_review": "pending",
        })

    general = method(source, masked, "getGeneralRequirements")
    item_rewards = method(source, masked, "getItemRewards")
    unlock_rewards = method(source, masked, "getUnlockRewards")
    claims = {
        symbol: rows for symbol, rows in definitions.items()
        if any(row.get("constructor") == "NpcStep" for row in rows)
        and re.search(r"claim|reward|finish", symbol, re.I)
    }
    # Store factual numeric fields and source locators, not reward descriptions.
    lamps = [
        {"xp_tenths": int(amount.replace(",", "")) * 10,
         "helper_level_number": int(level) if level else None}
        for amount, level in LAMP.findall(item_rewards[1] if item_rewards else "")
    ]
    travel_hints = []
    if unlock_rewards:
        offset, body = unlock_rewards
        for match, args in calls(body, re.compile(r"\bnew\s+UnlockReward\s*\(")):
            categories = re.findall(r"\b(?:teleport\w*|shortcut\w*|run energy|run restores?)\b", " ".join(args), re.I)
            if categories:
                travel_hints.append({"line": line_number(source, offset + match.start()),
                                     "mentions": sorted({category.lower() for category in categories})})
    used_symbols = set(claims) | {symbol for task in tasks for symbol in task["helper_symbols"]}
    return {
        "id": tier["id"],
        "helper_path": tier["helper_path"],
        "attribution": tier["attribution"],
        "general_requirements": general_requirements(source, general, quest_ids),
        "tasks": tasks,
        "helper_definitions": {symbol: definitions[symbol] for symbol in sorted(used_symbols)},
        "claim": {
            "id": tier["reward_claim_id"],
            "requires_tier_id": tier["id"],
            "previous_tier_claim_id": previous_claim_id,
            "helper_npc_candidates": sorted(claims),
            "item_rewards": rewards(item_rewards, "ItemReward"),
            "lamps": lamps,
            "travel_hints": travel_hints,
            "claim_review": "pending",
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("checkout", type=Path)
    parser.add_argument("--output", type=Path, default=ROOT / "data/raw/build-242/diaries")
    args = parser.parse_args()
    data = ROOT / "data"
    sources = json.loads((data / "sources.json").read_text(encoding="utf-8"))
    source = next(row for row in sources if row["id"] == SOURCE_ID)
    checkout = args.checkout.resolve()
    try:
        check_checkout(checkout, source["revision"])
    except ValueError as exc:
        parser.error(str(exc))
    journal = json.loads((data / "coverage/build-242/journal.json").read_text(encoding="utf-8"))
    quest_ids = {row["client_symbol"]: row["id"] for row in journal}
    ledger = json.loads((data / "coverage/build-242/diaries.json").read_text(encoding="utf-8"))
    args.output.mkdir(parents=True, exist_ok=True)
    files = []
    for region in ledger["regions"]:
        tiers = []
        previous_claim_id = None
        for tier in region["tiers"]:
            tiers.append(collect_tier(tier, checkout, quest_ids, previous_claim_id))
            previous_claim_id = tier["reward_claim_id"]
        filename = region["id"].removeprefix("diary.") + ".json"
        files.append(filename)
        # Keep each tier on its own line so this evidence can be regenerated without diff churn.
        content = ",\n".join("  " + json.dumps(row, ensure_ascii=False) for row in tiers)
        (args.output / filename).write_text("[\n" + content + "\n]\n", encoding="utf-8", newline="\n")
    write_json(args.output / "index.json", {
        "game_revision": "osrs-live-242",
        "source_ids": [SOURCE_ID],
        "source_revision": source["revision"],
        "files": files,
        "review_note": "Helper paths, requirements, claim candidates and lamp numbers are observations. Verify registration, claim order and game mechanics before normalization.",
    })


if __name__ == "__main__":
    main()
