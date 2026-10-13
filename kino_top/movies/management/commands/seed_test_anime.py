"""``python manage.py seed_test_anime`` — create test catalog data.

Creates N titles split across all media types (anime, kino, serial, manga),
each with ``--parts`` episodes. Every episode gets a ``TelegramMedia`` row that
reuses a ``file_id`` already present in the database (by default the first
existing video), so the seeded content is playable without uploading anything.
"""

from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils.text import slugify

from movies.models import Genre, MediaPart, MediaTitle, TelegramChannel, TelegramMedia

SEED_MARKER = "TEST-SEED"

ANIME_TITLES = [
	"Osmondagi Qilich",
	"Tungi Ovchi",
	"Yashil Vodiy",
	"Temir Yurak",
	"Yulduzlar Sayyohi",
	"Qorli Cho'qqi",
	"Alanga Ruhi",
	"Sokin Okean",
	"Soya Jarchisi",
	"Oltin Ajdar",
	"Bulutlar Usti",
	"Yong'in Qushi",
	"Muz Malikasi",
	"Qum Bo'roni",
	"Yashirin Qal'a",
	"Osmon Burguti",
	"Kuchli Iroda",
	"Bahor Shamoli",
	"Qora Bo'ri",
	"Nurli Kelajak",
	"Sirlar Kitobi",
	"Abadiy Sayohat",
	"Kichik Qahramon",
	"Katta Orzular",
	"Oq Kabutar",
	"Tungi Farishta",
	"Qizil Tong",
	"Yulduzli Tun",
	"Sehrli O'rmon",
	"Buyuk Yo'l",
	"Zangori Olov",
	"Kumush Nayza",
	"Temir Qalpoq",
	"Yashil Kamon",
	"Osmon Kaliti",
	"Zulmat Panohi",
	"Quyosh Bolasi",
	"Oy Yorug'i",
	"Shamol Chavandozi",
	"Tosh Qal'a",
	"Yulduz Jangi",
	"Sirli Orol",
	"Bahodir Ruhi",
	"Kichik Dunyo",
	"Katta Sirlar",
	"Osmonsaroy",
	"Qahramon Yo'li",
	"Abadiy Olov",
	"Nur Qushi",
	"Zafar Tongi",
]

TYPE_ORDER = [
	MediaTitle.MediaType.ANIME,
	MediaTitle.MediaType.MOVIE,
	MediaTitle.MediaType.SERIES,
	MediaTitle.MediaType.MANGA,
]

TYPE_LABELS = {
	MediaTitle.MediaType.ANIME: "anime",
	MediaTitle.MediaType.MOVIE: "kino",
	MediaTitle.MediaType.SERIES: "serial",
	MediaTitle.MediaType.MANGA: "manga",
}

GENRE_NAMES = [
	"Jangari",
	"Sarguzasht",
	"Fantaziya",
	"Drama",
	"Komediya",
	"Romantika",
	"Sehr",
	"Ilmiy fantastika",
	"Triller",
	"Sirli",
]

STATUSES = ["completed", "ongoing", "upcoming"]
PLANS = ["free", "plus", "pro"]
LANGUAGES = ["O'zbekcha", "Yaponcha"]
QUALITY_OPTIONS = ["480", "720", "1080"]


