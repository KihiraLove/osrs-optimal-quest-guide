# Adding catalog activities

Use the [activity tracker](activity-tracker.md) to find quests, miniquests,
Recipe for Disaster subquests, optional unlocks and reward claims. Use the
[diary tracker](diary-tracker.md) for achievement diary tiers and tasks. Each
row has a canonical ID. Assign work by ID because row numbers can move when
entries are added. The JSON inventories are the source of truth.

## Run parallel batches

1. Assign disjoint IDs to workers in GitHub or in their task prompts. Give each
   worker the same base commit and a separate branch or worktree. Group multiple
   **Very short**, **Short** and **Medium** quests by shared area or prerequisite.
   Assign a long chain to one worker or give the downstream worker the upstream
   branch and merge it first. Diary batches can share a region and tier.
   To list pending rows locally, run
   `rg -F '| Pending |' docs/activity-tracker.md docs/diary-tracker.md`.
2. Ask each worker to put new catalog files under a distinct
   `data/catalog/<batch>/` directory and raw review notes in
   `data/raw/build-242/<batch>-review.json`. The worker can register their files
   in the manifest, add their source rows and update the ledger rows they own.
   If two batches need the same existing location, item, edge, or action, assign
   one worker to edit that record and have the other reference the same ID.
3. Workers run the draft checks and replay their own routes once per batch. Have
   them hand off a branch or commit, the tracker IDs covered, dependencies and
   shared files touched, replay results, and remaining questions. A local
   worktree branch is enough when the integrator can access it. Reserve the
   combined test suite, version bump, tracker regeneration and saved-example
   refresh for the integrator. These generated files often conflict across
   otherwise independent branches.
4. Integrate in dependency order. Rebase or cherry-pick one batch at a time.
   Keep both batches' registrations in shared JSON arrays and preserve the
   original IDs. Validate the combined catalog before pushing it to `main`.
   GitHub Actions already runs the catalog checks, fixture solves and tests.

From a shared clone, create a branch and separate checkout with
`git worktree add -b codex/catalog-batch <worktree-path> <base-commit>`.
Use a different branch and worktree path for each worker.

You can give each worker a prompt like this.

> Catalog `<activity-id>` and `<activity-id>` from commit `<sha>` on
> `codex/catalog-<batch>`. Follow this guide. Reuse existing shared IDs. Report
> any other pending activity or missing item supply that blocks your route.
> Hand off your commit, covered IDs, focused replay results and unresolved facts.
> The integrator handles versioning and generated files.

## Add a batch

1. **Find the ledger entries and current sources.** Start with the tracker IDs.
   Use the [manifest](../data/manifest.json) to find the active coverage ledger.
   Its `entries` paths are relative to the ledger directory. The current
   snapshot uses these inventories.

   | Work | Source inventory |
   | --- | --- |
   | Quests, miniquests and RFD subquests | [journal.json](../data/coverage/build-242/journal.json) |
   | Diary tiers, tasks and NPC claim IDs | [diaries.json](../data/coverage/build-242/diaries.json) |
   | Museum, transport and other optional activities | [optional-activities.json](../data/coverage/build-242/optional-activities.json) |
   | Completion rewards and separate claims | [reward-reviews.json](../data/coverage/build-242/reward-reviews.json) and [reward-registry.json](../data/raw/build-242/reward-registry.json) |

   Search the pinned [quest observations](../data/raw/build-242/quest-helper/index.json)
   and [diary observations](../data/raw/build-242/diaries/index.json) by ID first.
   They include helper file paths, waypoints and candidate prerequisites.
   Check [Quest Month reward changes](../data/raw/build-242/quest-month-rewards.json)
   and other Jagex updates applicable to the pinned revision. Helper declarations
   may lag game updates or combine requirements from different phases. If an
   in-scope activity is missing from the inventory, establish its identity and
   source before adding it.

2. **Record observations and open questions.** Capture the actual start tile,
   stage sequence, base and boostable levels, AND/OR prerequisites, item
   sources and quantities, combat/assistance checks, unlock timing, waits, and
   every reward. Record the game revision, source IDs and any estimates in the
   batch review. Reuse [sources.json](../data/sources.json) IDs when they already
   point to the evidence. New source rows record the locator, observation date,
   revision, attribution and reuse terms. Use pinned licensed sources, official
   Jagex notes and in-game observations. Store original factual summaries in
   JSON. Both applications work offline and the project has no Wiki import.

