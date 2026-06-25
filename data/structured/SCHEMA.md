# TechHub Database Schema

**Database:** `techhub.db` (SQLite 3, 156 KB)  
**Purpose:** 用于 workshop 场景的电商客服系统数据库  
**Records:** 50 个 customers、25 个 products、250 个 orders、439 个 order items

## 表概览

```
customers (50)
    ↓ 1:N
orders (250)
    ↓ 1:N
order_items (439)
    ↓ N:1
products (25)
```

---

## 1. customers

客户账号信息。

| Column | Type | Constraints | 说明 |
|--------|------|-------------|-------------|
| `customer_id` | TEXT | PRIMARY KEY | 格式：`CUST-###` |
| `email` | TEXT | UNIQUE, NOT NULL | 用于客户验证 |
| `name` | TEXT | NOT NULL | 客户全名 |
| `phone` | TEXT | | 格式：`###-###-####` |
| `city` | TEXT | NOT NULL | 客户所在城市 |
| `state` | TEXT | NOT NULL | 美国州代码 |
| `segment` | TEXT | NOT NULL, CHECK | `'Consumer'`, `'Corporate'`, `'Home Office'` |

**Index:** `idx_customers_email` on `email`

**分布：**
- Consumer: 40 (80%) - @gmail.com, @yahoo.com, @icloud.com
- Corporate: 8 (16%) - company domain emails
- Home Office: 2 (4%)

---

## 2. products

商品目录，包含价格和库存状态。

| Column | Type | Constraints | 说明 |
|--------|------|-------------|-------------|
| `product_id` | TEXT | PRIMARY KEY | 格式：`TECH-XXX-###` |
| `name` | TEXT | NOT NULL | 带规格信息的商品名称 |
| `category` | TEXT | NOT NULL, CHECK | `'Laptops'`, `'Monitors'`, `'Keyboards'`, `'Audio'`, `'Accessories'` |
| `price` | REAL | NOT NULL, CHECK > 0 | 当前价格，单位 USD |
| `in_stock` | INTEGER | NOT NULL, CHECK IN (0, 1) | 1 = 有货，0 = 缺货 |

**Index:** `idx_products_category` on `category`

**类别：**
- Laptops (5): $899 - $1,999
- Monitors (4): $199 - $599
- Keyboards/Mice (6): $39 - $149
- Audio (5): $79 - $399
- Accessories (5): $19 - $79

---

## 3. orders

订单记录，用于追踪客户购买情况。

| Column | Type | Constraints | 说明 |
|--------|------|-------------|-------------|
| `order_id` | TEXT | PRIMARY KEY | 格式：`ORD-YYYY-####` |
| `customer_id` | TEXT | NOT NULL, FOREIGN KEY | References `customers.customer_id` |
| `order_date` | DATE | NOT NULL | 格式：`YYYY-MM-DD` |
| `status` | TEXT | NOT NULL, CHECK | `'Processing'`, `'Shipped'`, `'Delivered'`, `'Cancelled'` |
| `shipped_date` | DATE | | 未发货时为 NULL |
| `tracking_number` | TEXT | | 格式：`1Z999AA1XXXXXXXX`，未发货时为 NULL |
| `total_amount` | REAL | NOT NULL, CHECK >= 0 | 所有 order items 的合计金额 |

**Indexes:**
- `idx_orders_customer` on `customer_id`
- `idx_orders_date` on `order_date`
- `idx_orders_status` on `status`

**状态分布：**
- Delivered: 200 (80%)
- Shipped: 30 (12%)
- Processing: 17 (7%)
- Cancelled: 3 (1%)

**日期范围：**2023 年 10 月至 2025 年 10 月

**关键规则：**

- `shipped_date` 非 NULL 时必须大于等于 `order_date`；
- Processing / Cancelled 订单的 `shipped_date` 和 `tracking_number` 为 NULL；
- Cancelled 订单的 `total_amount` 为 0，且没有 order items。

---

## 4. order_items

订单明细表。

