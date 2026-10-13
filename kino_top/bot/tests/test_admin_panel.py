"""Administrator panel tests driven through the real Dispatcher.

Two guarantees are checked here:

* a non-administrator can never reach an administrative action, whatever
  callback data the client sends;
* every button the panel renders does something -- the keyboards are built with
  real fixtures, their callback payloads are harvested, and each payload is fed
  through the real Dispatcher (routers, middlewares and handlers). A button that
  silently does nothing fails the test.
"""

from __future__ import annotations

from movies.models import MediaTitle, TelegramChannel
from users.models import TelegramUser

from .. import callbacks as cb
from ..keyboards import admin as kb
from ..models import BotLogEntry, BotSettings, Broadcast, FSMState
from ..texts import ACCESS_DENIED_GENERIC, ADMIN_ONLY
from .base import DispatcherTestCase
from .fakes import ADMIN, BOT_TOKEN, USER, build_callback, build_command
from .helpers import bot_env, make_channel, make_genre, make_media, make_part, make_title

RESPONSES = {
	"SendMessage",
	"EditMessageText",
	"EditMessageCaption",
	"EditMessageReplyMarkup",
	"SendPhoto",
	"SendVideo",
	"SendDocument",
	"SendMediaGroup",
	"AnswerCallbackQuery",
	"DeleteMessage",
	"CopyMessage",
	"ForwardMessage",
}


class AdminGuardTests(DispatcherTestCase):
	"""Nobody outside ADMIN_IDS may reach the panel."""

	def test_non_administrator_callback_is_refused(self) -> None:
		with bot_env(ADMIN_IDS="", BOT_TOKEN=BOT_TOKEN):
			self.feed(build_callback(cb.ADM_STATS, user=USER))

		refusals = self.session.methods("AnswerCallbackQuery")
		self.assertTrue(refusals)
		self.assertEqual(refusals[0].text, ADMIN_ONLY)
		self.assertIn(ADMIN_ONLY, self.visible())

	def test_non_administrator_command_is_refused(self) -> None:
		with bot_env(ADMIN_IDS="", BOT_TOKEN=BOT_TOKEN):
			self.feed(build_command("admin", user=USER))

		self.assertIn(ADMIN_ONLY, self.visible())
		self.assertNotIn("Sozlamalar", self.visible())

	def test_administrator_sees_the_panel(self) -> None:
		with bot_env(ADMIN_IDS=str(ADMIN.id), BOT_TOKEN=BOT_TOKEN):
			self.feed(build_command("admin", user=ADMIN))

		visible = self.visible()
		for section in ("Kontent", "Qismlar", "Kanallar", "Broadcast", "Foydalanuvchilar", "Sozlamalar", "Jurnallar"):
			self.assertIn(section, visible)


