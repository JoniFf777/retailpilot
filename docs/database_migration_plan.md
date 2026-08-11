# 数据库迁移计划

## 规则

当前 head 为 `0007_governance_audit`。每个 revision 必须职责单一、保持线性且独立验证；不强制每个 phase
只有一个 revision，也不改写
历史 migration，不对 V2 Customer/orders 表改名或复用。所有 upgrade/downgrade 往返和数据迁移先在隔离
PostgreSQL 数据库验证。

当前 schema 由 `app/db/models.py` 和 `alembic/versions/0007_governance_audit.py` 定义；
`app/repositories/cart.py::get_cart_items` 仍以 product_id 为单位，是 P3 兼容迁移的直接参照。

## 计划

| 阶段 | migration | 内容 | 回滚 |
| --- | --- | --- | --- |
| P1A | `0008_shopmind_catalog_identity` | category、attribute definitions、SPU，nullable unique、无 FK 的 legacy product bridge | 删除全新表 |
| P1A | `0009_shopmind_skus_inventory` | SKU、inventory、Money/check/index | 删除全新表 |
| P2 | 后续线性 revision | action version/安全 preview 所需持久列（若不从现有字段导出） | 删除新增列 |
| P3 | 后续线性 revision | 新 SKU cart 表或审计、去重、唯一约束、兼容读迁移 | 保留备份映射后回退；不可在生产盲目 downgrade |
| P4 | 后续线性 revisions | orders/items/idempotency/outbox | 删除全新交易表 |
| P5 | 后续线性 revision | consumer inbox 与 publisher lease 所需列 | 删除全新表 |
| P6 | 后续线性 revision | 多 payment attempts 和状态约束 | 删除全新表 |

P3 是唯一有数据转换风险的阶段：先输出 owner/product 到 owner/SKU 的审计，针对一条 product 多 SKU 的
旧 cart 行要求明确映射；不能猜测 SKU。未映射行应保留在兼容表/隔离报告中，待用户处理后再启用唯一约束。

## 验收

P1A 迁移按 `0008→0007→0008`、`0009→0008→0009` 在随机隔离 schema 验证；`shopmind_categories` 使用
PostgreSQL 16 `UNIQUE NULLS NOT DISTINCT (parent_id, code)`。每个 revision 必须有 model/repository/API 测试、`upgrade head`、新库 `downgrade -1`、再 `upgrade head`，
以及 PostgreSQL 约束/并发测试。迁移期间不开启新 API 路由，直到 seed 和兼容检查完成。
