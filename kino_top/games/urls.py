from django.urls import path

from . import views
from .battle_views import (
    StartBattleView, NextWaveView, CompleteBattleView,
    FleeBattleView, GetMonsterTypesView,
)

app_name = "games"

urlpatterns = [
	path("status/", views.GameStatusView.as_view(), name="game-status"),
	path("titles/", views.GameTitlesView.as_view(), name="game-titles"),
	path("quiz/start/", views.QuizStartView.as_view(), name="quiz-start"),
	path("quiz/submit/", views.QuizSubmitView.as_view(), name="quiz-submit"),
	path("leaderboard/", views.LeaderboardView.as_view(), name="game-leaderboard"),

	# Anime Artifact Hunter & Dynamic Portals endpoints
	path("artifact/auth/", views.ArtifactAuthView.as_view(), name="artifact-auth"),
	path("artifact/state/", views.ArtifactGameStateView.as_view(), name="artifact-state"),
	path("artifact/select-character/", views.SelectCharacterClassView.as_view(), name="artifact-select-character"),
	path("artifact/save-position/", views.SavePlayerPositionView.as_view(), name="artifact-save-position"),
	path("artifact/enter-portal/", views.EnterPortalView.as_view(), name="artifact-enter-portal"),
	path("artifact/combat/", views.ArtifactCombatView.as_view(), name="artifact-combat"),
	path("artifact/inventory/toggle-equip/", views.ToggleEquipItemView.as_view(), name="artifact-toggle-equip"),

	# Jang tizimi (Battle System)
	path("artifact/battle/start/",    StartBattleView.as_view(),    name="battle-start"),
	path("artifact/battle/next-wave/", NextWaveView.as_view(),      name="battle-next-wave"),
	path("artifact/battle/complete/", CompleteBattleView.as_view(),  name="battle-complete"),
	path("artifact/battle/flee/",     FleeBattleView.as_view(),      name="battle-flee"),
	path("artifact/monsters/",        GetMonsterTypesView.as_view(), name="monster-types"),
]

