"""FSM state groups used by the user and administrator flows."""

from aiogram.fsm.state import State, StatesGroup


class UserSearchStates(StatesGroup):
	query = State()
	results = State()


class UserBrowseStates(StatesGroup):
	catalog = State()
	part = State()


class UserSubscriptionStates(StatesGroup):
	"""Waiting for the payment screenshot of a chosen plan."""

	awaiting_screenshot = State()


class UserCouponStates(StatesGroup):
	"""Waiting for a promo code to redeem."""

	code = State()


class UserSupportStates(StatesGroup):
	"""Waiting for the message the user wants the administrators to read."""

	message = State()


class UserAssistantStates(StatesGroup):
	"""Waiting for the message the AI yordamchi has to answer."""

	query = State()


class UserQuizStates(StatesGroup):
	"""One question of the in-bot quiz; the FSM data carries the attempt.

	``quiz_id`` — attempt pk, ``quiz_index`` / ``quiz_total`` — progress,
	``quiz_answers`` / ``quiz_elapsed`` — what was collected so far,
	``quiz_at`` — the moment the current question was asked (seconds),
	``quiz_msg_id`` — the question message (deleted before the next one),
	``quiz_title`` — the media title, ``quiz_pass_score`` — needed correct.
	"""

	question = State()


class AdminMediaStates(StatesGroup):
	search = State()
	select_type = State()
	title = State()
	synopsis = State()
	cover = State()
	genres = State()
	language = State()
	quality = State()
	plan = State()
	status = State()
	rating = State()
	preview = State()
	edit_value = State()


class AdminEpisodeStates(StatesGroup):
	"""Episode uploader.

	``season`` collects the season number, ``channel`` only appears when more
	than one Cloud channel exists, and ``media`` is the bulk-upload step where
	every incoming file becomes its own part until ``💾 Saqlash`` is pressed.
	"""

	season = State()
	channel = State()
	media = State()


class AdminChannelStates(StatesGroup):
	select_purpose = State()
	chat = State()
	title = State()
	username = State()
	preview = State()
	edit_value = State()
	awaiting_forward = State()


class AdminBroadcastStates(StatesGroup):
	select_kind = State()
	compose = State()
	awaiting_forward = State()
	preview = State()
	running = State()


class AdminUserStates(StatesGroup):
	query = State()
	edit_plan = State()


class AdminSettingsStates(StatesGroup):
	edit_value = State()


class AdminCouponStates(StatesGroup):
	"""Three-step coupon builder: duration, audience size, then the code."""

	days = State()
	uses = State()
	code = State()


class AdminGiveawayStates(StatesGroup):
	"""Giveaway builder: name, reward, winners, condition, flags."""

	ask_title = State()
	ask_days = State()
	ask_winners = State()
	ask_min_views = State()
	flags = State()


class AdminGenreStates(StatesGroup):
	name = State()
