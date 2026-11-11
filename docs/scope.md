# Scope and decisions

## Target and account

The default target is completion of every in-scope normal-mode OSRS quest in a
reviewed, versioned catalog. Miniquests, diaries and other activities are optional enabling
actions unless a target explicitly includes them. Do not require every diary just
because diaries are in the data. Quest completion is a goal expression over final
actions, not a hard-coded quest count or quest-point total.

The default members main starts at the Lumbridge Castle courtyard on arrival
from Tutorial Island. Learning the Ropes sits outside the route and its one quest
point is credited in the starting counter. The model uses level 10 Hitpoints,
zero XP in other skills and an empty inventory. The
[build 242 baseline](../data/profiles/main-baseline.json) records these assumptions
and all in-scope quest goals. Existing accounts can supply their own state in JSON.

Tradeable supplies may be acquired using an explicit abstract supply action at
configured supply locations. The default assumes sufficient GP; this does not
make untradeable items, quest progress, spellbooks, transport unlocks or use
requirements free. Record quantities and acquisition overhead; GP is informational
under this profile. A future budgeted scenario requires additional state/search.
Shared/player-owned-house services, assistance, minigame teleports, Wilderness
travel, death travel and world switching each require explicit profile policy.
No blanket assumption that a player-owned house or another player's unlocks exist.

## Objective agreed with the user

Minimise lexicographically:

1. `manual_training_xp`: sum of actual XP gains requested in explicit training
   steps across all skills. Every XP point has equal weight in this default policy.
2. `modeled_non_training_seconds`: activity execution + reward-claim visits +
   transport unlock/setup + travel + modelled supply handling and waits.
3. A stable lexicographic action/choice identifier sequence.

Do not substitute training time, XP/hour or recommended methods for the primary
objective. XP is retained exactly; levels are derived from JSON XP thresholds.
An output training block states the skill, XP before, XP to gain, XP after and the
gate it satisfies. A player may overshoot; recalculating for changed XP is future
work. No method, price-per-XP, rate or training location is prescribed.

The training abstraction resumes at the listed route waypoint after the player
trains however they choose. Time, location changes, incidental XP, consumables and
unlocks caused by that personal method are outside the baseline model. The viewer
must disclose this boundary. The optimizer may not invent incidental training XP
to satisfy another skill requirement.

This objective can select a long detour to save a small amount of manual XP. That
is intentional. Report both objectives, per-skill manual XP and detour costs so
the trade-off is visible. “Quest XP first” is a global search objective, not a
greedy rule that always picks any currently available XP quest.

## Lamps and other rewards

The requested default policy is `quest_lamp_skill_policy: any_skill`: quest lamps
may be assigned to any catalog skill. Keep observed eligibility restrictions in
the source data and flag any overridden skill restriction in the output. Do not
silently present that relaxation as verified in-game behaviour. A future strict
profile can use `observed` eligibility. Minimum levels, quantity, indivisibility,
claim time and retainability still need explicit data. Diary/non-quest reward
eligibility uses observed rules unless separately specified.

Model awarding a lamp, holding it and consuming it separately. Choice sets cannot
be summed together. Level-dependent XP uses a local lookup table or a versioned,
declarative formula; no executable strings in JSON. Quest completion, optional NPC
training, follow-up dialogue, books and museum claims are separate actions when
they are separately claimable. Each one-time reward has exactly one producer.

## Bounded scope

Normal main accounts only; exclude Ironman, Leagues, Deadman and temporary modes.
Exclude random events and unbounded repeatable/daily/weekly XP from the default
finite quest route. Candidates such as Tears of Guthix, repeatable museum work,
fossils and waiting for passive processes need a documented finite horizon,
acquisition model and one-time caps before admission. Otherwise they can turn
“minimise manual XP” into an indefinite wait or free XP exploit.

Required combat is represented by reviewed feasibility requirements and explicit
mandatory XP where reliably known. Do not equate a nominal combat level with a
guarantee that a player can beat a boss. Conservative combat assumptions and any
uncertain incidental XP belong in the profile/output limitations. Boosts must be
explicit, consumed when applicable and allowed only at boostable checks.

The first version is not a full game engine, tile-perfect navigator, real-time
price feed, shopping assistant or training-method recommender. No frontend or
Pages deployment is built until the data and route quality gates pass.
