# OSRS optimal quest guide

An offline Python quest-order optimizer for trade-enabled Old School RuneScape
main accounts, followed later by a separate GitHub Pages viewer.

The draft data pins live build 242 from 11 November 2026. The main baseline
starts in Lumbridge with one quest point, the starter kit and 25 banked coins.
The self-funded starter fixture runs three quests from that state. The full
route depends on the remaining catalog entries.
See the [data inventory](data/README.md) and [starter fixture](examples/build-242/README.md).

## What “optimal” means

1. Minimise counted manual XP. The main profile counts Prayer training only
   above level 43 and still reports all actual XP.
2. Reach priority skill targets early, then reach action milestones such as
   fairy-ring access.
3. Minimise total estimated activity and travel time.
4. Prefer actual spell casts on otherwise tied routes and break remaining
   ties deterministically.

Training steps specify the skill, required XP gain and target XP. **The player
chooses the training method.** Training time, training rates and travel to/from
training spots are not estimated. The secondary objective is therefore not an
estimate of total account completion time. See [scope and policies](docs/scope.md).

Quest rewards, lamps, miniquests, diary tasks and claims, the Natural History Quiz,
museum kudos and rewards, transport unlocks, and post-quest reward claims are all
part of the planned search. Recipe for Disaster is represented by its subquests.

## Two separate applications

| Path | Responsibility |
| --- | --- |
| `optimizer/` | Python loading, validation and, later, search and JSON export |
| `frontend/` | Reserved for the static viewer; implementation is deferred |
| `data/` | Versioned local JSON catalog, source register and future account profiles |
| `schemas/` | Draft contracts for catalog, profile and solution JSON |
| `examples/` | Synthetic contract fixtures, never production game data |
| `docs/` | Model, acquisition workflow, solver design, quality gates and issue roadmap |
| `artifacts/` | Generated output; published solutions will be explicitly reviewed |

The optimizer and future frontend must work without requesting game data from the
OSRS Wiki or other remote sources. All game facts and model inputs are committed
JSON. The future frontend will consume a validated solution JSON and the shared
[`kihiras-tools-common`](https://github.com/KihiraLove/kihiras-tools-common) module.

## Development

Use Python 3.11 or later. From the repository root:

```sh
python -m venv .venv
# Activate .venv using your shell's usual command.
python -m pip install -e ./optimizer
quest-optimizer validate-data data/manifest.json
quest-optimizer audit-data data/manifest.json
quest-optimizer normalize-data data/manifest.json --skills data/raw/build-242/skills.json
quest-optimizer validate-data examples/synthetic/manifest.json
quest-optimizer validate-json profile examples/synthetic/profile.json --catalog examples/synthetic/manifest.json
quest-optimizer replay examples/synthetic/solution.json --catalog examples/synthetic/manifest.json --profile examples/synthetic/profile.json
quest-optimizer solve-small examples/synthetic/manifest.json examples/synthetic/profile.json > artifacts/small-route.json
quest-optimizer solve-bounded data/manifest.json examples/build-242/museum-quiz-profile.json --incumbent artifacts/museum-route.json --report artifacts/museum-search.json
python -m unittest discover -s optimizer/tests -v
```

`validate-data` checks catalog shape and semantics. With `--catalog`,
`validate-json` also checks profile and solution references against local inputs.
Supply the matching `--profile` to check a solution's references, reward trace,
inventory consumption and supported ordered progression gates.
Standalone `validate-json` checks shape. `replay` reconstructs the route from
the original catalog and profile, checks the input hashes and verifies the
final state, goals and totals. The `--release` gate requires a reviewed
catalog, complete independent coverage and a reviewed profile.
See [the data pipeline](docs/data-pipeline.md).

`solve-small` writes a replay-verified exact result for a small finite instance.
It minimises manual XP first, then modelled activity and travel time, then
stable move IDs. The search fails explicitly if it hits `--max-states`
(50,000 by default). The game catalog remains in draft review.

`solve-bounded` searches larger profiles with a configurable beam width, expansion
budget and seed. It independently replays a complete route before returning it.
`--incumbent` reuses a verified route with matching inputs and saves improvements.
`--report` records search counts, runtime and traced Python memory.
See the [search benchmarks](docs/search-benchmarks.md).

## Documentation

- [Add catalog activities and coordinate parallel batches](docs/adding-activities.md)
- [Numbered activity tracker](docs/activity-tracker.md) and [achievement diary tracker](docs/diary-tracker.md)
- [Scope, assumptions and optimisation objective](docs/scope.md)
- [Data model and JSON contracts](docs/data-model.md)
- [Gathering, cleaning and maintaining data](docs/data-pipeline.md)
- [Search and independent replay design](docs/optimizer-design.md)
- [Verification and release gates](docs/validation.md)
- [GitHub issue roadmap](docs/roadmap.md)

The repository's BSD-2-Clause license covers project code. Source facts and any
third-party evidence need their own recorded attribution and reuse terms.
