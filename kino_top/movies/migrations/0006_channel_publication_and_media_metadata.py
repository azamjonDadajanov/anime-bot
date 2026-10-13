import django.db.models.deletion
from django.db import migrations, models
import movies.models


class Migration(migrations.Migration):
	dependencies = [
		("movies", "0005_genre_mediatitle_genres"),
	]

	operations = [
		migrations.AddField(
			model_name="telegramchannel",
			name="is_public",
			field=models.BooleanField(default=False),
		),
		migrations.AddField(
			model_name="mediatitle",
			name="available_plans",
			field=models.JSONField(blank=True, default=movies.models.default_available_plans),
		),
		migrations.AddField(
			model_name="mediatitle",
			name="default_quality",
			field=models.CharField(default="1080", max_length=20),
		),
		migrations.AddField(
			model_name="mediatitle",
			name="episode_count",
			field=models.PositiveSmallIntegerField(blank=True, null=True),
		),
		migrations.AddField(
			model_name="mediatitle",
			name="language",
			field=models.CharField(default="O'zbekcha", max_length=40),
		),
		migrations.AddField(
			model_name="mediatitle",
			name="rating",
			field=models.PositiveSmallIntegerField(default=5),
		),
		migrations.AddField(
			model_name="mediatitle",
			name="quality_options",
			field=models.JSONField(blank=True, default=list),
		),
		migrations.AddField(
			model_name="mediatitle",
			name="metadata_channel",
			field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="metadata_posts", to="movies.telegramchannel"),
		),
		migrations.AddField(
			model_name="mediatitle",
			name="metadata_message_id",
			field=models.PositiveBigIntegerField(blank=True, null=True),
		),
	]