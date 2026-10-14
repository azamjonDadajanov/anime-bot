from django.contrib import admin

from .models import (
	Coupon,
	CouponRedemption,
	FavoriteContent,
	Giveaway,
	GiveawayEntry,
	GiveawayWinner,
	ReferralReward,
	Subscription,
	SubscriptionRequest,
	TelegramUser,
)


@admin.register(Subscription)
class SubscriptionAdmin(admin.ModelAdmin):
	list_display = ("user", "plan", "started_at", "expires_at", "updated_at")
	list_filter = ("plan",)
	search_fields = ("user__username", "user__email")


@admin.register(SubscriptionRequest)
class SubscriptionRequestAdmin(admin.ModelAdmin):
	list_display = ("user", "plan", "amount", "status", "created_at")
	list_filter = ("status", "plan")
	search_fields = ("user__username", "user__email", "card_number")


@admin.register(Coupon)
class CouponAdmin(admin.ModelAdmin):
	list_display = ("code", "days", "max_uses", "used_count", "is_active", "created_at")
	list_filter = ("is_active",)
	search_fields = ("code",)
	readonly_fields = ("used_count", "created_at", "updated_at")


@admin.register(CouponRedemption)
class CouponRedemptionAdmin(admin.ModelAdmin):
	list_display = ("coupon", "user", "telegram_id", "days", "created_at")
	list_filter = ("coupon",)
	search_fields = ("coupon__code", "user__username", "telegram_id")
	readonly_fields = ("coupon", "user", "telegram_id", "days", "created_at")


@admin.register(TelegramUser)
class TelegramUserAdmin(admin.ModelAdmin):
	list_display = ("telegram_id", "username", "is_blocked", "referred_by", "created_at")
	list_filter = ("is_blocked",)
	search_fields = ("telegram_id", "username", "first_name", "last_name")


@admin.register(ReferralReward)
class ReferralRewardAdmin(admin.ModelAdmin):
	list_display = ("user", "milestone", "days", "claimed_at")
	list_filter = ("milestone",)
	search_fields = ("user__username", "user__email")
	readonly_fields = ("user", "milestone", "days", "claimed_at")


@admin.register(Giveaway)
class GiveawayAdmin(admin.ModelAdmin):
	list_display = ("title", "reward_days", "winner_count", "status", "created_at")
	list_filter = ("status",)
	search_fields = ("title",)
	filter_horizontal = ("channels",)


@admin.register(GiveawayEntry)
class GiveawayEntryAdmin(admin.ModelAdmin):
	list_display = ("giveaway", "telegram_id", "status", "created_at")
	list_filter = ("status",)


@admin.register(GiveawayWinner)
class GiveawayWinnerAdmin(admin.ModelAdmin):
	list_display = ("giveaway", "telegram_id", "days", "notified_at", "created_at")
	list_filter = ("giveaway",)


admin.site.register(FavoriteContent)
