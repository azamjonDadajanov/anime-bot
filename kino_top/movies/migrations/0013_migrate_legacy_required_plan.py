"""Collapse content gating tiers: ``plus``/``pro`` both become ``paid``.

Content is now either open to everyone (``free``) or reserved for a live
subscription (``paid``).
"""

from django.db import migrations

LEGACY_MAPPING = {"plus": "paid", "pro": "paid"}


def forwards(apps, schema_editor):
	MediaTitle = apps.get_model("movies", "MediaTitle")
	for old, new in LEGACY_MAPPING.items():
		MediaTitle.objects.filter(required_plan=old).update(required_plan=new)


def backwards(apps, schema_editor):
	MediaTitle = apps.get_model("movies", "MediaTitle")
	MediaTitle.objects.filter(required_plan="paid").update(required_plan="plus")


class Migration(migrations.Migration):

	dependencies = [
		("movies", "0012_alter_mediatitle_required_plan"),
	]

	operations = [
		migrations.RunPython(forwards, backwards),
	]
