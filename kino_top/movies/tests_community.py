"""The shared comment + 1-10 rating system, as the website sees it.

One table serves the site, the bot and the administrator panel, so these tests
pin the contract every platform relies on: one score per user, a duplicate text
never becomes a second comment, the crown follows a live subscription, and
every write leaves the stored average in step.
"""

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from users.models import Subscription

from .models import Genre, MediaPart, MediaTitle, TitleComment, TitleRating


def _make_title(slug: str, **overrides) -> MediaTitle:
	return MediaTitle.objects.create(
		type=MediaTitle.MediaType.ANIME,
		title=slug.replace("-", " ").title(),
		slug=slug,
		**overrides,
	)


def _make_premium(user, plan: str = "monthly") -> Subscription:
	subscription, _ = Subscription.objects.get_or_create(user=user)
	subscription.activate(plan)
	return subscription


class CommentApiTests(TestCase):
	def setUp(self):
		self.client = APIClient()
		self.user = get_user_model().objects.create_user(
			username="aziz", password="aziz-secret-4829"
		)
		self.other = get_user_model().objects.create_user(
			username="doston", password="doston-secret-4829"
		)
		self.title = _make_title("samurai-x")
		self.part = MediaPart.objects.create(content=self.title, number=1)

	def _list(self, **params):
		query = {"title": self.title.slug, **params}
		return self.client.get("/api/comments/", query)

	def test_listing_requires_a_title_parameter(self):
		response = self.client.get("/api/comments/")

		self.assertEqual(response.status_code, 400)
		self.assertEqual(response.data["code"], "title_required")

	def test_an_unknown_title_slug_is_a_404(self):
		response = self.client.get("/api/comments/", {"title": "no-such-title"})

		self.assertEqual(response.status_code, 404)

	def test_an_episode_from_another_title_is_rejected(self):
		other_title = _make_title("other-show")
		foreign_part = MediaPart.objects.create(content=other_title, number=1)
		self.client.force_authenticate(self.user)

		response = self.client.post(
			"/api/comments/",
			{"title": self.title.slug, "body": "Salom", "part": foreign_part.pk},
			format="json",
		)

		self.assertEqual(response.status_code, 400)
		self.assertFalse(TitleComment.objects.exists())

	def test_posting_requires_an_account(self):
		response = self.client.post(
			"/api/comments/",
			{"title": self.title.slug, "body": "Salom"},
			format="json",
		)

		self.assertIn(response.status_code, (401, 403))
		self.assertFalse(TitleComment.objects.exists())

	def test_a_comment_carries_its_author_and_the_crown_flag(self):
		_make_premium(self.user)
		self.client.force_authenticate(self.user)
		posted = self.client.post(
			"/api/comments/",
			{"title": self.title.slug, "body": "Ajoyib serial!"},
			format="json",
		)

		self.assertEqual(posted.status_code, 201)
		self.assertTrue(posted.data["created"])
		self.assertEqual(posted.data["comment"]["source"], "site")
		self.assertTrue(posted.data["comment"]["author"]["is_premium"])

		self.client.force_authenticate(self.other)
		self.client.post(
			"/api/comments/",
			{"title": self.title.slug, "body": "Oddiy fikr"},
			format="json",
		)
		listed = self._list()

		self.assertEqual(listed.status_code, 200)
		self.assertEqual(listed.data["count"], 2)
		authors = {row["author"]["username"]: row for row in listed.data["results"]}
		self.assertTrue(authors["aziz"]["author"]["is_premium"])
		self.assertFalse(authors["doston"]["author"]["is_premium"])

	def test_the_same_text_twice_stays_one_comment(self):
		self.client.force_authenticate(self.user)
		payload = {"title": self.title.slug, "body": "Bir xil fikr"}

		first = self.client.post("/api/comments/", payload, format="json")
		second = self.client.post("/api/comments/", payload, format="json")

		self.assertEqual(first.status_code, 201)
		self.assertEqual(second.status_code, 200)
		self.assertTrue(first.data["created"])
		self.assertFalse(second.data["created"])
		self.assertEqual(TitleComment.objects.filter(user=self.user).count(), 1)

	def test_a_comment_may_be_attached_to_an_episode(self):
		self.client.force_authenticate(self.user)

		response = self.client.post(
			"/api/comments/",
			{"title": self.title.slug, "body": "1-qism zo'r", "part": self.part.pk},
			format="json",
		)

		self.assertEqual(response.status_code, 201)
		self.assertEqual(response.data["comment"]["part"]["number"], 1)

	def test_an_empty_or_overlong_body_is_rejected(self):
		self.client.force_authenticate(self.user)

		empty = self.client.post(
			"/api/comments/", {"title": self.title.slug, "body": "   "}, format="json"
		)
		long = self.client.post(
			"/api/comments/",
			{"title": self.title.slug, "body": "a" * 1001},
			format="json",
		)

		self.assertEqual(empty.status_code, 400)
		self.assertEqual(long.status_code, 400)
		self.assertFalse(TitleComment.objects.exists())

	def test_only_the_author_or_a_staff_member_may_delete(self):
		self.client.force_authenticate(self.user)
		posted = self.client.post(
			"/api/comments/",
			{"title": self.title.slug, "body": "O'chiriladi"},
			format="json",
		)
		comment_id = posted.data["comment"]["id"]

		self.client.force_authenticate(self.other)
		forbidden = self.client.delete(f"/api/comments/{comment_id}/")

		self.assertEqual(forbidden.status_code, 403)
		self.assertTrue(TitleComment.objects.filter(pk=comment_id).exists())

		self.client.force_authenticate(self.user)
		allowed = self.client.delete(f"/api/comments/{comment_id}/")

		self.assertEqual(allowed.status_code, 204)
		self.assertFalse(TitleComment.objects.filter(pk=comment_id).exists())

	def test_a_staff_member_may_delete_anyone_s_comment(self):
		self.client.force_authenticate(self.other)
		posted = self.client.post(
			"/api/comments/",
			{"title": self.title.slug, "body": "Haqorat"},
			format="json",
		)
		comment_id = posted.data["comment"]["id"]
		staff = get_user_model().objects.create_user(
			username="moderator", password="mod-secret-4829", is_staff=True
		)

		self.client.force_authenticate(staff)
		response = self.client.delete(f"/api/comments/{comment_id}/")

		self.assertEqual(response.status_code, 204)
		self.assertFalse(TitleComment.objects.exists())

	def test_comments_of_other_titles_never_leak_into_the_page(self):
		other_title = _make_title("other-show")
		self.client.force_authenticate(self.other)
		self.client.post(
			"/api/comments/",
			{"title": other_title.slug, "body": "Boshqa serialdan"},
			format="json",
		)
		self.client.force_authenticate(self.user)
		self.client.post(
			"/api/comments/", {"title": self.title.slug, "body": "Shu serialdan"}, format="json"
		)

		listed = self._list()

		self.assertEqual(listed.data["count"], 1)
		self.assertEqual(listed.data["results"][0]["body"], "Shu serialdan")


