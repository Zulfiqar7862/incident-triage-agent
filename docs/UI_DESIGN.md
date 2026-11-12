# Operator console design notes

## Reference used

UI/UX Pro Max **2.15.0**, repository `nextlevelbuilder/ui-ux-pro-max-skill`,
pinned revision `b7d5353e0130feb8c5574ef1251f8a1db1873ccb`.
Read the repository README, `.claude/skills/ui-ux-pro-max/SKILL.md`,
`references/quick-reference.md`, and `references/pro-rules.md` (the latter is
native/mobile guidance; web-specific requirements take precedence here).
Downloaded only reference scripts/data to a separate scratch folder; no installer,
repository checkout, global skill changes, runtime dependency, or external font request.

Executed the inspected standard-library search/generator:

```sh
python3 /workspace/uiux-reference/scripts/search.py \
  'developer tool operations console' --design-system \
  --variance 3 --motion 2 --density 8 -p 'Incident Operations' --json
python3 /workspace/uiux-reference/scripts/search.py 'keyboard focus visible' --domain ux
python3 /workspace/uiux-reference/scripts/search.py 'accessible forms labels' --stack react
```

The initial `internal operations monitoring dashboard` query matched an IoT
product. That product mapping was rejected and narrowed once, as the skill
requires. The verified match is **Developer Tool / IDE**, **Minimalism & Swiss
Style**, **Developer Mono** typography, slate surfaces and functional status
colors. The generator's documentation/landing composition is not used: this is
an existing operator workspace, not a marketing page.

## Applied direction

- Retain Vite/React, TanStack Query, Zustand, Tailwind v4, Radix, and feature hooks.
- A restrained three-part workspace: investigation navigation, current incident
  and activity, operator decisions. At tablet widths navigation becomes a top
  strip; on phones incident context and approval precede the activity stream.
- Existing semantic theme tokens are updated rather than creating a parallel
  theme system. Slate text/surfaces; blue navigation/focus; emerald approve;
  amber approval waiting; red dangerous actions. No gradients or invented metrics.
- The reference's mono/sans distinction is adapted to a readable system-sans
  operator interface with monospace reserved for technical details. Keep the
  existing local font fallbacks; do not fetch Google Fonts under the app CSP.
- A 4/8px spacing rhythm, 12/14/16px UI hierarchy, 26px incident title, restrained
  8–12px corners, and lightweight 160ms feedback. No GSAP dependency or ornamental
  animation. Reduced-motion preferences retain the final semantic state.
- Approval is first in the decision column, with evidence, scope, confidence,
  edit disclosure, labeled feedback, and primary/secondary actions. Supporting
  plan/evidence stays available through disclosure rather than crowding actions.
- The default view now shows a concise checked-evidence list, not model thoughts,
  inferred plan progress, repeated approval notices, raw queries, or checkpoints.
- `app/presentation/views/` builds typed summaries from tool identities,
  numeric measurements, release records, and actual applied-action records. Unknown
  or free-form data gets an explicit fallback, not heuristic text sanitization.
- HTTP snapshots, reload event history, and SSE share the same projection.
  Canonical reasoning/results stay intact. Event display fields live outside the
  hash-chained payload, so the audit chain remains independently verifiable.
- Approval shows decision-relevant measurements/releases; the full readable checks
  remain in the activity list. Reported causes are explicitly not independently
  confirmed rather than presenting free-form model diagnosis as established fact.
- Original proposals, model plans/hypotheses, reports, and the context inspector are
  available only behind the separate **For engineers** disclosure.

## Accessibility and recovery

- Visible keyboard outlines and a working skip link; larger control targets;
  long labels wrap instead of clipping. Status meaning includes text, not only color.
- Visible associated form labels. Edit disclosure exposes `aria-expanded` and
  `aria-controls`. Approval failures remain retryable and are announced inline.
- Approval shortcuts work only inside the approval region and do not intercept
  modified system shortcuts or editable controls.
- Both themes' semantic normal-text/background pairs were checked locally:
  minimum **4.73:1** across the audited pairs. This is a token audit, not a claim
  of complete WCAG certification. Browser focus and horizontal-overflow checks
  are also part of the local automated flow/capture suites.

## Verification and visuals

`python -m scripts.e2e_ui` exercises message, edited approval, verified finish,
pause/resume, reject, and stop, plus focus navigation and plain operator report
text. It fails on unexpected console/page errors and reports warnings.

`python -m scripts.capture_screenshots` refreshes desktop empty/active/approval/
resolved/error, dark, and narrow views. Approval widths: 375, 768, 1024, 1440px;
390px resolved capture uses reduced motion. No horizontal page overflow is
allowed at the checked sizes. The deliberately missing-run error screenshot
produces reported 404 console errors; these are separated from unexpected errors.

Existing `docs/screenshots/walkthrough.mp4` is historical and was not re-recorded;
PNG captures and the two-frame GIF are refreshed by this change.

## Final simplification pass and installed skills

Two official Apache-2.0 skills are now installed project-locally, with immutable
provenance and licenses in `.claude/skills/PROVENANCE.md`. They are not runtime
packages. `frontend-design` informed a second, explicit critique: remove nested
trace cards, all-caps decision labels, redundant states, and decorative numbering;
make each row communicate an observed check and each decision communicate impact.
`webapp-testing` informed the existing native Python Playwright verification:
headless Chromium, rendered-state waits, role/label selectors, screenshot critique,
console capture, and separate rejection/cancellation flows to avoid a timing race.
The vendored helper's `--help` was checked; its servers/examples were not executed.

The final compact plan uses existing tokens, not a new theme:
- Slate text `#172437`, white surfaces `#ffffff`, canvas `#f3f5f8`.
- Focus/navigation blue `#2563eb`, approval amber `#b45309`, success `#047857`.
- Existing system-sans stack for readable prose; mono only in engineering data.
- Left-aligned content; no hero/marketing layout and no third-party font fetch.

```text
Desktop: [Investigations] [Problem + observed checks] [Evidence → action → risk → decision]
Phone:   Problem → decision (same evidence) → controls → observed checks
```

Reviewed against the brief: a raw transcript with cosmetic cards was rejected.
The structural change is source-to-render projections, not CSS hiding or a regex
"plain English" cleaner. Known limitation: arbitrary diagnostic text and operator
questions remain available to engineers; the default view cannot safely infer a
specific diagnosis/question from unknown free text and says so explicitly.
