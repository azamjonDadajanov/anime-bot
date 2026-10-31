"""Anime rating game: quiz-based proof of watching, points and monthly prize.

The anti-cheat contract (see ``games.services``):

* a quiz unlocks only after the user actually received parts of that title in
  the Telegram bot (``MediaView`` with ``source=bot``);
* each title allows **one attempt ever** — a failed quiz cannot be retried;
* correct answers are never revealed (only the score is returned);
* points scale with the number of correct answers; an anime is marked
  "watched" (verified) only at the pass threshold;
* server-side timing checks flag suspiciously fast submissions (0 points).
"""

from __future__ import annotations

from django.conf import settings
from django.db import models


class QuizQuestion(models.Model):
	"""One admin-authored quiz item: a question with four choices."""

	title = models.ForeignKey(
		"movies.MediaTitle",
		on_delete=models.CASCADE,
		related_name="quiz_questions",
	)
	text = models.CharField(max_length=500)
	choices = models.JSONField(default=list, blank=True)
	correct_index = models.PositiveSmallIntegerField(default=0)
	is_active = models.BooleanField(default=True)
	created_at = models.DateTimeField(auto_now_add=True)

	class Meta:
		ordering = ["title_id", "id"]

	def __str__(self) -> str:
		return f"{self.title_id}: {self.text[:40]}"

	@property
	def correct_choice(self) -> str:
		try:
			return str(self.choices[self.correct_index])
		except (IndexError, TypeError):
			return ""


class AnimeVerification(models.Model):
	"""A title the user *proved* they watched (>= pass score on the quiz)."""

	user = models.ForeignKey(
		settings.AUTH_USER_MODEL,
		on_delete=models.CASCADE,
		related_name="game_verifications",
	)
	title = models.ForeignKey(
		"movies.MediaTitle",
		on_delete=models.CASCADE,
		related_name="game_verifications",
	)
	points = models.PositiveIntegerField(default=0)
	verified_at = models.DateTimeField(auto_now_add=True)

	class Meta:
		ordering = ["-verified_at"]
		constraints = [
			models.UniqueConstraint(
				fields=["user", "title"],
				name="unique_game_verification",
			),
		]
		indexes = [
			models.Index(fields=["user", "-verified_at"], name="gamever_user_idx"),
		]

	def __str__(self) -> str:
		return f"{self.user_id} - {self.title_id} ({self.points})"


class QuizAttempt(models.Model):
	"""One quiz sitting; ``finished_at`` is set exactly once (no retries)."""

	user = models.ForeignKey(
		settings.AUTH_USER_MODEL,
		on_delete=models.CASCADE,
		related_name="game_attempts",
	)
	title = models.ForeignKey(
		"movies.MediaTitle",
		on_delete=models.CASCADE,
		related_name="game_attempts",
	)
	question_ids = models.JSONField(default=list, blank=True)
	choice_orders = models.JSONField(
		default=list,
		blank=True,
		help_text="Har uchun variantlar tartibi (tasodifiy aralashtirilgan indekslar).",
	)
	answers = models.JSONField(default=list, blank=True)
	elapsed_ms = models.PositiveIntegerField(default=0)
	started_at = models.DateTimeField(auto_now_add=True)
	finished_at = models.DateTimeField(null=True, blank=True)
	passed = models.BooleanField(default=False)
	points_awarded = models.PositiveIntegerField(default=0)
	is_suspicious = models.BooleanField(default=False)

	class Meta:
		ordering = ["-started_at"]
		indexes = [
			models.Index(fields=["user", "title", "finished_at"], name="gameattempt_user_idx"),
			models.Index(fields=["user", "started_at"], name="gameattempt_started_idx"),
		]

	def __str__(self) -> str:
		state = "done" if self.finished_at else "open"
		return f"{self.user_id} - {self.title_id} ({state})"


class GameActivity(models.Model):
	"""A day the user played (used for the monthly prize eligibility)."""

	user = models.ForeignKey(
		settings.AUTH_USER_MODEL,
		on_delete=models.CASCADE,
		related_name="game_activity_days",
	)
	date = models.DateField()

	class Meta:
		ordering = ["-date"]
		constraints = [
			models.UniqueConstraint(
				fields=["user", "date"],
				name="unique_game_activity_day",
			),
		]

	def __str__(self) -> str:
		return f"{self.user_id} - {self.date}"


class MonthlyPrize(models.Model):
	"""The 1-month subscription awarded to the top active non-subscriber."""

	year = models.PositiveIntegerField()
	month = models.PositiveSmallIntegerField()
	user = models.ForeignKey(
		settings.AUTH_USER_MODEL,
		on_delete=models.CASCADE,
		related_name="game_monthly_prizes",
	)
	points = models.PositiveIntegerField(default=0)
	days = models.PositiveIntegerField(default=30)
	awarded_at = models.DateTimeField(auto_now_add=True)

	class Meta:
		ordering = ["-awarded_at"]
		constraints = [
			models.UniqueConstraint(
				fields=["year", "month"],
				name="unique_game_monthly_prize",
			),
		]

	def __str__(self) -> str:
		return f"{self.year}-{self.month:02d}: {self.user_id} ({self.points} ball)"


# Artifact Hunter & Dynamic Portals models
from .artifact_models import *  # noqa: F401, F403

from .battle_models import *    # noqa: F401, F403
