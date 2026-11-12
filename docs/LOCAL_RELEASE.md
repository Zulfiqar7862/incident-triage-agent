# Source release notes

> Historical record. File paths here predate the layered restructure of 2026-11-12; see the [LLD](LLD.md#1-project-structure) for the current layout.

Baseline: `2096a05` on `main`, two existing commits ahead of `origin/main`.
The original ZIP snapshot included the complete tracked/untracked working-tree
refactor, assignment alignment, UI changes and project-local skills before
publication. It was prepared without committing or pushing. The owner subsequently
authorized committing and normally pushing these final changes to the existing
repository. No reset, rebase, force-push, or PR is part of that publication. The ZIP
has no Git history. For a Git checkout use the clone/install commands in README; use
[LOCAL_SETUP.md](LOCAL_SETUP.md) to install and test after extraction.

## What changed

- Domain policy/labels/ports; focused write-gate application helper and infrastructure
  factories; frontend run-data/action hooks. Runtime remains a compatibility facade;
  a full lifecycle rewrite was intentionally not attempted.
- Operator presentation is now a read-only typed projection in
  `app/presentation/operator.py`. Numeric measurements, observed releases, scoped
  service/version fields and applied-action records become plain readable facts.
  Free-form model text, log lines, raw queries and backend errors are never
  operator copy. No regex-based "English cleaner" or frontend humanizer is used.
- API snapshots, persisted event replay and SSE use the same projection. Event
  `operator` fields are outside the original hash-chained `payload`. Raw evidence,
  diagnoses, edited approval arguments and rejection feedback remain available for
  audit/context inspection; original stored payloads/hashes are not rewritten.
- Evidence-first approval: what was checked → proposed operation → scope → impact/
  risk → approve/edit/reject. The real restore operation is preserved as **Restore
  the previous version**. No repeated waiting cards, model thought blobs,
  checkpoint labels or stale retry/thinking states. Actual confidence is labeled
  as the agent's assessment, not a safety guarantee. Cause is not presented as
  independently confirmed when it is only free-form model reasoning.
- Separate **For engineers** disclosure for original proposals/reports/plans and
  context access; raw evidence is never interspersed in readable cards. Unknown
  display data fails closed with a truthful missing-structured-evidence fallback.
- Local skills: official `frontend-design` and `webapp-testing` at commit
  `ca45fc496a3436251f191354091d557da31c15b5` (Apache-2.0). Files are upstream originals,
  hash-verified, reviewed, and licensed locally; no remote installer/global change.
  UI/UX Pro Max 2.15.0 was consulted/generated separately, not installed. See
  `.claude/skills/PROVENANCE.md` and `UI_DESIGN.md` for exact sources/application.
- Setup documentation corrects the offline default and supported tool versions.
  `.env.example` contains blank secret fields, no actual credentials. The AI
  assistance document explicitly remains a summary, not a complete transcript.

## Final working-tree verification

All commands run locally; no CI pipeline was triggered remotely.

| Gate | Result |
| --- | --- |
| `ruff check app tests evals scripts` | Pass |
| `ruff format --check app tests evals scripts` | Pass, 69 files |
| `mypy -p app` | Pass, 54 source files |
| `TOOL_BACKOFF_S=0.01 pytest -q -m 'not live'` | 58 passed, 1 deselected |
| `TOOL_BACKOFF_S=0.01 python -m evals.run_evals --provider scripted` | 3/3 passed |
| frontend `npm run lint` | Pass |
| frontend `npm run typecheck` | Pass |
| frontend `npm test` | 31 passed, 10 files |
| frontend `npm run build` | Pass |
| `TOOL_BACKOFF_S=0.01 SCRIPTED_DELAY_S=0.12 python -m scripts.e2e_ui` | Pass |
| `python -m scripts.capture_screenshots` | Pass |
| `git diff --check` | Pass |
| frontend `npm run format:check` | Known baseline failure: 8 untouched files |

Use `.venv/bin/` for Python tools as shown in LOCAL_SETUP. The live Gemini test
was deliberately excluded. Docker was not built. Pytest reports the existing
unset asyncio fixture-loop setting and Sentry deprecations; intermittent
aiosqlite worker teardown warnings (`Event loop is closed`) still occur. These
warnings are not represented as resolved by this release.

The E2E flow exercises message, edited approval, pending reload/SSE replay,
resolution, pause/resume, rejection and cancellation, plus keyboard navigation
and explicit assertions against raw code/log strings. It reports no console
warnings or page/console errors. Screenshot capture reports no unexpected errors
or horizontal overflow; its intentional missing-run page produces four reported
404 resource messages. Approval captures cover 375/768/1024/1440px and the 390px
resolved capture uses reduced motion. The historical MP4 was not refreshed and
is excluded from the source archive; PNGs/GIF were refreshed and reviewed.

All frontend files now pass `npm run format:check` (Prettier); CI runs that check in the frontend job.

## Boundaries and limitations

- Simulated platform tools only, even when using a live LLM. No production cluster
  access is claimed. Live model correctness/cost/rate limits are not offline-tested.
- Arbitrary model diagnosis/questions cannot be safely inferred from raw text;
  full original reasoning/question is retained for explicit engineering review.
- Single-process run ownership, self-declared operator identity and local
  tamper-evident—not tamper-proof—audit storage remain as documented in README.
- Source archive omits `.git`, `.env`/credentials, installed environments, dependency
  trees, caches, databases/runtime data, frontend build output, and large videos.
  Package locks, migrations, tests, docs/screenshots, skills/licenses are included.
- Secret scanning is a best-effort path plus known-token/private-key/signature and
  example secret-assignment scan, not a guarantee against every possible secret format.

## Clean extraction validation

The source archive was extracted to a new directory with no `.git`, `.env`,
`.venv`, `node_modules`, or prebuilt frontend output. A fresh Python venv with
`pip install -r requirements-dev.txt` and a fresh `npm ci` both succeeded. From
that extracted source: backend Ruff/format/mypy, 58 offline pytest tests, all three
scripted evals, frontend lint/typecheck/31 tests/build, and the full UI E2E passed.
The E2E used the host's existing Playwright Chromium cache/system libraries;
that OS/browser dependency was not reinstalled in a separate machine/container.
ZIP CRC, safe archive paths, required file presence and byte-for-byte extraction
were verified; `SOURCE_MANIFEST.sha256` records every included source file.

`npm ci` also reported **three moderate dependency-audit findings**:
`@eslint/config-array`, `eslint`, and `minimatch` (transitive development tooling).
There were no high/critical findings in that npm audit. They are not fixed by this
UI change: no automatic broad dependency upgrade or lockfile rewrite was made.
A successful build/test run is not a clean security audit. Review/upgrade these
separately before treating the project as production-ready.
