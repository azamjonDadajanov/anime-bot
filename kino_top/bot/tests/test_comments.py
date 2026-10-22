"""💬 Izohlar: writing, reading and rating from inside Telegram.

The flow runs through the real dispatcher, so the FSM, the shared
``movies.community`` table and the re-delivered episode are all exercised the
same way a user experiences them: media → text → 1-10 score → the episode
comes back with its navigator.
"""

from __future__ import annotations

from unittest import mock

from movies import community
from movies.models import TitleComment, TitleRating
from users.models import TelegramUser

from .. import callbacks as cb
from ..texts import (
	CANCELLED,
	COMMENT_LIST_EMPTY,
	COMMENT_NO_ACCOUNT,
	COMMENT_SAVED,
)
from .base import DispatcherTestCase
from .fakes import USER, build_callback, build_command, build_message
from .helpers import make_media, make_part, make_title


class CommentWriteFlowTests(DispatcherTestCase):
	def setUp(self) -> None:
		super().setUp()
		self.feed(build_command("start"))
		self.update_id = 600
		self.title = make_title(code="9201", title="Comment Show")
		self.part = make_part(self.title, number=2, season=1)
		make_media(self.part, file_id="comment-file", media_type="video")

	def _press(self, data: str) -> None:
		self.update_id += 1
		self.feed(build_callback(data, update_id=self.update_id))

	def _write(self, text: str) -> None:
		self.update_id += 1
		self.feed(build_message(text, update_id=self.update_id))

	def _profile(self) -> TelegramUser:
		return TelegramUser.objects.get(telegram_id=USER.id)

	def _user(self):
		return self._profile().auth_user

	def test_the_delivered_episode_offers_the_comment_button(self) -> None:
		self.feed(build_callback(f"watch:{self.part.pk}"))

		self.assertIn("💬 Izoh qoldirish", self.button_texts())
		self.assertIn(f"cm:{self.title.pk}:{self.part.pk}", self.button_texts() + self._callbacks_text())

	def _callbacks_text(self) -> str:
		out = []
		for method in self.session.calls:
			markup = getattr(method, "reply_markup", None)
			for row in getattr(markup, "inline_keyboard", None) or []:
				for button in row:
					out.append(button.callback_data or "")
		return "\n".join(out)

	def test_the_title_card_offers_the_comment_list(self) -> None:
		self.feed(build_callback(f"t:{self.title.pk}:1:cat"))

		self.assertIn("💬 Izohlar", self.button_texts())
		self.assertIn(f"cml:{self.title.pk}:1", self._callbacks_text())

	def test_writing_a_comment_saves_it_and_re_delivers_the_episode(self) -> None:
		self._press(f"cm:{self.title.pk}:{self.part.pk}")

		self.assertIn("Izoh qoldirish", self.all_text())

		self.session.reset()
		self._write("Birinchi qism juda zo'r edi!")

		self.assertIn("Baho qoldiring", self.all_text())
		self.assertIn("1️⃣", self.button_texts())
		self.assertIn("🔟", self.button_texts())

		self.session.reset()
		self._press(f"{cb.COMMENT_RATE}:8")

		comment = TitleComment.objects.get(title=self.title)
		self.assertEqual(comment.user, self._user())
		self.assertEqual(comment.part, self.part)
		self.assertEqual(comment.source, TitleComment.Source.BOT)
		self.assertEqual(comment.body, "Birinchi qism juda zo'r edi!")
		rating = TitleRating.objects.get(user=self._user(), title=self.title)
		self.assertEqual(rating.score, 8)
		self.title.refresh_from_db()
		self.assertEqual(self.title.rating_average, 8.0)

		# The confirmation comes first, then the episode they were watching.
		self.assertIn(COMMENT_SAVED.split("\n")[0], self.all_text())
		self.assertIn("8", self.all_text())
		self.assertIn("comment-file", self.session.delivered_file_ids())

	def test_skipping_the_score_keeps_the_text_only(self) -> None:
		self._press(f"cm:{self.title.pk}")
		self._write("Faqat fikr, baho yo'q")
		self.session.reset()

		self._press(cb.COMMENT_RATE_SKIP)

		self.assertEqual(TitleComment.objects.count(), 1)
		self.assertFalse(TitleRating.objects.exists())
		self.assertEqual(self._callbacks_text().count(f"cm:{self.title.pk}"), 0)

	def test_an_empty_message_is_refused_and_the_flow_continues(self) -> None:
		self._press(f"cm:{self.title.pk}")
		self.session.reset()

		self._write("   ")

		self.assertFalse(TitleComment.objects.exists())
		self.assertIn("Izoh bo'sh", self.all_text())

		self._write("Endi normal fikr")
		self._press(f"{cb.COMMENT_RATE}:5")

		self.assertEqual(TitleComment.objects.get().body, "Endi normal fikr")

	def test_cancelling_leaves_nothing_behind(self) -> None:
		self._press(f"cm:{self.title.pk}")
		self._write("Ketayotgan fikr")
		self.session.reset()

		self._press(cb.COMMENT_CANCEL)

		self.assertIn(CANCELLED, self.all_text())
		self.assertFalse(TitleComment.objects.exists())
		self.assertFalse(TitleRating.objects.exists())

	def test_the_same_text_twice_becomes_one_comment(self) -> None:
		self._press(f"cm:{self.title.pk}")
		self._write("Takrorlanmas fikr")
		self._press(f"{cb.COMMENT_RATE}:7")

		self._press(f"cm:{self.title.pk}")
		self._write("Takrorlanmas fikr")
		self._press(f"{cb.COMMENT_RATE}:7")

		self.assertEqual(TitleComment.objects.filter(user=self._user()).count(), 1)

	def test_a_rating_button_without_a_pending_comment_says_so(self) -> None:
		self._press(f"{cb.COMMENT_RATE}:6")

		self.assertIn("vaqti tugadi", self.all_text())
		self.assertFalse(TitleComment.objects.exists())


