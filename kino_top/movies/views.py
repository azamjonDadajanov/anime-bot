from django.conf import settings
from django.http import FileResponse, HttpResponse
from django.shortcuts import get_object_or_404
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.pagination import PageNumberPagination
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import IsAdminUser, IsAuthenticated
from rest_framework.response import Response

import logging

logger = logging.getLogger(__name__)

from . import ai_assistant
from .models import MediaPart, MediaTitle, MediaView, ReadingProgress, TelegramChannel, TelegramMedia
from .permissions import IsAdminOrReadOnly
from .serializers import (
	AIAssistantQuerySerializer,
	AIAssistantResponseSerializer,
	MediaLookupSerializer,
	MediaPartSerializer,
	MediaTitleSerializer,
	MediaTitleDetailSerializer,
	ReadingProgressSerializer,
	TelegramChannelSerializer,
	TelegramMediaSerializer,
)
from .storage_copy import copy_file_to_storage
from .telegram_files import TelegramFileError, fetch_file_bytes, resolve_file_path


def _pdf_error_message(exc: TelegramFileError) -> str:
	message = str(exc)
	lowered = message.lower()
	if "too big" in lowered or "file is too big" in lowered:
		return "PDF Telegram orqali yuklanmaydi (bot uchun 20MB limit). Faylni saytga (serverga) yuklang."
	if "not found" in lowered or "wrong file" in lowered or "invalid" in lowered:
		return "Telegram file_id yaroqsiz yoki muddati o'tgan."
	return message


def _looks_like_pdf(upload) -> bool:
	name = (getattr(upload, "name", "") or "").lower()
	content_type = (getattr(upload, "content_type", "") or "").lower()
	return name.endswith(".pdf") or content_type == "application/pdf"


# How much of the user's taste the "Sevimlilar" analysis sees: the last ten
# favourites and the last ten watched titles — enough for a pattern, small
# enough that the prompt stays cheap.
TASTE_FAVORITES_LIMIT = 10
TASTE_VIEWS_LIMIT = 10


def _taste_line(title) -> str:
	genres = ", ".join(genre.name for genre in title.genres.all()[:3])
	parts = [title.get_type_display().lower()]
	if genres:
		parts.append(genres)
	return "(" + ", ".join(parts) + ")"


def _taste_context(user) -> tuple:
	"""A short block about the user's taste, plus how much it saw.

	Returns ``(context, favorites_count, views_count)``. Favourites come
	first (newest), then the last watched titles not already covered — the
	same shape the bot's AI context uses. Empty context when the account has
	neither yet.
	"""
	# Local import: the users app owns FavoriteContent, and movies must not
	# depend on it at module level.
	from users.models import FavoriteContent

	profile = getattr(user, "telegram_profile", None)
	favorites = []
	if profile is not None:
		favorites = list(
			FavoriteContent.objects.filter(user=profile)
			.select_related("content")
			.prefetch_related("content__genres")
			.order_by("-created_at")[:TASTE_FAVORITES_LIMIT]
		)
	views = list(
		MediaView.objects.filter(user=user)
		.select_related("title")
		.prefetch_related("title__genres")
		.order_by("-updated_at")[:TASTE_VIEWS_LIMIT]
	)
	lines = []
	if favorites:
		items = ", ".join(
			f"{row.content.title[:40]} {_taste_line(row.content)}" for row in favorites
		)
		lines.append(f"Sevimlilar: {items}")
	seen = {row.content_id for row in favorites}
	watched = [row for row in views if row.title_id not in seen]
	if watched:
		items = ", ".join(
			f"{row.title.title[:40]} {_taste_line(row.title)}" for row in watched
		)
		lines.append(f"Oxirgi ko'rganlari: {items}")
	return "\n".join(lines), len(favorites), len(views)


class CatalogPagination(PageNumberPagination):
	page_size = 20
	page_size_query_param = "page_size"
	max_page_size = 100


