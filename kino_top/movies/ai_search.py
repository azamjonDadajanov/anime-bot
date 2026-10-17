"""Vector index and semantic search over the catalogue.

The whole feature exists because a catalogue search by substring cannot answer
"menga sarguzasht va qo'rqinchli animelar ayt": the words the user types are
Uzbek while the store keeps Japanese/Russian/English titles, and no title field
contains "qo'rqinchli". So instead of matching text, every title is described in
one short document, that document is embedded with
:mod:`movies.embeddings` (a multilingual sentence encoder), and the same
encoder embeds the user's request. Titles are then ranked by cosine similarity —
which is why "qo'rqinchli" still lands on a horror title written in another
language.

The index is derived data, never a source of truth:

* ``TitleEmbedding`` holds one vector per title together with the digest of the
  document it came from;
* adding, editing or removing a title (or its genres) re-embeds only that title,
  through the signals in :mod:`movies.signals`;
* ``python manage.py index_anime_embeddings`` builds the initial index and
  backfills anything missing or stale.

Searching is a dot product over the whole matrix, which is exact (no approximate
index) and, at this catalogue's size — a few thousand titles of 384 floats —
both simpler and faster than anything fancier.
"""

from __future__ import annotations

import hashlib
import logging
import re
import threading
from dataclasses import dataclass
from typing import Callable, Dict, Iterable, List, Optional, Sequence

from django.conf import settings
from django.db import transaction
from django.db.models import Count, Max

from . import embeddings
from .models import MediaTitle, TitleEmbedding

logger = logging.getLogger(__name__)

# How a title is described to the model. Uzbek, because the catalogue copy is
# Uzbek and the encoder is multilingual; genres, status and the synopsis carry
# the meaning, and the plain sentences keep the vector close to how a user
# phrases a request.
DOCUMENT_TEMPLATE = (
	"Nomi: {title}\n"
	"Turi: {type}\n"
	"Janrlar: {genres}\n"
	"Yil: {year}\n"
	"Holat: {status}\n"
	"Tavsif: {synopsis}"
)
# The synopsis is trimmed so the whole document stays inside the encoder's
# 128-token window (metadata included): a mean-pooled vector of a truncated text
# is dominated by whatever came first, and measuring the ranking on this
# catalogue showed the shorter document ranks the intended titles slightly
# higher ("dengiz sarguzashtlari" → One Piece: rank 1 vs 2, 0.62 vs 0.61).
DOCUMENT_SYNOPSIS_CHARS = 220
SUMMARY_MAX_CHARS = 180

SUBSCRIPTION_REQUIRED_TEXT = (
	"AI qidiruv faqat obunachilar uchun. «🎫 Obuna» bo'limidan tarifni tanlang."
)
INDEX_UNAVAILABLE_TEXT = (
	"AI qidiruv hozircha ishga tushmagan: model yuklanmagan yoki indeks bo'sh."
)
EMPTY_QUERY_TEXT = "Qidiruv uchun savol yozing."

_SENTENCE_END = re.compile(r"(?<=[.!?…])\s+")


def enabled() -> bool:
	"""Whether the AI search is switched on for this deployment."""
	return bool(getattr(settings, "AI_SEARCH_ENABLED", False))


def top_k() -> int:
	return max(1, int(getattr(settings, "AI_SEARCH_TOP_K", 5) or 5))


def min_score() -> float:
	return float(getattr(settings, "AI_SEARCH_MIN_SCORE", 0.0) or 0.0)


def clean_text(value: object) -> str:
	"""Collapse whitespace so the document is stable for hashing."""
	return " ".join(str(value or "").split())


def title_document(title: MediaTitle, *, genres: Optional[Iterable[str]] = None) -> str:
	"""The text a title is embedded as.

	``genres`` lets a caller pass the already-loaded genre names (the indexer
	prefetches them); without it they are read from the instance.
	"""
	if genres is None:
		genres = [genre.name for genre in title.genres.all()]
	names = [clean_text(name) for name in genres if clean_text(name)]
	synopsis = clean_text(title.synopsis)[:DOCUMENT_SYNOPSIS_CHARS]
	return DOCUMENT_TEMPLATE.format(
		title=clean_text(title.title),
		type=title.get_type_display(),
		genres=", ".join(names) or "—",
		year=title.release_year or "—",
		status=title.get_status_display(),
		synopsis=synopsis or "—",
	)


def document_hash(document: str) -> str:
	return hashlib.sha256(document.encode("utf-8")).hexdigest()


