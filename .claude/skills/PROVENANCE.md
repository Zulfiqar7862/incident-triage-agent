# Project-local skill provenance

The two skills in the first section are redistributed unmodified from the official
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

## Architecture skills (wshobson/agents, MIT)

Two further skills are redistributed unmodified from
https://github.com/wshobson/agents at commit
`9c61ab243def98f72da12abd41cfcf5bcd91af9d`. The upstream MIT `LICENSE`
(blob `326f0a55c96e672fedf9d807ca043c00df05ba0e`) is copied into each skill folder.

| Local path | Upstream path | Git blob |
| --- | --- | --- |
| `architecture-patterns/SKILL.md` | `plugins/backend-development/skills/architecture-patterns/SKILL.md` | `d893cabeab6a84c17bd0dd4ea9f56b3c4d02c0f5` |
| `architecture-patterns/references/details.md` | `.../architecture-patterns/references/details.md` | `7b98690c602ac710938c4f99f6c5fc612b3911ad` |
| `architecture-patterns/references/advanced-patterns.md` | `.../architecture-patterns/references/advanced-patterns.md` | `158b062807afbc0bd1778655ba412f24121d7872` |
| `architecture-decision-records/SKILL.md` | `plugins/documentation-generation/skills/architecture-decision-records/SKILL.md` | `c3170c4044880480f2c4c0ee8f2b3b3df1006f31` |
| `architecture-decision-records/references/decision-templates.md` | `.../architecture-decision-records/references/decision-templates.md` | `4ac5c42dc4426a5e0cc3239a2bfdb9f54dcad083` |
| `architecture-decision-records/references/deprecation-rfc-templates.md` | `.../architecture-decision-records/references/deprecation-rfc-templates.md` | `d80bbf91d10abf828c14a4f15b3e490bc296e446` |

Each file was checked against the blob IDs returned by the GitHub contents API
for that commit. The files are Markdown only: no scripts, hooks or installers.

How they were used:

- `architecture-patterns` guided the layer split (`domain` / `application` /
  `infrastructure` / `presentation` / `core`), the Protocol ports and the
  composition root. `tests/test_architecture.py` enforces the dependency rule.
- `architecture-decision-records` provided the MADR-style template used in
  [`docs/adr/`](../../docs/adr/README.md).
