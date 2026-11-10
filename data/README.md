# Local game data

The draft catalog targets the Jagex live English build 242 snapshot archived on
3 November 2026 at 10:00:06 UTC. Dataset `0.3.0` loads 24 skill tables and
25 draft actions for nine early quests. The action durations estimate
interactions at a waypoint with supplies ready. Travel times belong to the
travel graph.

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

Each diary task preserves its helper
condition and the observed varbit or VarPlayer bit for identity. The source
paths are evidence for the identity of tasks. Their requirements and reward
amounts have a separate review.

[Sources](sources.json) records provenance and reuse terms. See
[attribution](ATTRIBUTION.md) for the third-party notices and
[reconciliation](raw/build-242/reconciliation.json) for field-level decisions.
A pending review preserves its evidence and reason until a verified value is
available. The [profile seed](profiles/main-baseline.json) records the goal list,
policies and known start fields. See [profiles](profiles/README.md) for capture.
