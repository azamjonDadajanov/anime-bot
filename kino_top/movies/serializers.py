from rest_framework import serializers

from .models import MediaPart, MediaTitle, ReadingProgress, TelegramChannel, TelegramMedia


class MediaTitleSerializer(serializers.ModelSerializer):
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
			"created_at",
			"updated_at",
		]
		read_only_fields = ["id", "created_at", "updated_at"]


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

	class Meta(MediaTitleSerializer.Meta):
		fields = [*MediaTitleSerializer.Meta.fields, "parts"]


class TelegramMediaSerializer(serializers.ModelSerializer):
	class Meta:
		model = TelegramMedia
		fields = ["id", "part", "channel", "file_id", "media_type", "order", "caption"]
		read_only_fields = ["id"]


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