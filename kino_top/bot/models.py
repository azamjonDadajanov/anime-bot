"""Bot persistent state: FSM storage, configuration, broadcasts and logs.

These models intentionally live in their own app so that the catalog and user
models keep their original shape. They reuse the existing ``movies`` and
``users`` models through foreign keys instead of duplicating them.
"""

from __future__ import annotations

from django.db import models
from django.utils import timezone


class FSMState(models.Model):
	"""A single persisted finite-state-machine record.

	The row is keyed by the exact string produced by the aiogram key builder so
	that chat/user/thread/destiny combinations never collide. ``data`` holds the
	JSON-serializable FSM payload, which survives restarts and deployments.
	"""

	key = models.CharField(max_length=255, unique=True, db_index=True)
	bot_id = models.BigIntegerField()
	chat_id = models.BigIntegerField()
	user_id = models.BigIntegerField()
	thread_id = models.BigIntegerField(null=True, blank=True)
	business_connection_id = models.CharField(max_length=64, blank=True, default="")
	destiny = models.CharField(max_length=32, default="default")
	state = models.CharField(max_length=200, blank=True, default="")
	data = models.JSONField(default=dict, blank=True)
	expires_at = models.DateTimeField(null=True, blank=True)
	created_at = models.DateTimeField(auto_now_add=True)
	updated_at = models.DateTimeField(auto_now=True)

	class Meta:
		ordering = ["-updated_at"]
		indexes = [
			models.Index(fields=["bot_id", "chat_id", "user_id"], name="bot_fsm_lookup_idx"),
			models.Index(fields=["expires_at"], name="bot_fsm_expires_idx"),
		]

	def __str__(self) -> str:
		return f"{self.key} -> {self.state or '<empty>'}"

	@property
	def is_expired(self) -> bool:
		return self.expires_at is not None and self.expires_at <= timezone.now()


class BotSettings(models.Model):
	"""Singleton row with runtime settings managed from the admin panel."""

	require_subscription = models.BooleanField(
		default=True,
		help_text=(
			"Require membership of every active 'required' and 'public' channel before the "
			"bot answers anything at all."
		),
	)
	auto_publish_new_content = models.BooleanField(
		default=False,
		help_text="Automatically publish new titles to the selected public channel.",
	)
	publish_channel = models.ForeignKey(
		"movies.TelegramChannel",
		on_delete=models.SET_NULL,
		null=True,
		blank=True,
		related_name="+",
		limit_choices_to={"purpose": "public"},
		help_text="Default public channel used for announcements and episode posts.",
	)
	completed_channel = models.ForeignKey(
		"movies.TelegramChannel",
		on_delete=models.SET_NULL,
		null=True,
		blank=True,
		related_name="+",
		limit_choices_to={"purpose": "public"},
		help_text="Tugallangan medialar (anime, kino, serial) uchun e'lon kanali.",
	)
	ongoing_channel = models.ForeignKey(
		"movies.TelegramChannel",
		on_delete=models.SET_NULL,
		null=True,
		blank=True,
		related_name="+",
		limit_choices_to={"purpose": "public"},
		help_text="Davom etayotgan (ongoing) medialar uchun e'lon kanali.",
	)
	manga_channel = models.ForeignKey(
		"movies.TelegramChannel",
		on_delete=models.SET_NULL,
		null=True,
		blank=True,
		related_name="+",
		limit_choices_to={"purpose": "public"},
		help_text="Mangalar (ongoing) uchun e'lon kanali.",
	)
	manga_completed_channel = models.ForeignKey(
		"movies.TelegramChannel",
		on_delete=models.SET_NULL,
		null=True,
		blank=True,
		related_name="+",
		limit_choices_to={"purpose": "public"},
		help_text="Tugallangan mangalar uchun e'lon kanali.",
	)
	welcome_text = models.TextField(
		blank=True,
		default="",
		help_text="Optional text shown at the top of the /start message.",
	)
	access_denied_text = models.TextField(
		blank=True,
		default="",
		help_text="Optional extra text shown when access is denied.",
	)
	broadcast_rate_per_second = models.PositiveSmallIntegerField(
		default=25,
		help_text="Messages per second while broadcasting (Telegram allows ~30).",
	)
	broadcast_concurrency = models.PositiveSmallIntegerField(
		default=5,
		help_text="How many parallel Telegram requests a broadcast may issue.",
	)
	protect_content = models.BooleanField(
		default=True,
		help_text="Forwarding/saving of delivered media is disabled when enabled.",
	)
	maintenance_mode = models.BooleanField(
		default=False,
		help_text="When enabled, only administrators may use the bot.",
	)
	log_channel_id = models.BigIntegerField(
		null=True,
		blank=True,
		help_text="Optional channel that receives administrative audit events.",
	)
	updated_at = models.DateTimeField(auto_now=True)

	class Meta:
		verbose_name = "Bot settings"
		verbose_name_plural = "Bot settings"

	def __str__(self) -> str:
		return "Bot settings"

	@classmethod
	def get_solo(cls) -> "BotSettings":
		obj, _ = cls.objects.get_or_create(pk=1)
		return obj


