import hashlib
import secrets

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import Count, Q
from django.template.defaultfilters import slugify

def default_available_plans():
	return ["free", "paid"]


class TelegramChannel(models.Model):
	class Purpose(models.TextChoices):
		# E'lon (announcement) kanallari katalog bo'limlari bo'yicha taqsimlanadi.
		ANIME_ONGOING = "anime_ongoing", "Animelar · Ongoing"
		ANIME_COMPLETED = "anime_completed", "Animelar · Tugagan"
		ANIME_VIP = "anime_vip", "Animelar · VIP"
		MOVIE = "movie", "Kinolar"
		MOVIE_VIP = "movie_vip", "Kinolar · VIP"
		MANGA_ONGOING = "manga_ongoing", "Mangalar · Ongoing"
		MANGA_COMPLETED = "manga_completed", "Mangalar · Tugagan"
		MANGA_VIP = "manga_vip", "Mangalar · VIP"
		# E'lon uchun ishlatilmaydigan kanallar.
		REQUIRED = "required", "Majburiy obuna"
		STORAGE = "storage", "Cloud saqlash"
		PUBLIC = "public", "Ommaviy kanal"

	chat_id = models.BigIntegerField(unique=True)
	title = models.CharField(max_length=200)
	username = models.CharField(max_length=64, blank=True)
	is_active = models.BooleanField(default=True)
	is_public = models.BooleanField(default=False)
	purpose = models.CharField(
		max_length=20,
		choices=Purpose.choices,
		default=Purpose.STORAGE,
	)
	invite_link = models.CharField(max_length=255, blank=True)
	last_checked_at = models.DateTimeField(null=True, blank=True)
	last_check_ok = models.BooleanField(default=False)
	check_details = models.JSONField(default=dict, blank=True)
	created_at = models.DateTimeField(auto_now_add=True)

	class Meta:
		ordering = ["title"]

	def __str__(self):
		return self.title

	def save(self, *args, **kwargs):
		# Keep the legacy `is_public` flag consistent with the new purpose field
		# so existing API clients and admin screens keep working.
		self.is_public = self.purpose == self.Purpose.PUBLIC
		if not self.invite_link and self.username:
			self.invite_link = f"https://t.me/{self.username.lstrip('@')}"
		super().save(*args, **kwargs)


class Genre(models.Model):
	name = models.CharField(max_length=50, unique=True)

	class Meta:
		ordering = ["name"]

	def __str__(self):
		return self.name


class MediaTitleQuerySet(models.QuerySet):
	def with_counts(self):
		"""Parts and quiz questions per title, computed in the listing query.

		``movies_count``/``quizess_count`` are otherwise one COUNT per row,
		so a page of 20 titles used to cost 40 extra queries (N+1).
		``distinct=True`` keeps the numbers right even when the same query
		also joins genres or another multi-valued relation.
		"""
		return self.annotate(
			_movies_count=Count("parts", distinct=True),
			_quizess_count=Count("quiz_questions", distinct=True),
		)


