"""Collect literal facts from the pinned, locally checked-out Quest Helper source."""

import argparse
import json
from pathlib import Path
import re
import subprocess


ROOT = Path(__file__).resolve().parents[1]
JAVA = Path("src/main/java/com/questhelper")
OBSERVATION_SOURCE = "source.quest_helper.quest_observations"
RFD_CLASSES = {
    "RFDStart": "another_cooks_quest",
    "RFDDwarf": "freeing_the_mountain_dwarf",
    "RFDGoblins": "freeing_the_goblin_generals",
    "RFDPiratePete": "freeing_pirate_pete",
    "RFDLumbridgeGuide": "freeing_the_lumbridge_guide",
    "RFDEvilDave": "freeing_evil_dave",
    "RFDSkrachUglogwee": "freeing_skrach_uglogwee",
    "RFDSirAmikVarze": "freeing_sir_amik_varze",
    "RFDAwowogei": "freeing_king_awowogei",
    "RFDFinal": "defeating_the_culinaromancer",
}
HELPER_INDEX = re.compile(
    r"^\s*([A-Z][A-Z0-9_]+)\(new (\w+)\([^\n]*?\),\s*(?:Quest\.([A-Z0-9_]+))?",
    re.MULTILINE,
)
JAVA_QUOTES = r'''"(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*' '''
COMMENTS = re.compile(JAVA_QUOTES.strip() + r"|//[^\n]*|/\*[\s\S]*?\*/")
QUOTES = re.compile(JAVA_QUOTES.strip())
REQUIREMENT = re.compile(r"\bnew\s+(\w+Requirement|Conditions)\s*\(")
LITERAL_REFS = re.compile(
    r"\b(?:ItemID|ItemCollections|QuestHelperQuest|Quest|QuestState|QuestVarbits|"
    r"QuestVarPlayer|VarbitID|VarPlayerID|Operation|Skill|LogicType)\.\w+"
)


def without_comments(source: str) -> str:
    return COMMENTS.sub(
        lambda match: re.sub(r"[^\n]", " ", match[0]) if match[0].startswith("/") else match[0],
        source,
    )


def mask_quotes(source: str) -> str:
    return QUOTES.sub(lambda match: re.sub(r"[^\n]", " ", match[0]), source)


def closing_index(masked: str, start: int, opening: str, closing: str) -> int:
    depth = 1
    for index in range(start + 1, len(masked)):
        char = masked[index]
        if char == opening:
            depth += 1
        if char == closing:
            depth -= 1
            if depth == 0:
                return index
    raise ValueError("Unbalanced Java delimiter")


def arguments(source: str) -> list[str]:
    stack = []
    start = 0
    result = []
    for index, char in enumerate(mask_quotes(source)):
        if char in "([{":
            stack.append(char)
        elif char in ")]}" and stack:
            stack.pop()
        elif char == "," and not stack:
            result.append(source[start:index].strip())
            start = index + 1
    if source[start:].strip():
        result.append(source[start:].strip())
    return result


def method(source: str, masked: str, name: str) -> tuple[int, str] | None:
    match = re.search(rf"\b{name}\s*\(\s*\)\s*\{{", masked)
    if match is None:
        return None
    return match.end(), source[match.end():closing_index(masked, match.end() - 1, "{", "}")]


def calls(source: str, pattern: re.Pattern):
    masked = mask_quotes(source)
    end = 0
    for match in pattern.finditer(masked):
        if match.start() < end:
            continue
        end = closing_index(masked, match.end() - 1, "(", ")")
        yield match, arguments(source[match.end():end])


def literal_int(value: str) -> int | None:
    return int(value.replace("_", "")) if re.fullmatch(r"-?\d[\d_]*", value) else None


