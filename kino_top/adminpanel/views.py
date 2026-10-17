from datetime import timedelta

from django.conf import settings
from django.db.models import Count, F, Q, Sum
from django.shortcuts import get_object_or_404
from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework import generics, status, viewsets
from rest_framework.decorators import action
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from bot.models import BotLogEntry, BotSettings, Broadcast
from games.models import AnimeVerification, MonthlyPrize, QuizAttempt, QuizQuestion
from movies.models import Genre, MediaPart, MediaTitle, TelegramChannel, TelegramMedia
from users.models import Coupon, Subscription, SubscriptionRequest, TelegramUser
from users.plans import PLAN_ORDER, plan_price

from .broadcast_runner import start_broadcast_async
from .coupon_publisher import maybe_auto_publish_coupon, publish_coupon_to_channel
from .models import Income
from .permissions import IsStaffAdmin
from .serializers import (
	AdminUserDetailSerializer,
	AdminUserSerializer,
	AnimeVerificationAdminSerializer,
	BotLogAdminSerializer,
	BotSettingsSerializer,
	BroadcastAdminSerializer,
	BroadcastCreateSerializer,
	CouponAdminSerializer,
	CouponRedemptionAdminSerializer,
	CouponWriteSerializer,
	GenreAdminSerializer,
	IncomeSerializer,
	MonthlyPrizeAdminSerializer,
	QuizAttemptAdminSerializer,
	QuizQuestionAdminSerializer,
	SubscriptionRequestAdminSerializer,
	UserBlockSerializer,
	UserPlanUpdateSerializer,
)


class AdminPagination(PageNumberPagination):
	page_size = 20
	page_size_query_param = "page_size"
	max_page_size = 100


@extend_schema(tags=["Admin"])
class AdminDashboardView(APIView):
	permission_classes = [IsStaffAdmin]

	def get(self, request):
		now = timezone.now()
		month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
		days_30 = now - timedelta(days=30)

		income_month = Income.objects.filter(paid_at__gte=month_start).aggregate(
			total=Sum("amount"), count=Count("id")
		)
		income_total = Income.objects.aggregate(total=Sum("amount"), count=Count("id"))
		income_by_source = dict(
			Income.objects.filter(paid_at__gte=month_start)
			.values_list("source")
			.annotate(total=Sum("amount"))
			.values_list("source", "total")
		)

		pending_requests = SubscriptionRequest.objects.filter(
			status=SubscriptionRequest.Status.PENDING,
		).count()

		return Response({
			"users": {
				"total": TelegramUser.objects.count(),
				"active_30d": TelegramUser.objects.filter(
					is_blocked=False,
				).filter(
					Q(last_seen_at__gte=days_30) | Q(created_at__gte=days_30)
				).count(),
				"blocked": TelegramUser.objects.filter(is_blocked=True).count(),
			},
			"media": {
				"titles": MediaTitle.objects.count(),
				"parts": MediaPart.objects.count(),
				"files": TelegramMedia.objects.count(),
				"genres": Genre.objects.count(),
				"by_type": dict(
					MediaTitle.objects.values_list("type")
					.annotate(total=Count("id"))
					.values_list("type", "total")
				),
			},
			"channels": {
				"total": TelegramChannel.objects.count(),
				"active": TelegramChannel.objects.filter(is_active=True).count(),
			},
			"income": {
				"month_total": income_month["total"] or 0,
				"month_count": income_month["count"] or 0,
				"all_time_total": income_total["total"] or 0,
				"all_time_count": income_total["count"] or 0,
				"by_source": income_by_source,
			},
			"subscriptions": {
				"pending": pending_requests,
				"approved": SubscriptionRequest.objects.filter(
					status=SubscriptionRequest.Status.APPROVED,
				).count(),
				"rejected": SubscriptionRequest.objects.filter(
					status=SubscriptionRequest.Status.REJECTED,
				).count(),
				"active": Subscription.objects.exclude(plan="free")
				.filter(expires_at__gte=now)
				.count(),
				"by_plan": {
					plan: Subscription.objects.filter(plan=plan).count()
					for plan in PLAN_ORDER
				},
			},
			"broadcasts": {
				"total": Broadcast.objects.count(),
				"running": Broadcast.objects.filter(status=Broadcast.Status.RUNNING).count(),
				"sent_30d": Broadcast.objects.filter(created_at__gte=days_30).count(),
			},
			"prices": {plan: plan_price(plan) for plan in PLAN_ORDER},
		})