class MediaTitle(models.Model):
	objects = MediaTitleQuerySet.as_manager()

	class AccessPlan(models.TextChoices):
		FREE = "free", "Bepul"
		PAID = "paid", "Obunaga"

	class MediaType(models.TextChoices):
		ANIME = "anime", "Anime"
		SERIES = "series", "Serial"
		MANGA = "manga", "Manga"
		MOVIE = "movie", "Kino"
		PODCAST = "podcast", "Podcast"

	class Status(models.TextChoices):
		UPCOMING = "upcoming", "Kutilmoqda"
		ONGOING = "ongoing", "Davom etmoqda"
		COMPLETED = "completed", "Tugallangan"

	type = models.CharField(max_length=10, choices=MediaType.choices)
	title = models.CharField(max_length=200)
	slug = models.SlugField(max_length=220, unique=True)
	genres = models.ManyToManyField(Genre, related_name="media_titles", blank=True)
	code = models.CharField(max_length=4, unique=True, editable=False)
	synopsis = models.TextField(blank=True)
	episode_count = models.PositiveSmallIntegerField(null=True, blank=True)
	quality_options = models.JSONField(default=list, blank=True)
	default_quality = models.CharField(max_length=20, default="1080")
	# How long one episode/film runs. Shown in the announcement the panels post
	# to the public channel and to every bot user ("⏱ Davomiyligi: 24 daqiqa").
	duration_minutes = models.PositiveSmallIntegerField(
		null=True,
		blank=True,
		help_text="Bir qismning davomiyligi (daqiqa).",
	)
	language = models.CharField(max_length=40, default="O'zbekcha")
	required_plan = models.CharField(
		max_length=4,
		choices=AccessPlan.choices,
		default=AccessPlan.FREE,
	)
	# Legacy single-number rating the catalogue and the bot have always shown.
	# It is kept in sync with ``rating_average`` (rounded, only while at least
	# one user has scored the title) so existing lists and cards never change
	# meaning; the live user ratings live in ``TitleRating`` below.
	rating = models.PositiveSmallIntegerField(default=5)
	# User ratings (1-10, one per account): the average and how many accounts
	# scored the title. Both are denormalised by ``movies.community`` so a
	# catalogue page never has to aggregate, and every platform (site, bot,
	# panel) reads exactly the same numbers.
	rating_average = models.FloatField(default=0.0)
	rating_count = models.PositiveIntegerField(default=0)
	# The cover is a real media file under MEDIA_ROOT/covers/, served by nginx
	# with long-lived cache headers. It used to be a BinaryField inlined as
	# base64 in every catalogue response, which no client could cache.
	cover = models.ImageField(upload_to="covers/", blank=True, null=True)
	cover_content_type = models.CharField(max_length=50, blank=True)
	metadata_channel = models.ForeignKey(
		TelegramChannel,
		on_delete=models.SET_NULL,
		null=True,
		blank=True,
		related_name="metadata_posts",
	)
	metadata_message_id = models.PositiveBigIntegerField(null=True, blank=True)
	release_year = models.PositiveSmallIntegerField(null=True, blank=True)
	status = models.CharField(
		max_length=10,
		choices=Status.choices,
		default=Status.UPCOMING,
	)
	quiz_size = models.PositiveSmallIntegerField(
		null=True,
		blank=True,
		help_text="Ko'rgach javob beriladigan savollar soni (bo'sh = global sozlama).",
	)
	created_at = models.DateTimeField(auto_now_add=True)
	updated_at = models.DateTimeField(auto_now=True)

	class Meta:
		ordering = ["title"]

	def __str__(self):
		return self.title

	def movies_count(self):
		# ``with_counts()`` supplies the number in the listing query itself;
		# the COUNT only runs for a single object that was never annotated
		# (a detail page, the admin, the bot).
		annotated = self.__dict__.get("_movies_count")
		return self.parts.count() if annotated is None else annotated

	def quizess_count(self):
		annotated = self.__dict__.get("_quizess_count")
		return self.quiz_questions.count() if annotated is None else annotated

	def save(self, *args, **kwargs):
		if not self.code:
			for _ in range(100):
				candidate = str(secrets.randbelow(9000) + 1000)
				if not type(self).objects.filter(code=candidate).exists():
					self.code = candidate
					break
			if not self.code:
				used_codes = set(type(self).objects.values_list("code", flat=True))
				available_codes = [
					str(number)
					for number in range(1000, 10000)
					if str(number) not in used_codes
				]
				if not available_codes:
					raise ValidationError("All 9000 four-digit media codes are in use.")
				self.code = secrets.choice(available_codes)
		if not self.slug:
			self.slug = slugify(self.title+self.type)
		super().save(*args, **kwargs)


class MediaPart(models.Model):
	content = models.ForeignKey(
		MediaTitle,
		on_delete=models.CASCADE,
		related_name="parts",
	)
	season_number = models.PositiveSmallIntegerField(null=True, blank=True)
	number = models.PositiveSmallIntegerField(validators=[MinValueValidator(1)])
	title = models.CharField(max_length=200, blank=True)
	pdf = models.FileField(upload_to="manga/pdf/", blank=True, null=True)
	created_at = models.DateTimeField(auto_now_add=True)

	class Meta:
		ordering = ["content", "season_number", "number"]
		constraints = [
			models.UniqueConstraint(
				fields=["content", "season_number", "number"],
				condition=Q(season_number__isnull=False),
				name="unique_part_per_season",
			),
			models.UniqueConstraint(
				fields=["content", "number"],
				condition=Q(season_number__isnull=True),
				name="unique_part_without_season",
			),
		]

	def __str__(self):
		return f"{self.content} - {self.number}"


