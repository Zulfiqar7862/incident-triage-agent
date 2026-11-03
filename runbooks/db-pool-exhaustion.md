# Runbook: Database connection pool exhaustion

Symptoms: elevated 5xx and p99 latency on an app service; logs show "could not acquire DB connection", "pool exhausted", waiters > 0; DB itself often looks idle (low active_connections).

Likely causes:
1. A recent deploy shrank DB_POOL_SIZE (or equivalent) below traffic demand.
2. A connection leak in application code.
3. Slow queries holding connections open.

Investigation:
1. describe_service and check config for pool size / timeout.
2. search_logs for pool / TimeoutError lines.
3. get_recent_deploys — look for pool or connection-related changes in the last hour.
4. query_metrics on the database for active_connections (a healthy DB with a tiny app pool is a tell).

Remediation:
- If a deploy changed the pool size, propose rollback_deploy to the previous version (requires approval).
- Do not restart the database. A restart will not grow the app's pool and can make things worse.
- Follow up: restore a sensible pool size behind a canary, and add a canary gate on error rate for config-only changes.
