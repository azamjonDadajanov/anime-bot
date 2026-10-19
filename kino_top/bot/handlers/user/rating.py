"""``🏆 Reyting``: the website's rating table, readable in the bot.

The table is the same one the site's "Reyting" page shows
(``games.services.leaderboard``): the top players by trustworthy points, each
with their level, and — when the Telegram visitor has linked a website account —
the visitor's own rank, verified count and attempts. The table itself is public,
so nothing here sits behind the subscription gate; only the "my rank" part needs
an account.
"""

from __future__ import annotations

from typing import Any, Dict

from aiogram import F, Router
from aiogram.types import CallbackQuery

from ... import callbacks as cb
from ...config import game_url
from ...keyboards.user import rating_keyboard
from ...services import quiz as quiz_service
from ...texts import (
	RATING_EMPTY,
	RATING_GUEST,
	RATING_OWN,
	RATING_ROW,
	RATING_ROW_SELF,
	RATING_TITLE,
	RATING_TOP,
)
from ...utils import escape_html, truncate
from ..common import render

router = Router(name="user-rating")

MEDALS = {1: "🥇", 2: "🥈", 3: "🥉"}
# A Telegram name can be long; the row still has to fit one line.
NAME_LIMIT = 24


def render_board(board: Dict[str, Any]) -> str:
	"""The rating table as one Telegram HTML message."""
	rows = board.get("results") or []
	own = board.get("own")
	if not rows:
		return RATING_EMPTY

	blocks = [RATING_TITLE]
	if own:
		blocks.append(
			RATING_OWN.format(
				rank=own["rank"],
				points=own["points"],
				level=own["level"],
				level_name=escape_html(own.get("level_name") or ""),
				verified=own.get("verified", 0),
				attempts=own.get("attempts", 0),
			)
		)
	elif not board.get("linked"):
		blocks.append(RATING_GUEST)

	lines = []
	own_rank = own["rank"] if own else None
	for row in rows:
		mark = MEDALS.get(int(row["rank"]), f"{row['rank']}.")
		template = RATING_ROW_SELF if row["rank"] == own_rank else RATING_ROW
		lines.append(
			template.format(
				mark=mark,
				name=escape_html(truncate(row.get("name") or "O'yinchi", NAME_LIMIT)),
				points=row["points"],
				level=row["level"],
			)
		)
	blocks.append("\n".join([RATING_TOP, *lines]))
	return "\n\n".join(blocks)


@router.callback_query(F.data == cb.RATING)
async def show_rating(callback: CallbackQuery, profile, is_admin: bool) -> None:
	"""Show the table; "🔄 Yangilash" is the same callback, so it re-reads it."""
	board = await quiz_service.leaderboard(profile)
	await render(
		callback,
		render_board(board),
		markup=rating_keyboard(game_url()),
		edit=True,
	)
