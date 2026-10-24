from django.contrib.auth import get_user_model
from rest_framework import serializers

from bot.models import BotLogEntry, BotSettings, Broadcast
from games.models import AnimeVerification, MonthlyPrize, QuizAttempt, QuizQuestion
from movies import community
from movies.models import (
	Genre,
	MediaPart,
	MediaTitle,
	TelegramChannel,
	TelegramMedia,
	TitleComment,
	TitleRating,
)
from users.coupons import generate_code, is_valid_code, normalize_code
from users.models import Coupon, CouponRedemption, Subscription, SubscriptionRequest, TelegramUser

from .models import Income


class AdminUserSerializer(serializers.ModelSerializer):
	telegram_id = serializers.SerializerMethodField()
	username = serializers.CharField(source="auth_user.username", read_only=True)
	email = serializers.CharField(source="auth_user.email", read_only=True)
	is_staff = serializers.BooleanField(source="auth_user.is_staff", read_only=True)
	plan = serializers.SerializerMethodField()
	plan_label = serializers.SerializerMethodField()
	plan_active = serializers.SerializerMethodField()
	plan_expires = serializers.SerializerMethodField()
	# 👑 the same rule as everywhere else, exposed for the panel's user rows.
	is_premium = serializers.SerializerMethodField()
	is_blocked = serializers.SerializerMethodField()
	full_name = serializers.SerializerMethodField()
	last_seen_at = serializers.SerializerMethodField()
	created_at = serializers.SerializerMethodField()
	favorites_count = serializers.SerializerMethodField()

	class Meta:
		model = TelegramUser
		fields = [
			"id",
			"telegram_id",
			"username",
			"email",
			"is_staff",
			"full_name",
			"first_name",
			"last_name",
			"language_code",
			"plan",
			"plan_label",
			"plan_active",
			"plan_expires",
			"is_premium",
			"is_blocked",
			"last_seen_at",
			"created_at",
			"favorites_count",
		]
		read_only_fields = fields

	def get_telegram_id(self, obj) -> int | None:
		return obj.telegram_id

	def get_username(self, obj) -> str:
		return obj.auth_user.username if obj.auth_user else ""

	def get_email(self, obj) -> str:
		return obj.auth_user.email if obj.auth_user else ""

	def get_is_staff(self, obj) -> bool:
		return bool(obj.auth_user and obj.auth_user.is_staff)

	def _subscription(self, obj):
		if obj.auth_user and hasattr(obj.auth_user, "subscription"):
			return obj.auth_user.subscription
		return None

	def get_plan(self, obj) -> str:
		sub = self._subscription(obj)
		return sub.plan if sub else Subscription.Plan.FREE

	def get_plan_label(self, obj) -> str:
		plan = self.get_plan(obj)
		return dict(Subscription.Plan.choices).get(plan, str(plan).title())

	def get_plan_active(self, obj) -> bool:
		sub = self._subscription(obj)
		return bool(sub and sub.is_active)

	def get_is_premium(self, obj) -> bool:
		from users.premium import is_premium_user

		return bool(obj.auth_user and is_premium_user(obj.auth_user))

	def get_plan_expires(self, obj):
		sub = self._subscription(obj)
		return sub.expires_at if sub else None

	def get_is_blocked(self, obj) -> bool:
		return obj.is_blocked

	def get_full_name(self, obj) -> str:
		return " ".join(p for p in [obj.first_name, obj.last_name] if p).strip()

	def get_last_seen_at(self, obj):
		return obj.last_seen_at

	def get_created_at(self, obj):
		return obj.created_at

	def get_favorites_count(self, obj) -> int:
		return obj.content_favorites.count()


class AdminUserDetailSerializer(AdminUserSerializer):
	subscription = serializers.SerializerMethodField()
	requests = serializers.SerializerMethodField()

	class Meta(AdminUserSerializer.Meta):
		fields = [*AdminUserSerializer.Meta.fields, "subscription", "requests"]

	def get_subscription(self, obj) -> dict:
		sub = getattr(obj.auth_user, "subscription", None) if obj.auth_user else None
		if not sub:
			return {
				"plan": Subscription.Plan.FREE,
				"plan_label": "Bepul",
				"is_active": False,
				"expires_at": None,
				"updated_at": None,
			}
		return {
			"plan": sub.plan,
			"plan_label": sub.get_plan_display(),
			"is_active": sub.is_active,
			"expires_at": sub.expires_at,
			"updated_at": sub.updated_at,
		}

	def get_requests(self, obj) -> list:
		if not obj.auth_user:
			return []
		requests = SubscriptionRequest.objects.filter(user=obj.auth_user).order_by("-created_at")[:10]
		return SubscriptionRequestAdminSerializer(requests, many=True).data


class UserPlanUpdateSerializer(serializers.Serializer):
	plan = serializers.ChoiceField(choices=Subscription.Plan.choices)


