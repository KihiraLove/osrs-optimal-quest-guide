# Data acquisition, cleaning and maintenance

## Local-first rule

Neither application downloads game data. Do not add a Wiki client, scraper or
runtime fetch fallback. Acquisition is a separate human-reviewed development
workflow. Prefer in-game observation, official Jagex release notes and suitably
licensed existing local/exported datasets. Any proposed external bulk import
must first document permission, license, provenance and how the snapshot is
stored; do not assume that a public repository or website is freely reusable.
No Wiki import is part of this plan. Source URLs are inert citations.

Keep raw factual observations/allowed excerpts as JSON under `data/raw/`. Record
source ID, observation/retrieval date, game revision or build, evidence locator,
attribution and reuse terms. Do not commit copied guide prose, artwork, account
credentials or large unlicensed page dumps. A source record can cite an in-game
observation without redistributing the original screen capture.

## Collection sequence

1. Pin the game revision and cutoff date; inventory the current skills, quests,
   subquests, miniquests and diary tiers without assuming a fixed historical count.
   Build a coverage ledger in JSON with expected IDs and collected/reviewed/excluded
   status, plus reasons for every exclusion. This ledger is a separate source of
   completeness expectations, not just the list of files already collected.
2. Record skill XP thresholds and the Lumbridge arrival profile with one
   starting quest point. Verify fractional XP handling and distinguish base
   levels from boostable checks.
3. Capture quest prerequisites, phase-specific checks, start/end coordinates,
   items, mandatory XP, reward choices, quest points and partial unlocks. Split
   Recipe for Disaster from the first pass. Record relevant combat/assistance
   constraints and uncertain incidental XP explicitly.
4. Inventory reward claims separately: all post-quest NPC visits, lamps, books,
   optional training and item exchanges. Reconcile totals with completion rewards
   to detect double counting and rewards that were moved by game updates.
5. Add miniquests and diary tasks/claims, then Natural History Quiz, museum
   history/finds/kudos/threshold claims and any admitted fossil rewards. Capture
   caps, prerequisite stages, deferability, one-time uniqueness and resource costs.
6. Capture travel waypoints/edges, unlock actions, all balloon route setups,
   museum camp facilities, teleports, ships, spirit trees, fairy rings and other
   relevant networks. Inventory missing networks at the pinned revision instead
   of treating this illustrative list as exhaustive.
7. Measure or estimate action/travel time ranges under explicit movement and
   combat assumptions. These are secondary-objective estimates. Never add training
   methods or XP/hour data: manual training is a requested amount of XP only.

## Normalisation pipeline

`raw JSON -> deterministic adapters -> normalized collections -> structural +
semantic checks -> human review -> versioned catalog -> optimizer -> replay ->
solution JSON`

Adapters are offline and source-specific. Normalize names through an explicit
alias map, use stable IDs, sort records by ID, use canonical units, and preserve
source links. Emit a change report for added/removed quests, changed requirements,
reward deltas, coordinates and travel locks. Unknown and conflicting fields go
into a review queue.

```sh
quest-optimizer normalize-data data/manifest.json --skills data/raw/build-242/skills.json
quest-optimizer audit-data data/manifest.json
quest-optimizer diff-data previous/manifest.json data/manifest.json
```

`normalize-data` validates the merged catalog and writes deterministic JSON to
stdout. The skill adapter reads the pinned skill index and exact XP curve.
For other reviewed observations, pass `--observations BATCH` once per local
file. A batch contains `batch_version: 1`, the matching `game_revision`, a
`collections` object of catalog record arrays, and an optional `aliases` map
from source identifiers to canonical IDs. A location can supply `tile` as
`[x, y, plane]`. A reward or effect can supply `xp` as an integer or exact
decimal string in XP units. The adapter converts that amount to integer XP
tenths. Records may declare an `unknown_fields` list for unresolved facts.

Conflicts and explicitly unknown fields stop normalization and print a JSON
review queue on stderr. The queue includes the conflicting values and their
evidence where available. Record the human decision in reconciliation and use the
reviewed values in the catalog and observation batch. `diff-data` reports added
and removed IDs and changed values by field, including action effects and
travel requirements.

Commit JSON in small domain batches. Each batch includes the raw observations,
normalized records, evidence references, coverage updates and relevant fixtures.
Review unusual requirements and every choice/claim with a second independent
evidence check when practical. Programmatically detect duplicate names/IDs, broken
references, impossible level thresholds, negative values, unreachable locations,
hard dependency cycles and duplicate reward producers. OR/partial-stage cycles
need state reachability analysis, not an indiscriminate DAG rejection.

## Release and maintenance

The draft catalog pins the build 242 snapshot from 3 November 2026. Its
[coverage ledger](../data/coverage/build-242.json) identifies the independently
inventoried content and unresolved reviews. A later game snapshot needs an
explicit revision update and a reconciliation of changed records.

Use the catalog manifest as the release manifest. Its `coverage_ledger` and
`release_profile` paths are relative to the manifest. The ledger references
its journal, diary, reward and optional activity inventories relative to its
own directory. Reconciliation, attribution and license notices are relative to
the manifest directory. Link an inventory row to its catalog records with
`catalog_ids` when it has a different ID. Reward review rows can record exact
action effects in `expected_effects` keyed by action ID.

Run `quest-optimizer validate-data data/manifest.json --release` with a reviewed
catalog, a fully reviewed ledger and a reviewed members profile covering the
quest goals in that ledger. `audit-data` prints the full JSON report. Its exit
status is 2 for audit errors, and a draft backlog is reported in `pending`.
The release check requires both lists to be empty.

Record dataset changes in the [changelog](../data/CHANGELOG.md). Hash normalized
inputs, profile and schemas into solutions and invalidate prior solutions after
relevant changes. New game updates trigger manual review of official notes and
affected records. CI checks committed files.