def one_line_summary(title: MediaTitle) -> str:
	"""One sentence about the title, shown under its link in the results.

	The first sentence of the synopsis is exactly the "qisqacha mazmun" a reader
	expects; a title without a synopsis is described by its metadata instead of
	showing an empty line.
	"""
	synopsis = clean_text(title.synopsis)
	if synopsis:
		sentence = _SENTENCE_END.split(synopsis)[0].strip()
		if len(sentence) > SUMMARY_MAX_CHARS:
			sentence = sentence[: SUMMARY_MAX_CHARS - 1].rstrip() + "…"
		return sentence
	genres = ", ".join(genre.name for genre in title.genres.all()[:3])
	label = title.get_type_display().lower()
	if genres:
		return f"{genres} janridagi {label}."
	return f"{title.get_type_display()} — {title.get_status_display().lower()}."


# --------------------------------------------------------------------------- #
# Indexing
# --------------------------------------------------------------------------- #
def index_title(title: MediaTitle, *, force: bool = False) -> bool:
	"""(Re)embed one title. Returns True when a vector was written.

	An unchanged document is left alone, which makes the "index everything"
	command cheap to re-run and keeps the signals from re-embedding on a save
	that changed nothing the model can see.
	"""
	document = title_document(title)
	digest = document_hash(document)
	existing = TitleEmbedding.objects.filter(title=title).first()
	if (
		existing is not None
		and not force
		and existing.document_hash == digest
		and existing.model_name == embeddings.MODEL_NAME
	):
		return False
	vectors = embeddings.encode_texts([document])
	if not vectors:
		return False
	vector = vectors[0]
	TitleEmbedding.objects.update_or_create(
		title=title,
		defaults={
			"model_name": embeddings.MODEL_NAME,
			"dim": len(vector),
			"document_hash": digest,
			"vector": TitleEmbedding.pack(vector),
		},
	)
	return True


def index_title_id(title_id: int, *, force: bool = False) -> bool:
	"""Index a title by id, swallowing the "model not available" case.

	Used by the post-save signals: a catalogue edit must never fail because the
	embedding service is down or the model was not downloaded. The title simply
	stays unindexed and the next ``index_anime_embeddings`` run picks it up.
	"""
	title = MediaTitle.objects.filter(pk=title_id).first()
	if title is None:
		return False
	try:
		return index_title(title, force=force)
	except embeddings.EmbeddingUnavailable as exc:
		logger.warning("Skipping AI index for title %s: %s", title_id, exc)
		return False


def forget_title(title_id: int) -> None:
	"""Drop the vector of a title (used when a title is deleted)."""
	TitleEmbedding.objects.filter(title_id=title_id).delete()


def index_titles(
	queryset=None,
	*,
	force: bool = False,
	limit: Optional[int] = None,
	on_progress: Optional[Callable[[MediaTitle, bool], None]] = None,
) -> Dict[str, int]:
	"""Index every title of ``queryset`` (the whole catalogue by default).

	Returns counters; ``failed`` counts the titles the encoder could not handle
	(which is what the command reports instead of pretending success).
	"""
	queryset = queryset if queryset is not None else MediaTitle.objects.all()
	queryset = queryset.prefetch_related("genres").order_by("pk")
	stats = {"total": 0, "indexed": 0, "skipped": 0, "failed": 0}
	for title in queryset.iterator(chunk_size=200):
		stats["total"] += 1
		try:
			written = index_title(title, force=force)
		except embeddings.EmbeddingUnavailable:
			raise
		except Exception:  # noqa: BLE001 - one bad row must not stop the run
			logger.exception("Failed to index title %s", title.pk)
			stats["failed"] += 1
			if on_progress is not None:
				on_progress(title, False)
			continue
		stats["indexed" if written else "skipped"] += 1
		if on_progress is not None:
			on_progress(title, written)
		if limit and stats["indexed"] >= limit:
			break
	return stats


def stale_titles(queryset=None) -> List[MediaTitle]:
	"""Titles with no vector, or whose stored vector no longer matches the text.

	Cheap (no model involved): the digest is recomputed from the database, so
	this is what tells an operator whether editing the catalogue left the index
	behind.
	"""
	queryset = queryset if queryset is not None else MediaTitle.objects.all()
	stored = {
		row["title_id"]: (row["document_hash"], row["model_name"])
		for row in TitleEmbedding.objects.values("title_id", "document_hash", "model_name")
	}
	stale: List[MediaTitle] = []
	for title in queryset.prefetch_related("genres").iterator(chunk_size=200):
		digest = document_hash(title_document(title))
		entry = stored.get(title.pk)
		if entry is None or entry[0] != digest or entry[1] != embeddings.MODEL_NAME:
			stale.append(title)
	return stale