def rule(kind: str, args: list[str], quest_ids: dict[str, str]) -> dict:
    if kind == "SkillRequirement" and len(args) >= 2 and args[0].startswith("Skill."):
        level = literal_int(args[1])
        if level is not None and (len(args) == 2 or args[2] in ("true", "false", "Operation.GREATER_EQUAL")):
            boostable = len(args) > 2 and args[2] == "true"
            return {"kind": "skill", "skill_id": "skill." + args[0][6:].lower(),
                    "minimum_level": level, "boostable": boostable}
    if kind == "QuestRequirement" and len(args) >= 2:
        symbol = args[0].removeprefix("QuestHelperQuest.").removeprefix("Quest.")
        if args[1].startswith("QuestState."):
            return {"kind": "quest", "helper_symbol": symbol, "activity_id": quest_ids.get(symbol),
                    "observed_state": args[1].split(".", 1)[1].lower()}
    if kind == "QuestPointRequirement" and args and (points := literal_int(args[0])) is not None:
        return {"kind": "quest_points", "minimum": points}
    if kind in ("ComplexRequirement", "Conditions") and args and args[0] in ("LogicType.AND", "LogicType.OR"):
        children = []
        for arg in args[1:]:
            if arg.startswith('"'):
                continue
            nested = next(calls(arg, REQUIREMENT), None)
            children.append(rule(nested[0][1], nested[1], quest_ids) if nested else
                            {"kind": "helper_condition", "symbols": re.findall(r"\b\w+\b", mask_quotes(arg))})
        return {"kind": args[0].split(".")[1].lower(), "requirements": children}
    return {"kind": "helper_condition", "constructor": kind,
            "symbols": sorted(set(LITERAL_REFS.findall(" ".join(args)))),
            "integer_arguments": [number for arg in args if (number := literal_int(arg)) is not None]}


def general_requirements(source: str, block: tuple[int, str] | None, quest_ids: dict[str, str]) -> dict:
    if block is None:
        return {"declared": False}
    offset, body = block
    masked = mask_quotes(body)
    guards = []
    for match in re.finditer(r"\bif\s*\(", masked):
        end = closing_index(masked, match.end() - 1, "(", ")")
        predicate = masked[match.end():end]
        start = end + 1
        while start < len(masked) and masked[start].isspace():
            start += 1
        stop = (closing_index(masked, start, "{", "}") if masked[start:start + 1] == "{"
                else masked.find(";", start))
        guards.append((start, stop, "ironman" if "isAnyIronman" in predicate else "source_conditional"))
    requirements = []
    for match, args in calls(body, REQUIREMENT):
        requirements.append({
            "line": source.count("\n", 0, offset + match.start()) + 1,
            "guards": [label for start, stop, label in guards if start <= match.start() <= stop],
            "observation": rule(match[1], args, quest_ids),
        })
    return {"declared": True, "observations": requirements}


def rewards(block: tuple[int, str] | None, constructor: str) -> dict:
    if block is None:
        return {"declared": False}
    _, body = block
    awards = []
    pattern = re.compile(rf"\bnew\s+({constructor})\s*\(")
    for _, args in calls(body, pattern):
        if constructor == "QuestPointReward":
            awards.append({"quest_points": literal_int(args[0])})
        elif constructor == "ExperienceReward":
            amount = literal_int(args[1]) if len(args) >= 2 else None
            awards.append({"skill_id": "skill." + args[0][6:].lower() if re.fullmatch(r"Skill\.\w+", args[0]) else None,
                           "xp_tenths": amount * 10 if amount is not None else None})
        else:
            awards.append({"item_symbols": LITERAL_REFS.findall(" ".join(args)),
                           "quantity": literal_int(args[-1]) if len(args) >= 3 else None,
                           "mentions_xp": bool(re.search(r"\b(?:experience|lamp|xp)\b", " ".join(args), re.I))})
    return {"declared": True, "observations": awards}


def item_definitions(source: str, required: tuple[int, str] | None, recommended: tuple[int, str] | None) -> dict:
    definitions = {}
    for match, args in calls(source, re.compile(r"\b(\w+)\s*=\s*new\s+ItemRequirement\s*\(")):
        symbol = match[1]
        definitions[symbol] = {
            "symbol": symbol,
            "item_symbols": sorted(set(LITERAL_REFS.findall(" ".join(args)))),
            "quantity": (literal_int(args[2]) if len(args) >= 3 else 1) if len(args) >= 2 else None,
            "acquired_during_quest": bool(re.search(rf"\b{symbol}\.canBeObtainedDuringQuest\(", source)),
        }
    result = {}
    for name, block in (("required", required), ("recommended", recommended)):
        used = dict.fromkeys(re.findall(r"\b\w+\b", mask_quotes(block[1]))) if block else {}
        result[name] = {"declared": block is not None, "observations": [
            definitions[symbol] for symbol in used if symbol in definitions
        ]}
    return result


