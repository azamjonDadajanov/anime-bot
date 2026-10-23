from rest_framework import serializers

from .covers import content_file, cover_url, decode_base64
from .models import Genre, MediaPart, MediaTitle, ReadingProgress, TelegramChannel, TelegramMedia

# Returned by CoverField.to_internal_value() when the client echoes the stored
# file URL back: the image is already on disk, nothing has to change.
UNCHANGED = object()


class CoverField(serializers.Field):
	"""``cover``: a /media/covers/... URL on read, an upload on write.

	The administrator panel posts base64 in JSON, the bot service layer and the
	import command hand over raw bytes, and an untouched form field echoes the
	URL it rendered earlier. All three are accepted; only new image data ever
	reaches the storage, which keeps nginx in charge of serving the bytes.
	"""

	default_error_messages = {
		"invalid": "Muqova rasm noto'g'ri formatda yuborildi.",
	}

	def to_representation(self, value) -> str:
		return cover_url(value)

	def to_internal_value(self, data):
		if data is None or data == "":
			return None
		# Multipart upload (POST /catalog/ with a real file).
		if hasattr(data, "read"):
			return data
		if not isinstance(data, str):
			self.fail("invalid")
		raw = data.strip()
		if raw.startswith("/media/") or raw.startswith(("http://", "https://")):
			return UNCHANGED
		try:
			blob = decode_base64(raw)
		except ValueError:
			self.fail("invalid")
		return content_file(blob)


class MediaTitleSerializer(serializers.ModelSerializer):
	slug = serializers.SlugField(required=False, allow_blank=True, allow_null=True, default="")
	genres = serializers.PrimaryKeyRelatedField(
		queryset=Genre.objects.all(),
		many=True,
		required=False,
	)
	# Reading side of ``genres``: the admin panel edits with primary keys, the
	# public site only needs the labels, so both shapes travel together.
	genre_names = serializers.SerializerMethodField()
	cover = CoverField(required=False, allow_null=True)

	def get_genre_names(self, obj) -> list:
		return [genre.name for genre in obj.genres.all()]

	def create(self, validated_data):
		# A URL means "already stored, nothing new": drop it, there is no file
		# to attach on creation.
		if validated_data.get("cover") is UNCHANGED:
			validated_data.pop("cover")
		return super().create(validated_data)

	def update(self, instance, validated_data):
		# Same on edit: the panel echoes /media/covers/... back when the form
		# field was untouched, and the file on disk must stay as it is.
		if validated_data.get("cover") is UNCHANGED:
			validated_data.pop("cover")
		return super().update(instance, validated_data)

	class Meta:
		model = MediaTitle
		fields = [
			"id",
			"type",
			"title",
			"slug",
			"genres",
			"genre_names",
			"code",
			"synopsis",
			"episode_count",
			"duration_minutes",
			"quality_options",
			"default_quality",
			"language",
			"required_plan",
			"rating",
			"rating_average",
			"rating_count",
			"cover",
			"cover_content_type",
			"release_year",
			"status",
			"quiz_size",
			"created_at",
			"updated_at",
			'quizess_count',
			'movies_count',
		]
		read_only_fields = ["id", "code", "created_at", "updated_at"]

	def validate(self, attrs):
		if self.instance is None and not attrs.get("title"):
			raise serializers.ValidationError({"title": "Nomi majburiy."})
		return attrs


class MediaPartSerializer(serializers.ModelSerializer):
	has_pdf = serializers.SerializerMethodField()

	class Meta:
		model = MediaPart
		fields = ["id", "content", "season_number", "number", "title", "has_pdf", "created_at"]
		read_only_fields = ["id", "created_at"]

	def get_has_pdf(self, obj) -> bool:
		if obj.pdf:
			return True
		return any(
			item.media_type == TelegramMedia.MediaType.DOCUMENT
			for item in obj.telegram_media.all()
		)


