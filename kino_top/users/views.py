import math

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db.models import Sum
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import generics, status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.pagination import PageNumberPagination
from rest_framework.views import APIView
from rest_framework_simplejwt.views import TokenObtainPairView
from rest_framework_simplejwt.views import TokenRefreshView
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from movies.models import MediaTitle, MediaView, ReadingProgress
from movies.serializers import MediaTitleSerializer

from .models import FavoriteContent, Subscription, SubscriptionRequest, SupportMessage, UserSettings

from .serializers import (
	CurrentUserSerializer,
	FavoriteTitleSerializer,
	PasswordTokenSerializer,
	ProfileUpdateSerializer,
	RegisterSerializer,
	SubscriptionRequestCreateSerializer,
	SubscriptionRequestSerializer,
	SupportMessageSerializer,
	TelegramMiniAppSerializer,
	TelegramWidgetSerializer,
	UserSettingsSerializer,
)
from .support import TOO_SOON, EMPTY, send_support_message_sync
from .telegram_auth import (
	create_telegram_tokens,
	get_or_create_telegram_user,
	link_mini_app_user,
	parse_mini_app_init_data,
	verify_login_widget_payload,
)


@extend_schema(tags=["Authentication"])
class RegisterView(generics.CreateAPIView):
	queryset = get_user_model().objects.all()
	serializer_class = RegisterSerializer
	permission_classes = [AllowAny]


@extend_schema(tags=["Authentication"])
class PasswordTokenView(TokenObtainPairView):
	serializer_class = PasswordTokenSerializer
	permission_classes = [AllowAny]


@extend_schema(tags=["Authentication"])
class PasswordTokenRefreshView(TokenRefreshView):
	permission_classes = [AllowAny]


@extend_schema(tags=["Authentication"])
class CurrentUserView(generics.RetrieveUpdateAPIView):
	serializer_class = CurrentUserSerializer
	permission_classes = [IsAuthenticated]

	def get_serializer_class(self):
		if self.request.method in {"PUT", "PATCH"}:
			return ProfileUpdateSerializer
		return CurrentUserSerializer

	def get_object(self):
		return self.request.user

	def update(self, request, *args, **kwargs):
		response = super().update(request, *args, **kwargs)
		response.data = CurrentUserSerializer(self.get_object()).data
		return response


@extend_schema(responses=OpenApiTypes.OBJECT, tags=["Profile"])
class TelegramLinkView(APIView):
	"""Whether this account's Telegram profile is linked, plus the deep link.

	The AI assistant's «Telegramga ulash» card polls this while the user
	presses the deep link in Telegram (the bot confirms the link there). ``url``
	is empty unless ``BOT_USERNAME`` is configured — the frontend then falls
	back to its own bot handle.
	"""

	permission_classes = [IsAuthenticated]

	def get(self, request):
		user = request.user
		profile = getattr(user, "telegram_profile", None)
		bot_username = str(getattr(settings, "BOT_USERNAME", "") or "").lstrip("@")
		url = ""
		if bot_username and user.username:
			url = f"https://t.me/{bot_username}?start={user.username}"
		return Response({
			"linked": profile is not None,
			"username": getattr(profile, "username", "") if profile else "",
			"url": url,
		})


class FavoritePagination(PageNumberPagination):
	page_size = 10


@extend_schema(tags=["Authentication"])
class FavoriteListView(generics.ListAPIView):
	serializer_class = FavoriteTitleSerializer
	permission_classes = [IsAuthenticated]
	pagination_class = FavoritePagination

	def get_queryset(self):
		profile = getattr(self.request.user, "telegram_profile", None)
		if profile is None:
			return MediaTitle.objects.none()

		queryset = MediaTitle.objects.filter(user_favorites__user=profile).order_by(
			"-user_favorites__created_at",
		).distinct()
		media_type = self.request.query_params.get("type")
		search = self.request.query_params.get("search", "").strip()
		if media_type in MediaTitle.MediaType.values:
			queryset = queryset.filter(type=media_type)
		if search:
			queryset = queryset.filter(title__icontains=search)
		return queryset


