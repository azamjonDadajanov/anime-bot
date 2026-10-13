from django.contrib import admin

from .models import Genre, MediaPart, MediaTitle, ReadingProgress, TelegramChannel, TelegramMedia


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


@admin.register(ReadingProgress)
class ReadingProgressAdmin(admin.ModelAdmin):
	list_display = ("user", "part", "page", "is_read", "updated_at")
	list_filter = ("is_read",)
	search_fields = ("user__username", "part__content__title")