class MediaTitleDetailSerializer(MediaTitleSerializer):
	parts = MediaPartSerializer(many=True, read_only=True)
	is_favorite = serializers.SerializerMethodField()
	# Community numbers shown on the detail page: the live average plus how
	# many accounts produced it, the caller's own 1-10 score (null when they
	# have not rated yet) and the comment counter.
	my_rating = serializers.SerializerMethodField()
	comments_count = serializers.SerializerMethodField()

	class Meta(MediaTitleSerializer.Meta):
		fields = [
			*MediaTitleSerializer.Meta.fields,
			"parts",
			"is_favorite",
			"my_rating",
			"comments_count",
		]

	def get_is_favorite(self, obj) -> bool:
		"""True when the authenticated caller has this title in favourites."""
		request = self.context.get("request")
		if request is None or not request.user or not request.user.is_authenticated:
			return False
		profile = getattr(request.user, "telegram_profile", None)
		if profile is None:
			return False
		return obj.user_favorites.filter(user=profile).exists()

	def get_my_rating(self, obj) -> int | None:
		request = self.context.get("request")
		if request is None or not request.user or not request.user.is_authenticated:
			return None
		from .community import user_rating_sync

		return user_rating_sync(request.user, obj)

	def get_comments_count(self, obj) -> int:
		from .community import comment_counts_sync

		return comment_counts_sync(obj)


class CommentAuthorSerializer(serializers.Serializer):
	"""Who wrote a comment — plus whether they currently hold the 👑."""

	id = serializers.IntegerField(allow_null=True)
	username = serializers.CharField()
	display_name = serializers.CharField()
	is_premium = serializers.BooleanField()


class CommentPartSerializer(serializers.Serializer):
	"""The episode the comment belongs to (null = about the whole title)."""

	id = serializers.IntegerField()
	number = serializers.IntegerField()
	season_number = serializers.IntegerField(allow_null=True)
	title = serializers.CharField()


class CommentTitleRefSerializer(serializers.Serializer):
	id = serializers.IntegerField()
	title = serializers.CharField()
	slug = serializers.CharField()
	type = serializers.CharField()


class TitleCommentSerializer(serializers.Serializer):
	"""Read shape of one comment (built from ``movies.community`` payloads)."""

	id = serializers.IntegerField()
	body = serializers.CharField()
	source = serializers.CharField()
	created_at = serializers.DateTimeField()
	part = CommentPartSerializer(allow_null=True)
	author = CommentAuthorSerializer()
	author_initial = serializers.CharField()
	author_rating = serializers.IntegerField(allow_null=True)
	title = CommentTitleRefSerializer()


class CommentListSerializer(serializers.Serializer):
	"""Paginated comment page (same shape in the API and in the bot)."""

	count = serializers.IntegerField()
	page = serializers.IntegerField()
	pages = serializers.IntegerField()
	page_size = serializers.IntegerField()
	results = TitleCommentSerializer(many=True)


class CommentCreateSerializer(serializers.Serializer):
	"""POST body: which title, what was written, optionally an episode and a 1-10 score."""

	title = serializers.SlugField()
	body = serializers.CharField(allow_blank=False, trim_whitespace=False)
	part = serializers.IntegerField(required=False, allow_null=True, default=None)
	# The score travels with the comment but is stored in its own table, so
	# later edits (or deletion) of the text can never touch the rating.
	rating = serializers.IntegerField(
		required=False, allow_null=True, default=None, min_value=1, max_value=10
	)

	def validate_body(self, value):
		from .community import CommunityError, validate_body

		try:
			return validate_body(value)
		except CommunityError as exc:
			raise serializers.ValidationError(exc.detail) from None

	def validate(self, attrs):
		from .models import MediaPart

		title = MediaTitle.objects.filter(slug=attrs["title"]).first()
		if title is None:
			raise serializers.ValidationError({"title": "Media topilmadi."})
		part = None
		part_id = attrs.get("part")
		if part_id:
			part = MediaPart.objects.filter(pk=part_id, content=title).first()
			if part is None:
				raise serializers.ValidationError({"part": "Bu media bunday qismga ega emas."})
		attrs["title_object"] = title
		attrs["part_object"] = part
		return attrs


class RatingCreateSerializer(serializers.Serializer):
	"""POST body of ``/catalog/{slug}/rating/``."""

	score = serializers.IntegerField(
		min_value=1, max_value=10, error_messages={"min_value": "Baho 1 dan 10 gacha.", "max_value": "Baha 1 dan 10 gacha."}
	)


class RatingSummarySerializer(serializers.Serializer):
	average = serializers.FloatField()
	count = serializers.IntegerField()
	my_score = serializers.IntegerField(allow_null=True)
	min = serializers.IntegerField()
	max = serializers.IntegerField()


