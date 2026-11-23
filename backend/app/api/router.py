"""API 路由汇总（前缀 /api/v1）。"""
from fastapi import APIRouter

from . import (
    routes_auth,
    routes_characters,
    routes_episodes,
    routes_projects,
    routes_shots,
    routes_storyboards,
    routes_styles,
    routes_tasks,
    routes_timelines,
    sse,
)

api_router = APIRouter(prefix="/api/v1")

api_router.include_router(routes_auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(routes_styles.router, prefix="/styles", tags=["styles"])
api_router.include_router(routes_projects.router, prefix="/projects", tags=["projects"])
api_router.include_router(routes_episodes.router, tags=["episodes"])
api_router.include_router(routes_storyboards.router, tags=["storyboards"])
api_router.include_router(routes_characters.router, tags=["characters"])
api_router.include_router(routes_shots.router, tags=["shots"])
api_router.include_router(routes_tasks.router, tags=["tasks"])
api_router.include_router(routes_timelines.router, tags=["timelines"])
api_router.include_router(sse.router, tags=["sse"])
