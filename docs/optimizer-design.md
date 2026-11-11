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

The reference search generates training candidates at quest gates, boosted
gates, combat term thresholds, lamp eligibility and reward lookup breakpoints.
It also enumerates every XP tenth up to the highest relevant threshold for
each skill. An action's fixed XP can cross a breakpoint before it forces an
immediate lamp pick, so a smaller training gain can be optimal. Above the
highest threshold, extra XP cannot affect a later requirement or reward
lookup. Consecutive training steps at one waypoint commute and leave the
clock unchanged, so the search combines them into one gain per skill in
skill ID order. The player chooses the training method and location.

Branch on reward target, claim time and allowed deferment. Retain exact deficits,
reward-instance identity and one-time caps. Spending a reward cannot precede its
producer and cannot be fractional unless explicitly permitted. The default quest
lamp skill policy and any departures from observed eligibility travel with output.

## Exact reference search

`solve-small` uses Dijkstra search with lexicographic costs ordered by manual
XP, non-training seconds and the sequence of stable move IDs. The search key
includes exact XP, progress, resources, held rewards and active timer lengths.
Absolute time saturates in the key once it reaches the largest elapsed-time
requirement. It still contributes to route cost and final state. One-second
waits cover every reachable timer boundary. Positive time or a finite use
count is required for travel, and travel that grants items or increases an
uncapped counter must have a finite use count. XP and reward producers are
one-time transitions.

The two-quest regression enumerates both orders and every training gain in
the fixture range. Dependency order and largest-XP-reward-first both require
4 XP tenths and 7 seconds. The optimum requires 3 XP tenths and 7 seconds.
A second enumeration checks that 3 XP tenths before a forced scaled reward
can beat training directly to the next threshold.

The state budget bounds the reference search. It produces an exact result
when it reaches the best goal and fails explicitly if the budget is exceeded.
Search on reviewed full-game inputs will need a scalable baseline, profiling,
and comparisons with bounded methods such as beam search and neighbourhood
improvement. Report any proved bounds and keep the manual XP objective first.

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
