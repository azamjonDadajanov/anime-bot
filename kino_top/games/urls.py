from django.urls import path

from . import views

app_name = "games"

urlpatterns = [
	path("status/", views.GameStatusView.as_view(), name="game-status"),
	path("titles/", views.GameTitlesView.as_view(), name="game-titles"),
	path("quiz/start/", views.QuizStartView.as_view(), name="quiz-start"),
	path("quiz/submit/", views.QuizSubmitView.as_view(), name="quiz-submit"),
	path("leaderboard/", views.LeaderboardView.as_view(), name="game-leaderboard"),
]