class TelegramMedia(models.Model):
	class MediaType(models.TextChoices):
		VIDEO = "video", "Video"
		PHOTO = "photo", "Rasm"
		DOCUMENT = "document", "Fayl"

	part = models.ForeignKey(
		MediaPart,
		on_delete=models.CASCADE,
		related_name="telegram_media",
	)
	channel = models.ForeignKey(
		TelegramChannel,
		on_delete=models.SET_NULL,
		null=True,
		blank=True,
		related_name="media_items",
	)
	source_message_id = models.PositiveBigIntegerField(null=True, blank=True)
	file_id = models.CharField(max_length=512)
	media_type = models.CharField(max_length=10, choices=MediaType.choices)
	order = models.PositiveSmallIntegerField(validators=[MinValueValidator(1)])
	caption = models.CharField(max_length=1024, blank=True)

	class Meta:
		ordering = ["part", "order"]
		constraints = [
			models.UniqueConstraint(
				fields=["part", "order"],
				name="unique_telegram_media_order",
			),
			models.UniqueConstraint(
				fields=["channel", "source_message_id"],
				condition=Q(channel__isnull=False, source_message_id__isnull=False),
				name="unique_channel_source_message",
			),
		]

	def __str__(self):
		return f"{self.part} - {self.get_media_type_display()} {self.order}"


class MediaView(models.Model):
	"""Latest watch/read activity per user, one row per title.

	The bot records a view when it delivers content and the website records one
	when a media page is opened, so "Oxirgi faolliklar" and "Oxirgi ko'rgan
	medialar" can show real data instead of guessing from favourites.
	"""

	class Source(models.TextChoices):
		SITE = "site", "Sayt"
		BOT = "bot", "Bot"

	user = models.ForeignKey(
		settings.AUTH_USER_MODEL,
		on_delete=models.CASCADE,
		related_name="media_views",
	)
	title = models.ForeignKey(
		MediaTitle,
		on_delete=models.CASCADE,
		related_name="views",
	)
	part = models.ForeignKey(
		MediaPart,
		on_delete=models.SET_NULL,
		null=True,
		blank=True,
		related_name="views",
	)
	source = models.CharField(max_length=8, choices=Source.choices, default=Source.SITE)
	count = models.PositiveIntegerField(default=1)
	created_at = models.DateTimeField(auto_now_add=True)
	updated_at = models.DateTimeField(auto_now=True)

	class Meta:
		ordering = ["-updated_at"]
		constraints = [
			models.UniqueConstraint(
				fields=["user", "title"],
				name="unique_user_title_view",
			),
		]
		indexes = [models.Index(fields=["user", "-updated_at"], name="mediaview_user_idx")]

	def __str__(self):
		return f"{self.user} - {self.title}"

	@classmethod
	def record(cls, user, title, *, part=None, source=Source.SITE):
		"""Create or bump the single activity row for ``user`` and ``title``."""
		if user is None or title is None or not getattr(user, "pk", None):
			return None
		view, created = cls.objects.get_or_create(
			user=user,
			title=title,
			defaults={"part": part, "source": source},
		)
		if not created:
			if part is not None:
				view.part = part
			view.source = source
			view.count += 1
			view.save(update_fields=["part", "source", "count", "updated_at"])
		return view


class ReadingProgress(models.Model):
	"""Per-user manga reading position: which page of which part is left off.

	Stored server-side for logged-in users so the position follows them across
	devices. ``is_read`` is set once the last page of the part is reached.
	"""

	user = models.ForeignKey(
		settings.AUTH_USER_MODEL,
		on_delete=models.CASCADE,
		related_name="reading_progress",
	)
	part = models.ForeignKey(
		MediaPart,
		on_delete=models.CASCADE,
		related_name="reading_progress",
	)
	page = models.PositiveIntegerField(default=1)
	is_read = models.BooleanField(default=False)
	created_at = models.DateTimeField(auto_now_add=True)
	updated_at = models.DateTimeField(auto_now=True)

	class Meta:
		ordering = ["-updated_at"]
		constraints = [
			models.UniqueConstraint(
				fields=["user", "part"],
				name="unique_user_part_progress",
			),
		]

	def __str__(self):
		return f"{self.user} - {self.part} - {self.page}-sahifa"


