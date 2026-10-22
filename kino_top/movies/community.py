"""Comments and 1-10 ratings shared by the website, the bot and the panel.

Everything here is synchronous on purpose: the Django views call it directly
and the aiogram handlers wrap it with ``bot.utils.to_async`` (the project's
rule for ORM code used from async handlers). One module keeps the validation,
the duplicate protection and the rating arithmetic identical on every platform,
so a comment written on the site and one written in Telegram are the same kind
of record in the same table.
"""

from __future__ import annotations

import math
import re
import unicodedata
from typing import Any, Dict, List, Optional, Sequence, Tuple

from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.db.models import Avg, Count, Q
from django.utils import timezone

from .models import MediaPart, MediaTitle, TitleComment, TitleRating

# Comments are short opinions, not documents: the same cap is enforced in the
# serializer, in the bot (before the FSM stores the text) and here.
COMMENT_MAX_LENGTH = TitleComment.MAX_LENGTH
MIN_SCORE = TitleRating.MIN_SCORE
MAX_SCORE = TitleRating.MAX_SCORE

# Public payloads paginate the same way everywhere (site + bot).
COMMENT_PAGE_SIZE = 10

# Characters that carry no meaning but show up when text is copied from a
# phone keyboard (zero-width joiners, bidi controls, stray direction marks).
_NOISE = dict.fromkeys(map(ord, "\u200b\u200c\u200d\u2060\ufeff\u200e\u200f"), None)


class CommunityError(Exception):
	"""A user-fixable problem (bad input, duplicate, forbidden)."""

	def __init__(self, code: str, detail: str):
		super().__init__(detail)
		self.code = code
		self.detail = detail


EMPTY_COMMENT = "Izoh matni bo'sh bo'lmasligi kerak."
TOO_LONG_COMMENT = f"Izoh {COMMENT_MAX_LENGTH} belgidan oshmasligi kerak."
DUPLICATE_COMMENT = "Bunday izoh allaqachon yuborilgan."
INVALID_RATING = f"Bahol {MIN_SCORE} dan {MAX_SCORE} gacha bo'lishi kerak."
NOT_FOUND = "Yozuv topilmadi."
FORBIDDEN = "Bu amal uchun ruxsat yo'q."


def normalize_body(text: Any) -> str:
	"""Trim, drop invisible noise and keep the user's own line breaks."""
	body = "" if text is None else str(text)
	body = unicodedata.normalize("NFKC", body.translate(_NOISE))
	body = "\n".join(line.rstrip() for line in body.split("\n"))
	# More than two blank lines in a row is padding, not content.
	body = re.sub(r"\n{3,}", "\n\n", body)
	return body.strip()


def validate_body(text: Any) -> str:
	body = normalize_body(text)
	if not body:
		raise CommunityError("empty", EMPTY_COMMENT)
	if len(body) > COMMENT_MAX_LENGTH:
		raise CommunityError("too_long", TOO_LONG_COMMENT)
	return body


def validate_score(value: Any) -> int:
	"""Accept ``"7"``, ``7`` or ``7.0`` and refuse everything else."""
	try:
		score = int(value)
	except (TypeError, ValueError):
		raise CommunityError("invalid_rating", INVALID_RATING) from None
	if score < MIN_SCORE or score > MAX_SCORE:
		raise CommunityError("invalid_rating", INVALID_RATING)
	return score


# ---------------------------------------------------------------------------
# Display helpers (one author shape for every platform)
# ---------------------------------------------------------------------------


def _author_name(user) -> str:
	"""Best available display name: username, Telegram name, then a fallback."""
	if user is None:
		return "Foydalanuvchi"
	username = (getattr(user, "username", "") or "").strip()
	if username:
		return username
	profile = getattr(user, "telegram_profile", None)
	if profile is not None:
		full_name = " ".join(
			part for part in [profile.first_name, profile.last_name] if part
		).strip()
		if full_name:
			return full_name
		if profile.username:
			return profile.username
	email = (getattr(user, "email", "") or "").strip()
	if email:
		return email.split("@")[0]
	return f"Foydalanuvchi #{user.pk}"


