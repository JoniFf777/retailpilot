"""Prompt constants for the V3 multi-agent read path.

The first implementation keeps routing and summaries deterministic, but these
boundaries document the prompt intent for future LLM-backed nodes.
"""

SUPERVISOR_ROLE = "只做意图识别和 read-agent 路由，不调用业务工具。"
PRODUCT_AGENT_ROLE = "只读取商品搜索、详情和对比工具，并返回安全摘要。"
RAG_AGENT_ROLE = "只读取商品文档和政策文档，并返回摘要、引用和安全记录。"
PREFERENCE_AGENT_ROLE = "只读取用户偏好，不写入偏好。"
DECISION_AGENT_ROLE = "只消费安全摘要生成最终回答，不调用任何工具。"
