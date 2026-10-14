from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone


class Income(models.Model):
	"""Oylik tushumlar: obuna to'lovlari va qo'lda kiritilgan daromadlar."""

	class Source(models.TextChoices):
		SUBSCRIPTION = "subscription", "Obuna"
		PODCAST = "podcast", "Podcast"
		OTHER = "other", "Boshqa"

	class Method(models.TextChoices):
		CARD = "card", "Karta"
		CASH = "cash", "Naqd"
		TRANSFAR = "transfer", "O'tkazma"
		OTHER = "other", "Boshqa"

	amount = models.DecimalField(
		max_digits=12,
		decimal_places=2,
		validators=[MinValueValidator(0)],
	)
	source = models.CharField(
		max_length=16,
		choices=Source.choices,
		default=Source.SUBSCRIPTION,
	)
	method = models.CharField(
		max_length=16,
		choices=Method.choices,
		default=Method.CARD,
	)
	plan = models.CharField(max_length=10, blank=True, default="")
	note = models.TextField(blank=True, default="")
	paid_at = models.DateTimeField(default=timezone.now)
	created_by = models.ForeignKey(
		settings.AUTH_USER_MODEL,
		on_delete=models.SET_NULL,
		null=True,
		blank=True,
		related_name="incomes_created",
	)
	created_at = models.DateTimeField(auto_now_add=True)
	updated_at = models.DateTimeField(auto_now=True)

	class Meta:
		ordering = ["-paid_at", "-id"]
		indexes = [
			models.Index(fields=["-paid_at"], name="income_paid_idx"),
			models.Index(fields=["source"], name="income_source_idx"),
		]

	def __str__(self) -> str:
		return f"{self.amount} ({self.get_source_display()}) - {self.paid_at:%Y-%m-%d}"

	@property
	def year_month(self) -> str:
		return self.paid_at.strftime("%Y-%m")