def is_premium_user(user) -> bool:
	"""True while the account's subscription is live (the 👑 rule).

	Imported from ``users`` here rather than at module level so ``movies`` never
	depends on another app's imports during Django's app loading.
	"""
	from users.premium import is_premium_user as premium

	return premium(user)


def author_payload(user) -> Dict[str, Any]:
	"""The author block embedded in every comment, on every platform."""
	if user is None:
		return {
			"id": None,
			"username": "",
			"display_name": "Foydalanuvchi",
			"is_premium": False,
		}
	return {
		"id": user.pk,
		"username": (getattr(user, "username", "") or ""),
		"display_name": _author_name(user),
		"is_premium": is_premium_user(user),
	}


def _avatar_letter(name: str) -> str:
	return (name[:1] or "?").upper()


# ---------------------------------------------------------------------------
# Comments
# ---------------------------------------------------------------------------


def _part_payload(part: Optional[MediaPart]) -> Optional[Dict[str, Any]]:
	if part is None:
		return None
	return {
		"id": part.pk,
		"number": part.number,
		"season_number": part.season_number,
		"title": part.title,
	}


def comment_payload(
	comment: TitleComment, *, ratings: Optional[Dict[int, Optional[int]]] = None
) -> Dict[str, Any]:
	"""One comment as the website, the bot and the panel all display it."""
	author = comment.user
	name = _author_name(author)
	score = None
	if ratings is not None and author is not None:
		score = ratings.get(author.pk)
	return {
		"id": comment.pk,
		"body": comment.body,
		"source": comment.source,
		"created_at": comment.created_at,
		"part": _part_payload(comment.part),
		"author": author_payload(author),
		"author_initial": _avatar_letter(name),
		"author_rating": score,
		"title": {
			"id": comment.title_id,
			"title": comment.title.title if comment.title_id else "",
			"slug": comment.title.slug if comment.title_id else "",
			"type": comment.title.type if comment.title_id else "",
		},
	}


def _attach_author_ratings(comments: Sequence[TitleComment]) -> Dict[int, Optional[int]]:
	"""The author's own score of this title, fetched once for the whole page."""
	if not comments:
		return {}
	title_id = comments[0].title_id
	user_ids = [comment.user_id for comment in comments if comment.user_id]
	if not user_ids:
		return {}
	rows = TitleRating.objects.filter(title_id=title_id, user_id__in=user_ids).values_list(
		"user_id", "score"
	)
	return {user_id: score for user_id, score in rows}


def create_comment_sync(
	*,
	user,
	title: MediaTitle,
	body: Any,
	part: Optional[MediaPart] = None,
	source: str = TitleComment.Source.SITE,
) -> Tuple[TitleComment, bool]:
	"""Create a comment; ``False`` in the second slot means "already existed".

	The fingerprint (and its unique constraint) is the duplicate-submission
	guard: a double tap, a retried request or the same text sent from both
	platforms can only ever produce one row.
	"""
	if user is None or not getattr(user, "pk", None):
		raise CommunityError("forbidden", FORBIDDEN)
	text = validate_body(body)
	if part is not None and part.content_id != title.pk:
		raise CommunityError("invalid", "Izoh bu qismga tegishli emas.")

	comment = TitleComment(
		user=user, title=title, part=part, body=text, source=source
	)
	comment.dedupe_hash = comment.compute_dedupe_hash()
	existing = TitleComment.objects.filter(
		user=user, dedupe_hash=comment.dedupe_hash
	).first()
	if existing is not None:
		return existing, False
	try:
		with transaction.atomic():
			comment.save()
	except IntegrityError:  # pragma: no cover - race between two identical sends
		existing = TitleComment.objects.filter(
			user=user, dedupe_hash=comment.dedupe_hash
		).first()
		if existing is None:
			raise CommunityError("duplicate", DUPLICATE_COMMENT) from None
		return existing, False
	return comment, True


