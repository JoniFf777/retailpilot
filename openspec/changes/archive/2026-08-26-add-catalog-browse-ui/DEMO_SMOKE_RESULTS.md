# add-catalog-browse-ui Demo Smoke

- Frontend URL: `http://127.0.0.1:5174/catalog`
- Backend: isolated local offline-demo on `http://127.0.0.1:8001`
- Sequence: Catalog → Phone → Phone product detail → Catalog → Router → Router product detail → canonical SKU PendingAction → existing confirmation → canonical Cart
- Result: PASS
- The old services on ports 8000/5173 were not modified. Temporary ports 8001/5174 were closed after the smoke.
- No LangSmith, Redis, RocketMQ, or external API was used.
