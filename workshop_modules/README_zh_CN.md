# 工作坊模块

本工作坊通过三个循序渐进的模块讲解完整的 AI Engineering Lifecycle。建议按顺序学习，因为每个模块都会建立在前一模块的基础上。

> 中文版保留 LangChain、LangGraph、LangSmith、Agent、Tool Calling、HITL、RAG 等专有名词。代码单元与英文原版保持一致；如有歧义，以英文原版为准。

## 开始学习

1. **从这里开始：** 打开 `module_1/section_1_foundation_zh_CN.ipynb`
2. **按顺序学习各节：** 每一节都建立在前一节的内容之上
3. **运行全部单元格：** Notebook 中包含完整讲解和可运行示例

每个 Notebook 包括：

- 📖 清晰的概念讲解
- 💻 可运行的代码示例
- 🎯 动手练习

---

## Module 1：Agent Development

从手动 Tool Calling 逐步构建到可用于生产的多 Agent 系统。

**Section 1：基础**（`module_1/section_1_foundation_zh_CN.ipynb`）

- 使用数据库 Tool 实现手动 Tool Calling 循环
- 理解 Agent 在底层如何工作

**Section 2：创建 Agent**（`module_1/section_2_create_agent_zh_CN.ipynb`）

- 使用 `create_agent()` 抽象
- 使用 checkpointer 实现短期记忆和 thread 隔离
- 使用 Streaming 改善用户体验

**Section 3：多 Agent 架构**（`module_1/section_3_multi_agent_zh_CN.ipynb`）

- Database Agent：订单状态、商品信息和价格
- Documents Agent：通过 RAG 检索商品规格和政策
- Supervisor Agent：协调并行或顺序执行的任务

**Section 4：LangGraph HITL**（`module_1/section_4_langgraph_hitl_zh_CN.ipynb`）

- 使用 `interrupt()` 完成客户身份验证
- 查询分类与条件路由
- 通过动态 Prompt 注入 `customer_id`
- 整合验证层、Supervisor 和子 Agent

**Bonus：使用 LangGraph 原语构建 ReAct 循环**（`module_1/bonus_react_loop_langgraph_primitives_zh_CN.ipynb`）

---

## Module 2：Evaluation & Improvement

学习 Evaluation-driven Development，通过可量化的评估系统性改进 Agent。

**Section 1：基线 Evaluation**（`module_2/section_1_baseline_evaluation_zh_CN.ipynb`）

- 创建包含 ground truth 的代表性 dataset
- 使用 LLM-as-Judge correctness evaluator
- 使用基于 trace 的 Tool Calling 计数器
- 在 LangSmith 中运行 experiment

**Section 2：Evaluation-driven Development**（`module_2/section_2_eval_driven_development_zh_CN.ipynb`）

- 发现固定数据库 Tool 导致 Tool Calling 次数过多
- 使用可灵活生成查询的 SQL Agent 改进系统
- 重新评估并量化改进效果
- 将改进后的 Agent 组合进现有系统

**Section 3：高级 Evaluation**（`module_2/section_3_advanced_evaluation_zh_CN.ipynb`）

- Single-step Evaluation：单独测试路由决策
- Trajectory Evaluation：验证 HITL 步骤、Tool Calling 序列和效率
- Run-based evaluator：遍历 LangSmith trace 树检查子 Agent 调用
- Multi-turn Simulation：使用 LLM 模拟真实客户对话

---

## Module 3：Deployment & Continuous Improvement

将应用部署到生产环境，并构建持续改进的 Data Flywheel。

**Section 1：Production Data Flywheel**（`module_3/section_1_production_data_flywheel_zh_CN.ipynb`）

- 在 LangSmith 中创建 Deployment
- 设置 Online Evaluation
- 创建 annotation queue 供人工审核
- 使用 automation rule 捕获生产故障
- 构建“生产 → 标注 → dataset → 改进”的 Data Flywheel

**Section 2：SDK Interaction**（`module_3/section_2_sdk_interaction_zh_CN.ipynb`）

- 使用 LangGraph SDK 调用已部署的 Agent
- Streaming 生产响应
- 以编程方式处理 HITL interrupt
- 构建自定义集成和应用

---

**准备好开始了吗？** 打开 `module_1/section_1_foundation_zh_CN.ipynb` 开始学习。