def index_status() -> Dict[str, object]:
	"""Cheap snapshot of the index, for the API and the dashboard."""
	aggregate = TitleEmbedding.objects.aggregate(
		count=Count("id"), latest=Max("indexed_at")
	)
	return {
		"enabled": enabled(),
		"model_ready": embeddings.is_ready(),
		"model": embeddings.MODEL_NAME,
		"titles": MediaTitle.objects.count(),
		"indexed": aggregate["count"] or 0,
		"latest": aggregate["latest"],
	}


def index_is_empty() -> bool:
	"""True when nothing has ever been embedded (so search cannot answer)."""
	return not TitleEmbedding.objects.filter(
		model_name=embeddings.MODEL_NAME
	).exists()


# --------------------------------------------------------------------------- #
# Signals entry points
# --------------------------------------------------------------------------- #
def schedule_index(title_id: int) -> None:
	"""Re-embed ``title_id`` once the surrounding transaction has committed.

	Deferring to ``on_commit`` matters for genres: the many-to-many rows are
	written after the title itself, so embedding inside the signal would miss
	the genres that were just attached.
	"""
	if not enabled() or not title_id:
		return
	transaction.on_commit(lambda: index_title_id(int(title_id)))


def schedule_index_all(title_ids: Sequence[int]) -> None:
	"""Re-embed several titles after commit (used when a genre is renamed)."""
	if not enabled():
		return
	ids = [int(value) for value in title_ids]
	if not ids:
		return
	def _run() -> None:
		for title_id in ids:
			index_title_id(title_id)

	transaction.on_commit(_run)


def schedule_forget(title_id: int) -> None:
	"""Drop a vector after commit (a deleted title leaves nothing behind)."""
	if not title_id:
		return
	transaction.on_commit(lambda: forget_title(int(title_id)))


# --------------------------------------------------------------------------- #
# Search
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class SearchHit:
	"""One ranked result with everything the clients render."""

	title: MediaTitle
	score: float

	def as_dict(self, *, site_url: str = "") -> dict:
		slug = self.title.slug
		base = str(site_url or "").rstrip("/")
		return {
			"id": self.title.pk,
			"title": self.title.title,
			"slug": slug,
			"type": self.title.type,
			"type_display": self.title.get_type_display(),
			"code": self.title.code,
			"release_year": self.title.release_year,
			"rating": self.title.rating,
			"genres": [genre.name for genre in self.title.genres.all()],
			"summary": one_line_summary(self.title),
			"url": f"{base}/media/{slug}" if base else f"/media/{slug}",
			"score": round(float(self.score), 4),
		}


@dataclass(frozen=True)
class SearchOutcome:
	"""What a search answers: the ranked page, plus every match it was cut from."""

	hits: List[SearchHit]
	total: int

	@property
	def has_more(self) -> bool:
		"""True when more titles matched than are in ``hits``."""
		return self.total > len(self.hits)


_MATRIX_LOCK = threading.Lock()
_MATRIX: Dict[str, object] = {"fingerprint": None, "ids": [], "vectors": None}


def _matrix_fingerprint():
	"""Anything that means "the stored vectors are no longer what we cached"."""
	row = TitleEmbedding.objects.filter(model_name=embeddings.MODEL_NAME).aggregate(
		count=Count("id"), latest=Max("indexed_at")
	)
	return (row["count"] or 0, row["latest"])


def _load_matrix():
	"""The whole index as ``(ids, matrix)``; reloaded only when it changed.

	One aggregate query per search decides whether the cached matrix is still
	current, so a search costs a hash lookup plus the dot product instead of
	rebuilding thousands of rows.
	"""
	import numpy as np

	fingerprint = _matrix_fingerprint()
	cached_vectors = _MATRIX.get("vectors")
	if _MATRIX.get("fingerprint") == fingerprint and cached_vectors is not None:
		return _MATRIX["ids"], cached_vectors
	with _MATRIX_LOCK:
		if _MATRIX.get("fingerprint") == fingerprint and _MATRIX.get("vectors") is not None:
			return _MATRIX["ids"], _MATRIX["vectors"]
		ids: List[int] = []
		rows: List[List[float]] = []
		for title_id, vector in TitleEmbedding.objects.filter(
			model_name=embeddings.MODEL_NAME
		).values_list("title_id", "vector"):
			raw = bytes(vector or b"")
			if not raw or len(raw) % 4:
				continue
			ids.append(title_id)
			rows.append(np.frombuffer(raw, dtype=np.float32).tolist())
		width = {len(row) for row in rows}
		if len(width) > 1:
			# A half-finished re-index (or a model switch): keep only the widest,
			# most common shape so the matrix stays rectangular.
			expected = max(width, key=lambda size: sum(1 for row in rows if len(row) == size))
			keep = [index for index, row in enumerate(rows) if len(row) == expected]
			ids = [ids[index] for index in keep]
			rows = [rows[index] for index in keep]
		matrix = (
			np.asarray(rows, dtype=np.float32) if rows else np.zeros((0, 0), dtype=np.float32)
		)
		_MATRIX["fingerprint"] = fingerprint
		_MATRIX["ids"] = ids
		_MATRIX["vectors"] = matrix
		logger.debug("AI index loaded: %s titles", len(ids))
		return ids, matrix


