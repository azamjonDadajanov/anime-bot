from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
	AdminAnimeVerificationViewSet,
	AdminBotSettingsView,
	AdminBroadcastViewSet,
	AdminCouponViewSet,
	AdminDashboardView,
	AdminGameLeaderboardView,
	AdminGenreViewSet,
	AdminIncomeViewSet,
	AdminLogListView,
	AdminMediaStatsView,
	AdminMonthlyPrizeViewSet,
	AdminPodcastSendView,
	AdminQuizAttemptViewSet,
	AdminQuizQuestionViewSet,
	AdminSubscriptionRequestViewSet,
	AdminUserViewSet,
)

router = DefaultRouter()
router.register("users", AdminUserViewSet, basename="admin-users")
router.register(
	"subscription-requests",
	AdminSubscriptionRequestViewSet,
	basename="admin-subscription-requests",
)
router.register("income", AdminIncomeViewSet, basename="admin-income")
router.register("genres", AdminGenreViewSet, basename="admin-genres")
router.register("coupons", AdminCouponViewSet, basename="admin-coupons")
router.register("broadcasts", AdminBroadcastViewSet, basename="admin-broadcasts")
router.register("quiz-questions", AdminQuizQuestionViewSet, basename="admin-quiz-questions")
router.register("quiz-attempts", AdminQuizAttemptViewSet, basename="admin-quiz-attempts")
router.register("verifications", AdminAnimeVerificationViewSet, basename="admin-verifications")
router.register("monthly-prizes", AdminMonthlyPrizeViewSet, basename="admin-monthly-prizes")

urlpatterns = [
	path("dashboard/", AdminDashboardView.as_view(), name="admin-dashboard"),
	path("media-stats/", AdminMediaStatsView.as_view(), name="admin-media-stats"),
	path("podcast/send/", AdminPodcastSendView.as_view(), name="admin-podcast-send"),
	path("settings/", AdminBotSettingsView.as_view(), name="admin-settings"),
	path("logs/", AdminLogListView.as_view(), name="admin-logs"),
	path("game/leaderboard/", AdminGameLeaderboardView.as_view(), name="admin-game-leaderboard"),
	path("", include(router.urls)),
]
