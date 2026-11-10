# Optimizer design

## Problem formulation

This is a finite state/action planning problem with ordering, consumable rewards
and a changing travel graph. A topological sort of quests cannot choose lamp
allocations, optional unlock detours, claim timing or training deficits correctly.

State includes XP, progress, counters, items, held rewards and location. Actions
check requirements, consume resources, advance time and apply effects atomically.
Goals are the profile's required action completions. Optional actions are retained
when they can reduce manual XP or secondary travel/activity cost; unrelated,
nonbeneficial actions can be pruned only with a sound argument.

## Training and reward decisions

Generate abstract training candidates at meaningful exact XP thresholds: quest
gates, lamp eligibility, next reward lookup breakpoint and any boost/combat-derived
gate. Allow a deliberate amount before a level-scaled lamp if it can improve the
global manual-XP objective. A simple “train only for the next quest” heuristic is
not complete. Threshold reduction needs proof or exact-small-instance comparison.
Never choose a training method, assign XP/hour or add a guessed training time.

Branch on reward target, claim time and allowed deferment. Retain exact deficits,
reward-instance identity and one-time caps. Spending a reward cannot precede its
producer and cannot be fractional unless explicitly permitted. The default quest
lamp skill policy and any departures from observed eligibility travel with output.

## Suggested implementation order

1. Implement a deterministic state transition engine and a separate route replay
   verifier. Validate requirements, claim limits, resource conservation, XP math,
   travel availability and terminal goals before writing a clever solver.
2. Build an exhaustive/Dijkstra or branch-and-bound reference search for tiny
   fixtures using lexicographic `(manual XP, non-training seconds)` path costs.
   Prove results for those finite instances, including optional detours and lamps.
3. Establish a deterministic feasible baseline for curated real slices: dependency
   scheduling, reward-aware lookahead and travel-aware tie breaking. Report it as
   a baseline, not globally optimal. Compare against a no-optional-reward baseline.
4. Evaluate A*/branch-and-bound, beam search and large-neighbourhood improvement.
   Profile state growth before selecting a production backend. A CP-SAT/MIP model
   is an experiment, not a promised fit for arbitrary dynamic state and travel.
5. Run the full reviewed catalog with bounded time/memory and a fixed seed. Store
   best-known incumbents and bounds where justified. Never change the primary
   objective into an undocumented weighted sum for convenience.

Travel routing uses directed edges filtered by state and policy. Pure fixed-cost
edges can use shortest path; consumed charges, granted XP/unlocks or cooldowns may
make a single shortest path insufficient. Preserve nondominated path outcomes
when they affect future feasibility/objectives. Cache by every relevant state
component, not merely the number of completed quests.

Pruning/dominance must respect location, held lamps, resource counts, false-flag
requirements, choice history and any time state. More XP can change level-dependent
rewards, so a pruning rule needs explicit proof/tests. Admissible lower bounds on
unavoidable manual XP must not over-credit incompatible future rewards. Minimise
secondary time only after the primary optimum is fixed or clearly label the
result as best known. Stable ordering makes runs reproducible.

## Output and explanation

Export an ordered route with quest/subquest/activity names, travel legs, reward
allocations, claim visits and training blocks. Include before/after state deltas,
the reason each training block is needed, unlocked travel, per-skill manual XP,
non-training time totals, input hashes and limitations. Full trace/checkpoint
compression is a later contract refinement; replay uses the original local data.

The independent verifier reconstructs every state from the profile rather than
trusting solver summaries. Export only after replay succeeds. Keep schema validity,
replay validity, dataset completeness and optimality proof as distinct statuses.
No solution is called “optimal” merely because a solver terminated successfully.