class UserBlockSerializer(serializers.Serializer):
	is_blocked = serializers.BooleanField()


class SubscriptionRequestAdminSerializer(serializers.ModelSerializer):
	user = serializers.SerializerMethodField()
	telegram_id = serializers.SerializerMethodField()
	plan_label = serializers.CharField(source="get_plan_display", read_only=True)
	status_label = serializers.CharField(source="get_status_display", read_only=True)
	screenshot_url = serializers.SerializerMethodField()

	class Meta:
		model = SubscriptionRequest
		fields = [
			"id",
			"user",
			"telegram_id",
			"plan",
			"plan_label",
			"amount",
			"card_number",
			"screenshot_url",
			"status",
			"status_label",
			"notes",
			"created_at",
			"updated_at",
		]
		read_only_fields = fields

	def get_user(self, obj) -> str:
		if obj.user:
			return obj.user.username or str(obj.user.id)
		return ""

	def get_telegram_id(self, obj) -> int | None:
		profile = getattr(obj.user, "telegram_profile", None)
		return profile.telegram_id if profile else None

	def get_screenshot_url(self, obj) -> str | None:
		if not obj.screenshot:
			return None
		request = self.context.get("request")
		url = obj.screenshot.url
		if request:
			return request.build_absolute_uri(url)
		return url


class IncomeSerializer(serializers.ModelSerializer):
	source_label = serializers.CharField(source="get_source_display", read_only=True)
	method_label = serializers.CharField(source="get_method_display", read_only=True)
	created_by = serializers.StringRelatedField(read_only=True)

	class Meta:
		model = Income
		fields = [
			"id",
			"amount",
			"source",
			"source_label",
			"method",
			"method_label",
			"plan",
			"note",
			"paid_at",
			"created_by",
			"created_at",
			"updated_at",
		]
		read_only_fields = ["id", "created_by", "created_at", "updated_at"]


class CouponRedemptionAdminSerializer(serializers.ModelSerializer):
	username = serializers.SerializerMethodField()

	class Meta:
		model = CouponRedemption
		fields = ["id", "user", "username", "telegram_id", "days", "created_at"]
		read_only_fields = fields

	def get_username(self, obj) -> str:
		return obj.user.username if obj.user else ""


class CouponAdminSerializer(serializers.ModelSerializer):
	remaining = serializers.IntegerField(read_only=True)
	status = serializers.SerializerMethodField()
	status_label = serializers.CharField(read_only=True)
	created_by = serializers.StringRelatedField(read_only=True)
	posted_channel_title = serializers.CharField(
		source="posted_channel.title", read_only=True, default=None
	)
	redemptions_count = serializers.SerializerMethodField()

	class Meta:
		model = Coupon
		fields = [
			"id",
			"code",
			"days",
			"max_uses",
			"used_count",
			"remaining",
			"is_active",
			"status",
			"status_label",
			"created_by",
			"posted_channel",
			"posted_channel_title",
			"posted_message_id",
			"redemptions_count",
			"created_at",
			"updated_at",
		]
		read_only_fields = fields

	def get_status(self, obj) -> str:
		if obj.is_exhausted:
			return "exhausted"
		if not obj.is_active:
			return "stopped"
		return "active"

	def get_redemptions_count(self, obj) -> int:
		return obj.redemptions.count()


class CouponWriteSerializer(serializers.ModelSerializer):
	"""Create/update payload for a coupon.

	A blank ``code`` asks the server to generate one, exactly like the ``-``
	answer in the bot flow. Redeemed coupons keep their history, so only
	``used_count`` is never editable.
	"""

	code = serializers.CharField(
		max_length=32, required=False, allow_blank=True, validators=[]
	)
	days = serializers.IntegerField(min_value=1, max_value=3650)
	max_uses = serializers.IntegerField(min_value=1, max_value=1_000_000)

	class Meta:
		model = Coupon
		fields = ["code", "days", "max_uses", "is_active", "posted_channel"]
		extra_kwargs = {"posted_channel": {"required": False, "allow_null": True}}

	def validate_code(self, value) -> str:
		normalized = normalize_code(value)
		if not normalized:
			return ""
		if not is_valid_code(normalized):
			raise serializers.ValidationError(
				"Kod 4-24 ta harf/raqamdan iborat bo'lishi va kamida bitta harf "
				"qatnashishi kerak."
			)
		existing = Coupon.objects.filter(code=normalized)
		if self.instance is not None:
			existing = existing.exclude(pk=self.instance.pk)
		if existing.exists():
			raise serializers.ValidationError("Bu kod allaqachon ishlatilgan.")
		return normalized

	def create(self, validated_data):
		validated_data["code"] = validated_data.get("code") or generate_code()
		request = self.context.get("request")
		if request is not None and request.user.is_authenticated:
			validated_data["created_by"] = request.user
		return super().create(validated_data)

	def update(self, instance, validated_data):
		# An empty code on edit means "leave it alone" — replacing it would
		# break the code users already read in the channel post.
		if not validated_data.get("code"):
			validated_data.pop("code", None)
		return super().update(instance, validated_data)


