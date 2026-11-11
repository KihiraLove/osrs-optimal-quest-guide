# Local game data

The draft catalog targets the Jagex live English build 242 snapshot archived on
3 November 2026 at 10:00:06 UTC. Dataset `0.13.0` loads 24 skill tables and
105 draft actions, including Lost City stages, The Restless Ghost, the museum
route and Enlightened Journey. Durations estimate each interaction at its
waypoint with supplies ready. Travel between
waypoints belongs to the travel graph. An action description identifies any
movement included in its duration.

[The coverage ledger](coverage/build-242.json) inventories identities
independently of the catalog. It links to the pinned journal, diary task, reward
review and optional activity lists. Later data batches reconcile their output
against these IDs. The ledger uses these statuses.

| Status | Meaning |
| --- | --- |
| `expected` | Identified from a source and awaiting normalized mechanics |
| `collected` | Present in the normalized catalog and checked by the validator |
| `reviewed` | Coverage and gameplay facts independently reviewed |
| `excluded` | Outside this route's scope, with a recorded reason |

The journal list preserves the client quest ID. Recipe for Disaster has one
parent goal and ten child activities in the
[stage review](raw/build-242/recipe-for-disaster-review.json). The review records
the finale gate and separates its lamp and quest point from the parent goal.
Equipment, combat, instance transitions and reward details require review
before the stages can enter the loaded catalog.

[Quest Helper observations](raw/build-242/quest-helper/index.json) cover 209
journal activities. They identify candidate coordinates, requirements,
source-specific branches, items and rewards. The remaining helper gaps and
all uncollected entries are explicit in the inventory. The
[publisher reward changes](raw/build-242/quest-month-rewards.json) identify the
build 242 XP updates, including the separately claimed Demon Slayer reward.
The [reward registry](raw/build-242/reward-registry.json) records 38 reward
entries, including seven separate claims. Each claim records its producer ID,
quest gate, available location evidence and known award details. Null values
identify fields that need verification. X Marks the Spot has a loaded producer
and lamp definition. The other packages stay in review while their quest
actions or use rules are being collected.

[Diary observations](raw/build-242/diaries/index.json) link all 492 tracker IDs
to helper steps, requirements and item candidates across 48 tiers. Each tier
has a separate claim record with the taskmaster candidates, lamp values and
travel unlock references. The [optional progression review](raw/build-242/optional-progression-review.json)
tracks pending mechanics for all 19 miniquests, publisher corrections and the
overlap between diary tasks and the essence mine teleports in Enter the Abyss.
Only the three individual task flags are loaded. Complete diary tiers and their
claims require gameplay review before they enter the catalog.

The [museum review](raw/build-242/museum-review.json) links all 14 quiz plaques to
the [archived object tiles](raw/build-242/museum-map.json). Each plaque gives two
kudos and Orlando Smith separately awards 1,000 XP in Hunter and Slayer. The
draft Bone Voyage route checks 100 kudos and imports The Dig Site completion from
profile history while that quest is being normalized. Bone Voyage unlocks the
barge edges and walking routes to six camp facility sites. Clerk rewards, camp
construction, additional travel activations, and fossil acquisition and exhibits
are in gameplay review.

[Balloon stop observations](raw/build-242/balloon-stops.json) record the six
build 242 basket locations and the fuel and skill requirements of discovery.
The draft graph includes four post-quest discovery actions, 30 directed
regular flights, the Entrana ferry, public walks, and one-way Varrock tablet
edges. Read the [travel assumptions](raw/build-242/travel-timing.json) for
packing and timing and the [network review](raw/build-242/travel-review.json)
for open acquisition and transport mechanics.

[Sources](sources.json) records provenance and reuse terms. See
[attribution](ATTRIBUTION.md) for the third-party notices and
[reconciliation](raw/build-242/reconciliation.json) for field-level decisions.
A pending review preserves its evidence and reason until a verified value is
available. The [main baseline](profiles/main-baseline.json) records the goal
list, policies and modeled Lumbridge arrival with one quest point. The
[self-funded economy](catalog/starter-economy/actions.json) models bank
withdrawal, one sale and purchases with carried coins. Price observations
are in the [starter economy record](raw/build-242/starter-economy.json).

[The Fairytale II review](raw/build-242/fairytale-ii-review.json) separates
fairy-ring access at the Godfather conversation from the later skill checks
and completion rewards. Two staff-gated surface codes are modeled. The
unlock fixture uses saved Lost City and Fairytale I progress while the
prerequisite routes and the second phase are in collection.

The [Lost City review](raw/build-242/lost-city-review.json) records the
Lumbridge Swamp start, the Entrana dungeon descent, the branch and staff skill
checks, and the first entry into Zanaris. The [Entrana loadout record](raw/build-242/entrana-loadout.json)
documents the reviewed item restrictions and the Port Sarim deposit box tile.
Ferry and balloon arrivals check the current pack. Banked gear can be retrieved
at Lumbridge Castle. The [Lost City combat review](raw/build-242/lost-city-combat.json)
records two conditional Fire Strike steps. The forecast debits each rune
reserve and credits a floor on base cast XP. Reconcile runes and XP with the
observed state before replanning. The funded fixture reaches Zanaris from
Lumbridge with saved levels and carried GP. The preparation and saved
post-combat fixtures remain available for those route segments.

The [timer inventory](raw/build-242/progression-timers.json) lists the step
blocked by each timer. Martin's timer runs in the catalog. Garden of
Tranquillity, the white-tree fruit diary task, Forgettable Tale and Rum Deal
still need their progression and travel records admitted.

The [standard teleport edges](catalog/standard-teleports/travel_edges.json)
cover selected origins for Varrock, Lumbridge and Falador. Casts require the
standard spellbook, carried runes and the spell's Magic level. The three
public house portals from Rimmington use the World 330 host assumption.

[The Restless Ghost review](raw/build-242/restless-ghost-review.json) records the
amulet and skull pickups, the route that leaves the skeleton behind, and the
Prayer XP and quest point at the coffin. It also records the remaining gameplay
checks for the waypoint and duration estimates.
