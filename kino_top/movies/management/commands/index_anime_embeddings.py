"""``python manage.py index_anime_embeddings`` — build/refresh the AI index.

The AI search ranks catalogue titles by sentence similarity (see
``movies.ai_search``). That index is derived data, so this command is the one
that can always be re-run:

* first run on a fresh deployment — download the model and embed everything;
* after a bulk import that ran with the AI search switched off;
* after switching ``AI_MODEL_FILE``/model version, which invalidates every
  vector at once.

Day-to-day edits do not need it: adding, editing or deleting a title (or its
genres) re-embeds just that title through the signals in ``movies.signals``.

	python manage.py index_anime_embeddings --download-model   # fetch the weights
	python manage.py index_anime_embeddings --status           # what is missing
	python manage.py index_anime_embeddings --test-llm         # is the chain alive?
	python manage.py index_anime_embeddings                    # fill the gaps
	python manage.py index_anime_embeddings --force --type anime
"""

from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError

from movies import ai_search, embeddings, llm
from movies.models import MediaTitle


class Command(BaseCommand):
	help = "Embed catalogue titles so the AI search can rank them (see movies.ai_search)."

	def add_arguments(self, parser) -> None:
		parser.add_argument(
			"--download-model",
			action="store_true",
			help="Download the ONNX model, tokenizer and configs before indexing.",
		)
		parser.add_argument(
			"--force",
			action="store_true",
			help="Re-embed every selected title instead of only the missing/stale ones.",
		)
		parser.add_argument(
			"--type",
			type=str,
			default="",
			help="Comma separated media types to index (default: every type).",
		)
		parser.add_argument(
			"--limit",
			type=int,
			default=0,
			help="Stop after embedding N titles (0 = no limit).",
		)
		parser.add_argument(
			"--dry-run",
			action="store_true",
			help="List what would be embedded without loading the model.",
		)
		parser.add_argument(
			"--status",
			action="store_true",
			help="Print the index coverage and exit.",
		)
		parser.add_argument(
			"--check",
			action="store_true",
			help="Verify that the model loads and can embed a sentence, then exit.",
		)
		parser.add_argument(
			"--test-llm",
			action="store_true",
			help="Send one real prompt through the reasoning chain and report which provider answered.",
		)
		parser.add_argument(
			"--quiet",
			action="store_true",
			help="Only print the final summary.",
		)

	def handle(self, *args, **options) -> None:
		if options["download_model"]:
			self._download()

		if options["status"]:
			self._status()
			return

		if options["check"]:
			self._check()
			return

		if options["test_llm"]:
			self._llm_test()
			return

		queryset = self._queryset(options["type"])
		if not ai_search.enabled() and not options["force"]:
			raise CommandError(
				"AI_SEARCH_ENABLED is off, so nothing will be indexed. "
				"Set AI_SEARCH_ENABLED=true (or pass --force to index anyway)."
			)

		if options["dry_run"]:
			self._dry_run(queryset, force=options["force"])
			return

		if not embeddings.is_ready():
			raise CommandError(
				"Model fayllari yo'q: "
				+ ", ".join(embeddings.missing_files())
				+ ". `python manage.py index_anime_embeddings --download-model` "
				"bilan yuklab oling (yoki AI_MODEL_DIR ni to'g'rilang)."
			)

		limit = int(options["limit"] or 0) or None
		quiet = bool(options["quiet"])

		# A steady line every 25 titles keeps a long first run from looking
		# frozen, without flooding the log of a large catalogue.
		progress_state = {"done": 0, "total": queryset.count()}

		def progress(title, written: bool) -> None:
			if quiet:
				return
			progress_state["done"] += 1
			done = progress_state["done"]
			if done % 25 == 0 or done == progress_state["total"]:
				self.stdout.write(f"  {done}/{progress_state['total']} — {title.title}")

		stats = {"total": 0, "indexed": 0, "skipped": 0, "failed": 0}
		try:
			stats = ai_search.index_titles(
				queryset, force=options["force"], limit=limit, on_progress=progress
			)
		except embeddings.EmbeddingUnavailable as exc:
			raise CommandError(str(exc)) from exc

		message = (
			f"AI indeks: {stats['indexed']} yangilandi, {stats['skipped']} o'zgarmadi, "
			f"{stats['failed']} xato (jami {stats['total']})."
		)
		self.stdout.write(self.style.SUCCESS(message))

	# ------------------------------------------------------------------ steps
	def _download(self) -> None:
		state = {"last": 0}

		def on_progress(name: str, done: int, total: int) -> None:
			# One line every ~20MB keeps a 470MB download visibly alive.
			if done - state["last"] < 20 << 20 and done != total:
				return
			state["last"] = done
			self.stdout.write(f"  {name}: {done / 1e6:.0f}/{total / 1e6:.0f} MB")

		self.stdout.write(f"Model papkasi: {embeddings.model_dir()}")
		downloaded = embeddings.download_model(on_progress=on_progress)
		if not downloaded:
			self.stdout.write("Barcha model fayllari allaqachon mavjud.")
		else:
			for path in downloaded:
				self.stdout.write(self.style.SUCCESS(f"Yuklandi: {path}"))
		embeddings.reset_encoder_cache()

	def _check(self) -> None:
		try:
			vectors = embeddings.encode_texts(["sarguzasht va qo'rqinchli anime"])
		except embeddings.EmbeddingUnavailable as exc:
			raise CommandError(str(exc)) from exc
		self.stdout.write(
			self.style.SUCCESS(
				f"Model ishlaydi: {embeddings.MODEL_NAME} "
				f"({embeddings.model_file()}), vektor o'lchami {len(vectors[0])}."
			)
		)

	def _status(self) -> None:
		status = ai_search.index_status()
		switched_on = "ha" if status["enabled"] else "yo'q"
		files_ready = "tayyor" if status["model_ready"] else "yo'q"
		self.stdout.write(f"Yoqilgan: {switched_on}")
		self.stdout.write(f"Model: {status['model']}")
		self.stdout.write(f"Model fayllari: {files_ready}")
		self.stdout.write(f"Model papkasi: {embeddings.model_dir()}")
		self.stdout.write(f"Indekslangan: {status['indexed']}/{status['titles']}")
		self.stdout.write(f"Oxirgi yangilanish: {status['latest'] or '—'}")
		self._llm_status()
		if not status["model_ready"]:
			self.stdout.write(
				self.style.WARNING(
					"  - `--download-model` bilan modelni yuklab oling."
				)
			)
		if not status["indexed"]:
			self.stdout.write(
				self.style.WARNING("  - indeks bo'sh: `index_anime_embeddings` ni ishga tushiring.")
			)
			return
		stale = ai_search.stale_titles()
		if not stale:
			self.stdout.write("Eskirgan yozuvlar yo'q.")
			return
		self.stdout.write(self.style.WARNING(f"Eskirgan: {len(stale)} ta"))
		for title in stale[:10]:
			self.stdout.write(f"  - #{title.pk} {title.title} ({title.type})")

	def _llm_status(self) -> None:
		"""The "fikrlash" chain: every provider, whether it can be asked now.

		Reported here because it is the one part of the feature that lives
		outside the repository — a missing key silently leaves the search
		answering without an explanation. The chain itself comes from the
		``AIProvider`` table (see ``movies.llm.provider_chain``), so this printout
		is exactly what the next search will try, in order.
		"""
		configuration = llm.configuration()
		providers = configuration["providers"]
		if not providers:
			self.stdout.write(
				self.style.WARNING(
					"Fikrlash modeli: yo'q — AI_LLM_API_KEY bo'sh va bazada faol AI "
					"provayder yo'q. Qidiruv ishlaydi, lekin izohsiz."
				)
			)
			return
		self.stdout.write(f"Fikrlash zanjiri ({len(providers)} ta provayder):")
		for config in providers:
			state = "ishlaydi" if config["usable"] else "kutishda (limit/xato)"
			sky = "kalit bor" if config["key_set"] else "KALIT YO'Q"
			self.stdout.write(
				f"  {config['priority']:>4}  {config['name']} / {config['model']} "
				f"[{config['kind']}, {sky}, {state}]"
			)
		if not configuration["from_database"]:
			self.stdout.write(
				"  (baza bo'sh: faqat .env'dagi provayder ishlatilmoqda — "
				"/django-admin/ dan qatorlar qo'shsangiz zanjir bo'ladi.)"
			)
		if configuration["configured"]:
			self.stdout.write(
				self.style.SUCCESS(
					f"  - {configuration['usable']} ta provayder tayyor, javob izohi yoqilgan "
					f"({configuration['timeout']}s/provayder, jami {configuration['deadline']}s)."
				)
			)
			return
		wait = configuration["next_retry_in"]
		self.stdout.write(
			self.style.WARNING(
				"  - hozir hammasi limitda: qidiruv vektor natijalari bilan javob beradi"
				+ (f", ~{wait}s dan keyin qayta uriniladi." if wait else ".")
			)
		)

	def _llm_test(self) -> None:
		"""Send one real prompt through the chain: which provider answers, how fast.

		The failover can only be believed by watching it happen, so this asks a
		trivial question and prints the provider that answered plus the elapsed
		time. A chain with one dead provider is the interesting case, and the
		result is visible in the log line above the answer.
		"""
		import time

		configuration = llm.configuration()
		if not configuration["providers"]:
			raise CommandError(
				"AI provayder yo'q: /django-admin/ da qator qo'shing yoki "
				"AI_LLM_API_KEY o'rnating."
			)
		if not configuration["configured"]:
			wait = configuration["next_retry_in"]
			raise CommandError(
				"Hamma provayder kutishda (limit yoki xato)"
				+ (f": ~{wait}s dan keyin qayta urinib ko'ring." if wait else ".")
			)
		before = llm.health()
		started = time.monotonic()
		try:
			answer = llm.chat(
				[
					{"role": "system", "content": "Bir so'z bilan javob ber."},
					{"role": "user", "content": "Toshkent O'zbekistonning poytaxtimi? Ha yoki yo'q."},
				],
				max_tokens=32,
			)
		except llm.LLMUnavailable as exc:
			raise CommandError(f"Hech bir provayder javob bermadi: {exc}") from exc
		elapsed = int((time.monotonic() - started) * 1000)
		self.stdout.write(self.style.SUCCESS(f"Javob ({elapsed}ms): {answer.strip()[:200]}"))
		self._llm_status()
		after = {row["name"]: row for row in llm.health()}
		for row in before:
			changed = after.get(row["name"])
			if not changed:
				continue
			if changed["success_count"] != row["success_count"]:
				self.stdout.write(f"  ✓ javob berdi: {row['name']}")
			elif changed["failure_count"] != row["failure_count"]:
				self.stdout.write(f"  ✗ o'tkazib yuborildi: {row['name']} — {changed['last_error']}")

	def _dry_run(self, queryset, *, force: bool) -> None:
		if force:
			pending = list(queryset.prefetch_related("genres"))
		else:
			pending = ai_search.stale_titles(queryset)
		self.stdout.write(f"Indekslanishi kerak: {len(pending)} ta")
		for title in pending[:20]:
			self.stdout.write(f"  - #{title.pk} {title.title} ({title.type})")
		if len(pending) > 20:
			self.stdout.write(f"  … yana {len(pending) - 20} ta")

	def _queryset(self, raw_types: str):
		"""Every title, or only the requested media types (validated)."""
		queryset = MediaTitle.objects.all()
		requested = [value.strip() for value in str(raw_types or "").split(",") if value.strip()]
		if not requested:
			return queryset
		invalid = [value for value in requested if value not in MediaTitle.MediaType.values]
		if invalid:
			raise CommandError(
				"Noto'g'ri tur(lar): "
				+ ", ".join(invalid)
				+ ". Ruxsat etilgan: "
				+ ", ".join(MediaTitle.MediaType.values)
			)
		return queryset.filter(type__in=requested)