@extend_schema(tags=["Catalog"])
class MediaTitleViewSet(viewsets.ModelViewSet):
	queryset = MediaTitle.objects.all()
	serializer_class = MediaTitleSerializer
	permission_classes = [IsAdminOrReadOnly]
	lookup_field = "slug"
	lookup_value_regex = r"[-a-zA-Z0-9_]+"

	def get_serializer_class(self):
		if self.action == "retrieve":
			return MediaTitleDetailSerializer
		return MediaTitleSerializer

	def get_queryset(self):
		queryset = super().get_queryset()
		media_type = self.request.query_params.get("type")
		status = self.request.query_params.get("status")
		search = self.request.query_params.get("search")
		if media_type:
			queryset = queryset.filter(type=media_type)
		if status:
			queryset = queryset.filter(status=status)
		if search:
			queryset = queryset.filter(title__icontains=search)
		if self.action == "retrieve":
			queryset = queryset.prefetch_related("genres", "parts", "parts__telegram_media")
		return queryset

	def perform_create(self, serializer):
		title = serializer.save()
		# Web orqali yangi kontent qo'shilganda ommaviy kanalga e'lon qilinadi
		# (faqat "Avtomatik e'lon" yoqilgan bo'lsa).
		from adminpanel.publisher import auto_publish_title

		auto_publish_title(title.pk)

	def perform_update(self, serializer):
		old_status = self.get_object().status
		title = serializer.save()
		if old_status != MediaTitle.Status.COMPLETED and title.status == MediaTitle.Status.COMPLETED:
			from adminpanel.publisher import auto_publish_completed

			auto_publish_completed(title.pk)

	@extend_schema(responses=MediaLookupSerializer, tags=["Catalog"])
	@action(
		detail=False,
		methods=["get"],
		url_path=r"code/(?P<code>[0-9]{4})",
		permission_classes=[IsAuthenticated],
	)
	def by_code(self, request, code=None):
		content = get_object_or_404(
			MediaTitle.objects.prefetch_related("parts__telegram_media__channel"),
			code=code,
		)
		return Response(MediaLookupSerializer(content).data)

	@extend_schema(request=None, responses=OpenApiTypes.OBJECT, tags=["Catalog"])
	@action(detail=True, methods=["post"], url_path="view", permission_classes=[IsAuthenticated])
	def view(self, request, slug=None):
		"""Record that the signed-in user opened (or played) a title.

		Keeps the "Oxirgi ko'rgan medialar" and "Oxirgi faolliklar" profile tabs
		fed by real activity instead of inferred data.
		"""
		title = self.get_object()
		part = None
		try:
			part_id = int(request.data.get("part") or 0)
		except (TypeError, ValueError):
			part_id = 0
		if part_id:
			part = MediaPart.objects.filter(pk=part_id, content=title).first()
		view = MediaView.record(request.user, title, part=part, source=MediaView.Source.SITE)
		return Response({"status": "ok", "view_id": view.pk if view else None})

	@extend_schema(
		request=AIAssistantQuerySerializer,
		responses={200: AIAssistantResponseSerializer},
		tags=["Catalog"],
	)
	@action(
		detail=False,
		methods=["post"],
		url_path="ai-assistant",
		permission_classes=[IsAuthenticated],
	)
	def ai_assistant(self, request):
		"""AniVoy: ask the AI assistant (subscribers only).

		The assistant is an online chat model with catalogue functions: it
		searches titles, reads their details or parts, lists genres and popular
		content, and only then writes the answer. ``results`` are the titles its
		functions actually returned, so a link the user can press is always a
		real catalogue row.
		"""
		serializer = AIAssistantQuerySerializer(data=request.data)
		serializer.is_valid(raise_exception=True)
		if not ai_assistant.user_can_use(request.user):
			return Response(
				{
					"code": "subscription_required",
					"detail": ai_assistant.SUBSCRIPTION_REQUIRED_TEXT,
				},
				status=status.HTTP_403_FORBIDDEN,
			)
		try:
			limit = int(request.data.get("limit") or 0) or None
		except (TypeError, ValueError):
			limit = None
		media_type = str(request.data.get("type") or "").strip()
		if media_type and media_type not in MediaTitle.MediaType.values:
			media_type = ""
		result = ai_assistant.answer(
			serializer.validated_data["query"],
			limit=limit,
			media_type=media_type,
			# The chat the question came from: the assistant answers "nima
			# aytgandingiz?" from the last turns instead of guessing.
			history=serializer.validated_data.get("history") or [],
			# "Adminga xabar": technical problems get fix-it steps.
			support=bool(serializer.validated_data.get("support")),
			# "Sevimlilar": the account's favourites and last watched titles
			# become the assistant's personal_taste tool.
			personal_context=(
				_taste_context(request.user)[0]
				if serializer.validated_data.get("taste")
				else ""
			),
		)
		if not result.used_llm:
			# Only online models can answer: a deployment without a key, or a
			# chain that is fully on cooldown, has no offline fallback any more.
			if result.error:
				logger.warning("AI assistant is unavailable: %s", result.error)
			return Response(
				{"code": "ai_unavailable", "detail": ai_assistant.UNAVAILABLE_TEXT},
				status=status.HTTP_503_SERVICE_UNAVAILABLE,
			)
		site_url = getattr(settings, "BOT_SITE_URL", "") or ""
		results = [ai_assistant.title_payload(title, site_url=site_url) for title in result.titles]
		return Response(
			{
				"query": result.query,
				"count": len(results),
				"answer": result.answer,
				# True when the assistant answered a conversational question
				# instead of searching: ``results`` is empty on purpose and the
				# client shows ``answer`` alone, without the "nothing found" copy.
				"conversational": result.conversational,
				# The functions that ran, so a client can show what it looked up.
				"tools": list(result.tools),
				"results": results,
			}
		)

	def _serialize(self, request, queryset):
		paginator = CatalogPagination()
		page = paginator.paginate_queryset(queryset, request, view=self)
		serializer = MediaTitleSerializer(page, many=True)
		return paginator.get_paginated_response(serializer.data)

	def _flat(self, request, queryset, limit=20):
		try:
			limit = int(request.query_params.get("limit", limit))
		except (TypeError, ValueError):
			limit = 20
		return Response(MediaTitleSerializer(queryset[: max(1, min(limit, 50))], many=True).data)

	@extend_schema(responses=MediaTitleSerializer(many=True), tags=["Catalog"])
	@action(detail=False, methods=["get"])
	def latest(self, request):
		return self._serialize(request, MediaTitle.objects.order_by("-created_at", "-id"))

	@extend_schema(responses=MediaTitleSerializer(many=True), tags=["Catalog"])
	@action(detail=False, methods=["get"])
	def popular(self, request):
		return self._serialize(request, MediaTitle.objects.order_by("-rating", "-created_at"))

	@extend_schema(responses=MediaTitleSerializer(many=True), tags=["Catalog"])
	@action(detail=False, methods=["get"])
	def upcoming(self, request):
		queryset = MediaTitle.objects.filter(status=MediaTitle.Status.UPCOMING)
		return self._serialize(request, queryset.order_by("-created_at"))

	def _by_type(self, request, media_type):
		queryset = MediaTitle.objects.filter(type=media_type)
		return self._serialize(request, queryset.order_by("-created_at"))

	@extend_schema(responses=MediaTitleSerializer(many=True), tags=["Catalog"])
	@action(detail=False, methods=["get"])
	def movies(self, request):
		return self._by_type(request, MediaTitle.MediaType.MOVIE)

	@extend_schema(responses=MediaTitleSerializer(many=True), tags=["Catalog"])
	@action(detail=False, methods=["get"])
	def anime(self, request):
		return self._by_type(request, MediaTitle.MediaType.ANIME)

	@extend_schema(responses=MediaTitleSerializer(many=True), tags=["Catalog"])
	@action(detail=False, methods=["get"])
	def manga(self, request):
		return self._by_type(request, MediaTitle.MediaType.MANGA)

	@extend_schema(responses=MediaTitleSerializer(many=True), tags=["Catalog"])
	@action(detail=False, methods=["get"])
	def series(self, request):
		return self._by_type(request, MediaTitle.MediaType.SERIES)

	@extend_schema(responses=MediaTitleSerializer(many=True), tags=["Catalog"])
	@action(detail=False, methods=["get"], url_path="random")
	def random_titles(self, request):
		return self._flat(request, MediaTitle.objects.order_by("?"))


