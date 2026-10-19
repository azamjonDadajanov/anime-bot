"""``python manage.py ai_status`` — is the AI assistant able to answer?

The assistant is an online chat model with catalogue tools (see
``movies.ai_assistant``). This command reports exactly what the next question
will try, and can send one real prompt through the whole chain:

    python manage.py ai_status            # providers, models, cooldowns
    python manage.py ai_status --test     # one live call, then the answer

A deployment with no provider is a valid setup for everything else (the
catalogue, the bot, the site) — but the AI assistant is then unavailable,
because there is no offline fallback any more.
"""

from __future__ import annotations

import time

from django.core.management.base import BaseCommand, CommandError

from movies import ai_assistant, llm


class Command(BaseCommand):
	help = "Report the AI assistant's provider chain and optionally test it."

	def add_arguments(self, parser) -> None:
		parser.add_argument(
			"--test",
			action="store_true",
			help="Send one real prompt through the chain and report which provider answered.",
		)

	def handle(self, *args, **options) -> None:
		if options["test"]:
			self._test()
		self._status()

	def _status(self) -> None:
		configuration = llm.configuration()
		providers = configuration["providers"]
		if not providers:
			self.stdout.write(
				self.style.WARNING(
					"AI provayder yo'q: /django-admin/ da qator qo'shing yoki "
					"AI_LLM_API_KEY o'rnating. Yordamchi javob bera olmaydi."
				)
			)
			return
		self.stdout.write(f"AI zanjiri ({len(providers)} ta provayder):")
		for config in providers:
			state = "ishlaydi" if config["usable"] else "kutishda (limit/xato)"
			key = "kalit bor" if config["key_set"] else "KALIT YO'Q"
			self.stdout.write(
				f"  {config['priority']:>4}  {config['name']} / {config['model']} "
				f"[{config['kind']}, {key}, {state}]"
			)
		if not configuration["from_database"]:
			self.stdout.write(
				"  (baza bo'sh: faqat .env'dagi provayder ishlatilmoqda — "
				"/django-admin/ dan qatorlar qo'shsangiz zanjir bo'ladi.)"
			)
		if configuration["configured"]:
			self.stdout.write(
				self.style.SUCCESS(
					f"  - {configuration['usable']} ta provayder tayyor "
					f"({configuration['timeout']}s/provayder, jami "
					f"{configuration['deadline']}s)."
				)
			)
			return
		wait = configuration["next_retry_in"]
		self.stdout.write(
			self.style.WARNING(
				"  - hozir hammasi limitda: yordamchi javob bera olmaydi"
				+ (f", ~{wait}s dan keyin qayta uriniladi." if wait else ".")
			)
		)

	def _test(self) -> None:
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
		before = {row["name"]: row for row in llm.health()}
		started = time.monotonic()
		try:
			result = ai_assistant.answer("Katalogda nechta anime bor? Qisqa javob ber.")
		except Exception as exc:  # noqa: BLE001 - the command reports the failure
			raise CommandError(f"Yordamchi javob bermadi: {exc}") from exc
		elapsed = int((time.monotonic() - started) * 1000)
		if not result.used_llm:
			reason = result.error or "sabab noma'lum"
			raise CommandError(f"Yordamchi javob bermadi: {reason}")
		self.stdout.write(self.style.SUCCESS(f"Javob ({elapsed}ms): {result.answer[:400]}"))
		if result.tools:
			self.stdout.write("Chaqirilgan funksiyalar: " + ", ".join(result.tools))
		after = {row["name"]: row for row in llm.health()}
		for name, row in before.items():
			changed = after.get(name)
			if not changed:
				continue
			if changed["success_count"] != row["success_count"]:
				self.stdout.write(f"  ✓ javob berdi: {name}")
			elif changed["failure_count"] != row["failure_count"]:
				self.stdout.write(f"  ✗ o'tkazib yuborildi: {name} — {changed['last_error']}")
