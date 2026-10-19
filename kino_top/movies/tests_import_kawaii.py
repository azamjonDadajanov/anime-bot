"""Unit tests for the kawaii.uz importer's parsing helpers.

These stay offline: they exercise the name parser, the JSON-LD extractor and
the metadata mapper against a trimmed copy of a real ``/anime/<hash_id>`` page.
Deduplication (slug / title+type) is covered with a lightweight fake ORM.
"""

from types import SimpleNamespace
from unittest.mock import patch

from django.test import SimpleTestCase

from movies.management.commands.import_kawaii import (
	Command,
	build_metadata,
	derive_status,
	extract_ld_graphs,
	find_catalog_node,
	guess_image_type,
	map_media_type,
	normalize_rating,
	parse_names,
)

ANIME_PAGE = """
<div class="wrap"><!--$--><!--/$--><script type="application/ld+json">{"@context":"https://schema.org","@graph":[{"@type":"TVSeries","@id":"https://bot.kawaii.uz/anime/rqtzpkrd#anime","name":"Uyalchang","alternateName":["Shy","Стесняшка"],"description":"Yaponiya qahramoni Shy sifatida yashirin kimligi bilan mashhur.","image":"https://cdn.kawaii.uz/kawaii-bot-media/posters/ea003f17.webp","url":"https://bot.kawaii.uz/anime/rqtzpkrd","inLanguage":"uz-UZ","genre":["Jangari","Drama","G'ayritabiiy kuch","Shonen"],"datePublished":"2023","numberOfEpisodes":12,"contentRating":"13 yoshdan kattalar uchun (PG-13)","aggregateRating":{"@type":"AggregateRating","ratingValue":6.72,"bestRating":"10","worstRating":"1","ratingCount":28246},"productionStatus":"https://schema.org/CompletedActionStatus"},{"@type":"BreadcrumbList","@id":"https://bot.kawaii.uz/anime/rqtzpkrd#breadcrumb","itemListElement":[]},{"@type":"WebPage","@id":"https://bot.kawaii.uz/anime/rqtzpkrd#webpage","name":"Uyalchang"}]}</script><main><h1>Uyalchang</h1><a href="https://telegram.me/kawaii_uz_bot?start=a-rqtzpkrd">Tomosha qilish</a></main></div>
"""

SEARCH_ITEM = {
	"hash_id": "rqtzpkrd",
	"title_uzb": "Uyalchang",
	"title_org": "Shy",
	"type_uzb": "TV serial",
	"year": 2023,
	"episode_kawaii": 12,
	"episode_source": 12,
	"poster": "https://cdn.kawaii.uz/kawaii-bot-media/posters/ea003f17.webp",
}


class ParseNamesTests(SimpleTestCase):
	def test_telegram_menu_dump_is_parsed(self) -> None:
		text = (
			"📌----♧◇ Anime Menyu ◇♧---- 1-Bo'lim\n\n"
			"1. [Bleach (https://t.me/Bleachuz/5)]\n"
			"2. [Re:Zero -Hayotni no'ldan boshlash- (https://t.me/x/1)]\n"
			"203. [Sinfdagi qiz] (https://t.me/Chiroyli_qiz)\n"
			"⚠️👇Keyngi Bo'lim Pasda👇⚠️\n"
			"••••••••••  2-BO'LIM  •••••••••• (https://t.me/Anime_uzbekcha/1037)\n"
		)
		self.assertEqual(
			parse_names(text),
			["Bleach", "Re:Zero -Hayotni no'ldan boshlash-", "Sinfdagi qiz"],
		)

	def test_plain_lines_are_parsed_and_deduplicated(self) -> None:
		self.assertEqual(parse_names("Naruto\nnaruto\n\nBleach\n"), ["Naruto", "Bleach"])


