"""Keep the AI index in sync with the catalogue.

Every write path — the Django admin, the DRF catalogue API behind the web
administrator panel, the bot's media uploader, an import command — goes through
the ORM, so receivers are the one place that catches all of them and neither the
API nor the bot handlers have to remember to re-embed anything.

All receivers are *deferred* (``transaction.on_commit``) and *best effort*: the
index is derived data, so a catalogue write must succeed even when the embedding
model is unavailable; the title then simply stays unindexed until
``python manage.py index_anime_embeddings`` runs.

Deleting a title needs no receiver at all: ``TitleEmbedding.title`` cascades.
"""

from __future__ import annotations

import logging

from django.db.models.signals import m2m_changed, post_save
from django.dispatch import receiver

from . import ai_search
from .models import Genre, MediaTitle

logger = logging.getLogger(__name__)

# ``pre_*`` actions run before the rows exist; only the post hooks describe the
# state the document has to be built from.
GENRE_ACTIONS = frozenset({"post_add", "post_remove", "post_clear"})


@receiver(post_save, sender=MediaTitle, dispatch_uid="ai_index_media_title")
def index_media_title(sender, instance, **kwargs) -> None:
	"""Re-embed a title after it was created or edited.

	``index_title`` compares the document digest first, so a save that changed
	nothing the model can see (a cover upload, a quality flag) costs one query
	and no inference.
	"""
	ai_search.schedule_index(instance.pk)


@receiver(m2m_changed, sender=MediaTitle.genres.through, dispatch_uid="ai_index_media_genres")
def index_media_genres(sender, instance, action, reverse, pk_set, **kwargs) -> None:
	"""Genres are part of the document, so attaching them re-embeds the title."""
	if action not in GENRE_ACTIONS:
		return
	if reverse:
		# ``genre.media_titles.add(...)``: ``instance`` is the Genre and every
		# title in ``pk_set`` changed. ``post_clear`` has no pk_set (the rows are
		# already gone) and is not used by this project's write paths.
		if pk_set:
			ai_search.schedule_index_all(list(pk_set))
		return
	if instance is not None and instance.pk:
		ai_search.schedule_index(instance.pk)


@receiver(post_save, sender=Genre, dispatch_uid="ai_index_genre_rename")
def index_genre_titles(sender, instance, created, **kwargs) -> None:
	"""A renamed genre rewrites the document of every title that carries it."""
	if created or not ai_search.enabled():
		return
	title_ids = list(
		MediaTitle.objects.filter(genres=instance).values_list("pk", flat=True)
	)
	if title_ids:
		logger.debug("Genre %s changed; re-checking %s titles", instance.pk, len(title_ids))
		ai_search.schedule_index_all(title_ids)
