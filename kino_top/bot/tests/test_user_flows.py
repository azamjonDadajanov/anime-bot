"""End-to-end user flow tests driven through a real aiogram Dispatcher."""

from __future__ import annotations

from datetime import timedelta

from django.utils import timezone
from movies.models import MediaTitle, TelegramChannel
from users.models import FavoriteContent, Subscription, TelegramUser

from .. import callbacks as cb
from ..texts import WATCH_PARTS_HINT
from .base import DispatcherTestCase
from .fakes import (
	USER,
	build_callback,
	build_command,
	build_message,
	fake_document,
	fake_photo,
	fake_video,
)
from .helpers import bot_env, make_channel, make_genre, make_media, make_part, make_title


class StartFlowTests(DispatcherTestCase):
	def test_start_registers_the_user_and_creates_the_subscription(self) -> None:
		self.feed(build_command("start"))

		profile = TelegramUser.objects.get(telegram_id=111)
		self.assertIsNotNone(profile.auth_user_id)
		# The pre-existing signal must have created the premium row.
		self.assertEqual(Subscription.objects.get(user=profile.auth_user).plan, "free")
		text = self.all_text()
		self.assertIn("AniChopar", text)
		self.assertIn("qidirish", text.lower())

	def test_second_start_greets_a_returning_user(self) -> None:
		self.feed(build_command("start"))
		self.session.reset()
		self.feed(build_command("start", update_id=2))

		self.assertIn("Xush kelibsiz", self.all_text())

	def test_deep_link_opens_the_title_card_by_code(self) -> None:
		title = make_title(code="1234", title="Naruto")
		self.feed(build_command("start", payload="anime_1234"))

		text = self.all_text()
		self.assertIn("Naruto", text)
		self.assertIn("1234", text)
		self.assertEqual(title.code, "1234")

	def test_deep_link_works_for_every_media_type_prefix(self) -> None:
		make_title(code="1200", title="Movie One", media_type=MediaTitle.MediaType.MOVIE)
		self.feed(build_command("start", payload="movie_1200"))
		self.assertIn("Movie One", self.all_text())

	def test_part_deep_link_opens_the_selected_part(self) -> None:
		title = make_title(code="1201", title="Deep Linked Series", media_type=MediaTitle.MediaType.SERIES)
		part = make_part(title, number=3, season=2, part_title="The Return")

		self.feed(build_command("start", payload=f"part_{part.pk}"))

		self.assertIn("Deep Linked Series", self.all_text())
		self.assertIn("3-qism", self.all_text())

	def test_unknown_deep_link_reports_not_found(self) -> None:
		self.feed(build_command("start", payload="anime_9999"))
		self.assertIn("topilmadi", self.all_text().lower())


