"""Errors raised by platform adapters behind ``ClusterPort``.

They live in the domain so application code (tool execution, approval gates)
can handle them without importing a concrete adapter.
"""


class ToolError(Exception):
    """A permanent failure the agent should read and adapt to (bad args, unknown service)."""


class ToolTransientError(Exception):
    """A transient failure (timeout, 5xx). The runtime retries these with backoff."""
