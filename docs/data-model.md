# Data model (draft v0.1.0)

The machine-readable contracts are in `schemas/`. Validation checks shape and
relationships between records. Gameplay evidence, coverage and route replay
have separate gates. Game facts and estimates come from local JSON.

## Files and identity

`data/manifest.json` declares dataset ID, version, game revision, status, coverage
status and the relative JSON files for each collection. The loader combines the
collections into a catalog before JSON Schema validation. Paths must stay within
the manifest directory. No URL imports, remote schema references or implicit
network fetching are allowed. `data/sources.json` is a source registry, not a
download queue. `examples/synthetic/` uses the same format with invented facts.

Stable lowercase IDs are globally unique across collections, such as
`quest.cooks_assistant.complete`, `rfd.freeing_the_goblin_generals.complete`,
`claim.museum.quest_history.example` and `travel.balloon.route.example`. These
are naming illustrations, not populated factual records. Renames keep aliases in
a reviewed migration map. Foreign keys always use canonical IDs.

## Compatibility and migrations

The loader accepts `0.1.0`. The new mechanics add optional fields and variants
at this version, so the original `0.1.0` files still load. An earlier validator
may reject documents that use the new fields. The semantic checks require every
reference to resolve and every skill to have explicit XP in saved states. For a
partially used reward with distinct choices, recover the previous picks from the
source record before adding `used_skill_ids`. Use integer literals for quantities,
XP and time, such as `1000` for 100 XP.

A breaking change requires a schema version and schema `$id` update, an offline
migration for affected manifests, collections and profiles, and updated fixtures.
Keep the source JSON and record any changed units or assumptions in the migration
notes. A data-only revision changes `dataset_version`. Regenerate solution
artifacts from migrated inputs and their new hashes.

Keep IDs stable when display names change. When correcting an ID, preserve an
explicit old-to-new mapping scoped to the source revision and collection. The
normalizer or migration must reject ambiguous aliases, cycles and nonexistent
targets, then rewrite references to canonical IDs. The runtime validator accepts
canonical IDs directly and reports stale references with their record and field.

| Collection | Main fields and purpose |
| --- | --- |
| `sources` | Source kind, locator, retrieval/observation date, revision, attribution, license, notes |
| `skills` | Name and exact cumulative XP thresholds in tenths of XP, indexed from level 1 |
| `locations` | Region, world tile x/y/plane, instance key, provenance; graph vertices |
| `tokens` | Boolean progression/unlock/quest-stage flags and bounded counters such as quest points and kudos |
| `items` | Tradeability, stackability and abstract inventory role; no implication that trade bypasses use gates |
| `activities` | Grouping metadata for quests, RFD subquests, miniquests, diary tiers and museum/unlock activities |
| `actions` | Atomic transitions: requirements, start/end location, duration, consumes, effects and one-time/repeat limit |
| `travel_edges` | Directed start/end, movement mode, requirements, time, consumables and effects |
| `xp_rewards` | Fixed/choice/level-dependent XP packages, eligibility, lamp policy class, retention and use rules |
| `combat_formulas` | Optional collection of data-driven combat level calculations |

Every factual entity has `evidence`: source IDs, verification status and a note.
An evidence note maps exceptions or estimates to fields; field-specific evidence
can be added when one record combines conflicting sources. `unknown` is not zero.
Draft data may be incomplete; release gates reject unresolved facts on reachable
routes. Durations include nominal/min/max values to support sensitivity tests.

## State and requirement expressions

Solver state: exact XP vector, completed action set, flags, counters, inventory,
unspent reward instances, current location, elapsed modelled time, active boosts,
cooldowns, choices and repeat counts. Profile JSON supplies the initial state and
policy choices.
Use integer tenths of XP (`xp_tenths`) throughout to retain fractional XP without
floating-point drift. Seconds are non-negative integers. Tiles use world
coordinates and plane; regions and instance IDs prevent false same-tile matches.

Requirements form recursive `all` / `any` expressions (empty `all` is true).
Leaves check `skill`, `action_completed`, `flag`, `counter`, `item`, `policy`,
`combat_level`, `elapsed_time`, `cooldown_ready` or `choice`. Skill tables start
at zero XP for level 1 and strictly increase. A `skill` leaf with `boostable: true`
can use a currently active bonus. Flag checks can require true or false.

Do not flatten OR prerequisites into AND dependencies. Requirements are checked
before effects. Use phase actions for start vs mid-quest checks, partial-quest
access, exclusive paths and unlocks available before completion. Activity-level
grouping has no effects. Dependencies live on actions, not on display groups.

Effects award fixed XP, grant/clear flags, add counters/items or award an XP reward
instance. `consumes` lists the items debited atomically with a transition.
Counter effects apply within zero and the token's `maximum` if one is set.
Each reward has at most one producer, and reviewed catalogs require a producer.
Every transition that awards XP or an XP reward has `repeat_limit: 1`.

## Typed transition mechanics

