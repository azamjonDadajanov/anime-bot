import secrets

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import Q
from django.template.defaultfilters import slugify

def default_available_plans():
	return ["free", "plus", "pro"]


class TelegramChannel(models.Model):
	class Purpose(models.TextChoices):
		REQUIRED = "required", "Majburiy obuna"
		STORAGE = "storage", "Cloud saqlash"
		PUBLIC = "public", "Ommaviy kanal"

	chat_id = models.BigIntegerField(unique=True)
	title = models.CharField(max_length=200)
	username = models.CharField(max_length=64, blank=True)
	is_active = models.BooleanField(default=True)
	is_public = models.BooleanField(default=False)
	purpose = models.CharField(
		max_length=10,
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


class MediaTitle(models.Model):
	class AccessPlan(models.TextChoices):
		FREE = "free", "Free"
		PLUS = "plus", "Plus"
		PRO = "pro", "Pro"

	class MediaType(models.TextChoices):
		ANIME = "anime", "Anime"
		SERIES = "series", "Serial"
		MANGA = "manga", "Manga"
		MOVIE = "movie", "Kino"

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
	language = models.CharField(max_length=40, default="O'zbekcha")
	required_plan = models.CharField(
		max_length=4,
		choices=AccessPlan.choices,
		default=AccessPlan.FREE,
	)
	rating = models.PositiveSmallIntegerField(default=5)
	cover = models.BinaryField(blank=True, null=True)
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
	created_at = models.DateTimeField(auto_now_add=True)
	updated_at = models.DateTimeField(auto_now=True)

	class Meta:
		ordering = ["title"]

	def __str__(self):
		return self.title

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