class Broadcast(models.Model):
	"""A persisted broadcast campaign with resumable delivery statistics."""

	class Kind(models.TextChoices):
		TEXT = "text", "Matn"
		PHOTO = "photo", "Rasm"
		VIDEO = "video", "Video"
		DOCUMENT = "document", "Fayl"
		AUDIO = "audio", "Audio"
		FORWARD = "forward", "Forward"

	class Status(models.TextChoices):
		DRAFT = "draft", "Qoralama"
		RUNNING = "running", "Yuborilmoqda"
		PAUSED = "paused", "To'xtatilgan"
		COMPLETED = "completed", "Yakunlangan"
		CANCELLED = "cancelled", "Bekor qilingan"
		FAILED = "failed", "Xato"

	admin_telegram_id = models.BigIntegerField()
	kind = models.CharField(max_length=10, choices=Kind.choices, default=Kind.TEXT)
	text = models.TextField(blank=True)
	caption = models.CharField(max_length=1024, blank=True)
	file_id = models.CharField(max_length=512, blank=True)
	from_chat_id = models.BigIntegerField(null=True, blank=True)
	source_message_id = models.BigIntegerField(null=True, blank=True)
	disable_notification = models.BooleanField(default=False)
	protect_content = models.BooleanField(default=True)
	include_blocked = models.BooleanField(default=False)
	status = models.CharField(max_length=12, choices=Status.choices, default=Status.DRAFT)
	cancel_requested = models.BooleanField(default=False)
	total = models.PositiveIntegerField(default=0)
	sent_count = models.PositiveIntegerField(default=0)
	failed_count = models.PositiveIntegerField(default=0)
	blocked_count = models.PositiveIntegerField(default=0)
	cursor_telegram_id = models.BigIntegerField(default=0)
	last_error = models.TextField(blank=True)
	panel_chat_id = models.BigIntegerField(null=True, blank=True)
	panel_message_id = models.BigIntegerField(null=True, blank=True)
	created_at = models.DateTimeField(auto_now_add=True)
	started_at = models.DateTimeField(null=True, blank=True)
	finished_at = models.DateTimeField(null=True, blank=True)

	class Meta:
		ordering = ["-created_at"]
		indexes = [models.Index(fields=["status"], name="bot_broadcast_status_idx")]

	def __str__(self) -> str:
		return f"Broadcast #{self.pk} ({self.get_kind_display()}) - {self.status}"

	@property
	def processed(self) -> int:
		return self.sent_count + self.failed_count + self.blocked_count

	def mark_finished(self, status: str) -> None:
		self.status = status
		self.finished_at = timezone.now()
		self.save(update_fields=["status", "finished_at", "sent_count", "failed_count", "blocked_count", "last_error"])


class BroadcastDelivery(models.Model):
	"""Per-recipient delivery result. Makes statistics durable and resumable."""

	class Status(models.TextChoices):
		SENT = "sent", "Yuborildi"
		FAILED = "failed", "Xato"
		BLOCKED = "blocked", "Bloklangan"

	broadcast = models.ForeignKey(Broadcast, on_delete=models.CASCADE, related_name="deliveries")
	telegram_id = models.BigIntegerField()
	status = models.CharField(max_length=8, choices=Status.choices)
	error = models.CharField(max_length=255, blank=True)
	created_at = models.DateTimeField(auto_now_add=True)

	class Meta:
		ordering = ["telegram_id"]
		constraints = [
			models.UniqueConstraint(
				fields=["broadcast", "telegram_id"],
				name="unique_broadcast_delivery",
			),
		]
		indexes = [models.Index(fields=["broadcast", "status"], name="bot_delivery_status_idx")]

	def __str__(self) -> str:
		return f"#{self.broadcast_id} -> {self.telegram_id}: {self.status}"


class BotLogEntry(models.Model):
	"""Administrative audit log and error journal, readable from the panel."""

	class Level(models.TextChoices):
		DEBUG = "DEBUG", "Debug"
		INFO = "INFO", "Info"
		WARNING = "WARNING", "Ogohlantirish"
		ERROR = "ERROR", "Xato"
		CRITICAL = "CRITICAL", "Kritik"

	level = models.CharField(max_length=10, choices=Level.choices, default=Level.INFO)
	logger = models.CharField(max_length=64, blank=True, default="")
	message = models.TextField()
	telegram_id = models.BigIntegerField(null=True, blank=True)
	created_at = models.DateTimeField(auto_now_add=True)

	class Meta:
		ordering = ["-created_at"]
		indexes = [
			models.Index(fields=["level"], name="bot_log_level_idx"),
			models.Index(fields=["-created_at"], name="bot_log_created_idx"),
		]

	def __str__(self) -> str:
		return f"[{self.level}] {self.message[:60]}"
