# 亮点三：持久化任务、恢复与安全写入

> 这一篇回答：Agent 为什么需要 Harness，进程挂掉怎样继续，两个 Worker 怎样不重复提交，以及用户确认为什么不能只是一个前端弹窗。

## 1. 业务背景

普通 Agent Demo 常见流程是“收到请求—调用模型—调用工具—返回”。真实购物任务会遇到：

- 模型或检索耗时较长，HTTP 连接可能断开；
- 服务进程重启，内存中的执行状态消失；
- 两个 Worker 同时领取同一任务；
- 旧 Worker 超时后仍返回结果；
- 用户重复提交或响应丢失；
- 用户确认时价格、库存或证据已经变化；
- 组合中一个 SKU 失败，但前两个已经写入；
- 售后分析误读其他用户订单；
- Agent 直接写购物车，提示词失误变成真实副作用。

因此项目把“生成建议”和“可靠执行”分开。前者可以使用模型，后者必须由持久化状态、数据库事务和服务端权限保证。

## 2. Harness、任务调度器和 Action Service 的区别

| 组件 | 管什么 | 不管什么 |
| --- | --- | --- |
| Runtime Harness | 一次 Agent/模型运行的 ID、幂等、预算、事件、结果和错误 | 不决定业务步骤依赖 |
| Task Scheduler/Worker | 长任务的计划、步骤依赖、领取、恢复和局部修订 | 不直接获得购物车写权限 |
| Tool Gateway | 某角色是否能用某工具、参数是否合法、owner 是否匹配 | 不代替用户确认 |
| Action Service | 用户确认后的业务重验、锁和原子写入 | 不生成推荐理由 |

可以记成：Harness 管“一次运行”，Scheduler 管“一个长任务”，Gateway 管“一次工具调用”，Action Service 管“一次真实副作用”。

## 3. 为什么要把任务拆成多张表

```text
ShoppingTask       当前目标、状态、版本、预算、租约、过期时间
ShoppingTaskPlan   每次计划修订及原因
ShoppingTaskStep   依赖、状态、步骤租约、尝试次数、输出引用
ShoppingTaskAttempt 每次实际执行、usage、错误和结束时间
ShoppingTaskArtifact 不可变中间结果、输入/证据指纹、验证状态
ShoppingTaskEvent  单调 sequence 的公开生命周期事件
ShoppingTaskAction 待确认动作、版本、TTL 和 Resolution
WorkerHeartbeat    Worker 最近存活时间，供 readiness 使用
```

只保存最终答案无法恢复到正确位置；只保存步骤状态又无法审计哪次尝试产生了结果。分表后可以回答“哪一版计划、哪个步骤、哪次尝试、基于什么输入和证据产生了这个产物”。

## 4. 一次任务怎样被领取

Worker 的核心流程是：

1. 更新自身 heartbeat；
2. 查询 queued/running 且租约为空或过期的任务；
3. 使用行锁与 `SKIP LOCKED` 领取一条；
4. 增加 scheduler epoch，生成随机 task lease token；
5. 找出当前 plan revision 中依赖已完成的步骤；
6. 最多领取三个，分别生成 step lease token 和 Attempt；
7. 提交领取事务，释放数据库锁；
8. 在事务外执行模型、检索和业务读取；
9. 使用 token 和 revision 条件保存结果。

外部模型调用期间不持有长数据库事务。否则模型等待几十秒会长期占有行锁，影响其他请求。

## 5. Lease 和 Fencing Token 分别解决什么

Lease 表示“在某个时间窗口内由我处理”，让任务在 Worker 崩溃后可以重新领取。但只有过期时间还不够：旧 Worker 可能在失租后迟到返回。

因此每次领取生成不可预测 token。保存结果时必须同时满足：

- task 仍是可执行状态；
- task token 与当前记录一致；
- step token 与当前记录一致；
- step lease 未过期；
- result.plan_revision 等于 active plan revision；
- 任务没有被取消、删除或过期。

Worker B 接管后会得到新 token，Worker A 的迟到结果即使内容正确也会被拒绝。这就是 fencing。

