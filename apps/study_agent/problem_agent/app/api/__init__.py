"""API router registration helpers for the problem/feedback module."""

import re

from fastapi import FastAPI
from fastapi.routing import APIRoute

from app.api.learning_contents import router as learning_contents_router
from app.api.problems import router as problems_router

RouteKey = tuple[str, str]


def include_problem_feedback_routers(app: FastAPI) -> None:
    """Attach this module's routers to a shared FastAPI application.

    The future integrated server should call this function instead of importing
    this package's standalone ``app.main.app`` object.
    """
    app.include_router(problems_router)
    app.include_router(learning_contents_router)


def problem_feedback_route_keys() -> list[RouteKey]:
    """Return canonical ``(method, path)`` keys owned by this module."""
    return _route_keys([*problems_router.routes, *learning_contents_router.routes])


def find_problem_feedback_route_conflicts(app: FastAPI) -> list[RouteKey]:
    """Return routes that already exist on ``app`` before this module is included."""
    existing = set(_route_keys(app.routes))
    return [key for key in problem_feedback_route_keys() if key in existing]


def _route_keys(routes: list) -> list[RouteKey]:
    keys: list[RouteKey] = []
    for route in routes:
        if not isinstance(route, APIRoute):
            continue
        path = _canonical_route_path(route.path)
        for method in sorted((route.methods or set()) - {"HEAD", "OPTIONS"}):
            keys.append((method, path))
    return keys


def _canonical_route_path(path: str) -> str:
    return re.sub(r"\{[^}/]+\}", "{}", path)


__all__ = [
    "find_problem_feedback_route_conflicts",
    "include_problem_feedback_routers",
    "learning_contents_router",
    "problem_feedback_route_keys",
    "problems_router",
]
