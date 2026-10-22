"""Account actions proposed by AniVoy, confirmed by the user, then executed.

The assistant may never touch the account itself: its ``submit_action`` tool
only *proposes* one, and everything real happens after the user confirmed the
card — on the website or in the Telegram bot. A proposal travels as a signed
token (``django.core.signing``) carrying the action key, the values the model
picked and the user it belongs to, so a client can neither invent an action nor
apply it to somebody else.

Privacy is the point of this split: the model writes the values it understood
from the request («familiyamni Kim qil» → ``{"last_name": "Kim"}``), the card
is built server-side from the real account state, and the tool's text result is
a fixed sentence — the model never reads a name, a plan or a photo back.

Every action is three small functions plus a field list:

* ``prepare`` — normalise and validate the merged values (whitelist first);
* ``fields``  — the editable card the client renders;
* ``run``     — the real write, only ever reached through :func:`execute`.
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Dict, List, Optional, Tuple

from django.core import signing

from . import community
from .community import CommunityError
from .models import MediaTitle, TitleComment

logger = logging.getLogger(__name__)

# Salt keeps these tokens in their own namespace; the window is long enough
# for a human to read a card and short enough that a stale one is worthless.
TOKEN_SALT = "movies.ai_action"
TOKEN_MAX_AGE = 1800

AVATAR_MAX_BYTES = 5 * 1024 * 1024
NAME_MAX_LENGTH = 150

THEME_OPTIONS = ["system", "light", "dark"]
THEME_LABELS = {"system": "Tizim", "light": "Kunduzgi", "dark": "Tungi"}

LINK_TELEGRAM = "link_telegram"
UNLINK_TELEGRAM = "unlink_telegram"

ACTION_LABELS = {
	"write_comment": "Izoh yozish",
	"set_rating": "Yulduzcha qo'yish",
	"set_avatar": "Profil rasmi",
	"subscription_request": "Obunani uzaytirish",
	LINK_TELEGRAM: "Telegramga ulash",
	UNLINK_TELEGRAM: "Telegramni uzish",
	"change_name": "Ism/familiya",
	"set_theme": "Mavzu",
	"set_reduce_motion": "Harakatlarni kamaytirish",
}


class ActionError(Exception):
	"""A refused action; ``code`` is what the clients branch on."""

	def __init__(self, code: str, detail: str) -> None:
		super().__init__(detail)
		self.code = code
		self.detail = detail


# --------------------------------------------------------------------------- #
# Small shared helpers
# --------------------------------------------------------------------------- #
def _as_int(value: Any, *, field: str) -> int:
	try:
		number = int(value)
	except (TypeError, ValueError):
		raise ActionError("invalid_values", f"«{field}» butun son bo'lishi kerak.") from None
	return number


def _text(value: Any, *, max_length: int) -> str:
	return str(value or "").strip()[:max_length]


def _find_title(value: Any) -> MediaTitle:
	title_id = _as_int(value, field="title_id")
	title = MediaTitle.objects.filter(pk=title_id).first()
	if title is None:
		raise ActionError("invalid_values", "Bunday kontent katalogda topilmadi.")
	return title


def _settings_for(user):
	from users.models import UserSettings

	settings_object, _ = UserSettings.objects.get_or_create(user=user)
	return settings_object


def _linked_profile(user):
	from users.models import TelegramUser

	return TelegramUser.objects.filter(auth_user=user).first()


def _check_image(upload) -> None:
	content_type = str(getattr(upload, "content_type", "") or "")
	size = int(getattr(upload, "size", 0) or 0)
	if content_type and not content_type.startswith("image/"):
		raise ActionError("invalid_values", "Faqat rasm fayli yuklash mumkin.")
	if size > AVATAR_MAX_BYTES:
		raise ActionError("invalid_values", "Rasm 5 MB dan oshmasligi kerak.")


def _plan_options() -> List[Dict[str, str]]:
	from users.plans import PLAN_LABELS, PLAN_ORDER, plan_price

	options = []
	for plan in PLAN_ORDER:
		price = plan_price(plan)
		options.append({
			"value": plan,
			"label": f"{PLAN_LABELS.get(plan, plan)} — {price:,} so'm" if price else PLAN_LABELS.get(plan, plan),
		})
	return options


# --------------------------------------------------------------------------- #
# write_comment — an izoh under a title, optionally with a 1-10 score
# --------------------------------------------------------------------------- #
def _comment_prepare(user, values, source) -> Dict[str, Any]:
	title = _find_title(values.get("title_id"))
	body = community.validate_body(values.get("body"))
	clean: Dict[str, Any] = {"title_id": title.pk, "body": body}
	score = values.get("score")
	if score not in (None, ""):
		clean["score"] = community.validate_score(score)
	return clean


def _comment_fields(user, values, source) -> List[Dict[str, Any]]:
	title = MediaTitle.objects.filter(pk=values.get("title_id")).first()
	return [
		{
			"key": "title",
			"label": "Kontent",
			"type": "static",
			"value": title.title if title else "—",
			"href": f"/media/{title.slug}" if title else "",
		},
		{
			"key": "score",
			"label": "Yulduzchalar",
			"type": "int",
			"value": values.get("score"),
			"min": community.MIN_SCORE,
			"max": community.MAX_SCORE,
			"editable": True,
			"required": False,
		},
		{
			"key": "body",
			"label": "Izoh matni",
			"type": "textarea",
			"value": values.get("body", ""),
			"editable": True,
			"required": True,
			"max_length": community.COMMENT_MAX_LENGTH,
			"help": "AI yozgan matn — o'zgartirishingiz mumkin.",
		},
	]


def _comment_run(user, values, files, source) -> Tuple[Dict[str, Any], str]:
	title = _find_title(values.get("title_id"))
	comment_source = TitleComment.Source.BOT if source == "bot" else TitleComment.Source.SITE
	comment, created = community.create_comment_sync(
		user=user, title=title, body=values.get("body"), source=comment_source
	)
	data: Dict[str, Any] = {"comment_id": comment.pk, "created": created, "title_id": title.pk}
	message = "Izoh yuborildi." if created else "Bunday izoh allaqachon yuborilgan edi."
	if values.get("score") is not None:
		rating = community.set_rating_sync(user, title, values["score"])
		data["score"] = rating.score
		message = "Izoh va yulduzcha saqlandi."
	return data, message


# --------------------------------------------------------------------------- #
# set_rating — the user's own 1-10 score of one title
# --------------------------------------------------------------------------- #
def _rating_prepare(user, values, source) -> Dict[str, Any]:
	title = _find_title(values.get("title_id"))
	return {"title_id": title.pk, "score": community.validate_score(values.get("score"))}


def _rating_fields(user, values, source) -> List[Dict[str, Any]]:
	title = MediaTitle.objects.filter(pk=values.get("title_id")).first()
	return [
		{
			"key": "title",
			"label": "Kontent",
			"type": "static",
			"value": title.title if title else "—",
			"href": f"/media/{title.slug}" if title else "",
		},
		{
			"key": "score",
			"label": "Yulduzchalar",
			"type": "int",
			"value": values.get("score"),
			"min": community.MIN_SCORE,
			"max": community.MAX_SCORE,
			"editable": True,
			"required": True,
		},
	]


def _rating_run(user, values, files, source) -> Tuple[Dict[str, Any], str]:
	title = _find_title(values.get("title_id"))
	rating = community.set_rating_sync(user, title, values.get("score"))
	return {"title_id": title.pk, "score": rating.score}, "Yulduzcha saqlandi."


# --------------------------------------------------------------------------- #
# set_avatar — an emoji/text avatar or an uploaded picture (UserSettings)
# --------------------------------------------------------------------------- #
def _avatar_prepare(user, values, source) -> Dict[str, Any]:
	value = _text(values.get("avatar"), max_length=500)
	if not value:
		raise ActionError("invalid_values", "Profil rasmi (emoji yoki rasm havolasi) kiriting.")
	if value.startswith(("http://", "https://")):
		if len(value) > 500:
			raise ActionError("invalid_values", "Rasm havolasi juda uzun.")
	elif len(value) > 64:
		raise ActionError("invalid_values", "Emoji yoki qisqa matn kiriting.")
	return {"avatar": value}


def _avatar_fields(user, values, source) -> List[Dict[str, Any]]:
	settings_object = _settings_for(user)
	return [
		{
			"key": "avatar",
			"label": "Emoji yoki rasm havolasi",
			"type": "text",
			"value": values.get("avatar", ""),
			"editable": True,
			"required": True,
			"help": "Masalan 🦊 yoki https://…/avatar.jpg",
		},
		{
			"key": "avatar_file",
			"label": "Rasm yuklash (ixtiyoriy)",
			"type": "file",
			"required": False,
			"accept": "image/*",
			"value": bool(getattr(settings_object, "avatar_file", None)),
		},
	]


def _avatar_run(user, values, files, source) -> Tuple[Dict[str, Any], str]:
	settings_object = _settings_for(user)
	uploaded = files.get("avatar_file")
	if uploaded is not None:
		_check_image(uploaded)
		settings_object.avatar_file = uploaded
		settings_object.save(update_fields=["avatar_file", "updated_at"])
		return {"avatar_file": str(settings_object.avatar_file.name)}, "Profil rasmi yangilandi."
	settings_object.avatar = values.get("avatar", "")
	settings_object.save(update_fields=["avatar", "updated_at"])
	return {"avatar": settings_object.avatar}, "Profil rasmi yangilandi."


# --------------------------------------------------------------------------- #
# subscription_request — the payment screenshot flow, shared with «Obuna»
# --------------------------------------------------------------------------- #
def _subscription_prepare(user, values, source) -> Dict[str, Any]:
	from users.plans import PLAN_ORDER

	plan = str(values.get("plan") or "").strip().lower()
	if plan and plan not in PLAN_ORDER:
		raise ActionError("invalid_values", "Bunday tarif mavjud emas.")
	return {"plan": plan}


def _subscription_fields(user, values, source) -> List[Dict[str, Any]]:
	from users.plans import card_number

	return [
		{
			"key": "plan",
			"label": "Tarif",
			"type": "select",
			"value": values.get("plan") or "",
			"options": _plan_options(),
			"editable": True,
			"required": True,
		},
		{
			"key": "card_number",
			"label": "Karta raqami",
			"type": "static",
			"value": card_number() or "—",
		},
		{
			"key": "screenshot",
			"label": "To'lov skrinshoti",
			"type": "file",
			"required": True,
			"accept": "image/*",
		},
	]


def _subscription_run(user, values, files, source) -> Tuple[Dict[str, Any], str]:
	from users.models import SubscriptionRequest
	from users.plans import PLAN_ORDER, card_number, plan_price

	plan = str(values.get("plan") or "").strip().lower()
	if plan not in PLAN_ORDER:
		raise ActionError("needs_input", "Tarifni tanlang.")
	uploaded = files.get("screenshot")
	if uploaded is None:
		# The bot never carries a file through the token: the caller drops the
		# user into the shared «awaiting_screenshot» state instead.
		raise ActionError("needs_input", "To'lov skrinshotini yuklang.")
	_check_image(uploaded)
	pending = SubscriptionRequest.objects.filter(
		user=user, plan=plan, status=SubscriptionRequest.Status.PENDING
	).exists()
	if pending:
		raise ActionError("conflict", "Bu tarif uchun arizangiz allaqachon ko'rib chiqilmoqda.")
	instance = SubscriptionRequest.objects.create(
		user=user,
		plan=plan,
		amount=plan_price(plan),
		card_number=card_number(),
		screenshot=uploaded,
		status=SubscriptionRequest.Status.PENDING,
	)
	try:
		from users.telegram_notify import notify_admins_new_request

		notify_admins_new_request(instance)
	except Exception:  # noqa: BLE001 - a delivery failure must not lose the request
		logger.warning("Could not notify admins about request %s.", instance.pk, exc_info=True)
	return {
		"request_id": instance.pk,
		"plan": plan,
	}, "Ariza yuborildi — administratorlar to'lovni tekshirib, tasdiqlashadi."


# --------------------------------------------------------------------------- #
# link_telegram / unlink_telegram — the website account ↔ Telegram profile
# --------------------------------------------------------------------------- #
def _link_prepare(user, values, source) -> Dict[str, Any]:
	return {}


def _link_fields(user, values, source) -> List[Dict[str, Any]]:
	profile = _linked_profile(user)
	username = getattr(profile, "username", "") or ""
	return [
		{
			"key": "status",
			"label": "Holat",
			"type": "static",
			"value": f"Ulangan (@{username})" if profile else "Ulanmagan",
		},
	]


def _link_info(user) -> Dict[str, Any]:
	"""The polling payload the website's link card watches."""
	from django.conf import settings as django_settings

	profile = _linked_profile(user)
	username = str(getattr(profile, "username", "") or "")
	bot_username = str(getattr(django_settings, "BOT_USERNAME", "") or "").lstrip("@")
	url = ""
	if bot_username and getattr(user, "username", ""):
		url = f"https://t.me/{bot_username}?start={user.username}"
	return {"linked": profile is not None, "username": username, "url": url}