class TelegramMediaSerializer(serializers.ModelSerializer):
	class Meta:
		model = TelegramMedia
		fields = ["id", "part", "channel", "file_id", "media_type", "order", "caption"]
		read_only_fields = ["id"]
		extra_kwargs = {"part": {"required": True}}

	def __init__(self, *args, **kwargs):
		super().__init__(*args, **kwargs)
		# Disable the auto-generated UniqueTogetherValidator so validate() gives a friendly message.
		self.validators = [
			v for v in self.validators
			if v.__class__.__name__ != "UniqueTogetherValidator"
		]

	def validate(self, attrs):
		part = attrs.get("part") or (self.instance.part if self.instance else None)
		order = attrs.get("order") or (self.instance.order if self.instance else None)
		if part is not None and order is not None:
			qs = TelegramMedia.objects.filter(part=part, order=order)
			if self.instance:
				qs = qs.exclude(pk=self.instance.pk)
			if qs.exists():
				raise serializers.ValidationError(
					{"order": f"Bu qismda {order}-tartibli media allaqachon mavjud."}
				)
		return attrs


class TelegramChannelSerializer(serializers.ModelSerializer):
	class Meta:
		model = TelegramChannel
		fields = [
			"id",
			"chat_id",
			"title",
			"username",
			"is_active",
			"purpose",
			"invite_link",
			"created_at",
		]
		read_only_fields = ["id", "created_at"]


class TelegramMediaLookupSerializer(serializers.ModelSerializer):
	channel = TelegramChannelSerializer(read_only=True)

	class Meta:
		model = TelegramMedia
		fields = ["id", "channel", "file_id", "media_type", "order", "caption"]


class MediaPartLookupSerializer(serializers.ModelSerializer):
	telegram_media = TelegramMediaLookupSerializer(many=True, read_only=True)

	class Meta:
		model = MediaPart
		fields = ["id", "season_number", "number", "title", "telegram_media"]


class MediaLookupSerializer(serializers.ModelSerializer):
	parts = MediaPartLookupSerializer(many=True, read_only=True)

	class Meta:
		model = MediaTitle
		fields = ["id", "type", "title", "slug", "genres", "code", "synopsis", "episode_count", "duration_minutes", "quality_options", "default_quality", "language", "required_plan", "rating", "rating_average", "rating_count", "cover_content_type", "parts"]


class AIHistoryMessageSerializer(serializers.Serializer):
	"""One earlier turn of the chat, so follow-up questions still mean something."""

	role = serializers.ChoiceField(
		choices=["user", "ai"],
		default="user",
		error_messages={"invalid": "Xabar roli noto'g'ri."},
	)
	text = serializers.CharField(
		max_length=300,
		trim_whitespace=True,
		allow_blank=True,
		error_messages={"max_length": "Xabar 300 belgidan oshmasligi kerak."},
	)


class AIAssistantQuerySerializer(serializers.Serializer):
	"""The request the user phrases in their own words."""

	query = serializers.CharField(
		max_length=300,
		trim_whitespace=True,
		allow_blank=False,
		error_messages={
			"required": "Savol matnini kiriting.",
			"blank": "Savol matnini kiriting.",
			"max_length": "Savol 300 belgidan oshmasligi kerak.",
		},
	)
	# The last few turns of the conversation ("adminga xabar" and the chat
	# both ask follow-ups). Only the newest HISTORY_LIMIT are kept — the
	# prompt needs the thread, not the transcript.
	history = AIHistoryMessageSerializer(
		many=True,
		required=False,
		allow_empty=True,
		default=list,
	)
	# True for the "adminga xabar" flow: the model switches to the technical
	# support persona and answers a problem with fix-it steps and advice.
	support = serializers.BooleanField(
		required=False,
		default=False,
		error_messages={"invalid": "support maydoni mantiqiy bo'lishi kerak."},
	)
	# True for the "Sevimlilar" mode: the account's favourites and last
	# watched titles ride along as the model's personal-data block, so any
	# query is answered against the user's actual taste.
	taste = serializers.BooleanField(
		required=False,
		default=False,
		error_messages={"invalid": "taste maydoni mantiqiy bo'lishi kerak."},
	)

	HISTORY_LIMIT = 10

	def validate_history(self, value):
		return value[-self.HISTORY_LIMIT :]