class SubscriptionGateTests(DispatcherTestCase):
	def test_required_channel_blocks_the_deep_link(self) -> None:
		make_title(code="2222", title="Gated Anime")
		make_channel(
			chat_id=-1005550001111,
			title="Majburiy kanal",
			purpose=TelegramChannel.Purpose.REQUIRED,
		)
		self.session.member_status = "left"

		self.feed(build_command("start", payload="anime_2222"))

		text = self.all_text()
		self.assertIn("Majburiy obuna", text)
		self.assertNotIn("Gated Anime", text)

	def test_inactive_required_channel_is_not_enforced(self) -> None:
		make_title(code="2233", title="Open Anime")
		make_channel(
			chat_id=-1005550003333,
			title="O'chirilgan kanal",
			purpose=TelegramChannel.Purpose.REQUIRED,
			is_active=False,
		)
		self.session.member_status = "left"

		self.feed(build_command("start", payload="anime_2233"))

		self.assertIn("Open Anime", self.all_text())

	def test_storage_channels_are_never_required(self) -> None:
		make_title(code="2244", title="Free Anime")
		make_channel(chat_id=-1005550004444, purpose=TelegramChannel.Purpose.STORAGE)
		self.session.member_status = "left"

		self.feed(build_command("start", payload="anime_2244"))

		self.assertIn("Free Anime", self.all_text())

	def test_public_channels_are_mandatory(self) -> None:
		"""A public (ommaviy) channel is a mandatory-subscription channel too."""
		make_title(code="2245", title="Public Gated Anime")
		make_channel(
			chat_id=-1005550005555,
			title="Ommaviy kanal",
			purpose=TelegramChannel.Purpose.PUBLIC,
		)
		self.session.member_status = "left"

		self.feed(build_command("start", payload="anime_2245"))

		text = self.all_text()
		self.assertIn("Majburiy obuna", text)
		self.assertNotIn("Public Gated Anime", text)

	def test_the_gate_blocks_plain_actions_not_only_content(self) -> None:
		"""Without the subscription the user cannot use *any* feature."""
		make_channel(
			chat_id=-1005550007777,
			title="Majburiy kanal 3",
			purpose=TelegramChannel.Purpose.REQUIRED,
		)
		self.session.member_status = "left"

		self.feed(build_callback(cb.CATALOG_MENU))

		text = self.all_text()
		self.assertIn("Majburiy obuna", text)
		self.assertNotIn("Katalog", text)

	def test_the_gate_blocks_bare_code_messages(self) -> None:
		make_title(code="4712", title="Blocked Bleach")
		make_channel(
			chat_id=-1005550008888,
			title="Majburiy kanal 4",
			purpose=TelegramChannel.Purpose.REQUIRED,
		)
		self.session.member_status = "left"

		self.feed(build_message("4712"))

		text = self.all_text()
		self.assertIn("Majburiy obuna", text)
		self.assertNotIn("Blocked Bleach", text)

	def test_only_the_unjoined_channels_are_listed(self) -> None:
		"""Channels the user already joined must not be shown again."""
		from aiogram.types import ChatMemberLeft, ChatMemberMember

		joined = make_channel(
			chat_id=-1005550009111,
			title="Joined Channel",
			purpose=TelegramChannel.Purpose.REQUIRED,
		)
		make_channel(
			chat_id=-1005550009222,
			title="Pending Channel",
			purpose=TelegramChannel.Purpose.REQUIRED,
		)

		def membership(method):
			if int(getattr(method, "chat_id", 0)) == joined.chat_id:
				return ChatMemberMember(status="member", user=USER)
			return ChatMemberLeft(status="left", user=USER)

		self.session.responders["GetChatMember"] = membership

		self.feed(build_command("start"))

		text = self.all_text()
		self.assertIn("Majburiy obuna", text)
		self.assertIn("Pending Channel", text)
		self.assertNotIn("Joined Channel", text)

	def test_subscription_check_resumes_the_pending_delivery(self) -> None:
		title = make_title(code="3333", title="Resume Anime")
		part = make_part(title, number=1)
		make_media(part, file_id="resume-file-id", media_type="video")
		make_channel(
			chat_id=-1005550002222,
			title="Majburiy kanal 2",
			purpose=TelegramChannel.Purpose.REQUIRED,
		)
		self.session.member_status = "left"

		self.feed(build_callback(f"watch:{part.pk}"))
		self.assertIn("Majburiy obuna", self.all_text())
		self.assertEqual(self.session.delivered_file_ids(), [])

		# The user subscribes and presses "check"; the pending part is delivered.
		self.session.member_status = "member"
		self.session.reset()
		self.feed(build_callback("subchk", update_id=3))

		self.assertEqual(self.session.delivered_file_ids(), ["resume-file-id"])

	def test_unverifiable_channel_fails_open(self) -> None:
		"""A channel the bot cannot inspect must not block the whole user base."""
		from aiogram.exceptions import TelegramBadRequest

		make_title(code="3344", title="Fail Open Anime")
		make_channel(
			chat_id=-1005550006666,
			purpose=TelegramChannel.Purpose.REQUIRED,
		)

		def raise_bad_request(method):
			return TelegramBadRequest(method=method, message="Bad Request: chat not found")

		self.session.responders["GetChatMember"] = raise_bad_request
		self.feed(build_command("start", payload="anime_3344"))

		self.assertIn("Fail Open Anime", self.all_text())