def _unlink_prepare(user, values, source) -> Dict[str, Any]:
	return {}


def _unlink_fields(user, values, source) -> List[Dict[str, Any]]:
	profile = _linked_profile(user)
	return [
		{
			"key": "status",
			"label": "Ulangan akkaunt",
			"type": "static",
			"value": f"@{getattr(profile, 'username', '')}" if profile else "Ulanmagan",
		},
	]


def _unlink_run(user, values, files, source) -> Tuple[Dict[str, Any], str]:
	profile = _linked_profile(user)
	if profile is None:
		return {"linked": False}, "Telegram akkaunt allaqachon uzilgan."
	profile.auth_user = None
	profile.save(update_fields=["auth_user", "updated_at"])
	return {"linked": False}, "Telegram akkaunt uzildi."


# --------------------------------------------------------------------------- #
# change_name — the site account's first/last name (shown on comments)
# --------------------------------------------------------------------------- #
def _name_prepare(user, values, source) -> Dict[str, Any]:
	first = values.get("first_name")
	last = values.get("last_name")
	if first is None:
		first = getattr(user, "first_name", "") or ""
	if last is None:
		last = getattr(user, "last_name", "") or ""
	first = _text(first, max_length=NAME_MAX_LENGTH)
	last = _text(last, max_length=NAME_MAX_LENGTH)
	if not first and not last:
		raise ActionError("invalid_values", "Ism yoki familiyani kiriting.")
	return {"first_name": first, "last_name": last}


