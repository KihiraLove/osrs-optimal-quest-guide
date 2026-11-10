# Raw observations

Store permitted raw factual observations as JSON, with source IDs, dates, revision,
field values and uncertainty. Keep raw inputs immutable after review; corrections
are new observations with an explicit relationship to the old one. No Wiki scrape,
copied guide prose, credentials or unlicensed media. Normalizers run offline.

## Quest Helper observations

Use `python tools/collect_quest_observations.py <pinned-checkout>` to reproduce
the build 242 observations from a local Quest Helper checkout. The collector
checks the commit against `sources.json` and reads the Java files as text.
It collects literal declarations and helper waypoint candidates. Complex
conditions, combat feasibility and reward timing still need review.

`declared: false` marks an absent source method. A null value records an
unresolved fact. A helper's recommended supplies or progress selectors guide
review and have no effect on the loaded catalog. Use the release notes for
build-specific reward changes, then verify quest phases and the point of award.

## Diary observations

Run `python tools/collect_diary_observations.py <pinned-checkout>` to regenerate
the regional files in `build-242/diaries/`. The collector ties the independent
tracker ledger to Java steps, requirements and panels in the pinned checkout.
Each tier includes source line numbers, taskmaster candidates and lamp numbers
as written in the helper. Resolve boostability, item consumption, tracker
registration and claim sequencing in the
[optional progression review](build-242/optional-progression-review.json).
Panel order and suggested gear are evidence for review.

## Museum observations

`build-242/museum-map.json` records only object names, IDs and origin tiles
from the OpenRS2 copy of build 242 and the pinned RuneLite object IDs.
`build-242/museum-review.json` records reward and unlock evidence separately
from object placement. Candidate tracker gates, inputs and reward amounts
require in-game verification before admission. Movement timing is estimated.

## Travel observations

`build-242/balloon-stops.json` ties the six balloon flags to their tracker IDs
and archived basket and log-storage objects. It records the fuel required for
discovery and subsequent use. `build-242/travel-review.json` inventories other
networks and their review questions. `build-242/travel-timing.json` documents
route estimates and the loadout assumptions behind the draft edges.
