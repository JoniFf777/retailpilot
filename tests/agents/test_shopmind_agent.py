from contextlib import contextmanager

from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
from langchain_core.messages import AIMessage, ToolMessage
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import agents.shopmind_agent as shopmind_agent_module
from agents.shopmind_agent import SHOPMIND_TOOLS, create_shopmind_agent, invoke_shopmind_agent
from app.db.base import Base
from app.db.models import Product
import tools.products as product_tools


class ToolCallingFakeChatModel(FakeMessagesListChatModel):
    def bind_tools(self, tools, *, tool_choice=None, **kwargs):
        return self


class CapturingFakeAgent:
    def __init__(self, raw_result):
        self.raw_result = raw_result
        self.invocation_input = None

    def invoke(self, invocation_input):
        self.invocation_input = invocation_input
        return self.raw_result


@pytest.fixture(autouse=True)
def product_repository_session(monkeypatch):
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    session.add_all(
        [
            Product(
                product_id="TECH-KEY-010",
                name="Logitech MX Keys",
                category="Keyboards",
                price=119.00,
                in_stock=True,
            ),
            Product(
                product_id="TECH-KEY-011",
                name="Mechanical Gaming Keyboard",
                category="Keyboards",
                price=149.00,
                in_stock=True,
            ),
        ]
    )
    session.commit()

    @contextmanager
    def fake_product_session():
        yield session

    monkeypatch.setattr(product_tools, "_get_product_session", fake_product_session)
    yield
    session.close()


def test_create_shopmind_agent_can_create_with_mock_model() -> None:
    model = ToolCallingFakeChatModel(responses=[AIMessage(content="你好，我是 ShopMind。")])

    agent = create_shopmind_agent(model=model)

    assert agent is not None


def test_shopmind_agent_tools_include_preference_tools() -> None:
    tool_names = {tool.name for tool in SHOPMIND_TOOLS}

    assert "get_user_preferences" in tool_names
    assert "add_user_preference" in tool_names
    assert "clear_user_preferences" not in tool_names


def test_shopmind_agent_tools_include_cart_prepare_and_read_tools_only() -> None:
    tool_names = {tool.name for tool in SHOPMIND_TOOLS}

    assert "prepare_add_to_cart" in tool_names
    assert "get_cart_items" in tool_names
    assert "confirm_add_to_cart" not in tool_names
    assert "cancel_pending_action" not in tool_names
    assert "clear_cart_items" not in tool_names


def test_recommend_keyboard_returns_chinese_answer_with_mock_model(monkeypatch) -> None:
    model = ToolCallingFakeChatModel(
        responses=[
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "search_products",
                        "args": {"query": "keyboard", "limit": 3},
                        "id": "call_search_products",
                    }
                ],
            ),
            AIMessage(content="我建议你优先考虑 Logitech MX Keys，因为它有货，适合日常办公使用。"),
        ]
    )
    agent = create_shopmind_agent(model=model)
    monkeypatch.setattr(shopmind_agent_module, "create_shopmind_agent", lambda: agent)

    result = invoke_shopmind_agent("推荐一个键盘")

    assert "建议" in result["answer"]
    assert "Logitech MX Keys" in result["answer"]
    assert "search_products" in result["tool_calls"]


def test_product_spec_question_tends_to_call_detail_or_docs_tool(monkeypatch) -> None:
    model = ToolCallingFakeChatModel(
        responses=[
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "get_product_detail",
                        "args": {"product_identifier": "Mechanical"},
                        "id": "call_get_product_detail",
                    }
                ],
            ),
            AIMessage(content="我先查询了商品信息。数据库中找到 Mechanical Gaming Keyboard。"),
        ]
    )
    agent = create_shopmind_agent(model=model)
    monkeypatch.setattr(shopmind_agent_module, "create_shopmind_agent", lambda: agent)

    result = invoke_shopmind_agent("TechPro Mechanical Keyboard 规格")

    assert result["answer"]
    assert any(
        tool_name in result["tool_calls"]
        for tool_name in ["get_product_detail", "search_product_docs"]
    )


def test_invoke_shopmind_agent_passes_user_and_thread_context(monkeypatch) -> None:
    fake_agent = CapturingFakeAgent(
        raw_result={"messages": [AIMessage(content="我会结合你的偏好进行推荐。")]}
    )
    monkeypatch.setattr(shopmind_agent_module, "create_shopmind_agent", lambda: fake_agent)

    result = invoke_shopmind_agent(
        "推荐一个键盘",
        user_id="USER-001",
        thread_id="THREAD-001",
    )

    user_message = fake_agent.invocation_input["messages"][0]["content"]
    assert "当前用户 ID 是 USER-001" in user_message
    assert "请先读取该用户偏好" in user_message
    assert "当前 thread_id 是 THREAD-001" in user_message
    assert "请把该 thread_id 传给 prepare_add_to_cart" in user_message
    assert "用户问题：推荐一个键盘" in user_message
    assert result["answer"] == "我会结合你的偏好进行推荐。"


def test_long_term_preference_can_extract_add_user_preference_tool_call(monkeypatch) -> None:
    fake_agent = CapturingFakeAgent(
        raw_result={
            "messages": [
                AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "name": "add_user_preference",
                            "args": {
                                "user_id": "USER-001",
                                "preference_type": "avoid",
                                "preference_value": "不喜欢声音大的键盘，以后别推荐青轴",
                            },
                            "id": "call_add_user_preference",
                        }
                    ],
                ),
                AIMessage(content="已记录你的长期偏好：以后会避免推荐声音大的青轴键盘。"),
            ]
        }
    )
    monkeypatch.setattr(shopmind_agent_module, "create_shopmind_agent", lambda: fake_agent)

    result = invoke_shopmind_agent(
        "我不喜欢声音大的键盘，以后别推荐青轴",
        user_id="USER-001",
    )

    assert "add_user_preference" in result["tool_calls"]
    assert "已记录" in result["answer"]


def test_pending_action_result_returns_confirmation_required(monkeypatch) -> None:
    pending_action_id = "123e4567-e89b-12d3-a456-426614174000"
    fake_agent = CapturingFakeAgent(
        raw_result={
            "messages": [
                AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "name": "prepare_add_to_cart",
                            "args": {
                                "user_id": "USER-001",
                                "product_id": "TECH-KEY-010",
                                "quantity": 1,
                            },
                            "id": "call_prepare_add_to_cart",
                        }
                    ],
                ),
                ToolMessage(
                    content=(
                        "已生成待确认的加入购物车动作。\n"
                        f"- pending_action_id：{pending_action_id}\n"
                        "商品：Apple Magic Keyboard（TECH-KEY-010）\n"
                        "请用户确认后再调用 confirm_add_to_cart，当前尚未写入购物车。"
                    ),
                    name="prepare_add_to_cart",
                    tool_call_id="call_prepare_add_to_cart",
                ),
                AIMessage(content="我已为你生成待确认加购，请确认是否加入购物车。"),
            ]
        }
    )
    monkeypatch.setattr(shopmind_agent_module, "create_shopmind_agent", lambda: fake_agent)

    result = invoke_shopmind_agent("帮我把这个键盘加入购物车", user_id="USER-001")

    assert result["status"] == "confirmation_required"
    assert result["pending_action_id"] == pending_action_id
    assert result["answer"] == "我已为你生成待确认加购，请确认是否加入购物车。"
    assert "prepare_add_to_cart" in result["tool_calls"]