def _name_fields(user, values, source) -> List[Dict[str, Any]]:
	return [
		{
			"key": "first_name",
			"label": "Ism",
			"type": "text",
			"value": values.get("first_name", ""),
			"editable": True,
			"required": False,
			"max_length": NAME_MAX_LENGTH,
		},
		{
			"key": "last_name",
			"label": "Familiya",
			"type": "text",
			"value": values.get("last_name", ""),
			"editable": True,
			"required": False,
			"max_length": NAME_MAX_LENGTH,
		},
	]


def _name_run(user, values, files, source) -> Tuple[Dict[str, Any], str]:
	user.first_name = values.get("first_name", "")
	user.last_name = values.get("last_name", "")
	user.save(update_fields=["first_name", "last_name"])
	return {
		"first_name": user.first_name,
		"last_name": user.last_name,
	}, "Ism-familiya yangilandi."


# --------------------------------------------------------------------------- #
# set_theme / set_reduce_motion — the «Sozlamalar» preferences
# --------------------------------------------------------------------------- #
def _theme_prepare(user, values, source) -> Dict[str, Any]:
	theme = str(values.get("theme") or "").strip().lower()
	if not theme:
		theme = _settings_for(user).theme
	if theme not in THEME_OPTIONS:
		raise ActionError("invalid_values", "Mavzu noto'g'ri.")
	return {"theme": theme}


