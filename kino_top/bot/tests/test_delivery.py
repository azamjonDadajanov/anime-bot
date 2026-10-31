"""Media delivery tests: file selection, fallback and failure handling."""

from __future__ import annotations

import html
import asyncio

from aiogram.exceptions import TelegramBadRequest
from aiogram.types import Chat, Message
from django.test import TransactionTestCase
from movies.models import MediaPart, MediaTitle, TelegramMedia

from ..services.media import (
	MediaUnavailable,
	deliver_part,
	select_media_for_delivery_sync,
)
from .fakes import NOW, FakeSession, make_bot
from .helpers import make_media, make_part, make_title
from .helpers import bot_env, make_channel


def load_part(part) -> MediaPart:
	return MediaPart.objects.select_related("content").get(pk=part.pk)


def gone(method):
	return TelegramBadRequest(method=method, message="Bad Request: file is not found")


class DeliverySelectionTests(TransactionTestCase):
	def test_video_part_is_delivered_by_file_id(self) -> None:
		title = make_title(code="1001")
		part = load_part(make_part(title))
		make_media(part, file_id="video-file-id", media_type="video")

		bot = make_bot(FakeSession())
		sent = asyncio.run(deliver_part(bot, 111, part))

		self.assertEqual(len(sent), 1)
		self.assertEqual(bot.session.delivered_file_ids(), ["video-file-id"])

	def test_document_part_is_answered_with_a_website_link(self) -> None:
		"""PDF chapters are never attached: a downloadable file must not be sent."""
		title = make_title(code="1002")
		part = load_part(make_part(title))
		make_media(part, file_id="doc-file-id", media_type="document")

		session = FakeSession()
		with bot_env(BOT_SITE_URL="https://kino.test"):
			sent = asyncio.run(deliver_part(make_bot(session), 111, part))

		self.assertEqual(session.methods("SendDocument"), [])
		messages = session.methods("SendMessage")
		self.assertEqual(len(messages), 1)
		self.assertIn(f"https://kino.test/read/{title.slug}/1", messages[0].text)
		self.assertEqual(len(sent), 1)

	def test_document_part_without_site_url_reports_unavailable(self) -> None:
		title = make_title(code="1012")
		part = load_part(make_part(title))
		make_media(part, file_id="doc-only", media_type="document")

		session = FakeSession()
		with bot_env(BOT_SITE_URL=None):
			with self.assertRaises(MediaUnavailable):
				asyncio.run(deliver_part(make_bot(session), 111, part))

		self.assertEqual(session.methods("SendDocument"), [])

	def test_photo_only_part_sends_every_page_as_a_group(self) -> None:
		title = make_title(code="1003")
		part = load_part(make_part(title))
		for order in (1, 2, 3):
			make_media(part, file_id=f"page-{order}", media_type="photo", order=order)

		session = FakeSession()
		sent = asyncio.run(deliver_part(make_bot(session), 111, part))

		self.assertEqual(len(session.methods("SendMediaGroup")), 1)
		group = session.methods("SendMediaGroup")[0]
		self.assertEqual([item.media for item in group.media], ["page-1", "page-2", "page-3"])
		self.assertEqual(len(sent), 1)  # the fake returns one message per group

	def test_quality_selects_the_matching_variant(self) -> None:
		title = make_title(code="1004")
		part = load_part(make_part(title))
		make_media(part, file_id="low", media_type="video", order=1, caption="480p sifat")
		make_media(part, file_id="high", media_type="video", order=2, caption="1080p sifat")
		make_media(part, file_id="mid", media_type="video", order=3, caption="720p sifat")

		# Every stored copy stays available as a fallback, requested quality first.
		chosen = select_media_for_delivery_sync(part, "720")
		self.assertEqual(chosen[0].file_id, "mid")
		self.assertEqual(
			{item.file_id for item in chosen}, {"low", "high", "mid"}
		)

		default = select_media_for_delivery_sync(part)
		self.assertEqual(default[0].file_id, "low")
		self.assertEqual(len(default), 3)

	def test_pdf_documents_are_never_delivery_candidates(self) -> None:
		title = make_title(code="1014")
		part = load_part(make_part(title))
		make_media(part, file_id="doc", media_type="document")

		self.assertEqual(select_media_for_delivery_sync(part), [])