class AIProvider(models.Model):
	"""One online chat model the AI assistant may call, in preference order.

	The assistant must survive a provider running out of quota, so it is not
	configured in one place but as a *chain* of rows: ``movies.llm`` reads them
	with a function and tries them one at a time (see
	:func:`movies.llm.provider_chain`). A row is also where the runtime state
	lives — measured latency, failure count, cooldown — so every gunicorn worker
	and the bot process share the same picture of which provider still works, and
	nothing has to be redeployed to add a key or re-order the chain.

	``priority`` is the operator's preference (lower first); ``avg_latency_ms``
	breaks ties in favour of the provider that already proved fast. A timeout or
	a "rate limit" answer sets ``cooldown_until``, so the next request skips it
	instead of paying for the same failure again.
	"""

	class Kind(models.TextChoices):
		GROQ = "groq", "Groq"
		GEMINI = "gemini", "Google Gemini"
		OPENAI = "openai", "OpenAI"
		CUSTOM = "custom", "Boshqa (OpenAI-mos)"
		# Called through the in-process Respan Gateway instead of directly:
		# the model is the route the gateway asks for (movies.gateway).
		GATEWAY = "gateway", "Respan Gateway"

	name = models.CharField(max_length=60, unique=True, help_text="Masalan: Groq (asosiy)")
	kind = models.CharField(max_length=20, choices=Kind.choices, default=Kind.GROQ)
	api_key = models.CharField(
		max_length=200,
		blank=True,
		help_text=(
			"Bo'sh bo'lsa .env'dagi AI_LLM_API_KEY ishlatiladi — faqat turi "
			"mos bo'lsa (masalan Gemini qatori uchun Gemini kaliti)."
		),
	)
	model = models.CharField(
		max_length=120, blank=True, help_text="Bo'sh = provayderning standart modeli."
	)
	base_url = models.CharField(
		max_length=200, blank=True, help_text="Bo'sh = provayderning standart manzili."
	)
	priority = models.PositiveSmallIntegerField(
		default=100, help_text="Kichik raqam avval uriniladi."
	)
	is_active = models.BooleanField(default=True)
	# A provider that cannot be asked for functions still answers: the
	# question goes to it without the catalogue, and the model is told so.
	supports_tools = models.BooleanField(
		default=True, help_text="Funksiyalar (katalog chaqiruvlari) qo'llab-quvvatlanadimi?"
	)
	# --- runtime state (written by movies.llm after every call) ---------------
	avg_latency_ms = models.PositiveIntegerField(default=0)
	success_count = models.PositiveIntegerField(default=0)
	failure_count = models.PositiveIntegerField(default=0)
	cooldown_until = models.DateTimeField(null=True, blank=True)
	last_error = models.CharField(max_length=200, blank=True)
	last_used_at = models.DateTimeField(null=True, blank=True)
	created_at = models.DateTimeField(auto_now_add=True)
	updated_at = models.DateTimeField(auto_now=True)

	class Meta:
		ordering = ["priority", "avg_latency_ms", "id"]
		verbose_name = "AI provayder"
		verbose_name_plural = "AI provayderlar"

	def __str__(self):
		return f"{self.name} ({self.kind})"

	@property
	def cooling_down(self) -> bool:
		"""True while this provider is being skipped after a failure."""
		from django.utils import timezone as _timezone

		return bool(self.cooldown_until and self.cooldown_until > _timezone.now())

	@property
	def masked_key(self) -> str:
		"""The key as it is safe to display (never the whole secret)."""
		value = (self.api_key or "").strip()
		if not value:
			return "—"
		if len(value) <= 8:
			return "•" * len(value)
		return f"{value[:4]}…{value[-4:]}"


