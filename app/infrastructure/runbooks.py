"""Tiny local runbook retrieval — keyword overlap, precision over volume.

No embeddings: with a handful of runbooks, token overlap plus a stem boost is
enough, stays deterministic for evals, and avoids dumping noise into context.
"""

from __future__ import annotations

import re
from pathlib import Path

RUNBOOK_DIR = Path(__file__).resolve().parents[2] / "runbooks"


def _tokenize(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9_]+", (text or "").lower()))


def search_runbooks(query: str, top_k: int = 2) -> list[dict]:
    if not RUNBOOK_DIR.exists():
        return []
    q = _tokenize(query)
    if not q:
        return []
    scored: list[tuple[int, Path, str]] = []
    for path in sorted(RUNBOOK_DIR.glob("*.md")):
        body = path.read_text(encoding="utf-8")
        tokens = _tokenize(path.stem.replace("-", " ") + " " + body)
        overlap = len(q & tokens)
        stem_hits = len(q & _tokenize(path.stem.replace("-", " ")))
        score = overlap + stem_hits * 3
        if score > 0:
            scored.append((score, path, body))
    scored.sort(key=lambda x: (-x[0], x[1].name))
    out = []
    for score, path, body in scored[: max(1, min(top_k, 3))]:
        excerpt = body if len(body) <= 1400 else body[:1400] + "\n…[truncated for context budget]"
        out.append({"id": path.stem, "score": score, "content": excerpt})
    return out
