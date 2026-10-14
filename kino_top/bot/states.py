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