def observe(path: Path, checkout: Path, symbol: str, quest_id: str, quest_ids: dict[str, str]) -> dict:
    original = path.read_text(encoding="utf-8")
    source = without_comments(original)
    masked = mask_quotes(source)
    blocks = {name: method(source, masked, name) for name in (
        "getGeneralRequirements", "getItemRequirements", "getItemRecommended",
        "getQuestPointReward", "getExperienceRewards", "getItemRewards", "getCombatRequirements",
    )}
    points = []
    for match in re.finditer(
        r"\b(\w+)\s*=\s*new\s+\w+Step\s*\([^;]*?new WorldPoint\(\s*(\d+),\s*(\d+),\s*([0-3])\s*\)",
        masked,
    ):
        points.append({"step": match[1], "tile": [int(match[i]) for i in range(2, 5)]})
    return {
        "activity_id": quest_id,
        "helper_symbol": symbol,
        "file": path.relative_to(checkout).as_posix(),
        "copyright": [line.strip().removeprefix("* ") for line in original.splitlines()[:28] if "Copyright (c)" in line],
        "general_requirements": general_requirements(source, blocks["getGeneralRequirements"], quest_ids),
        "items": item_definitions(source, blocks["getItemRequirements"], blocks["getItemRecommended"]),
        "combat_review": "required" if blocks["getCombatRequirements"] is not None else "unspecified",
        "mandatory_incidental_xp_tenths": None,
        "declared_quest_points": rewards(blocks["getQuestPointReward"], "QuestPointReward"),
        "declared_xp": rewards(blocks["getExperienceRewards"], "ExperienceReward"),
        "declared_items": rewards(blocks["getItemRewards"], "ItemReward"),
        "waypoint_candidates": points,
        "phase_selectors": [
            {"progress": int(progress), "step": step}
            for progress, step in re.findall(r"\bsteps\.put\(\s*(\d+),\s*(\w+)\s*\);", masked)
        ],
    }


def write_json(path: Path, value) -> None:
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("checkout", type=Path)
    parser.add_argument("--output", type=Path, default=ROOT / "data/raw/build-242/quest-helper")
    args = parser.parse_args()
    checkout = args.checkout.resolve()
    data = ROOT / "data"
    source = next(row for row in json.loads((data / "sources.json").read_text(encoding="utf-8"))
                  if row["id"] == OBSERVATION_SOURCE)
    commit = subprocess.check_output(
        ["git", "-c", f"safe.directory={checkout.as_posix()}", "-C", str(checkout), "rev-parse", "HEAD"],
        text=True,
    ).strip()
    if commit != source["revision"]:
        parser.error(f"checkout must point at pinned commit {source['revision']}")
    if subprocess.check_output(
        ["git", "--no-optional-locks", "-c", f"safe.directory={checkout.as_posix()}", "-C", str(checkout),
         "status", "--porcelain", "--untracked-files=all", "--", JAVA.as_posix()],
        text=True,
    ).strip():
        parser.error("quest helper Java sources must match the pinned checkout")
    journal = json.loads((data / "coverage/build-242/journal.json").read_text(encoding="utf-8"))
    by_symbol = {row["client_symbol"]: row["id"] for row in journal}
    index_source = (checkout / JAVA / "questinfo/QuestHelperQuest.java").read_text(encoding="utf-8")
    paths = {path.stem: path for path in sorted((checkout / JAVA / "helpers").rglob("*.java"))}
    helpers = []
    quest_ids = dict(by_symbol)
    for symbol, helper_class, client_symbol in HELPER_INDEX.findall(index_source):
        quest_id = by_symbol.get(client_symbol or symbol)
        if helper_class in RFD_CLASSES:
            quest_id = "rfd." + RFD_CLASSES[helper_class]
        if quest_id is not None and helper_class in paths:
            quest_ids[symbol] = quest_id
            helpers.append((quest_id, symbol, paths[helper_class]))
    observations = [
        observe(path, checkout, symbol, quest_id, quest_ids)
        for quest_id, symbol, path in sorted(helpers)
    ]
    observed = {entry["activity_id"] for entry in observations}
    args.output.mkdir(parents=True, exist_ok=True)
    files = []
    for start in range(0, len(observations), 35):
        filename = f"observations-{start // 35 + 1:02}.json"
        rows = observations[start:start + 35]
        # Keep each source observation on its own line for focused diffs.
        content = ",\n".join("  " + json.dumps(row, ensure_ascii=False) for row in rows)
        (args.output / filename).write_text("[\n" + content + "\n]\n", encoding="utf-8", newline="\n")
        files.append(filename)
    write_json(args.output / "index.json", {
        "game_revision": "osrs-live-242",
        "source_ids": [OBSERVATION_SOURCE],
        "source_revision": commit,
        "files": files,
        "observed_activity_count": len(observed),
        "missing_helper_activity_ids": sorted({row["id"] for row in journal} - observed - {"quest.recipe_for_disaster"}),
        "review_note": "Source declarations are candidates. Check logic, stage timing, items and release overrides before admission to the catalog.",
    })


if __name__ == "__main__":
    main()
