"""Cluster adapter factory — MockCluster today; live adapters later behind ClusterPort."""

from __future__ import annotations

from app.mock_env import MockCluster, load_scenario


def cluster_for_run(scenario_id: str, env: dict) -> MockCluster:
    """Factory: assemble a cluster adapter bound to a run's scenario + env checkpoint."""
    return MockCluster(load_scenario(scenario_id), env)