class AdminPanelButtonTests(DispatcherTestCase):
	"""Every rendered button must answer a click, as an administrator."""

	def setUp(self) -> None:
		super().setUp()
		env = bot_env(ADMIN_IDS=str(ADMIN.id), BOT_TOKEN=BOT_TOKEN)
		env.__enter__()
		self.addCleanup(env.__exit__, None, None, None)

		# A profile registered through the real /start flow.
		self.feed(build_command("start", user=USER))
		self.profile = TelegramUser.objects.get(telegram_id=USER.id)

		self.genre = make_genre("Action")
		self.title = make_title(code="1234", title="Panel Anime")
		self.title.genres.add(self.genre)
		self.part = make_part(self.title, number=1, season=1, part_title="Pilot")

		self.required = make_channel(
			chat_id=-1007770000001, title="Majburiy", purpose=TelegramChannel.Purpose.REQUIRED
		)
		self.storage = make_channel(
			chat_id=-1007770000002, title="Cloud", purpose=TelegramChannel.Purpose.STORAGE
		)
		self.public = make_channel(
			chat_id=-1007770000003,
			title="Ommaviy",
			purpose=TelegramChannel.Purpose.PUBLIC,
			username="kinotop_news",
		)
		self.media = make_media(
			self.part, file_id="panel-video", media_type="video", channel=self.storage
		)
		self.broadcast = Broadcast.objects.create(
			admin_telegram_id=ADMIN.id,
			kind=Broadcast.Kind.TEXT,
			text="Salom!",
			status=Broadcast.Status.COMPLETED,
			total=1,
			sent_count=1,
		)
		BotLogEntry.objects.create(level=BotLogEntry.Level.WARNING, logger="test", message="Sinov xatosi")
		BotSettings.get_solo()
		self.session.reset()
		self.update_id = 500

	# ------------------------------------------------------------------ helpers
	def click(self, data: str) -> None:
		"""Press one inline button as the administrator."""
		FSMState.objects.all().delete()  # never inherit a previous flow's state
		self.session.reset()
		self.update_id += 1
		self.feed(build_callback(data, user=ADMIN, update_id=self.update_id))

		names = {type(method).__name__ for method in self.session.calls}
		self.assertTrue(names & RESPONSES, f"pressing {data!r} produced no Telegram call")

		alerts = " ".join(
			str(method.text or "") for method in self.session.methods("AnswerCallbackQuery")
		)
		visible = self.visible()
		self.assertNotIn(ADMIN_ONLY, f"{alerts}\n{visible}", f"{data!r} was refused as a non-admin")
		self.assertNotIn(
			ACCESS_DENIED_GENERIC, f"{alerts}\n{visible}", f"{data!r} hit the access-denied path"
		)

	def harvest(self) -> list[str]:
		"""Every callback payload the panel can render with the current fixtures."""
		payloads: list[str] = []

		def collect(markup) -> None:
			# Uniqueness is asserted per keyboard: the same payload (e.g. the
			# "🏠 Panel" shortcut) legitimately recurs across keyboards.
			seen: set[str] = set()
			for row in markup.inline_keyboard:
				for button in row:
					if button.callback_data and button.callback_data != cb.NOOP:
						self.assertNotIn(
							button.callback_data,
							seen,
							f"duplicate payload {button.callback_data!r} inside one keyboard",
						)
						seen.add(button.callback_data)
						payloads.append(button.callback_data)

		collect(kb.admin_panel())
		collect(kb.media_menu())
		collect(kb.media_types())
		collect(kb.media_list([self.title], 1, 1))
		collect(kb.media_actions(self.title))
		collect(kb.media_edit_fields(self.title))
		collect(
			kb.value_choice_keyboard(
				f"{cb.ADM_MEDIA}:plan",
				[("Free", "free"), ("Plus", "plus")],
				back=f"{cb.ADM_MEDIA}:view:{self.title.pk}",
			)
		)
		collect(kb.episodes_menu())
		collect(kb.title_picker([self.title], 1, 1))
		collect(kb.parts_list([self.part], self.title.pk, 1, 1))
		collect(
			kb.part_actions(
				self.part, title_pk=self.title.pk, page=1, media_items=[self.media]
			)
		)
		collect(kb.channels_menu())
		collect(kb.channel_purposes(f"{cb.ADM_CHANNELS}:new"))
		collect(
			kb.channel_picker(
				list(TelegramChannel.objects.all()), f"{cb.ADM_EPISODES}:ch"
			)
		)
		for purpose in TelegramChannel.Purpose.values:
			channels = list(TelegramChannel.objects.filter(purpose=purpose))
			collect(kb.channels_list(channels, purpose, 1, 1))
			for channel in channels:
				collect(kb.channel_actions(channel, purpose=purpose, page=1))
				collect(kb.channel_edit_fields(channel, purpose=purpose, page=1))
		collect(kb.broadcast_menu())
		collect(kb.broadcast_history([self.broadcast], 1, 1))
		collect(kb.broadcast_actions(self.broadcast))
		collect(kb.broadcast_preview(self.broadcast.pk))
		collect(kb.broadcast_running(self.broadcast.pk))
		collect(kb.users_menu())
		collect(kb.user_results([self.profile]))
		collect(kb.user_actions(self.profile))
		collect(kb.plan_picker(self.profile.telegram_id))
		collect(kb.settings_menu(BotSettings.get_solo()))
		collect(kb.settings_channel_picker([self.public]))
		collect(kb.logs_menu())
		return payloads

	# -------------------------------------------------------------------- tests
	def test_the_panel_exposes_a_broad_set_of_buttons(self) -> None:
		payloads = self.harvest()
		self.assertGreater(len(payloads), 40)
		# Many keyboards repeat shared shortcuts; the set of distinct payloads
		# must still be broad.
		self.assertGreater(len(set(payloads)), 40)

	def test_every_harvested_button_answers(self) -> None:
		for data in self.harvest():
			with self.subTest(data=data):
				self.click(data)

	def test_panel_navigation_renders_every_section(self) -> None:
		for data, expected in (
			(cb.ADM_STATS, "Statistika"),
			(cb.ADM_MEDIA, "Kontent boshqaruvi"),
			(cb.ADM_EPISODES, "Qismlar"),
			(cb.ADM_CHANNELS, "Kanallar"),
			(cb.ADM_BROADCAST, "Broadcast"),
			(cb.ADM_USERS, "Foydalanuvchilar"),
			(cb.ADM_SETTINGS, "Sozlamalar"),
			(cb.ADM_LOGS, "Jurnallar"),
		):
			with self.subTest(section=data):
				self.click(data)
				self.assertIn(expected, self.visible())

	def test_destructive_action_asks_for_confirmation(self) -> None:
		self.click(f"{cb.ADM_MEDIA}:del:{self.title.pk}:1")

		self.assertIn("tasdiqlayman", self.visible().lower())
		# Nothing is deleted until the confirmation button is pressed.
		self.assertTrue(MediaTitle.objects.filter(pk=self.title.pk).exists())

	def test_cancelling_a_confirmation_keeps_the_row(self) -> None:
		self.click(f"{cb.ADM_MEDIA}:del:{self.title.pk}:1")
		self.click(f"{cb.ADM_MEDIA}:view:{self.title.pk}")

		self.assertTrue(MediaTitle.objects.filter(pk=self.title.pk).exists())

	def test_confirmed_deletion_removes_the_title(self) -> None:
		self.click(f"{cb.ADM_MEDIA}:del:{self.title.pk}:1")
		self.click(f"{cb.ADM_MEDIA}:delok:{self.title.pk}:1")

		self.assertFalse(MediaTitle.objects.filter(pk=self.title.pk).exists())
