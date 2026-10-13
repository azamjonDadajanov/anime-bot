"""Filters used by the routers."""

from __future__ import annotations

from typing import Union

from aiogram.filters import BaseFilter
from aiogram.types import CallbackQuery, Message

from .config import is_admin


class AdminFilter(BaseFilter):
	"""Allow the update only for Telegram IDs listed in ``ADMIN_IDS``."""

	async def __call__(self, event: Union[Message, CallbackQuery]) -> bool:
		user = event.from_user
		return bool(user and is_admin(user.id))