class CommentListTests(DispatcherTestCase):
	def setUp(self) -> None:
		super().setUp()
		self.feed(build_command("start"))
		self.update_id = 700
		self.title = make_title(code="9202", title="Listed Show")
		self.user = TelegramUser.objects.get(telegram_id=USER.id).auth_user
		community.create_comment_sync(
			user=self.user, title=self.title, body="Saytda yozilgan fikr"
		)

	def test_the_list_shows_the_body_and_the_average(self) -> None:
		self.feed(build_callback(f"cml:{self.title.pk}:1", update_id=self.update_id))

		self.assertIn("Saytda yozilgan fikr", self.all_text())
		self.assertIn("Izohlar", self.all_text())

	def test_an_empty_title_explains_itself(self) -> None:
		empty = make_title(code="9203", title="Quiet Show")

		self.feed(build_callback(f"cml:{empty.pk}:1", update_id=self.update_id + 1))

		self.assertIn(COMMENT_LIST_EMPTY, self.all_text())

	def test_an_unknown_title_is_not_found(self) -> None:
		self.feed(build_callback("cml:999999:1", update_id=self.update_id + 2))

		self.assertIn("topilmadi", self.all_text())


class CommentAccessTests(DispatcherTestCase):
	def setUp(self) -> None:
		super().setUp()
		self.update_id = 800
		self.title = make_title(code="9204", title="Linked Show")

	def test_writing_requires_a_linked_account(self) -> None:
		self.feed(build_command("start", update_id=self.update_id))
		# A profile without a website account has nothing to write from.
		with mock.patch(
			"bot.handlers.user.comments.account_of", return_value=None
		):
			self.feed(build_callback(f"cm:{self.title.pk}", update_id=self.update_id + 1))

		self.assertIn(COMMENT_NO_ACCOUNT, self.all_text())
		self.assertFalse(TitleComment.objects.exists())