class PremiumGateTests(DispatcherTestCase):
	def test_free_user_cannot_watch_paid_content(self) -> None:
		title = make_title(code="4444", title="Paid Anime", required_plan="paid")
		part = make_part(title, number=1)
		make_media(part, file_id="paid-file-id", media_type="video")

		self.feed(build_callback(f"watch:{part.pk}"))

		self.assertIn("Faol obuna kerak", self.all_text())
		self.assertEqual(self.session.delivered_file_ids(), [])

	def test_a_subscription_unlocks_paid_content(self) -> None:
		title = make_title(code="5555", title="Paid Anime 2", required_plan="paid")
		part = make_part(title, number=1)
		make_media(part, file_id="paid-file-2", media_type="video")

		self.feed(build_command("start"))
		profile = TelegramUser.objects.get(telegram_id=111)
		subscription = Subscription.objects.get(user=profile.auth_user)
		subscription.activate("yearly")
		self.session.reset()

		self.feed(build_callback(f"watch:{part.pk}"))

		self.assertEqual(self.session.delivered_file_ids(), ["paid-file-2"])

	def test_an_expired_subscription_locks_paid_content_again(self) -> None:
		title = make_title(code="5566", title="Paid Anime 3", required_plan="paid")
		part = make_part(title, number=1)
		make_media(part, file_id="paid-file-3", media_type="video")

		self.feed(build_command("start"))
		profile = TelegramUser.objects.get(telegram_id=111)
		subscription = Subscription.objects.get(user=profile.auth_user)
		subscription.activate("daily")
		Subscription.objects.filter(pk=subscription.pk).update(
			expires_at=timezone.now() - timedelta(seconds=1)
		)
		self.session.reset()

		self.feed(build_callback(f"watch:{part.pk}"))

		self.assertIn("Faol obuna kerak", self.all_text())
		self.assertEqual(self.session.delivered_file_ids(), [])

	def test_premium_gate_is_not_applied_for_free_content(self) -> None:
		title = make_title(code="5577", title="Free Anime 2")
		part = make_part(title, number=1)
		make_media(part, file_id="free-file", media_type="video")

		self.feed(build_callback(f"watch:{part.pk}"))

		self.assertEqual(self.session.delivered_file_ids(), ["free-file"])


