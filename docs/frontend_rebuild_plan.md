# 前端重做计划

## 基线保护

`frontend/` 为用户未跟踪代码，不删除、不覆盖，也不作为已发布功能宣称。Git branch/tag 不能保护未跟踪
目录，因此 **Phase 1B 前** 必须由用户选择其一：仓库外 ZIP/目录备份、单独 baseline commit，或带 SHA-256
校验值的仓库外备份；选择和位置（不含敏感数据）记录到 `.local/retailpilot-runbook.md`。该保护不阻塞不改
前端的 Phase 1A；未获得明确选择前，禁止删除或原地重写前端。其
`src/api/client.ts`、`src/api/sse.ts`、`streamReducer.ts`、AbortController 流程和现有单测是协议参考。
重做应在明确的迁移目录/分支中进行；本 Phase 0 不移动代码。

## 目标信息架构

| 页面 | 依赖的结构化契约 |
| --- | --- |
| 决策工作台 | RecommendationResult、终态 SSE、Agent progress |
| 比较抽屉 | recommendation SKU/specifications/Money/score/evidence |
| HITL 抽屉 | PendingActionView，绝不解析 answer/tool_calls |
| Cart | cart response（SKU、价格、库存、price change） |
| Checkout | server preview、地址/配送输入、创建订单 mutation |
| Orders/Payment | order/payment 公开 read models |

先将 API 类型从 OpenAPI/受控生成物更新；以最终结构化响应驱动卡片，动态按
`ProductSpecificationView.display_order/comparable` 渲染属性，Money 按 amount/currency 显示，SSE 中间事件
只驱动时间线。completed 使用推荐结果；cancelled/failed 只显示终态与可恢复错误，绝不渲染旧结果。
新 UI 必须保留 JSON chat fallback、AbortController、无障碍 loading/error/retry，且不在浏览器持久化 action
payload、身份 secret 或伪造的价格/状态。

## 分批实施

P1B 才做结构化需求面板和产品卡/比较，以 mock contract 做组件测试，再接真实 HTTP/SSE。P2 替换 action
抽屉为 PendingActionView。P3 增加 Cart。P4/6 增加 checkout/orders/payments。新旧切换标准是：generated
type 更新、JSON/stream completed/cancelled/failed 测试、Abort、HITL 回归和目标页面 Playwright 通过；此前
保留旧页面和路由，不进行原地大删除。

当前开发端口是 5173，Vite `/api` proxy 指向 127.0.0.1:8000；最终 demo 端口/Compose 只在实际配置完成后
写入 README，不能预先声称 3000。
