from rest_framework import serializers


class GameStatusSerializer(serializers.Serializer):
	"""Response of ``GET status/`` — ``services.user_status`` verbatim."""

	points = serializers.IntegerField()
	verified_count = serializers.IntegerField()
	attempts = serializers.IntegerField()
	level = serializers.IntegerField()
	name = serializers.CharField()
	next_in = serializers.IntegerField()
	quiz_size = serializers.IntegerField()
	pass_score = serializers.IntegerField()
	min_parts = serializers.IntegerField()
	no_retry = serializers.BooleanField()


class UnlockedTitleSerializer(serializers.Serializer):
	id = serializers.IntegerField()
	title = serializers.CharField()
	type = serializers.CharField()
	bot_views = serializers.IntegerField()
	points = serializers.IntegerField()
	questions = serializers.IntegerField()
	quiz_size = serializers.IntegerField()
	ready = serializers.BooleanField()
	# Bot deliveries this title needs (``GAME_MIN_PARTS`` capped by its parts).
	min_parts = serializers.IntegerField()


class VerifiedTitleSerializer(serializers.Serializer):
	id = serializers.IntegerField()
	title = serializers.CharField()
	type = serializers.CharField()
	points = serializers.IntegerField()
	verified_at = serializers.DateTimeField()


class GameTitlesSerializer(serializers.Serializer):
	"""Response of ``GET titles/``."""

	unlocked = UnlockedTitleSerializer(many=True)
	verified = VerifiedTitleSerializer(many=True)
	min_parts = serializers.IntegerField()


class QuizQuestionSerializer(serializers.Serializer):
	id = serializers.IntegerField()
	text = serializers.CharField()
	choices = serializers.ListField(child=serializers.CharField())


class QuizTitleSerializer(serializers.Serializer):
	id = serializers.IntegerField()
	title = serializers.CharField()


class QuizStartSerializer(serializers.Serializer):
	title_id = serializers.IntegerField()


class QuizSubmitSerializer(serializers.Serializer):
	attempt_id = serializers.IntegerField()
	answers = serializers.ListField(
		child=serializers.IntegerField(),
		allow_empty=False,
	)
	elapsed_ms = serializers.IntegerField(required=False, default=0, min_value=0)


class QuizStartResponseSerializer(serializers.Serializer):
	attempt_id = serializers.IntegerField()
	title = QuizTitleSerializer()
	questions = QuizQuestionSerializer(many=True)
	pass_score = serializers.IntegerField()


class QuizSubmitResponseSerializer(serializers.Serializer):
	correct = serializers.IntegerField()
	total = serializers.IntegerField()
	points_awarded = serializers.IntegerField()
	verified = serializers.BooleanField()
	suspicious = serializers.BooleanField()
	no_retry = serializers.BooleanField()


class LeaderboardSerializer(serializers.Serializer):
	"""Query of ``GET leaderboard/``; the response is :class:`LeaderboardResultSerializer`."""

	limit = serializers.IntegerField(required=False, default=50, min_value=1, max_value=200)


class LeaderboardEntrySerializer(serializers.Serializer):
	rank = serializers.IntegerField()
	user_id = serializers.IntegerField()
	name = serializers.CharField()
	points = serializers.IntegerField()
	verified = serializers.IntegerField()
	level = serializers.IntegerField()
	level_name = serializers.CharField()
	next_in = serializers.IntegerField()


class LeaderboardOwnSerializer(serializers.Serializer):
	rank = serializers.IntegerField()
	points = serializers.IntegerField()
	name = serializers.CharField()
	level = serializers.IntegerField()
	level_name = serializers.CharField()
	next_in = serializers.IntegerField()


class LeaderboardResultSerializer(serializers.Serializer):
	results = LeaderboardEntrySerializer(many=True)
	own = LeaderboardOwnSerializer(allow_null=True)
	month = serializers.CharField()
