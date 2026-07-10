"""ShopMind V1 single-agent implementation.

This module defines a standalone shopping decision agent that can be invoked
directly today and later wired into the FastAPI `/api/chat` endpoint.
"""

import re
from typing import Any

from langchain.agents import create_agent
from langchain.chat_models import init_chat_model
from langchain_core.messages import AIMessage, BaseMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import MessagesState

from config import Context, DEFAULT_MODEL
from tools.cart import get_cart_items, prepare_add_to_cart
from tools.documents import search_policy_docs, search_product_docs
from tools.preferences import add_user_preference, get_user_preferences
from tools.products import compare_products, get_product_detail, search_products


SHOPMIND_SYSTEM_PROMPT = """你是 ShopMind，一名“智能购物决策 Agent”，负责帮助中文用户完成商品搜索、商品理解、商品对比和购物决策。

你的回答必须面向中文用户，默认使用清晰、自然、简洁的中文。

核心约束：
1. 不能凭空编造商品、价格、库存、规格、兼容性、安装方法、退换货、保修或配送政策。
2. 涉及商品搜索、商品详情、商品价格、商品库存、商品对比时，必须调用商品工具：
   - search_products：搜索商品、按类别/预算/库存筛选商品；
   - get_product_detail：查询单个商品的详情、价格、类别、库存；
   - compare_products：对比多个商品。
3. 涉及商品规格、兼容性、安装、使用说明、技术细节时，必须调用 search_product_docs。
4. 涉及退换货、保修、配送、售后政策时，必须调用 search_policy_docs。
5. 如果请求中传入了 user_id，在推荐商品、比较商品或给出购买建议前，优先调用 get_user_preferences 获取用户偏好。
6. 当用户明确表达长期偏好时，例如“我不喜欢声音大的键盘”“以后别推荐青轴”“我预算一般在 100 美元以内”，调用 add_user_preference 保存。
7. 偏好类型建议：
   - budget：预算偏好；
   - brand：品牌偏好；
   - avoid：排除项或不喜欢的特征；
   - usage：使用场景；
   - style：风格偏好；
   - other：其他偏好。
8. 不要把一次性需求误存为长期偏好，例如“这次我想买一个键盘”不一定需要保存。
9. 用户需求不完整时，优先追问关键约束，例如预算、用途、品牌偏好、是否必须有库存、是否有尺寸/兼容性要求。
10. 推荐商品时，要结合用户偏好，但仍然必须基于商品工具返回的真实商品信息，并说明推荐理由。
11. 如果工具没有找到商品或文档，要明确说明“没有找到”，不要自行补充不存在的信息。
12. 当用户表达“加入购物车”“买这个”“就选第二个”“帮我加购”等意图时，不允许直接完成加购。
13. 加购前必须先调用 prepare_add_to_cart 创建待确认动作；创建待确认动作后，应提示用户确认。
14. 不要调用任何直接写入购物车的工具；确认加购由后续 API 完成。
15. 如果用户想查看购物车，可以调用 get_cart_items。
16. 如果用户没有明确商品 ID 或商品选择不清楚，应先追问，或调用商品检索/详情工具确认商品。
17. 如果请求上下文提供 thread_id，调用 prepare_add_to_cart 时必须把相同 thread_id 传入工具。
18. 如果工具返回的信息不足以做确定判断，请说明缺少哪些信息，并提出下一步建议。

你可以帮助用户做初步购物决策，但所有事实性商品和政策信息都必须来自工具结果。"""


SHOPMIND_TOOLS = [
    search_products,
    get_product_detail,
    compare_products,
    search_product_docs,
    search_policy_docs,
    get_user_preferences,
    add_user_preference,
    prepare_add_to_cart,
    get_cart_items,
]


def create_shopmind_agent(
    model: str | Any | None = None,
    system_prompt: str | None = None,
    use_checkpointer: bool = False,
):
    """Create the ShopMind V1 single agent.

    Args:
        model: 可选。可以传模型名称字符串，也可以传测试用的 BaseChatModel / fake model。
        system_prompt: 可选。覆盖默认中文 system prompt。
        use_checkpointer: 是否启用 MemorySaver。默认 False，便于独立函数调用和测试。

    Returns:
        一个使用 LangChain create_agent 创建的可调用 Agent graph。
    """
    llm = init_chat_model(model or DEFAULT_MODEL, configurable_fields=["model"]) if isinstance(model, str) or model is None else model

    agent_kwargs: dict[str, Any] = {
        "model": llm,
        "tools": SHOPMIND_TOOLS,
        "name": "shopmind_agent",
        "system_prompt": system_prompt or SHOPMIND_SYSTEM_PROMPT,
        "state_schema": MessagesState,
        "context_schema": Context,
    }

    if use_checkpointer:
        agent_kwargs["checkpointer"] = MemorySaver()

    return create_agent(**agent_kwargs)


