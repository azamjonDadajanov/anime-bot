from datetime import timedelta

from django.conf import settings
from django.db import models
from django.utils import timezone


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
	referred_by = models.ForeignKey(
		"self",
		on_delete=models.SET_NULL,
		null=True,
		blank=True,
		related_name="referrals",
		editable=False,
	)

	class Meta:
		ordering = ["-created_at"]
		indexes = [
			models.Index(fields=["last_seen_at"], name="tguser_last_seen_idx"),
			models.Index(fields=["referred_by"], name="tguser_referred_by_idx"),
		]

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
	# Profile picture shown next to comments: a short emoji/text avatar, or a
	# real uploaded image (the AI assistant's «Profil rasmi» action writes both).
	avatar = models.CharField(max_length=500, blank=True)
	avatar_file = models.ImageField(upload_to="avatars/", blank=True, null=True)
	updated_at = models.DateTimeField(auto_now=True)

	class Meta:
		verbose_name = "User settings"
		verbose_name_plural = "User settings"

	def __str__(self):
		return f"{self.user} - sozlamalar"


class Subscription(models.Model):
	"""Duration based plan: every paid plan unlocks everything for N days."""

	class Plan(models.TextChoices):
		FREE = "free", "Bepul"
		DAILY = "daily", "Kunlik"
		D15 = "d15", "15 kunlik"
		MONTHLY = "monthly", "1 oylik"
		QUARTERLY = "quarterly", "3 oylik"
		YEARLY = "yearly", "1 yillik"
		# Granted by a coupon: a fixed number of days that is not one of the
		# catalogue durations. It still counts as a paid tier.
		COUPON = "coupon", "Kupon"

	user = models.OneToOneField(
		settings.AUTH_USER_MODEL,
		on_delete=models.CASCADE,
		related_name="subscription",
	)
	plan = models.CharField(max_length=16, choices=Plan.choices, default=Plan.FREE)
	started_at = models.DateTimeField(null=True, blank=True)
	expires_at = models.DateTimeField(null=True, blank=True)
	# Subscription reminders (see ``users.reminders``): the stage already sent
	# for the *current* window, so the daily cron never repeats itself, and when
	# it went out. Both are cleared whenever the window is (re)written, which
	# starts a fresh reminder cycle.
	reminder_stage = models.CharField(max_length=16, blank=True, default="")
	reminder_sent_at = models.DateTimeField(null=True, blank=True)
	updated_at = models.DateTimeField(auto_now=True)

	class Meta:
		ordering = ["user_id"]

	def __str__(self):
		return f"{self.user} - {self.get_plan_display()}"

	@property
	def is_active(self) -> bool:
		"""A plan is live only while it is paid *and* not expired."""
		if self.plan == self.Plan.FREE:
			return False
		return self.expires_at is not None and self.expires_at > timezone.now()

	REMINDER_FIELDS = ("reminder_stage", "reminder_sent_at")

	def reset_reminder(self) -> None:
		"""Forget the reminder already sent for the out-going window."""
		self.reminder_stage = ""
		self.reminder_sent_at = None

	def grant_days(self, days: int, at=None) -> None:
		"""Extend access by ``days`` (used by coupons).

		Unlike :meth:`activate`, which is tied to a catalogue plan, a coupon
		promises a number of days. A still running plan keeps its label and simply
		gets extra days; a free or expired account moves to the dedicated "Kupon"
		tier so the window counts as a paid subscription.
		"""
		at = at or timezone.now()
		days = int(days or 0)
		if days <= 0:
			return
		extends = bool(self.expires_at and self.expires_at > at)
		if not extends:
			self.started_at = at
			if self.plan in (None, "", self.Plan.FREE) or not self.is_active:
				self.plan = self.Plan.COUPON
		base = self.expires_at if extends else at
		self.expires_at = base + timedelta(days=days)
		self.reset_reminder()
		self.save(
			update_fields=[
				"plan",
				"started_at",
				"expires_at",
				"updated_at",
				*self.REMINDER_FIELDS,
			]
		)

	def activate(self, plan: str, at=None) -> None:
		"""Switch to ``plan`` for its full period.

		A still running subscription is extended instead of cut short, so a
		renewal (or a switch to a longer plan) never loses paid time.
		"""
		from .plans import plan_days

		at = at or timezone.now()
		days = int(plan_days(plan))
		self.plan = plan or self.Plan.FREE
		if days <= 0:
			self.started_at = None
			self.expires_at = None
		else:
			extends = bool(self.expires_at and self.expires_at > at)
			if not extends:
				self.started_at = at
			base = self.expires_at if extends else at
			self.expires_at = base + timedelta(days=days)
		# A new window deserves new reminders, even when only the end date moved.
		self.reset_reminder()
		self.save(
			update_fields=[
				"plan",
				"started_at",
				"expires_at",
				"updated_at",
				*self.REMINDER_FIELDS,
			]
		)


