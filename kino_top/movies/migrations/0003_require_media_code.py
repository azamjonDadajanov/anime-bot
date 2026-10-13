from django.db import migrations, models


def assign_missing_codes(apps, schema_editor):
	media_title = apps.get_model("movies", "MediaTitle")
	database = schema_editor.connection.alias
	used_codes = set(
		media_title.objects.using(database)
		.exclude(code__isnull=True)
		.values_list("code", flat=True)
	)
	available_codes = (str(number) for number in range(1000, 10000) if str(number) not in used_codes)

	for item in media_title.objects.using(database).filter(code__isnull=True).order_by("pk").iterator():
		try:
			item.code = next(available_codes)
		except StopIteration as exc:
			raise RuntimeError("Only 9000 four-digit media codes are available.") from exc
		item.save(update_fields=["code"])


class Migration(migrations.Migration):
	dependencies = [
		("movies", "0002_telegramchannel_mediatitle_code_and_more"),
	]

	operations = [
		migrations.RunPython(assign_missing_codes, migrations.RunPython.noop),
		migrations.AlterField(
			model_name="mediatitle",
			name="code",
			field=models.CharField(editable=False, max_length=4, unique=True),
		),
	]