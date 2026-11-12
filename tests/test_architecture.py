"""Architecture fitness tests: layer layout, dependency rule, size budgets, port conformance.

They parse the source with ``ast``, so a forbidden import fails the build even if
the module is never executed by another test. They run in the default suite (CI).

Layers (imports point inward only):

    presentation -> application -> domain
    infrastructure -> application ports / domain ports
    core.container (composition root) -> everything; core.config -> nothing in app
"""

from __future__ import annotations

import ast
import sys
import typing
from pathlib import Path

import pytest

APP = Path(__file__).resolve().parents[1] / "app"
LAYERS = {"domain", "application", "infrastructure", "presentation", "core"}

MAX_FILE_LINES = 300
MAX_FUNCTION_LINES = 60
MAX_CLASS_LINES = 250
SIZE_EXEMPT = {
    # Deterministic offline test policy: a linear script of the demo scenarios, kept in one
    # place on purpose so a reviewer can read the whole "model" top to bottom.
    "app/infrastructure/llm/scripted.py",
}


def _module_name(path: Path) -> str:
    rel = path.relative_to(APP.parent).with_suffix("")
    parts = list(rel.parts)
    if parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def _imports(path: Path, *, nested_only: bool = False) -> set[str]:
    """Absolute module names imported by a file (relative imports resolved)."""
    tree = ast.parse(path.read_text(), filename=str(path))
    pkg = _module_name(path) if path.name == "__init__.py" else _module_name(path).rpartition(".")[0]
    nodes = ast.walk(tree)
    if nested_only:
        nodes = (
            n for fn in ast.walk(tree) if isinstance(fn, ast.FunctionDef | ast.AsyncFunctionDef) for n in ast.walk(fn)
        )
    out: set[str] = set()
    for node in nodes:
        if isinstance(node, ast.Import):
            out.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                base = pkg.split(".")
                base = base[: len(base) - (node.level - 1)]
                out.add(".".join([*base, node.module] if node.module else base))
            else:
                out.add(node.module or "")
    return out


def _files(*packages: str) -> list[Path]:
    files: list[Path] = []
    for pkg in packages:
        target = APP / pkg
        files.extend(sorted(target.rglob("*.py")) if target.is_dir() else [target.with_suffix(".py")])
    return files


def _violations(files: list[Path], forbidden: tuple[str, ...]) -> list[str]:
    return [
        f"{f.relative_to(APP.parent)} imports {mod}"
        for f in files
        for mod in _imports(f)
        if any(mod == p or mod.startswith(p + ".") for p in forbidden)
    ]


# ---- layout ---------------------------------------------------------------------------------
def test_every_backend_module_lives_in_a_named_layer():
    """Only the five layer packages and the ASGI entrypoint sit at the top of ``app/``."""
    top = {p.name for p in APP.iterdir() if not p.name.startswith(("__pycache__", "."))}
    assert top - {"__init__.py", "main.py"} == LAYERS


# ---- dependency rule --------------------------------------------------------------------------
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
    "app.core.container",
    "fastapi",
    "starlette",
    "sqlalchemy",
    "sqlite3",
    "aiosqlite",
    "httpx",
    "prometheus_client",
    "opentelemetry",
    "structlog",
    "langfuse",
)


def test_application_depends_on_ports_not_adapters():
    """Use cases, the LangGraph graph, the tool catalog, and context building never import
    adapters, the web framework, persistence drivers, or telemetry SDKs."""
    assert _violations(_files("application"), APPLICATION_FORBIDDEN) == []


def test_graph_nodes_see_only_the_step_port():
    """Nodes talk to ``AgentStepsPort``; never to the run service, the runner, or the Store."""
    forbidden = (
        "app.application.run_service",
        "app.application.graph_runner",
        "app.application.agent_steps",
        "app.application.tool_dispatch",
        "app.domain.ports",
    )
    assert _violations(_files("application/agent/nodes"), forbidden) == []


def test_infrastructure_does_not_depend_on_presentation_or_core_wiring():
    assert (
        _violations(_files("infrastructure"), ("app.presentation", "app.main", "app.core.container", "fastapi")) == []
    )


def test_presentation_uses_application_not_adapters():
    """HTTP routes and views reach storage, models, and metrics only through application ports."""
    forbidden = ("app.infrastructure", "app.core.container", "app.main", "sqlite3", "sqlalchemy", "prometheus_client")
    assert _violations(_files("presentation"), forbidden) == []


