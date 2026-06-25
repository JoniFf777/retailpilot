# TechHub Dataset Generation

本目录包含生成 TechHub 合成电商数据集的脚本。当前数据已经生成并可直接使用；只有在需要重新生成或修改数据时，才需要运行这些脚本。

## 数据集概览

**包含内容：**

- 50 个 customers，覆盖 Consumer、Corporate、Home Office 等 segment；
- 25 个 products，包括 laptops、monitors、keyboards、audio、accessories；
- 250 个 orders，覆盖约 2 年时间范围；
- 约 440 条 order items，包含商品搭配购买模式；
- SQLite database，约 156 KB；
- 30 个 RAG 文档，包括 product specs 和 policies。

## 快速重新生成

如需重新生成完整数据集：

```bash
# 1. Generate customers (requires: pip install faker)
python data/data_generation/generate_customers.py

# 2. Generate orders
python data/data_generation/generate_orders.py

# 3. Generate order items
python data/data_generation/generate_order_items.py

# 4. Create SQLite database
python data/data_generation/create_database.py

# 5. Validate
python data/data_generation/validate_database.py

# 6. Build vectorstore
# Default: HuggingFace embeddings (local, no API key)
python data/data_generation/build_vectorstore.py

# Optional: Use OpenAI embeddings instead (requires OPENAI_API_KEY in .env)
# EMBEDDING_PROVIDER=openai python data/data_generation/build_vectorstore.py
```

**总耗时：**约 5 分钟。

**注意：**商品数据手动定义在 `data/structured/products.json` 中，如需修改商品请直接编辑该文件。

### Embedding Provider 选项

vectorstore 支持两种 embedding provider：

- **HuggingFace（默认）**：本地模型，不需要 API key，文件约 2.5 MB；
- **OpenAI**：需要 `OPENAI_API_KEY`，文件约 4.7 MB，适合 HuggingFace 下载受限的环境。

通过 `.env` 中的 `EMBEDDING_PROVIDER` 配置，默认值为 `huggingface`。

## 生成脚本

| Script | Output | 用途 |
|--------|--------|---------|
| `generate_customers.py` | `customers.json` | 使用 Faker 生成 50 个 customer profile |
| `generate_orders.py` | `orders.json` | 生成 250 个带时间分布模式的 orders |
| `generate_order_items.py` | `order_items.json` | 生成约 440 条带商品关联模式的 order items |
| `create_database.py` | `techhub.db` | 创建带 schema 的 SQLite database |
| `validate_database.py` | Validation report | 执行数据质量检查 |
| `build_vectorstore.py` | `techhub_vectorstore_{provider}.pkl` | 构建 RAG embeddings，支持 HuggingFace 或 OpenAI |

## 关键特性

**真实感模式：**

- 季节性订单波动，例如 Q4 spike；
- 幂律 customer 分布，例如少数客户贡献多数订单；
- 商品搭配购买模式，例如 laptop 搭配 accessories、monitor 搭配 keyboard；
- status 分布：80% Delivered、12% Shipped、7% Processing、1% Cancelled。

**可复现：**

- 固定 random seed 为 42，便于稳定重新生成；
- 如需生成不同分布，可修改脚本中的 seed。

## 自定义

可以修改各脚本中的常量：

- `NUM_CUSTOMERS`、`NUM_ORDERS`：调整数据量；
- `CURRENT_DATE`：调整日期锚点；
- `random.seed(42)`：调整随机分布。

更多细节可查看脚本内注释。

## 数据质量

校验脚本会检查：

- 外键无孤立记录；
- 日期逻辑正确，例如 `shipped_date >= order_date`；
- 订单总额与订单明细一致；
- 价格波动在 ±5% 内；
- 常用查询在 1ms 内完成。

## 相关文档

- **Database schema:** `../structured/SCHEMA.md`
- **Document corpus:** `../documents/DOCUMENTS_OVERVIEW.md`
- **Sample queries:** `sample_queries.sql`