class DeliveryFallbackTests(TransactionTestCase):
	def test_stale_file_falls_back_to_the_next_stored_copy(self) -> None:
		title = make_title(code="1005")
		part = load_part(make_part(title))
		make_media(part, file_id="stale-file", media_type="video", order=1)
		make_media(part, file_id="good-file", media_type="video", order=2)

		calls = {"count": 0}

		async def responder(method):
			# Only the first stored file is stale; the second must still be sent.
			calls["count"] += 1
			if calls["count"] == 1:
				raise gone(method)
			return Message(
				message_id=1,
				date=NOW,
				chat=Chat(id=int(method.chat_id), type="private"),
			)

		session = FakeSession(responders={"SendVideo": responder})
		sent = asyncio.run(deliver_part(make_bot(session), 111, part))

		self.assertEqual(len(sent), 1)
		self.assertEqual(calls["count"], 2)

	def test_media_unavailable_when_every_copy_is_gone(self) -> None:
		title = make_title(code="1006")
		part = load_part(make_part(title))
		make_media(part, file_id="stale-1", media_type="video", order=1)
		make_media(part, file_id="stale-2", media_type="video", order=2)

		session = FakeSession(responders={"SendVideo": gone})
		with self.assertRaises(MediaUnavailable):
			asyncio.run(deliver_part(make_bot(session), 111, part))

	def test_part_without_files_raises(self) -> None:
		title = make_title(code="1007")
		part = load_part(make_part(title))

		with self.assertRaises(MediaUnavailable):
			asyncio.run(deliver_part(make_bot(FakeSession()), 111, part))

	def test_protect_content_is_forwarded_to_telegram(self) -> None:
		title = make_title(code="1008")
		part = load_part(make_part(title))
		make_media(part, file_id="protected-file", media_type="video")

		session = FakeSession()
		asyncio.run(deliver_part(make_bot(session), 111, part, protect_content=True))

		self.assertTrue(session.methods("SendVideo")[0].protect_content)

	def test_delivery_caption_describes_the_part_not_the_cloud_message(self) -> None:
		"""The stored caption (Cloud text, VIP promo) must never reach the user."""
		title = make_title(code="1015", title="Naruto")
		MediaTitle.objects.filter(pk=title.pk).update(episode_count=12)
		part = load_part(make_part(title, number=5, season=2))
		make_media(
			part,
			file_id="video-file",
			media_type="video",
			caption="Naruto\n2-5\n\nVIPga obuna bo'ling",
		)

		session = FakeSession()
		asyncio.run(deliver_part(make_bot(session), 111, part))

		sent = session.methods("SendVideo")[0]
		self.assertEqual(sent.caption, "🎬 <b>Naruto</b>\n🎞 5/12\n📺 2-fasl")

	def test_delivery_caption_omits_the_season_line_when_there_is_none(self) -> None:
		title = make_title(code="1016", title="Kino")
		part = load_part(make_part(title, number=1))
		make_media(part, file_id="movie-file", media_type="video")

		session = FakeSession()
		asyncio.run(deliver_part(make_bot(session), 111, part))

		sent = session.methods("SendVideo")[0]
		self.assertEqual(sent.caption, "🎬 <b>Kino</b>\n🎞 1/1")

	def test_delivery_caption_escapes_the_title_for_html(self) -> None:
		"""Telegram rejects an unescaped ``&`` in an HTML caption."""
		title = make_title(code="1017", title="Tom & Jerry")
		part = load_part(make_part(title, number=1))
		make_media(part, file_id="escaped-file", media_type="video")

		session = FakeSession()
		asyncio.run(deliver_part(make_bot(session), 111, part))

		sent = session.methods("SendVideo")[0]
		self.assertEqual(
			sent.caption,
			f"🎬 <b>{html.escape('Tom & Jerry', quote=False)}</b>\n🎞 1/1",
		)

	def test_storage_channel_metadata_is_preserved(self) -> None:
		title = make_title(code="1009")
		part = load_part(make_part(title))
		channel = make_channel(chat_id=-100999)
		media = make_media(
			part,
			file_id="channel-file",
			media_type="video",
			channel=channel,
			source_message_id=4242,
		)

		self.assertEqual(media.channel_id, channel.pk)
		self.assertEqual(media.source_message_id, 4242)
		self.assertEqual(TelegramMedia.objects.get(pk=media.pk).file_id, "channel-file")