class GenreAdminSerializer(serializers.ModelSerializer):
	media_count = serializers.SerializerMethodField()

	class Meta:
		model = Genre
		fields = ["id", "name", "media_count"]
		read_only_fields = ["id", "media_count"]

	def get_media_count(self, obj) -> int:
		return obj.media_titles.count()


class BroadcastAdminSerializer(serializers.ModelSerializer):
	kind_label = serializers.CharField(source="get_kind_display", read_only=True)
	status_label = serializers.CharField(source="get_status_display", read_only=True)
	processed = serializers.IntegerField(read_only=True)

	class Meta:
		model = Broadcast
		fields = [
			"id",
			"kind",
			"kind_label",
			"text",
			"caption",
			"file_id",
			"status",
			"status_label",
			"disable_notification",
			"protect_content",
			"include_blocked",
			"total",
			"sent_count",
			"failed_count",
			"blocked_count",
			"processed",
			"last_error",
			"created_at",
			"started_at",
			"finished_at",
		]
		read_only_fields = [
			"id",
			"status",
			"total",
			"sent_count",
			"failed_count",
			"blocked_count",
			"last_error",
			"created_at",
			"started_at",
			"finished_at",
		]


class BroadcastCreateSerializer(serializers.ModelSerializer):
	class Meta:
		model = Broadcast
		fields = [
			"kind",
			"text",
			"caption",
			"file_id",
			"disable_notification",
			"protect_content",
			"include_blocked",
		]

	def validate(self, attrs):
		kind = attrs.get("kind", Broadcast.Kind.TEXT)
		if kind == Broadcast.Kind.TEXT and not (attrs.get("text") or "").strip():
			raise serializers.ValidationError({"text": "Matn majburiy."})
		if kind in {Broadcast.Kind.PHOTO, Broadcast.Kind.VIDEO, Broadcast.Kind.DOCUMENT, Broadcast.Kind.AUDIO}:
			if not (attrs.get("file_id") or "").strip():
				raise serializers.ValidationError({"file_id": "Telegram file_id majburiy."})
		return attrs


class BotSettingsSerializer(serializers.ModelSerializer):
	publish_channel_title = serializers.CharField(
		source="publish_channel.title", read_only=True, default=None
	)

	class Meta:
		model = BotSettings
		fields = [
			"require_subscription",
			"auto_publish_new_content",
			"publish_channel",
			"publish_channel_title",
			"welcome_text",
			"access_denied_text",
			"broadcast_rate_per_second",
			"broadcast_concurrency",
			"protect_content",
			"maintenance_mode",
			"log_channel_id",
			"updated_at",
		]
		read_only_fields = ["updated_at"]


class BotLogAdminSerializer(serializers.ModelSerializer):
	level_label = serializers.CharField(source="get_level_display", read_only=True)

	class Meta:
		model = BotLogEntry
		fields = [
			"id",
			"level",
			"level_label",
			"logger",
			"message",
			"telegram_id",
			"created_at",
		]
		read_only_fields = fields


# ---------------------------------------------------------------------------
# Games (anime rating quiz)
# ---------------------------------------------------------------------------


class QuizQuestionAdminSerializer(serializers.ModelSerializer):
	title_title = serializers.CharField(source="title.title", read_only=True)
	title_type = serializers.CharField(source="title.type", read_only=True)

	class Meta:
		model = QuizQuestion
		fields = [
			"id",
			"title",
			"title_title",
			"title_type",
			"text",
			"choices",
			"correct_index",
			"is_active",
			"created_at",
		]
		read_only_fields = ["id", "created_at"]

	def validate_choices(self, value):
		if not isinstance(value, (list, tuple)) or len(value) < 2:
			raise serializers.ValidationError("Kamida 2 ta variant kerak.")
		if len(value) > 6:
			raise serializers.ValidationError("Ko'pi bilan 6 ta variant.")
		return [str(item) for item in value]

	def validate_correct_index(self, value):
		choices = self.initial_data.get("choices") or (self.instance.choices if self.instance else [])
		if choices and not (0 <= int(value) < len(choices)):
			raise serializers.ValidationError("To'g'ri javob indeksi variantlar chegarasida bo'lishi kerak.")
		return int(value)