@extend_schema(tags=["Admin"])
class AdminUserViewSet(viewsets.ReadOnlyModelViewSet):
	queryset = TelegramUser.objects.select_related("auth_user", "auth_user__subscription")
	serializer_class = AdminUserSerializer
	permission_classes = [IsStaffAdmin]
	pagination_class = AdminPagination

	def get_serializer_class(self):
		if self.action == "retrieve":
			return AdminUserDetailSerializer
		return AdminUserSerializer

	def get_queryset(self):
		queryset = super().get_queryset()
		search = self.request.query_params.get("search", "").strip()
		plan = self.request.query_params.get("plan", "").strip()
		blocked = self.request.query_params.get("blocked", "").strip()
		if search:
			queryset = queryset.filter(
				Q(username__icontains=search)
				| Q(first_name__icontains=search)
				| Q(last_name__icontains=search)
				| Q(telegram_id__icontains=search)
			)
		if plan in Subscription.Plan.values:
			queryset = queryset.filter(auth_user__subscription__plan=plan)
		if blocked in {"1", "true", "True"}:
			queryset = queryset.filter(is_blocked=True)
		elif blocked in {"0", "false", "False"}:
			queryset = queryset.filter(is_blocked=False)
		return queryset

	@extend_schema(request=UserPlanUpdateSerializer, tags=["Admin"])
	@action(detail=True, methods=["post"], url_path="plan")
	def set_plan(self, request, pk=None):
		serializer = UserPlanUpdateSerializer(data=request.data)
		serializer.is_valid(raise_exception=True)
		profile = self.get_object()
		if not profile.auth_user:
			return Response(
				{"detail": "Bu Telegram profili sayt hisobiga ulanmagan."},
				status=status.HTTP_400_BAD_REQUEST,
			)
		subscription, _ = Subscription.objects.get_or_create(user=profile.auth_user)
		subscription.activate(serializer.validated_data["plan"])
		return Response({
			"status": "ok",
			"plan": subscription.plan,
			"expires_at": subscription.expires_at,
		})

	@extend_schema(request=UserBlockSerializer, tags=["Admin"])
	@action(detail=True, methods=["post"], url_path="block")
	def set_block(self, request, pk=None):
		serializer = UserBlockSerializer(data=request.data)
		serializer.is_valid(raise_exception=True)
		profile = self.get_object()
		profile.is_blocked = serializer.validated_data["is_blocked"]
		profile.save(update_fields=["is_blocked", "updated_at"])
		return Response({"status": "ok", "is_blocked": profile.is_blocked})


@extend_schema(tags=["Admin"])
class AdminSubscriptionRequestViewSet(viewsets.ReadOnlyModelViewSet):
	queryset = SubscriptionRequest.objects.select_related("user", "user__telegram_profile")
	serializer_class = SubscriptionRequestAdminSerializer
	permission_classes = [IsStaffAdmin]
	pagination_class = AdminPagination

	def get_queryset(self):
		queryset = super().get_queryset()
		req_status = self.request.query_params.get("status", "").strip()
		if req_status in SubscriptionRequest.Status.values:
			queryset = queryset.filter(status=req_status)
		return queryset

	def _process(self, request, pk, new_status):
		req = get_object_or_404(SubscriptionRequest, pk=pk)
		if req.status != SubscriptionRequest.Status.PENDING:
			return Response(
				{"detail": f"Bu ariza allaqachon {req.get_status_display()}."},
				status=status.HTTP_400_BAD_REQUEST,
			)
		req.status = new_status
		req.processed_by = request.user
		req.notes = str(request.data.get("notes") or req.notes or "")
		req.save(update_fields=["status", "processed_by", "notes", "updated_at"])
		if new_status == SubscriptionRequest.Status.APPROVED and req.user:
			subscription, _ = Subscription.objects.get_or_create(user=req.user)
			subscription.activate(req.plan)
		return Response(SubscriptionRequestAdminSerializer(req, context={"request": request}).data)

	@extend_schema(request=None, tags=["Admin"])
	@action(detail=True, methods=["post"])
	def approve(self, request, pk=None):
		return self._process(request, pk, SubscriptionRequest.Status.APPROVED)

	@extend_schema(request=None, tags=["Admin"])
	@action(detail=True, methods=["post"])
	def reject(self, request, pk=None):
		return self._process(request, pk, SubscriptionRequest.Status.REJECTED)