class Coupon(models.Model):
	"""A limited-use promo code: the first ``max_uses`` people win ``days`` days.

	Redemption is first-come-first-served. Once more people have entered the code
	than the administrator allowed, the coupon reads as *expired* (nothing is
	deleted, so the history stays visible in the panel).
	"""

	code = models.CharField(max_length=32, unique=True)
	days = models.PositiveIntegerField(default=0)
	max_uses = models.PositiveIntegerField(default=1)
	used_count = models.PositiveIntegerField(default=0)
	is_active = models.BooleanField(default=True)
	created_by = models.ForeignKey(
		settings.AUTH_USER_MODEL,
		on_delete=models.SET_NULL,
		null=True,
		blank=True,
		related_name="coupons_created",
	)
	posted_channel = models.ForeignKey(
		"movies.TelegramChannel",
		on_delete=models.SET_NULL,
		null=True,
		blank=True,
		related_name="posted_coupons",
	)
	posted_message_id = models.PositiveBigIntegerField(null=True, blank=True)
	created_at = models.DateTimeField(auto_now_add=True)
	updated_at = models.DateTimeField(auto_now=True)

	class Meta:
		ordering = ["-created_at"]
		indexes = [models.Index(fields=["-created_at"], name="coupon_created_idx")]

	def __str__(self) -> str:
		return f"{self.code} ({self.days} kun, {self.used_count}/{self.max_uses})"

	@property
	def is_exhausted(self) -> bool:
		"""True once as many (or more) people redeemed it as allowed."""
		return self.max_uses > 0 and self.used_count >= self.max_uses

	@property
	def is_expired(self) -> bool:
		"""A coupon stops handing out rewards once its limit or toggle says so."""
		return (not self.is_active) or self.is_exhausted

	@property
	def remaining(self) -> int:
		return max(0, self.max_uses - self.used_count)

	@property
	def status_label(self) -> str:
		if self.is_exhausted:
			return "Tugagan"
		if not self.is_active:
			return "To'xtatilgan"
		return "Faol"


class CouponRedemption(models.Model):
	"""One successful coupon use; the unique constraint stops double dipping."""

	coupon = models.ForeignKey(Coupon, on_delete=models.CASCADE, related_name="redemptions")
	user = models.ForeignKey(
		settings.AUTH_USER_MODEL,
		on_delete=models.CASCADE,
		related_name="coupon_redemptions",
	)
	telegram_id = models.PositiveBigIntegerField(null=True, blank=True)
	days = models.PositiveIntegerField(default=0)
	created_at = models.DateTimeField(auto_now_add=True)

	class Meta:
		ordering = ["-created_at"]
		constraints = [
			models.UniqueConstraint(
				fields=["coupon", "user"],
				name="unique_coupon_redemption",
			),
		]

	def __str__(self) -> str:
		return f"{self.coupon.code} - {self.user}"


class ReferralReward(models.Model):
	"""A claimed referral milestone; the unique constraint stops double claiming."""

	MILESTONE_10 = 10
	MILESTONE_15 = 15
	MILESTONES = {MILESTONE_10: 15, MILESTONE_15: 30}

	user = models.ForeignKey(
		settings.AUTH_USER_MODEL,
		on_delete=models.CASCADE,
		related_name="referral_rewards",
	)
	milestone = models.PositiveIntegerField()
	days = models.PositiveIntegerField(default=0)
	claimed_at = models.DateTimeField(auto_now_add=True)

	class Meta:
		ordering = ["-claimed_at"]
		constraints = [
			models.UniqueConstraint(
				fields=["user", "milestone"],
				name="unique_referral_reward",
			),
		]

	def __str__(self) -> str:
		return f"{self.user} - {self.milestone} referral ({self.days} kun)"


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
	plan = models.CharField(max_length=16, choices=Subscription.Plan.choices)
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


class Giveaway(models.Model):
	"""An administrator-run raffle with eligibility conditions.

	The administrator picks the reward and the conditions; at draw time the bot
	re-verifies channel membership and the referral link in the user's bio via
	the Bot API, then grants the reward to ``winner_count`` random eligible
	subscribers.
	"""

	class Status(models.TextChoices):
		DRAFT = "draft", "Loyiha"
		OPEN = "open", "Ochiq"
		DRAWN = "drawn", "E'lon qilingan"
		CLOSED = "closed", "Yopilgan"

	title = models.CharField(max_length=200)
	reward_days = models.PositiveIntegerField(default=0)
	winner_count = models.PositiveIntegerField(default=3)
	# Condition: the candidate watched at least N anime titles via the bot.
	min_bot_views = models.PositiveIntegerField(default=0)
	# Condition: the candidate is subscribed to every selected channel
	# (falls back to the bot's mandatory channels when none are selected).
	require_channels = models.BooleanField(default=False)
	# Condition: the candidate's Telegram bio contains their referral link.
	require_bio_ref = models.BooleanField(default=False)
	channels = models.ManyToManyField(
		"movies.TelegramChannel",
		blank=True,
		related_name="giveaways",
	)
	status = models.CharField(
		max_length=10, choices=Status.choices, default=Status.DRAFT
	)
	created_by = models.ForeignKey(
		settings.AUTH_USER_MODEL,
		on_delete=models.SET_NULL,
		null=True,
		blank=True,
		related_name="giveaways_created",
	)
	created_at = models.DateTimeField(auto_now_add=True)
	drawn_at = models.DateTimeField(null=True, blank=True)
	updated_at = models.DateTimeField(auto_now=True)

	class Meta:
		ordering = ["-created_at"]

	def __str__(self) -> str:
		return f"{self.title} ({self.reward_days} kun, {self.status})"


