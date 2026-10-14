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