@extend_schema(tags=["Admin"])
class AdminIncomeViewSet(viewsets.ModelViewSet):
	queryset = Income.objects.all()
	serializer_class = IncomeSerializer
	permission_classes = [IsStaffAdmin]
	pagination_class = AdminPagination

	def get_queryset(self):
		queryset = super().get_queryset()
		month = self.request.query_params.get("month", "").strip()
		if month:
			queryset = queryset.filter(paid_at__year=month[:4], paid_at__month=month[5:7])
		source = self.request.query_params.get("source", "").strip()
		if source in Income.Source.values:
			queryset = queryset.filter(source=source)
		return queryset

	def perform_create(self, serializer):
		serializer.save(created_by=self.request.user)

	@extend_schema(tags=["Admin"])
	@action(detail=False, methods=["get"])
	def monthly(self, request):
		"""Oylik tushumlar hisoboti: yil bo'ylab o'rtacha va jami."""
		now = timezone.now()
		try:
			year = int(request.query_params.get("year", now.year))
		except (TypeError, ValueError):
			year = now.year
		rows = (
			Income.objects.filter(paid_at__year=year)
			.values("paid_at__month")
			.annotate(total=Sum("amount"), count=Count("id"))
			.order_by("paid_at__month")
		)
		months = {row["paid_at__month"]: row for row in rows}
		series = []
		for month in range(1, 13):
			row = months.get(month)
			series.append({
				"month": month,
				"label": f"{year}-{month:02d}",
				"total": row["total"] if row else 0,
				"count": row["count"] if row else 0,
			})
		total = sum(item["total"] or 0 for item in series)
		filled = [item for item in series if item["count"]]
		average = (total / len(filled)) if filled else 0
		return Response({
			"year": year,
			"total": total,
			"average_monthly": average,
			"months": series,
		})


@extend_schema(tags=["Admin"])
class AdminGenreViewSet(viewsets.ModelViewSet):
	queryset = Genre.objects.all()
	serializer_class = GenreAdminSerializer
	permission_classes = [IsStaffAdmin]
	pagination_class = AdminPagination

	def get_queryset(self):
		queryset = super().get_queryset()
		search = self.request.query_params.get("search", "").strip()
		if search:
			queryset = queryset.filter(name__icontains=search)
		return queryset


@extend_schema(tags=["Admin"])
class AdminCouponViewSet(viewsets.ModelViewSet):
	"""Kuponlar (promo kodlar) CRUD + e'lonni kanalga joylash."""

	queryset = Coupon.objects.select_related("created_by", "posted_channel")
	serializer_class = CouponAdminSerializer
	permission_classes = [IsStaffAdmin]
	pagination_class = AdminPagination

	def get_serializer_class(self):
		if self.action in {"create", "update", "partial_update"}:
			return CouponWriteSerializer
		return CouponAdminSerializer

	def get_queryset(self):
		queryset = super().get_queryset()
		search = self.request.query_params.get("search", "").strip()
		if search:
			queryset = queryset.filter(code__icontains=search)
		status_filter = self.request.query_params.get("status", "").strip()
		if status_filter == "active":
			queryset = queryset.filter(is_active=True, used_count__lt=F("max_uses"))
		elif status_filter == "exhausted":
			queryset = queryset.filter(used_count__gte=F("max_uses"))
		elif status_filter == "stopped":
			queryset = queryset.filter(is_active=False)
		return queryset

	def _payload(self, coupon) -> dict:
		return CouponAdminSerializer(coupon, context=self.get_serializer_context()).data

	def create(self, request, *args, **kwargs):
		serializer = self.get_serializer(data=request.data)
		serializer.is_valid(raise_exception=True)
		coupon = serializer.save()
		# Post the promotion to the public channel right away when the
		# administrator enabled auto-publishing (never fails the request).
		maybe_auto_publish_coupon(coupon.pk)
		coupon.refresh_from_db()
		return Response(self._payload(coupon), status=status.HTTP_201_CREATED)

	def update(self, request, *args, **kwargs):
		partial = kwargs.pop("partial", False)
		coupon = self.get_object()
		serializer = self.get_serializer(coupon, data=request.data, partial=partial)
		serializer.is_valid(raise_exception=True)
		serializer.save()
		return Response(self._payload(coupon))

	@extend_schema(request=None, tags=["Admin"])
	@action(detail=True, methods=["post"])
	def toggle(self, request, pk=None):
		"""Kuponni to'xtatish yoki qayta faollashtirish."""
		coupon = self.get_object()
		coupon.is_active = not coupon.is_active
		coupon.save(update_fields=["is_active", "updated_at"])
		return Response(self._payload(coupon))

	@extend_schema(request=None, tags=["Admin"])
	@action(detail=True, methods=["post"])
	def publish(self, request, pk=None):
		"""Kupon e'lonini tanlangan ommaviy kanalga joylash."""
		coupon = self.get_object()
		message_id, error = publish_coupon_to_channel(coupon.pk)
		if message_id is None:
			return Response({"detail": error}, status=status.HTTP_400_BAD_REQUEST)
		coupon.refresh_from_db()
		return Response({
			"detail": "Kupon kanalga joylandi.",
			"message_id": message_id,
			"coupon": self._payload(coupon),
		})

	@extend_schema(tags=["Admin"])
	@action(detail=True, methods=["get"])
	def redemptions(self, request, pk=None):
		"""Kuponni ishlatgan oxirgi foydalanuvchilar."""
		coupon = self.get_object()
		rows = coupon.redemptions.select_related("user").order_by("-created_at")[:100]
		return Response(CouponRedemptionAdminSerializer(rows, many=True).data)


