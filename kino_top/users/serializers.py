from django.contrib.auth import get_user_model, password_validation
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

from movies.models import MediaTitle
from movies.serializers import MediaTitleSerializer

from .models import Subscription, SubscriptionRequest, UserSettings


class RegisterSerializer(serializers.ModelSerializer):
	password = serializers.CharField(write_only=True, min_length=8)
	password_confirm = serializers.CharField(write_only=True)

	class Meta:
		model = get_user_model()
		fields = ["id", "username", "email", "password", "password_confirm"]
		read_only_fields = ["id"]

	def validate(self, attrs):
		if attrs["password"] != attrs.pop("password_confirm"):
			raise serializers.ValidationError({"password_confirm": "Passwords do not match."})
		try:
			password_validation.validate_password(attrs["password"])
		except DjangoValidationError as exc:
			raise serializers.ValidationError({"password": exc.messages}) from exc
		return attrs

	def create(self, validated_data):
		return get_user_model().objects.create_user(**validated_data)


class PasswordTokenSerializer(TokenObtainPairSerializer):
	@classmethod
	def get_token(cls, user):
		token = super().get_token(user)
		token["auth_method"] = "password"
		return token


class TelegramMiniAppSerializer(serializers.Serializer):
	init_data = serializers.CharField(trim_whitespace=False)
	email = serializers.EmailField(required=False, allow_blank=True)
	password = serializers.CharField(write_only=True)


class TelegramWidgetSerializer(serializers.Serializer):
	id = serializers.CharField()
	first_name = serializers.CharField(required=False, allow_blank=True)
	last_name = serializers.CharField(required=False, allow_blank=True)
	username = serializers.CharField(required=False, allow_blank=True)
	photo_url = serializers.CharField(required=False, allow_blank=True)
	language_code = serializers.CharField(required=False, allow_blank=True)
	auth_date = serializers.CharField()
	hash = serializers.CharField()


class UserSettingsSerializer(serializers.ModelSerializer):
	class Meta:
		model = UserSettings
		fields = ["theme", "language", "reduce_motion", "updated_at"]
		read_only_fields = ["updated_at"]


class CurrentUserSerializer(serializers.ModelSerializer):
	telegram_id = serializers.SerializerMethodField()
	subscription = serializers.SerializerMethodField()
	settings = serializers.SerializerMethodField()

	class Meta:
		model = get_user_model()
		fields = [
			"id",
			"username",
			"email",
			"is_staff",
			"telegram_id",
			"subscription",
			"settings",
			"date_joined",
			"last_login",
		]
		read_only_fields = fields

	def get_telegram_id(self, user) -> int | None:
		profile = getattr(user, "telegram_profile", None)
		return profile.telegram_id if profile else None

	def get_subscription(self, user) -> dict[str, str]:
		subscription = getattr(user, "subscription", None)
		return {"plan": subscription.plan if subscription else Subscription.Plan.FREE}

	def get_settings(self, user) -> dict:
		settings, _ = UserSettings.objects.get_or_create(user=user)
		return UserSettingsSerializer(settings).data


class ProfileUpdateSerializer(serializers.ModelSerializer):
	class Meta:
		model = get_user_model()
		fields = ["username", "email"]


class FavoriteTitleSerializer(MediaTitleSerializer):
	class Meta(MediaTitleSerializer.Meta):
		fields = MediaTitleSerializer.Meta.fields


class SubscriptionRequestSerializer(serializers.ModelSerializer):
	class Meta:
		model = SubscriptionRequest
		fields = [
			"id",
			"plan",
			"amount",
			"card_number",
			"screenshot",
			"status",
			"notes",
			"created_at",
			"updated_at",
		]
		read_only_fields = ["id", "status", "notes", "created_at", "updated_at"]


class SubscriptionRequestCreateSerializer(serializers.ModelSerializer):
	class Meta:
		model = SubscriptionRequest
		fields = ["plan", "amount", "screenshot"]
		extra_kwargs = {
			"amount": {"required": False, "allow_null": True},
			"screenshot": {"required": True},
		}

	def validate_plan(self, value):
		if value not in Subscription.Plan.values:
			raise serializers.ValidationError("Invalid plan")
		return value