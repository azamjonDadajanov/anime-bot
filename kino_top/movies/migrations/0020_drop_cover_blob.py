# Drop the old cover blob column: every cover now lives on the media volume.

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('movies', '0019_migrate_covers_to_files'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='mediatitle',
            name='cover_blob',
        ),
    ]
