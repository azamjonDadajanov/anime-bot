"""``python manage.py import_kawaii`` — import the kawaii.uz anime catalog.

bot.kawaii.uz is a React/Next.js front end. Two rules shape this command:

* Its search endpoint (``/api/v1/search/?q=...``) only accepts a query of **at
  least three characters** — anything shorter returns a generic default list —
  and it has no pagination, so one call returns *every* match. We therefore
  query it with real anime names (the bundled list, or ``--names-file``/``-q``).
* The detail page must be loaded as HTML. It is server-rendered, so a plain
  GET of ``/anime/<hash_id>`` already contains the full
  ``<script type="application/ld+json">`` block with the real metadata. That is
  why no headless browser is needed: we fetch the page HTML and read the
  embedded JSON-LD.

The command is resumable and **never re-imports** a title that is already in
the database. A row is considered imported when either its ``slug`` equals the
kawaii ``hash_id`` (the normal path) **or** the same ``title`` + ``type``
already exists (covers rows created earlier by the bot/admin with a different
slug). ``--limit`` caps how many titles a single run stores (default 10, hard
maximum 10).

Each run is paced so it takes **at least ~10 seconds** of wall time (network
requests are spread out with ``--delay`` and, if the work finished too quickly,
the remainder is slept at the end) — this keeps the importer from looking like
a burst attack against bot.kawaii.uz. Re-run the command until it reports that
nothing new is left.

Posters are downloaded and stored as media files under ``MEDIA_ROOT/covers/``
(``MediaTitle.cover``), so nginx serves them and the API only ships URLs.

Examples::

    python manage.py import_kawaii                 # store the next 10 titles
    python manage.py import_kawaii --limit 3       # store only 3 this run
    python manage.py import_kawaii -q Bleach -q Naruto
    python manage.py import_kawaii --limit 1 --dry-run   # fetch + parse only
"""

from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

import httpx
from django.core.management.base import BaseCommand, CommandError

from movies.covers import content_file as new_cover_file
from movies.models import Genre, MediaTitle

DEFAULT_BASE_URL = "https://bot.kawaii.uz"
SEARCH_ENDPOINT = "/api/v1/search/"
ANIME_PATH = "/anime/{hash_id}"
DEFAULT_NAMES_FILE = Path(__file__).resolve().parents[2] / "data" / "kawaii_anime_names.txt"

# The site caps a useful search at three characters; the importer is meant to be
# re-run in small batches, so a single run never stores more than this.
MAX_LIMIT = 10
DEFAULT_LIMIT = 10
# Minimum wall-clock seconds per run so a batch does not look like a burst.
MIN_RUN_SECONDS = 10.0
DEFAULT_DELAY = 1.0

