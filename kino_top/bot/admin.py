"""Django admin integration for the bot models."""

from __future__ import annotations

from django.contrib import admin

from .models import BotLogEntry, BotSettings, Broadcast, BroadcastDelivery, FSMState


@admin.register(BotSettings)
class BotSettingsAdmin(admin.ModelAdmin):
	list_display = (
		"__str__",
		"require_subscription",
		"auto_publish_new_content",
		"publish_channel",
		"protect_content",
		"maintenance_mode",
		"updated_at",
	)

	def has_add_permission(self, request) -> bool:
		# The row is a singleton created on demand by the bot.
		return not BotSettings.objects.exists()


@admin.register(FSMState)
class FSMStateAdmin(admin.ModelAdmin):
	list_display = ("key", "user_id", "chat_id", "state", "expires_at", "updated_at")
	list_filter = ("destiny",)
	search_fields = ("key", "state")
	readonly_fields = ("created_at", "updated_at")


class BroadcastDeliveryInline(admin.TabularInline):
	model = BroadcastDelivery
	extra = 0
	readonly_fields = ("telegram_id", "status", "error", "created_at")
	can_delete = False


@admin.register(Broadcast)
class BroadcastAdmin(admin.ModelAdmin):
	list_display = (
		"id",
		"kind",
		"status",
		"admin_telegram_id",
		"total",
		"sent_count",
		"failed_count",
		"blocked_count",
		"created_at",
	)
	list_filter = ("status", "kind")
	search_fields = ("text", "caption", "id")
	readonly_fields = ("created_at", "started_at", "finished_at", "cursor_telegram_id")
	inlines = (BroadcastDeliveryInline,)


@admin.register(BotLogEntry)
class BotLogEntryAdmin(admin.ModelAdmin):
	list_display = ("created_at", "level", "logger", "telegram_id", "message")
	list_filter = ("level",)
	search_fields = ("message", "logger")
	readonly_fields = ("created_at", "level", "logger", "message", "telegram_id")
