# Runbook: OOMKilled / memory crash-loop

Symptoms: pods CrashLoopBackOff or partial ready counts; logs show OutOfMemoryError / OOMKilled; memory metric near limit; restart count climbing.

Likely causes:
1. Memory leak in a long-running process (cache without eviction is common).
2. Recent deploy that raised memory use.
3. Memory limit set too low for current traffic.

Investigation:
1. query_metrics for memory and restarts.
2. search_logs for OutOfMemoryError / OOMKilled.
3. get_recent_deploys on the failing service AND its dependents — a downstream caller may look unhealthy when the real OOM is upstream.
4. Prefer following error messages to the component that is actually dying.

Remediation:
- A rolling restart_service clears a leaked heap and restores capacity (requires approval). It does not fix the leak.
- Rolling back a caller that only started failing because of an upstream OOM will not help.
- Follow up: fix the leak, alert on heap above ~85% and on restart count.
