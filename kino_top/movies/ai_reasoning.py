"""The reasoning step of the AI search: route the request, explain the picks.

The vector search (:mod:`movies.ai_search`) is good at *finding* titles by
meaning and blind at everything else: it cannot say **why** a title fits, it
cannot tell a request for "qo'rqinchli animelar" from "qo'rqinchli seriallar"
beyond cosine scores, and it has no way to answer "bunday kino bormi?" in words.

So a request is answered in steps, and the expensive one — handing the model the
catalogue — runs only when it is actually needed:

1. **Routing** — the user's own words are sent to the model *without* any
   candidates (a tiny prompt). It answers ``qidiruv`` (the user wants content,
   with an optional cleaned-up search text) or ``suhbat`` (a greeting, "who are
   you", anything that is not a catalogue lookup, answered right there). A
   conversation therefore never pays for the candidate list.
2. **Retrieval** — for a ``qidiruv`` the multilingual encoder ranks the
   catalogue (and is handed the model's cleaned-up query when it gave one).
3. **Reasoning** — the retrieved candidates are sent to the model with the
   request, which re-orders them, drops the ones that do not fit, and writes a
   short Uzbek answer plus its reasoning.

Every model step is strictly an improvement, never a dependency: with no API
key, a quota error or a timeout the callers keep the vector-only answer (see
:func:`route_with_fallback`, :func:`reason_with_fallback` and the ``used_llm``
flag every result carries).

Candidates are passed as short lines, and the model may only pick from them, so
it can never invent a title that is not in the catalogue.
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from . import ai_search, llm
from .ai_search import SearchHit, one_line_summary

logger = logging.getLogger(__name__)

# How many candidates the model may choose from. Large enough to cover a
# "show me everything like this" request, small enough that the prompt stays
# cheap and inside every provider's context window.
MAX_CANDIDATES = 20
# Reasoning + answer for one request: short on purpose, both for latency and
# because a wall of text in a Telegram message is unreadable.
MAX_ANSWER_TOKENS = 900
# The routing call returns one short JSON object (or a 2-4 sentence chat reply),
# so its budget is smaller than a full search answer's.
MAX_ROUTE_TOKENS = 700
# An identical request inside this window reuses the previous explanation
# instead of paying for it again (the bot's "yana so'rash" and a page refresh
# are the common repeats). Small and time-boxed, so a catalogue edit shows up.
CACHE_TTL_SECONDS = 120
CACHE_MAX_ENTRIES = 128

# What the router decided the user wants.
ACTION_SEARCH = "qidiruv"
ACTION_CHAT = "suhbat"

# Step 1: classify the request *without* sending any candidates, so a
# conversation costs a fraction of a search. The model may also clean the query
# up for the encoder, which is what "unga kerak bo'lgan ro'yxat" hangs on.
ROUTER_SYSTEM_PROMPT = (
	"Sen AniVoy — AniChopar platformasidagi aqlli yordamchisan. Katalog "
	"anime, serial, kino va mangadan iborat. O'zingni bot deb atamaysan: "
	"senga «bot ekansanmi?» desalar, qat'iy va qisqa javob ber — «Yo'q, bot "
	"emasman. AniVoyman, shu platformada ishlayman. Ish yuzasidan savolingiz "
	"bormi?»\n\n"
	"Foydalanuvchi so'rovini ikki turdan biriga ajrat:\n"
	"1. «qidiruv» — foydalanuvchi kontent izlaydi: janr, kayfiyat, tur, mavzu, "
	"yil yoki nom (masalan «sarguzasht va qo'rqinchli», «romantika», «Naruto»).\n"
	"2. «suhbat» — salomlashish, «sen kimsan», «nima qila olasan», «bot "
	"ekansanmi», yordam, minnatdorchilik yoki katalogga aloqasi yo'q savol.\n\n"
	"«qidiruv» bo'lsa: «qidiruv» maydoniga qidirish uchun qisqa matn yoz, "
	"«javob» bo'sh qolsin.\n"
	"«suhbat» bo'lsa: «javob» maydoniga o'zbekcha 2-4 jumla javob yoz, "
	"«qidiruv» bo'sh qolsin. Ohang qat'iy, ishonchli va qisqa bo'lsin — "
	"keraksiz uzr va poyeshchilik yo'q.\n\n"
	"Foydalanuvchi shaxsiy ma'lumotlari (sevimlilari, oxirgi ko'rganlari) "
	"berilsa, «men oxirgi ko'rganimga o'xshashini ayt», «sevimlim mosini "
	"top» kabi so'rovlar ham «qidiruv»: qidiruv maydoniga o'sha asar "
	"nom(lar)i va unga mos hususiyatlarni yoz.\n\n"
	"Faqat JSON qaytarasan, boshqa matn yozmaysan:\n"
	'{"harakat": "qidiruv" yoki "suhbat", "qidiruv": "", "javob": ""}'
)

# Step 3: the candidates are known to be relevant; the model only ranks and
# explains them. Smaller than the router prompt because the classification
# instructions are no longer needed.
SYSTEM_PROMPT = (
	"Sen AniVoy — AniChopar platformasining katalog yordamchisisan. Katalog "
	"anime, serial, kino va mangadan iborat. Senga semantik qidiruv topgan "
	"nomzodlar ro'yxati beriladi. O'zingni bot deb atamaysan.\n\n"
	"Vazifang: foydalanuvchi so'roviga eng mos nomzodlarni tanlash.\n"
	"Qoidalar:\n"
	"* Faqat ro'yxatdagi raqamlarni tanlaysan — yangi nom o'ylab topmaysan.\n"
	"* Mos kelmaydiganlarini tanlovga qo'shmaysan; hech narsa mos kelmasa, "
	"tanlov bo'sh bo'ladi va buni javobda aytasan.\n"
	"* Janr, yil, tur yoki qism soni haqida faqat ro'yxatda yozilganini aytasan.\n"
	"* Foydalanuvchi shaxsiy ma'lumotlari (sevimlilari, oxirgi ko'rganlari) "
	"berilsa, javobni shunga moslab yoz: «o'xshashini ayt» so'rovida nomzodlarni "
	"shu asarlarga qarab tanla va qaysi biriga o'xshashligini sababi bilan ayt.\n"
	"* O'zbek tilida, 2-4 jumla yozasan. Ohang qat'iy va ishonchli: qisqa "
	"javob ber, keraksiz uzr yoki poyeshchilik qo'shma. «fikrlash» — 1-3 "
	"qisqa qadam.\n\n"
	"Faqat JSON qaytarasan, boshqa matn yozmaysan:\n"
	'{"fikrlash": "...", "tanlov": [1, 4, 2], "javob": "..."}'
)


@dataclass(frozen=True)
class Answer:
	"""A complete answer: the ranked titles plus what the model said about them."""

	query: str
	hits: List[SearchHit]
	total: int
	answer: str = ""
	thinking: str = ""
	used_llm: bool = False
	error: str = ""
	# True when the model treated the request as a conversation (a greeting,
	# "who are you", a question about the assistant) rather than a catalogue
	# lookup: ``answer`` holds the reply and ``hits`` is empty on purpose, so a
	# client shows only the words and no result list.
	conversational: bool = False

	@property
	def has_more(self) -> bool:
		return self.total > len(self.hits)


@dataclass(frozen=True)
class ReasoningResult:
	"""What the model added to a search (or that it could not add anything)."""

	answer: str = ""
	thinking: str = ""
	ordered_ids: Tuple[int, ...] = ()
	used_llm: bool = False
	error: str = ""

	@property
	def has_answer(self) -> bool:
		return bool(self.answer.strip())


@dataclass(frozen=True)
class Route:
	"""What the model decided the request is, before any retrieval happens.

	``action`` is :data:`ACTION_SEARCH` or :data:`ACTION_CHAT`. A chat carries
	its ``answer`` right here (and needs no catalogue and no candidate list); a
	search carries an optional cleaned-up ``search_query`` for the encoder.
	``used_llm`` is False when the model could not be reached at all, which the
	caller reports by falling back to the vectors.
	"""

	action: str = ACTION_SEARCH
	search_query: str = ""
	answer: str = ""
	thinking: str = ""
	used_llm: bool = False
	error: str = ""

	@property
	def is_chat(self) -> bool:
		return self.used_llm and self.action == ACTION_CHAT


def candidate_lines(hits: Sequence[SearchHit], *, limit: int = MAX_CANDIDATES) -> List[str]:
	"""One short line per candidate: the model reads these, not the documents."""
	lines: List[str] = []
	for index, hit in enumerate(list(hits)[:limit], start=1):
		title = hit.title
		genres = ", ".join(genre.name for genre in title.genres.all()[:4]) or "—"
		parts = [
			f"Nomi: {title.title}",
			f"Turi: {title.get_type_display()}",
			f"Janrlar: {genres}",
			f"Yil: {title.release_year or '—'}",
			f"Holat: {title.get_status_display()}",
		]
		synopsis = one_line_summary(title)
		lines.append(
			f"{index}. " + " | ".join(parts) + f" | Mazmun: {synopsis}"
			+ f" | Moslik: {round(float(hit.score) * 100)}%"
		)
	return lines


def build_prompt(
	query: str,
	hits: Sequence[SearchHit],
	*,
	media_type: str = "",
	context: str = "",
) -> str:
	"""The user message: the request, then the numbered candidates."""
	lines = [f"Foydalanuvchi so'rovi: {query.strip()}"]
	if media_type:
		lines.append(f"Faqat shu tur ko'rsatilishi mumkin: {media_type}")
	if context.strip():
		lines.append("")
		lines.append("Foydalanuvchi shaxsiy ma'lumotlari:")
		lines.append(context.strip())
	lines.append("")
	lines.append("Qidiruv topgan nomzodlar:")
	lines.extend(candidate_lines(hits))
	lines.append("")
	lines.append(
		"Yuqoridagi nomzodlardan eng mos keladiganlarini tanlab, JSON qaytar."
	)
	return "\n".join(lines)


def parse_picks(raw: Any, hits: Sequence[SearchHit]) -> Tuple[int, ...]:
	"""Turn the model's 1-based picks into title ids, in its order.

	Unknown, repeated or out-of-range numbers are ignored: a hallucinated index
	is a bug in the answer, not a reason to drop the whole explanation.
	"""
	candidates = list(hits)[:MAX_CANDIDATES]
	picked: List[int] = []
	for value in _as_list(raw):
		try:
			position = int(value)
		except (TypeError, ValueError):
			continue
		if 1 <= position <= len(candidates):
			title_id = candidates[position - 1].title.pk
			if title_id not in picked:
				picked.append(title_id)
	return tuple(picked)


def _as_list(raw: Any) -> List[Any]:
	if raw is None:
		return []
	if isinstance(raw, (list, tuple)):
		return list(raw)
	if isinstance(raw, str):
		# "1, 3" or "1 3" — models slip into plain text often enough.
		cleaned = raw.replace(",", " ").replace(";", " ")
		return [chunk for chunk in cleaned.split() if chunk.strip()]
	return [raw]


_CACHE: Dict[Tuple[Any, ...], Tuple[float, Any]] = {}
_CACHE_LOCK = threading.Lock()


def _cache_key(
	query: str, hits: Sequence[SearchHit], media_type: str, context: str = ""
) -> Tuple[Any, ...]:
	state = (
		(query or "").strip().lower(),
		media_type,
		# The same question asked with a different user's favourites is a
		# different question: the context must split the entry.
		(context or "").strip(),
		# The chain, not one provider: the same question answered by a different
		# model must not reuse the other's explanation.
		llm.chain_signature(),
		tuple(hit.title.pk for hit in hits),
		# The ranking itself matters: same ids in a different order is a
		# different question for the model.
		tuple(round(float(hit.score), 3) for hit in hits),
	)
	return state


def _route_cache_key(query: str, media_type: str, context: str = "") -> Tuple[Any, ...]:
	# The "route:" prefix keeps routing decisions from colliding with the
	# explanation entries in the one cache (they share the TTL and eviction).
	return (
		"route",
		(query or "").strip().lower(),
		media_type,
		(context or "").strip(),
		llm.chain_signature(),
	)


def _cache_get(key: Tuple[Any, ...]) -> Optional[Any]:
	now = time.monotonic()
	with _CACHE_LOCK:
		entry = _CACHE.get(key)
		if entry is None:
			return None
		stored_at, result = entry
		if now - stored_at > CACHE_TTL_SECONDS:
			_CACHE.pop(key, None)
			return None
		return result


def _cache_put(key: Tuple[Any, ...], result: Any) -> None:
	with _CACHE_LOCK:
		if len(_CACHE) >= CACHE_MAX_ENTRIES:
			# Cheap eviction: drop the oldest half instead of tracking access
			# order for a cache this small and this short-lived.
			oldest = sorted(_CACHE.items(), key=lambda item: item[1][0])
			for stale_key, _ in oldest[: max(1, CACHE_MAX_ENTRIES // 2)]:
				_CACHE.pop(stale_key, None)
		_CACHE[key] = (time.monotonic(), result)


def clear_cache() -> None:
	"""Drop every cached route and explanation (tests, or a catalogue change)."""
	with _CACHE_LOCK:
		_CACHE.clear()


def _normalize_action(raw: Any, payload: Dict[str, Any]) -> str:
	"""The router's decision as one of the two actions.

	Missing or unknown values fall back on the shape of the answer: a legacy
	payload that carries ``tanlov`` is a search, a bare ``javob`` is a chat,
	and anything else is treated as a search (the safer default — it still ends
	up either with picks or with the "nothing fits" path).
	"""
	text = str(raw or "").strip().lower()
	if text in {ACTION_SEARCH, "qidirish", "qidir", "search"}:
		return ACTION_SEARCH
	if text in {ACTION_CHAT, "suhbet", "chat", "gaplash", "conversation"}:
		return ACTION_CHAT
	if "tanlov" in payload:
		return ACTION_SEARCH
	if str(payload.get("javob") or "").strip():
		return ACTION_CHAT
	return ACTION_SEARCH


def route(query: str, *, media_type: str = "", context: str = "") -> Route:
	"""Ask the model which kind of request this is — with no candidates sent."""
	key = _route_cache_key(query, media_type, context)
	cached = _cache_get(key)
	if cached is not None:
		return cached

	user_message = f"Foydalanuvchi: {query.strip()}"
	if context.strip():
		user_message += (
			"\n\nFoydalanuvchi shaxsiy ma'lumotlari:\n" + context.strip()
		)
	raw = llm.chat(
		[
			{"role": "system", "content": ROUTER_SYSTEM_PROMPT},
			{"role": "user", "content": user_message},
		],
		max_tokens=MAX_ROUTE_TOKENS,
	)
	try:
		payload = llm.parse_json_object(raw)
	except llm.LLMUnavailable:
		# The model answered, just not as JSON. Treat it as a search with the
		# user's own words rather than as a failure: the vector search still
		# answers, and a chat is the router's job to get right.
		payload = {}

	action = _normalize_action(payload.get("harakat"), payload)
	if action == ACTION_CHAT:
		result = Route(
			action=ACTION_CHAT,
			answer=str(payload.get("javob") or "").strip(),
			thinking=str(payload.get("fikrlash") or "").strip(),
			used_llm=True,
		)
	else:
		result = Route(
			action=ACTION_SEARCH,
			search_query=str(payload.get("qidiruv") or "").strip() or query.strip(),
			used_llm=True,
		)
	_cache_put(key, result)
	return result


def route_with_fallback(
	query: str, *, media_type: str = "", context: str = ""
) -> Route:
	"""Like :func:`route`, but a failure is reported instead of raised.

	No configured provider is not reported as an error here (the caller checks
	:func:`movies.llm.is_configured` itself and keeps the old vector path); a
	provider that could not answer comes back with ``used_llm=False`` and the
	reason in ``error``.
	"""
	try:
		return route(query, media_type=media_type, context=context)
	except llm.LLMUnavailable as exc:
		logger.info("AI routing skipped: %s", exc)
		return Route(error=str(exc))
	except Exception as exc:  # noqa: BLE001 - the search must still answer
		logger.exception("AI routing failed")
		return Route(error=str(exc))


def reason(
	query: str,
	hits: Sequence[SearchHit],
	*,
	media_type: str = "",
	context: str = "",
) -> ReasoningResult:
	"""Ask the model about the candidates. Raises :class:`llm.LLMUnavailable`."""
	if not hits:
		return ReasoningResult()
	key = _cache_key(query, hits, media_type, context)
	cached = _cache_get(key)
	if cached is not None:
		return cached

	raw = llm.chat(
		[
			{"role": "system", "content": SYSTEM_PROMPT},
			{
				"role": "user",
				"content": build_prompt(
					query, hits, media_type=media_type, context=context
				),
			},
		],
		max_tokens=MAX_ANSWER_TOKENS,
	)
	payload = llm.parse_json_object(raw)
	result = ReasoningResult(
		answer=str(payload.get("javob") or "").strip(),
		thinking=str(payload.get("fikrlash") or "").strip(),
		ordered_ids=parse_picks(payload.get("tanlov"), hits),
		used_llm=True,
	)
	_cache_put(key, result)
	return result


def reason_with_fallback(
	query: str,
	hits: Sequence[SearchHit],
	*,
	media_type: str = "",
	context: str = "",
) -> ReasoningResult:
	"""Like :func:`reason`, but a failure is reported instead of raised.

	The search must answer even when the reasoning model is down, so every
	problem ends up in ``result.error`` with ``used_llm=False`` and the caller
	keeps the vector ranking.
	"""
	try:
		return reason(query, hits, media_type=media_type, context=context)
	except llm.LLMUnavailable as exc:
		logger.info("AI reasoning skipped: %s", exc)
		return ReasoningResult(error=str(exc))
	except Exception as exc:  # noqa: BLE001 - the answer must still be rendered
		logger.exception("AI reasoning failed")
		return ReasoningResult(error=str(exc))


def order_hits(hits: Sequence[SearchHit], ordered_ids: Iterable[int]) -> List[SearchHit]:
	"""Vector hits re-ordered by the model's picks (the rest keeps its rank)."""
	items = list(hits)
	picked = list(ordered_ids)
	by_id = {hit.title.pk: hit for hit in items}
	ordered = [by_id[title_id] for title_id in picked if title_id in by_id]
	return ordered + [hit for hit in items if hit.title.pk not in set(picked)]


