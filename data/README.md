# Local game data

The draft catalog targets the Jagex live English build 242 snapshot archived on
11 November 2026 at 11:45:06 UTC. Dataset `0.41.0` loads 24 skill tables and
1,852 draft actions across 145 journal activities, the museum route and travel
networks.
Durations estimate each interaction at its
waypoint with supplies ready. Travel between
waypoints belongs to the travel graph. An action description identifies any
movement included in its duration.

[The coverage ledger](coverage/build-242.json) inventories identities
independently of the catalog. It links to the pinned journal, diary task, reward
review and optional activity lists. Later data batches reconcile their output
against these IDs. The ledger uses these statuses.

Use the [numbered activity tracker](../docs/activity-tracker.md) and
[achievement diary tracker](../docs/diary-tracker.md) to choose pending entries.
The [contributor guide](../docs/adding-activities.md) describes batch assignments,
catalog records and verification.

| Status | Meaning |
| --- | --- |
| `expected` | Identified from a source and awaiting normalized mechanics |
| `collected` | Present in the normalized catalog and checked by the validator |
| `reviewed` | Coverage and gameplay facts independently reviewed |
| `excluded` | Outside this route's scope, with a recorded reason |

The journal list preserves the client quest ID. Recipe for Disaster has one
parent goal and ten child activities in the
[stage review](raw/build-242/recipe-for-disaster-review.json). Another Cook's
Quest, Freeing the Goblin Generals, Freeing the Mountain Dwarf, Freeing
Pirate Pete, Freeing Skrach Uglogwee, Freeing Evil Dave and Freeing the
Lumbridge Guide have loaded quest actions, ingredients and travel. The parent
records saved finale completion without awarding its lamp or quest point
again. Three stages remain in review.

The [Fishing Contest review](raw/build-242/fishing-contest-review.json) records
Vestri's quest route, the contest fee and the tunnel that opens at the trophy
handover. The Mountain Dwarf rescue uses both tunnel entrances and can cool the
cake on pickup with ice gloves or after a successful Icefiend fight. The eastern
Fishing Contest route and passive cooling duration remain in review.

The [Pirate Pete review](raw/build-242/pirate-pete-review.json) records the
diving gear exchange before the rescue, the ballast used to enter each
grounded area, and the conditional combat and successful fishcake cook. The
successful cook credits 100 Cooking XP. The catalog includes a public walk
to Port Khazard, a Fishing Trawler grouping teleport from Lumbridge and
Lumbridge Teleport from the dock. The dive step states the loadout the player
must verify in game.

The [Big Chompy Bird Hunting review](raw/build-242/big-chompy-bird-hunting-review.json)
records Rantz's demonstration, the hunt and the roast. Rantz hands over the
ogre bow during the quest. The player's hunt credits the build 242 Hunter XP,
and the bow and charged bellows carry forward to Freeing Skrach Uglogwee.
The route can gather the seasonings in Feldip or buy them with carried coins.
It reserves all six possible seasonings because each ogre requests one of two
ingredients. The Feldip approach includes fairy ring A.K.S. and a surface walk
from Port Khazard.

The [Skrach Uglogwee review](raw/build-242/skrach-uglogwee-review.json) records
the fallen tree, signal fire and return ride with Bugs and Fycie. The route
can reach Karamja independently via Captain Barnaby or fairy ring C.K.R.
The hunt uses two bellows loads per balloon toad and the rescue awards
repeat boat access. The post-quest fares and burn recovery remain in review.

