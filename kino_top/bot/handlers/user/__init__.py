"""User-facing routers (private chats only)."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.enums import ChatType

from . import catalog, delivery, fallback, favorites, search, start, subscription

user_router = Router(name="user")
# The bot serves private conversations only; group/channel updates are ignored
# so that catalog callbacks can never be triggered from a public channel.
user_router.message.filter(F.chat.type == ChatType.PRIVATE)
user_router.callback_query.filter(F.message.chat.type == ChatType.PRIVATE)

# Registration/deep links first, then browsing, search, delivery and finally the
# catch-all fallback.
user_router.include_router(start.router)
user_router.include_router(catalog.router)
user_router.include_router(favorites.router)
user_router.include_router(subscription.router)
user_router.include_router(search.router)
user_router.include_router(delivery.router)
user_router.include_router(fallback.router)

__all__ = ["user_router"]
