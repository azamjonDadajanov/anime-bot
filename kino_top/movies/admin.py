from django.contrib import admin

from . import llm
from .models import (
	AIProvider,
	Genre,
	MediaPart,
	MediaTitle,
	ReadingProgress,
	TelegramChannel,
	TelegramMedia,
)


@admin.register(MediaTitle)
class MediaTitleAdmin(admin.ModelAdmin):
	list_display = ("title", "code", "slug", "type", "status", "required_plan")
	list_filter = ("type", "status", "required_plan")
	search_fields = ("title", "code", "slug")
	readonly_fields = ("code",)
	filter_horizontal = ("genres",)


@admin.register(TelegramChannel)
class TelegramChannelAdmin(admin.ModelAdmin):
	list_display = ("title", "chat_id", "username", "purpose", "is_active", "is_public")
	list_filter = ("purpose", "is_active", "is_public")
	search_fields = ("title", "chat_id", "username")


admin.site.register(MediaPart)
admin.site.register(TelegramMedia)
admin.site.register(Genre)


@admin.register(AIProvider)
class AIProviderAdmin(admin.ModelAdmin):
	"""The chat-model chain of the AI search, in the order it is tried.

	A search asks the first row that is not on cooldown and moves on only when
	that one refuses (see ``movies.llm.chat``), so this list is also the failover
	order: put the fastest free provider first, keep the paid one as the last
	resort. The runtime columns are written by the search itself — the actions
	below are for the two moments an operator needs them: clearing a cooldown
	after fixing a key, and trying a row right now.
	"""

	list_display = (
		"name",
		"kind",
		"model",
		"priority",
		"is_active",
		"key_state",
		"state",
		"avg_latency_ms",
		"last_error",
	)
	list_filter = ("kind", "is_active")
	search_fields = ("name", "kind", "model", "base_url")
	list_editable = ("priority", "is_active")
	readonly_fields = (
		"avg_latency_ms",
		"success_count",
		"failure_count",
		"cooldown_until",
		"last_error",
		"last_used_at",
		"created_at",
		"updated_at",
	)
	actions = ("test_selected", "clear_cooldowns", "activate", "deactivate")
	fieldsets = (
		(
			None,
			{
				"fields": (
					"name",
					"kind",
					"api_key",
					"model",
					"base_url",
					"priority",
					"is_active",
				),
				"description": (
					"Kalit, model va manzil bo'sh qolsa provayderning standart "
					"qiymati olinadi. Kalitsiz qator zanjirda ishlatilmaydi."
				),
			},
		),
		(
			"Holat (qidiruv yozadi)",
			{
				"fields": (
					"avg_latency_ms",
					"success_count",
					"failure_count",
					"cooldown_until",
					"last_error",
					"last_used_at",
				)
			},
		),
	)

	@admin.display(description="Kalit")
	def key_state(self, obj: AIProvider) -> str:
		return obj.masked_key

	@admin.display(description="Holat")
	def state(self, obj: AIProvider) -> str:
		if not obj.is_active:
			return "o'chirilgan"
		if obj.cooling_down:
			return "kutishda (limit)"
		if not (obj.api_key or "").strip():
			return "kalitsiz"
		return "tayyor"

	def save_model(self, request, obj, form, change) -> None:
		super().save_model(request, obj, form, change)
		# A saved row may be the fix for a limit that this very worker has in
		# memory: forget the in-process cooldowns so the next search tries again.
		llm.reset_cooldowns()

	@admin.action(description="Tanlangan provayderni hozir sinab ko'rish")
	def test_selected(self, request, queryset) -> None:
		"""Ask one provider a trivial question and report what came back."""
		import time

		for row in queryset:
			settings_row = llm.ProviderConfig(
				name=row.name,
				kind=row.kind,
				api_key=(row.api_key or "").strip(),
				model=(row.model or "").strip()
				or llm.PRESETS.get(row.kind, llm.PRESETS["custom"])["model"],
				base_url=(row.base_url or "").strip().rstrip("/")
				or llm.PRESETS.get(row.kind, llm.PRESETS["custom"])["base_url"],
				row_id=row.pk,
			)
			if not settings_row.api_key:
				self.message_user(request, f"{row.name}: kalit yo'q, sinab bo'lmaydi.")
				continue
			started = time.monotonic()
			try:
				answer = llm._attempt(
					settings_row,
					[{"role": "user", "content": "Ha yoki yo'q deb javob ber."}],
					max_tokens=16,
					temperature=0.0,
					seconds=llm.timeout(),
				)
			except llm.LLMUnavailable as exc:
				self.message_user(request, f"{row.name}: xato — {exc}")
				continue
			elapsed = int((time.monotonic() - started) * 1000)
			self.message_user(request, f"{row.name}: {elapsed}ms — {answer.strip()[:80]}")

	@admin.action(description="Kutishni (cooldown) tozalash")
	def clear_cooldowns(self, request, queryset) -> None:
		updated = queryset.update(cooldown_until=None, last_error="")
		llm.reset_cooldowns()
		self.message_user(request, f"{updated} ta provayderdan kutish olib tashlandi.")

	@admin.action(description="Yoqish")
	def activate(self, request, queryset) -> None:
		self.message_user(request, f"{queryset.update(is_active=True)} ta provayder yoqildi.")

	@admin.action(description="Zanjirdan chiqarish")
	def deactivate(self, request, queryset) -> None:
		self.message_user(
			request, f"{queryset.update(is_active=False)} ta provayder o'chirildi."
		)


@admin.register(ReadingProgress)
class ReadingProgressAdmin(admin.ModelAdmin):
	list_display = ("user", "part", "page", "is_read", "updated_at")
	list_filter = ("is_read",)
	search_fields = ("user__username", "part__content__title")
