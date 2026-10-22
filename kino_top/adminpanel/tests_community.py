"""Moderation of the shared comment + rating tables, from the panel's side.

The website and the bot write into the same rows, so one screen has to show
both sources; these tests pin that contract: staff-only access, the filters
the panel offers, bulk deletion, and the recomputation that keeps a title's
average honest after a score is removed.
"""

from django.contrib.auth import get_user_model
from django.test import TransactionTestCase
from rest_framework.test import APIClient

from movies.models import MediaPart, MediaTitle, TitleComment, TitleRating
from users.models import Subscription

COMMENTS = "/api/admin/comments/"
RATINGS = "/api/admin/ratings/"


class AdminCommunityTestCase(TransactionTestCase):
	"""One staff client (the panel), one ordinary writer and one title."""

	def setUp(self) -> None:
		super().setUp()
		self.staff = get_user_model().objects.create_user(
			username="panel-admin",
			email="panel@example.com",
			password="panel-secret-4829",
			is_staff=True,
		)
		self.writer = get_user_model().objects.create_user(
			username="aziz", password="aziz-secret-4829"
		)
		self.other = get_user_model().objects.create_user(
			username="doston", password="doston-secret-4829"
		)
		self.title = MediaTitle.objects.create(
			type=MediaTitle.MediaType.ANIME,
			title="Moderated Show",
			slug="moderated-show",
		)
		self.part = MediaPart.objects.create(content=self.title, number=1)
		self.client = APIClient()
		self.client.force_authenticate(self.staff)

	def _comment(self, *, body: str = "Birinchi fikr", part=None, source="site") -> TitleComment:
		comment = TitleComment(
			user=self.writer,
			title=self.title,
			part=part,
			body=body,
			source=source,
		)
		# The fingerprint is what stops a double submit; rows created directly
		# still have to carry one so the unique constraint stays honest.
		comment.dedupe_hash = comment.compute_dedupe_hash()
		comment.save()
		return comment

	def _score(self, score: int, user=None) -> TitleRating:
		rating = TitleRating.objects.create(
			user=user or self.writer, title=self.title, score=score
		)
		from movies.community import recompute_title_rating_sync

		recompute_title_rating_sync(self.title)
		return rating


class AdminCommentModerationTests(AdminCommunityTestCase):
	def test_the_list_is_staff_only(self):
		self._comment()

		anonymous = APIClient()
		guest_list = anonymous.get(COMMENTS)
		ordinary = APIClient()
		ordinary.force_authenticate(self.writer)
		ordinary_list = ordinary.get(COMMENTS)

		self.assertIn(guest_list.status_code, (401, 403))
		self.assertIn(ordinary_list.status_code, (401, 403))

	def test_every_source_shares_one_screen(self):
		self._comment(body="Saytdan", source="site")
		self._comment(body="Botdan", source="bot")

		response = self.client.get(COMMENTS)

		self.assertEqual(response.status_code, 200)
		self.assertEqual(response.data["count"], 2)
		sources = {row["source"] for row in response.data["results"]}
		self.assertEqual(sources, {"site", "bot"})

	def test_search_and_filters_narrow_the_list(self):
		self._comment(body="Ajoyib epizod")
		self._comment(body="Faqat botdan", source="bot", part=self.part)

		by_text = self.client.get(COMMENTS, {"search": "Ajoyib"})
		by_source = self.client.get(COMMENTS, {"source": "bot"})
		by_title_slug = self.client.get(COMMENTS, {"title": self.title.slug})
		by_title_id = self.client.get(COMMENTS, {"title": str(self.title.pk)})

		self.assertEqual(by_text.data["count"], 1)
		self.assertEqual(by_text.data["results"][0]["body"], "Ajoyib epizod")
		self.assertEqual(by_source.data["count"], 1)
		self.assertEqual(by_title_slug.data["count"], 2)
		self.assertEqual(by_title_id.data["count"], 2)

	def test_a_row_names_the_author_the_episode_and_the_crown(self):
		subscription, _ = Subscription.objects.get_or_create(user=self.writer)
		subscription.activate("monthly")
		self._comment(part=self.part)

		response = self.client.get(COMMENTS)

		row = response.data["results"][0]
		self.assertEqual(row["author"]["username"], "aziz")
		self.assertTrue(row["author"]["is_premium"])
		self.assertEqual(row["part_number"], 1)
		self.assertEqual(row["title_slug"], self.title.slug)

	def test_a_moderator_deletes_one_comment(self):
		comment = self._comment()

		response = self.client.delete(f"{COMMENTS}{comment.pk}/")

		self.assertEqual(response.status_code, 204)
		self.assertFalse(TitleComment.objects.exists())

	def test_bulk_delete_clears_only_what_was_asked(self):
		keep = self._comment(body="Qoladi")
		drop_a = self._comment(body="O'chiriladi 1")
		drop_b = self._comment(body="O'chiriladi 2")

		response = self.client.post(
			f"{COMMENTS}bulk-delete/", {"ids": [drop_a.pk, drop_b.pk]}, format="json"
		)

		self.assertEqual(response.status_code, 200)
		self.assertEqual(response.data["deleted"], 2)
		self.assertTrue(TitleComment.objects.filter(pk=keep.pk).exists())

	def test_bulk_delete_rejects_a_non_list_payload(self):
		response = self.client.post(
			f"{COMMENTS}bulk-delete/", {"ids": "not-a-list"}, format="json"
		)

		self.assertEqual(response.status_code, 400)