def delete_comment_sync(comment: TitleComment) -> None:
	"""Hard delete so every platform stops showing it immediately."""
	comment.delete()


def comment_counts_sync(title: MediaTitle) -> int:
	return TitleComment.objects.filter(title=title).count()


def list_comments_sync(
	title: MediaTitle,
	*,
	part: Optional[MediaPart] = None,
	page: int = 1,
	page_size: int = COMMENT_PAGE_SIZE,
) -> Dict[str, Any]:
	"""Paginated comments (newest first) with author, episode and score."""
	page_size = max(1, min(int(page_size or COMMENT_PAGE_SIZE), 50))
	queryset = TitleComment.objects.filter(title=title).select_related(
		"user", "part", "title"
	)
	if part is not None:
		queryset = queryset.filter(part=part)
	total = queryset.count()
	pages = max(1, math.ceil(total / page_size))
	current = max(1, min(int(page or 1), pages))
	offset = (current - 1) * page_size
	page_rows = list(queryset[offset : offset + page_size])
	ratings = _attach_author_ratings(page_rows)
	return {
		"count": total,
		"page": current,
		"pages": pages,
		"page_size": page_size,
		"results": [comment_payload(row, ratings=ratings) for row in page_rows],
	}


def get_comment_sync(comment_id: int) -> Optional[TitleComment]:
	return (
		TitleComment.objects.select_related("user", "part", "title")
		.filter(pk=comment_id)
		.first()
	)


# ---------------------------------------------------------------------------
# Ratings
# ---------------------------------------------------------------------------


def recompute_title_rating_sync(title) -> Dict[str, Any]:
	"""Re-read every live rating of ``title`` and write the totals back.

	Called after any insert, change or deletion (including an administrator
	removing an abusive score), so the average shown on the site, in the bot and
	in the panel is always derived from the current rows — never stale.
	"""
	title_id = getattr(title, "pk", title)
	row = TitleRating.objects.filter(title_id=title_id).aggregate(
		average=Avg("score"), count=Count("id")
	)
	count = int(row["count"] or 0)
	average = round(float(row["average"] or 0.0), 2)
	MediaTitle.objects.filter(pk=title_id).update(
		rating_average=average,
		rating_count=count,
		# Keep the legacy single number in step (rounded) while anyone has
		# scored; with no ratings the admin's own value stays untouched.
		**({"rating": max(MIN_SCORE, min(MAX_SCORE, round(average)))} if count else {}),
	)
	return {"average": average, "count": count}


def set_rating_sync(user, title, score: Any) -> TitleRating:
	"""Insert or update the single rating ``user`` has for ``title``."""
	if user is None or not getattr(user, "pk", None):
		raise CommunityError("forbidden", FORBIDDEN)
	value = validate_score(score)
	with transaction.atomic():
		rating, created = TitleRating.objects.update_or_create(
			user=user,
			title=title,
			defaults={"score": value},
		)
		recompute_title_rating_sync(title)
	return rating


def remove_rating_sync(user, title) -> bool:
	"""Drop a user's score (used by administrators clearing a bad rating)."""
	deleted, _ = TitleRating.objects.filter(user=user, title=title).delete()
	if deleted:
		recompute_title_rating_sync(title)
	return bool(deleted)


def user_rating_sync(user, title) -> Optional[int]:
	if user is None or not getattr(user, "pk", None):
		return None
	return (
		TitleRating.objects.filter(user=user, title=title)
		.values_list("score", flat=True)
		.first()
	)


def rating_summary_sync(title, user=None) -> Dict[str, Any]:
	"""``{average, count, my_score}`` — the numbers every page displays."""
	return {
		"average": float(getattr(title, "rating_average", 0.0) or 0.0),
		"count": int(getattr(title, "rating_count", 0) or 0),
		"my_score": user_rating_sync(user, title),
		"min": MIN_SCORE,
		"max": MAX_SCORE,
	}


