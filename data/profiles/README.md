# Account profiles

The [build 242 main baseline](main-baseline.json) starts a trade-enabled members
main at the Lumbridge Castle courtyard with one quest point. Learning the
Ropes is recorded as excluded in the journal ledger. The modeled inventory
is empty, with 1,154 base Hitpoints XP and zero XP in all other skills.
The courtyard is the existing walking waypoint for the Lumbridge arrival area.
[Jagex tutorial release notes](https://secure.runescape.com/m=news/grid-master-rewards-poll--new-player-improvements?oldschool=1)

The baseline lists every in-scope quest goal. It passes standalone profile
validation. Catalog validation and a full run depend on the remaining quest
actions. The [starter profile](../../examples/build-242/lumbridge-arrival-profile.json)
uses the same state and policies and targets four modeled quests.

To plan for an existing account, supply its own `initial_state` with exact
XP in tenths, a catalog waypoint, inventory, progress, and any active timers.
Use `validate-json profile --catalog` to check the values against the catalog.
