# Future static viewer

Implementation is deliberately deferred until the optimizer's data and route
quality gates pass. This directory will be a separate frontend-only application
served by GitHub Pages, consuming a reviewed `solution.json` artifact.

Use `kihiras-tools-common` as a pinned Git submodule under `frontend/toolkit-common`
when implementation begins. Load `toolkit.css` before the viewer stylesheet and
use `mountToolkitHeader` / `mountToolkitFooter` from `toolkit.mjs`; keep the shared
skip-link target `<main id="main">`. Copy only static frontend assets into the
Pages deployment. No optimizer code, Python dependency or live game-data service
belongs in this application. No Pages workflow is enabled by this scaffold.