@extend_schema(tags=["Admin"])
class AdminMediaStatsView(APIView):
	permission_classes = [IsStaffAdmin]

	def get(self, request):
		titles = MediaTitle.objects.prefetch_related("parts", "genres").order_by("-created_at")
		search = request.query_params.get("search", "").strip()
		media_type = request.query_params.get("type", "").strip()
		if search:
			titles = titles.filter(
				Q(title__icontains=search) | Q(code__icontains=search)
			)
		if media_type in MediaTitle.MediaType.values:
			titles = titles.filter(type=media_type)
		return Response({
			"count": titles.count(),
			"types": dict(
				MediaTitle.objects.values_list("type")
				.annotate(total=Count("id"))
				.values_list("type", "total")
			),
		})


@extend_schema(tags=["Admin"])
class AdminBroadcastViewSet(viewsets.ModelViewSet):
	queryset = Broadcast.objects.all()
	permission_classes = [IsStaffAdmin]
	pagination_class = AdminPagination

	def get_serializer_class(self):
		if self.action == "create":
			return BroadcastCreateSerializer
		return BroadcastAdminSerializer

	def get_queryset(self):
		queryset = super().get_queryset()
		broadcast_status = self.request.query_params.get("status", "").strip()
		if broadcast_status in Broadcast.Status.values:
			queryset = queryset.filter(status=broadcast_status)
		return queryset

	def perform_create(self, serializer):
		serializer.save(admin_telegram_id=self.request.user.id or 0)

	@extend_schema(request=None, tags=["Admin"])
	@action(detail=True, methods=["post"])
	def start(self, request, pk=None):
		broadcast = self.get_object()
		if broadcast.status == Broadcast.Status.COMPLETED:
			return Response({"detail": "Yakunlangan broadcastni qayta bo'lmaydi."}, status=400)
		if broadcast.status == Broadcast.Status.RUNNING:
			return Response({"detail": "Broadcast allaqachon ishlayapti."}, status=400)
		error = start_broadcast_async(broadcast.pk)
		if error:
			return Response({"detail": error}, status=400)
		broadcast.refresh_from_db()
		return Response(BroadcastAdminSerializer(broadcast).data)

	@extend_schema(request=None, tags=["Admin"])
	@action(detail=True, methods=["post"])
	def cancel(self, request, pk=None):
		from bot.services.broadcast import request_cancel_sync

		broadcast = self.get_object()
		request_cancel_sync(broadcast.pk)
		broadcast.refresh_from_db()
		return Response(BroadcastAdminSerializer(broadcast).data)


