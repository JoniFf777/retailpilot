from fastapi import APIRouter

from app.api.routes import cart, checkout, chat, chat_confirm, chat_stream, health, orders, owner_data, payments, pending_actions


api_router = APIRouter()
api_router.include_router(health.router, tags=["health"])
api_router.include_router(chat.router, tags=["chat"])
api_router.include_router(chat_confirm.router, tags=["chat"])
api_router.include_router(chat_stream.router, tags=["chat", "streaming"])
api_router.include_router(owner_data.router, tags=["governance", "owner-data"])
api_router.include_router(pending_actions.router, tags=["pending-actions"])
api_router.include_router(cart.router, tags=["cart"])
api_router.include_router(checkout.router, tags=["checkout"])
api_router.include_router(orders.router, tags=["orders"])
api_router.include_router(payments.router, tags=["payments"])
