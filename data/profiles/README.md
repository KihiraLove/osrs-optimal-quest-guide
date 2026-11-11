# Account profiles

[The build 242 main profile seed](main-baseline.json) records the objective,
policy choices, all quest goal IDs and the published facts about tutorial
completion. It is awaiting an observed account state and the catalog actions
referenced by those goals. A null value records a specific capture gap.

To prepare the solver profile, capture a fresh, trade-enabled normal members main
at its first controllable tile after leaving Tutorial Island, before taking any
other action. Record the client build, observation date and tutorial choices.

1. Record the world tile and plane, equipped items and inventory quantities.
2. Record XP for each skill, including Hitpoints and XP gained during the tutorial.
   Use exact values in tenths, with evidence for any fractional gains. Levels
   alone only establish an XP range.
3. Record quest progress and quest points, starting flags and counters, held
   rewards and remaining teleport cooldowns. Note any tutorial unlocks.
4. Save the factual observation under `data/raw/` with a source ID, date, build
   and locator. Keep player identifiers and credentials out of the data.
5. Normalize the capture and resolve the goal IDs once the quest actions exist.
   Validate the resulting profile using `validate-json profile --catalog`.

Jagex documents one quest point for tutorial completion and the Home Teleport
to Lumbridge. The documented cooldown reset applies before casting. Record
the first controllable tile and remaining cooldown on arrival. Keep the
observed tile separate from the estimated courtyard walking anchor until
they can be compared. [Tutorial release notes](https://secure.runescape.com/m=news/grid-master-rewards-poll--new-player-improvements?oldschool=1)

Record the observed tutorial path so its skill XP can be reproduced. The
January 2026 notes document a change to combat training on the island.
[New Player Improvements Round 2](https://secure.runescape.com/m=news/new-player-improvements-round-2?oldschool=1)