@extend_schema(tags=["Admin"])
class AdminPodcastSendView(APIView):
	"""Audio (podcast) broadcast yaratish va yuborish."""

	permission_classes = [IsStaffAdmin]

	def post(self, request):
		serializer = BroadcastCreateSerializer(data={
			**{k: request.data.get(k) for k in (
				"caption", "disable_notification", "protect_content", "include_blocked",
			)},
			"kind": Broadcast.Kind.AUDIO,
			"text": request.data.get("text", ""),
			"file_id": request.data.get("file_id", ""),
		})
		serializer.is_valid(raise_exception=True)
		broadcast = serializer.save(admin_telegram_id=request.user.id or 0)
		if request.data.get("send_now", True):
			error = start_broadcast_async(broadcast.pk)
			if error:
				return Response({"detail": error, "broadcast": BroadcastAdminSerializer(broadcast).data}, status=400)
		broadcast.refresh_from_db()
		return Response(
			BroadcastAdminSerializer(broadcast).data,
			status=status.HTTP_201_CREATED,
		)


@extend_schema(tags=["Admin"])
class AdminBotSettingsView(APIView):
	permission_classes = [IsStaffAdmin]

	def get(self, request):
		return Response(BotSettingsSerializer(BotSettings.get_solo()).data)

	def patch(self, request):
		settings_obj = BotSettings.get_solo()
		serializer = BotSettingsSerializer(settings_obj, data=request.data, partial=True)
		serializer.is_valid(raise_exception=True)
		serializer.save()
		return Response(BotSettingsSerializer(settings_obj).data)


@extend_schema(tags=["Admin"])
class AdminLogListView(generics.ListAPIView):
	serializer_class = BotLogAdminSerializer
	permission_classes = [IsStaffAdmin]
	pagination_class = AdminPagination

	def get_queryset(self):
		queryset = BotLogEntry.objects.all()
		level = self.request.query_params.get("level", "").strip()
		if level:
			queryset = queryset.filter(level=level)
		return queryset


# ---------------------------------------------------------------------------
# Games: quiz questions, leaderboard, attempts, verifications, monthly prizes
# ---------------------------------------------------------------------------


@extend_schema(tags=["Admin"])
class AdminQuizQuestionViewSet(viewsets.ModelViewSet):
	"""Quiz savollarini to'liq boshqarish (CRUD)."""

	queryset = QuizQuestion.objects.select_related("title")
	serializer_class = QuizQuestionAdminSerializer
	permission_classes = [IsStaffAdmin]
	pagination_class = AdminPagination

	def get_queryset(self):
		queryset = super().get_queryset()
		search = self.request.query_params.get("search", "").strip()
		if search:
			queryset = queryset.filter(Q(text__icontains=search) | Q(title__title__icontains=search))
		title_id = self.request.query_params.get("title", "").strip()
		if title_id.isdigit():
			queryset = queryset.filter(title_id=int(title_id))
		is_active = self.request.query_params.get("is_active", "").strip()
		if is_active == "1":
			queryset = queryset.filter(is_active=True)
		elif is_active == "0":
			queryset = queryset.filter(is_active=False)
		return queryset


@extend_schema(tags=["Admin"])
class AdminGameLeaderboardView(APIView):
	"""O'yin reytingi: barcha o'yinchilarning ballari va darajalari."""

	permission_classes = [IsStaffAdmin]

	def get(self, request):
		from django.contrib.auth import get_user_model

		from games.services import level_for, user_points

		rows = (
			QuizAttempt.objects.filter(is_suspicious=False, finished_at__isnull=False)
			.values("user_id")
			.annotate(points=Sum("points_awarded"), attempts=Count("id"))
			.order_by("-points", "user_id")
		)
		limit = min(max(int(request.query_params.get("limit", 100) or 100), 1), 500)
		results = []
		for index, row in enumerate(rows[:limit], start=1):
			profile = get_user_model().objects.filter(pk=row["user_id"]).select_related("telegram_profile").first()
			name = ""
			telegram_id = None
			if profile is not None:
				telegram = getattr(profile, "telegram_profile", None)
				telegram_id = getattr(telegram, "telegram_id", None)
				name = (
					getattr(telegram, "first_name", "")
					or getattr(profile, "username", "")
					or str(row["user_id"])
				)
			verified = AnimeVerification.objects.filter(user_id=row["user_id"]).count()
			level = level_for(int(row["points"] or 0))
			results.append({
				"rank": index,
				"user_id": row["user_id"],
				"telegram_id": telegram_id,
				"name": name,
				"points": int(row["points"] or 0),
				"attempts": int(row["attempts"] or 0),
				"verified": verified,
				"level": level["level"],
				"level_name": level["name"],
			})
		total_players = rows.count()
		return Response({"results": results, "count": total_players})