class QuizAttemptAdminSerializer(serializers.ModelSerializer):
	username = serializers.CharField(source="user.username", read_only=True, default=None)
	telegram_id = serializers.SerializerMethodField()
	title_title = serializers.CharField(source="title.title", read_only=True)
	correct = serializers.SerializerMethodField()

	class Meta:
		model = QuizAttempt
		fields = [
			"id",
			"user",
			"username",
			"telegram_id",
			"title",
			"title_title",
			"question_ids",
			"choice_orders",
			"answers",
			"correct",
			"elapsed_ms",
			"started_at",
			"finished_at",
			"passed",
			"points_awarded",
			"is_suspicious",
		]
		read_only_fields = [
			"id",
			"user",
			"title",
			"question_ids",
			"choice_orders",
			"answers",
			"elapsed_ms",
			"started_at",
			"finished_at",
			"passed",
			"points_awarded",
		]

	def get_telegram_id(self, obj) -> int | None:
		profile = getattr(obj.user, "telegram_profile", None)
		return getattr(profile, "telegram_id", None)

	def get_correct(self, obj) -> int:
		if not obj.finished_at or not obj.answers:
			return 0
		from games.models import QuizQuestion

		questions = QuizQuestion.objects.in_bulk(obj.question_ids or [])
		orders = list(obj.choice_orders or [])
		correct = 0
		for index, question_id in enumerate(obj.question_ids or []):
			question = questions.get(question_id)
			if question is None or index >= len(obj.answers):
				continue
			answer = int(obj.answers[index])
			order = orders[index] if index < len(orders) else None
			if order and 0 <= answer < len(order):
				answer = int(order[answer])
			if answer == question.correct_index:
				correct += 1
		return correct


class AnimeVerificationAdminSerializer(serializers.ModelSerializer):
	username = serializers.CharField(source="user.username", read_only=True, default=None)
	telegram_id = serializers.SerializerMethodField()
	title_title = serializers.CharField(source="title.title", read_only=True)

	class Meta:
		model = AnimeVerification
		fields = [
			"id",
			"user",
			"username",
			"telegram_id",
			"title",
			"title_title",
			"points",
			"verified_at",
		]
		read_only_fields = ["id", "verified_at"]

	def get_telegram_id(self, obj) -> int | None:
		profile = getattr(obj.user, "telegram_profile", None)
		return getattr(profile, "telegram_id", None)

	def validate(self, attrs):
		user = attrs.get("user") or (self.instance.user if self.instance else None)
		title = attrs.get("title") or (self.instance.title if self.instance else None)
		if user is not None and title is not None:
			qs = AnimeVerification.objects.filter(user=user, title=title)
			if self.instance:
				qs = qs.exclude(pk=self.instance.pk)
			if qs.exists():
				raise serializers.ValidationError("Bu foydalanuvchi uchun bu anime allaqachon tasdiqlangan.")
		return attrs


class MonthlyPrizeAdminSerializer(serializers.ModelSerializer):
	username = serializers.CharField(source="user.username", read_only=True, default=None)
	telegram_id = serializers.SerializerMethodField()

	class Meta:
		model = MonthlyPrize
		fields = [
			"id",
			"year",
			"month",
			"user",
			"username",
			"telegram_id",
			"points",
			"days",
			"awarded_at",
		]
		read_only_fields = ["id", "awarded_at"]

	def get_telegram_id(self, obj) -> int | None:
		profile = getattr(obj.user, "telegram_profile", None)
		return getattr(profile, "telegram_id", None)


class AdminCommentSerializer(serializers.ModelSerializer):
	"""Moderation row for comments: who wrote what, where, and from which app.

	Site and bot comments live in one table, so this single screen shows both
	sources; ``author`` carries the crown flag the panel renders next to the
	name (``community.author_payload`` computes it from the live subscription).
	"""

	author = serializers.SerializerMethodField()
	part_number = serializers.SerializerMethodField()
	title_name = serializers.CharField(source="title.title", read_only=True)
	title_slug = serializers.CharField(source="title.slug", read_only=True)

	class Meta:
		model = TitleComment
		fields = [
			"id",
			"title",
			"title_name",
			"title_slug",
			"part",
			"part_number",
			"source",
			"body",
			"author",
			"created_at",
		]
		read_only_fields = fields

	def get_author(self, obj) -> dict:
		return community.author_payload(obj.user)

	def get_part_number(self, obj) -> int | None:
		return obj.part.number if obj.part_id else None


class AdminRatingSerializer(serializers.ModelSerializer):
	"""Moderation row for a single 1-10 score on a title."""

	author = serializers.SerializerMethodField()
	title_name = serializers.CharField(source="title.title", read_only=True)
	title_slug = serializers.CharField(source="title.slug", read_only=True)

	class Meta:
		model = TitleRating
		fields = [
			"id",
			"title",
			"title_name",
			"title_slug",
			"score",
			"author",
			"created_at",
			"updated_at",
		]
		read_only_fields = fields

	def get_author(self, obj) -> dict:
		return community.author_payload(obj.user)