3. **Reuse or add catalog records.** Search by item, waypoint, action and token
   ID before creating a record. Create only the collection files the batch uses,
   each containing a JSON array. Register each path under its collection in
   `data/manifest.json`. Paths are relative to `data/`. Keep IDs lowercase and
   use the journal ID exactly for the `activities.json` record.

   | File | Batch content |
   | --- | --- |
   | `activities.json` | Name, kind, parent and completion action IDs |
   | `actions.json` | Stages, supply actions, diary tasks and reward claims |
   | `locations.json` | Waypoints with world `x`, `y`, `plane` and instance ID where relevant |
   | `travel_edges.json` | Directed routes, unlock checks, costs, XP and durations |
   | `items.json` | New items, tradeability and stackability |
   | `tokens.json` | New flags, counters, timers and exclusive choices |
   | `xp_rewards.json` | Lamp or choice eligibility, minimum base level, amount and retention |

   All records need evidence. Use integer XP tenths (`46620` means 4,662 XP)
   and integer seconds for ordered `min_seconds`, `expected_seconds` and
   `max_seconds`. See the [data model](data-model.md) and
   [JSON schemas](../schemas/) for field definitions.

4. **Build the route stage by stage.** A stage names its start and end waypoint.
   Requirements apply when it starts. Use `action_completed` for mandatory
   predecessor actions, `all` and `any` for actual logical requirements, and
   `boostable` only where the game permits a boost. Keep held tools in item
   requirements and debit spent supplies with `consumes`. Make GP purchases
   debit carried coins. Give the route a reachable way to obtain every required
   item, including untradeables, or record a missing upstream producer. Use
   `planned_outcome` for uncertain fights, drops and other success-dependent
   transitions. State what the player checks and how to recover. Record a
   conservative XP estimate or a review gap when incidental XP depends on play.

5. **Connect travel and waits.** Connect every stage to the existing graph.
   Add the return journey where the game allows it, including exits from
   dungeons and instances. Check ferry fares, teleports and charges, public
   house access, loadout checks, and which unlocks are already available at that
   point. Put spell XP on the cast edge. Model waiting with `start_cooldown` and
   `cooldown_ready` on the dependent stage so other actions can use the time.
   Use independent cooldowns for independently progressing steps. Keep the
   existing account policies, priorities and manual-training XP objective.

6. **Award rewards where they occur.** Put quest points and fixed completion XP
   on the real completion step. Use separate stages for partial unlocks and
   separate actions for post-quest claims. For lamps and choices, record what
   the game allows, including skill set, base level, number of picks and whether
   a lamp can be held. The existing profile handles any-skill quest lamp policy.
   A package has one producer, and a claim must check its prerequisites and
   prevent duplicate awards. Give RFD subquests their own stages and rewards.
   The parent goal records the finale without paying the rewards again.
   Keep Observatory Quest's random XP and item rewards out of the modeled
   awards. The starting state already credits Learning the Ropes' quest point.

7. **Reconcile the ledger.** Move only the IDs whose catalog records were
   added from `expected` to `collected`. Keep existing goal, client and parent
   IDs. A reward review links to its producing action with `catalog_ids` and
   can record the exact `effects` array under `expected_effects` by action ID.
   Update the raw reward registry when a tracked lamp or claim is added. For
   optional rows whose ID differs from the catalog ID, list the corresponding
   `catalog_ids`. Link the batch review from the relevant section of
   [build-242.json](../data/coverage/build-242.json). Keep unimplemented rows
   pending and note any draft estimates or upstream blockers. Independent review
   is the step that moves a row to `reviewed`.

