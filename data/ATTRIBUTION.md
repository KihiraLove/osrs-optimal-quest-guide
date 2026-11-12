# Build 242 data attribution

The local JSON records factual identifiers, names, numeric XP thresholds and
original descriptions of findings. The data uses pinned upstream sources.

- Build and release facts come from Jagex release notes and the metadata for
  Jagex's archived build. Source locators are in [sources.json](sources.json).
- Museum plaque and camp waypoints use object coordinates from the archived
  build 242 map and IDs from RuneLite. Dean's OSRSGuide gameplay capture
  documents the quiz and Orlando Smith's reward visit.
- Balloon basket and storage tiles use the same archive and RuneLite IDs.
  First-flight helper observations use Quest Helper, with historical interface
  and fuel observations from Tip.It.
- The Port Sarim deposit box uses the archived object tile and RuneLite ID.
  Patrick Watts's Entrana plugin supplies evidence for the catalog's reviewed
  equipment restrictions. [Pinned source and license](https://github.com/pwatts6060/runelite-plugins/tree/07a86a771674c3a36ed49babc0c47c414c3a57db)
- Lost City combat planning uses Jagex's combat updates, RuneLite's base
  Fire Strike XP and NPC health observations, and the pinned Quest Helper
  dungeon sequence. The combat review records the differing health values
  and the project's rune reserves.
- Count Check's lamp uses Jagex's account security update. Stronghold
  room and exit waypoints come from the build 242 map and Quest Helper.
  Enjar's gameplay capture documents the early coin claims.
- Recipe for Disaster ingredient and instance observations come from the pinned
  Quest Helper. Tip.It's historical walkthrough documents the timing of the
  opening quest point. Jagex's Grand Exchange records supply price estimates.
- Fishing Contest and the Mountain Dwarf use pinned Quest Helper waypoints and
  RuneLite item IDs. The Fishing Contest review and timer inventory link to
  historical accounts of the trophy reward and rock cake cooling.
- Pirate Pete uses the pinned Quest Helper, RuneLite item and NPC metadata,
  and RuneLite's Cooking calculator. Tip.It records the historical dive
  sequence, and OSRS Guide documents the Fishing Trawler grouping teleport.
- Big Chompy Bird Hunting uses the pinned Quest Helper and Tip.It's historical
  walkthrough. Jagex's August 2026 Hunter update supplies the hunt XP.
  The Feldip ring tile comes from the pinned Shortest Path transport data.
- Skrach Uglogwee uses the pinned Quest Helper and Tip.It's historical
  sequence. The RuneLite calculators and NPC health snapshot support the
  incidental XP, and Shortest Path records the Karamja transport waypoints.
- Gertrude's Cat uses pinned Quest Helper and RuneLite IDs, an Old School
  RuneHQ walkthrough, and Shortest Path's fence and scroll tiles. Kitten
  Tracker supplies the follower growth and care observations.
- Demon Slayer uses pinned Quest Helper and RuneLite metadata, Slayermusiq1's
  speedrunning footage, Shortest Path's sewer tiles, and Jagex's update about
  the separate Aris lamps. Quest Helper tracks Evil Dave's random spice doses.
- The Golem uses pinned Quest Helper and RuneLite metadata, Slayermusiq1's
  Old School walkthrough, and Tip.It's historical gameplay observations.
  Shortest Path supplies the desert gate, D.L.Q. and Uzer carpet waypoints.
- The roster and XP curve use RuneLite's `Skill` and `Experience` sources.
  The journal inventory uses RuneLite's `Quest` enum (copyright 2019, Abex).
  Diary and museum tracker identities use RuneLite's generated game constants.
  [RuneLite BSD 2-Clause license](licenses/RuneLite-BSD-2-Clause.txt)
- Quest Helper supplies journal classifications and diary task tracker references.
  The diary ledger records the contributing copyright notices and exact file
  paths. [Quest Helper BSD 2-Clause license](licenses/QuestHelper-BSD-2-Clause.txt)

The stored facts and source locators are sufficient for the offline validator.
Release text, guide prose, client cache bytes and game artwork remain with
their respective sources.