class RatingApiTests(TestCase):
	def setUp(self):
		self.client = APIClient()
		self.user = get_user_model().objects.create_user(
			username="aziz", password="aziz-secret-4829"
		)
		self.other = get_user_model().objects.create_user(
			username="doston", password="doston-secret-4829"
		)
		self.title = _make_title("rating-show")

	def _rating_url(self) -> str:
		return f"/api/catalog/{self.title.slug}/rating/"

	def _refresh(self):
		self.title.refresh_from_db()
		return self.title

	def test_scoring_writes_one_row_and_updates_the_average(self):
		self.client.force_authenticate(self.user)
		self.client.post(self._rating_url(), {"score": 6}, format="json")
		self.client.force_authenticate(self.other)
		self.client.post(self._rating_url(), {"score": 9}, format="json")

		self.assertEqual(TitleRating.objects.filter(title=self.title).count(), 2)
		refreshed = self._refresh()
		self.assertEqual(refreshed.rating_average, 7.5)
		self.assertEqual(refreshed.rating_count, 2)
		# The legacy single number stays in step with the live average.
		self.assertEqual(int(refreshed.rating), 8)

	def test_changing_my_score_replaces_it_instead_of_adding(self):
		self.client.force_authenticate(self.user)
		self.client.post(self._rating_url(), {"score": 4}, format="json")
		self.client.post(self._rating_url(), {"score": 10}, format="json")

		row = TitleRating.objects.get(user=self.user, title=self.title)
		self.assertEqual(row.score, 10)
		refreshed = self._refresh()
		self.assertEqual(refreshed.rating_count, 1)
		self.assertEqual(refreshed.rating_average, 10.0)

	def test_anonymous_scoring_is_refused(self):
		response = self.client.post(self._rating_url(), {"score": 8}, format="json")

		self.assertEqual(response.status_code, 401)
		self.assertFalse(TitleRating.objects.exists())

	def test_a_score_outside_one_to_ten_is_rejected(self):
		self.client.force_authenticate(self.user)

		too_small = self.client.post(self._rating_url(), {"score": 0}, format="json")
		too_big = self.client.post(self._rating_url(), {"score": 11}, format="json")

		self.assertEqual(too_small.status_code, 400)
		self.assertEqual(too_big.status_code, 400)
		self.assertFalse(TitleRating.objects.exists())

	def test_the_summary_returns_my_score_and_the_totals(self):
		self.client.force_authenticate(self.user)
		self.client.post(self._rating_url(), {"score": 7}, format="json")

		response = self.client.get(self._rating_url())

		self.assertEqual(response.status_code, 200)
		self.assertEqual(response.data["average"], 7.0)
		self.assertEqual(response.data["count"], 1)
		self.assertEqual(response.data["my_score"], 7)
		self.assertEqual(response.data["min"], 1)
		self.assertEqual(response.data["max"], 10)

	def test_an_anonymous_summary_has_no_my_score(self):
		self.client.force_authenticate(self.user)
		self.client.post(self._rating_url(), {"score": 7}, format="json")

		anonymous = APIClient()
		response = anonymous.get(self._rating_url())

		self.assertIsNone(response.data["my_score"])
		self.assertEqual(response.data["count"], 1)

	def test_a_comment_may_carry_the_score_without_duplicating_it(self):
		self.client.force_authenticate(self.user)

		response = self.client.post(
			"/api/comments/",
			{"title": self.title.slug, "body": "Zo'r!", "rating": 8},
			format="json",
		)

		self.assertEqual(response.status_code, 201)
		self.assertEqual(response.data["rating"]["my_score"], 8)
		self.assertEqual(TitleRating.objects.filter(user=self.user).count(), 1)

	def test_deleting_a_comment_never_touches_the_score(self):
		self.client.force_authenticate(self.user)
		posted = self.client.post(
			"/api/comments/",
			{"title": self.title.slug, "body": "Keyin o'chiraman", "rating": 9},
			format="json",
		)
		comment_id = posted.data["comment"]["id"]

		self.client.delete(f"/api/comments/{comment_id}/")

		self.assertFalse(TitleComment.objects.exists())
		self.assertEqual(TitleRating.objects.get(user=self.user).score, 9)
		self.assertEqual(self._refresh().rating_count, 1)


