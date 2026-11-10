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
