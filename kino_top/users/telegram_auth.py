import hashlib
import hmac
import json
import time
from urllib.parse import parse_qsl

from django.conf import settings
from django.contrib.auth import get_user_model, password_validation
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from rest_framework.exceptions import AuthenticationFailed, ValidationError
from rest_framework_simplejwt.tokens import RefreshToken

from .models import Subscription, TelegramUser


MAX_AUTH_AGE_SECONDS = 86400


def _is_temporary_auth_user(auth_user, telegram_id) -> bool:
	"""True for the throwaway ``telegram_<id>`` account created by the bot."""
	return bool(
		auth_user
		and auth_user.username == f"telegram_{telegram_id}"
		and not auth_user.has_usable_password()
	)


def _verify_payload(fields, *, mini_app):
	bot_token = settings.TELEGRAM_BOT_TOKEN
	if not bot_token:
		raise AuthenticationFailed("Telegram login is not configured.")

	provided_hash = fields.get("hash", "")
	if not provided_hash:
		raise AuthenticationFailed("Telegram signature is missing.")

	check_string = "\n".join(
		f"{key}={value}"
		for key, value in sorted(fields.items())
		if key != "hash"
	)
	if mini_app:
		secret_key = hmac.new(
			b"WebAppData",
			bot_token.encode(),
			hashlib.sha256,
		).digest()
	else:
		secret_key = hashlib.sha256(bot_token.encode()).digest()

	expected_hash = hmac.new(
		secret_key,
		check_string.encode(),
		hashlib.sha256,
	).hexdigest()
	if not hmac.compare_digest(expected_hash, provided_hash):
		raise AuthenticationFailed("Telegram signature is invalid.")

	try:
		auth_date = int(fields["auth_date"])
	except (KeyError, TypeError, ValueError) as exc:
		raise AuthenticationFailed("Telegram authentication date is invalid.") from exc

	current_time = int(time.time())
	if auth_date > current_time + 60 or current_time - auth_date > MAX_AUTH_AGE_SECONDS:
		raise AuthenticationFailed("Telegram authentication data has expired.")


def parse_mini_app_init_data(init_data):
	try:
		pairs = parse_qsl(init_data, keep_blank_values=True, strict_parsing=True)
	except ValueError as exc:
		raise AuthenticationFailed("Telegram init data is malformed.") from exc
	fields = dict(pairs)
	if len(fields) != len(pairs):
		raise AuthenticationFailed("Telegram init data contains duplicate fields.")

	_verify_payload(fields, mini_app=True)
	try:
		user_data = json.loads(fields["user"])
	except (KeyError, TypeError, ValueError) as exc:
		raise AuthenticationFailed("Telegram user data is invalid.") from exc
	if not isinstance(user_data, dict) or "id" not in user_data:
		raise AuthenticationFailed("Telegram user data is invalid.")
	return user_data


def verify_login_widget_payload(fields):
	_verify_payload(fields, mini_app=False)
	if "id" not in fields:
		raise AuthenticationFailed("Telegram user ID is missing.")
	return fields


@transaction.atomic
def get_or_create_telegram_user(user_data):
	try:
		telegram_id = int(user_data["id"])
	except (KeyError, TypeError, ValueError) as exc:
		raise AuthenticationFailed("Telegram user ID is invalid.") from exc
	if telegram_id <= 0:
		raise AuthenticationFailed("Telegram user ID is invalid.")

	user_model = get_user_model()
	profile = TelegramUser.objects.select_related("auth_user").filter(
		telegram_id=telegram_id,
	).first()
	if profile and profile.auth_user_id:
		auth_user = profile.auth_user
	else:
		auth_user, created = user_model.objects.get_or_create(
			username=f"telegram_{telegram_id}",
		)
		if created:
			auth_user.set_unusable_password()
			auth_user.save(update_fields=["password"])

	profile_values = {
		"username": str(user_data.get("username", ""))[:64],
		"first_name": str(user_data.get("first_name", ""))[:128],
		"last_name": str(user_data.get("last_name", ""))[:128],
		"language_code": str(user_data.get("language_code", ""))[:10],
	}
	if profile is None:
		profile = TelegramUser.objects.create(
			telegram_id=telegram_id,
			auth_user=auth_user,
			**profile_values,
		)
	else:
		changed_fields = []
		for field, value in profile_values.items():
			if getattr(profile, field) != value:
				setattr(profile, field, value)
				changed_fields.append(field)
		if profile.auth_user_id is None:
			profile.auth_user = auth_user
			changed_fields.append("auth_user")
		if changed_fields:
			profile.save(update_fields=changed_fields + ["updated_at"])

	if profile.is_blocked or not auth_user.is_active:
		raise AuthenticationFailed("This Telegram account is not allowed to log in.")
	return profile