def _theme_fields(user, values, source) -> List[Dict[str, Any]]:
	return [
		{
			"key": "theme",
			"label": "Mavzu",
			"type": "select",
			"value": values.get("theme") or "",
			"options": [{"value": key, "label": THEME_LABELS[key]} for key in THEME_OPTIONS],
			"editable": True,
			"required": True,
		},
	]


def _theme_run(user, values, files, source) -> Tuple[Dict[str, Any], str]:
	settings_object = _settings_for(user)
	settings_object.theme = values.get("theme", settings_object.theme)
	settings_object.save(update_fields=["theme", "updated_at"])
	return {"theme": settings_object.theme}, "Mavzu yangilandi."


def _motion_prepare(user, values, source) -> Dict[str, Any]:
	enabled = values.get("enabled")
	if enabled is None:
		enabled = _settings_for(user).reduce_motion
	return {"enabled": bool(enabled)}


def _motion_fields(user, values, source) -> List[Dict[str, Any]]:
	return [
		{
			"key": "enabled",
			"label": "Harakatlarni kamaytirish",
			"type": "bool",
			"value": bool(values.get("enabled")),
			"editable": True,
			"required": True,
			"help": "Yong'oq-sekin animatsiyalarni o'chiradi.",
		},
	]


def _motion_run(user, values, files, source) -> Tuple[Dict[str, Any], str]:
	settings_object = _settings_for(user)
	settings_object.reduce_motion = bool(values.get("enabled"))
	settings_object.save(update_fields=["reduce_motion", "updated_at"])
	return {"enabled": settings_object.reduce_motion}, "Sozlama saqlandi."