@extend_schema(tags=["Authentication"])
class FavoriteToggleView(APIView):
	"""Add/remove a catalog title from the caller's favourites (by slug)."""

	permission_classes = [IsAuthenticated]

	def post(self, request, slug: str = ""):
		profile = getattr(request.user, "telegram_profile", None)
		if profile is None:
			return Response({"detail": "Telegram profil bog'lanmagan."}, status=400)

		slug = (slug or request.data.get("slug") or "").strip()
		if not slug:
			return Response({"detail": "slug majburiy."}, status=400)

		title = get_object_or_404(MediaTitle, slug=slug)
		link = FavoriteContent.objects.filter(user=profile, content=title).first()
		if link is not None:
			link.delete()
			is_favorite = False
		else:
			FavoriteContent.objects.create(user=profile, content=title)
			is_favorite = True
		return Response({"slug": slug, "is_favorite": is_favorite})


@extend_schema(tags=["Authentication"])
class TelegramMiniAppLoginView(generics.GenericAPIView):
	serializer_class = TelegramMiniAppSerializer
	permission_classes = [AllowAny]

	def post(self, request, *args, **kwargs):
		serializer = self.get_serializer(data=request.data)
		serializer.is_valid(raise_exception=True)
		telegram_data = parse_mini_app_init_data(serializer.validated_data["init_data"])
		profile = link_mini_app_user(
			telegram_data,
			email=serializer.validated_data.get("email", ""),
			password=serializer.validated_data["password"],
		)
		return Response({
			**create_telegram_tokens(profile, "telegram_mini_app"),
			"user": CurrentUserSerializer(profile.auth_user).data,
		})


@extend_schema(tags=["Authentication"])
class TelegramWidgetLoginView(generics.GenericAPIView):
	serializer_class = TelegramWidgetSerializer
	permission_classes = [AllowAny]

	def post(self, request, *args, **kwargs):
		serializer = self.get_serializer(data=request.data)
		serializer.is_valid(raise_exception=True)
		telegram_data = verify_login_widget_payload(serializer.validated_data)
		profile = get_or_create_telegram_user(telegram_data)
		return Response({
			**create_telegram_tokens(profile, "telegram_widget"),
			"user": CurrentUserSerializer(profile.auth_user).data,
		})


@extend_schema(tags=["Subscription"])
class SubscriptionPlansView(APIView):
	permission_classes = [IsAuthenticated]

	def get(self, request):
		from .plans import all_plan_details, card_number

		subscription = getattr(request.user, "subscription", None)
		current = (subscription.plan if subscription else "free") or "free"
		pending = (
			SubscriptionRequest.objects.filter(
				user=request.user,
				status=SubscriptionRequest.Status.PENDING,
			)
			.order_by("-created_at")
			.first()
		)
		from .reminders import reminder_payload

		return Response({
			"current_plan": current,
			"current_active": bool(subscription and subscription.is_active),
			"expires_at": subscription.expires_at if subscription and subscription.is_active else None,
			"card_number": card_number(),
			"plans": all_plan_details(),
			"pending_request": SubscriptionRequestSerializer(pending).data if pending else None,
			# The same rule the bot's cron reminders use, so the panel never
			# promises something the Telegram message would not.
			"reminder": reminder_payload(subscription),
		})


@extend_schema(tags=["Subscription"])
class SubscriptionCardView(APIView):
	permission_classes = [IsAuthenticated]

	def get(self, request):
		return Response({"card_number": getattr(settings, "SUBSCRIPTION_CARD_NUMBER", "")})