class TopRatingRankingTests(TestCase):
	"""«Top reyting»: the highest average, the most votes deciding a tie.

	The widget and the full ``Mashhurlar`` list must agree, otherwise the
	fifth row on the homepage is not the fifth row of the page it links to.
	"""

	def setUp(self):
		self.client = APIClient()
		self.people = [
			get_user_model().objects.create_user(
				username=f"voter{index}", password=f"voter-secret-{index}"
			)
			for index in range(4)
		]

	def _score(self, title: MediaTitle, user, score: int) -> None:
		self.client.force_authenticate(user)
		self.client.post(
			f"/api/catalog/{title.slug}/rating/", {"score": score}, format="json"
		)

	def _slugs(self, path: str, **params) -> list:
		response = self.client.get(path, params)
		self.assertEqual(response.status_code, 200)
		rows = response.data["results"] if isinstance(response.data, dict) else response.data
		return [row["slug"] for row in rows]

	def test_the_average_decides_before_the_vote_count(self):
		beloved = _make_title("beloved-show")
		liked = _make_title("liked-show")
		# One 9 beats three 8s on the average, even with fewer votes.
		self._score(beloved, self.people[0], 9)
		for person in self.people[:3]:
			self._score(liked, person, 8)

		slugs = self._slugs("/api/catalog/top-rated/")

		self.assertEqual(slugs[:2], [beloved.slug, liked.slug])

	def test_equal_averages_rank_the_title_with_more_votes_first(self):
		agreed = _make_title("agreed-show")
		lonely = _make_title("lonely-show")
		self._score(agreed, self.people[0], 9)
		self._score(agreed, self.people[1], 9)
		self._score(lonely, self.people[2], 9)

		slugs = self._slugs("/api/catalog/top-rated/")

		self.assertEqual(slugs[:2], [agreed.slug, lonely.slug])

	def test_unscored_titles_are_left_out_and_the_limit_is_honoured(self):
		scored = _make_title("scored-show")
		_make_title("unscored-show", rating=10)
		self._score(scored, self.people[0], 6)

		all_ranked = self._slugs("/api/catalog/top-rated/")
		limited = self._slugs("/api/catalog/top-rated/", limit=1)

		self.assertEqual(all_ranked, [scored.slug])
		self.assertEqual(len(limited), 1)

	def test_without_any_score_the_catalogue_rating_still_fills_the_section(self):
		best = MediaTitle.objects.create(
			type=MediaTitle.MediaType.ANIME,
			title="Editor Favourite",
			slug="editor-favourite",
			rating=10,
		)
		MediaTitle.objects.create(
			type=MediaTitle.MediaType.ANIME,
			title="Editor Runner Up",
			slug="editor-runner-up",
			rating=4,
		)

		slugs = self._slugs("/api/catalog/top-rated/")

		self.assertEqual(slugs[:1], [best.slug])

	def test_the_full_popular_list_uses_the_same_ranking(self):
		agreed = _make_title("agreed-show")
		lonely = _make_title("lonely-show")
		self._score(agreed, self.people[0], 7)
		self._score(agreed, self.people[1], 7)
		self._score(lonely, self.people[2], 7)

		top = self._slugs("/api/catalog/top-rated/", limit=2)
		popular = self._slugs("/api/catalog/popular/")

		self.assertEqual(popular[:2], top)