@transaction.atomic
def link_mini_app_user(user_data, *, email, password):
	try:
		telegram_id = int(user_data["id"])
	except (KeyError, TypeError, ValueError) as exc:
		raise AuthenticationFailed("Telegram user ID is invalid.") from exc
	if telegram_id <= 0:
		raise AuthenticationFailed("Telegram user ID is invalid.")

	user_model = get_user_model()
	profile = TelegramUser.objects.select_for_update().select_related("auth_user").filter(
		telegram_id=telegram_id,
	).first()
	normalized_email = (email or "").strip().lower()
	is_temporary_profile = bool(
		profile
		and profile.auth_user_id
		and _is_temporary_auth_user(profile.auth_user, telegram_id)
	)
	if profile and profile.auth_user_id and not is_temporary_profile:
		auth_user = profile.auth_user
	else:
		matching_users = user_model.objects.filter(email__iexact=normalized_email) if normalized_email else user_model.objects.none()
		if profile and profile.auth_user_id:
			matching_users = matching_users.exclude(pk=profile.auth_user_id)
		if matching_users.count() > 1:
			raise AuthenticationFailed("More than one account uses this email. Contact support.")
		auth_user = matching_users.first()
		if auth_user:
			if not auth_user.check_password(password):
				raise AuthenticationFailed("Email or password is incorrect.")
		elif is_temporary_profile:
			auth_user = profile.auth_user
			if normalized_email and auth_user.email and auth_user.email.lower() != normalized_email:
				raise AuthenticationFailed("Email or password is incorrect.")
			if normalized_email:
				auth_user.email = normalized_email
			try:
				password_validation.validate_password(password, user=auth_user)
			except DjangoValidationError as exc:
				raise ValidationError({"password": exc.messages}) from exc
			auth_user.set_password(password)
			auth_user.save(update_fields=["email", "password"])
		else:
			base_username = f"telegram_{telegram_id}"
			username = base_username
			suffix = 1
			while user_model.objects.filter(username=username).exists():
				suffix += 1
				username = f"{base_username}_{suffix}"
			auth_user = user_model(username=username, email=normalized_email)
			try:
				password_validation.validate_password(password, user=auth_user)
			except DjangoValidationError as exc:
				raise ValidationError({"password": exc.messages}) from exc
			auth_user.set_password(password)
			auth_user.save()

	if not auth_user.is_active:
		raise AuthenticationFailed("This account is not allowed to log in.")
	if TelegramUser.objects.filter(auth_user=auth_user).exclude(pk=getattr(profile, "pk", None)).exists():
		raise AuthenticationFailed("This account is already linked to another Telegram account.")

	profile_values = {
		"username": str(user_data.get("username", ""))[:64],
		"first_name": str(user_data.get("first_name", ""))[:128],
		"last_name": str(user_data.get("last_name", ""))[:128],
		"language_code": str(user_data.get("language_code", ""))[:10],
	}
	if profile is None:
		profile = TelegramUser.objects.create(
			telegram_id=telegram_id,
			auth_user=auth_user,
			**profile_values,
		)
	else:
		profile.auth_user = auth_user
		for field, value in profile_values.items():
			setattr(profile, field, value)
		profile.save(update_fields=["auth_user", *profile_values, "updated_at"])

	if profile.is_blocked:
		raise AuthenticationFailed("This Telegram account is not allowed to log in.")
	return profile


@transaction.atomic
def link_profile_by_username(profile, username) -> str:
	"""Attach ``profile`` to the site account named ``username``.

	Used by the ``/start <username>`` deep link the profile page generates.
	Returns ``linked``, ``already``, ``not_found``, ``inactive``, ``taken`` or
	``conflict``; only a disposable ``telegram_<id>`` account is replaced, a
	real site account on the profile is never stolen.
	"""
	cleaned = str(username or "").strip().lstrip("@")
	if not cleaned:
		return "not_found"

	target = get_user_model().objects.filter(username__iexact=cleaned).first()
	if target is None:
		return "not_found"
	if profile.auth_user_id == target.pk:
		return "already"
	if not target.is_active:
		return "inactive"
	if TelegramUser.objects.filter(auth_user=target).exclude(pk=profile.pk).exists():
		return "taken"

	current = profile.auth_user
	if current is not None and not _is_temporary_auth_user(current, profile.telegram_id):
		return "conflict"

	profile.auth_user = target
	profile.save(update_fields=["auth_user", "updated_at"])
	# Keep the reverse relation warm: handlers run in async context where a
	# lazy ``auth_user.subscription`` fetch would raise SynchronousOnlyOperation.
	subscription = Subscription.objects.filter(user=target).first()
	if subscription is not None:
		target.subscription = subscription
	return "linked"


def create_telegram_tokens(profile, auth_method):
	refresh = RefreshToken.for_user(profile.auth_user)
	refresh["auth_method"] = auth_method
	refresh["telegram_id"] = profile.telegram_id
	return {
		"refresh": str(refresh),
		"access": str(refresh.access_token),
	}