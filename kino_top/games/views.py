"""Game REST endpoints (JWT protected).

Routes (mounted under ``/api/game/``):

* ``GET  status/``      — points, level, verified count and the rules echo.
* ``GET  titles/?q=``   — unlocked + verified titles for the current user.
* ``POST quiz/start/``  — open a quiz (one attempt per title, lifetime).
* ``POST quiz/submit/`` — score an attempt (never reveals correct answers).
* ``GET  leaderboard/`` — monthly-style top players by points.
"""

from __future__ import annotations

from django.utils import timezone
from rest_framework import status
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from . import services
from .serializers import LeaderboardSerializer, QuizStartSerializer, QuizSubmitSerializer


class GameErrorMixin:
	"""Translate :class:`services.GameError` into a proper 4xx response."""

	def handle_error(self, exc: services.GameError) -> Response:
		codes = {
			services.ALREADY_VERIFIED: status.HTTP_409_CONFLICT,
			services.NO_RETRY: status.HTTP_409_CONFLICT,
			services.UNFINISHED: status.HTTP_409_CONFLICT,
			services.DAILY_LIMIT: status.HTTP_429_TOO_MANY_REQUESTS,
			services.NOT_WATCHED: status.HTTP_403_FORBIDDEN,
			services.NO_QUESTIONS: status.HTTP_404_NOT_FOUND,
			services.NOT_FOUND: status.HTTP_404_NOT_FOUND,
			services.BAD_INPUT: status.HTTP_400_BAD_REQUEST,
		}
		return Response(
			{"detail": exc.detail, "code": exc.code},
			status=codes.get(exc.code, status.HTTP_400_BAD_REQUEST),
		)


class GameStatusView(APIView, GameErrorMixin):
	permission_classes = [IsAuthenticated]

	def get(self, request):
		return Response(services.user_status(request.user))


class GameTitlesView(APIView, GameErrorMixin):
	permission_classes = [IsAuthenticated]

	def get(self, request):
		query = (request.query_params.get("q") or "").strip()
		return Response(services.eligible_titles(request.user, query))


class QuizStartView(APIView, GameErrorMixin):
	permission_classes = [IsAuthenticated]

	def post(self, request):
		serializer = QuizStartSerializer(data=request.data)
		serializer.is_valid(raise_exception=True)
		try:
			payload = services.start_attempt_sync(
				request.user, serializer.validated_data["title_id"]
			)
		except services.GameError as exc:
			return self.handle_error(exc)
		return Response(payload, status=status.HTTP_201_CREATED)


class QuizSubmitView(APIView, GameErrorMixin):
	permission_classes = [IsAuthenticated]

	def post(self, request):
		serializer = QuizSubmitSerializer(data=request.data)
		serializer.is_valid(raise_exception=True)
		data = serializer.validated_data
		try:
			payload = services.submit_attempt_sync(
				request.user,
				data["attempt_id"],
				data["answers"],
				data.get("elapsed_ms", 0),
			)
		except services.GameError as exc:
			return self.handle_error(exc)
		return Response(payload)


class LeaderboardView(APIView, GameErrorMixin):
	permission_classes = [IsAuthenticated]

	def get(self, request):
		serializer = LeaderboardSerializer(data=request.query_params)
		serializer.is_valid(raise_exception=True)
		payload = services.leaderboard(
			user=request.user,
			limit=serializer.validated_data.get("limit", 50),
		)
		payload["month"] = timezone.now().strftime("%Y-%m")
		return Response(payload)
