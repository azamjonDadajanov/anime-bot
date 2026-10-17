"""Root router.

Order matters: the decorative router runs first so page counters and section
headers never leave a loading spinner open, then the administrator router, then
the user-facing routers (whose catch-all handlers are registered last).

The administrator *guard* lives on the admin router itself, so a
non-administrator update falls through to ``user.fallback`` instead of being
swallowed here.
"""

from __future__ import annotations

from aiogram import Router

from .admin import admin_router
from .decorative import router as decorative_router
from .storage_channel import router as storage_router
from .user import user_router

__all__ = ["build_router", "admin_router", "user_router", "decorative_router", "storage_router"]


def build_router() -> Router:
	root = Router(name="root")
	root.include_router(storage_router)
	root.include_router(decorative_router)
	root.include_router(admin_router)
	root.include_router(user_router)
	return root
