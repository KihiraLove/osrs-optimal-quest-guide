# Data model (draft v0.1.0)

The machine-readable contracts are in `schemas/`. They define the initial shape,
not proof of gameplay accuracy. Breaking changes require a schema version bump,
fixture updates and a migration note. All game rules and estimates come from
local JSON; Python implements generic requirement/effect semantics and search.

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
a reviewed migration map; display names never serve as foreign keys.

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

Every factual entity has `evidence`: source IDs, verification status and a note.
An evidence note maps exceptions or estimates to fields; field-specific evidence
can be added when one record combines conflicting sources. `unknown` is not zero.
Draft data may be incomplete; release gates reject unresolved facts on reachable
routes. Durations include nominal/min/max values to support sensitivity tests.

## State and requirement expressions

Solver state: exact XP vector, completed action set, flags, counters, inventory,
unspent reward instances, current location, elapsed modelled time and limited-use
travel/cooldown state. Profile JSON supplies the initial state and policy choices.
Use integer tenths of XP (`xp_tenths`) throughout to retain fractional XP without
floating-point drift. Seconds are non-negative integers. Tiles use world
coordinates and plane; regions and instance IDs prevent false same-tile matches.

Requirements form recursive `all` / `any` expressions (empty `all` is true).
Leaves check `skill` (minimum level and whether boostable), `action_completed`,
`flag`, `counter`, `item` or `policy`. Exact XP/level relationships derive from the
skill's XP table. A boostable check permits a separately modeled active boost; it
does not automatically supply one. Flag checks can require true or false, so the
search cannot blindly assume every unlock only helps.

Do not flatten OR prerequisites into AND dependencies. Requirements are checked
before effects. Use phase actions for start vs mid-quest checks, partial-quest
access, exclusive paths and unlocks available before completion. Activity-level
grouping has no effects. Dependencies live on actions, not on display groups.

Effects award fixed XP, grant/clear flags, add counters/items or award an XP reward
instance. Consumed items are separate from requirements so possession is not
confused with consumption. Each action completion is automatically recorded once;
repeat limits are explicit. Mutually exclusive choices use state flags/choice
groups, not multiple simultaneously awarded rewards. Counter caps and reward
instance ownership prevent duplicate kudos, quest points and lamps.

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
access, logout/world switching and cooldowns are profile-controlled refinements.
The first schema does not yet model active boost expiration or generic cooldown
timers: add typed state and tests in the mechanics issue before admitting records
that rely on them. No untyped catch-all extension can make a route release-ready.

## Rewards

`xp_rewards` distinguishes quest lamps, other lamps, tomes and choice packages.
It stores quantity, eligibility by skill and minimum level, observed restrictions,
whether the reward can be banked/deferred, and either a fixed amount or an exact
lookup by target level. Multiple picks have explicit count and distinct-skill
constraints. Each pick is indivisible unless the source explicitly says otherwise.
Award and consume occur separately; immediate-use rewards must be spent at their
claim before another action. The model must not spend a future lamp to unlock its
own source. Multiple-skill fixed rewards use separate `xp` effects.

## Profile and solution boundary

Profile JSON includes initial state, required goal action IDs and all optimization
policies. Production goals enumerate reviewed quest completion actions at a pinned
revision. Optional activities are not goals merely because they are present.

`solution.schema.json` requires input identities/hashes, policy summary, solver
version/seed/status, objective values, manual XP totals, ordered steps, final state,
limitations and verification status. Step variants distinguish action, travel,
reward use and abstract training. A training step includes `skill_id`, `gain_xp_tenths`,
`before_xp_tenths`, `after_xp_tenths`, `required_by` and `resume_location_id`.
The future replay verifier checks arithmetic, requirements, ownership and all
state transitions; JSON Schema only checks their shape.

Expose route evidence and assumptions to the viewer. `optimal` requires a proof
or exhausted exact search for the declared finite model. `feasible` / `best_known`
must be used for heuristic results. Lower bounds/gaps are per lexicographic phase,
never a single weighted objective disguised as an XP optimum. A synthetic example
must remain marked `example` and unverified.
