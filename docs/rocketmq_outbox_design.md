# ShopMind Transactional Outbox 与 RocketMQ 设计

> 更新时间：2026-09-17
>
> 状态：Phase 6A 与 6B-2 accepted/closed。RocketMQ 仍是可选 Advanced Reliability Demo；Core Demo 不需要 SDK 或 Broker。Consumer/Inbox deferred。

## 1. 一句话说明

ShopMind 不是让订单事务直接调用 RocketMQ，而是在同一 PostgreSQL 事务中写入 Outbox 事件，再由独立 worker 异步发布。

```text
业务状态 + Outbox event  --同一数据库事务提交-->
独立 Publisher  --事务外--> RocketMQ
```

这样解决“订单已提交但消息永久丢失”，但无法消除 Broker 接收成功、本地完成标记丢失造成的重复投递，因此语义是 at-least-once，不是 exactly-once。

## 2. 已实现边界

Phase 6A 实现：

- PostgreSQL `shopmind_outbox_events`；
- Order Create、Order Cancel、Order Expire、Payment Success 同事务 enqueue；
- 独立 RocketMQ FIFO Publisher；
- lease、CAS、退避重试、dead-letter 和 redrive；
- 有界、无 payload 的运维检查；
- Core readiness 与可选 Publisher 状态分离。

当前没有实现：

- RocketMQ Consumer；
- Inbox；
- 消费端 event ID 去重；
- webhook；
- 自动对账 worker；
- RocketMQ 驱动业务编排；
- RocketMQ 驱动购物证据入库。

## 3. 为什么不能直接发布

两种简单做法都有失败窗口：

1. **先提交数据库，再发消息**：进程可能在提交后、发送前崩溃，事件永久丢失；
2. **先发消息，再提交数据库**：消费者可能看到最终回滚的订单状态。

Transactional Outbox 将业务事实和待发布事件放进一个数据库事务。只要业务提交，发布事实就已经持久化；Broker 短暂不可用不会回滚订单。

## 4. Outbox 数据事实

`shopmind_outbox_events` 包含：

- UUID `id`；
- `aggregate_type`、`aggregate_id`、`aggregate_sequence`；
- `event_type`、`event_version`、JSONB `payload`、`occurred_at`；
- `status`、`attempt_count`、`redrive_count`、`available_at`；
- lease owner/expiry；
- 脱敏 `last_error` 和 Broker message ID；
- `created_at`、`updated_at`、`published_at`。

约束包括：

- sequence/version 必须为正；
- retry/redrive 计数不得为负；
- 同 aggregate sequence 唯一；
- lease 与状态必须一致；
- published 状态必须有 `published_at`。

## 5. 事件类型

当前封闭事件集合：

- `shopmind.order.created.v1`；
- `shopmind.order.cancelled.v1`；
- `shopmind.order.expired.v1`；
- `shopmind.payment.succeeded.v1`。

所有事件都使用：

- `aggregate_type=order`；
- `aggregate_id=order_id`；
- 业务迁移后的 Order version 作为 sequence。

相同幂等请求重放不会新增第二条事件。Provider 的中间结果不会直接发布，只有本地业务状态完成后才 enqueue 对应事实。

## 6. 业务事务映射

```text
创建订单
  预占库存 + 精确消费 Cart + 创建 Order
  + order.created event
  -- 一个 PostgreSQL 事务

取消订单
  释放 active Reservation + 更新 Order version
  + order.cancelled event
  -- 一个 PostgreSQL 事务

订单过期
  释放 active Reservation + 更新 Order version
  + order.expired event
  -- 一个 PostgreSQL 事务

支付成功
  消耗 Reservation + 扣减 Inventory + 更新版本
  + PaymentAttempt succeeded + Order paid
  + payment.succeeded event
  -- 一个 PostgreSQL 事务
```

## 7. Claim 与发布生命周期

worker 每轮执行：

1. 在短事务中回收过期 `publishing` lease；
2. 用 `FOR UPDATE SKIP LOCKED` 领取可用 `pending` 行；
3. 写入新的 lease owner、数据库时间 lease expiry，并增加 attempt count；
4. 提交 claim 事务；
5. 在数据库事务外调用 RocketMQ；
6. 成功后用 event ID、`publishing` 状态和 lease owner 做 CAS 完成；
7. 失败时清除 lease，按退避时间重新变为 pending，达到上限后进入 dead-letter。

