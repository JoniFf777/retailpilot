# Phase 1 商品中心与 SKU 设计

## 目标和边界

第一阶段仅完整支持 Laptop，但数据模型允许 Monitor、Keyboard、Audio、Accessories 继续接入。
不修改已有 `products`、`orders` 或 Customer 历史数据；新增 ShopMind catalog 表，避免破坏
`tools/products.py` 和 V2 种子/检索契约。`shopmind_products.legacy_product_id` 是 nullable、unique 的
字符串，不建立到 `products.product_id` 的数据库外键：旧 Product 数据集可被旧 seed 清空和重建，Catalog
与其生命周期独立。Catalog Repository 和 Catalog seed 在应用层校验、报告并可对账 legacy 映射；悬空映射
不会阻止商品进入推荐，只会使旧产品 RAG evidence 为空。

当前参照物是 `app/db/models.py` 的 `Product`（仅价格和 `in_stock`）与
`app/repositories/products.py` 的 `search_products`；它们保留为旧 read path，不能充当 SKU/inventory 实现。

## 新模型

| 表 | 关键列 | 说明 |
| --- | --- | --- |
| `shopmind_categories` | UUID id, parent_id, code, name, status, managed_by_seed, seed_source, seed_version | PostgreSQL `UNIQUE NULLS NOT DISTINCT (parent_id, code)`；status 为 active/inactive |
| `shopmind_attribute_definitions` | UUID id, category_id, code, name, scope, data_type, unit, required, filterable, searchable, comparable, sku_dimension, options_json, display_order, managed_by_seed, seed_source, seed_version | `(category_id, code)` unique；scope 为 spu/sku |
| `shopmind_products` | UUID id, unique product_code, nullable unique legacy_product_id（无 FK）, category_id, brand, name, description, sale_status, attributes_json, managed_by_seed, seed_source, seed_version, timestamps | SPU；sale_status 为 draft/active/inactive |
| `shopmind_product_skus` | UUID id, product_id, unique sku_code, name, money_amount, currency, sale_status, variant_attributes_json, managed_by_seed, seed_source, seed_version, timestamps | SKU；money 为 `NUMERIC(12,2)`，currency 为 ISO 4217 |
| `shopmind_inventory` | sku_id, on_hand_quantity, reserved_quantity, version, updated_at | sku FK；Phase 1 初始化，Phase 4 才预留 |

所有 ID 使用 PostgreSQL UUID；category parent 是 self FK（删除受限），SPU 删除受限于 SKU，SKU 删除受限于
inventory/cart/order。SKU 的价格、sale_status 和库存是业务事实；属性 JSONB 仅容纳经类目定义验证的值。
DB check 为 `money_amount > 0`、`length(currency) = 3`、`currency = upper(currency)`、
`on_hand_quantity >= 0`、`reserved_quantity >= 0`、`reserved_quantity <= on_hand_quantity`、
`version >= 0`，允许零库存。因为项目使用 PostgreSQL 16，category 使用 `UNIQUE NULLS NOT DISTINCT
(parent_id, code)`，根类目也不能重复 code；需有 PostgreSQL 回归测试。索引包括 category/status、legacy_product_id、product_id、sale_status、
filterable attribute 的 JSONB GIN（只在实际查询证实需要时建立）和 inventory 可售读路径。Laptop seed
至少定义 cpu_tier、gpu_tier、memory_gb、storage_gb、weight_kg、screen_inches、用途标签。
新增已有类目的商品/SKU/普通属性仅改 seed 或管理数据，不改代码。

## 候选、SKU 排名与读模型

新增 Pydantic catalog contract 和 repository：属性 code 必须属于 SKU/SPU 类目、scope 必须匹配，数值/枚举
必须符合定义中的 data_type/unit/options；`sku_dimension=true` 只允许在 SKU attributes，非 SKU dimension
的展示属性只允许 SPU attributes。新推荐主路径由 `CatalogRepository` 直接查询 active SKU，读取 SPU、
SKU、库存为结构化候选；它是候选、SKU、价格、规格、sale status 与 inventory 的唯一事实来源，绝不从
`product_summary`、answer 或其他自然语言字段解析 product id。可用库存始终为
`on_hand_quantity - reserved_quantity`，不得从缓存读取。

硬过滤和评分都在 SKU 层执行。默认 Top K 先对 SKU 排序，再按 SPU 去重：每个 SPU 选择得分最高的 SKU
占用一个推荐名额；同 SPU 的其他可售 SKU 可放在 `alternative_skus`，不占独立 Top K 名额。结果总是返回
明确 `sku_id`，加购只能使用该 sku id。Laptop seed 可以为每个 legacy Product 建一个默认 SKU，但 service
与测试必须支持一 SPU 多 SKU 的排序、去重和 alternative 行为。

## 旧商品、Product Agent 与 RAG 桥接

Phase 1 Laptop seed 为每个可映射旧 `products.product_id` 的 SPU 填入同值的 `legacy_product_id`；新 SPU
仍生成新 UUID，SKU 永远只使用新 UUID。旧 Product Agent 可继续返回旧文本兼容路径；若未来复用它，工具或
Adapter 必须提供独立的结构化 `legacy_product_ids`，不能从其摘要文本解析。它不是新 RecommendationResult
的唯一或默认召回入口。RAG 通过 Catalog 已确定 Top K SPU 的 legacy id 精确过滤
`documents.product_id`（`app/repositories/documents.py` 的 Document read model）；没有 legacy id 的新 SPU
可返回空产品 evidence，只使用 catalog specifications，并在结果中声明 `evidence_unavailable`，不能猜测。

事实优先级固定为：SKU money/sale status/inventory 和结构化规格来自新 Catalog；政策/说明来自 legacy id
过滤后的 documents；旧 `products.price/in_stock` 仅服务旧路径。RAG 与 catalog 的名称、价格、库存、可售或
规格冲突时，RAG evidence 不覆盖 catalog，冲突写入白名单 diagnostic/soft tradeoff；若 evidence 的
legacy product id 与 SPU 不同则排除该 evidence。这保证文本、卡片和引用对应同一商品。

## 种子和迁移

使用职责单一、线性且独立验证的 `0008_shopmind_catalog_identity`（category、attribute definition、SPU）与
`0009_shopmind_skus_inventory`（SKU、inventory、索引）migrations。提供独立的
`scripts/seed_shopmind_catalog.py` 和 JSON seed；它不进入 `seed_postgres.py --clear` 的 destructive 流程。seed 默认
只 insert 缺失的稳定 `product_code` / `sku_code`，绝不覆盖已有人工修改。SPU/SKU 都有全局 unique 的业务
code，并带 `managed_by_seed`、`seed_source`、`seed_version`。显式 `--replace-managed-seed` 只能更新
`managed_by_seed=true` 且 `seed_source` 相同的记录，事务前必须输出变更计划；其它记录跳过并报告。种子只写
新表，不清空已有 V2 数据，也不修改旧 products。普通运行报告 insert、skip 和 dangling legacy mapping；
Inventory 仅为不存在 SKU 初始化，任何普通或 replace seed 均不重置既有数量。迁移回滚只删除新表，必须在隔离数据库
验证，不能对共享 smoke 数据库执行。
