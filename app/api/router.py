from fastapi import APIRouter

from app.api.routes import chat, chat_confirm, health


api_router = APIRouter()
api_router.include_router(health.router, tags=["health"])
api_router.include_router(chat.router, tags=["chat"])
api_router.include_router(chat_confirm.router, tags=["chat"])