class GiveawayEntry(models.Model):
	"""Per-candidate verification journal written during a draw."""

	class Status(models.TextChoices):
		ELIGIBLE = "eligible", "Mos"
		WINNER = "winner", "G'olib"
		NO_SUBSCRIPTION = "no_sub", "Obunasi yo'q"
		NO_VIEWS = "no_views", "Kam anime ko'rgan"
		NO_CHANNEL = "no_channel", "Kanalga obuna yo'q"
		NO_BIO = "no_bio", "Bio'da havola yo'q"
		NO_ACCOUNT = "no_account", "Hisob yo'q"

	giveaway = models.ForeignKey(
		Giveaway, on_delete=models.CASCADE, related_name="entries"
	)
	user = models.ForeignKey(
		settings.AUTH_USER_MODEL,
		on_delete=models.CASCADE,
		related_name="giveaway_entries",
	)
	telegram_id = models.PositiveBigIntegerField()
	status = models.CharField(
		max_length=16, choices=Status.choices, default=Status.ELIGIBLE
	)
	created_at = models.DateTimeField(auto_now_add=True)

	class Meta:
		ordering = ["-created_at"]
		constraints = [
			models.UniqueConstraint(
				fields=["giveaway", "user"],
				name="unique_giveaway_entry",
			),
		]

	def __str__(self) -> str:
		return f"{self.giveaway_id} - {self.telegram_id} - {self.status}"


class GiveawayWinner(models.Model):
	"""A drawn winner; the unique constraint stops a double grant per raffle."""

	giveaway = models.ForeignKey(
		Giveaway, on_delete=models.CASCADE, related_name="winners"
	)
	user = models.ForeignKey(
		settings.AUTH_USER_MODEL,
		on_delete=models.CASCADE,
		related_name="giveaway_wins",
	)
	telegram_id = models.PositiveBigIntegerField()
	days = models.PositiveIntegerField(default=0)
	notified_at = models.DateTimeField(null=True, blank=True)
	created_at = models.DateTimeField(auto_now_add=True)

	class Meta:
		ordering = ["-created_at"]
		constraints = [
			models.UniqueConstraint(
				fields=["giveaway", "user"],
				name="unique_giveaway_winner",
			),
		]

	def __str__(self) -> str:
		return f"{self.giveaway_id} - {self.telegram_id} ({self.days} kun)"


class SupportMessage(models.Model):
	"""A message a user sent to the administrators from the bot or the website.

	The row is the durable record of the request: the website and the polling
	bot are separate processes, so the message is forwarded over the Bot API
	(see ``users.telegram_notify``) and the outcome is kept here — an
	undelivered message is never silently lost.
	"""

	class Source(models.TextChoices):
		BOT = "bot", "Bot"
		WEB = "web", "Sayt"

	class Status(models.TextChoices):
		PENDING = "pending", "Yuborilmoqda"
		SENT = "sent", "Yuborildi"
		FAILED = "failed", "Yuborilmadi"

	user = models.ForeignKey(
		settings.AUTH_USER_MODEL,
		on_delete=models.CASCADE,
		related_name="support_messages",
	)
	telegram_id = models.PositiveBigIntegerField(null=True, blank=True)
	text = models.TextField()
	source = models.CharField(max_length=4, choices=Source.choices, default=Source.WEB)
	status = models.CharField(
		max_length=8, choices=Status.choices, default=Status.PENDING
	)
	error = models.CharField(max_length=255, blank=True, default="")
	created_at = models.DateTimeField(auto_now_add=True)

	class Meta:
		ordering = ["-created_at"]
		indexes = [models.Index(fields=["-created_at"], name="support_created_idx")]

	def __str__(self) -> str:
		return f"{self.get_source_display()} → admin ({self.user_id}): {self.text[:40]}"

	def mark_delivered(self, delivered: bool, error: str = "") -> None:
		self.status = self.Status.SENT if delivered else self.Status.FAILED
		self.error = (error or "")[:255]
		self.save(update_fields=["status", "error"])
