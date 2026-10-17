"""Test doubles: an in-memory aiogram session and Telegram update builders.

``FakeSession`` records every Bot API method the bot issues and answers with
canned, correctly typed aiogram objects, so handler flows can be exercised end
to end (middlewares, FSM storage, keyboards) without hitting Telegram.
"""

from __future__ import annotations

import asyncio
import datetime as dt
from typing import Any, Callable, Dict, List, Optional

from aiogram import Bot
from aiogram.client.session.base import BaseSession
from aiogram.types import (
	CallbackQuery,
	Chat,
	ChatMemberAdministrator,
	ChatMemberBanned,
	ChatMemberLeft,
	ChatMemberMember,
	ChatMemberOwner,
	ChatMemberRestricted,
	Document,
	Message,
	PhotoSize,
	Update,
	User,
	Video,
)

BOT_ID = 999
BOT_TOKEN = f"{BOT_ID}:TEST-TOKEN-abcdefghijklmnopqrstuvwxyz1234567"

BOT_USER = User(id=BOT_ID, is_bot=True, first_name="Test Bot", username="test_bot")
USER = User(id=111, is_bot=False, first_name="Tester", username="tester", language_code="uz")
ADMIN = User(id=555, is_bot=False, first_name="Admin", username="admin", language_code="uz")

NOW = dt.datetime(2026, 1, 1, 12, 0, tzinfo=dt.timezone.utc)

MESSAGE_METHODS = {
	"SendMessage",
	"SendPhoto",
	"SendVideo",
	"SendDocument",
	"SendAudio",
	"SendAnimation",
	"SendVoice",
	"EditMessageText",
	"EditMessageCaption",
	"EditMessageMedia",
	"EditMessageReplyMarkup",
	"CopyMessage",
	"ForwardMessage",
}


class FakeSession(BaseSession):
	"""Deterministic :class:`BaseSession` implementation for tests."""

	def __init__(
		self,
		*,
		member_status: str = "member",
		bot_status: str = "administrator",
		responders: Optional[Dict[str, Callable[[Any], Any]]] = None,
	) -> None:
		super().__init__()
		self.calls: List[Any] = []
		self.member_status = member_status
		self.bot_status = bot_status
		self.responders: Dict[str, Callable[[Any], Any]] = responders or {}
		self._message_seq = 100

	# ------------------------------------------------------------------ helpers
	def methods(self, name: str) -> List[Any]:
		return [method for method in self.calls if type(method).__name__ == name]

	def sent_texts(self) -> List[str]:
		return [method.text for method in self.methods("SendMessage")]

	def delivered_file_ids(self) -> List[str]:
		file_ids: List[str] = []
		for method in self.calls:
			name = type(method).__name__
			if name in {"SendVideo", "SendDocument"}:
				file_ids.append(str(getattr(method, "video", None) or getattr(method, "document", None)))
			elif name == "SendPhoto":
				file_ids.append(str(method.photo))
			elif name == "SendMediaGroup":
				for item in method.media:
					file_ids.append(str(item.media))
		return file_ids

	def reset(self) -> None:
		self.calls.clear()

	@staticmethod
	def _chat_id_of(method: Any, default: int = -1001) -> int:
		"""Numeric chat id for a method; usernames fall back to a sentinel."""
		raw = getattr(method, "chat_id", None)
		try:
			return int(raw)
		except (TypeError, ValueError):
			return default

	def _new_message(self, method: Any) -> Message:
		self._message_seq += 1
		return Message(
			message_id=self._message_seq,
			date=NOW,
			chat=Chat(id=self._chat_id_of(method), type="private"),
		)

	# ---------------------------------------------------------------- interface
	@staticmethod
	def _mount(response: Any, bot: Bot) -> Any:
		"""Attach the bot to a returned object, the way ``Bot.__call__`` does.

		Without this a ``Message`` the bot itself sent cannot be edited, so any
		flow that replaces its own message ("🤔 AI o'ylayapti…" → the answer)
		would fail in tests while working against real Telegram.
		"""
		if isinstance(response, Message):
			return response.as_(bot)
		if isinstance(response, list):
			for item in response:
				if isinstance(item, Message):
					item.as_(bot)
		return response

	async def make_request(self, bot: Bot, method: Any, timeout: Optional[int] = None) -> Any:
		self.calls.append(method)
		name = type(method).__name__
		responder = self.responders.get(name)
		if responder is not None:
			result = responder(method)
			if asyncio.iscoroutine(result):
				result = await result
			if isinstance(result, BaseException):
				raise result
			return self._mount(result, bot)
		return self._mount(self._default_response(method, name), bot)

	def _default_response(self, method: Any, name: str) -> Any:
		if name in MESSAGE_METHODS:
			return self._new_message(method)
		if name == "SendMediaGroup":
			return [self._new_message(method)]
		if name == "GetMe":
			return BOT_USER
		if name == "GetChat":
			return Chat(
				id=self._chat_id_of(method),
				type="channel",
				title="Test Channel",
				username="test_channel",
			)
		if name == "GetChatMember":
			if int(getattr(method, "user_id", 0)) == BOT_ID:
				return _member_for(self.bot_status, BOT_USER, with_post_rights=True)
			return _member_for(self.member_status)
		if name == "AnswerCallbackQuery":
			return True
		returning = getattr(method, "__returning__", None)
		if returning is bool:
			return True
		raise AssertionError(f"FakeSession has no canned response for {name}")

	async def stream_content(  # type: ignore[override]
		self,
		url: str,
		headers: Optional[Dict[str, Any]] = None,
		timeout: int = 30,
		chunk_size: int = 65536,
		raise_for_status: bool = True,
	):
		if False:  # pragma: no cover - keeps this an async generator
			yield b""

	async def close(self) -> None:
		return None