@extend_schema(tags=["Subscription"])
class SubscriptionCreateView(generics.CreateAPIView):
	serializer_class = SubscriptionRequestCreateSerializer
	permission_classes = [IsAuthenticated]

	def create(self, request, *args, **kwargs):
		serializer = self.get_serializer(data=request.data)
		serializer.is_valid(raise_exception=True)
		plan = serializer.validated_data["plan"]
		subscription = getattr(request.user, "subscription", None)
		current_plan = (subscription.plan if subscription else "free") or "free"
		if plan == current_plan and subscription is not None and subscription.is_active:
			return Response(
				{"detail": "Bu tarif allaqachon sizniki."},
				status=status.HTTP_400_BAD_REQUEST,
			)
		pending = SubscriptionRequest.objects.filter(
			user=request.user,
			plan=plan,
			status=SubscriptionRequest.Status.PENDING,
		).exists()
		if pending:
			return Response(
				{"detail": "Bu tarif uchun arizangiz allaqachon ko'rib chiqilmoqda."},
				status=status.HTTP_400_BAD_REQUEST,
			)
		from .plans import plan_price

		instance = SubscriptionRequest.objects.create(
			user=request.user,
			plan=plan,
			amount=plan_price(plan),
			card_number=getattr(settings, "SUBSCRIPTION_CARD_NUMBER", ""),
			screenshot=serializer.validated_data["screenshot"],
			status=SubscriptionRequest.Status.PENDING,
		)
		from .telegram_notify import notify_admins_new_request

		notify_admins_new_request(instance)
		return Response(
			SubscriptionRequestSerializer(instance).data,
			status=status.HTTP_201_CREATED,
		)


PROFILE_ACTIVITY_LIMIT = 30

SUBSCRIPTION_STATUS_LABELS = {
	SubscriptionRequest.Status.PENDING: "Ariza ko'rib chiqilmoqda",
	SubscriptionRequest.Status.APPROVED: "To'lov tasdiqlandi",
	SubscriptionRequest.Status.REJECTED: "Ariza rad etildi",
	SubscriptionRequest.Status.CANCELLED: "Ariza bekor qilindi",
}


def _plan_label(plan: str) -> str:
	return dict(Subscription.Plan.choices).get(plan, str(plan or "").title())


def _subscription_summary(user) -> dict:
	"""Plan, expiry and payment totals for the profile pages.

	Every duration plan stores its own window on ``Subscription.expires_at``,
	which is (re)written whenever a request is approved or an admin changes the
	plan. Renewals extend a still running window instead of overwriting it.
	"""
	from .plans import plan_days

	subscription = getattr(user, "subscription", None)
	plan = (subscription.plan if subscription else Subscription.Plan.FREE) or Subscription.Plan.FREE
	started_at = subscription.started_at if subscription else None
	expires_at = subscription.expires_at if subscription else None
	now = timezone.now()
	days_left = None
	if expires_at is not None:
		days_left = max(0, math.ceil((expires_at - now).total_seconds() / 86400))
	period_days = plan_days(plan)
	if plan == Subscription.Plan.COUPON and started_at and expires_at:
		# A coupon matches no catalogue duration, so report the stored window.
		period_days = max(0, round((expires_at - started_at).total_seconds() / 86400))
	# A coupon is a paid tier even though no catalogue plan describes it.
	is_paid = bool(subscription and plan != Subscription.Plan.FREE)
	approved = SubscriptionRequest.objects.filter(
		user=user,
		status=SubscriptionRequest.Status.APPROVED,
	).order_by("-updated_at", "-id")
	last_payment = approved.first()
	return {
		"plan": plan,
		"plan_label": _plan_label(plan),
		"is_paid": is_paid,
		"is_active": is_paid and expires_at is not None and expires_at >= now,
		"period_days": period_days,
		"started_at": started_at,
		"expires_at": expires_at,
		"days_left": days_left,
		"expires_soon": is_paid and days_left is not None and days_left <= 7,
		"last_amount": last_payment.amount if last_payment else None,
		"total_paid": approved.aggregate(total=Sum("amount"))["total"] or 0,
		"payments_count": approved.count(),
	}


def _telegram_payload(user) -> dict:
	profile = getattr(user, "telegram_profile", None)
	if profile is None:
		return {"linked": False}
	full_name = " ".join(
		part for part in [profile.first_name, profile.last_name] if part
	).strip()
	return {
		"linked": True,
		"telegram_id": profile.telegram_id,
		"username": profile.username,
		"first_name": profile.first_name,
		"last_name": profile.last_name,
		"full_name": full_name,
		"language_code": profile.language_code,
		"is_blocked": profile.is_blocked,
		"joined_at": profile.created_at,
		"last_seen_at": profile.last_seen_at,
	}


