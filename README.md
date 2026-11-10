# OSRS optimal quest guide

An offline Python quest-order optimizer for trade-enabled Old School RuneScape
main accounts, followed later by a separate GitHub Pages viewer.

The draft data pins live build 242 from 3 November 2026. It includes skill
tables, the independent content inventory, and a first batch of quest actions.
The full route requires the remaining quest mechanics and a fresh account capture.
See the [data inventory](data/README.md) and [implementation plan](docs/roadmap.md).

## What “optimal” means

1. Minimise the total XP the player must train manually, summed across skills.
2. Among routes with the same manual XP, minimise estimated activity and travel
   seconds under the selected account and travel assumptions.
3. Break remaining ties deterministically.

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
quest-optimizer validate-data examples/synthetic/manifest.json
quest-optimizer validate-json profile examples/synthetic/profile.json --catalog examples/synthetic/manifest.json
quest-optimizer validate-json solution examples/synthetic/solution.json --catalog examples/synthetic/manifest.json --profile examples/synthetic/profile.json
python -m unittest discover -s optimizer/tests -v
```

`validate-data` checks catalog shape and semantics. With `--catalog`,
`validate-json` also checks profile and solution references against local inputs.
Solutions require the matching `--profile` for that check. Standalone
`validate-json` checks shape. Route replay is tracked in [#10](https://github.com/KihiraLove/osrs-optimal-quest-guide/issues/10).
The `--release` gate requires the independent coverage audit in
[#9](https://github.com/KihiraLove/osrs-optimal-quest-guide/issues/9).

## Documentation

- [Scope, assumptions and optimisation objective](docs/scope.md)
- [Data model and JSON contracts](docs/data-model.md)
- [Gathering, cleaning and maintaining data](docs/data-pipeline.md)
- [Search and independent replay design](docs/optimizer-design.md)
- [Verification and release gates](docs/validation.md)
- [GitHub issue roadmap](docs/roadmap.md)

The repository's BSD-2-Clause license covers project code. Source facts and any
third-party evidence need their own recorded attribution and reuse terms.