class JsonLdTests(SimpleTestCase):
	def test_only_the_anime_node_is_selected(self) -> None:
		node = find_catalog_node(extract_ld_graphs(ANIME_PAGE))
		self.assertIsNotNone(node)
		self.assertEqual(node["@type"], "TVSeries")
		self.assertEqual(node["name"], "Uyalchang")

	def test_metadata_is_built_from_the_page(self) -> None:
		node = find_catalog_node(extract_ld_graphs(ANIME_PAGE))
		metadata = build_metadata("rqtzpkrd", SEARCH_ITEM, node, ANIME_PAGE)

		self.assertEqual(metadata["title"], "Uyalchang")
		self.assertEqual(metadata["type"], "series")
		self.assertEqual(metadata["year"], 2023)
		self.assertEqual(metadata["episodes"], 12)
		self.assertEqual(metadata["rating"], 7)
		self.assertEqual(metadata["status"], "completed")
		self.assertEqual(
			metadata["genres"], ["Jangari", "Drama", "G'ayritabiiy kuch", "Shonen"]
		)
		self.assertIn("Asl nomi: Shy", metadata["synopsis"])
		self.assertTrue(metadata["poster"].startswith("https://cdn.kawaii.uz/"))


class MappingTests(SimpleTestCase):
	def test_media_type(self) -> None:
		self.assertEqual(map_media_type("TV serial", None, ""), "series")
		self.assertEqual(map_media_type("Film", None, ""), "movie")
		self.assertEqual(map_media_type("Manga", None, ""), "manga")
		self.assertEqual(map_media_type("", "Movie", ""), "movie")
		self.assertEqual(map_media_type("", None, "s"), "series")
		self.assertEqual(map_media_type("OVA", None, ""), "anime")

	def test_status(self) -> None:
		self.assertEqual(derive_status("https://schema.org/CompletedActionStatus", 12, 12), "completed")
		self.assertEqual(derive_status("", 5, 12), "ongoing")
		self.assertEqual(derive_status("", 12, 12), "completed")
		self.assertEqual(derive_status("", 0, None), "upcoming")

	def test_rating_and_image_type(self) -> None:
		self.assertEqual(normalize_rating(6.72), 7)
		self.assertEqual(normalize_rating(12), 10)
		self.assertIsNone(normalize_rating("n/a"))
		self.assertEqual(guess_image_type("https://x/y.webp"), "image/webp")
		self.assertEqual(guess_image_type("https://x/y.png?v=2"), "image/png")


class DedupTests(SimpleTestCase):
	"""Already-imported titles (slug or title+type) must never be re-created."""

	def _command(self) -> Command:
		return Command()

	def test_slug_match_marks_imported(self) -> None:
		cmd = self._command()
		with patch("movies.management.commands.import_kawaii.MediaTitle") as model:
			model.objects.filter.return_value.exists.return_value = True
			self.assertTrue(cmd._already_imported("rqtzpkrd", "Uyalchang", "series"))
			model.objects.filter.assert_called_with(slug="rqtzpkrd")

	def test_title_and_type_match_marks_imported(self) -> None:
		cmd = self._command()
		existing = SimpleNamespace(slug="uyalchang-series")

		class _QS:
			def exists(self):
				return True

		def filter(**kwargs):
			if kwargs.get("slug") == "rqtzpkrd":
				return SimpleNamespace(exists=lambda: False)
			if kwargs == {"title__iexact": "Uyalchang", "type": "series"}:
				return _QS()
			raise AssertionError(f"unexpected filter: {kwargs}")

		with patch("movies.management.commands.import_kawaii.MediaTitle") as model:
			model.objects.filter.side_effect = filter
			self.assertTrue(cmd._already_imported("rqtzpkrd", "Uyalchang", "series"))

	def test_unknown_title_is_not_imported(self) -> None:
		cmd = self._command()

		class _QS:
			def exists(self):
				return False

		with patch("movies.management.commands.import_kawaii.MediaTitle") as model:
			model.objects.filter.side_effect = lambda **kw: _QS()
			self.assertFalse(cmd._already_imported("newhash", "Yangi", "anime"))
