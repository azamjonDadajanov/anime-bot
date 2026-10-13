from django.conf import settings
from django.db import migrations


def create_existing_subscriptions(apps, schema_editor):
	app_label, model_name = settings.AUTH_USER_MODEL.split(".")
	user_model = apps.get_model(app_label, model_name)
	subscription_model = apps.get_model("users", "Subscription")
	database = schema_editor.connection.alias
	subscriptions = [
		subscription_model(user_id=user_id)
		for user_id in user_model.objects.using(database).values_list("pk", flat=True)
	]
	subscription_model.objects.using(database).bulk_create(subscriptions, ignore_conflicts=True)


class Migration(migrations.Migration):
	dependencies = [
		("users", "0003_subscription"),
		migrations.swappable_dependency(settings.AUTH_USER_MODEL),
	]

	operations = [
		migrations.RunPython(create_existing_subscriptions, migrations.RunPython.noop),
	]