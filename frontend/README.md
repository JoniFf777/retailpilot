# ShopMind Web

This is the isolated React + TypeScript + Vite frontend for ShopMind. It is
kept under `frontend/`; the repository root remains backend-only.

```powershell
npm install
npm run lint
npm run typecheck
npm run test
npm run build
```

Local Vite requests under `/api` proxy to `http://127.0.0.1:8000`. Browser
code must never receive the identity signing credential or copy values from
the repository `.env`. Production identity is owned by trusted ingress.

F0 provides the public API contract types, JSON client, POST-SSE reader, route
shell, design tokens, and focused tests. JSON chat is the next F1 slice.
