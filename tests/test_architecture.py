"""Architecture fitness tests: layer boundaries and port conformance.

These run in the default pytest suite (and therefore in CI). They parse the
source with ``ast`` so a forbidden import fails the build even if the module is
never executed by another test.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

import pytest

APP = Path(__file__).resolve().parents[1] / "app"


def _module_name(path: Path) -> str:
    rel = path.relative_to(APP.parent).with_suffix("")
    parts = list(rel.parts)
    if parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def _imports(path: Path) -> set[str]:
    """Absolute module names imported by a file (relative imports resolved)."""
    tree = ast.parse(path.read_text(), filename=str(path))
    pkg = _module_name(path) if path.name == "__init__.py" else _module_name(path).rpartition(".")[0]
    out: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            out.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                base = pkg.split(".")
                base = base[: len(base) - (node.level - 1)]
                mod = ".".join([*base, node.module] if node.module else base)
            else:
                mod = node.module or ""
            out.add(mod)
    return out


def _files(*packages: str) -> list[Path]:
    files: list[Path] = []
    for pkg in packages:
        target = APP / pkg
        files.extend(sorted(target.rglob("*.py")) if target.is_dir() else [target.with_suffix(".py")])
    return files


def _violations(files: list[Path], forbidden: tuple[str, ...]) -> list[str]:
    bad = []
    for f in files:
        for mod in _imports(f):
            if any(mod == p or mod.startswith(p + ".") for p in forbidden):
                bad.append(f"{f.relative_to(APP.parent)} imports {mod}")
    return bad


def test_domain_is_pure_python():
    """Domain imports only the standard library and other domain modules."""
    bad = []
    for f in _files("domain"):
        for mod in _imports(f):
            top = mod.split(".")[0]
            if mod.startswith("app.") and not mod.startswith("app.domain"):
                bad.append(f"{f.name} imports {mod}")
            elif top != "app" and top not in sys.stdlib_module_names and top != "__future__":
                bad.append(f"{f.name} imports third-party {mod}")
    assert bad == []


APPLICATION_FORBIDDEN = (
    "app.infrastructure",
    "app.presentation",
    "app.main",
    "app.runtime",
    "app.llm",
    "fastapi",
    "starlette",
    "sqlalchemy",
    "sqlite3",
    "aiosqlite",
    "httpx",
)


@pytest.mark.parametrize("package", ["application", "agent", "tools", "context"])
def test_application_layer_depends_on_ports_not_adapters(package):
    """Use cases, the LangGraph graph, the tool catalog, and context building never import
    concrete adapters, the web framework, or persistence drivers."""
    assert _violations(_files(package), APPLICATION_FORBIDDEN) == []


def test_infrastructure_does_not_depend_on_presentation():
    assert _violations(_files("infrastructure", "llm"), ("app.presentation", "app.main", "fastapi")) == []


def test_presentation_uses_application_not_adapters():
    """HTTP routes and views reach storage only through the run service."""
    assert _violations(_files("presentation"), ("app.infrastructure", "sqlite3", "sqlalchemy", "app.llm")) == []


def test_routes_are_not_defined_in_the_composition_root():
    tree = ast.parse((APP / "main.py").read_text())
    paths = [
        d.args[0].value
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef)
        for d in node.decorator_list
        if isinstance(d, ast.Call) and d.args and isinstance(d.args[0], ast.Constant)
    ]
    assert paths == ["/"]  # only the SPA shell; API routes live in presentation/http/routes.py


def test_adapters_implement_domain_ports(tmp_path):
    from app.domain.ports import ClusterPort, LLMPort, RunStorePort
    from app.infrastructure.mock_cluster import MockCluster, load_scenario
    from app.infrastructure.store import Store
    from app.llm.providers import AnthropicLLM, GeminiLLM, GeminiWithFallback, OpenAILLM
    from app.llm.scripted import ScriptedPolicy

    assert isinstance(Store(str(tmp_path / "a.db")), RunStorePort)
    assert isinstance(MockCluster(load_scenario("db-pool-regression"), {}), ClusterPort)
    providers = [
        ScriptedPolicy(0),
        GeminiLLM("m", "k", 1),
        AnthropicLLM("m", "k", 1),
        OpenAILLM("m", "k", 1),
        GeminiWithFallback(GeminiLLM("m", "k", 1), None),
    ]
    assert all(isinstance(p, LLMPort) for p in providers)


def test_runtime_satisfies_agent_runtime_port(tmp_path):
    from app.application.ports import AgentRuntimePort
    from app.config import Settings
    from app.infrastructure.store import Store
    from app.llm.scripted import ScriptedPolicy
    from app.runtime import Runtime

    rt = Runtime(Store(str(tmp_path / "a.db")), ScriptedPolicy(0), Settings(db_path=str(tmp_path / "a.db")))
    assert isinstance(rt, AgentRuntimePort)