The transition and replay work in [#10](https://github.com/KihiraLove/osrs-optimal-quest-guide/issues/10)
uses these contracts. All requirements are checked at transition start, then
time advances and effects apply at transition end. Split a transition into
phases when it has checks at different times. A `wait` step adds a positive
number of modelled seconds. Personal training leaves the modelled clock unchanged.

- `skill_boost` applies one constant bonus per skill. It replaces that skill's
  active bonus and expires at transition end time plus `duration_seconds`.
  Activation requires `allow_boosts`. Store an active bonus in `active_boosts`
  with `bonus_levels` and `expires_at_seconds`. Remove it at the expiry timestamp.
  Decay schedules need a future contract extension.
- `combat_level` checks a `formula_id` against unboosted skill levels. Each term
  contributes `weight * floor(level * level_multiplier / level_divisor)`. Sum
  the base terms, add the highest style sum, then floor after dividing by the
  formula's `divisor`. Formula values and evidence belong in the catalog.
- `elapsed_time` compares the current clock with `minimum_seconds`.
  `start_cooldown` sets a cooldown token's ready time to transition end time
  plus `duration_seconds`. It replaces that token's timer. `cooldown_ready`
  passes once the timer expires or if none is active. The `cooldowns` map stores
  future ready times only.
- `choice` checks the selected option for a choice token, with `null` meaning
  unset. `choose` sets an option once and requires an unset token. A saved
  state's `choices` map contains only selected options.
- Actions record completion on first execution. A completed action has count
  one unless `action_counts` gives a larger count within `repeat_limit`.
  Travel edges with `repeat_limit` record uses in `travel_counts`. An edge
  without a limit can be reused, subject to its gates and resources.

Saved states can omit the new maps when empty. The exact `xp_tenths` vector
contains every catalog skill. Missing flags default to false, and missing
counter and inventory entries default to zero.

## Important decompositions

- **Recipe for Disaster:** opening segment, each rescue subquest and final segment
  get separate activities/actions; prerequisites, quest points, XP, access and
  reward claims apply at their actual stages. Completion of the parent is an
  explicit final goal, never a second copy of all subquest rewards.
- **Achievement diaries:** tasks, task registration where needed, tier completion
  and NPC reward claim are separate. Model lower-tier claims, per-task boosts,
  counters, equipment and incremental transport benefits. Tasks may overlap other
  actions only when evidence confirms that performing the action records the task.
- **Museum:** Natural History Quiz, quest-history dialogue, finds, exhibits,
  kudos thresholds, threshold reward visits and fossil-related rewards are separate
  capped sources. Fossil acquisition is not free; tradeability is recorded.
- **Transport:** unlock quests and route-specific setup, balloon destinations,
  landing points, museum camp construction, relevant facilities and subsequent
  transport activation are distinct from merely having reached an area.
- **Post-quest rewards:** completion flags unlock separate NPC visits, training,
  books or item exchanges. Award once, at the correct location, with their own
  skill/quest checks and reward choices.

These are the required collection categories; exact game values and the complete
list of sources/claims must be verified during acquisition, not guessed here.

## Travel and inventory

Use a directed graph of meaningful waypoints with measured/curated walk links.
Coordinates support display and audit; Euclidean distance is not a walk route
through walls, water, one-way obstacles or instances. Each edge has requirements,
consumes, effects, a mode and time bounds. Fast routes can appear only after their
setup action. Charged jewellery, runes, transport fees and limited-use teleports
consume inventory/counters. Spellbook, level, quest, region, equipment, cooldown
and wilderness restrictions must be expressed explicitly before release.

Intra-quest travel must be represented either by intermediate action legs or in
the action duration; never both. Start/end waypoints are mandatory even for an
aggregate quest action. Walking, run-energy assumptions, stamina supplies, POH
access and logout/world switching are profile-controlled refinements.

## Rewards

`xp_rewards` distinguishes quest lamps, other lamps, tomes and choice packages.
It stores quantity, eligibility by skill and minimum level, observed restrictions,
whether the reward can be banked/deferred, and either a fixed amount or an exact
lookup by target level. Multiple picks have explicit count and distinct-skill
constraints. Each pick is indivisible unless the source explicitly says otherwise.
Award and consume occur separately; immediate-use rewards must be spent at their
claim before another action. The model must not spend a future lamp to unlock its
own source. Multiple-skill fixed rewards use separate `xp` effects.
A saved held reward records its `remaining_picks`. For a partially used package
that requires distinct skills, `used_skill_ids` lists every previous pick.
Immediate-use rewards must be fully resolved before a saved state boundary.

## Profile and solution boundary

Profile JSON includes initial state, required goal action IDs and all optimization
policies. Production goals enumerate reviewed quest completion actions at a pinned
revision. Optional activities are not goals merely because they are present.

`solution.schema.json` requires input identities/hashes, policy summary, solver
version/seed/status, objective values, manual XP totals, ordered steps, final state,
limitations and verification status. Step variants distinguish action, travel,
reward use, waiting and abstract training. A training step includes `skill_id`, `gain_xp_tenths`,
`before_xp_tenths`, `after_xp_tenths`, `required_by` and `resume_location_id`.
The future replay verifier checks arithmetic, requirements, ownership and all
state transitions; JSON Schema only checks their shape.

Expose route evidence and assumptions to the viewer. `optimal` requires a proof
or exhausted exact search for the declared finite model. `feasible` / `best_known`
must be used for heuristic results. Lower bounds/gaps are per lexicographic phase,
never a single weighted objective disguised as an XP optimum. A synthetic example
must remain marked `example` and unverified.