def _profile_stats(user, profile) -> dict:
	return {
		"favorites": FavoriteContent.objects.filter(user=profile).count() if profile else 0,
		"views": MediaView.objects.filter(user=user).count(),
		"reading": ReadingProgress.objects.filter(user=user).count(),
		"requests": SubscriptionRequest.objects.filter(user=user).count(),
	}


def _activity_feed(user, limit: int = PROFILE_ACTIVITY_LIMIT) -> list:
	"""Merge favourites, watch/read activity and payment events newest first."""
	events = []
	profile = getattr(user, "telegram_profile", None)
	if profile is not None:
		favorites = (
			FavoriteContent.objects.filter(user=profile)
			.select_related("content")
			.order_by("-created_at")[:limit]
		)
		for favorite in favorites:
			events.append({
				"kind": "favorite",
				"at": favorite.created_at,
				"label": "Sevimlilarga qo'shildi",
				"icon": "bi-heart-fill",
				"title": favorite.content.title,
				"slug": favorite.content.slug,
				"type": favorite.content.type,
				"detail": "",
				"amount": None,
			})

	views = MediaView.objects.filter(user=user).select_related("title", "part")[:limit]
	for view in views:
		part = view.part if view.part_id else None
		is_manga = view.title.type == MediaTitle.MediaType.MANGA
		where = "Botda" if view.source == MediaView.Source.BOT else "Saytda"
		events.append({
			"kind": "read" if is_manga else "watch",
			"at": view.updated_at,
			"label": f"{where} " + ("o'qildi" if is_manga else "tomosha qilindi"),
			"icon": "bi-book-half" if is_manga else "bi-play-circle-fill",
			"title": view.title.title,
			"slug": view.title.slug,
			"type": view.title.type,
			"detail": f"{part.number}-qism" if part else "",
			"amount": None,
		})

	requests = SubscriptionRequest.objects.filter(user=user).order_by("-updated_at", "-id")[:limit]
	for request in requests:
		events.append({
			"kind": "subscription",
			"at": request.updated_at,
			"label": SUBSCRIPTION_STATUS_LABELS.get(request.status, request.status),
			"icon": "bi-ticket-perforated",
			"title": f"{_plan_label(request.plan)} tarifi",
			"slug": "",
			"type": "subscription",
			"detail": request.get_status_display(),
			"amount": request.amount,
		})

	events.sort(key=lambda event: event["at"], reverse=True)
	return events[:limit]


def _view_payload(view: MediaView) -> dict:
	"""Catalog fields plus the activity metadata the profile pages show."""
	payload = dict(MediaTitleSerializer(view.title).data)
	part = view.part if view.part_id else None
	payload.update(
		{
			"view_id": view.pk,
			"kind": "read" if view.title.type == MediaTitle.MediaType.MANGA else "watch",
			"source": view.source,
			"part_id": part.pk if part else None,
			"part_number": part.number if part else None,
			"season_number": part.season_number if part else None,
			"part_title": part.title if part else "",
			"viewed_at": view.updated_at,
			"view_count": view.count,
		}
	)
	return payload


@extend_schema(responses=OpenApiTypes.OBJECT, tags=["Profile"])
class ProfileOverviewView(APIView):
	permission_classes = [IsAuthenticated]

	def get(self, request):
		user = request.user
		profile = getattr(user, "telegram_profile", None)
		from .premium import is_premium_user

		return Response(
			{
				"account": {
					"id": user.pk,
					"username": user.username,
					"email": user.email,
					"first_name": user.first_name,
					"last_name": user.last_name,
					"is_staff": user.is_staff,
					"is_premium": is_premium_user(user),
					"joined_at": user.date_joined,
					"last_login": user.last_login,
				},
				"telegram": _telegram_payload(user),
				"stats": _profile_stats(user, profile),
				"subscription": _subscription_summary(user),
				"recent_activity": _activity_feed(user, limit=5),
			}
		)


