from django.conf import settings
from django.db import models


class TelegramUser(models.Model):
	auth_user = models.OneToOneField(
		settings.AUTH_USER_MODEL,
		on_delete=models.CASCADE,
		null=True,
		blank=True,
		related_name="telegram_profile",
	)
	telegram_id = models.PositiveBigIntegerField(unique=True)
	username = models.CharField(max_length=64, blank=True)
	first_name = models.CharField(max_length=128, blank=True)
	last_name = models.CharField(max_length=128, blank=True)
	language_code = models.CharField(max_length=10, blank=True)
	is_blocked = models.BooleanField(default=False)
	panel_message_id = models.PositiveBigIntegerField(null=True, blank=True)
	panel_message_kind = models.CharField(max_length=8, default="text")
	temporary_message_ids = models.JSONField(default=list, blank=True)
	favorites = models.ManyToManyField(
		"movies.MediaTitle",
		through="FavoriteContent",
		related_name="favorited_by",
		blank=True,
	)
	created_at = models.DateTimeField(auto_now_add=True)
	updated_at = models.DateTimeField(auto_now=True)
	last_seen_at = models.DateTimeField(null=True, blank=True)

	class Meta:
		ordering = ["-created_at"]
		indexes = [models.Index(fields=["last_seen_at"], name="tguser_last_seen_idx")]

	def __str__(self):
		return self.username or self.first_name or str(self.telegram_id)


class UserSettings(models.Model):
	"""Per-user website preferences shown on the "Sozlamalar" profile tab."""

	class Theme(models.TextChoices):
		SYSTEM = "system", "Tizim"
		LIGHT = "light", "Kunduzgi"
		DARK = "dark", "Tungi"

	class Language(models.TextChoices):
		UZ = "uz", "O'zbekcha"
		RU = "ru", "Русский"
		EN = "en", "English"

	user = models.OneToOneField(
		settings.AUTH_USER_MODEL,
		on_delete=models.CASCADE,
		related_name="site_settings",
	)
	theme = models.CharField(max_length=6, choices=Theme.choices, default=Theme.SYSTEM)
	language = models.CharField(max_length=5, choices=Language.choices, default=Language.UZ)
	reduce_motion = models.BooleanField(default=False)
	updated_at = models.DateTimeField(auto_now=True)

	class Meta:
		verbose_name = "User settings"
		verbose_name_plural = "User settings"

	def __str__(self):
		return f"{self.user} - sozlamalar"


class Subscription(models.Model):
	class Plan(models.TextChoices):
		FREE = "free", "Free"
		PLUS = "plus", "Plus"
		PRO = "pro", "Pro"

	user = models.OneToOneField(
		settings.AUTH_USER_MODEL,
		on_delete=models.CASCADE,
		related_name="subscription",
	)
	plan = models.CharField(max_length=4, choices=Plan.choices, default=Plan.FREE)
	updated_at = models.DateTimeField(auto_now=True)

	class Meta:
		ordering = ["user_id"]

	def __str__(self):
		return f"{self.user} - {self.get_plan_display()}"


class SubscriptionRequest(models.Model):
	class Status(models.TextChoices):
		PENDING = "pending", "Pending"
		APPROVED = "approved", "Approved"
		REJECTED = "rejected", "Rejected"
		CANCELLED = "cancelled", "Cancelled"

	user = models.ForeignKey(
		settings.AUTH_USER_MODEL,
		on_delete=models.CASCADE,
		related_name="subscription_requests",
	)
	plan = models.CharField(max_length=4, choices=Subscription.Plan.choices)
	amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
	card_number = models.CharField(max_length=20, blank=True)
	screenshot = models.ImageField(upload_to="subscription_screenshots/", blank=True, null=True)
	telegram_message_id = models.PositiveBigIntegerField(null=True, blank=True)
	admin_message_id = models.PositiveBigIntegerField(null=True, blank=True)
	status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
	notes = models.TextField(blank=True)
	processed_by = models.ForeignKey(
		settings.AUTH_USER_MODEL,
		on_delete=models.SET_NULL,
		null=True,
		blank=True,
		related_name="processed_subscription_requests",
	)
	created_at = models.DateTimeField(auto_now_add=True)
	updated_at = models.DateTimeField(auto_now=True)

	class Meta:
		ordering = ["-created_at"]

	def __str__(self):
		return f"{self.user} - {self.plan} - {self.status}"


class FavoriteContent(models.Model):
	user = models.ForeignKey(
		TelegramUser,
		on_delete=models.CASCADE,
		related_name="content_favorites",
	)
	content = models.ForeignKey(
		"movies.MediaTitle",
		on_delete=models.CASCADE,
		related_name="user_favorites",
	)
	created_at = models.DateTimeField(auto_now_add=True)

	class Meta:
		ordering = ["-created_at"]
		constraints = [
			models.UniqueConstraint(
				fields=["user", "content"],
				name="unique_user_favorite_content",
			),
		]

	def __str__(self):
		return f"{self.user} - {self.content}"
