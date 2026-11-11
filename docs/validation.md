# Validation and acceptance gates

## Local validation

The loader rejects malformed/duplicate-key JSON, non-finite numeric values,
escaping file paths, unexpected fields, duplicate entity IDs, unsupported schema
versions and missing provenance source IDs. The CLI checks typed requirements,
effects, coordinates, rewards, profiles and output shape. Semantic errors in
catalog records identify the record, field, collection file and evidence source
IDs. All checks run offline.

`validate-data` checks nested requirements, typed foreign keys, XP thresholds
and level ranges, duration ordering, token caps, activity ownership and reward
producers, eligibility and pick counts. Use `validate-json --catalog` to check a
profile's dataset, goals and saved state. For a solution, also supply `--profile`
to check the inputs, route references and reward trace. The trace catches spending
before the award, repeated producers, premature claims, split or repeated picks,
missing base levels and deferred immediate rewards. Full route replay checks
travel, items, remaining requirements, final XP, objective totals and input hashes
in #10.

## Production release checks

`audit-data` reconciles local catalog records with the independent coverage
ledger and reports the open review and reachability findings. `--release`
requires reviewed catalog and profile status and an empty coverage audit.

The audit matches quest, subquest, diary, claim and optional activity records to
the ledger. It checks reviewed reward effects when supplied, requires a reason
for each exclusion, and checks provenance references and local attribution.
Duration estimates are allowed for reviewed transitions.

Reachability follows directed links and evaluates AND and OR requirements from
the initial profile. It computes possible progress across routes and allows
manual skill training and waiting. It uses items from the profile or reachable
producers. The report lists blocked transitions and locations for the selected
profile. A blocked quest goal prevents release. Optional routes can remain
unavailable under that profile's policies. Joint route feasibility remains part
of full replay and search.

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
Test the typed contracts at the transition boundaries: a boost is unavailable
at its expiry, a cooldown is ready at its expiry, combat gates use base levels,
and a recorded choice cannot be overwritten. Replay must apply wait steps and
enforce action and travel counts against their respective limits.

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
