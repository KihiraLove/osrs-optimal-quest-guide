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
2. Capture skill XP thresholds, tutorial state and account assumptions. Verify
   fractional XP handling and distinguish base levels from boostable checks.
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

## Normalisation pipeline to implement

`raw JSON -> deterministic adapters -> normalized collections -> structural +
semantic checks -> human review -> versioned catalog -> optimizer -> replay ->
solution JSON`

Adapters are offline and source-specific. Normalize names through an explicit
alias map, use stable IDs, sort records by ID, use canonical units, and preserve
source links. Emit a change report for added/removed quests, changed requirements,
reward deltas, coordinates and travel locks. Unknown and conflicting fields go
into a review queue; never fill them with zero or silently prefer the newest file.

Commit JSON in small domain batches. Each batch includes the raw observations,
normalized records, evidence references, coverage updates and relevant fixtures.
Review unusual requirements and every choice/claim with a second independent
evidence check when practical. Programmatically detect duplicate names/IDs, broken
references, impossible level thresholds, negative values, unreachable locations,
hard dependency cycles and duplicate reward producers. OR/partial-stage cycles
need state reachability analysis, not an indiscriminate DAG rejection.

## Release and maintenance

The initial catalog is empty and marked `draft`, with unknown game revision/date.
Never label it as the game state on the scaffolding date. Synthetic examples are
stored separately and cannot pass the release gate.

A dataset release requires a complete reviewed coverage ledger, verified required
facts, recorded estimates/uncertainties, semantic checks and a human-readable diff.
Hash normalized inputs, profile and schemas into the solution. Keep a changelog
and invalidate prior solutions after relevant data/model changes. New game updates
trigger manual review of official notes and affected records; no automatic live
update happens in either application. CI checks committed files only.
