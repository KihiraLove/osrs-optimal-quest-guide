# Validation and acceptance gates

## Scaffold checks now

The loader rejects malformed/duplicate-key JSON, non-finite numeric values,
escaping file paths, unexpected fields, duplicate entity IDs, unsupported schema
versions and missing provenance source IDs. JSON Schemas check typed requirements,
effects, coordinates, rewards, profiles and output shape. These checks work fully
offline once the Python dependency is installed.

`--release` deliberately fails closed pending the semantic validation issue. An
empty draft catalog is useful for development, not a usable route dataset. The
synthetic example is contract-only and is never asserted to be a real route.

## Required checks before production data

- Resolve every typed foreign key, including nested requirements/effects, goals,
  initial state, reward eligibility and start/end/travel locations.
- Verify monotonic XP tables, referenced level ranges, exact unit conversions,
  unique reward producers, activity completion ownership, quest-point and kudos
  reconciliation, choice cardinality and caps.
- Validate reachability using OR-aware/phase-aware rules and the initial profile;
  report unsatisfied requirements/cycles without inventing training or supplies.
- Reconcile the independent coverage ledger with all current quests, RFD parts,
  diary tasks/claims and admitted optional content at the pinned game revision.
- Reject synthetic or unresolved facts for production; distinguish measured time
  ranges from gameplay requirements and publish uncertainty where allowed.

## Transition and solver regression cases

Maintain small hand-audited fixtures for: quest XP avoiding training; unavoidable
training; a useful optional quest; an optional detour that is not useful; an OR
prerequisite; a partial-quest unlock; independent RFD subquests and final gates;
delayed post-quest rewards; diary task then claim; quiz then museum threshold claim;
locked balloon route setup; museum camp unlock; asymmetric walking links;
consumed teleport charges; an unusable purchased item; false flags/exclusive
choices; minimum-level lamps; a held lamp; forced immediate use; multiple picks;
level-scaled reward training breakpoints; insufficient resources; impossible goals.

Test that training output contains only XP amounts/gates/resume waypoint and never
chooses methods or estimates training time. Test the requested any-skill quest
lamp policy separately from observed eligibility and non-quest lamp restrictions.
Test no double XP/kudos/quest points, no reward before claim and no travel before
unlock. Network-denied runs must validate and solve with installed dependencies.

Compare candidate solvers against exhaustive optima on tiny cases. On real slices,
replay every step independently, compare per-skill manual XP to a documented
baseline, measure search runtime/memory and inspect route plausibility manually.
Vary activity/travel estimates to expose unstable secondary decisions. Report
heuristic status honestly; require proof for any `optimal` label.

## Frontend release gate (later)

Only begin the viewer after a complete reviewed catalog and a replay-verified full
quest route meet agreed XP/quality targets. The viewer consumes local static JSON,
shows manual XP and reward decisions, exposes assumptions and result status, and
uses `kihiras-tools-common` at a pinned revision. GitHub Pages must deploy only the
frontend distribution and reviewed solution assets; no Python runtime or live Wiki
queries. Add accessibility/responsive and asset-path checks at that stage.
