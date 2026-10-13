"""Answer purely decorative inline buttons.

Page counters ("2/5"), media-type headers and channels without a link are
rendered as *disabled-looking* buttons so the keyboard keeps its shape. They
still produce a callback query when tapped, and Telegram shows a loading
spinner until that query is answered -- so this router silently acknowledges
them before any other router sees the update.
"""

from __future__ import annotations

from aiogram import F, Router
from aiogram.types import CallbackQuery

from .. import callbacks as cb

router = Router(name="decorative")


@router.callback_query(F.data == cb.NOOP)
async def acknowledge_decorative(callback: CallbackQuery) -> None:
	# No text: Telegram closes the spinner without showing a toast or alert.
	await callback.answer()
