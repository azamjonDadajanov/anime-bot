from django.contrib import admin

from .models import AnimeVerification, GameActivity, MonthlyPrize, QuizAttempt, QuizQuestion


@admin.register(QuizQuestion)
class QuizQuestionAdmin(admin.ModelAdmin):
	list_display = ("id", "title", "text", "correct_index", "is_active", "created_at")
	list_filter = ("is_active", "title__type")
	search_fields = ("text", "title__title")
	list_editable = ("is_active",)


@admin.register(AnimeVerification)
class AnimeVerificationAdmin(admin.ModelAdmin):
	list_display = ("id", "user", "title", "points", "verified_at")
	list_filter = ("title__type",)
	search_fields = ("user__username", "title__title")


@admin.register(QuizAttempt)
class QuizAttemptAdmin(admin.ModelAdmin):
	list_display = ("id", "user", "title", "passed", "points_awarded", "is_suspicious", "started_at", "finished_at")
	list_filter = ("passed", "is_suspicious", "title__type")
	search_fields = ("user__username", "title__title")
	readonly_fields = ("question_ids", "answers", "elapsed_ms", "started_at", "finished_at")


@admin.register(GameActivity)
class GameActivityAdmin(admin.ModelAdmin):
	list_display = ("id", "user", "date")
	list_filter = ("date",)
	search_fields = ("user__username",)


@admin.register(MonthlyPrize)
class MonthlyPrizeAdmin(admin.ModelAdmin):
	list_display = ("id", "year", "month", "user", "points", "days", "awarded_at")
	list_filter = ("year", "month")
	search_fields = ("user__username",)


# =====================================================================
# Artifact Hunter & Dynamic Portals Admin Setup
# =====================================================================

from .artifact_models import (
	ArtifactPlayerProfile,
	GameItem,
	GamePortal,
	PlayerInventory,
	PortalAccessLog,
	PortalCondition,
	PortalLootTable,
)


class PortalConditionInline(admin.TabularInline):
	model = PortalCondition
	extra = 1
	autocomplete_fields = ["custom_title"]


class PortalLootTableInline(admin.TabularInline):
	model = PortalLootTable
	extra = 1
	autocomplete_fields = ["item"]


@admin.register(GameItem)
class GameItemAdmin(admin.ModelAdmin):
	list_display = ("id", "name", "code", "rarity", "item_type", "power", "is_sellable", "sell_price")
	list_filter = ("rarity", "item_type", "is_sellable")
	search_fields = ("name", "code", "description")
	prepopulated_fields = {"code": ("name",)}


@admin.register(GamePortal)
class GamePortalAdmin(admin.ModelAdmin):
	list_display = ("id", "name", "code", "tier", "is_active", "cooldown_minutes", "pos_x", "pos_z")
	list_filter = ("tier", "is_active")
	search_fields = ("name", "code", "description")
	prepopulated_fields = {"code": ("name",)}
	inlines = [PortalConditionInline, PortalLootTableInline]


@admin.register(ArtifactPlayerProfile)
class ArtifactPlayerProfileAdmin(admin.ModelAdmin):
	list_display = ("id", "user", "character_class", "level", "experience", "coins", "gems", "portals_cleared")
	list_filter = ("character_class", "level")
	search_fields = ("user__username", "user__first_name")


@admin.register(PlayerInventory)
class PlayerInventoryAdmin(admin.ModelAdmin):
	list_display = ("id", "player", "item", "quantity", "is_equipped", "acquired_at")
	list_filter = ("is_equipped", "item__rarity", "item__item_type")
	search_fields = ("player__user__username", "item__name")
	autocomplete_fields = ["player", "item"]


@admin.register(PortalAccessLog)
class PortalAccessLogAdmin(admin.ModelAdmin):
	list_display = ("id", "player", "portal", "accessed_at")
	list_filter = ("portal",)
	search_fields = ("player__user__username", "portal__name")
	readonly_fields = ("player", "portal", "reward_summary", "accessed_at")

