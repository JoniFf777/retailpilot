# Focused Verification Results

All focused checks were run with `LANGSMITH_TRACING=false` and external model/Redis/RocketMQ services disabled.

- Recommendation, schema engine, architecture guard, graph, Laptop/Monitor, parser, and service focus: passed; final schema-engine file `6 passed`, architecture proof/guard included in the final backend suite.
- API/OpenAPI/Chat error/retry/runtime focus: `24 passed`.
- Catalog validator/repository focus: tests passed; the host pytest temp cleanup emitted a Windows ACL error when using `tmp_path`, while the same tests passed in the final full backend run with an isolated escalated basetemp.
- OpenAPI schema focus: `5 passed` after official export and generated-type generation.
- Catalog validator command: `valid=true`, `issues=[]`, `categories=2`, `products=16`, `skus=16`.
- Laptop/Monitor existing behavior: full backend regression passed with existing hard-filter/order/alternative/evidence/Commerce assertions.

No test changed production Catalog product counts or managed product/document data.
