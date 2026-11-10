# Local game data

The draft catalog targets the Jagex live English build 242 snapshot archived on
3 November 2026 at 10:00:06 UTC. The manifest currently loads 24 skills and
their effective level XP thresholds. Quest, diary, museum and travel records
are collected in later batches.

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
parent goal and ten child activities. Each diary task preserves its helper
condition and the observed varbit or VarPlayer bit for identity. The source
paths are evidence for the identity of tasks. Their requirements and reward
amounts have a separate review.

[Sources](sources.json) records provenance and reuse terms. See
[attribution](ATTRIBUTION.md) for the third-party notices and
[reconciliation](raw/build-242/reconciliation.json) for field-level decisions.
A pending review preserves its evidence and reason until a verified value is
available. The [profile seed](profiles/main-baseline.json) records the goal list,
policies and known start fields. See [profiles](profiles/README.md) for capture.
