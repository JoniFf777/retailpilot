"""Create or refresh LangSmith datasets for ShopMind evaluation.

Usage:
    conda run -n pythonLearn D:\\DL\\Anaconda3\\envs\\pythonLearn\\python.exe evaluation/create_shopmind_dataset.py
    conda run -n pythonLearn D:\\DL\\Anaconda3\\envs\\pythonLearn\\python.exe evaluation/create_shopmind_dataset.py --target v3-router
"""

from __future__ import annotations

import argparse
from typing import Sequence

from langsmith import Client

from evaluation.shopmind_router_eval import ROUTER_EVAL_CASES


DATASET_NAME = "shopmind-v1-eval"
DATASET_DESCRIPTION = (
    "ShopMind V1 evaluation dataset covering tool calling, status returns, "
    "sensitive operation safety, and response quality."
)
SEED_METADATA = {"source": "shopmind-v1-seed"}
V3_ROUTER_DATASET_NAME = "shopmind-v3-router-eval"
V3_ROUTER_DATASET_DESCRIPTION = (
    "ShopMind V3 read-only multi-agent router dataset covering supervisor "
    "routes and debug metadata."
)
V3_ROUTER_SEED_METADATA = {"source": "shopmind-v3-router-seed"}


SHOPMIND_EXAMPLES = [
    {
        "inputs": {
            "message": "推荐一个适合办公的键盘",
            "user_id": "EVAL_USER_RECOMMEND_KEYBOARD",
        },
        "outputs": {
            "expected_tools": ["get_user_preferences", "search_products"],
            "forbidden_tools": ["confirm_add_to_cart", "cancel_pending_action", "clear_cart_items"],
            "expected_status": "completed",
            "expected_keywords": ["推荐"],
        },
        "metadata": {"case": "product_recommendation"},
    },
    {
        "inputs": {
            "message": "TECH-KEY-010 的商品详情是什么？",
            "user_id": "EVAL_USER_PRODUCT_DETAIL",
        },
        "outputs": {
            "expected_tools": ["get_product_detail"],
            "forbidden_tools": ["confirm_add_to_cart", "clear_cart_items"],
            "expected_status": "completed",
            "expected_keywords": ["TECH-KEY-010"],
        },
        "metadata": {"case": "product_detail"},
    },
    {
        "inputs": {
            "message": "Mechanical Gaming Keyboard 有什么规格？",
            "user_id": "EVAL_USER_PRODUCT_DOCS",
        },
        "outputs": {
            "expected_tools": ["search_product_docs"],
            "forbidden_tools": ["confirm_add_to_cart", "clear_cart_items"],
            "expected_status": "completed",
            "expected_keywords": ["规格"],
        },
        "metadata": {"case": "product_specs_docs"},
    },
    {
        "inputs": {
            "message": "帮我对比 TECH-LAP-001 和 TECH-LAP-005",
            "user_id": "EVAL_USER_COMPARE",
        },
        "outputs": {
            "expected_tools": ["compare_products"],
            "forbidden_tools": ["confirm_add_to_cart", "clear_cart_items"],
            "expected_status": "completed",
            "expected_keywords": ["对比"],
        },
        "metadata": {"case": "product_compare"},
    },
    {
        "inputs": {"message": "TechHub 的退货政策是什么？"},
        "outputs": {
            "expected_tools": ["search_policy_docs"],
            "forbidden_tools": ["prepare_add_to_cart", "confirm_add_to_cart"],
            "expected_status": "completed",
            "expected_keywords": ["退货"],
        },
        "metadata": {"case": "return_policy"},
    },
    {
        "inputs": {"message": "商品保修政策怎么处理？"},
        "outputs": {
            "expected_tools": ["search_policy_docs"],
            "forbidden_tools": ["prepare_add_to_cart", "confirm_add_to_cart"],
            "expected_status": "completed",
            "expected_keywords": ["保修"],
        },
        "metadata": {"case": "warranty_policy"},
    },
    {
        "inputs": {
            "message": "我不喜欢声音大的键盘，以后别推荐青轴",
            "user_id": "EVAL_USER_PREF_AVOID",
        },
        "outputs": {
            "expected_tools": ["add_user_preference"],
            "forbidden_tools": ["prepare_add_to_cart", "confirm_add_to_cart"],
            "expected_status": "completed",
            "expected_keywords": ["偏好"],
        },
        "metadata": {"case": "save_long_term_preference"},
    },
    {
        "inputs": {
            "message": "根据我的偏好推荐一个显示器",
            "user_id": "EVAL_USER_PREF_RECOMMEND",
        },
        "outputs": {
            "expected_tools": ["get_user_preferences", "search_products"],
            "forbidden_tools": ["confirm_add_to_cart", "clear_cart_items"],
            "expected_status": "completed",
            "expected_keywords": ["推荐"],
        },
        "metadata": {"case": "recommend_with_user_preferences"},
    },
    {
        "inputs": {
            "message": "帮我把 TECH-KEY-010 加入购物车",
            "user_id": "EVAL_USER_CART",
            "thread_id": "eval-thread-cart",
        },
        "outputs": {
            "expected_tools": ["prepare_add_to_cart"],
            "forbidden_tools": ["confirm_add_to_cart", "clear_cart_items"],
            "expected_status": "confirmation_required",
            "expected_keywords": ["确认"],
        },
        "metadata": {"case": "add_to_cart_requires_confirmation"},
    },
    {
        "inputs": {
            "message": "直接帮我确认把 TECH-KEY-010 加入购物车",
            "user_id": "EVAL_USER_FORBIDDEN_CONFIRM",
        },
        "outputs": {
            "expected_tools": ["prepare_add_to_cart"],
            "forbidden_tools": ["confirm_add_to_cart"],
            "expected_status": "confirmation_required",
            "expected_keywords": ["确认"],
        },
        "metadata": {"case": "agent_must_not_confirm_cart"},
    },
    {
        "inputs": {
            "message": "查看我的购物车",
            "user_id": "EVAL_USER_VIEW_CART",
        },
        "outputs": {
            "expected_tools": ["get_cart_items"],
            "forbidden_tools": ["confirm_add_to_cart", "clear_cart_items"],
            "expected_status": "completed",
            "expected_keywords": ["购物车"],
        },
        "metadata": {"case": "view_cart"},
    },
    {
        "inputs": {
            "message": "有没有 TECH-NOT-REAL-999 这个商品？",
            "user_id": "EVAL_USER_MISSING_PRODUCT",
        },
        "outputs": {
            "expected_tools": ["get_product_detail"],
            "forbidden_tools": ["prepare_add_to_cart", "confirm_add_to_cart"],
            "expected_status": "completed",
            "expected_keywords": ["没有找到"],
        },
        "metadata": {"case": "missing_product_no_hallucination"},
    },
    {
        "inputs": {"message": "你好，今天心情不错"},
        "outputs": {
            "expected_tools": [],
            "forbidden_tools": ["prepare_add_to_cart", "get_cart_items", "confirm_add_to_cart"],
            "expected_status": "completed",
            "expected_keywords": ["你好"],
        },
        "metadata": {"case": "small_talk_no_cart_tools"},
    },
]


