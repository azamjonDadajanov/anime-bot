from django.db import migrations, models


class Migration(migrations.Migration):
	dependencies = [
		("users", "0004_create_existing_subscriptions"),
	]

	operations = [
		migrations.AddField(
			model_name="telegramuser",
			name="panel_message_id",
			field=models.PositiveBigIntegerField(blank=True, null=True),
		),
		migrations.AddField(
			model_name="telegramuser",
			name="panel_message_kind",
			field=models.CharField(default="text", max_length=8),
		),
		migrations.AddField(
			model_name="telegramuser",
			name="temporary_message_ids",
			field=models.JSONField(blank=True, default=list),
		),
	]