class TitleComment(models.Model):
	"""One user's comment on a title, optionally tied to a single episode.

	The row is the canonical record shared by the website, the Telegram bot and
	the administrator panel: all three read and write this table, so a comment
	written in one place is visible in the other two without synchronisation.

	``dedupe_hash`` is a fingerprint of (user, title, episode, normalized text)
	with a unique constraint behind it — pressing "send" twice (a double tap in
	the bot, a re-submit on the site after a slow response) can no longer create
	a second row.
	"""

	class Source(models.TextChoices):
		SITE = "site", "Sayt"
		BOT = "bot", "Bot"

	MAX_LENGTH = 1000

	user = models.ForeignKey(
		settings.AUTH_USER_MODEL,
		on_delete=models.CASCADE,
		related_name="title_comments",
	)
	title = models.ForeignKey(
		MediaTitle,
		on_delete=models.CASCADE,
		related_name="comments",
	)
	# The episode the comment was written about (bot context, or the episode a
	# website visitor had selected); null means "about the title in general".
	part = models.ForeignKey(
		MediaPart,
		on_delete=models.SET_NULL,
		null=True,
		blank=True,
		related_name="comments",
	)
	body = models.TextField()
	source = models.CharField(max_length=8, choices=Source.choices, default=Source.SITE)
	dedupe_hash = models.CharField(max_length=64, editable=False, blank=True)
	created_at = models.DateTimeField(auto_now_add=True)
	updated_at = models.DateTimeField(auto_now=True)

	class Meta:
		ordering = ["-created_at", "-id"]
		constraints = [
			models.UniqueConstraint(
				fields=["user", "dedupe_hash"],
				name="unique_user_comment_fingerprint",
			),
		]
		indexes = [
			models.Index(fields=["title", "-created_at"], name="titlecomment_title_idx"),
			models.Index(fields=["part", "-created_at"], name="titlecomment_part_idx"),
			models.Index(fields=["-created_at"], name="titlecomment_created_idx"),
		]

	def __str__(self) -> str:
		return f"{self.user_id} → {self.title_id}: {self.body[:40]}"

	def compute_dedupe_hash(self) -> str:
		"""Fingerprint of *what* was written, ignoring case/spacing runs."""
		normalized = " ".join((self.body or "").split()).lower()
		raw = "|".join(
			[
				str(self.user_id or ""),
				str(self.title_id or ""),
				str(self.part_id or ""),
				normalized,
			]
		)
		return hashlib.sha256(raw.encode("utf-8")).hexdigest()

	def save(self, *args, **kwargs):
		if not self.dedupe_hash:
			self.dedupe_hash = self.compute_dedupe_hash()
		super().save(*args, **kwargs)


class TitleRating(models.Model):
	"""A user's 1-10 score of one title.

	One row per (user, title) enforced by the database, so an update (changing
	one's mind) rewrites the row instead of adding a duplicate. Ratings are kept
	**separate from comments**: editing or deleting a comment can never touch a
	score, and vice versa.
	"""

	MIN_SCORE = 1
	MAX_SCORE = 10

	user = models.ForeignKey(
		settings.AUTH_USER_MODEL,
		on_delete=models.CASCADE,
		related_name="title_ratings",
	)
	title = models.ForeignKey(
		MediaTitle,
		on_delete=models.CASCADE,
		related_name="user_ratings",
	)
	score = models.PositiveSmallIntegerField(
		validators=[MinValueValidator(MIN_SCORE), MaxValueValidator(MAX_SCORE)]
	)
	created_at = models.DateTimeField(auto_now_add=True)
	updated_at = models.DateTimeField(auto_now=True)

	class Meta:
		ordering = ["-updated_at"]
		constraints = [
			models.UniqueConstraint(
				fields=["user", "title"],
				name="unique_user_title_rating",
			),
		]
		indexes = [
			models.Index(fields=["title", "-updated_at"], name="titlerating_title_idx"),
		]

	def __str__(self) -> str:
		return f"{self.user_id} → {self.title_id}: {self.score}/10"

	def clean(self):
		if self.score < self.MIN_SCORE or self.score > self.MAX_SCORE:
			raise ValidationError({"score": f"Reyting {self.MIN_SCORE} dan {self.MAX_SCORE} gacha bo'lishi kerak."})

