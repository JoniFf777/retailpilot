# Workshop Modules

本 workshop 通过三个递进式 module 讲解完整的 AI engineering lifecycle。建议按顺序学习，因为每个 module 都建立在前一个 module 的概念之上。

## 开始学习

1. **从这里开始：**打开 `module_1/section_1_foundation.ipynb`
2. **按顺序学习：**每个 section 都依赖前面的概念
3. **运行所有 cells：**notebooks 中包含完整解释和示例

每个 notebook 都包含：
- 📖 概念解释
- 💻 可运行代码示例
- 🎯 动手练习
---

## Module 1: Agent Development

从手动 tool calling 逐步构建到可部署的 multi-agent systems。

**Section 1: Foundation** (`module_1/section_1_foundation.ipynb`)
- 使用 database tools 实现手动 tool calling loop
- 理解 Agent 底层工作方式

**Section 2: Create Agent** (`section_2_create_agent.ipynb`)
- 使用 `create_agent()` abstraction
- 使用 checkpointers 和 thread separation 管理 memory
- 使用 streaming 改善 UX

**Section 3: Multi-Agent** (`section_3_multi_agent.ipynb`)
- Database Agent：处理 order status、product info、pricing
- Documents Agent：通过 RAG 检索 product specs 和 policies
- Supervisor Agent：协调并行和串行任务

**Section 4: LangGraph HITL** (`section_4_langgraph_hitl.ipynb`)
- 使用 `interrupt()` 实现 customer verification 和 HITL
- Query classification 和 conditional routing
- Dynamic prompts 注入 state，例如 `customer_id`
- 集成 verification、supervisor 和 sub-agents

---

## Module 2: Evaluation & Improvement

学习 evaluation-driven development，用系统化方式改进 Agent。

**Section 1: Baseline Evaluation** (`module_2/section_1_baseline_evaluation.ipynb`)
- 带 ground truth examples 的 curated dataset
- LLM-as-Judge correctness evaluator
- Trace-based tool call counter
- 在 LangSmith 中运行 experiments

**Section 2: Eval-Driven Development** (`section_2_eval_driven_development.ipynb`)
- Identified problem: Rigid DB tools → excessive tool calls
- 解决方案：使用支持灵活 query generation 的 SQL Agent
- 通过 re-evaluation 展示量化改进
- 将改进后的 Agent 组合回现有系统

**Section 3: Advanced Evaluation** (`section_3_advanced_evaluation.ipynb`)
- Single-step evaluation：对独立 routing decision 做 unit test
- Trajectory evaluation：验证 HITL steps、tool call sequences 和效率
- Run-based evaluators：遍历 LangSmith trace tree，检查 sub-agent tool calls
- Multi-turn simulation：使用 LLM-simulated users 构造真实感客户对话

---

## Module 3: Deployment & Continuous Improvement

学习如何部署到生产环境，并构建 data flywheel 实现持续改进。

**Section 1: Production Data Flywheel** (`module_3/section_1_production_data_flywheel.ipynb`)
- 在 LangSmith 中创建 deployments
- 设置 online evaluation，例如用 LLM-as-Judge 评估 helpfulness
- 构建 annotation queues 供人工 review
- 使用 automation rules 捕获生产问题
- Complete data flywheel: production → annotation → dataset → improvement

**Section 2: SDK Interaction** (`section_2_sdk_interaction.ipynb`)
- 使用 LangGraph SDK 调用已部署 Agent
- 从生产环境 streaming responses
- 以编程方式处理 HITL interrupts
- 构建自定义 integrations 和 applications

---

## 涵盖的关键概念

### Agent Development
- Tool calling 和 agent loops
- 基于 supervisor pattern 的 multi-agent systems
- Sub-agent coordination，包括 parallel 和 sequential
- State management 和 memory
- Human-in-the-loop with interrupts

### Evaluation & Testing
- 使用 LangSmith 做 offline evaluation
- LLM-as-Judge evaluators
- Trace-based metrics
- Experiment comparison
- Evaluation-driven development workflow

### Deployment & Production
- LangSmith deployments 和 revisions
- Online evaluation 和 monitoring
- Annotation queues 和 human review
- 用于持续改进的 automation rules
- 面向自定义应用的 SDK integration

### Best Practices Throughout
- 使用 factory functions 提升 Agent 复用性
- 区分 dev checkpointer 和 deploy platform-managed state
- 使用 state injection 构造 dynamic prompts
- 使用 Pydantic 定义 structured outputs
- 使用 streaming 改善 UX

---

**Ready to begin?** Open `module_1/section_1_foundation.ipynb` and start building! 🚀

