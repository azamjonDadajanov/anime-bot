from django.contrib import admin

from .models import Income


@admin.register(Income)
class IncomeAdmin(admin.ModelAdmin):
	list_display = ("amount", "source", "method", "plan", "paid_at", "created_by")
	list_filter = ("source", "method", "plan")
	search_fields = ("note", "plan")
	date_hierarchy = "paid_at"
