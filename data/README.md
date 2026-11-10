# Local game data

The catalog is intentionally empty and marked draft. `game_revision` and `as_of`
remain null until a real snapshot is gathered and reviewed. Do not use synthetic
examples as game facts. The manifest lists collection files; all are local JSON.

See `../docs/data-pipeline.md` for the acquisition and maintenance process. Add
reviewed JSON in focused batches and keep provenance, units and stable IDs intact.
Production account profiles will live in `profiles/` after starting state is
verified. `sources.json` records evidence and licensing; it is never fetched by
the loader. A full release requires the separate coverage ledger planned in issues.