| Column | Type | Constraints | 说明 |
|--------|------|-------------|-------------|
| `order_item_id` | INTEGER | PRIMARY KEY AUTOINCREMENT | 自动生成 ID |
| `order_id` | TEXT | NOT NULL, FOREIGN KEY | References `orders.order_id` |
| `product_id` | TEXT | NOT NULL, FOREIGN KEY | References `products.product_id` |
| `quantity` | INTEGER | NOT NULL, CHECK > 0 | 通常为 1-5 |
| `price_per_unit` | REAL | NOT NULL, CHECK > 0 | 下单时的商品单价 |

**Indexes:**
- `idx_order_items_order` on `order_id`
- `idx_order_items_product` on `product_id`

**Key Rules:**
- Sum of (`quantity` × `price_per_unit`) = `orders.total_amount`
- `price_per_unit` within ±5% of current `products.price`
- Cancelled orders have NO items

---

## 常见查询

### Customer Verification (HITL)
```sql
SELECT customer_id, name, email, segment
FROM customers 
WHERE email = 'sarah.chen@gmail.com';
```

### Order History
```sql
SELECT order_id, order_date, status, tracking_number, total_amount
FROM orders 
WHERE customer_id = 'CUST-001'
ORDER BY order_date DESC;
```

### Order Details
```sql
SELECT 
    o.order_id,
    o.status,
    p.name as product_name,
    oi.quantity,
    oi.price_per_unit,
    (oi.quantity * oi.price_per_unit) as line_total
FROM orders o
JOIN order_items oi ON o.order_id = oi.order_id
JOIN products p ON oi.product_id = p.product_id
WHERE o.order_id = 'ORD-2024-0123';
```

### Product Availability
```sql
SELECT product_id, name, price
FROM products 
WHERE category = 'Laptops' 
AND in_stock = 1
ORDER BY price;
```

### Customer Purchase History
```sql
SELECT DISTINCT
    p.name,
    p.category,
    o.order_date
FROM orders o
JOIN order_items oi ON o.order_id = oi.order_id
JOIN products p ON oi.product_id = p.product_id
WHERE o.customer_id = 'CUST-001'
AND o.status != 'Cancelled'
ORDER BY o.order_date DESC;
```

### Revenue by Category
```sql
SELECT 
    p.category,
    COUNT(DISTINCT oi.order_id) as num_orders,
    SUM(oi.quantity) as units_sold,
    SUM(oi.quantity * oi.price_per_unit) as total_revenue
FROM order_items oi
JOIN products p ON oi.product_id = p.product_id
JOIN orders o ON oi.order_id = o.order_id
WHERE o.status != 'Cancelled'
GROUP BY p.category
ORDER BY total_revenue DESC;
```

---

## 关键约束

**外键：**
- `orders.customer_id` → `customers.customer_id`
- `order_items.order_id` → `orders.order_id`
- `order_items.product_id` → `products.product_id`

**不变量：**
1. 没有孤立记录，所有外键都有效；
2. 日期一致性：`shipped_date` >= `order_date`；
3. 金额准确性：订单总额与 line items 一致；
4. Cancelled 订单总额为 0，且没有明细；
5. Price bounds: items within ±5% of product price

**数据质量：**

- 外键违规数量为 0；
- 日期逻辑错误数量为 0；
- 订单金额准确率 100%；
- 常用查询执行时间小于 1ms。

---

## 查询建议

**面向 SQL Agent：**

- 查询订单前可先用 email 查找 `customer_id`；
- 做收入分析时过滤 `status = 'Cancelled'`；
- 注意 `shipped_date` 和 `tracking_number` 可能为 NULL；
- 优先使用显式 JOIN，便于理解；
- 金额计算可使用 ROUND()。

**ID 格式：**
- Customer IDs: `CUST-###`
- Order IDs: `ORD-YYYY-####`
- Product IDs: `TECH-XXX-###`

**日期函数：**

- 日期以 `YYYY-MM-DD` 存储；
- 可以使用 `julianday()` 做日期计算。

---

## 相关资源

**Data Generation:** `../data_generation/README.md`  
**Document Corpus:** `../documents/DOCUMENTS_OVERVIEW.md`