class AIAssistantResultSerializer(serializers.Serializer):
	"""One title a tool returned: the link plus the sentence under it.

	Declared explicitly (it is built from a ``MediaTitle``, not from the
	model) so the OpenAPI schema documents exactly what the clients receive.
	"""

	id = serializers.IntegerField()
	title = serializers.CharField()
	slug = serializers.CharField()
	type = serializers.CharField()
	type_display = serializers.CharField()
	code = serializers.CharField()
	release_year = serializers.IntegerField(allow_null=True)
	rating = serializers.IntegerField()
	genres = serializers.ListField(child=serializers.CharField())
	summary = serializers.CharField()
	url = serializers.CharField()


class AIActionFieldSerializer(serializers.Serializer):
	"""One row of the confirmation card the client renders.

	Built server-side from the real account state (never by the model), so the
	schema documents every kind a client must handle: ``static`` (read-only),
	``text``/``textarea`` (edited inline), ``int`` (min/max), ``select``
	(options), ``bool`` and ``file`` (a screenshot or avatar upload).
	"""

	key = serializers.CharField()
	label = serializers.CharField()
	type = serializers.CharField()
	value = serializers.JSONField(allow_null=True, required=False)
	editable = serializers.BooleanField(required=False, default=False)
	required = serializers.BooleanField(required=False, default=False)
	options = serializers.ListField(child=serializers.DictField(), required=False)
	min = serializers.IntegerField(required=False)
	max = serializers.IntegerField(required=False)
	max_length = serializers.IntegerField(required=False)
	accept = serializers.CharField(required=False)
	help = serializers.CharField(required=False)
	href = serializers.CharField(required=False)


class AIActionSerializer(serializers.Serializer):
	"""A proposed account action, waiting for the user's confirmation.

	``token`` is the signed proposal (user, action, values) the confirm
	endpoint receives back; ``link`` only rides along for ``link_telegram``,
	where the card's own buttons do the work and polling just flips the state.
	"""

	token = serializers.CharField()
	action = serializers.CharField()
	label = serializers.CharField()
	kind = serializers.CharField()
	source = serializers.CharField()
	fields = AIActionFieldSerializer(many=True)
	link = serializers.DictField(required=False)


class AIAssistantResponseSerializer(serializers.Serializer):
	query = serializers.CharField()
	count = serializers.IntegerField()
	# The assistant's own words. Empty only when it could not answer at all —
	# in that case the action returns a 503 instead of this payload.
	answer = serializers.CharField()
	# True when the model answered a conversational question (no catalogue
	# lookup), so ``results`` is empty on purpose and the client shows the
	# words alone, without the "nothing found" copy.
	conversational = serializers.BooleanField()
	# The functions the assistant actually ran for this request
	# (``search_catalog``, ``list_parts``, ``personal_taste``, ...).
	tools = serializers.ListField(child=serializers.CharField())
	results = AIAssistantResultSerializer(many=True)
	# The confirmation card when the model proposed an account action.
	action = AIActionSerializer(allow_null=True, required=False)


class AIActionConfirmSerializer(serializers.Serializer):
	"""The confirm call: the signed token plus whatever the user edited.

	Files (a payment screenshot, an avatar picture) ride as multipart parts
	and are read from ``request.FILES`` by the view, so they stay out of this
	JSON-ish body.
	"""

	token = serializers.CharField(
		max_length=2048,
		error_messages={"required": "Amal kartasi tokeni kerak."},
	)
	# Only the action's own editable keys survive the whitelist in
	# ``movies.ai_actions.execute``; anything else is dropped silently.
	values = serializers.JSONField(required=False, allow_null=True, default=dict)


class ReadingProgressSerializer(serializers.ModelSerializer):
	part = serializers.PrimaryKeyRelatedField(queryset=MediaPart.objects.all())
	page = serializers.IntegerField(required=False, min_value=1)
	is_read = serializers.BooleanField(required=False)

	class Meta:
		model = ReadingProgress
		fields = ["id", "part", "page", "is_read", "updated_at"]
		read_only_fields = ["id", "updated_at"]

	def to_representation(self, instance):
		data = super().to_representation(instance)
		data["part_number"] = instance.part.number
		data["season_number"] = instance.part.season_number
		data["title_slug"] = instance.part.content.slug
		return data