# Build 242 fixtures

`cooks-assistant-profile.json` is a synthetic account at the cook's waypoint,
with the three required ingredients ready. Its goal is the real draft catalog
action. One completion should consume the ingredients, award 300 Cooking XP and
one quest point, and unlock the cook's range.

```sh
quest-optimizer validate-json profile examples/build-242/cooks-assistant-profile.json --catalog data/manifest.json
```

The [Recipe for Disaster progression review](../../data/raw/build-242/recipe-for-disaster-review.json)
contains the ten stages and the finale prerequisites. The runtime replay fixture
depends on resolving the review fields and adding those stages to the catalog.

The optional progression tests cover the three essence mine task flags in the
draft catalog. A synthetic fixture compares manual training with a diary task,
tier completion and NPC lamp claim that together meet the same quest goal.

`museum-quiz-profile.json` starts on the final quiz plaque with 98 kudos and
The Dig Site complete. The example finishes that plaque, claims Orlando's XP
and starts Bone Voyage at 100 kudos. The saved account is synthetic. The
catalog's museum and travel IDs are used throughout.

```sh
quest-optimizer validate-json solution examples/build-242/museum-quiz-solution.json --catalog data/manifest.json --profile examples/build-242/museum-quiz-profile.json
```

`balloon-travel-profile.json` starts after Enlightened Journey with a light
pack and enough logs for Varrock discovery and two ordinary flights. Its
solution discovers Varrock, flies to Taverley, then flies back to Varrock.
The last leg can be compared with the walk through Varrock square.

```sh
quest-optimizer validate-json solution examples/build-242/balloon-travel-solution.json --catalog data/manifest.json --profile examples/build-242/balloon-travel-profile.json
```