class SimilarTitlesApiTests(TestCase):
	def setUp(self):
		self.client = APIClient()
		self.action = Genre.objects.create(name="Action")
		self.title = _make_title("hero-show")
		self.title.genres.add(self.action)

	def test_shared_genres_rank_first_and_self_is_never_listed(self):
		close = _make_title("close-show")
		close.genres.add(self.action)
		other_type = MediaTitle.objects.create(
			type=MediaTitle.MediaType.MOVIE,
			title="Action Movie",
			slug="action-movie",
		)
		other_type.genres.add(self.action)
		_make_title("unrelated-show")

		response = self.client.get(f"/api/catalog/{self.title.slug}/similar/")

		self.assertEqual(response.status_code, 200)
		slugs = [row["slug"] for row in response.data["results"]]
		self.assertEqual(response.data["count"], len(slugs))
		self.assertNotIn(self.title.slug, slugs)
		self.assertEqual(len(set(slugs)), len(slugs))
		# The strongest match (same format + shared genre) leads the rail, and a
		# cross-format row may only fill in after every same-format title.
		self.assertEqual(slugs[0], "close-show")
		self.assertIn("action-movie", slugs)
		self.assertLess(slugs.index("close-show"), slugs.index("unrelated-show"))
		self.assertLess(slugs.index("unrelated-show"), slugs.index("action-movie"))

	def test_the_limit_is_clamped_and_the_default_is_a_dozen(self):
		for index in range(15):
			twin = _make_title(f"twin-show-{index}")
			twin.genres.add(self.action)

		default = self.client.get(f"/api/catalog/{self.title.slug}/similar/")
		huge = self.client.get(f"/api/catalog/{self.title.slug}/similar/", {"limit": 999})

		self.assertLessEqual(len(default.data["results"]), 12)
		self.assertLessEqual(len(huge.data["results"]), 30)
		self.assertEqual(huge.data["count"], len(huge.data["results"]))


class DetailCarriesRatingTests(TestCase):
	def setUp(self):
		self.client = APIClient()
		self.user = get_user_model().objects.create_user(
			username="aziz", password="aziz-secret-4829"
		)
		self.title = _make_title("detail-show")

	def test_the_detail_page_reports_the_live_average_and_my_score(self):
		self.client.force_authenticate(self.user)
		self.client.post(
			"/api/comments/",
			{"title": self.title.slug, "body": "Fikrim", "rating": 8},
			format="json",
		)

		response = self.client.get(f"/api/catalog/{self.title.slug}/")

		self.assertEqual(response.status_code, 200)
		self.assertEqual(response.data["rating_average"], 8.0)
		self.assertEqual(response.data["rating_count"], 1)
		self.assertEqual(response.data["my_rating"], 8)
		self.assertEqual(response.data["comments_count"], 1)
