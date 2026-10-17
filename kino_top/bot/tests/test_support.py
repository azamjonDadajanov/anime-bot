"""``✉️ Adminga xabar``: a user's message reaches every administrator.

Driven through the real dispatcher, so the mandatory-subscription gate is part
of the test: writing to an administrator must stay possible for a user the
bot otherwise refuses.
"""

from __future__ import annotations

from unittest import mock

from django.test import override_settings
from movies.models import TelegramChannel
from users.models import SupportMessage, TelegramUser

from .. import callbacks as cb
from ..models import BotSettings
from ..texts import SUPPORT_EMPTY, SUPPORT_FAILED, SUPPORT_SENT, SUPPORT_TOO_SOON
from .base import DispatcherTestCase
from .fakes import USER, build_callback, build_command, build_message
from .helpers import make_channel

TOKEN = "123456:test-bot-token"


def recording_client(captured, *, status_code: int = 200):
	"""Stand-in for ``httpx.Client`` that records every Bot API call."""

	class _Response:
		def __init__(self) -> None:
			self.status_code = status_code
			self.text = "ok" if status_code == 200 else "rejected"

	class _Client:
		def __init__(self, *args, **kwargs) -> None:
			pass

		def __enter__(self):
			return self

		def __exit__(self, *exc):
			return False

		def post(self, url, data=None, files=None):
			captured.append((url, data or {}))
			return _Response()

	return _Client


class SupportFlowTests(DispatcherTestCase):
	def setUp(self) -> None:
		super().setUp()
		self.feed(build_command("start"))
		self.update_id = 400

	def _press(self, data: str) -> None:
		self.update_id += 1
		self.feed(build_callback(data, update_id=self.update_id))

	def _write(self, text: str, *, captured, status_code: int = 200, admins: str = "111,222"):
		self._press(cb.SUPPORT)
		self.session.reset()
		with mock.patch(
			"users.telegram_notify.httpx.Client",
			recording_client(captured, status_code=status_code),
		), override_settings(ADMIN_IDS=admins, BOT_ADMIN_IDS=admins, BOT_TOKEN=TOKEN):
			self.update_id += 1
			self.feed(build_message(text, update_id=self.update_id))

	def test_the_main_menu_offers_the_button(self) -> None:
		self.feed(build_callback(cb.MENU, update_id=410))

		self.assertIn("✉️ Adminga xabar", self.button_texts())

	def test_the_button_opens_the_writing_prompt(self) -> None:
		self.session.reset()
		self._press(cb.SUPPORT)

		self.assertIn("Adminga xabar", self.all_text())

	def test_a_typed_message_is_stored_and_sent_to_every_admin(self) -> None:
		captured = []

		self._write("Obuna to'lovim tasdiqlanmadi, yordam bering.", captured=captured)

		self.assertIn(SUPPORT_SENT.split("\n")[0].replace("</b>", ""), self.all_text())
		message = SupportMessage.objects.get()
		self.assertEqual(message.text, "Obuna to'lovim tasdiqlanmadi, yordam bering.")
		self.assertEqual(message.source, SupportMessage.Source.BOT)
		self.assertEqual(message.status, SupportMessage.Status.SENT)
		self.assertEqual(message.telegram_id, USER.id)
		self.assertEqual(message.error, "")

		self.assertEqual(len(captured), 2, "one Bot API call per administrator")
		for url, data in captured:
			self.assertIn("/sendMessage", url)
			self.assertIn("Obuna to'lovim tasdiqlanmadi", data["text"])
		self.assertEqual(
			{data["chat_id"] for _url, data in captured},
			{111, 222},
		)

	def test_the_admin_notice_names_the_sender(self) -> None:
		captured = []

		self._write("Salom", captured=captured)

		_caption = captured[0][1]["text"]
		self.assertIn(f"<code>{USER.id}</code>", _caption)
		self.assertIn("Foydalanuvchi xabari", _caption)

	def test_a_photo_message_is_refused_instead_of_stored(self) -> None:
		self._press(cb.SUPPORT)
		self.session.reset()

		self.update_id += 1
		self.feed(build_message("", update_id=self.update_id))

		self.assertIn(SUPPORT_EMPTY, self.all_text())
		self.assertEqual(SupportMessage.objects.count(), 0)

	def test_two_messages_in_a_row_are_rate_limited(self) -> None:
		captured = []
		self._write("Birinchi xabar", captured=captured)

		self._write("Ikkinchi xabar", captured=captured)

		self.assertIn(SUPPORT_TOO_SOON.split("\n")[0], self.all_text())
		self.assertEqual(SupportMessage.objects.count(), 1)
		self.assertEqual(len(captured), 2, "the second message never reaches Telegram")

	def test_a_telegram_failure_is_reported_and_the_message_is_kept(self) -> None:
		captured = []

		self._write("Yuborilmaydigan xabar", captured=captured, status_code=500)

		self.assertIn(SUPPORT_FAILED.split("\n")[0], self.all_text())
		message = SupportMessage.objects.get()
		self.assertEqual(message.status, SupportMessage.Status.FAILED)
		self.assertIn("500", message.error)
		self.assertEqual(message.text, "Yuborilmaydigan xabar")

	def test_missing_admin_configuration_is_reported_as_failure(self) -> None:
		captured = []

		self._write("Adminsiz xabar", captured=captured, admins="")

		self.assertIn(SUPPORT_FAILED.split("\n")[0], self.all_text())
		self.assertEqual(SupportMessage.objects.get().status, SupportMessage.Status.FAILED)
		self.assertEqual(captured, [])

	def test_a_user_without_the_mandatory_subscription_can_still_write(self) -> None:
		"""The contact screen stays open: it is what a stuck user needs."""
		settings = BotSettings.get_solo()
		settings.require_subscription = True
		settings.save(update_fields=["require_subscription", "updated_at"])
		make_channel(
			chat_id=-1005550007777,
			title="Majburiy kanal",
			purpose=TelegramChannel.Purpose.REQUIRED,
		)
		self.session.member_status = "left"
		captured = []

		self._write("Kanalga qo'shildim, lekin bot tanimayapti", captured=captured)

		self.assertNotIn("Majburiy obuna", self.all_text())
		self.assertEqual(SupportMessage.objects.count(), 1)
		self.assertEqual(len(captured), 2)

	def test_an_unsubscribed_user_is_still_refused_elsewhere(self) -> None:
		"""Guard the exception: only the support screen is exempt."""
		settings = BotSettings.get_solo()
		settings.require_subscription = True
		settings.save(update_fields=["require_subscription", "updated_at"])
		make_channel(
			chat_id=-1005550007778,
			title="Majburiy kanal",
			purpose=TelegramChannel.Purpose.REQUIRED,
		)
		self.session.member_status = "left"

		self.session.reset()
		self._press(cb.CATALOG_MENU)

		self.assertIn("Majburiy obuna", self.all_text())
		self.assertEqual(TelegramUser.objects.filter(telegram_id=USER.id).count(), 1)
