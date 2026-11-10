from fastapi import APIRouter

from app.api import brief, chat, feed, profile, system

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(feed.router)
api_router.include_router(brief.router)
api_router.include_router(chat.router)
api_router.include_router(profile.router)
api_router.include_router(system.router)