@extend_schema(responses=OpenApiTypes.OBJECT, tags=["Profile"])
class ProfileActivityView(APIView):
	permission_classes = [IsAuthenticated]

	def get(self, request):
		return Response({"count": PROFILE_ACTIVITY_LIMIT, "results": _activity_feed(request.user)})


class ProfileHistoryPagination(PageNumberPagination):
	page_size = 12


@extend_schema(responses=OpenApiTypes.OBJECT, tags=["Profile"])
class ProfileHistoryView(APIView):
	permission_classes = [IsAuthenticated]

	def get(self, request):
		queryset = MediaView.objects.filter(user=request.user).select_related("title", "part")
		paginator = ProfileHistoryPagination()
		page = paginator.paginate_queryset(queryset, request, view=self)
		return paginator.get_paginated_response([_view_payload(view) for view in page])


@extend_schema(responses=OpenApiTypes.OBJECT, tags=["Profile"])
class ProfileSubscriptionView(APIView):
	permission_classes = [IsAuthenticated]

	def get(self, request):
		requests = SubscriptionRequest.objects.filter(user=request.user).order_by("-created_at")
		return Response(
			{
				"summary": _subscription_summary(request.user),
				"requests": SubscriptionRequestSerializer(
					requests, many=True, context={"request": request}
				).data,
			}
		)


@extend_schema(request=UserSettingsSerializer, responses=UserSettingsSerializer, tags=["Profile"])
class UserSettingsView(APIView):
	permission_classes = [IsAuthenticated]

	def get_settings(self, user) -> UserSettings:
		settings_object, _ = UserSettings.objects.get_or_create(user=user)
		return settings_object

	def get(self, request):
		return Response(
			UserSettingsSerializer(
				self.get_settings(request.user), context={"request": request}
			).data
		)

	def patch(self, request):
		serializer = UserSettingsSerializer(
			self.get_settings(request.user),
			data=request.data,
			partial=True,
			context={"request": request},
		)
		serializer.is_valid(raise_exception=True)
		serializer.save()
		return Response(serializer.data)


@extend_schema(request=SupportMessageSerializer, tags=["Support"])
class SupportMessageView(APIView):
	"""(POST) Send a message from the website to the administrators.

	The row is stored first and delivered second, so a Telegram outage never
	loses what the user wrote: ``delivered`` tells the panel whether the message
	actually reached an administrator.
	"""

	permission_classes = [IsAuthenticated]

	def post(self, request):
		serializer = SupportMessageSerializer(data=request.data)
		serializer.is_valid(raise_exception=True)
		result = send_support_message_sync(
			request.user,
			serializer.validated_data["text"],
			source=SupportMessage.Source.WEB,
		)
		if result.status == EMPTY:
			return Response(
				{"detail": "Xabar matni bo'sh bo'lmasligi kerak."},
				status=status.HTTP_400_BAD_REQUEST,
			)
		if result.status == TOO_SOON:
			return Response(
				{
					"detail": (
						"Oldingi xabaringiz yuborilgan. Iltimos, bir daqiqadan so'ng "
						"qayta yuboring."
					),
					"retry_after": result.retry_after,
				},
				status=status.HTTP_429_TOO_MANY_REQUESTS,
			)
		return Response(
			{
				"id": result.message.pk,
				"status": result.message.status,
				"delivered": result.delivered,
				"detail": (
					"Xabaringiz administratorlarga yuborildi."
					if result.delivered
					else "Xabar saqlandi, lekin hozircha yuborilmadi. Keyinroq urinib ko'ring."
				),
			},
			status=status.HTTP_201_CREATED,
		)


@extend_schema(tags=["Subscription"])
class SubscriptionRequestDetailView(generics.RetrieveAPIView):
	serializer_class = SubscriptionRequestSerializer
	permission_classes = [IsAuthenticated]
	queryset = SubscriptionRequest.objects.all()

	def get_object(self):
		return get_object_or_404(
			SubscriptionRequest,
			pk=self.kwargs["pk"],
			user=self.request.user,
		)
