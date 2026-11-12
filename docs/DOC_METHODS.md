# Documentation and design methods

This note records which published methods shaped the code layout and the
design documents, and which were considered but not used. Star counts are
GitHub stargazers on 2026-11-12.

## Methods used

| Method | Applied in |
| --- | --- |
| arc42 template (chapter structure) | [HLD.md](HLD.md): section titles carry the arc42 chapter number |
| C4 model (levels 1–3) | HLD §4 context, HLD §5 containers, LLD §3 components |
| Google-style design doc (goals, non-goals, alternatives) | HLD §2 requirements and out-of-scope, HLD §14 alternatives |
| System-design interview order (requirements → estimates → design → bottlenecks) | HLD §1–3 and §12–13 |
| MADR-style ADRs | [adr/](adr/README.md) |
| Ports and adapters, composition root (*Architecture Patterns with Python*) | `app/domain/ports.py`, `app/core/container.py`; [ADR-0003](adr/0003-ports-and-adapters-with-composition-root.md) |
| bulletproof-react project structure | `frontend/src/{app,features,components,hooks,lib,stores,types}` |
| FastAPI best practices (dependencies, routers per concern) | `app/presentation/http/dependencies.py`, `routes.py` |

## Project-local skills installed

| Skill | Source | License | Use |
| --- | --- | --- | --- |
| `architecture-patterns` | wshobson/agents @ `9c61ab2` | MIT | Layering, ports, dependency rule |
| `architecture-decision-records` | wshobson/agents @ `9c61ab2` | MIT | ADR template and process |
| `frontend-design`, `webapp-testing` | anthropics/skills @ `ca45fc4` (installed earlier) | Apache-2.0 | UI work and Playwright testing |

File-level provenance and Git blob IDs: [`.claude/skills/PROVENANCE.md`](../.claude/skills/PROVENANCE.md).

## Research table

| Source | URL | Stars / license | Contribution | Used? Why |
| --- | --- | --- | --- | --- |
| Anthropic skills | https://github.com/anthropics/skills | 193k / per-skill (Apache-2.0 for the two installed) | Official SKILL.md format; frontend-design, webapp-testing | Yes, already installed. Its document skills (docx, pptx) are not open source and are not relevant |
| obra/superpowers | https://github.com/obra/superpowers | 316k / MIT | TDD, debugging, planning and code-review workflows | Followed as process during the work; not vendored because it is a general workflow pack, not project guidance |
| wshobson/agents | https://github.com/wshobson/agents | 42.4k / MIT | Plugin skills incl. architecture-patterns, architecture-decision-records | Yes, two skills installed unmodified |
| VoltAgent/awesome-claude-code-subagents | https://github.com/VoltAgent/awesome-claude-code-subagents | 26.5k / MIT | Subagent prompt catalogue | No: subagent prompts, not architecture guidance |
| hesreallyhim/awesome-claude-code | https://github.com/hesreallyhim/awesome-claude-code | 57.8k / no SPDX licence | Curated list of Claude Code resources | Used for discovery only; nothing copied |
| travisvn/awesome-claude-skills | https://github.com/travisvn/awesome-claude-skills | 15.8k / no licence | Curated list of skills | Discovery only; no licence, nothing copied |
| arc42 | https://arc42.org, https://github.com/arc42/arc42-template | 1.3k / CC BY-SA 4.0 (template) | Architecture documentation chapters | Yes: chapter structure, written in our own words |
| C4 model | https://c4model.com | site / CC BY 4.0 | Context, container, component diagrams | Yes: HLD and LLD diagrams (Mermaid) |
| Structurizr | https://github.com/structurizr/java | 1.1k / Apache-2.0 | C4 tooling and DSL | No: Mermaid renders on GitHub without extra tooling |
| MADR | https://github.com/adr/madr | 2.6k / MIT or CC0 | ADR template | Yes: section shape of our ADRs |
| architecture-decision-record (J. P. Henderson) | https://github.com/architecture-decision-record/architecture-decision-record | 17.5k / no SPDX licence | ADR examples and templates | Read for examples; nothing copied |
| adr-tools | https://github.com/npryce/adr-tools | 5.8k / no SPDX licence | CLI for ADR files | No: six ADRs do not need tooling |
| Architecture Patterns with Python (Cosmic Python) | https://github.com/cosmicpython/book | 3.9k / CC BY-NC-ND | Repository, unit of work, bootstrap / composition root | Yes: ideas only (ports, `build_*` bootstrap); no text copied |
| bulletproof-react | https://github.com/alan2207/bulletproof-react | 36.1k / MIT | Feature-based React structure, no cross-feature imports | Yes: frontend layout and the boundary test |
| fastapi-best-practices | https://github.com/zhanymkanov/fastapi-best-practices | 18.3k / no SPDX licence | Dependencies for validation, router layout | Yes: ideas only |
| system-design-primer | https://github.com/donnemartin/system-design-primer | 378k / CC BY 4.0 | Interview structure, estimates, scaling steps | Yes: HLD order and back-of-the-envelope section |
| system-design-101 (ByteByteGo) | https://github.com/ByteByteGoHq/system-design-101 | 91.2k / no SPDX licence | Visual system-design explainers | Read only; overlaps the primer |
| Google engineering practices | https://github.com/google/eng-practices | 23.3k / CC BY 3.0 | Code review standards | Used as the bar for the harsh review; not copied |
| clean-code-python | https://github.com/zedr/clean-code-python | 4.9k / MIT | Naming, function size | Informed the size budgets in `tests/test_architecture.py` |
| clean-code-javascript | https://github.com/ryanmcdermott/clean-code-javascript | 94.7k / MIT | Same for TypeScript | Informed the 200-line component limit |
