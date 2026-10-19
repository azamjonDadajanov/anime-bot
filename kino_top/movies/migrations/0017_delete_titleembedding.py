from django.db import migrations


class Migration(migrations.Migration):
    """The offline sentence encoder is gone: its vector table goes with it.

    The AI assistant now asks the online model, which calls catalogue
    functions, so no per-title vectors are stored or read anywhere.
    """

    dependencies = [
        ("movies", "0016_aiprovider"),
    ]

    operations = [
        migrations.DeleteModel(
            name="TitleEmbedding",
        ),
    ]
