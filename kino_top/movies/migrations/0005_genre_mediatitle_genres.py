from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
	dependencies = [
		("movies", "0004_telegrammedia_source_message_id_and_more"),
	]

	operations = [
		migrations.CreateModel(
			name="Genre",
			fields=[
				("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
				("name", models.CharField(max_length=50, unique=True)),
			],
			options={"ordering": ["name"]},
		),
		migrations.AddField(
			model_name="mediatitle",
			name="genres",
			field=models.ManyToManyField(blank=True, related_name="media_titles", to="movies.genre"),
		),
	]