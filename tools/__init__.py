"""
Shared tools for the AI Engineering Lifecycle workshop.

This module contains reusable tools that can be imported across multiple workshop modules.
Tools are typically introduced in the notebooks first for pedagogical purposes,
then refactored here for reuse in later sections.
"""

from tools.database import (
    get_customer_orders,
    get_order_item_price,
    get_order_items,
    get_order_status,
    get_product_info,
)
from tools.cart import (
    cancel_pending_action,
    clear_cart_items,
    confirm_add_to_cart,
    get_cart_items,
    prepare_add_to_cart,
)
from tools.documents import search_policy_docs, search_product_docs
from tools.preferences import (
    add_user_preference,
    clear_user_preferences,
    get_user_preferences,
)
from tools.products import compare_products, get_product_detail, search_products

__all__ = [
    "get_order_status",
    "get_order_items",
    "get_product_info",
    "get_order_item_price",
    "get_customer_orders",
    "prepare_add_to_cart",
    "confirm_add_to_cart",
    "cancel_pending_action",
    "get_cart_items",
    "clear_cart_items",
    "search_product_docs",
    "search_policy_docs",
    "search_products",
    "get_product_detail",
    "compare_products",
    "get_user_preferences",
    "add_user_preference",
    "clear_user_preferences",
]
