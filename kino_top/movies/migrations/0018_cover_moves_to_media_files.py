# Covers move from base64 blobs in the database to real media files.
#
# The old BinaryField is renamed first (so the name `cover` is free), then the
# ImageField that stores `covers/<name>.<ext>` under MEDIA_ROOT is added. The
# bytes are copied over by 0019 and the blob column is dropped by 0020.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('movies', '0017_delete_titleembedding'),
    ]

    operations = [
        migrations.RenameField(
            model_name='mediatitle',
            old_name='cover',
            new_name='cover_blob',
        ),
        migrations.AddField(
            model_name='mediatitle',
            name='cover',
            field=models.ImageField(blank=True, null=True, upload_to='covers/'),
        ),
    ]
