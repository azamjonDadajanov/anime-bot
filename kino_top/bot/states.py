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
	select_title = State()
	season = State()
	number = State()
	title = State()
	channel = State()
	media = State()
	preview = State()


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


class AdminGenreStates(StatesGroup):
	name = State()
