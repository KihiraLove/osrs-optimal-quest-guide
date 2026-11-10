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
