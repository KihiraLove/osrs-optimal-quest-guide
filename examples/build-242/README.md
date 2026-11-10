# Build 242 fixture

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