8. **Validate and replay the batch.** Set up Python 3.11+ using the
   [development commands](../README.md#development). Run these checks from the
   repository root.

   ```sh
   quest-optimizer validate-data data/manifest.json
   quest-optimizer audit-data data/manifest.json
   quest-optimizer normalize-data data/manifest.json --skills data/raw/build-242/skills.json > artifacts/catalog-check.json
   git diff --check
   ```

   Require zero audit errors. The draft audit also prints the remaining backlog.
   For each activity, use a focused profile or local `RouteState` replay with
   the required earlier progress and supplies. Check ordered transitions,
   return paths, spent items, XP, unlocks and repeat protection. Try the gates
   that would fail if a prerequisite, cooldown or claim step were missing.
   A seeded replay proves that slice can run. Report any prerequisite or supply
   that you had to seed because the broader Lumbridge route cannot produce it
   yet. Use the [example profiles](../examples/build-242/) and
   [transition tests](../optimizer/tests/test_quest_collection.py) for patterns.
   Keep scratch replay files under `artifacts/`.

## Pick an existing example

| Mechanic | Example |
| --- | --- |
| Small quest with item inputs and a lamp | [X Marks the Spot catalog](../data/catalog/x-marks-the-spot/) |
| Start gates versus mid-quest travel unlock | [Fairy-ring access actions](../data/catalog/fairy-ring-access/actions.json) |
| Overlapping timers and white tree fruit diary credit | [Garden of Tranquillity and Morytania actions](../data/catalog/morytania-and-garden/actions.json) |
| Task registration shared by a quest stage and a standalone diary action | [Enter the Abyss and diary tasks](../data/catalog/abyss-and-diary-tasks/actions.json) |
| Quiz kudos and later NPC rewards | [Museum catalog](../data/catalog/museum/) |
| Separate setup and use of transport | [Balloon travel catalog](../data/catalog/travel/) |
| Separate post-quest claims and a held choice lamp | [Lighthouse, Varrock and Kourend actions](../data/catalog/varrock-lighthouse-and-kourend/actions.json) |
| Subquests and the parent goal | [Recipe for Disaster review](../data/raw/build-242/recipe-for-disaster-review.json) |

For a diary tier, model task registration, tier completion and the NPC claim
as distinct steps. A task may grant credit on an existing quest or travel
transition if it actually registers in game. Share the task flag across valid
producers and prevent duplicate standalone credit. Gate higher-tier rewards on
the previous tier's claim where required.

For museum and transport, model setup and reward visits separately. Check
kudos thresholds against the persistent counter. Track balloon routes and
museum camp facilities by their individual unlocks.

## Integrate the combined batch

1. Bump `dataset_version` together in `data/manifest.json`,
   `data/coverage/build-242.json`, `data/profiles/main-baseline.json` and
   `examples/build-242/*-profile.json`. Update
   [the changelog](../data/CHANGELOG.md) and the counts in
   [the data inventory](../data/README.md). Keep the game revision pinned until
   a new snapshot is deliberately reconciled.
2. Refresh each saved `*-solution.json` paired with its `*-profile.json`.
   Use `input_identity` from [replay.py](../optimizer/src/quest_optimizer/replay.py)
   for the new hashes. Keep a saved route only if `verify_solution` accepts it
   with the updated inputs. If a route's transitions changed, regenerate or
   fix and replay it before committing.

   Run this Python snippet from the repo root after all catalog and profile
   edits. It checks the routes before writing their updated input fields.

   ```python
   import json
   from pathlib import Path

   from quest_optimizer.data import Contracts, load_catalog, read_json
   from quest_optimizer.replay import input_identity, verify_solution
   from quest_optimizer.semantics import CatalogValidator

   contracts = Contracts(Path("schemas"))
   catalog = load_catalog(Path("data/manifest.json"), contracts)
   validator = CatalogValidator(catalog, contracts)
   refreshed = []
   for path in sorted(Path("examples/build-242").glob("*-solution.json")):
       profile_path = path.with_name(path.name.replace("-solution.json", "-profile.json"))
       profile = read_json(profile_path)
       solution = read_json(path)
       solution["inputs"] = input_identity(catalog, profile, contracts.schemas)
       verify_solution(solution, profile, validator)
       refreshed.append((path, solution))
   for path, solution in refreshed:
       path.write_text(json.dumps(solution, indent=2, ensure_ascii=False) + "\n",
                       encoding="utf-8", newline="\n")
   ```

3. Run the tracker generator, draft checks and tests once on the merged result.

   ```sh
   python tools/render_activity_tracker.py
   python tools/render_activity_tracker.py --check
   quest-optimizer validate-data data/manifest.json
   quest-optimizer audit-data data/manifest.json
   python -m unittest discover -s optimizer/tests -v
   git diff --check
   ```

   Check [the workflow](../.github/workflows/validate.yml) after pushing the
   integrated change. If existing solves fail, diagnose the new records against
   the failing profiles and keep the catalog changes scoped to game data.
