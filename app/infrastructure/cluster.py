"""Cluster adapter factory: ``MockCluster`` today; live adapters later behind ``ClusterPort``."""

from __future__ import annotations

from app.domain.ports import ClusterPort
from app.infrastructure.mock_cluster import MockCluster, load_scenario


def cluster_for_run(scenario_id: str, env: dict) -> ClusterPort:
    """Factory: assemble a cluster adapter bound to a run's scenario + env checkpoint."""
    return MockCluster(load_scenario(scenario_id), env)