@extend_schema(tags=["Admin"])
class AdminQuizAttemptViewSet(viewsets.ModelViewSet):
	"""O'yin urinishlari: ko'rish, tahrirlash (suspect belgilash), o'chirish."""

	queryset = QuizAttempt.objects.select_related("user__telegram_profile", "title")
	serializer_class = QuizAttemptAdminSerializer
	permission_classes = [IsStaffAdmin]
	pagination_class = AdminPagination
	http_method_names = ["get", "patch", "delete", "head", "options"]

	def get_queryset(self):
		queryset = super().get_queryset()
		search = self.request.query_params.get("search", "").strip()
		if search:
			queryset = queryset.filter(
				Q(user__username__icontains=search)
				| Q(title__title__icontains=search)
				| Q(user__telegram_profile__telegram_id__icontains=search)
			)
		title_id = self.request.query_params.get("title", "").strip()
		if title_id.isdigit():
			queryset = queryset.filter(title_id=int(title_id))
		suspicious = self.request.query_params.get("suspicious", "").strip()
		if suspicious == "1":
			queryset = queryset.filter(is_suspicious=True)
		elif suspicious == "0":
			queryset = queryset.filter(is_suspicious=False)
		passed = self.request.query_params.get("passed", "").strip()
		if passed == "1":
			queryset = queryset.filter(passed=True)
		elif passed == "0":
			queryset = queryset.filter(passed=False)
		return queryset


@extend_schema(tags=["Admin"])
class AdminAnimeVerificationViewSet(viewsets.ModelViewSet):
	"""Tasdiqlangan animelar: qo'shish, o'chirish, tahrirlash."""

	queryset = AnimeVerification.objects.select_related("user__telegram_profile", "title")
	serializer_class = AnimeVerificationAdminSerializer
	permission_classes = [IsStaffAdmin]
	pagination_class = AdminPagination

	def get_queryset(self):
		queryset = super().get_queryset()
		search = self.request.query_params.get("search", "").strip()
		if search:
			queryset = queryset.filter(
				Q(user__username__icontains=search)
				| Q(title__title__icontains=search)
				| Q(user__telegram_profile__telegram_id__icontains=search)
			)
		title_id = self.request.query_params.get("title", "").strip()
		if title_id.isdigit():
			queryset = queryset.filter(title_id=int(title_id))
		return queryset


@extend_schema(tags=["Admin"])
class AdminMonthlyPrizeViewSet(viewsets.ModelViewSet):
	"""Oylik mukofotlar: CRUD + avtomatik berish."""

	queryset = MonthlyPrize.objects.select_related("user__telegram_profile")
	serializer_class = MonthlyPrizeAdminSerializer
	permission_classes = [IsStaffAdmin]
	pagination_class = AdminPagination

	def get_queryset(self):
		queryset = super().get_queryset()
		year = self.request.query_params.get("year", "").strip()
		if year.isdigit():
			queryset = queryset.filter(year=int(year))
		month = self.request.query_params.get("month", "").strip()
		if month.isdigit():
			queryset = queryset.filter(month=int(month))
		return queryset

	@extend_schema(request=None, tags=["Admin"])
	@action(detail=False, methods=["post"])
	def award(self, request):
		"""Berilgan yil/oy uchun eng faol obunasisiz o'yinchiga mukofot bering."""
		from games.services import award_monthly_prize_sync

		try:
			year = int(request.data.get("year") or timezone.now().year)
			month = int(request.data.get("month") or timezone.now().month)
		except (TypeError, ValueError):
			return Response({"detail": "Yil va oy noto'g'ri."}, status=400)
		if not 1 <= month <= 12:
			return Response({"detail": "Oy 1..12 bo'lishi kerak."}, status=400)

		prize = award_monthly_prize_sync(year, month)
		if prize is None:
			return Response({"detail": f"{year}-{month:02d} uchun mukofot allaqachon berilgan yoki nomzod yo'q."}, status=400)
		return Response(MonthlyPrizeAdminSerializer(prize).data, status=status.HTTP_201_CREATED)
