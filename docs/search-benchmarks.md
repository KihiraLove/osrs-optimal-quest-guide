# Search benchmarks

Run the committed cases from the repository root with the optimizer installed.

```sh
python optimizer/benchmarks/search.py > artifacts/search-benchmarks.json
```

The report records hashed inputs, route IDs, objectives, solver settings,
expansions, wall time and traced Python peak memory. Wall time includes tracing
and route replay. Timing and memory are local measurements. The bounded runs
below use seed 0, beam width 32 and at most 20,000 expansions. The fixture
overrides use synthetic saved accounts and the committed build 242 catalog.
[Fixture definitions](../examples/build-242/search-benchmarks.json)

| Fixture and search | Manual XP | Modelled seconds | States expanded | Wall seconds | Traced peak MiB |
| --- | ---: | ---: | ---: | ---: | ---: |
| Synthetic exact | 100 | 60 | | 0.65 | 3.82 |
| Synthetic bounded | 100 | 60 | 1 | 0.10 | 0.32 |
| Three Lumbridge quests, exact | | | | 1.57 | 24.82 |
| Three Lumbridge quests, bounded | 0 | 520 | 554 | 1.78 | 2.99 |
| Museum threshold, optional claim available | 0 | 102 | 64 | 0.37 | 2.05 |
| Museum threshold, optional claim excluded | 0 | 102 | 44 | 0.36 | 2.02 |
| Varrock balloon, Crafting Guild discovery available | 0 | 222 | 45 | 0.42 | 2.02 |
| Varrock balloon, Crafting Guild discovery excluded | 2,000 | 105 | 860 | 1.53 | 3.63 |

The exact Lumbridge run exceeded its 5,000-state limit. The bounded route
completed Cook's Assistant, Sheep Shearer and X Marks the Spot. Its manual XP
matches the primary lower bound of zero. The bounded solver reported a 50 XP
lower bound on the synthetic route, which has a 100 XP exact optimum.

Both museum routes reach 100 kudos at the final plaque and proceed to the
Bone Voyage start goal without visiting Orlando for the separate XP claim.
In the balloon case, Crafting
Guild discovery supplies 2,000 Firemaking XP before the Varrock level gate.
The available detour remained the chosen route with the catalog's minimum
and maximum duration estimates, taking 96 and 500 seconds respectively.
The restricted runs use the same account and goals and change only the
indicated action's availability to the search. The synthetic diary regression
also compares a task, tier and lamp claim with the claim excluded.

The draft catalog contains 12 collected entries out of 204 in the journal
coverage ledger. A reviewed full-route comparison and larger-instance search
evaluation remain open. [Issue #12](https://github.com/KihiraLove/osrs-optimal-quest-guide/issues/12)
