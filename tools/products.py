"""ShopMind product tools.

These tools query the product catalog through the V2 repository layer and
return Chinese, LLM-readable responses for the ShopMind Agent.
"""

from contextlib import contextmanager
from typing import Any, Dict, List, Optional, Sequence

from langchain_core.tools import tool
from pydantic import BaseModel, Field

from app.repositories import products as product_repository
from tools.documents import search_policy_docs, search_product_docs


class SearchProductsInput(BaseModel):
    query: Optional[str] = Field(
        default=None,
        description="可选。按商品名称或商品类别进行模糊搜索，例如 laptop、monitor、keyboard。",
    )
    category: Optional[str] = Field(
        default=None,
        description="可选。按商品类别过滤，例如 Laptops、Monitors、Keyboards、Audio、Accessories。",
    )
    max_price: Optional[float] = Field(
        default=None,
        ge=0,
        description="可选。只返回价格不高于该金额的商品，单位为美元。",
    )
    in_stock_only: bool = Field(
        default=True,
        description="是否只返回有库存商品。默认 true，只返回 in_stock=1 的商品。",
    )
    limit: int = Field(
        default=5,
        ge=1,
        le=25,
        description="返回商品数量上限，默认 5，最大 25。",
    )


class ProductDetailInput(BaseModel):
    product_identifier: str = Field(
        ...,
        min_length=1,
        description="商品 ID 或商品名称关键词，例如 TECH-LAP-001 或 MacBook Air。",
    )


class CompareProductsInput(BaseModel):
    product_identifiers: List[str] = Field(
        ...,
        min_length=1,
        description="要对比的商品 ID 或商品名称关键词列表，例如 ['TECH-LAP-001', 'TECH-LAP-005']。",
    )


ProductRow = Dict[str, Any]


@contextmanager
def _get_product_session():
    from app.db.session import SessionLocal

    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def _fetch_products(
    query: Optional[str] = None,
    category: Optional[str] = None,
    max_price: Optional[float] = None,
    in_stock_only: bool = True,
    limit: int = 5,
) -> List[ProductRow]:
    with _get_product_session() as session:
        return product_repository.search_products(
            session,
            query=query,
            category=category,
            max_price=max_price,
            in_stock_only=in_stock_only,
            limit=limit,
        )


def _find_product(product_identifier: str) -> Optional[ProductRow]:
    with _get_product_session() as session:
        return product_repository.get_product_detail(session, product_identifier)


def _stock_status(product: ProductRow) -> str:
    return "有货" if product["in_stock"] else "缺货"


def _format_product_line(product: ProductRow, index: Optional[int] = None) -> str:
    prefix = f"{index}. " if index is not None else ""
    return (
        f"{prefix}{product['name']}（{product['product_id']}）\n"
        f"   - 类别：{product['category']}\n"
        f"   - 价格：${product['price']:.2f}\n"
        f"   - 库存：{_stock_status(product)}"
    )


def _format_detail(product: ProductRow) -> str:
    return (
        f"商品详情：\n"
        f"- 商品 ID：{product['product_id']}\n"
        f"- 名称：{product['name']}\n"
        f"- 类别：{product['category']}\n"
        f"- 价格：${product['price']:.2f}\n"
        f"- 库存状态：{_stock_status(product)}\n"
        f"\n以上信息来自商品数据库，请不要凭空补充数据库中不存在的商品信息。"
    )


def _format_search_filters(
    query: Optional[str],
    category: Optional[str],
    max_price: Optional[float],
    in_stock_only: bool,
    limit: int,
) -> str:
    filters = [
        f"关键词：{query}" if query else "关键词：未指定",
        f"类别：{category}" if category else "类别：未指定",
        f"最高价格：${max_price:.2f}" if max_price is not None else "最高价格：未指定",
        f"仅看有货：{'是' if in_stock_only else '否'}",
        f"数量上限：{limit}",
    ]
    return "；".join(filters)


