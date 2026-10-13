from django.contrib import admin

from .models import FavoriteContent, Subscription, SubscriptionRequest, TelegramUser


@admin.register(Subscription)
class SubscriptionAdmin(admin.ModelAdmin):
	list_display = ("user", "plan", "updated_at")
	list_filter = ("plan",)
	search_fields = ("user__username", "user__email")


@admin.register(SubscriptionRequest)
class SubscriptionRequestAdmin(admin.ModelAdmin):
	list_display = ("user", "plan", "amount", "status", "created_at")
	list_filter = ("status", "plan")
	search_fields = ("user__username", "user__email", "card_number")


@admin.register(TelegramUser)
class TelegramUserAdmin(admin.ModelAdmin):
	list_display = ("telegram_id", "username", "is_blocked", "created_at")
	list_filter = ("is_blocked",)
	search_fields = ("telegram_id", "username", "first_name", "last_name")


admin.site.register(FavoriteContent)
