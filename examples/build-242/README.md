# Build 242 fixtures

`lumbridge-arrival-profile.json` uses the self-funded baseline with three quest
goals. The saved route uses the first Stronghold of Security reward to buy a
spade and the Cook's Assistant ingredients. It completes Cook's Assistant,
The Restless Ghost and X Marks the Spot. It starts with 50,339 Prayer XP to
reach level 43. That XP has zero weight in the objective. The bounded search
uses the saved route as its starting incumbent.

```sh
cp examples/build-242/lumbridge-arrival-solution.json artifacts/lumbridge-arrival-incumbent.json
quest-optimizer solve-bounded data/manifest.json examples/build-242/lumbridge-arrival-profile.json --beam-width 144 --max-expansions 60000 --incumbent artifacts/lumbridge-arrival-incumbent.json > artifacts/lumbridge-arrival.json
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
Crafting and Farming. Progress on the other stages is recorded in the
[Recipe for Disaster progression review](../../data/raw/build-242/recipe-for-disaster-review.json).

```sh
quest-optimizer solve-bounded data/manifest.json examples/build-242/rfd-opening-goblins-profile.json --beam-width 96 > artifacts/rfd-opening-goblins.json
quest-optimizer replay artifacts/rfd-opening-goblins.json --catalog data/manifest.json --profile examples/build-242/rfd-opening-goblins-profile.json
```

`rfd-mountain-dwarf-profile.json` starts at Vestri with Fishing 10, saved
banquet access, supplies and 326 GP. The route wins Fishing Contest, uses the
tunnel and pays for the Asgoldian ale recipe and rock cake. It assumes a
successful solo Icefiend fight with a bronze shortsword to cool the cake. The
fixture carries four shrimps and leaves actual food use to the encounter.

```sh
quest-optimizer solve-bounded data/manifest.json examples/build-242/rfd-mountain-dwarf-profile.json --beam-width 128 --max-expansions 40000 > artifacts/rfd-mountain-dwarf.json
quest-optimizer replay artifacts/rfd-mountain-dwarf.json --catalog data/manifest.json --profile examples/build-242/rfd-mountain-dwarf-profile.json
```

`rfd-pirate-pete-profile.json` starts at the Grand Exchange with the banquet
open, Fishing Contest complete, Cooking and Magic 31, prepared melee stats
and 1,194 GP. The route purchases supplies, reaches Murphy via the Fishing
Trawler grouping teleport, and climbs the anchor to return to the dock. The
forecast assumes successful combat and a successful first fishcake cook.

```sh
quest-optimizer solve-bounded data/manifest.json examples/build-242/rfd-pirate-pete-profile.json --beam-width 128 --max-expansions 40000 > artifacts/rfd-pirate-pete.json
quest-optimizer replay artifacts/rfd-pirate-pete.json --catalog data/manifest.json --profile examples/build-242/rfd-pirate-pete-profile.json
```

`big-chompy-bird-hunting-profile.json` starts at the Grand Exchange after
Fishing Contest with Cooking and Ranged 30, Fletching 5 and 2,016 GP. The
route budgets six arrows for Rantz and eight for the player's hunt. It gathers
the six possible seasonings in Feldip and keeps the ogre bow and one remaining
bellows load after the quest. The quest reward raises the fixture to Cooking 31.
The saved itinerary keeps the replay independent of the bounded search budget.

```sh
quest-optimizer replay examples/build-242/big-chompy-bird-hunting-solution.json --catalog data/manifest.json --profile examples/build-242/big-chompy-bird-hunting-profile.json
```

`rfd-skrach-uglogwee-profile.json` starts at the Grand Exchange after the
banquet and Big Chompy Bird Hunting. It carries the ogre bow, a one-load
bellows and 3,239 GP. The saved itinerary buys supplies, pays Captain Barnaby
to reach Karamja, and uses the children's quest ride to return to Feldip.
The forecast uses two gas loads for the bait and assumes the signal roast,
hunt and final roast succeed. Fresh bounded searches can insert extra walks
while the Fishing Trawler cooldown runs. The saved itinerary gives a verified
route for replay or for use as an incumbent.

```sh
quest-optimizer replay examples/build-242/rfd-skrach-uglogwee-solution.json --catalog data/manifest.json --profile examples/build-242/rfd-skrach-uglogwee-profile.json
```

`gertrudes-cat-profile.json` starts at the Grand Exchange with one quest
point and 150 GP. The route buys the sardine and milk, gathers a doogle leaf
and pays the children 100 GP. It visits Fluffs upstairs, retrieves her kittens
from a crate and returns to Gertrude for the pet kitten and 1,525 Cooking XP.

```sh
quest-optimizer solve-bounded data/manifest.json examples/build-242/gertrudes-cat-profile.json --beam-width 96 > artifacts/gertrudes-cat.json
quest-optimizer replay artifacts/gertrudes-cat.json --catalog data/manifest.json --profile examples/build-242/gertrudes-cat-profile.json
```

`demon-slayer-profile.json` starts at the Grand Exchange with an empty bucket,
one quest point and 1,176 GP. The route buys 25 unnoted bones, pays Aris,
recovers all three keys and trades them for Silverlight. The Delrith encounter
assumes a successful melee fight and awards three quest points at banishment.

```sh
quest-optimizer solve-bounded data/manifest.json examples/build-242/demon-slayer-profile.json --beam-width 96 > artifacts/demon-slayer.json
quest-optimizer replay artifacts/demon-slayer.json --catalog data/manifest.json --profile examples/build-242/demon-slayer-profile.json
```

`the-golem-profile.json` starts at the Grand Exchange with Crafting 20,
Thieving 25, four filled waterskins, a hammer, a chisel and 905 GP. The route
spends 705 GP on materials and two passes, claims six throne gems and finishes
the quest. The remaining 200 GP covers a carpet ride. The replay treats
waterskins as packed supplies and leaves charge depletion in review.

```sh
quest-optimizer solve-bounded data/manifest.json examples/build-242/the-golem-profile.json --beam-width 128 --max-expansions 40000 > artifacts/the-golem.json
quest-optimizer replay artifacts/the-golem.json --catalog data/manifest.json --profile examples/build-242/the-golem-profile.json
```

`shadow-of-the-storm-profile.json` starts after Demon Slayer and The Golem
with Crafting 30 and prepared combat stats. It supplies 1,731 GP for the
disguise, silver bar, food reserve and desert travel.
It assumes successful combat, transforms Silverlight into Darklight and
resolves the 10,000 XP choice at completion.

```sh
quest-optimizer solve-bounded data/manifest.json examples/build-242/shadow-of-the-storm-profile.json --beam-width 128 --max-expansions 40000 > artifacts/shadow-of-the-storm.json
quest-optimizer replay artifacts/shadow-of-the-storm.json --catalog data/manifest.json --profile examples/build-242/shadow-of-the-storm-profile.json
```

`rfd-evil-dave-profile.json` starts after the opening, Gertrude's Cat and
Shadow of the Storm with Gertrude's kitten and stew. The route spends 1,362 GP
on eight stews and two sardines. It budgets six spice doses per colour, gets
Dave's approval and casts Lumbridge Teleport from the cellar. It awards 7,000
Cooking XP with no additional training. Hunt duration and care are estimates.
The saved kitten route checks the quest mechanics independently of the bounded
search budget.

```sh
quest-optimizer replay examples/build-242/rfd-evil-dave-solution.json --catalog data/manifest.json --profile examples/build-242/rfd-evil-dave-profile.json
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
