""""O'xshash animelar": relevance scoring over real catalogue metadata.

The recommendation is computed in the database from what the catalogue
actually stores — shared genres, media type, status, release year and
language — so it needs no extra service and always reflects the current rows.
The current title is excluded, results are de-duplicated by primary key, and
the whole thing is one query per page.
"""

from __future__ import annotations

from typing import List, Optional

from django.db.models import (
	Case,
	Count,
	F,
	IntegerField,
	Q,
	Value,
	When,
)

from .models import MediaTitle

# How many suggestions a detail page asks for; the endpoint clamps to this so
# one request can never drag the whole catalogue into memory.
SIMILAR_LIMIT = 12
MAX_LIMIT = 30

# Weights: a shared genre is the strongest signal available, then the format,
# then a close release window, then "same show, different week".
GENRE_WEIGHT = 10
TYPE_WEIGHT = 6
STATUS_WEIGHT = 2
YEAR_NEAR_WEIGHT = 3
YEAR_FAR_WEIGHT = 1
LANGUAGE_WEIGHT = 1


def _year_expression(year: Optional[int], output_field=IntegerField()):
	if not year:
		return Value(0, output_field=output_field)
	return Case(
		When(release_year__isnull=False, release_year__gte=year - 2, release_year__lte=year + 2, then=Value(YEAR_NEAR_WEIGHT)),
		When(release_year__isnull=False, release_year__gte=year - 5, release_year__lte=year + 5, then=Value(YEAR_FAR_WEIGHT)),
		default=Value(0),
		output_field=output_field,
	)


def _scored(queryset, title: MediaTitle, genre_ids):
	"""Annotate ``queryset`` with the relevance score of ``title``."""
	if genre_ids:
		shared = Count(
			"genres",
			filter=Q(genres__id__in=genre_ids),
			distinct=True,
		)
	else:
		shared = Value(0, output_field=IntegerField())

	scored = queryset.annotate(shared_genres=shared).annotate(
		score=F("shared_genres") * GENRE_WEIGHT
		+ Case(
			When(type=title.type, then=Value(TYPE_WEIGHT)),
			default=Value(0),
			output_field=IntegerField(),
		)
		+ Case(
			When(status=title.status, then=Value(STATUS_WEIGHT)),
			default=Value(0),
			output_field=IntegerField(),
		)
		+ _year_expression(title.release_year)
		+ Case(
			When(language=title.language, then=Value(LANGUAGE_WEIGHT)),
			default=Value(0),
			output_field=IntegerField(),
		)
	)
	return scored


def similar_titles_sync(
	title: MediaTitle, *, limit: int = SIMILAR_LIMIT
) -> List[MediaTitle]:
	"""Titles most similar to ``title``, best match first.

	Two passes keep the result honest:

	1. the same format (anime with anime), ranked by shared genres and the
	   metadata above — this is what a "similar anime" rail should show;
	2. only if that is still short, other formats that share at least one
	   genre, so a small catalogue still offers something relevant instead of
	   an empty section.
	"""
	limit = max(1, min(int(limit or SIMILAR_LIMIT), MAX_LIMIT))
	genre_ids = list(title.genres.values_list("id", flat=True))
	base = MediaTitle.objects.with_counts().exclude(pk=title.pk).prefetch_related("genres")

	same_type = _scored(base.filter(type=title.type), title, genre_ids)
	same_type = list(
		same_type.order_by(
			"-score", "-rating_average", "-rating_count", "-created_at", "-id"
		)[:limit]
	)
	seen = {row.pk for row in same_type}
	if len(same_type) >= limit:
		return same_type

	# Cross-format fill: only rows that actually share a genre, and never the
	# same row twice.
	if genre_ids:
		cross = _scored(base.exclude(type=title.type).filter(genres__id__in=genre_ids), title, genre_ids).distinct()
		for row in cross.order_by(
			"-score", "-rating_average", "-rating_count", "-created_at", "-id"
		):
			if row.pk in seen:
				continue
			same_type.append(row)
			seen.add(row.pk)
			if len(same_type) >= limit:
				break
	return same_type
