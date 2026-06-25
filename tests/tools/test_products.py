from tools.products import compare_products, get_product_detail, search_products


def test_search_products_returns_product_list() -> None:
    result = search_products.invoke({"query": "MacBook", "limit": 3})

    assert "找到" in result
    assert "TECH-LAP-001" in result
    assert "MacBook Air" in result
    assert "以上结果来自商品数据库" in result


def test_search_products_supports_max_price() -> None:
    result = search_products.invoke(
        {
            "category": "Accessories",
            "max_price": 50,
            "in_stock_only": True,
            "limit": 5,
        }
    )

    assert "最高价格：$50.00" in result
    assert "TECH-ACC-021" in result
    assert "TECH-ACC-022" in result
    assert "TECH-ACC-023" not in result


def test_get_product_detail_returns_existing_product() -> None:
    result = get_product_detail.invoke({"product_identifier": "TECH-LAP-001"})

    assert "商品详情" in result
    assert "TECH-LAP-001" in result
    assert "MacBook Air M2" in result
    assert "库存状态：有货" in result


def test_compare_products_compares_two_products() -> None:
    result = compare_products.invoke(
        {"product_identifiers": ["TECH-LAP-001", "TECH-LAP-005"]}
    )

    assert "商品对比结果" in result
    assert "TECH-LAP-001" in result
    assert "TECH-LAP-005" in result
    assert "简要结论" in result


def test_missing_product_returns_clear_chinese_message() -> None:
    detail_result = get_product_detail.invoke({"product_identifier": "NO-SUCH-PRODUCT"})
    compare_result = compare_products.invoke(
        {"product_identifiers": ["TECH-LAP-001", "NO-SUCH-PRODUCT"]}
    )

    assert "没有找到商品：NO-SUCH-PRODUCT" in detail_result
    assert "不能凭空编造商品信息" in detail_result
    assert "未找到以下商品：NO-SUCH-PRODUCT" in compare_result