@extend_schema(tags=["Catalog"])
class MediaPartViewSet(viewsets.ModelViewSet):
	queryset = MediaPart.objects.select_related("content")
	serializer_class = MediaPartSerializer
	permission_classes = [IsAdminOrReadOnly]

	def get_queryset(self):
		queryset = super().get_queryset()
		content_id = self.request.query_params.get("content")
		if content_id:
			queryset = queryset.filter(content_id=content_id)
		return queryset

	def perform_create(self, serializer):
		part = serializer.save()
		# Web orqali yangi qism qo'shilganda ommaviy kanalga e'lon qilinadi
		# (faqat "Avtomatik e'lon" yoqilgan bo'lsa).
		from adminpanel.publisher import auto_publish_part

		auto_publish_part(part.content_id, part.pk)

	@extend_schema(tags=["Catalog"])
	@action(detail=True, methods=["get", "delete"], url_path="pdf")
	def pdf(self, request, pk=None):
		"""Serve the chapter PDF: local upload first, Telegram document fallback.

		Add ``?meta=1`` to only report availability (no download), so the reader
		can show a clear reason instead of a broken viewer. ``DELETE`` removes
		the locally stored PDF (staff only).
		"""
		part = self.get_object()

		if request.method == "DELETE":
			if not request.user.is_staff:
				return Response({"detail": "Ruxsat yo'q."}, status=403)
			if part.pdf:
				part.pdf.delete(save=True)
			return Response(status=204)

		filename = f"{part.content.slug}-{part.number}.pdf"
		meta_only = request.query_params.get("meta")
		has_local = bool(part.pdf) and part.pdf.storage.exists(part.pdf.name)

		if has_local:
			if meta_only:
				return Response({"available": True, "source": "local", "size": part.pdf.size})
			response = FileResponse(part.pdf.open("rb"), content_type="application/pdf")
			response["Content-Disposition"] = f'inline; filename="{filename}"'
			response["Accept-Ranges"] = "none"
			return response

		document = next(
			(
				item
				for item in part.telegram_media.all()
				if item.media_type == TelegramMedia.MediaType.DOCUMENT
			),
			None,
		)
		if document is None:
			if meta_only:
				return Response({"available": False, "reason": "Bu qism uchun PDF topilmadi."})
			return Response({"detail": "Bu qism uchun PDF topilmadi."}, status=404)

		if meta_only:
			try:
				resolve_file_path(document.file_id)
			except TelegramFileError as exc:
				return Response({"available": False, "reason": _pdf_error_message(exc)})
			return Response({"available": True, "source": "telegram"})

		try:
			content, _ = fetch_file_bytes(document.file_id)
		except TelegramFileError as exc:
			return Response({"detail": _pdf_error_message(exc)}, status=502)

		response = HttpResponse(content, content_type="application/pdf")
		response["Content-Disposition"] = f'inline; filename="{filename}"'
		response["Accept-Ranges"] = "none"
		return response

	@extend_schema(tags=["Catalog"])
	@action(
		detail=True,
		methods=["post"],
		url_path="pdf/upload",
		permission_classes=[IsAdminUser],
		parser_classes=[MultiPartParser, FormParser],
	)
	def pdf_upload(self, request, pk=None):
		"""Store a local PDF for this part (staff only).

		Telegram's Bot API cannot serve files over 20 MB, so large chapters are
		uploaded here and served directly by the website.
		"""
		part = self.get_object()
		upload = request.FILES.get("file")
		if upload is None:
			return Response({"detail": "PDF fayl yuborilmadi (file maydoni)."}, status=400)
		if not _looks_like_pdf(upload):
			return Response({"detail": "Faqat PDF fayl yuklash mumkin."}, status=400)

		filename = f"{part.content.slug}-{part.number}.pdf"
		part.pdf.save(filename, upload, save=True)
		return Response(
			{"available": True, "source": "local", "size": part.pdf.size, "has_pdf": True}
		)