class AdminRatingModerationTests(AdminCommunityTestCase):
	def test_the_list_is_staff_only_and_carries_the_score(self):
		self._score(8)

		anonymous = APIClient()
		guest = anonymous.get(RATINGS)
		mine = self.client.get(RATINGS)

		self.assertIn(guest.status_code, (401, 403))
		self.assertEqual(mine.status_code, 200)
		self.assertEqual(mine.data["count"], 1)
		row = mine.data["results"][0]
		self.assertEqual(row["score"], 8)
		self.assertEqual(row["author"]["username"], "aziz")
		self.assertEqual(row["title_slug"], self.title.slug)

	def test_score_bounds_filter_the_list(self):
		self._score(3, user=self.writer)
		self._score(9, user=self.other)

		low = self.client.get(RATINGS, {"min_score": 1, "max_score": 5})
		high = self.client.get(RATINGS, {"min_score": 6})

		self.assertEqual(low.data["count"], 1)
		self.assertEqual(low.data["results"][0]["score"], 3)
		self.assertEqual(high.data["count"], 1)
		self.assertEqual(high.data["results"][0]["score"], 9)

	def test_deleting_one_score_recomputes_the_average(self):
		self._score(4, user=self.writer)
		self._score(6, user=self.other)
		self.title.refresh_from_db()
		self.assertEqual(self.title.rating_count, 2)
		rating = TitleRating.objects.filter(score=4).get()

		response = self.client.delete(f"{RATINGS}{rating.pk}/")

		self.assertEqual(response.status_code, 204)
		self.title.refresh_from_db()
		self.assertEqual(self.title.rating_count, 1)
		self.assertEqual(self.title.rating_average, 6.0)

	def test_bulk_delete_recomputes_every_touched_title(self):
		first = self._score(2, user=self.writer)
		second = self._score(10, user=self.other)
		self.title.refresh_from_db()
		self.assertEqual(self.title.rating_count, 2)

		response = self.client.post(
			f"{RATINGS}bulk-delete/", {"ids": [first.pk, second.pk]}, format="json"
		)

		self.assertEqual(response.status_code, 200)
		self.assertEqual(response.data["title_ids"], [self.title.pk])
		self.assertFalse(TitleRating.objects.exists())
		self.title.refresh_from_db()
		self.assertEqual(self.title.rating_count, 0)
		self.assertEqual(self.title.rating_average, 0.0)
