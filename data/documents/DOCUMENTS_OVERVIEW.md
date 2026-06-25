# TechHub Document Corpus

**Location:** `data/documents/`  
**Purpose:** 用于 RAG Agent 查询的非结构化内容  
**Total:** 30 个文档（25 个 product specs + 5 个 policies）  
**Format:** Markdown

## 概览

这些文档补充了结构化数据库中的商品和政策信息，包含 product specifications、setup guides、troubleshooting 和 store policies，主要用于自然语言检索。

**关键特性：**

- Product names 和 product IDs 与数据库保持一致；
- 所有文档结构统一；
- 商品规格接近真实厂商资料；
- 政策引用在所有文档中保持一致。

---

## 目录结构

```
data/documents/
├── products/           # 25 product documents
│   ├── TECH-LAP-001.md to TECH-LAP-005.md  (5 laptops)
│   ├── TECH-MON-006.md to TECH-MON-009.md  (4 monitors)
│   ├── TECH-KEY-010.md to TECH-KEY-015.md  (6 keyboards/mice)
│   ├── TECH-AUD-016.md to TECH-AUD-020.md  (5 audio)
│   └── TECH-ACC-021.md to TECH-ACC-025.md  (5 accessories)
│
└── policies/          # 5 policy documents
    ├── return_policy.md
    ├── warranty_guide.md
    ├── shipping_guide.md
    ├── compatibility_guide.md
    └── support_faq.md
```

---

## Product Documents（25 个文件）

**命名规则：**`{product_id}.md`，例如 `TECH-LAP-001.md`。

**标准结构**（7 个部分）：

1. Product Overview：目标用户和核心价值；
2. Key Specifications：技术规格；
3. Compatibility：OS、连接方式和兼容设备；
4. What's Included：包装内容；
5. Setup & Getting Started：5 步安装/启动流程；
6. Common Questions：升级、兼容性、保修等问题；
7. Troubleshooting：常见问题和解决方案。

**类别：**
- **Laptops** (5): MacBook Air/Pro, Dell XPS, Lenovo ThinkPad, HP Pavilion
- **Monitors** (4): Dell UltraSharp, LG, Samsung Gaming, BenQ Designer
- **Keyboards/Mice** (6): Apple Magic, Logitech MX, Gaming, Combos
- **Audio** (5): Sony/Apple headphones, Blue Yeti mic, speakers, JBL
- **Accessories** (5): USB-C hub, laptop stand, webcam, sleeve, cables

---

## Policy Documents（5 个文件）

### return_policy.md
退货资格、时间窗口和流程。
- Unopened: 30-day window
- Opened: 14-day window
- 15% restocking fee for opened items over $500
- Refunds in 5-7 business days

### warranty_guide.md
保修范围和申请流程。
- 1-year manufacturer warranty on all products
- Covers defects, excludes damage
- Claims through manufacturers

### shipping_guide.md
配送方式和时间。
- Standard (5-7 days): FREE on $50+
- Express (2-3 days): $14.99
- UPS/FedEx/USPS

### compatibility_guide.md ⭐
**对 multi-agent query 很关键**：用于跨商品兼容性判断。
- Mac/PC compatibility matrix
- Monitor connections by laptop model
- USB-C vs Thunderbolt explained
- Common setup recommendations
- Adapter requirements

### support_faq.md
通用支持问题。
- Order tracking
- Account management
- Contact: 1-800-555-TECH, support@techhub.com
- Payment and security

---

## 使用模式

### Product Queries
```
"What ports does the MacBook have?" 
→ Retrieve TECH-LAP-001.md, return Key Specifications section
```

### Policy Queries
```
"What's the return policy?"
→ Retrieve return_policy.md
```

### Multi-Agent Queries
```
"Will this monitor work with my Dell laptop?"
→ DB Agent: identify customer's Dell model
→ RAG Agent: retrieve compatibility_guide.md
```

```
"Can I return the monitor I bought last month?"
→ DB Agent: find purchase date
→ RAG Agent: check return_policy.md rules
```

---

## 数据质量

**Consistency checks:**
- ✅ All 25 products have documents
- ✅ Product names/IDs match database
- ✅ Prices match database
- ✅ Policy references consistent (return windows, fees, warranty terms)
- ✅ Contact info consistent across all documents

**关键政策值**（标准化）：
- 14-day return window for opened electronics
- 30-day return window for unopened items
- 15% restocking fee for opened items over $500
- 1-year manufacturer warranty
- Free shipping on orders $50+

---

## RAG 使用建议

1. **Document selection：**商品问题优先使用 product_id，政策问题使用关键词，例如 "return", "warranty"；
2. **Section targeting：**Product docs 结构统一，便于定位具体部分；
3. **Multi-document：**部分问题需要多个来源，例如退货资格 = 购买日期 + policy rules；
4. **Compatibility guide：**对 setup 和多商品兼容性问题非常重要。

---

## 相关资源

**Database schema:** `../structured/SCHEMA.md`  
**Generation process:** `../data_generation/README.md`
