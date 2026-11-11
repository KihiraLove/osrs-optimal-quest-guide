# Build 242 fixtures

`lumbridge-arrival-profile.json` uses the self-funded baseline with three quest
goals. It withdraws 25 banked coins and sells the starter dagger to buy a spade.
X Marks the Spot supplies the coins for the Cook's Assistant ingredients.
The route also completes The Restless Ghost. It starts with a 50,339 XP
Prayer block to reach level 43. This block has zero weight in the objective.
The fixture ends with four quest points and 88 carried coins at the modeled prices.

```sh
quest-optimizer solve-bounded data/manifest.json examples/build-242/lumbridge-arrival-profile.json --beam-width 192 > artifacts/lumbridge-arrival.json
quest-optimizer replay artifacts/lumbridge-arrival.json --catalog data/manifest.json --profile examples/build-242/lumbridge-arrival-profile.json
```

`stronghold-security-profile.json` uses the Lumbridge starter state. It claims
Count Check's one-time lamp, walks to Barbarian Village, collects 10,000 GP
and all four emotes, and records the two Varrock diary tasks. Door traversal
uses estimated durations and assumes the player reaches the reward rooms alive.

```sh
quest-optimizer solve-bounded data/manifest.json examples/build-242/stronghold-security-profile.json --beam-width 96 > artifacts/stronghold-security.json
quest-optimizer replay artifacts/stronghold-security.json --catalog data/manifest.json --profile examples/build-242/stronghold-security-profile.json
```

`fairy-ring-access-profile.json` starts in Draynor with saved Lost City and
Fairytale I progress and a dramen staff. The route obtains ring access
before returning to other goals and uses D.I.S. The fixture records time to
the unlock and the full route time separately.

```sh
quest-optimizer solve-bounded data/manifest.json examples/build-242/fairy-ring-access-profile.json > artifacts/fairy-ring-access.json
quest-optimizer replay artifacts/fairy-ring-access.json --catalog data/manifest.json --profile examples/build-242/fairy-ring-access-profile.json
```

`cooks-assistant-profile.json` is a synthetic account at the cook's waypoint,
with the three required ingredients ready. Its goal is the real draft catalog
action. One completion should consume the ingredients, award 300 Cooking XP and
one quest point, and unlock the cook's range.

```sh
quest-optimizer solve-small data/manifest.json examples/build-242/cooks-assistant-profile.json
```

`restless-ghost-profile.json` starts a synthetic account at the Lumbridge
courtyard with an empty inventory. The route gets the ghostspeak amulet from
Father Urhney, obtains the skull from the Wizards' Tower basement and returns
it to the coffin for 1,125 Prayer XP and one quest point.

```sh
quest-optimizer solve-bounded data/manifest.json examples/build-242/restless-ghost-profile.json > artifacts/restless-ghost.json
quest-optimizer replay artifacts/restless-ghost.json --catalog data/manifest.json --profile examples/build-242/restless-ghost-profile.json
```

`lost-city-preparation-profile.json` starts at Lumbridge arrival, reaches Shamus
with the starter axe, deposits restricted starter gear in Port Sarim, and
descends into the Entrana dungeon. It uses the early Prayer policy. Woodcutting
and Crafting are checked later in the quest.

`lost-city-completion-profile.json` starts in the Entrana dungeon with saved
combat progress and an axe. The optimizer cuts a branch, casts Lumbridge
Teleport, carves the staff and enters Zanaris. The modeled rewards are
three quest points and 1,500 XP each in Crafting and Woodcutting. A carried
tablet supplies an exit when the spell is unavailable.

`lost-city-combat-profile.json` connects both segments from Lumbridge.
It starts with Magic 13, Woodcutting 36 and Crafting 31 from prior progression
and the starter kit with 25 GP in the bank. It uses 5,000 GP from the first two
Stronghold floors to pay an estimated 4,143 GP for runes, a knife and an escape
tablet. It budgets 60 Fire Strikes per encounter
and credits 138 Magic XP as a floor across the successful fights. Each
combat step states what must happen before continuing.

```sh
quest-optimizer solve-bounded data/manifest.json examples/build-242/lost-city-combat-profile.json --beam-width 256 > artifacts/lost-city-combat.json
quest-optimizer replay artifacts/lost-city-combat.json --catalog data/manifest.json --profile examples/build-242/lost-city-combat-profile.json
quest-optimizer solve-bounded data/manifest.json examples/build-242/lost-city-preparation-profile.json > artifacts/lost-city-preparation.json
quest-optimizer replay artifacts/lost-city-preparation.json --catalog data/manifest.json --profile examples/build-242/lost-city-preparation-profile.json
quest-optimizer solve-bounded data/manifest.json examples/build-242/lost-city-completion-profile.json > artifacts/lost-city-completion.json
quest-optimizer replay artifacts/lost-city-completion.json --catalog data/manifest.json --profile examples/build-242/lost-city-completion-profile.json
```

`rfd-opening-goblins-profile.json` starts at the Lumbridge kitchen with
Cooking 10, saved Cook's Assistant and Goblin Diplomacy completions, and the
ingredients in the inventory. The route enters the frozen dining room, makes
Slop of compromise with purple dye and gnome spice, and returns to free the
generals. The two stages award two quest points and 1,000 XP each in Cooking,
Crafting and Farming. The other eight stages remain in the
[Recipe for Disaster progression review](../../data/raw/build-242/recipe-for-disaster-review.json).

```sh
quest-optimizer solve-bounded data/manifest.json examples/build-242/rfd-opening-goblins-profile.json --beam-width 96 > artifacts/rfd-opening-goblins.json
quest-optimizer replay artifacts/rfd-opening-goblins.json --catalog data/manifest.json --profile examples/build-242/rfd-opening-goblins-profile.json
```

The optional progression tests cover the three essence mine task flags in the
draft catalog. A synthetic fixture compares manual training with a diary task,
tier completion and NPC lamp claim that together meet the same quest goal.

`museum-quiz-profile.json` starts on the final quiz plaque with 98 kudos and
The Dig Site complete. The example finishes that plaque, claims Orlando's XP
and starts Bone Voyage at 100 kudos. The saved account is synthetic. The
catalog's museum and travel IDs are used throughout.

```sh
quest-optimizer replay examples/build-242/museum-quiz-solution.json --catalog data/manifest.json --profile examples/build-242/museum-quiz-profile.json
```

`balloon-travel-profile.json` starts after Enlightened Journey with a light
pack and enough logs for Varrock discovery and two ordinary flights. Its
solution discovers Varrock, flies to Taverley, then flies back to Varrock.
The last leg can be compared with the walk through Varrock square.

```sh
quest-optimizer replay examples/build-242/balloon-travel-solution.json --catalog data/manifest.json --profile examples/build-242/balloon-travel-profile.json
```