模型调用可能接近两分钟，项目使用独立 Session 周期性续租。调用返回后，执行 Session 先刷新数据库状态，再做 fencing，避免拿旧缓存中的 lease deadline 错误拒绝有效结果。

## 6. 中断恢复不是“重新执行一遍”

进程重启后，新 Worker 根据数据库判断：

- completed 且输入/依赖/证据版本仍有效的步骤可以复用；
- running 但 lease 已过期的步骤回到 pending，旧 Attempt 标记失败；
- usage 无法确定时记录 unknown usage，不能当作零；
- 被局部修订影响的步骤 superseded；
- 已确认动作和终态任务不会重新执行。

恢复的关键是“数据库中的事实”，不是比较两段内存轨迹是否相似。

## 7. 幂等、版本 CAS 和租约不是一回事

### 幂等键

防止同一业务命令因客户端重试重复执行。同 key、同请求返回原结果；同 key、不同请求返回冲突；原请求进行中返回 in-progress。

### Version CAS

防止用户或并发请求基于旧版本修改任务。请求必须携带 `expected_version`，当前版本不一致就先刷新状态。

### Lease/Fencing

防止多个 Worker 或迟到 Worker 同时提交步骤结果。

三者分别控制“重复命令”“陈旧用户更新”“重复后台执行”，不能用一个幂等键概括全部并发安全。

## 8. 为什么写操作必须经过 HITL

只读 Agent 可以提出建议，但“推荐加入购物车”和“已经加入购物车”是两件事。模型判断存在概率，用户授权也必须对应明确商品、数量和当前版本。

动作流程：

```text
已验证 Artifact
→ Action Preview
→ 前端展示商品/数量/影响
→ 用户确认或取消
→ 服务端锁定并重新验证
→ 原子执行
→ 保存 Resolution
```

Preview 绑定：owner、task id、goal version、plan revision、artifact id、action version、payload 和 expires_at。任何关键版本变化都会使旧预览失效。

## 9. 组合加购为什么不能循环调用单品接口

如果按三个单品依次提交：笔记本成功、显示器成功、扩展坞缺货，就留下不完整购物车。补偿删除也可能失败，并且并发下很难恢复原数量。

项目在一个数据库事务中：

1. 锁 Task 和 Action；
2. 检查 owner、状态、TTL、version 和请求 hash；
3. 按稳定 SKU 顺序锁商品、库存和购物车记录，降低死锁概率；
4. 重新读取价格、币种、可售状态和库存；
5. 检查现有购物车数量与最大限制；
6. 所有 SKU 均通过后批量合并购物车；
7. 写入 Action Resolution；
8. 一次 commit。

任何一项失败都 rollback，整组不产生部分副作用。

## 10. 为什么确认后还要重验

用户确认的是“这个具体方案”，但确认发生前后外部事实可能变化：

- 库存被别人购买；
- 商品下架；
- 价格或币种变化；
- 证据版本撤销；
- 任务被用户修改；
- Action 已过期；
- 订单归属或状态不再满足。

因此确认不是绕过校验的通行证。系统重验失败时拒绝旧动作并要求生成新预览，让用户看到新的影响后重新确认。

## 11. 响应丢失和重复确认怎样处理

最危险的情况是数据库已经 commit，但 HTTP 响应在网络中丢失。用户重试时，如果只看 expected_version，可能误报冲突；如果直接再执行，会重复加购。

项目先按 owner、action、Idempotency-Key 和 request hash 查已保存 Resolution。完全匹配且已终态时优先重放原结果，不再次写入。不同请求复用同 key 则冲突。

这个顺序叫“成功重放优先于版本冲突”，专门处理 commit 后响应丢失。

## 12. 售后草稿为什么不是售后申请

当前系统读取本人订单和适用政策，生成本地草稿预览。用户确认后保存草稿记录，但不会：

- 调外部客服或工单系统；
- 自动退款；
- 修改订单状态；
- 伪造签收、拆封或损坏事实；
- 发送邮件或消息。