class BrowsingTests(DispatcherTestCase):
	def test_bare_code_message_opens_the_title_card(self) -> None:
		make_title(code="4711", title="Bleach")
		self.feed(build_message("4711"))
		self.assertIn("Bleach", self.all_text())

	def test_search_finds_titles_by_name(self) -> None:
		make_title(code="7777", title="One Piece")
		self.feed(build_callback("search"))
		self.feed(build_message("piece", update_id=9))
		self.assertIn("One Piece", self.visible())

	def test_search_screen_offers_type_genre_and_see_all(self) -> None:
		self.feed(build_callback("search"))

		text = self.visible()
		self.assertIn("Anime", text)
		self.assertIn("Janr bo'yicha", text)
		self.assertIn("Barchasini ko'rish", text)

	def test_search_can_filter_by_media_type(self) -> None:
		make_title(code="2001", title="Filter Anime", media_type=MediaTitle.MediaType.ANIME)
		make_title(code="2002", title="Filter Movie", media_type=MediaTitle.MediaType.MOVIE)

		self.feed(build_callback("sft:anime:1"))

		text = self.visible()
		self.assertIn("Filter Anime", text)
		self.assertNotIn("Filter Movie", text)

	def test_search_can_filter_by_genre(self) -> None:
		genre = make_genre("Comedy")
		matching = make_title(code="2003", title="Comedy Anime")
		matching.genres.add(genre)
		make_title(code="2004", title="Other Anime")

		self.feed(build_callback(f"sfgi:{genre.pk}:1"))

		text = self.visible()
		self.assertIn("Comedy Anime", text)
		self.assertNotIn("Other Anime", text)

	def test_search_see_all_lists_every_title(self) -> None:
		make_title(code="2005", title="Listed Anime", media_type=MediaTitle.MediaType.ANIME)
		make_title(code="2006", title="Listed Movie", media_type=MediaTitle.MediaType.MOVIE)

		self.feed(build_callback("sfall"))

		text = self.visible()
		self.assertIn("Listed Anime", text)
		self.assertIn("Listed Movie", text)

	def test_a_typed_query_refines_the_selected_type(self) -> None:
		make_title(code="2007", title="Naruto Anime", media_type=MediaTitle.MediaType.ANIME)
		make_title(code="2008", title="Naruto Movie", media_type=MediaTitle.MediaType.MOVIE)

		self.feed(build_callback("sft:anime:1"))
		self.session.reset()
		self.feed(build_message("naruto", update_id=11))

		text = self.visible()
		self.assertIn("Naruto Anime", text)
		self.assertNotIn("Naruto Movie", text)

	def test_search_can_paginate_inside_a_media_type(self) -> None:
		for index in range(12):
			make_title(code=f"30{index:02d}", title=f"Page Anime {index}", media_type=MediaTitle.MediaType.ANIME)

		self.feed(build_callback("sft:anime:2"))

		# Titles sort alphabetically, so 6-9 land on the second page (size 8).
		self.assertIn("Page Anime 6", self.visible())

	def test_see_all_results_can_paginate(self) -> None:
		for index in range(12):
			make_title(code=f"31{index:02d}", title=f"All Anime {index:02d}")

		self.feed(build_callback("sfall"))
		self.assertIn("All Anime 00", self.visible())

		# "Barchasini ko'rish" keeps every filter empty, so ``sres:2`` must
		# still remember the unfiltered list instead of bouncing to the menu.
		self.feed(build_callback("sres:2"))
		self.assertIn("All Anime 08", self.visible())

	def test_mini_app_button_appears_only_when_the_url_is_configured(self) -> None:
		with bot_env(BOT_WEBAPP_URL="https://example.test"):
			self.feed(build_callback("search"))
		self.assertIn("Ilovada qidirish", self.visible())

		self.session.reset()
		with bot_env(BOT_WEBAPP_URL=None):
			self.feed(build_callback("search", update_id=12))
		self.assertNotIn("Ilovada qidirish", self.visible())

	def test_main_menu_links_the_mini_app_when_configured(self) -> None:
		with bot_env(BOT_WEBAPP_URL="https://example.test"):
			self.feed(build_command("start"))

		buttons = []
		for method in self.session.calls:
			markup = getattr(method, "reply_markup", None)
			for row in getattr(markup, "inline_keyboard", None) or []:
				buttons.extend(row)
		app_buttons = [button for button in buttons if getattr(button, "web_app", None)]
		self.assertTrue(app_buttons, "Mini App button missing from the main menu")
		self.assertEqual(
			app_buttons[0].web_app.url,
			"https://example.test/telegram-auth",
		)

	def test_catalog_lists_titles_of_a_type(self) -> None:
		make_title(code="8888", title="Type Anime", media_type=MediaTitle.MediaType.ANIME)
		make_title(code="8889", title="Type Movie", media_type=MediaTitle.MediaType.MOVIE)

		self.feed(build_callback("type:anime:1"))

		text = self.visible()
		self.assertIn("Type Anime", text)
		self.assertNotIn("Type Movie", text)

	def test_genre_browsing_lists_matching_titles(self) -> None:
		from .helpers import make_genre

		title = make_title(code="8899", title="Genre Anime")
		title.genres.add(make_genre("Drama"))
		make_title(code="8891", title="Other Anime")

		self.feed(build_callback("g:1:1"))

		text = self.visible()
		self.assertIn("Genre Anime", text)
		self.assertNotIn("Other Anime", text)

	def test_favorites_can_be_toggled_and_listed(self) -> None:
		title = make_title(code="6666", title="Favorite Anime")

		self.feed(build_callback(f"favt:{title.pk}:1:cat"))
		self.assertEqual(FavoriteContent.objects.filter(content=title).count(), 1)

		self.session.reset()
		self.feed(build_callback("fav:1", update_id=4))
		self.assertIn("Favorite Anime", self.visible())

		self.session.reset()
		self.feed(build_callback(f"favt:{title.pk}:1:cat", update_id=5))
		self.assertEqual(FavoriteContent.objects.filter(content=title).count(), 0)

	def test_parts_and_part_card_render(self) -> None:
		title = make_title(code="9911", title="Parts Anime")
		part = make_part(title, number=1, season=1, part_title="Pilot")
		make_media(part, file_id="parts-file", media_type="video")

		self.feed(build_callback(f"p:list:{title.pk}:1"))
		self.assertIn("Pilot", self.visible())

		self.session.reset()
		self.feed(build_callback(f"p:view:{part.pk}", update_id=6))
		self.assertIn("1-qism", self.visible())

	def test_unknown_text_falls_back_to_help(self) -> None:
		self.feed(build_message("salom"))
		self.assertIn("Yordam", self.all_text())