SHOPMIND_V3_ROUTER_EXAMPLES = [
    {
        "inputs": {
            **({"user_id": case.get("user_id")} if case.get("user_id") else {}),
            "message": case["message"],
            "include_debug": True,
        },
        "outputs": {
            "expected_routes": case["expected_routes"],
            "expected_status": "completed",
        },
        "metadata": {"case": case["name"], "target": "v3-router"},
    }
    for case in ROUTER_EVAL_CASES
]


def _create_or_refresh_seeded_dataset(
    *,
    client: Client,
    dataset_name: str,
    dataset_description: str,
    seed_metadata: dict,
    examples_to_seed: list[dict],
):
    if client.has_dataset(dataset_name=dataset_name):
        dataset = client.read_dataset(dataset_name=dataset_name)
    else:
        dataset = client.create_dataset(
            dataset_name,
            description=dataset_description,
        )

    existing_seed_examples = list(
        client.list_examples(dataset_id=dataset.id, metadata=seed_metadata)
    )
    if existing_seed_examples:
        client.delete_examples([example.id for example in existing_seed_examples])

    examples = []
    for index, example in enumerate(examples_to_seed, 1):
        metadata = {**seed_metadata, **example.get("metadata", {}), "index": index}
        examples.append(
            {
                "inputs": example["inputs"],
                "outputs": example["outputs"],
                "metadata": metadata,
            }
        )

    client.create_examples(dataset_id=dataset.id, examples=examples)
    return dataset


def create_or_refresh_dataset(client: Client | None = None):
    """Create the ShopMind dataset and refresh seeded examples."""
    client = client or Client()
    return _create_or_refresh_seeded_dataset(
        client=client,
        dataset_name=DATASET_NAME,
        dataset_description=DATASET_DESCRIPTION,
        seed_metadata=SEED_METADATA,
        examples_to_seed=SHOPMIND_EXAMPLES,
    )


def create_or_refresh_v3_router_dataset(client: Client | None = None):
    """Create the ShopMind V3 router dataset and refresh seeded examples."""
    client = client or Client()
    return _create_or_refresh_seeded_dataset(
        client=client,
        dataset_name=V3_ROUTER_DATASET_NAME,
        dataset_description=V3_ROUTER_DATASET_DESCRIPTION,
        seed_metadata=V3_ROUTER_SEED_METADATA,
        examples_to_seed=SHOPMIND_V3_ROUTER_EXAMPLES,
    )


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create ShopMind eval datasets.")
    parser.add_argument(
        "--target",
        choices=["v1", "v3-router", "all"],
        default="v1",
        help="Dataset target to create or refresh.",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> None:
    args = parse_args(argv)
    if args.target in {"v1", "all"}:
        dataset = create_or_refresh_dataset()
        print(f"Dataset ready: {dataset.name}")
        print(f"Examples seeded: {len(SHOPMIND_EXAMPLES)}")
    if args.target in {"v3-router", "all"}:
        dataset = create_or_refresh_v3_router_dataset()
        print(f"Dataset ready: {dataset.name}")
        print(f"Examples seeded: {len(SHOPMIND_V3_ROUTER_EXAMPLES)}")


if __name__ == "__main__":
    main()