def top_rated_titles_sync(limit: int = 10) -> List[MediaTitle]:
	"""Highest scored titles — shared by the site's rating widgets."""
	return list(
		MediaTitle.objects.filter(rating_count__gt=0)
		.order_by("-rating_average", "-rating_count", "-id")[: max(1, limit)]
	)


# ---------------------------------------------------------------------------
# Administrator maintenance
# ---------------------------------------------------------------------------


def search_comments_sync(
	*,
	query: str = "",
	title_id: Optional[int] = None,
	source: str = "",
	user_id: Optional[int] = None,
	page: int = 1,
	page_size: int = 20,
) -> Dict[str, Any]:
	"""Filtered, paginated comment list for the moderation screen."""
	queryset = TitleComment.objects.select_related("user", "part", "title").order_by(
		"-created_at", "-id"
	)
	text = (query or "").strip()
	if text:
		queryset = queryset.filter(
			Q(body__icontains=text)
			| Q(user__username__icontains=text)
			| Q(title__title__icontains=text)
		)
	if title_id:
		queryset = queryset.filter(title_id=title_id)
	if source in TitleComment.Source.values:
		queryset = queryset.filter(source=source)
	if user_id:
		queryset = queryset.filter(user_id=user_id)
	return _paginate(queryset, page, page_size)


def search_ratings_sync(
	*,
	query: str = "",
	title_id: Optional[int] = None,
	min_score: Optional[int] = None,
	max_score: Optional[int] = None,
	page: int = 1,
	page_size: int = 20,
) -> Dict[str, Any]:
	"""Filtered, paginated rating list for the moderation screen."""
	queryset = TitleRating.objects.select_related("user", "title").order_by(
		"-updated_at", "-id"
	)
	text = (query or "").strip()
	if text:
		queryset = queryset.filter(
			Q(user__username__icontains=text) | Q(title__title__icontains=text)
		)
	if title_id:
		queryset = queryset.filter(title_id=title_id)
	if min_score is not None:
		queryset = queryset.filter(score__gte=min_score)
	if max_score is not None:
		queryset = queryset.filter(score__lte=max_score)
	return _paginate(queryset, page, page_size)


def _paginate(queryset, page: int, page_size: int) -> Dict[str, Any]:
	page_size = max(1, min(int(page_size or 20), 100))
	total = queryset.count()
	pages = max(1, math.ceil(total / page_size))
	current = max(1, min(int(page or 1), pages))
	offset = (current - 1) * page_size
	return {
		"count": total,
		"page": current,
		"pages": pages,
		"page_size": page_size,
		"results": list(queryset[offset : offset + page_size]),
	}


def rating_row_payload(rating: TitleRating) -> Dict[str, Any]:
	"""One rating as the panel shows it (author, title and the score)."""
	return {
		"id": rating.pk,
		"score": rating.score,
		"created_at": rating.created_at,
		"updated_at": rating.updated_at,
		"author": author_payload(rating.user),
		"title": {
			"id": rating.title_id,
			"title": rating.title.title,
			"slug": rating.title.slug,
			"type": rating.title.type,
		},
	}


def delete_comments_sync(comment_ids: Sequence[int]) -> int:
	"""Bulk delete for moderation; returns how many rows actually went away."""
	deleted, _ = TitleComment.objects.filter(pk__in=list(comment_ids)).delete()
	return int(deleted)


def delete_ratings_sync(rating_ids: Sequence[int]) -> List[int]:
	"""Bulk delete scores, recomputing only the titles that were touched."""
	ratings = list(TitleRating.objects.filter(pk__in=list(rating_ids)))
	title_ids = {rating.title_id for rating in ratings}
	deleted, _ = TitleRating.objects.filter(pk__in=[row.pk for row in ratings]).delete()
	for title_id in title_ids:
		recompute_title_rating_sync(title_id)
	return sorted(title_ids)


def comment_count_since(when) -> int:
	return TitleComment.objects.filter(created_at__gte=when).count()


def now():
	return timezone.now()


def display_name(user) -> str:
	return _author_name(user)


def user_lookup(user_id: int):
	return get_user_model().objects.filter(pk=user_id).first()