def _message_content_to_text(content: Any) -> str:
    if isinstance(content, str):
        return content

    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                text = item.get("text") or item.get("content")
                if text:
                    parts.append(str(text))
        return "\n".join(parts)

    return str(content) if content is not None else ""


def _append_unique(items: list[str], value: str | None) -> None:
    if value and value not in items:
        items.append(value)


def _extract_tool_call_names_from_message(message: Any) -> list[str]:
    names: list[str] = []

    tool_calls = getattr(message, "tool_calls", None)
    if tool_calls:
        for tool_call in tool_calls:
            if isinstance(tool_call, dict):
                _append_unique(names, tool_call.get("name"))
            else:
                _append_unique(names, getattr(tool_call, "name", None))

    additional_kwargs = getattr(message, "additional_kwargs", None) or {}
    for tool_call in additional_kwargs.get("tool_calls", []) or []:
        if isinstance(tool_call, dict):
            function_payload = tool_call.get("function") or {}
            _append_unique(names, function_payload.get("name") or tool_call.get("name"))

    if isinstance(message, dict):
        for tool_call in message.get("tool_calls", []) or []:
            if isinstance(tool_call, dict):
                _append_unique(names, tool_call.get("name"))

    # Some LangChain runs include ToolMessage objects after execution. Use their
    # `name` as a fallback so callers can still see which tools were involved.
    if getattr(message, "type", None) == "tool":
        _append_unique(names, getattr(message, "name", None))

    return names


def _extract_tool_call_names(raw_result: Any) -> list[str]:
    names: list[str] = []
    messages = raw_result.get("messages", []) if isinstance(raw_result, dict) else []

    for message in messages:
        for name in _extract_tool_call_names_from_message(message):
            _append_unique(names, name)

    return names


def _extract_final_answer(raw_result: Any) -> str:
    if isinstance(raw_result, dict):
        messages = raw_result.get("messages", [])
        for message in reversed(messages):
            if isinstance(message, AIMessage):
                content = _message_content_to_text(message.content).strip()
                if content:
                    return content
            elif isinstance(message, BaseMessage) and getattr(message, "type", None) == "ai":
                content = _message_content_to_text(message.content).strip()
                if content:
                    return content
            elif isinstance(message, dict) and message.get("role") == "assistant":
                content = _message_content_to_text(message.get("content")).strip()
                if content:
                    return content

        if "output" in raw_result:
            return _message_content_to_text(raw_result["output"]).strip()

    return _message_content_to_text(raw_result).strip()


def _extract_pending_action_id(raw_result: Any) -> str | None:
    if not isinstance(raw_result, dict):
        return None

    messages = raw_result.get("messages", [])
    for message in messages:
        content = None
        if isinstance(message, BaseMessage):
            content = message.content
        elif isinstance(message, dict):
            content = message.get("content")

        text = _message_content_to_text(content)
        match = re.search(r"pending_action_id[：:]\s*([0-9a-fA-F-]+)", text)
        if match:
            return match.group(1)

    return None


def invoke_shopmind_agent(
    message: str,
    user_id: str | None = None,
    thread_id: str | None = None,
) -> dict[str, Any]:
    """Invoke ShopMind Agent and return a structured result.

    Args:
        message: 用户输入。
        user_id: 可选用户 ID。若提供，会明确放入 Agent 上下文，便于偏好工具读取/写入。
        thread_id: 可选会话 ID。若提供，加购待确认动作应关联到该会话。

    Returns:
        dict，至少包含 answer、tool_calls、raw_result。
    """
    agent = create_shopmind_agent()
    context_lines: list[str] = []
    if user_id:
        context_lines.extend(
            [
                f"当前用户 ID 是 {user_id}。",
                "如果需要个性化推荐、商品比较或购买建议，请先读取该用户偏好。",
            ]
        )
    if thread_id:
        context_lines.extend(
            [
                f"当前 thread_id 是 {thread_id}。",
                "如果创建待确认加购动作，请把该 thread_id 传给 prepare_add_to_cart。",
            ]
        )
    if context_lines:
        user_message = "\n".join([*context_lines, f"用户问题：{message}"])
    else:
        user_message = message
    raw_result = agent.invoke({"messages": [{"role": "user", "content": user_message}]})
    tool_calls = _extract_tool_call_names(raw_result)
    pending_action_id = _extract_pending_action_id(raw_result)
    answer = _extract_final_answer(raw_result)

    result = {
        "answer": answer,
        "status": "confirmation_required" if pending_action_id else "completed",
        "tool_calls": tool_calls,
        "raw_result": raw_result,
    }

    if pending_action_id:
        result["pending_action_id"] = pending_action_id

    return result


__all__ = [
    "SHOPMIND_SYSTEM_PROMPT",
    "SHOPMIND_TOOLS",
    "create_shopmind_agent",
    "invoke_shopmind_agent",
]
