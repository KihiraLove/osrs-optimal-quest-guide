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
