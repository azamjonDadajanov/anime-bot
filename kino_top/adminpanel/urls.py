from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
	AdminBotSettingsView,
	AdminBroadcastViewSet,
	AdminCouponViewSet,
	AdminDashboardView,
	AdminGenreViewSet,
	AdminIncomeViewSet,
	AdminLogListView,
	AdminMediaStatsView,
	AdminPodcastSendView,
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

urlpatterns = [
	path("dashboard/", AdminDashboardView.as_view(), name="admin-dashboard"),
	path("media-stats/", AdminMediaStatsView.as_view(), name="admin-media-stats"),
	path("podcast/send/", AdminPodcastSendView.as_view(), name="admin-podcast-send"),
	path("settings/", AdminBotSettingsView.as_view(), name="admin-settings"),
	path("logs/", AdminLogListView.as_view(), name="admin-logs"),
	path("", include(router.urls)),
]