@tool(args_schema=SearchProductsInput)
def search_products(
    query: Optional[str] = None,
    category: Optional[str] = None,
    max_price: Optional[float] = None,
    in_stock_only: bool = True,
    limit: int = 5,
) -> str:
    """搜索商品目录，适合在用户想找商品、按类别浏览、按预算筛选或询问有货商品时调用。

    输入字段含义：
    - query：可选，按商品名称或商品类别模糊搜索；
    - category：可选，按商品类别过滤；
    - max_price：可选，只返回不高于该价格的商品；
    - in_stock_only：默认 true，只返回有库存商品；
    - limit：默认 5，限制返回数量。

    返回内容：
    - 返回匹配商品的 ID、名称、类别、价格和库存状态；
    - 如果没有匹配结果，会返回中文提示。

    注意：不要凭空编造商品信息，必须基于数据库查询结果回答。
    """
    products = _fetch_products(
        query=query,
        category=category,
        max_price=max_price,
        in_stock_only=in_stock_only,
        limit=limit,
    )

    filter_summary = _format_search_filters(
        query=query,
        category=category,
        max_price=max_price,
        in_stock_only=in_stock_only,
        limit=limit,
    )

    if not products:
        return (
            f"没有找到符合条件的商品。\n"
            f"筛选条件：{filter_summary}\n"
            f"请基于数据库结果回答，不要凭空编造商品。"
        )

    lines = [_format_product_line(product, index) for index, product in enumerate(products, 1)]
    return (
        f"找到 {len(products)} 个符合条件的商品：\n"
        f"筛选条件：{filter_summary}\n\n"
        + "\n\n".join(lines)
        + "\n\n以上结果来自商品数据库。"
    )


@tool(args_schema=ProductDetailInput)
def get_product_detail(product_identifier: str) -> str:
    """查询单个商品详情，适合在用户询问某个具体商品的价格、类别或库存状态时调用。

    输入字段含义：
    - product_identifier：商品 ID 或商品名称关键词，例如 TECH-LAP-001 或 MacBook Air。

    返回内容：
    - 返回商品 ID、名称、类别、价格、库存状态；
    - 如果商品不存在，会返回明确的中文提示。

    注意：不要凭空编造商品信息，必须基于数据库查询结果回答。
    """
    product = _find_product(product_identifier)
    if not product:
        return f"没有找到商品：{product_identifier}。请检查商品 ID 或名称，不能凭空编造商品信息。"

    return _format_detail(product)


@tool(args_schema=CompareProductsInput)
def compare_products(product_identifiers: Sequence[str]) -> str:
    """对比多个商品，适合在用户要求比较两款或多款商品的价格、类别、库存时调用。

    输入字段含义：
    - product_identifiers：商品 ID 或商品名称关键词列表，例如 ['TECH-LAP-001', 'TECH-LAP-005']。

    返回内容：
    - 返回适合 LLM 阅读的中文对比结果；
    - 对每个存在的商品列出 ID、名称、类别、价格、库存状态；
    - 如果某个商品不存在，会在结果中用中文明确说明。

    注意：不要凭空编造商品信息，必须基于数据库查询结果回答。
    """
    if not product_identifiers:
        return "请至少提供一个要对比的商品 ID 或名称。不要凭空编造商品信息。"

    found_products: List[ProductRow] = []
    missing_identifiers: List[str] = []

    for identifier in product_identifiers:
        product = _find_product(identifier)
        if product:
            found_products.append(product)
        else:
            missing_identifiers.append(identifier)

    response_parts: List[str] = ["商品对比结果："]

    if found_products:
        response_parts.append(
            "\n".join(
                _format_product_line(product, index)
                for index, product in enumerate(found_products, 1)
            )
        )

        cheapest = min(found_products, key=lambda product: product["price"])
        in_stock_count = sum(1 for product in found_products if product["in_stock"])
        response_parts.append(
            f"简要结论：当前可对比的商品中，价格最低的是 {cheapest['name']}（{cheapest['product_id']}），"
            f"价格为 ${cheapest['price']:.2f}；共有 {in_stock_count} 个商品有货。"
        )

    if missing_identifiers:
        missing_text = "、".join(missing_identifiers)
        response_parts.append(f"未找到以下商品：{missing_text}。请检查商品 ID 或名称。")

    response_parts.append("以上信息来自商品数据库，请不要凭空补充数据库中不存在的商品信息。")
    return "\n\n".join(response_parts)


__all__ = [
    "SearchProductsInput",
    "ProductDetailInput",
    "CompareProductsInput",
    "search_products",
    "get_product_detail",
    "compare_products",
    "search_product_docs",
    "search_policy_docs",
]
