from rest_framework.routers import DefaultRouter

from .views import (
	MediaPartViewSet,
	MediaTitleViewSet,
	ReadingProgressViewSet,
	TelegramChannelViewSet,
	TelegramMediaViewSet,
	TitleCommentViewSet,
)


router = DefaultRouter()
router.register("catalog", MediaTitleViewSet, basename="catalog")
router.register("comments", TitleCommentViewSet, basename="comments")
router.register("parts", MediaPartViewSet, basename="parts")
router.register("reading", ReadingProgressViewSet, basename="reading")
router.register("telegram-media", TelegramMediaViewSet, basename="telegram-media")
router.register("channels", TelegramChannelViewSet, basename="channels")

urlpatterns = router.urls