USER_AGENT = (
	"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
	"(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)

LD_JSON_RE = re.compile(r'<script type="application/ld\+json">(.*?)</script>', re.S)
START_LINK_RE = re.compile(r"\?start=([A-Za-z])-([A-Za-z0-9]+)")
MENU_ITEM_RE = re.compile(r"\[(.+?)\]")
TRAILING_URL_RE = re.compile(r"\s*\(https?://[^)]*\)\s*$")
IMAGE_TYPES = {".webp": "image/webp", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png"}

LD_TYPE_TO_MEDIA = {"TVSeries": "series", "TVShow": "series", "Movie": "movie"}
START_LETTER_TO_MEDIA = {"a": "anime", "m": "movie", "s": "series"}


# --------------------------------------------------------------------- parsing
def parse_names(text: str) -> List[str]:
	"""Extract anime names from a Telegram menu dump or a plain one-per-line list.

	The menu format looks like ``12. [Naruto (https://t.me/...)]``; a stray URL
	after the closing bracket (``[Title] (https://...)``) is handled too. Names
	are de-duplicated case-insensitively while keeping their order.
	"""
	names: List[str] = []
	seen = set()
	for line in (text or "").splitlines():
		match = MENU_ITEM_RE.search(line)
		if match:
			candidate = TRAILING_URL_RE.sub("", match.group(1)).strip()
		else:
			stripped = line.strip()
			if not stripped or stripped[0] in "📌⚠️•#":
				continue
			candidate = stripped
		if not candidate:
			continue
		key = candidate.casefold()
		if key in seen:
			continue
		seen.add(key)
		names.append(candidate)
	return names


def extract_ld_graphs(html: str) -> List[Any]:
	"""Parse every ``application/ld+json`` block embedded in the page HTML."""
	graphs: List[Any] = []
	for block in LD_JSON_RE.findall(html or ""):
		try:
			graphs.append(json.loads(block))
		except (TypeError, ValueError):
			continue
	return graphs


def _nodes_of(graph: Any) -> List[Dict[str, Any]]:
	if not isinstance(graph, dict):
		return []
	nodes = graph.get("@graph")
	if isinstance(nodes, list):
		return [node for node in nodes if isinstance(node, dict)]
	return [graph]


def find_catalog_node(graphs: List[Any]) -> Optional[Dict[str, Any]]:
	"""Return the schema.org node describing the anime itself.

	The page exposes a ``TVSeries``/``Movie`` node whose ``@id`` ends with
	``#anime``; prefer it, then fall back to any recognised media type.
	"""
	fallback: Optional[Dict[str, Any]] = None
	for graph in graphs:
		for node in _nodes_of(graph):
			if str(node.get("@id") or "").endswith("#anime"):
				return node
			if fallback is None and node.get("@type") in LD_TYPE_TO_MEDIA:
				fallback = node
	return fallback


def map_media_type(type_uzb: Any, ld_type: Any, start_letter: Any) -> str:
	"""Map the site's type labels onto ``MediaTitle.MediaType`` values."""
	text = str(type_uzb or "").casefold()
	if "manga" in text:
		return MediaTitle.MediaType.MANGA
	if any(word in text for word in ("film", "kino", "movie")):
		return MediaTitle.MediaType.MOVIE
	if "serial" in text or "tv" in text:
		return MediaTitle.MediaType.SERIES
	if ld_type in LD_TYPE_TO_MEDIA:
		return LD_TYPE_TO_MEDIA[ld_type]
	if isinstance(start_letter, str) and start_letter in START_LETTER_TO_MEDIA:
		return START_LETTER_TO_MEDIA[start_letter]
	return MediaTitle.MediaType.ANIME


def derive_status(production_status: Any, episodes: Any, source_episodes: Any) -> str:
	"""Infer the catalog status from the schema.org status and episode counts."""
	value = str(production_status or "").casefold()
	if "completed" in value:
		return MediaTitle.Status.COMPLETED
	if "active" in value or "ongoing" in value:
		return MediaTitle.Status.ONGOING
	if "potential" in value:
		return MediaTitle.Status.UPCOMING
	if isinstance(episodes, int):
		if episodes == 0:
			return MediaTitle.Status.UPCOMING
		if isinstance(source_episodes, int) and source_episodes and episodes >= source_episodes:
			return MediaTitle.Status.COMPLETED
	return MediaTitle.Status.ONGOING


def normalize_rating(value: Any) -> Optional[int]:
	try:
		number = float(value)
	except (TypeError, ValueError):
		return None
	return max(1, min(10, int(round(number))))


def _first_text(*values: Any) -> str:
	for value in values:
		if value is None:
			continue
		text = str(value).strip()
		if text:
			return text
	return ""


def _as_int(value: Any) -> Optional[int]:
	"""Pull the first integer out of a value such as ``"2023"`` or ``2023``."""
	if isinstance(value, bool):
		return None
	if isinstance(value, int):
		return value
	match = re.search(r"\d+", str(value or ""))
	return int(match.group(0)) if match else None


def guess_image_type(url: str) -> str:
	suffix = Path(str(url).split("?")[0]).suffix.casefold()
	return IMAGE_TYPES.get(suffix, "image/jpeg")


def build_metadata(
	hash_id: str,
	search_item: Dict[str, Any],
	node: Optional[Dict[str, Any]],
	html: str,
) -> Dict[str, Any]:
	"""Merge the search hit and the page's JSON-LD into one import payload."""
	search_item = search_item or {}
	node = node or {}

	title = _first_text(search_item.get("title_uzb"), node.get("name")) or hash_id
	original = _first_text(search_item.get("title_org"))
	synopsis = str(node.get("description") or "").strip()
	if original:
		synopsis = f"Asl nomi: {original}\n\n{synopsis}".strip()

	genres = [
		genre.strip()
		for genre in (node.get("genre") or [])
		if isinstance(genre, str) and genre.strip()
	]
	year = _as_int(search_item.get("year")) or _as_int(node.get("datePublished"))

	episodes = search_item.get("episode_kawaii")
	if episodes is None:
		episodes = _as_int(node.get("numberOfEpisodes"))
	source_episodes = search_item.get("episode_source")

	rating_node = node.get("aggregateRating")
	rating = normalize_rating(rating_node.get("ratingValue") if isinstance(rating_node, dict) else None)

	start_match = START_LINK_RE.search(html or "")
	start_letter = start_match.group(1).lower() if start_match else ""

	poster = _first_text(search_item.get("poster"), node.get("image"))

	return {
		"hash_id": hash_id,
		"title": title[:200],
		"synopsis": synopsis,
		"genres": genres[:12],
		"year": year,
		"episodes": episodes,
		"rating": rating,
		"status": derive_status(node.get("productionStatus"), episodes, source_episodes),
		"type": map_media_type(search_item.get("type_uzb"), node.get("@type"), start_letter),
		"poster": poster,
	}


# --------------------------------------------------------------------- command
class Command(BaseCommand):
	help = (
		"Search bot.kawaii.uz by anime names, load each anime page as HTML and "
		"store the parsed catalog (MediaTitle + genres + poster) in the database. "
		"Resumable: re-runs import the next titles that are not stored yet."
	)

	def add_arguments(self, parser) -> None:
		parser.add_argument("names", nargs="*", help="Anime names to search for.")
		parser.add_argument(
			"-q",
			"--query",
			dest="queries",
			action="append",
			default=[],
			help="Anime name to search for (repeatable).",
		)
		parser.add_argument(
			"--names-file",
			default=str(DEFAULT_NAMES_FILE),
			help="Text file with names (Telegram menu dump or one name per line).",
		)
		parser.add_argument(
			"--no-names-file",
			action="store_true",
			help="Ignore --names-file and only use names given on the command line.",
		)
		parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help="Site base URL.")
		parser.add_argument(
			"--limit",
			type=int,
			default=DEFAULT_LIMIT,
			help=f"Titles to store in this run (default {DEFAULT_LIMIT}, maximum {MAX_LIMIT}).",
		)
		parser.add_argument(
			"--delay",
			type=float,
			default=DEFAULT_DELAY,
			help=f"Seconds to sleep between requests (default {DEFAULT_DELAY}).",
		)
		parser.add_argument(
			"--min-run-seconds",
			type=float,
			default=MIN_RUN_SECONDS,
			help=f"Pad each run to at least this many seconds (default {MIN_RUN_SECONDS}).",
		)
		parser.add_argument("--timeout", type=float, default=25.0, help="Per-request timeout in seconds.")
		parser.add_argument("--min-length", type=int, default=3, help="Skip shorter search terms (API minimum).")
		parser.add_argument("--no-covers", action="store_true", help="Do not download/store poster images.")
		parser.add_argument("--dry-run", action="store_true", help="Fetch and parse, but write nothing.")

	def handle(self, *args, **options) -> None:
		started = time.monotonic()
		names = self._collect_names(options)
		if not names:
			raise CommandError("No anime names to search for. Pass names, -q or --names-file.")

		limit = self._resolve_limit(options)
		self.stdout.write(
			self.style.MIGRATE_HEADING(
				f"{len(names)} name(s) · limit {limit} · covers "
				f"{'off' if options['no_covers'] else 'on'} · {options['base_url']}"
			)
		)

		client = httpx.Client(
			base_url=options["base_url"].rstrip("/"),
			headers={"User-Agent": USER_AGENT, "Accept": "application/json, text/html;q=0.9, */*;q=0.8"},
			timeout=options["timeout"],
			follow_redirects=True,
		)
		try:
			stats = self._run(client, names, options, limit)
		except KeyboardInterrupt:  # pragma: no cover - operator convenience
			self.stdout.write(self.style.WARNING("\nInterrupted; stored rows were kept."))
			return
		finally:
			client.close()

		elapsed = time.monotonic() - started
		min_run = float(options.get("min_run_seconds") or 0)
		if min_run > 0 and elapsed < min_run and not options["dry_run"]:
			pad = min_run - elapsed
			self.stdout.write(f"Pacing: sleeping {pad:.1f}s so the run takes >= {min_run:.0f}s.")
			time.sleep(pad)
			elapsed = time.monotonic() - started

		self.stdout.write(f"Elapsed: {elapsed:.1f}s")

		if stats["stored"] == 0 and stats["skipped"] == 0:
			self.stdout.write(
				self.style.WARNING(
					f"Hech nima qilinmadi: bazada mavjud bo'lmagan yangi anime topilmadi "
					f"({stats['failed']} xato)."
				)
			)
			return
		if stats["stored"] == 0:
			self.stdout.write(
				self.style.SUCCESS(
					f"Hammasi allaqachon bazada: skipped={stats['skipped']} failed={stats['failed']}."
				)
			)
			return
		self.stdout.write(
			self.style.SUCCESS(
				f"Done. created={stats['created']} updated={stats['updated']} "
				f"skipped={stats['skipped']} failed={stats['failed']} · {stats['stored']}/{limit} this run"
			)
		)

	# ------------------------------------------------------------------ helpers
	def _resolve_limit(self, options) -> int:
		"""Clamp ``--limit`` into ``[1, MAX_LIMIT]`` (the site is queried in batches)."""
		try:
			value = int(options["limit"])
		except (TypeError, ValueError):
			value = DEFAULT_LIMIT
		return min(max(value, 1), MAX_LIMIT)

	def _collect_names(self, options) -> List[str]:
		"""Combine CLI names with the names file, de-duplicated and filtered."""
		names = list(options["queries"] or []) + list(options["names"] or [])
		if not options["no_names_file"]:
			path = Path(options["names_file"]).expanduser()
			if path.exists():
				names = parse_names(path.read_text(encoding="utf-8", errors="replace")) + names
			elif names:
				self.stdout.write(self.style.WARNING(f"Names file not found: {path}"))
			else:
				raise CommandError(f"Names file not found: {path}")

		minimum = max(int(options["min_length"]), 1)
		result: List[str] = []
		seen = set()
		for name in names:
			clean = str(name).strip()
			if len(clean) < minimum:
				continue
			key = clean.casefold()
			if key in seen:
				continue
			seen.add(key)
			result.append(clean)
		return result

	def _run(self, client, names: List[str], options, limit: int) -> Dict[str, int]:
		"""Search the names in order and store the next not-yet-stored titles.

		A title is skipped when it is already in the database under the kawaii
		``hash_id`` slug **or** under the same ``title`` + ``type`` (imported
		earlier via the bot/admin with a different slug). That way re-runs never
		create a second row for the same anime.
		"""
		dry_run = bool(options["dry_run"])
		with_cover = not options["no_covers"]

		stats = {"created": 0, "updated": 0, "failed": 0, "stored": 0, "found": 0, "skipped": 0}
		processed: Set[str] = set()
		total = len(names)

		for index, name in enumerate(names, start=1):
			if stats["stored"] >= limit:
				break
			try:
				results = self._search(client, name)
			except httpx.HTTPError as exc:
				stats["failed"] += 1
				self.stdout.write(self.style.WARNING(f"[{index}/{total}] {name!r}: search failed ({exc})"))
				self._sleep(options)
				continue

			stats["found"] += len(results)
			fresh = 0
			for item in results:
				if stats["stored"] >= limit:
					break
				hash_id = str(item.get("hash_id") or "").strip()
				if not hash_id or hash_id in processed:
					continue
				processed.add(hash_id)
				title_guess = _first_text(item.get("title_uzb"), item.get("title_org"))
				type_guess = map_media_type(item.get("type_uzb"), None, "")
				if self._already_imported(hash_id, title_guess, type_guess):
					stats["skipped"] += 1
					continue
				if self._store(client, hash_id, item, stats, with_cover=with_cover, dry_run=dry_run):
					fresh += 1
					stats["stored"] += 1
			self.stdout.write(
				f"[{index}/{total}] {name!r}: {len(results)} result(s), {fresh} new "
				f"(run total {stats['stored']}/{limit}, skipped={stats['skipped']})"
			)
			self._sleep(options)
		return stats

	def _already_imported(self, hash_id: str, title: str, media_type: str) -> bool:
		"""True when this kawaii title already has a row in the database."""
		if MediaTitle.objects.filter(slug=hash_id).exists():
			return True
		if title and media_type:
			if MediaTitle.objects.filter(title__iexact=title, type=media_type).exists():
				return True
		return False

	def _store(self, client, hash_id: str, item: Dict[str, Any], stats, *, with_cover: bool, dry_run: bool) -> bool:
		"""Fetch one anime page and persist it. Returns ``True`` when handled."""
		try:
			metadata, cover, cover_type = self._fetch_detail(client, hash_id, item, with_cover=with_cover)
		except (httpx.HTTPError, ValueError) as exc:
			stats["failed"] += 1
			self.stdout.write(self.style.WARNING(f"  {hash_id}: fetch failed ({exc})"))
			return False

		if dry_run:
			self.stdout.write(
				f"  ~ {hash_id}: {metadata['type']} · {metadata['title']!r} · {metadata['year']} · "
				f"{metadata['episodes']} qism · cover={'yes' if cover else 'no'}"
			)
			return True

		try:
			outcome = self._upsert(metadata, cover, cover_type)
		except Exception as exc:  # noqa: BLE001 - one bad row must not stop the import
			stats["failed"] += 1
			self.stdout.write(self.style.WARNING(f"  {hash_id}: save failed ({exc})"))
			return False

		stats[outcome] += 1
		self.stdout.write(
			self.style.SUCCESS(
				f"  {outcome}: {metadata['title']!r} ({metadata['type']}, #{hash_id}, cover={'yes' if cover else 'no'})"
			)
		)
		return True

	def _search(self, client, name: str) -> List[Dict[str, Any]]:
		response = client.get(SEARCH_ENDPOINT, params={"q": name})
		response.raise_for_status()
		try:
			payload = response.json()
		except ValueError as exc:
			raise httpx.HTTPError(f"invalid JSON for {name!r}") from exc
		data = payload.get("data") if isinstance(payload, dict) else None
		return [item for item in (data or []) if isinstance(item, dict)]

	def _fetch_detail(self, client, hash_id: str, search_item: Dict[str, Any], *, with_cover: bool):
		response = client.get(ANIME_PATH.format(hash_id=hash_id))
		response.raise_for_status()
		html = response.text
		metadata = build_metadata(hash_id, search_item, find_catalog_node(extract_ld_graphs(html)), html)
		cover, cover_type = (None, "")
		if with_cover and metadata["poster"]:
			cover, cover_type = self._download_cover(client, metadata["poster"])
		return metadata, cover, cover_type

	def _download_cover(self, client, url: str) -> Tuple[Optional[bytes], str]:
		try:
			response = client.get(url)
			response.raise_for_status()
		except httpx.HTTPError:
			return None, ""
		content_type = (response.headers.get("content-type") or "").split(";")[0].strip()
		if not content_type.startswith("image/"):
			content_type = guess_image_type(url)
		return response.content, content_type[:50]

	def _upsert(self, metadata: Dict[str, Any], cover: Optional[bytes], cover_type: str) -> str:
		"""Create (or refresh) the ``MediaTitle`` for this kawaii hash.

		Match order: ``slug == hash_id`` first, then the same ``title`` + ``type``
		(row created earlier by the bot/admin). Never creates a second row for
		an anime that is already in the catalog.
		"""
		slug = metadata["hash_id"]
		existing = MediaTitle.objects.filter(slug=slug).first()
		if existing is None and metadata["title"]:
			existing = MediaTitle.objects.filter(
				title__iexact=metadata["title"], type=metadata["type"]
			).first()
		if existing is not None:
			changed: List[str] = []
			for field, value in (
				("title", metadata["title"]),
				("type", metadata["type"]),
				("synopsis", metadata["synopsis"]),
				("release_year", metadata["year"]),
				("episode_count", metadata["episodes"]),
				("status", metadata["status"]),
				("language", "O'zbekcha"),
			):
				if value is not None and getattr(existing, field) != value:
					setattr(existing, field, value)
					changed.append(field)
			if metadata["rating"] is not None and existing.rating != metadata["rating"]:
				existing.rating = metadata["rating"]
				changed.append("rating")
			if cover:
				existing.cover = new_cover_file(cover, name=slug)
				existing.cover_content_type = cover_type
				changed += ["cover", "cover_content_type"]
			if changed:
				existing.save(update_fields=list(dict.fromkeys(changed + ["updated_at"])))
			self._sync_genres(existing, metadata["genres"])
			return "updated"

		title = MediaTitle(
			slug=slug,
			type=metadata["type"],
			title=metadata["title"],
			synopsis=metadata["synopsis"],
			release_year=metadata["year"],
			episode_count=metadata["episodes"],
			rating=metadata["rating"] or 5,
			status=metadata["status"],
			language="O'zbekcha",
			required_plan=MediaTitle.AccessPlan.FREE,
		)
		if cover:
			title.cover = new_cover_file(cover, name=slug)
			title.cover_content_type = cover_type
		title.save()
		self._sync_genres(title, metadata["genres"])
		return "created"

	def _sync_genres(self, title: MediaTitle, names: List[str]) -> None:
		if not names:
			return
		genres = []
		for name in names:
			genre, _ = Genre.objects.get_or_create(name=name[:50])
			genres.append(genre)
		title.genres.set(genres)

	def _sleep(self, options) -> None:
		delay = float(options.get("delay") or 0)
		if delay > 0:
			time.sleep(delay)
