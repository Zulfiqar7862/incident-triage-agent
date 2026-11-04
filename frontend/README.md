# Operator console

Vite + React + TypeScript frontend for the incident triage agent.

```bash
npm ci
npm run dev        # http://127.0.0.1:5173 — proxies /api to FastAPI :8000
npm run build      # writes dist/ (served by FastAPI in production)
npm run lint && npm run typecheck && npm test
```

See the repository root README for architecture, env vars, and deployment.
