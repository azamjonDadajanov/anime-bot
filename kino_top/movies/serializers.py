from rest_framework import serializers

from .models import Genre, MediaPart, MediaTitle, ReadingProgress, TelegramChannel, TelegramMedia


class MediaTitleSerializer(serializers.ModelSerializer):
	slug = serializers.SlugField(required=False, allow_blank=True, allow_null=True, default="")
	genres = serializers.PrimaryKeyRelatedField(
		queryset=Genre.objects.all(),
		many=True,
		required=False,
	)

	class Meta:
		model = MediaTitle
		fields = [
			"id",
			"type",
			"title",
			"slug",
			"genres",
			"code",
			"synopsis",
			"episode_count",
			"quality_options",
			"default_quality",
			"language",
			"required_plan",
			"rating",
			"cover",
			"cover_content_type",
			"release_year",
			"status",
			"quiz_size",
			"created_at",
			"updated_at",
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

	class Meta(MediaTitleSerializer.Meta):
		fields = [*MediaTitleSerializer.Meta.fields, "parts", "is_favorite"]

	def get_is_favorite(self, obj) -> bool:
		"""True when the authenticated caller has this title in favourites."""
		request = self.context.get("request")
		if request is None or not request.user or not request.user.is_authenticated:
			return False
		profile = getattr(request.user, "telegram_profile", None)
		if profile is None:
			return False
		return obj.user_favorites.filter(user=profile).exists()


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
		fields = ["id", "type", "title", "slug", "genres", "code", "synopsis", "episode_count", "quality_options", "default_quality", "language", "required_plan", "rating", "cover_content_type", "parts"]


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