用户补充的事实保留 `user_reported` 来源。缺少可信送达日期时只能给 conditional/unknown。这也是简历应写“售后草稿/申请准备”，不能写“自动办理售后”的原因。

## 13. Harness 管理一次 Agent 运行

任务 Planner 和 Reviewer 通过统一 Harness 调用。一次 Run 包含：

- run/thread/trace/request id；
- owner 和 operation；
- idempotency key 与请求指纹；
- policy 和 token/步骤/工具/时长预算；
- started/completed/failed 事件；
- 结果、typed error 和 usage；
- 可选 SSE 生命周期事件。

Harness 让单 Agent、多 Agent、Planner 和 Reviewer 使用一致的运行语义。它不是业务图，也不是 OS sandbox；真正的工具权限仍由 Tool Gateway 和业务服务执行。

## 14. Redis、PostgreSQL、RocketMQ 各自做什么

| 组件 | 当前职责 |
| --- | --- |
| PostgreSQL | 任务事实、步骤租约、业务事务、Catalog、订单、购物车、Outbox |
| Redis（可选） | 多实例 admission lease、速率限制、去重、短期缓存 |
| RocketMQ（可选） | Transactional Outbox 事件发布 |

Agent 步骤不是通过 RocketMQ 相互通信。任务 DAG 需要事务、依赖查询和 fencing，当前由 PostgreSQL Worker 完成。RocketMQ Consumer/Inbox 尚未实现，不能声称端到端 exactly-once。

## 15. Readiness 和回滚怎样做

新任务功能默认关闭。关闭时旧 Chat 路径不应因新 Worker 或 `0020` 要求被阻断；开启时 readiness 检查：

- PostgreSQL 可连接；
- migration 达到 `0020_task_worker_heartbeat`；
- coordination backend 可用；
- agent/offline 模式配置合法；
- Worker heartbeat 新鲜。

回滚流程不是 downgrade 数据库：先关闭任务准入，再停止 Worker 新领取，等待 lease 结束或显式取消，保留已确认 Cart/草稿和历史任务；RAG 回到受控兼容路径时仍执行撤销与版本 gate。

## 16. 最难的工程问题

**外部调用不能持有长事务。** 领取与执行分离，模型期间独立续租。

**迟到结果可能覆盖新计划。** 使用 task/step token、revision 和条件提交 fencing。

**重试可能重复副作用。** Action Preview、事务 Resolution 和成功重放优先。

**组合写入可能部分成功。** 稳定锁序和单事务整组提交。

**关闭新功能不能拖垮旧系统。** Feature flag、not-applicable preflight 和兼容 migration readiness。

## 17. 面试追问与回答

**为什么租约放 PostgreSQL，不放 Redis？** 任务和步骤本来就在 PostgreSQL，领取、状态和事件需要事务一致性。Redis 适合跨实例轻量协调，但不必成为任务事实源。

**数据库事务能保证 exactly-once 吗？** 对本库动作可以通过幂等与唯一约束实现一次业务结果；跨 MQ/外部系统只有 Outbox 的 at-least-once 发布，Consumer 去重尚未实现，不能说全链路 exactly-once。

**前端确认弹窗为什么不够？** 客户端可以重放或伪造请求。授权对象、版本、归属、TTL 和执行结果都必须由服务端持久化与验证。

**服务挂了怎样继续？** Worker lease 过期后新实例领取未完成步骤，复用仍有效 Artifact；终态 Action Resolution 直接重放，不重复副作用。

## 18. 30 秒口述

> 我把复杂购物任务的计划、步骤、尝试、中间产物和事件全部持久化。Worker 用 PostgreSQL 行锁、SKIP LOCKED 和租约领取步骤，外部模型调用期间不持有长事务，而是续租；结果提交还要校验 fencing token 和 plan revision，所以旧 Worker 的迟到结果不会覆盖新状态。写操作与只读 Agent 隔离，先生成有版本和 TTL 的预览，用户确认后重新检查价格、库存、证据和订单归属，组合加购在一个事务中整组提交。响应丢失时重放原 Resolution，不重复产生副作用。
