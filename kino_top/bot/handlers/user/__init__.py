"""User-facing routers (private chats only)."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.enums import ChatType

from . import (
	ai_assistant,
	catalog,
	comments,
	coupons,
	delivery,
	fallback,
	favorites,
	quiz,
	rating,
	referral,
	search,
	start,
	subscription,
	support,
)

user_router = Router(name="user")
# The bot serves private conversations only; group/channel updates are ignored
# so that catalog callbacks can never be triggered from a public channel.
user_router.message.filter(F.chat.type == ChatType.PRIVATE)
user_router.callback_query.filter(F.message.chat.type == ChatType.PRIVATE)

# Registration/deep links first, then browsing (with the in-bot quiz), search,
# delivery and finally the catch-all fallback.
user_router.include_router(start.router)
user_router.include_router(catalog.router)
user_router.include_router(favorites.router)
user_router.include_router(quiz.router)
user_router.include_router(rating.router)
user_router.include_router(subscription.router)
user_router.include_router(coupons.router)
user_router.include_router(referral.router)
user_router.include_router(support.router)
# The AI yordamchi keeps its own FSM state, so it must be registered before the
# plain search router: that one also reacts to bare messages (a four-digit code
# typed while the assistant prompt is open has to be a question, not a lookup).
user_router.include_router(ai_assistant.router)
# Izohlar work the same way: while a comment is being written, the text the
# user sends belongs to the FSM, not to the search box.
user_router.include_router(comments.router)
user_router.include_router(search.router)
user_router.include_router(delivery.router)
user_router.include_router(fallback.router)

__all__ = ["user_router"]
