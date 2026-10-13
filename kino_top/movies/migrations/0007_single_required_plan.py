from django.db import migrations, models


PLAN_ORDER = ("free", "plus", "pro")


def migrate_available_plans(apps, schema_editor):
	media_model = apps.get_model("movies", "MediaTitle")
	database = schema_editor.connection.alias
	for content in media_model.objects.using(database).only("pk", "available_plans").iterator():
		plans = set(content.available_plans or [])
		required_plan = next((plan for plan in PLAN_ORDER if plan in plans), "free")
		media_model.objects.using(database).filter(pk=content.pk).update(required_plan=required_plan)


class Migration(migrations.Migration):
	dependencies = [
		("movies", "0006_channel_publication_and_media_metadata"),
	]

	operations = [
		migrations.AddField(
			model_name="mediatitle",
			name="required_plan",
			field=models.CharField(
				choices=[("free", "Free"), ("plus", "Plus"), ("pro", "Pro")],
				default="free",
				max_length=4,
			),
		),
		migrations.RunPython(migrate_available_plans, migrations.RunPython.noop),
		migrations.RemoveField(
			model_name="mediatitle",
			name="available_plans",
		),
	]