def _required_flags(model, **overrides) -> Dict[str, bool]:
	"""Every required boolean privilege of ``model``, defaulted to False.

	Telegram keeps adding privileges (stories, ...), so the fakery fills whatever
	the installed aiogram version demands instead of hardcoding a list.
	"""
	flags = {
		name: False
		for name, field in model.model_fields.items()
		if field.is_required() and field.annotation is bool
	}
	flags.update(overrides)
	return flags


def make_administrator(user, status: str = "administrator", **overrides) -> ChatMemberAdministrator:
	return ChatMemberAdministrator(
		status=status,
		user=user,
		**_required_flags(ChatMemberAdministrator, **overrides),
	)


def _member_for(status: str, user=USER, *, with_post_rights: bool = True):
	"""Build the ChatMember variant that matches ``status``."""
	if status in {"creator", "owner"}:
		return ChatMemberOwner(status="creator", user=user, is_anonymous=False)
	if status == "administrator":
		return make_administrator(
			user,
			can_manage_chat=True,
			can_delete_messages=True,
			can_manage_video_chats=True,
			can_restrict_members=True,
			can_promote_members=True,
			can_change_info=True,
			can_invite_users=True,
			can_post_messages=with_post_rights,
			can_edit_messages=with_post_rights,
			can_pin_messages=with_post_rights,
		)
	if status in {"left", "kicked"}:
		return ChatMemberLeft(status="left", user=user)
	if status == "banned":
		return ChatMemberBanned(status="kicked", user=user, until_date=NOW)
	if status == "restricted":
		return ChatMemberRestricted(
			status="restricted",
			user=user,
			is_member=True,
			until_date=NOW,
			**_required_flags(ChatMemberRestricted),
		)
	return ChatMemberMember(status="member", user=user)


def make_bot(session: Optional[FakeSession] = None) -> Bot:
	return Bot(token=BOT_TOKEN, session=session or FakeSession())


def fake_video(file_id: str = "video-file-id") -> Video:
	return Video(file_id=file_id, file_unique_id=file_id, width=1280, height=720, duration=60)


def fake_document(file_id: str = "document-file-id") -> Document:
	return Document(file_id=file_id, file_unique_id=file_id)


def fake_photo(file_id: str = "photo-file-id") -> PhotoSize:
	return PhotoSize(file_id=file_id, file_unique_id=file_id, width=800, height=1200)


def build_message(
	text: str,
	*,
	user: User = USER,
	chat_id: Optional[int] = None,
	message_id: int = 1,
	update_id: int = 1,
	command_payload: Optional[str] = None,
	**extra: Any,
) -> Update:
	"""Build a private-chat ``Message`` update."""
	chat = Chat(id=chat_id or user.id, type="private")
	message = Message(
		message_id=message_id,
		date=NOW,
		chat=chat,
		from_user=user,
		text=text,
		**extra,
	)
	return Update(update_id=update_id, message=message)


def build_command(command: str, payload: Optional[str] = None, **kwargs: Any) -> Update:
	text = f"/{command}"
	if payload:
		text = f"{text} {payload}"
	return build_message(text, **kwargs)


def build_callback(
	data: str,
	*,
	user: User = USER,
	message_id: int = 5,
	update_id: int = 2,
	chat_id: Optional[int] = None,
	video: Optional[Video] = None,
	document: Optional[Document] = None,
	photo: Optional[PhotoSize] = None,
	media_group_id: Optional[str] = None,
	**extra: Any,
) -> Update:
	"""Build a callback update.

	Passing ``video``/``document``/``photo`` makes the callback's message look
	like the delivered file the inline keyboard rides on — which is exactly the
	situation the in-place media swap inspects.
	"""
	chat = Chat(id=chat_id or user.id, type="private")
	content: Dict[str, Any] = {"text": "panel"}
	if video is not None:
		content = {"video": video}
	elif document is not None:
		content = {"document": document}
	elif photo is not None:
		content = {"photo": [photo]}
	if media_group_id is not None:
		content["media_group_id"] = media_group_id
	message = Message(
		message_id=message_id,
		date=NOW,
		chat=chat,
		from_user=BOT_USER,
		**content,
	)
	return Update(
		update_id=update_id,
		callback_query=CallbackQuery(
			id=f"cb-{update_id}",
			from_user=user,
			chat_instance="test",
			data=data,
			message=message,
			**extra,
		),
	)