class Command(BaseCommand):
	help = (
		"Seed test catalog data for every media type (anime, kino, serial, "
		"manga) that reuses an existing Telegram video file_id from the database."
	)

	def add_arguments(self, parser) -> None:
		parser.add_argument("--count", type=int, default=50, help="Number of titles to create.")
		parser.add_argument("--parts", type=int, default=24, help="Episodes (parts) per title.")
		parser.add_argument(
			"--types",
			type=str,
			default=",".join(TYPE_ORDER),
			help="Comma separated media types to distribute titles across.",
		)
		parser.add_argument("--file-id", type=str, default=None, help="Explicit Telegram video file_id to reuse.")
		parser.add_argument("--channel", type=int, default=None, help="TelegramChannel id to attach the media to.")
		parser.add_argument("--reset", action="store_true", help="Delete previously seeded test rows first.")

	def handle(self, *args, **options) -> None:
		count = max(int(options["count"]), 0)
		parts_per = max(int(options["parts"]), 1)
		types = self._resolve_types(options["types"])

		file_id, channel, media_type = self._resolve_source(options)
		self.stdout.write(f"Reusing file_id: {file_id}")
		self.stdout.write(f"Channel: {channel} | media_type: {media_type}")
		self.stdout.write(f"Types: {', '.join(TYPE_LABELS[t] for t in types)}")

		if options["reset"]:
			removed = MediaTitle.objects.filter(synopsis__contains=SEED_MARKER).delete()[0]
			self.stdout.write(self.style.WARNING(f"Reset: removed {removed} previously seeded rows."))

		genres = [Genre.objects.get_or_create(name=name)[0] for name in GENRE_NAMES]

		titles_created = 0
		parts_created = 0
		media_created = 0
		per_type = {media_type_key: 0 for media_type_key in TYPE_ORDER}

		with transaction.atomic():
			for index in range(count):
				name = self._title_for(index)
				title_type = types[index % len(types)]

				if MediaTitle.objects.filter(title=name, type=title_type).exists():
					continue

				slug = self._unique_slug(name, title_type)
				synopsis = f"{name} — namunaviy {TYPE_LABELS[title_type]} tavsifi. [{SEED_MARKER}]"

				media = MediaTitle(
					type=title_type,
					title=name,
					slug=slug,
					synopsis=synopsis,
					episode_count=parts_per,
					quality_options=QUALITY_OPTIONS,
					default_quality="1080",
					language=LANGUAGES[index % len(LANGUAGES)],
					required_plan=PLANS[index % len(PLANS)],
					rating=(index % 10) + 1,
					release_year=2008 + (index % 18),
					status=STATUSES[index % len(STATUSES)],
				)
				media.save()
				media.genres.set([genres[index % len(genres)], genres[(index + 3) % len(genres)]])
				titles_created += 1
				per_type[title_type] += 1

				parts = [
					MediaPart(content=media, number=number, title=f"{number}-qism")
					for number in range(1, parts_per + 1)
				]
				MediaPart.objects.bulk_create(parts)

				telegram_items = [
					TelegramMedia(
						part=part,
						channel=channel,
						file_id=file_id,
						media_type=media_type,
						order=1,
						caption=f"{name} · {part.number}-qism",
					)
					for part in parts
				]
				TelegramMedia.objects.bulk_create(telegram_items)

				parts_created += len(parts)
				media_created += len(telegram_items)

		summary = ", ".join(
			f"{TYPE_LABELS[t]}: {per_type[t]}" for t in TYPE_ORDER if t in per_type
		)
		self.stdout.write(
			self.style.SUCCESS(
				f"Created {titles_created} titles ({summary}), "
				f"{parts_created} parts, {media_created} telegram media rows."
			)
		)

	def _resolve_types(self, raw: str):
		requested = [value.strip() for value in str(raw).split(",") if value.strip()]
		valid = set(TYPE_ORDER)
		types = [value for value in requested if value in valid]
		if not types:
			raise CommandError(f"No valid media types given; choose from {', '.join(TYPE_ORDER)}.")
		return types

	def _resolve_source(self, options):
		file_id = options["file_id"]
		if file_id:
			source = TelegramMedia.objects.filter(file_id=file_id).first()
			if source is None:
				raise CommandError(f"No TelegramMedia row found for file_id {file_id!r}.")
		else:
			source = (
				TelegramMedia.objects.filter(media_type=TelegramMedia.MediaType.VIDEO)
				.order_by("id")
				.first()
			)
			if source is None:
				source = TelegramMedia.objects.order_by("id").first()
			if source is None:
				raise CommandError("No TelegramMedia rows exist; pass --file-id with a real file id.")

		channel_id = options["channel"]
		if channel_id:
			channel = TelegramChannel.objects.filter(id=channel_id).first()
			if channel is None:
				raise CommandError(f"No TelegramChannel with id {channel_id}.")
		else:
			channel = source.channel or TelegramChannel.objects.order_by("id").first()

		return source.file_id, channel, source.media_type

	def _title_for(self, index: int) -> str:
		base = ANIME_TITLES[index % len(ANIME_TITLES)]
		if index < len(ANIME_TITLES):
			return base
		return f"{base} {index + 1}"

	def _unique_slug(self, name: str, media_type: str) -> str:
		base = slugify(f"{name} {media_type}") or f"{media_type}-{name}"
		slug = base
		counter = 2
		while MediaTitle.objects.filter(slug=slug).exists():
			slug = f"{base}-{counter}"
			counter += 1
		return slug
