from rest_framework import serializers


class GameStatusSerializer(serializers.Serializer):
	"""No fields — the view returns ``services.user_status`` verbatim."""


class QuizStartSerializer(serializers.Serializer):
	title_id = serializers.IntegerField()


class QuizSubmitSerializer(serializers.Serializer):
	attempt_id = serializers.IntegerField()
	answers = serializers.ListField(
		child=serializers.IntegerField(),
		allow_empty=False,
	)
	elapsed_ms = serializers.IntegerField(required=False, default=0, min_value=0)


class LeaderboardSerializer(serializers.Serializer):
	limit = serializers.IntegerField(required=False, default=50, min_value=1, max_value=200)