@extend_schema(tags=["Catalog"])
class ReadingProgressViewSet(viewsets.ModelViewSet):
	queryset = ReadingProgress.objects.select_related("part", "part__content")
	serializer_class = ReadingProgressSerializer
	permission_classes = [IsAuthenticated]

	def get_queryset(self):
		queryset = super().get_queryset().filter(user=self.request.user)
		title_slug = self.request.query_params.get("title")
		if title_slug:
			queryset = queryset.filter(part__content__slug=title_slug)
		return queryset

	def create(self, request, *args, **kwargs):
		serializer = self.get_serializer(data=request.data)
		serializer.is_valid(raise_exception=True)
		part = serializer.validated_data["part"]
		defaults = {}
		if "page" in serializer.validated_data:
			defaults["page"] = serializer.validated_data["page"]
		if "is_read" in serializer.validated_data:
			defaults["is_read"] = serializer.validated_data["is_read"]
		progress, _ = ReadingProgress.objects.update_or_create(
			user=request.user,
			part=part,
			defaults=defaults,
		)
		return Response(self.get_serializer(progress).data)



@extend_schema(tags=["Telegram media"])
class TelegramMediaViewSet(viewsets.ModelViewSet):
	queryset = TelegramMedia.objects.select_related("part", "part__content")
	serializer_class = TelegramMediaSerializer
	permission_classes = [IsAdminUser]

	def get_queryset(self):
		queryset = super().get_queryset()
		part_id = self.request.query_params.get("part")
		if part_id:
			queryset = queryset.filter(part_id=part_id)
		return queryset

	def perform_create(self, serializer):
		media = serializer.save()
		# Web orqali file_id qo'shilganda fayl Cloud kanalga ko'chiriladi.
		if media.file_id and not media.channel_id:
			success, error = copy_file_to_storage(
				media.pk,
				media.file_id,
				media.media_type,
				media.caption or "",
			)
			if not success:
				# Xatolikni log qilamiz, lekin media yozuvini saqlab qolamiz
				# (admin tuzatib qayta urinishi mumkin)
				logger.warning("Cloud kanalga ko'chirish amalga oshmadi (media #%s): %s", media.pk, error)
				# Error'ni response'ga qo'shish uchun serializer'ga qo'shamiz
				serializer.instance.storage_error = error

	def create(self, request, *args, **kwargs):
		serializer = self.get_serializer(data=request.data)
		serializer.is_valid(raise_exception=True)
		self.perform_create(serializer)
		headers = self.get_success_headers(serializer.data)
		# Storage xatolik bo'lsa response'ga qo'shamiz
		storage_error = getattr(serializer.instance, "storage_error", None)
		data = serializer.data
		if storage_error:
			data["storage_error"] = storage_error
		return Response(data, status=status.HTTP_201_CREATED, headers=headers)


@extend_schema(tags=["Telegram media"])
class TelegramChannelViewSet(viewsets.ModelViewSet):
	queryset = TelegramChannel.objects.all()
	serializer_class = TelegramChannelSerializer
	permission_classes = [IsAdminUser]