class WatchButtonTests(DispatcherTestCase):
	"""The "ko'rish" button behaves per media type and stays private."""

	def _button_urls(self) -> str:
		urls = []
		for method in self.session.calls:
			markup = getattr(method, "reply_markup", None)
			rows = getattr(markup, "inline_keyboard", None) or []
			for row in rows:
				for button in row:
					if getattr(button, "url", None):
						urls.append(button.url)
		return "\n".join(urls)

	def test_movie_card_delivers_the_movie_in_one_tap(self) -> None:
		title = make_title(code="6001", title="Solo Movie", media_type=MediaTitle.MediaType.MOVIE)
		part = make_part(title, number=1)
		make_media(part, file_id="movie-file", media_type="video")

		self.feed(build_command("start", payload="movie_6001"))
		self.assertIn("Kinoni ko'rish", self.button_texts())

		self.session.reset()
		self.feed(build_callback(f"wt:{title.pk}", update_id=7))
		self.assertEqual(self.session.delivered_file_ids(), ["movie-file"])

	def test_anime_card_opens_the_parts_list(self) -> None:
		title = make_title(code="6002", title="Episodic Anime")
		make_part(title, number=1, season=1, part_title="Pilot")

		self.feed(build_command("start", payload="anime_6002"))
		self.assertIn("Animeni ko'rish", self.button_texts())

		self.session.reset()
		self.feed(build_callback(f"p:list:{title.pk}:1", update_id=7))
		self.assertIn("Pilot", self.visible())

	def test_manga_card_links_to_the_website(self) -> None:
		title = make_title(code="6003", title="Reader Manga", media_type=MediaTitle.MediaType.MANGA)
		with bot_env(BOT_SITE_URL="https://kino.test"):
			self.feed(build_command("start", payload="manga_6003"))
			self.assertIn("Saytda o'qish", self.button_texts())
			self.assertIn(f"https://kino.test/read/{title.slug}", self._button_urls())

	def test_manga_part_watch_redirects_to_the_website(self) -> None:
		title = make_title(code="6004", title="Gated Manga", media_type=MediaTitle.MediaType.MANGA)
		part = make_part(title, number=1)
		make_media(part, file_id="manga-page", media_type="photo")

		with bot_env(BOT_SITE_URL="https://kino.test"):
			self.feed(build_callback(f"watch:{part.pk}"))
			self.assertEqual(self.session.delivered_file_ids(), [])
			self.assertIn("Saytda o'qish", self.visible())
			self.assertIn(f"https://kino.test/read/{title.slug}", self._button_urls())

	def test_card_without_parts_still_offers_watch(self) -> None:
		title = make_title(code="6006", title="Empty Anime")

		self.feed(build_command("start", payload="anime_6006"))
		self.assertIn("Animeni ko'rish", self.button_texts())

		self.session.reset()
		self.feed(build_callback(f"p:list:{title.pk}:1", update_id=7))
		self.assertIn("qo'shilmagan", self.all_text().lower())

	def test_movie_without_parts_reports_empty(self) -> None:
		title = make_title(code="6007", title="Empty Movie", media_type=MediaTitle.MediaType.MOVIE)

		self.feed(build_command("start", payload="movie_6007"))
		self.assertIn("Kinoni ko'rish", self.button_texts())

		self.session.reset()
		self.feed(build_callback(f"wt:{title.pk}", update_id=7))
		self.assertEqual(self.session.delivered_file_ids(), [])
		self.assertIn("qo'shilmagan", self.all_text().lower())

	def test_manga_without_parts_still_links_to_the_website(self) -> None:
		title = make_title(code="6008", title="Empty Manga", media_type=MediaTitle.MediaType.MANGA)

		with bot_env(BOT_SITE_URL="https://kino.test"):
			self.feed(build_command("start", payload="manga_6008"))
			self.assertIn("Saytda o'qish", self.button_texts())
			self.assertIn(f"https://kino.test/read/{title.slug}", self._button_urls())

	def test_movie_button_pushes_only_the_first_part(self) -> None:
		"""The rest of the parts are offered as buttons, never dumped at once."""
		title = make_title(code="6009", title="Serial Movie", media_type=MediaTitle.MediaType.MOVIE)
		parts = [make_part(title, number=number) for number in (1, 2, 3)]
		for part in parts:
			make_media(part, file_id=f"movie-{part.number}", media_type="video", order=1)

		self.feed(build_callback(f"wt:{title.pk}"))

		self.assertEqual(self.session.delivered_file_ids(), ["movie-1"])
		videos = self.session.methods("SendVideo")
		self.assertEqual(len(videos), 1)
		rows = [[button.text for button in row] for row in videos[0].reply_markup.inline_keyboard]
		self.assertEqual(rows[0], ["🟢 1", "2", "3"])

	def test_delivered_media_blocks_forwarding(self) -> None:
		title = make_title(code="6005", title="Protected Anime")
		part = make_part(title, number=1)
		make_media(part, file_id="guard-file", media_type="video")

		self.feed(build_callback(f"watch:{part.pk}"))

		videos = self.session.methods("SendVideo")
		self.assertEqual(len(videos), 1)
		self.assertTrue(videos[0].protect_content)