def test_config_is_a_leaf():
    assert [m for m in _imports(APP / "core" / "config.py") if m.startswith("app.")] == []


def test_no_function_local_imports_of_app_modules():
    """Imports inside functions are how import cycles get hidden; none are allowed for ``app.*``."""
    bad = [
        f"{f.relative_to(APP.parent)}: {m}"
        for f in _files(*LAYERS, "main")
        for m in _imports(f, nested_only=True)
        if m.startswith("app.")
    ]
    assert bad == []


def test_entrypoint_defines_no_routes():
    tree = ast.parse((APP / "main.py").read_text())
    decorated = [n.name for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.decorator_list]
    assert decorated == []  # routes live in presentation/http


# ---- size budgets --------------------------------------------------------------------------
def _size_violations() -> list[str]:
    bad = []
    for f in sorted(APP.rglob("*.py")):
        rel = str(f.relative_to(APP.parent))
        if rel in SIZE_EXEMPT or "migrations" in rel:
            continue
        src = f.read_text()
        if len(src.splitlines()) > MAX_FILE_LINES:
            bad.append(f"{rel}: {len(src.splitlines())} lines")
        for node in ast.walk(ast.parse(src)):
            if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
                continue
            n = (node.end_lineno or node.lineno) - node.lineno + 1
            limit = MAX_CLASS_LINES if isinstance(node, ast.ClassDef) else MAX_FUNCTION_LINES
            if n > limit:
                bad.append(f"{rel}:{node.name} is {n} lines")
    return bad


def test_modules_functions_and_classes_stay_small():
    assert _size_violations() == []


# ---- ports and registries ------------------------------------------------------------------
def test_adapters_implement_ports(tmp_path):
    from app.application.ports import NullTelemetry, TelemetryPort
    from app.domain.ports import ClusterPort, EventLog, LLMPort, OperatorInbox, RunRepository, RunStorePort
    from app.infrastructure.cluster.mock_cluster import MockCluster, load_scenario
    from app.infrastructure.llm import AnthropicLLM, GeminiLLM, GeminiWithFallback, OpenAILLM, ScriptedPolicy
    from app.infrastructure.observability.telemetry import PrometheusOtelTelemetry
    from app.infrastructure.persistence.store import Store

    store = Store(str(tmp_path / "a.db"))
    assert all(isinstance(store, port) for port in (RunStorePort, RunRepository, EventLog, OperatorInbox))
    assert isinstance(MockCluster(load_scenario("db-pool-regression"), {}), ClusterPort)
    providers = [
        ScriptedPolicy(0),
        GeminiLLM("m", "k", 1),
        AnthropicLLM("m", "k", 1),
        OpenAILLM("m", "k", 1),
        GeminiWithFallback(GeminiLLM("m", "k", 1), None),
    ]
    assert all(isinstance(p, LLMPort) for p in providers)
    assert isinstance(PrometheusOtelTelemetry(), TelemetryPort)
    assert isinstance(NullTelemetry(), TelemetryPort)


def test_agent_steps_satisfies_the_step_port(tmp_path):
    from app.application.ports import AgentStepsPort
    from app.core.config import Settings
    from app.core.container import build_run_service
    from app.infrastructure.llm import ScriptedPolicy
    from app.infrastructure.persistence.store import Store

    service = build_run_service(
        Store(str(tmp_path / "a.db")), ScriptedPolicy(0), Settings(db_path=str(tmp_path / "a.db"))
    )
    assert isinstance(service.steps, AgentStepsPort)


def test_provider_registry_covers_every_configurable_provider():
    from app.core.config import Settings
    from app.infrastructure.llm import PROVIDERS

    options = set(typing.get_args(Settings.model_fields["llm_provider"].annotation)) - {"auto"}
    assert set(PROVIDERS) == options


@pytest.mark.parametrize("tool", sorted(__import__("app.application.tools", fromlist=["TOOLS"]).TOOLS))
def test_every_tool_has_a_dispatch_handler(tool):
    from app.application.tool_dispatch import ToolCallDispatcher
    from app.application.tools import TOOLS

    dispatcher = ToolCallDispatcher(
        tools=TOOLS,
        executor=None,  # type: ignore[arg-type]
        write_gate=None,  # type: ignore[arg-type]
        events=None,  # type: ignore[arg-type]
        cluster_for=lambda st: None,  # type: ignore[arg-type,return-value]
        present_tool=lambda *a, **k: {},
        max_identical_calls=3,
    )
    assert callable(dispatcher.handler_for(TOOLS[tool]))
