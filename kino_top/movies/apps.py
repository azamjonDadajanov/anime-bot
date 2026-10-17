from django.apps import AppConfig


class MoviesConfig(AppConfig):
    name = 'movies'

    def ready(self) -> None:
        # Importing the module registers the receivers that keep the AI search
        # index in sync with catalogue writes.
        from . import signals  # noqa: F401
