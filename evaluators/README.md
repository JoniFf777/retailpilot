# Evaluators

本目录包含原 TechHub workshop 中用于评测 Agent 表现的 evaluator。ShopMind V1 在 `evaluation/` 目录中新增了更偏业务规则的 evaluator，并复用了这里的通用 evaluator。

## 可用 Evaluator

| Evaluator | 类型 | 衡量内容 | 返回 |
|-----------|------|----------|---------|
| `correctness_evaluator` | Reference-based | 使用 LLM-as-Judge 对比参考答案，评估事实正确性 | Boolean |
| `count_total_tool_calls_evaluator` | Trace-based | 统计一次执行中的 Tool 调用次数 | Integer |

## 用法

### correctness_evaluator

`correctness_evaluator` 会使用 LLM-as-Judge，将 Agent 输出与 reference output 对比：

```python
from evaluators import correctness_evaluator

result = correctness_evaluator(
    inputs={"messages": [{"role": "user", "content": "What's my order status?"}]},
    outputs={"messages": [{"role": "assistant", "content": "Your order shipped"}]},
    reference_outputs={"messages": [{"role": "assistant", "content": "Shipped"}]}
)

# Returns: {"key": "correctness", "score": True, "comment": "reasoning..."}
```

它主要检查：

- 事实准确性；
- 回答完整性；
- 逻辑一致性。

注意：这是 LLM-as-Judge，会产生额外模型调用成本。ShopMind V1 的默认 evaluation 不自动启用它。

### count_total_tool_calls_evaluator

`count_total_tool_calls_evaluator` 会遍历 LangSmith trace，统计 Tool 调用次数：

```python
from evaluators import count_total_tool_calls_evaluator
from langsmith import Client

client = Client()
run = client.read_run(run_id, load_child_runs=True)

result = count_total_tool_calls_evaluator(run)

# Returns: {"key": "total_tool_calls", "score": 7}
```

它适合衡量：

- 执行效率；
- 是否出现不必要的 Tool 调用；
- 改造前后 Tool 调用数量是否下降。

## 在 LangSmith Experiment 中使用

两个 evaluator 都可以传给 LangSmith 的 `evaluate()`：

```python
from langsmith import Client
from evaluators import correctness_evaluator, count_total_tool_calls_evaluator

client = Client()

results = client.evaluate(
    target_function,
    data="your-dataset-name",
    evaluators=[
        correctness_evaluator,
        count_total_tool_calls_evaluator
    ],
    experiment_prefix="my-experiment"
)
```

## Evaluator 签名

LangSmith 会根据函数签名自动判断 evaluator 类型。

Reference-based evaluator：
```python
def evaluator(inputs: dict, outputs: dict, reference_outputs: dict) -> dict:
    # Has access to example data and expected outputs
    pass
```

Trace-based evaluator：
```python
from langsmith.schemas import Run

def evaluator(run: Run) -> dict:
    # Has access to full execution trace
    pass
```

同一个 experiment 中可以混合使用这两种 evaluator。

## Module 2 学习路径

- Section 1：在 notebook 中从零构建 evaluator，理解 evaluation 概念；
- Section 2：复用这里的 evaluator，重点学习 eval-driven development workflow。

ShopMind V1 的评测入口见 `evaluation/` 目录。