# --------------------------------------------------------------------------- #
# The catalogue
# --------------------------------------------------------------------------- #
ACTIONS: Dict[str, Dict[str, Any]] = {
	"write_comment": {
		"label": ACTION_LABELS["write_comment"],
		"prepare": _comment_prepare,
		"fields": _comment_fields,
		"run": _comment_run,
	},
	"set_rating": {
		"label": ACTION_LABELS["set_rating"],
		"prepare": _rating_prepare,
		"fields": _rating_fields,
		"run": _rating_run,
	},
	"set_avatar": {
		"label": ACTION_LABELS["set_avatar"],
		"prepare": _avatar_prepare,
		"fields": _avatar_fields,
		"run": _avatar_run,
	},
	"subscription_request": {
		"label": ACTION_LABELS["subscription_request"],
		"prepare": _subscription_prepare,
		"fields": _subscription_fields,
		"run": _subscription_run,
	},
	LINK_TELEGRAM: {
		"label": ACTION_LABELS[LINK_TELEGRAM],
		"kind": "link",
		"prepare": _link_prepare,
		"fields": _link_fields,
		"run": None,
		"link": _link_info,
	},
	UNLINK_TELEGRAM: {
		"label": ACTION_LABELS[UNLINK_TELEGRAM],
		"prepare": _unlink_prepare,
		"fields": _unlink_fields,
		"run": _unlink_run,
	},
	"change_name": {
		"label": ACTION_LABELS["change_name"],
		"prepare": _name_prepare,
		"fields": _name_fields,
		"run": _name_run,
	},
	"set_theme": {
		"label": ACTION_LABELS["set_theme"],
		"prepare": _theme_prepare,
		"fields": _theme_fields,
		"run": _theme_run,
	},
	"set_reduce_motion": {
		"label": ACTION_LABELS["set_reduce_motion"],
		"prepare": _motion_prepare,
		"fields": _motion_fields,
		"run": _motion_run,
	},
}

# Editable keys per action — the whitelist a client's edits are filtered by.
EDITABLE_KEYS: Dict[str, Tuple[str, ...]] = {
	"write_comment": ("body", "score"),
	"set_rating": ("score",),
	"set_avatar": ("avatar",),
	"subscription_request": ("plan",),
	"change_name": ("first_name", "last_name"),
	"set_theme": ("theme",),
	"set_reduce_motion": ("enabled",),
}


