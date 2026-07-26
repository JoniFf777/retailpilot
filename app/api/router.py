from fastapi import APIRouter

from app.api.routes import chat, chat_confirm, chat_stream, health, owner_data


api_router = APIRouter()
api_router.include_router(health.router, tags=["health"])
api_router.include_router(chat.router, tags=["chat"])
api_router.include_router(chat_confirm.router, tags=["chat"])
api_router.include_router(chat_stream.router, tags=["chat", "streaming"])
api_router.include_router(owner_data.router, tags=["governance", "owner-data"])
