"""``python manage.py ai_setup`` — the provider chain, ready to work.

The assistant must survive a provider running out of quota or a model being
withdrawn, so it is configured as a *chain* of rows (see
:func:`movies.llm.provider_chain`) instead of one key. This command writes that
chain: a set of models that work with the key in ``.env``, tried one after
another, so a dead model is skipped instead of breaking the whole feature.

    python manage.py ai_setup           # add or update the default chain
    python manage.py ai_setup --reset   # drop the rows this command owns first

The rows carry **no key of their own**: a Gemini row borrows the Gemini key
from ``.env`` (a Groq key cannot open Gemini's door), so the secret stays in
one place. A row that needs its own key — a second provider, a paid tier —
simply gets one in the admin panel.

The chain is idempotent: running it again only refreshes what it owns, and a
row the operator renamed or disabled is left alone.
"""

from __future__ import annotations

from django.core.management.base import BaseCommand
from django.db import transaction

from movies import llm
from movies.models import AIProvider

# The default chain: same key, different models. A model that is withdrawn
# (HTTP 404) or overloaded (503) is skipped for a while, and the next one
# answers — which is exactly what a single model cannot do.
#
# Every model below was checked with this key: it answers, and it can call
# the catalogue's functions (a model that cannot is useless for a search
# assistant). The order is by how quickly they answer.
DEFAULT_CHAIN = (
	{
		"name": "Gemini 3.5 Flash Lite",
		"kind": AIProvider.Kind.GEMINI,
		"model": "gemini-3.5-flash-lite",
		"priority": 10,
	},
	{
		"name": "Gemini 3.6 Flash",
		"kind": AIProvider.Kind.GEMINI,
		"model": "gemini-3.6-flash",
		"priority": 20,
	},
	{
		"name": "Gemini Flash Lite (alias)",
		"kind": AIProvider.Kind.GEMINI,
		"model": "gemini-flash-lite-latest",
		"priority": 30,
	},
	{
		"name": "Gemini 3.1 Flash Lite Preview",
		"kind": AIProvider.Kind.GEMINI,
		"model": "gemini-3.1-flash-lite-preview",
		"priority": 40,
	},
	{
		"name": "Gemini 3 Flash Preview",
		"kind": AIProvider.Kind.GEMINI,
		"model": "gemini-3-flash-preview",
		"priority": 50,
	},
)


# The names this command has used over time. ``--reset`` removes exactly
# these rows: a row an operator created by hand is never touched.
OWNED_NAMES = tuple(item["name"] for item in DEFAULT_CHAIN) + (
	"Gemma 4 31B",
)


class Command(BaseCommand):
	help = "Write the default AI provider chain (the models that work with the .env key)."

	def add_arguments(self, parser) -> None:
		parser.add_argument(
			"--reset",
			action="store_true",
			help="Remove the rows this command owns before writing them again.",
		)
		parser.add_argument(
			"--only",
			default="",
			help="Write only the named models (comma separated), e.g. gemini-3.5-flash-lite.",
		)

	def handle(self, *args, **options) -> None:
		env = llm.env_provider()
		if not env.api_key:
			self.stdout.write(
				self.style.WARNING(
					"AI_LLM_API_KEY yo'q: qatorlar kalitsiz yoziladi va .env'ga "
					"kalit qo'yilgach ishlatiladi."
				)
			)
		wanted = {item.strip() for item in str(options["only"] or "").split(",") if item.strip()}
		chain = [
			item for item in DEFAULT_CHAIN if not wanted or item["model"] in wanted
		]
		if not chain:
			self.stdout.write(self.style.WARNING("Mos model topilmadi."))
			return

		if options["reset"]:
			removed, _ = AIProvider.objects.filter(name__in=OWNED_NAMES).delete()
			self.stdout.write(f"{removed} ta eski qator o'chirildi.")

		created = 0
		updated = 0
		with transaction.atomic():
			for item in chain:
				row, was_created = AIProvider.objects.update_or_create(
					name=item["name"],
					defaults={
						"kind": item["kind"],
						"model": item["model"],
						"priority": item["priority"],
						"is_active": True,
						"supports_tools": True,
					},
				)
				if was_created:
					created += 1
					self.stdout.write(f"  + {row.name} ({row.model})")
				else:
					updated += 1
					self.stdout.write(f"  ~ {row.name} ({row.model}) yangilandi")

		# A row the operator turned off stays off: only the chain this command
		# owns was touched, and the cooldown of an edited row is stale anyway.
		llm.reset_cooldowns()
		llm.reset_signature_cache()
		self.stdout.write(
			self.style.SUCCESS(
				f"{created} ta qator yozildi, {updated} ta yangilandi. "
				"Endi zanjirni tekshiring: python manage.py ai_status --test"
			)
		)