def invalidate_cache() -> None:
	"""Force the next search to reload the matrix (tests, manual re-index)."""
	_MATRIX["fingerprint"] = None
	_MATRIX["vectors"] = None
	_MATRIX["ids"] = []


def search_outcome(
	query: str,
	*,
	limit: Optional[int] = None,
	media_type: str = "",
	threshold: Optional[float] = None,
) -> "SearchOutcome":
	"""Rank the catalogue against ``query``: the best ``limit`` hits + the total.

	Vectors are L2 normalised in both directions, so the cosine similarity is a
	plain dot product. Results below ``threshold`` are dropped: a request the
	catalogue cannot answer ("bugungi ob-havo qanday") should come back empty
	instead of with five unrelated titles.

	``total`` counts *every* title above the threshold, not just the ones that
	fit in the answer: the user asked for all matching content, and a client that
	shows the strongest few can then say honestly how many more there are (and
	ask for them with a larger ``limit``).
	"""
	import numpy as np

	text = clean_text(query)
	if not text:
		return SearchOutcome(hits=[], total=0)
	wanted = max(1, int(limit or top_k()))
	cut_off = min_score() if threshold is None else float(threshold)
	ids, matrix = _load_matrix()
	if not ids:
		return SearchOutcome(hits=[], total=0)
	query_vector = np.asarray(embeddings.encode_texts([text])[0], dtype=np.float32)
	if query_vector.shape[0] != matrix.shape[1]:
		# The index was built by another model version: rebuild it instead of
		# raising, and answer from the (empty) index.
		logger.warning(
			"AI index dimension mismatch (index=%s, query=%s); a re-index is required.",
			matrix.shape[1],
			query_vector.shape[0],
		)
		return SearchOutcome(hits=[], total=0)
	scores = matrix @ query_vector
	matching = scores >= cut_off
	if media_type:
		# The type filter is applied to the vectors, not after the limit: a
		# "only manga" request must count and return manga hits, however many
		# anime sit above them.
		allowed = MediaTitle.objects.filter(type=media_type).values_list("pk", flat=True)
		matching &= np.isin(np.asarray(ids), list(allowed))
	matched = np.nonzero(matching)[0]
	total = int(matched.size)
	if total == 0:
		return SearchOutcome(hits=[], total=0)
	# Exact ranking of the matches (no approximate index): a few thousand floats
	# sort in well under a millisecond.
	best = matched[np.argsort(-scores[matched])][:wanted]
	candidates = [(ids[int(index)], float(scores[int(index)])) for index in best]
	titles = MediaTitle.objects.prefetch_related("genres").in_bulk(
		[title_id for title_id, _ in candidates]
	)
	hits = [
		SearchHit(title=titles[title_id], score=score)
		for title_id, score in candidates
		if title_id in titles
	]
	return SearchOutcome(hits=hits, total=total)


def search(
	query: str,
	*,
	limit: Optional[int] = None,
	media_type: str = "",
	threshold: Optional[float] = None,
) -> List[SearchHit]:
	"""The ranked hits alone (see :func:`search_outcome`)."""
	return search_outcome(
		query, limit=limit, media_type=media_type, threshold=threshold
	).hits


def user_can_search(user) -> bool:
	"""AI search is a paid feature: an active subscription is required.

	Deliberately the same rule the rest of the site uses — ``is_active`` means a
	plan that is paid *and* not expired — so an expired subscriber loses the AI
	search with their other paid access.
	"""
	if user is None or not getattr(user, "is_authenticated", False):
		return False
	subscription = getattr(user, "subscription", None)
	return bool(subscription is not None and subscription.is_active)