同一 aggregate 的低 sequence 未 published 时，会阻塞后续 sequence。候选按 `created_at, id` 选择。

## 8. RocketMQ envelope

Publisher 发送：

- topic：`shopmind-order-events-v1`；
- FIFO `message_group=str(order_id)`；
- tag：`event_type`；
- message key：`event_id`；
- body：紧凑、版本化 JSON envelope。

成功 CAS 保存 Broker message ID 和数据库 `published_at`，同时清空 `last_error`。旧 lease owner 不能覆盖新的领取者。

## 9. 崩溃窗口与至少一次

最关键窗口：

```text
RocketMQ 已接受消息
  → worker 在 PostgreSQL 标记 published 前崩溃
  → lease 过期
  → 同一 event ID 再次发布
```

系统无法仅靠 Producer 判断第一次消息是否已经被 Broker/Consumer 处理，所以允许重复发送。未来 Consumer 必须按 immutable `event_id` 去重，并将消费结果与 Inbox 业务事务绑定。

面试中的正确说法是“Transactional Outbox + at-least-once + 为 Inbox 去重预留稳定 event ID”，不能说端到端 exactly-once。

## 10. 重试、死信和 Redrive

发布失败使用确定性指数退避：

- 基础 5 秒；
- 最大 15 分钟；
- 第 12 次失败进入 `dead_letter`。

过期 lease 在未达到上限时回到 pending，达到上限时进入 dead-letter。记录的错误为本地安全文本，不持久化原始凭据、连接 URL 或任意异常 payload。

显式重投：

```powershell
python scripts/redrive_outbox.py EVENT_ID
```

Redrive 只允许 dead-letter：

- 重置 attempt count；
- 增加 redrive count；
- 清除 delivery 字段和 `last_error`；
- 立即变为 pending。

`publishing` 和 `published` 事件不能 redrive。

## 11. SDK 和启动边界

Apache RocketMQ Python SDK 只由 worker 延迟导入，不是 FastAPI API 依赖。固定源码 commit 为：

```text
d463e6400e9819f95a944fa086877336d2e6aad8
```

构建版本：`rocketmq-python-client==5.1.1`。`scripts/bootstrap_rocketmq_sdk.ps1` 使用固定 grpc/protobuf/OpenTelemetry 依赖构建 wheel 并记录 SHA-256。

开发默认关闭 Publisher。显式启动需要：

```text
SHOPMIND_OUTBOX_ENABLED=true
```

endpoint、topic、凭据或 SDK 不完整时，worker fail closed；FastAPI 启动不受影响。API lifespan 不拥有 Publisher loop。

## 12. 运维观察

```powershell
python scripts/inspect_outbox.py --json
```

检查结果只包含：

- 各状态计数；
- 有界 recent failure/dead-letter 事实；
- 安全时间戳；
- 封闭 recommended action。

不会返回 payload、用户身份、Provider Key、request hash 或原始异常。

`GET /api/health/outbox` 暴露同类有界状态。Publisher disabled、积压或 dead-letter 不会直接让核心 API readiness 失败；Readiness 不进行 RocketMQ 网络连接测试。

## 13. 与购物证据 Pipeline 的区别

| 对比项 | 交易 Outbox | 购物证据 Pipeline |
| --- | --- | --- |
| 目标 | 发布已提交订单/支付事件 | 导入商品说明、兼容资料、指南和政策 |
| 事实源 | Order/Payment 事务 | 受信文档 + Catalog/政策元数据 |
| 调度 | 独立 Publisher，可选 RocketMQ | PostgreSQL task lease + node CAS |
| Topic | `shopmind-order-events-v1` | 当前没有 Topic |
| Consumer/Inbox | 未实现 | 首阶段不需要 MQ Consumer |
| 失败语义 | 重试、dead-letter、redrive | 节点恢复、旧版本继续可见、活动指针切换 |

不要为了复用 RocketMQ 而把证据任务发到订单 Topic。未来如果真实入库吞吐证明 PostgreSQL 任务不足，应单独设计证据 Topic、Consumer、Inbox 和幂等合同。

## 14. 当前边界

- Core Demo 不需要 RocketMQ；
- 当前只实现 Publisher 侧；
- 没有端到端 exactly-once；
- 没有 Broker 生产容量或 SLA 证据；
- 没有消费者业务；
- 购物证据不依赖 RocketMQ；
- 工作区最新实现尚未形成新正式 Release。