def answer_search(
	query: str,
	*,
	limit: Optional[int] = None,
	media_type: str = "",
	threshold: Optional[float] = None,
	context: str = "",
) -> "Answer":
	"""Route, retrieve, then reason: the one entry point both clients use.

	With a model configured the request is first *routed* on its own (no
	candidates, a tiny prompt): a conversation is answered right there and never
	pays for the catalogue, while a search goes on to retrieval and reasoning.
	Retrieval otherwise always runs, and a reasoning failure leaves the vector
	ranking untouched (``used_llm`` tells the client whether prose exists).

	When the model runs but selects no candidate, the request was not a
	catalogue lookup or nothing in the candidates fit: the vector hits are not
	an answer, so they are withheld and only the model's words are shown —
	``conversational`` marks that case.

	``context`` is an optional short block about the user (favourites, last
	watched) that is appended to both model calls, so "something like the last
	one I watched" has a chance of meaning something.
	"""
	route_result: Optional[Route] = None
	if llm.is_configured():
		route_result = route_with_fallback(
			query, media_type=media_type, context=context
		)
		if route_result.is_chat:
			return Answer(
				query=query,
				hits=[],
				total=0,
				answer=route_result.answer,
				thinking=route_result.thinking,
				used_llm=True,
				conversational=True,
			)
		if not route_result.used_llm:
			# The model could not be reached at all: answer from the vectors
			# alone, exactly as if no provider were configured, and keep its
			# error so the client/management command can explain the outage.
			outcome = ai_search.search_outcome(
				query, limit=limit, media_type=media_type, threshold=threshold
			)
			return Answer(
				query=query,
				hits=list(outcome.hits),
				total=outcome.total,
				error=route_result.error,
			)

	# The model may have cleaned the query up for the encoder ("unga kerak
	# bo'lgan ro'yxat"): search with its words when it gave any.
	search_text = (route_result.search_query if route_result else "") or query
	outcome = ai_search.search_outcome(
		search_text, limit=limit, media_type=media_type, threshold=threshold
	)
	if not outcome.hits:
		return Answer(
			query=query,
			hits=[],
			total=outcome.total,
			error=route_result.error if route_result else "",
		)
	reasoning = reason_with_fallback(
		search_text, outcome.hits, media_type=media_type, context=context
	)
	conversational = reasoning.used_llm and not reasoning.ordered_ids
	return Answer(
		query=query,
		hits=[] if conversational else order_hits(outcome.hits, reasoning.ordered_ids),
		total=0 if conversational else outcome.total,
		answer=reasoning.answer,
		thinking=reasoning.thinking,
		used_llm=reasoning.used_llm,
		error=reasoning.error,
		conversational=conversational,
	)


