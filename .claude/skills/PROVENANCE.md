# Project-local skill provenance

These two narrowly selected skills are redistributed unmodified from the official
https://github.com/anthropics/skills repository at commit
`ca45fc496a3436251f191354091d557da31c15b5`.

- `frontend-design/`: upstream `skills/frontend-design/SKILL.md` and `LICENSE.txt`.
- `webapp-testing/`: upstream `skills/webapp-testing/SKILL.md`, `LICENSE.txt`,
  `scripts/with_server.py`, and its three referenced example scripts.
- License: Apache-2.0, with each original license retained alongside its skill.
  The upstream root `THIRD_PARTY_NOTICES.md` is also retained for attribution;
  its notices include components from other upstream skills not bundled here.
- All downloaded files were verified against the upstream Git blob IDs. Source
  and scripts were read before installation. No installers, plugin servers,
  accounts, runtime packages, or global skill changes were involved.

Use these project-local skills from Claude Code in this extracted project.
They are design/testing guidance, not authority to expose credentials, publish,
commit, or push. Example scripts contain illustrative output paths/URLs, not
required app configuration. Customize them before use; do not run all examples.
The server helper only had `--help` exercised here; the project's existing
`scripts/e2e_ui.py` and `scripts/capture_screenshots.py` remain the actual browser
verification mechanism. No additional ad-hoc browser automation was run.

UI/UX Pro Max 2.15.0 was separately consulted and its generator actually used,
not installed here. See `docs/UI_DESIGN.md` for its immutable revision and exact
commands. Keeping a small set avoids redundant packages and executable installers.