class PartsNavigatorTests(DispatcherTestCase):
	"""The parts navigator that rides on every delivered part."""

	def _navigator(self):
		"""Inline keyboard of the last message the bot attached one to."""
		for method in reversed(self.session.calls):
			markup = getattr(method, "reply_markup", None)
			if markup is not None and getattr(markup, "inline_keyboard", None):
				return markup
		return None

	def _rows(self):
		markup = self._navigator()
		if markup is None:
			return []
		return [[button.text for button in row] for row in markup.inline_keyboard]

	def _callbacks(self):
		markup = self._navigator()
		if markup is None:
			return []
		return [[button.callback_data for button in row] for row in markup.inline_keyboard]

	def _season_parts(self, title, count: int = 3, season: int = 1):
		parts = [make_part(title, number=number, season=season) for number in range(1, count + 1)]
		for part in parts:
			make_media(part, file_id=f"file-{season}-{part.number}", media_type="video", order=1)
		return parts

	def test_delivered_part_carries_the_five_per_row_navigator(self) -> None:
		title = make_title(code="7001", title="Navigator Anime")
		parts = self._season_parts(title, count=7)

		self.feed(build_callback(f"watch:{parts[2].pk}"))

		self.assertEqual(self.session.delivered_file_ids(), ["file-1-3"])
		rows = self._rows()
		self.assertEqual(rows[0], ["1", "2", "🟢 3", "4", "5"])
		self.assertEqual(rows[1], ["6", "7"])
		self.assertEqual(rows[2], ["⬅️ Oldingi qism", "1-mavsum", "Keyingi qism ➡️"])

		callbacks = self._callbacks()
		self.assertEqual(callbacks[0][2], f"watch:{parts[2].pk}")
		self.assertEqual(callbacks[2][0], f"watch:{parts[1].pk}")
		self.assertEqual(callbacks[2][2], f"watch:{parts[3].pk}")

	def test_number_button_delivers_that_part_and_moves_the_green_marker(self) -> None:
		title = make_title(code="7002", title="Tap Anime")
		parts = self._season_parts(title, count=3)

		self.feed(build_callback(f"watch:{parts[0].pk}"))
		target = self._callbacks()[0][2]
		self.assertEqual(target, f"watch:{parts[2].pk}")

		self.session.reset()
		self.feed(build_callback(target, update_id=8))

		self.assertEqual(self.session.delivered_file_ids(), ["file-1-3"])
		self.assertEqual(self._rows()[0], ["1", "2", "🟢 3"])

	def test_next_arrow_rolls_into_the_next_season(self) -> None:
		title = make_title(code="7003", title="Two Seasons")
		first = self._season_parts(title, count=2, season=1)
		second = self._season_parts(title, count=2, season=2)

		self.feed(build_callback(f"watch:{first[1].pk}"))
		callbacks = self._callbacks()
		self.assertEqual(callbacks[1][2], f"watch:{second[0].pk}")

		self.session.reset()
		self.feed(build_callback(callbacks[1][2], update_id=9))

		# The next season is delivered with its own parts and first media.
		self.assertEqual(self.session.delivered_file_ids(), ["file-2-1"])
		rows = self._rows()
		self.assertEqual(rows[0], ["🟢 1", "2"])
		self.assertEqual(rows[1], ["⬅️ Oldingi qism", "2-mavsum", "Keyingi qism ➡️"])

	def test_arrows_are_inert_at_the_very_first_and_last_part(self) -> None:
		title = make_title(code="7004", title="Edge Anime")
		parts = self._season_parts(title, count=2)

		self.feed(build_callback(f"watch:{parts[0].pk}"))
		self.assertEqual(self._callbacks()[1][0], cb.NOOP)

		self.session.reset()
		self.feed(build_callback(f"watch:{parts[1].pk}", update_id=10))
		self.assertEqual(self._callbacks()[1][2], cb.NOOP)

	def test_long_season_is_paginated_ten_per_page(self) -> None:
		title = make_title(code="7005", title="Long Anime")
		parts = self._season_parts(title, count=12)

		self.feed(build_callback(f"watch:{parts[0].pk}"))
		rows = self._rows()
		self.assertEqual(rows[0], ["🟢 1", "2", "3", "4", "5"])
		self.assertEqual(rows[1], ["6", "7", "8", "9", "10"])
		self.assertEqual(rows[2], ["⬅️ Oldingi qism", "1-mavsum 1/2", "Keyingi qism ➡️"])

		self.session.reset()
		self.feed(build_callback(f"watch:{parts[10].pk}", update_id=11))
		rows = self._rows()
		self.assertEqual(rows[0], ["🟢 11", "12"])
		self.assertEqual(rows[1], ["⬅️ Oldingi qism", "1-mavsum 2/2", "Keyingi qism ➡️"])

	def test_unseasoned_parts_share_one_navigator(self) -> None:
		title = make_title(code="7006", title="No Season Anime")
		parts = [make_part(title, number=number) for number in (1, 2)]
		for part in parts:
			make_media(part, file_id=f"plain-{part.number}", media_type="video", order=1)

		self.feed(build_callback(f"watch:{parts[0].pk}"))

		self.assertEqual(self._rows()[1], ["⬅️ Oldingi qism", "Qismlar", "Keyingi qism ➡️"])

	def test_single_part_title_gets_no_navigator(self) -> None:
		title = make_title(code="7007", title="One Part")
		part = make_part(title, number=1, season=1)
		make_media(part, file_id="only-file", media_type="video", order=1)

		self.feed(build_callback(f"watch:{part.pk}"))

		self.assertEqual(self.session.delivered_file_ids(), ["only-file"])
		self.assertIsNone(self._navigator())

	def test_multi_page_part_posts_the_navigator_under_the_group(self) -> None:
		title = make_title(code="7008", title="Scanned Anime")
		parts = [make_part(title, number=number, season=1) for number in (1, 2)]
		make_media(parts[0], file_id="scan-1", media_type="photo", order=1)
		make_media(parts[0], file_id="scan-2", media_type="photo", order=2)
		make_media(parts[1], file_id="scan-3", media_type="photo", order=1)

		self.feed(build_callback(f"watch:{parts[0].pk}"))

		# A media group cannot carry a keyboard, so it goes out as its own message.
		self.assertEqual(len(self.session.methods("SendMediaGroup")), 1)
		hint = [
			method
			for method in self.session.methods("SendMessage")
			if method.text == WATCH_PARTS_HINT
		]
		self.assertEqual(len(hint), 1)
		rows = [[button.text for button in row] for row in hint[0].reply_markup.inline_keyboard]
		self.assertEqual(rows[0], ["🟢 1", "2"])