The [Gertrude's Cat review](raw/build-242/gertrudes-cat-review.json) records
the 100 GP fee, Fluffs' loft, the crate search and the return to Gertrude
for direct Cooking XP, a pet kitten, chocolate cake and stew. It also links
the two nearby Varrock diary tasks and records the nominal three-hour growth
clock while a kitten follows. Follower time and care remain in review for
the Evil Dave route.

The [Demon Slayer review](raw/build-242/demon-slayer-review.json) records the
three Silverlight keys, the Varrock Palace and sewer route, and the 25 unnoted
bones for Traiborn. Sir Prysin gives Silverlight before the Delrith encounter.
Aris's two post-quest combat lamps, Delrith's incidental combat XP, and the
Silverlight report for museum kudos remain in review.

The [Golem review](raw/build-242/the-golem-review.json) records the Uzer
repairs, museum statuette, phoenix feather and final program. It includes a
separate throne gem claim, the Shantay Pass approach, fairy ring D.L.Q., and
both Uzer carpet directions after completion. Desert heat, incidental
Thieving XP, and the related Desert Diary credits remain in review.

The [Shadow of the Storm review](raw/build-242/shadow-of-the-storm-review.json)
records the disguise, furnace, four possible tome locations and both ritual
orders. The fight converts dyed Silverlight into Darklight. The completion
dialogue grants one immediate 10,000 XP combat choice. The replay models a
successful fight and debits a food reserve. Incidental XP and the exact sigil
handovers remain in review.

The [Freeing Evil Dave review](raw/build-242/evil-dave-review.json) records the
Doris and Dave conversations, kitten and adult cat hunts, and one- and two-dose
taste tests. The route reserves nine plain stews and six doses of each colour,
then carries the approved bowl to the feast. It includes fairy ring D.K.R.
and a Lumbridge Teleport from the cellar. Behemoth access unlocks at completion.
Hunt durations, active follower growth and actual supply use remain in review.

The [western quest review](raw/build-242/western-quests-review.json) records
Witch's Potion, Witch's House, Murder Mystery, Plague City, Biohazard, Clock
Tower, Hazeel Cult and Sheep Herder. Plague City's scroll is a separate
unlock. Biohazard uses a continuous ferry and walking route with the fragile
sample. Clock Tower and Sheep Herder include their build 242 XP. Hazeel Cult
uses Clivet's branch. The alternate branch, incidental combat XP and earlier
guest access to Ardougne portals remain in review.

The [Morytania and starter quest review](raw/build-242/morytania-and-starter-quests-review.json)
covers Priest in Peril, Nature Spirit, In Search of the Myreque, Freeing the
Lumbridge Guide, Vampyre Slayer, Ernest the Chicken, Romeo & Juliet and
Pirate's Treasure. Priest in Peril uses two unnoted essence trips. Nature Spirit
provides the blessed sickle and pouch before the Myreque route. The two new
build 242 completion lamps are modeled as held items. Their exact retention
and skill restrictions, incidental XP and the repeat Myreque shortcut remain
in review.

[Quest Helper observations](raw/build-242/quest-helper/index.json) cover 209
journal activities. They identify candidate coordinates, requirements,
source-specific branches, items and rewards. The remaining helper gaps and
all uncollected entries are explicit in the inventory. The
[publisher reward changes](raw/build-242/quest-month-rewards.json) identify the
build 242 XP updates, including the separately claimed Demon Slayer reward.
The [reward registry](raw/build-242/reward-registry.json) records 39 reward
entries, including seven separate claims. Each claim records its producer ID,
quest gate, available location evidence and known award details. Null values
identify fields that need verification. X Marks the Spot, Shadow of the
Storm, Ernest the Chicken, Romeo & Juliet and Fairytale II have loaded reward
producers.
The remaining packages stay in review while their quest actions or use
rules are being collected.

[Diary observations](raw/build-242/diaries/index.json) link all 492 tracker IDs
to helper steps, requirements and item candidates across 48 tiers. Each tier
has a separate claim record with the taskmaster candidates, lamp values and
travel unlock references. The [optional progression review](raw/build-242/optional-progression-review.json)
tracks pending mechanics for all 19 miniquests, publisher corrections and the
overlap between diary tasks and the essence mine teleports in Enter the Abyss.
Three essence mine task flags and the two Stronghold tasks for Varrock are
loaded. Complete diary tiers and their claims remain in review.

The [museum review](raw/build-242/museum-review.json) links all 14 quiz plaques to
the [archived object tiles](raw/build-242/museum-map.json). Each plaque gives two
kudos and Orlando Smith separately awards 1,000 XP in Hunter and Slayer. The
draft Bone Voyage route checks 100 kudos and The Dig Site completion. The Dig
Site also unlocks specimen cleaning in the museum. Bone Voyage unlocks the
barge edges and walking routes to six camp facility sites. Clerk rewards, camp
construction, additional travel activations, and fossil acquisition and exhibits
are in gameplay review.

[Balloon stop observations](raw/build-242/balloon-stops.json) record the six
build 242 basket locations and the fuel and skill requirements of discovery.
The draft graph includes four post-quest discovery actions, 30 directed
regular flights, the Entrana ferry, public walks, and one-way Varrock tablet
edges. Read the [travel assumptions](raw/build-242/travel-timing.json) for
packing and timing and the [network review](raw/build-242/travel-review.json)
for open acquisition and transport mechanics.

[Sources](sources.json) records provenance and reuse terms. See
[attribution](ATTRIBUTION.md) for the third-party notices and
[reconciliation](raw/build-242/reconciliation.json) for field-level decisions.
A pending review preserves its evidence and reason until a verified value is
available. The [main baseline](profiles/main-baseline.json) records the goal
list, policies and modeled Lumbridge arrival with one quest point. The
[self-funded economy](catalog/starter-economy/actions.json) models bank
withdrawal, one sale and purchases with carried coins. Price observations
are in the [starter economy record](raw/build-242/starter-economy.json).
The [account security record](raw/build-242/account-security.json) documents
the Jagex account, bank PIN and authenticator assumptions. Walking to the
Stronghold opens up to 10,000 GP across the first three rooms. Its four emotes
support the Varrock Medium task. Count Check offers a one-time lamp in
Lumbridge Graveyard worth ten times the chosen skill's base level at use.

The [Troll and Keldagrim review](raw/build-242/troll-and-keldagrim-review.json)
covers eight quests, the separate Kelda growth and fermentation timers,
Trollheim Teleport, the Keldagrim minecarts and the Dorgesh-Kaan railway.

The [Temple Knights and Lumbridge review](raw/build-242/temple-knights-and-lumbridge-review.json)
covers eight quests, the Black Knights’ Fortress lamps, Recruitment Drive banking,
the Dorgeshuun tunnel network, Guardians of the Rift access, and Daddy’s Home’s
house and crate rewards. Recruitment Drive’s restricted-item list covers every
item in this catalog version.

The [Kourend and Varlamore review](raw/build-242/kourend-and-varlamore-review.json)
covers eight quests, Client of Kourend’s two lamps, the five memoir pages and
their shared charge pool, paid and free minecarts, Primio’s first arrival and
Renu’s quest flight. It also records regular quetzal flights and spell, tablet,
fairy ring and public house travel.

The [Kandarin, Camelot and Dig Site review](raw/build-242/kandarin-camelot-and-digsite-review.json)
covers eight quests, the Dig Site dependency for Bone Voyage, the Corsair Cove
ferry, gnome gliders and the Fisher Realm. Observatory Quest credits its fixed
Crafting XP and quest points. The randomized constellation rewards are omitted.

The [Fairytale and Kandarin review](raw/build-242/fairytale-and-kandarin-review.json)
covers both Fairytale quests, Jungle Potion, Fight Arena, Tree Gnome Village,
Waterfall Quest, Sea Slug and The Knight's Sword. It records the conditional
secateurs ingredients, Glarial's Tomb banking and the spirit-tree hub.

[The Fairytale II review](raw/build-242/fairytale-ii-review.json) records the
five-minute Martin stage and the early Godfather conversation. The complete
Fairytale I route produces the flag for that conversation's quest chain.
The Farming, Herblore and Thieving checks occur later, on the queen's route.

The [Lost City review](raw/build-242/lost-city-review.json) records the
Lumbridge Swamp start, the Entrana dungeon descent, the branch and staff skill
checks, and the first entry into Zanaris. The [Entrana loadout record](raw/build-242/entrana-loadout.json)
documents the reviewed item restrictions and the Port Sarim deposit box tile.
Ferry and balloon arrivals check the current pack. Banked gear can be retrieved
at Lumbridge Castle. The [Lost City combat review](raw/build-242/lost-city-combat.json)
records two conditional Fire Strike steps. The forecast debits each rune
reserve and credits a floor on base cast XP. Reconcile runes and XP with the
observed state before replanning. The funded fixture starts at Lumbridge with
saved levels and uses the first two Stronghold payouts to buy supplies. The preparation and saved
post-combat fixtures remain available for those route segments.

The [timer inventory](raw/build-242/progression-timers.json) lists the step
blocked by each timer. Martin's timer runs in the catalog. Garden of
Tranquillity, the white-tree fruit diary task, Forgettable Tale and Rum Deal
still need their progression and travel records admitted.

The [standard teleport edges](catalog/standard-teleports/travel_edges.json)
cover selected origins for Varrock, Lumbridge and Falador. Casts require the
standard spellbook, carried runes and the spell's Magic level. The three
public house portals from Rimmington use the World 330 host assumption.

[The Restless Ghost review](raw/build-242/restless-ghost-review.json) records the
amulet and skull pickups, the route that leaves the skeleton behind, and the
Prayer XP and quest point at the coffin. It also records the remaining gameplay
checks for the waypoint and duration estimates.

The [Morytania and garden review](raw/build-242/morytania-and-garden-review.json)
records seven quests and Tarn's Lair. It includes separate crop and fruit
readiness checks, Port Phasmatys fares, the Ectophial, and the optional Salve
amulet crafts. The recurring Tears of Guthix XP claim and exact growth timings
remain in review.

The [pirates and Myreque review](raw/build-242/pirates-and-myreque-review.json)
records the pirate chain through Harmony Island, the Burgh de Rott repairs,
Tolna's rift, the first bone list and Skippy. It includes overlapping
blindweed growth, two diary tasks and separate post-quest reward claims.

The [Fremennik and Kandarin review](raw/build-242/fremennik-and-kandarin-review.json)
records eight quests, including both Fremennik lyre routes, the Isles bridges,
Waterbirth and Miscellania travel, the two Elemental Workshops, and the
Rellekka coal and brine rat diary tasks.

The [Misthalin and Kandarin review](raw/build-242/misthalin-and-kandarin-review.json)
records eight quests, both Shield of Arrav gang routes, the Al Kharid gate and
Foundry travel, the What Lies Below museum report, and Bert's first sand
claim for the Ardougne diary.

The [Kebos, desert and Kandarin review](raw/build-242/kebos-desert-and-kandarin-review.json)
records seven quests and Alfred Grimhand's Barcrawl, the Tourist Trap XP
selections, five Slug Menace altars and four Desert diary tasks.

The [Quest Month weeks one and two review](raw/build-242/quest-month-week-two-review.json)
records the four November quests, their rewards and the journal changes between
the two build 242 archives.

The [Lumbridge and Varlamore review](raw/build-242/lumbridge-and-varlamore-review.json)
records seven quests and the Vale Totems tutorial, plus the Cowbell teleport,
Aldarin ferry and Costume needle claim.

The [Varrock, Lighthouse and Kourend review](raw/build-242/varrock-lighthouse-and-kourend-review.json)
records three quests and three miniquests, plus separate gauntlet and god book
claims, the Abyss Law rift and the Forthos lamp.

The [Glouphrie, Barrows and Museum review](raw/build-242/glouphrie-barrows-and-museum-review.json)
records two journal routes, the crystal saw diary task, the Museum Camp
facilities and Peter's fossil claim, four Minas reports and the three Varrock
Museum clerk rewards.

The [Ikov, Mage Arena and specimen review](raw/build-242/ikov-arena-and-specimens-review.json)
records two journal routes, five Museum specimen exhibits, and the Digsite
pendant and its Varrock Medium diary task. It also connects the Woodcutting
Guild gate and potion supplies needed to finish Bone Voyage.
