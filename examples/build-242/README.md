# Build 242 fixtures

`lumbridge-arrival-profile.json` uses the self-funded baseline with three quest
goals. It withdraws 25 banked coins and sells the starter dagger to buy a spade.
X Marks the Spot supplies the coins for the Cook's Assistant ingredients.
The route also completes The Restless Ghost. It ends with zero manual XP,
four quest points and 88 carried coins at the modeled prices.

```sh
quest-optimizer solve-bounded data/manifest.json examples/build-242/lumbridge-arrival-profile.json > artifacts/lumbridge-arrival.json
quest-optimizer replay artifacts/lumbridge-arrival.json --catalog data/manifest.json --profile examples/build-242/lumbridge-arrival-profile.json
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

The [Recipe for Disaster progression review](../../data/raw/build-242/recipe-for-disaster-review.json)
contains the ten stages and the finale prerequisites. A replay test uses
the recorded finale gates and quest points with synthetic waypoints and
durations. A full in-game route fixture depends on resolving the review
fields and adding those stages to the catalog.

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