class InPlaceSwapTests(DispatcherTestCase):
	"""Tapping another part swaps the file inside the same message."""

	def _season(self, title, count: int = 3):
		parts = [make_part(title, number=number, season=1) for number in range(1, count + 1)]
		for part in parts:
			make_media(part, file_id=f"swap-{part.number}", media_type="video", order=1)
		return parts

	def _edit(self):
		edits = self.session.methods("EditMessageMedia")
		self.assertEqual(len(edits), 1)
		return edits[0]

	@staticmethod
	def _rows(markup):
		return [[button.text for button in row] for row in markup.inline_keyboard]

	def test_the_tapped_part_replaces_the_file_without_touching_the_message(self) -> None:
		title = make_title(code="7101", title="Swap Anime")
		parts = self._season(title)

		# Part 1 is on screen; the user taps part 3 in the navigator below it.
		self.feed(
			build_callback(
				f"watch:{parts[2].pk}",
				update_id=8,
				message_id=42,
				video=fake_video("swap-1"),
			)
		)

		edit = self._edit()
		self.assertEqual(edit.chat_id, USER.id)
		self.assertEqual(edit.message_id, 42)
		self.assertEqual(edit.media.media, "swap-3")
		# Nothing was deleted and no new message went out.
		self.assertEqual(self.session.methods("SendVideo"), [])
		self.assertEqual(self.session.methods("SendMessage"), [])
		self.assertEqual(self.session.methods("DeleteMessage"), [])

	def test_the_green_marker_moves_and_the_old_part_loses_it(self) -> None:
		title = make_title(code="7102", title="Marker Anime")
		parts = self._season(title)

		self.feed(
			build_callback(
				f"watch:{parts[1].pk}",
				update_id=8,
				message_id=42,
				video=fake_video("swap-1"),
			)
		)

		rows = self._rows(self._edit().reply_markup)
		self.assertEqual(rows[0], ["1", "🟢 2", "3"])
		self.assertEqual(rows[1], ["⬅️ Oldingi qism", "1-mavsum", "Keyingi qism ➡️"])

	def test_the_next_arrow_swaps_in_place_too(self) -> None:
		title = make_title(code="7103", title="Arrow Anime")
		parts = self._season(title)

		self.feed(
			build_callback(
				f"watch:{parts[1].pk}",
				update_id=8,
				message_id=42,
				video=fake_video("swap-1"),
			)
		)

		self.assertEqual(self._edit().media.media, "swap-2")

	def test_a_document_is_swapped_for_another_document(self) -> None:
		title = make_title(code="7107", title="Doc Anime")
		parts = [make_part(title, number=number, season=1) for number in (1, 2)]
		for part in parts:
			make_media(part, file_id=f"doc-{part.number}", media_type="document", order=1)

		self.feed(
			build_callback(
				f"watch:{parts[1].pk}",
				update_id=8,
				message_id=42,
				document=fake_document("doc-1"),
			)
		)

		self.assertEqual(self._edit().media.media, "doc-2")
		self.assertEqual(self.session.methods("SendDocument"), [])

	def test_a_different_file_kind_is_sent_as_a_new_message(self) -> None:
		"""Telegram cannot change a message's media type, so that falls back."""
		title = make_title(code="7104", title="Mixed Anime")
		parts = [make_part(title, number=number, season=1) for number in (1, 2)]
		make_media(parts[0], file_id="mixed-1", media_type="video", order=1)
		make_media(parts[1], file_id="mixed-2", media_type="document", order=1)

		self.feed(
			build_callback(
				f"watch:{parts[1].pk}",
				video=fake_video("mixed-1"),
			)
		)

		self.assertEqual(self.session.methods("EditMessageMedia"), [])
		self.assertEqual(self.session.delivered_file_ids(), ["mixed-2"])
		self.assertEqual(len(self.session.methods("SendDocument")), 1)

	def test_an_album_item_is_not_swapped_in_place(self) -> None:
		title = make_title(code="7105", title="Scanned Swap")
		parts = [make_part(title, number=number, season=1) for number in (1, 2)]
		make_media(parts[0], file_id="group-1", media_type="photo", order=1)
		make_media(parts[1], file_id="group-2", media_type="photo", order=1)

		self.feed(
			build_callback(
				f"watch:{parts[1].pk}",
				photo=fake_photo("group-1"),
				media_group_id="album-1",
			)
		)

		self.assertEqual(self.session.methods("EditMessageMedia"), [])
		self.assertEqual(self.session.delivered_file_ids(), ["group-2"])

	def test_tapping_the_part_already_watching_is_harmless(self) -> None:
		"""Telegram's "message is not modified" must not surface as an error."""
		from aiogram.exceptions import TelegramBadRequest

		title = make_title(code="7106", title="Same Part")
		parts = self._season(title)

		def unchanged(method):
			return TelegramBadRequest(method=method, message="Bad Request: message is not modified")

		self.session.responders["EditMessageMedia"] = unchanged
		self.feed(
			build_callback(
				f"watch:{parts[0].pk}",
				message_id=42,
				video=fake_video("swap-1"),
			)
		)

		self.assertEqual(self.session.delivered_file_ids(), [])
		self.assertEqual(self.session.methods("SendMessage"), [])
		self.assertEqual(len(self.session.methods("AnswerCallbackQuery")), 1)


class DecorativeButtonTests(DispatcherTestCase):
	def test_page_counter_is_acknowledged_without_editing_anything(self) -> None:
		"""Tapping "1/3" must close the Telegram spinner and change nothing."""
		self.feed(build_callback(cb.NOOP))

		answers = self.session.methods("AnswerCallbackQuery")
		self.assertEqual(len(answers), 1)
		self.assertFalse(getattr(answers[0], "show_alert", False))
		self.assertFalse(answers[0].text)
		self.assertEqual(self.session.methods("EditMessageText"), [])
		self.assertEqual(self.session.methods("SendMessage"), [])

	def test_counter_button_inside_a_real_keyboard_is_acknowledged(self) -> None:
		make_title(code="7700", title="Paged Anime")
		self.feed(build_callback("catmenu"))
		self.assertIn("Katalog", self.visible())

		self.session.reset()
		self.feed(build_callback(cb.NOOP, update_id=7))
		self.assertEqual(len(self.session.methods("AnswerCallbackQuery")), 1)
