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

The documented starting boundary credits Learning the Ropes and one quest point.
A different tutorial path can yield different XP. The recorded profile should
name the observed path so the exact starting values are reproducible.