def known_actions() -> List[str]:
	return sorted(ACTIONS)


def action_label(key: str) -> str:
	return ACTIONS.get(str(key or ""), {}).get("label", str(key or ""))


# --------------------------------------------------------------------------- #
# Token + the two public entry points
# --------------------------------------------------------------------------- #
def issue_token(user, key: str, values: Dict[str, Any], source: str) -> str:
	return signing.dumps(
		{"u": user.pk, "a": key, "v": values, "s": source or "site"},
		salt=TOKEN_SALT,
	)


def load_token(token: str) -> Dict[str, Any]:
	try:
		data = signing.loads(str(token or ""), salt=TOKEN_SALT, max_age=TOKEN_MAX_AGE)
	except signing.SignatureExpired as exc:
		raise ActionError("expired", "Kartaning muddati tugagan. Yangi amal so'rang.") from exc
	except signing.BadSignature as exc:
		raise ActionError("invalid_token", "Amal kartasi yaroqsiz.") from exc
	if not isinstance(data, dict):
		raise ActionError("invalid_token", "Amal kartasi yaroqsiz.")
	return data


def _prepare(spec: Dict[str, Any], user, values: Dict[str, Any], source: str) -> Dict[str, Any]:
	"""Run the action's validation, flattening CommunityError into ActionError."""
	try:
		return spec["prepare"](user, values, source)
	except CommunityError as exc:
		raise ActionError(exc.code, exc.detail) from exc


def _run(spec: Dict[str, Any], user, values, files, source) -> Tuple[Dict[str, Any], str]:
	try:
		return spec["run"](user, values, files, source)
	except CommunityError as exc:
		raise ActionError(exc.code, exc.detail) from exc


def build_action(user, key: str, values: Any = None, *, source: str = "site") -> Dict[str, Any]:
	"""Validate what the model proposed and turn it into a client card.

	Everything user-specific (the title's name, the current plan, the linked
	username) is read here, server-side: the card is built for the client and
	never travels back through the model.
	"""
	key = str(key or "").strip()
	spec = ACTIONS.get(key)
	if spec is None:
		raise ActionError(
			"unknown_action",
			f"Noma'lum amal «{key}». Mavjudlar: " + ", ".join(known_actions()),
		)
	raw = values if isinstance(values, dict) else {}
	clean = _prepare(spec, user, raw, source)
	card: Dict[str, Any] = {
		"token": issue_token(user, key, clean, source),
		"action": key,
		"label": spec["label"],
		"kind": spec.get("kind", "confirm"),
		"source": source,
		"fields": spec["fields"](user, clean, source),
	}
	link_builder: Optional[Callable[[Any], Dict[str, Any]]] = spec.get("link")
	if link_builder is not None:
		card["link"] = link_builder(user)
	return card


def execute(
	user,
	token: str,
	*,
	values: Optional[Dict[str, Any]] = None,
	files: Optional[Dict[str, Any]] = None,
	source: str = "site",
) -> Dict[str, Any]:
	"""Run a confirmed action; raises :class:`ActionError` on any refusal."""
	payload = load_token(token)
	if int(payload.get("u") or 0) != getattr(user, "pk", 0):
		raise ActionError("forbidden", "Bu amal boshqa foydalanuvchiga tegishli.")
	key = str(payload.get("a") or "")
	spec = ACTIONS.get(key)
	if spec is None:
		raise ActionError("unknown_action", "Noma'lum amal.")
	run = spec.get("run")
	if run is None:
		raise ActionError("invalid_action", "Bu amal tasdiq orqali bajarilmaydi.")
	stored = payload.get("v") if isinstance(payload.get("v"), dict) else {}
	merged: Dict[str, Any] = dict(stored)
	for field_key, value in (values or {}).items():
		if field_key in EDITABLE_KEYS.get(key, ()):
			merged[field_key] = value
	clean = _prepare(spec, user, merged, source)
	data, message = _run(spec, user, clean, files or {}, source)
	return {
		"action": key,
		"label": spec["label"],
		"message": message,
		"data": data,
	}
