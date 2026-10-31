from django.contrib.auth import authenticate, get_user_model, login
from django.db import IntegrityError
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from .artifact_models import (
	ArtifactPlayerProfile,
	CharacterClass,
	GamePortal,
	PlayerInventory,
)
from .battle_models import calculate_level_from_xp, xp_required_for_level
from .portal_engine import (
	enter_portal_and_claim_loot,
	evaluate_portal_for_player,
	get_or_create_player_profile,
)

User = get_user_model()


def max_hp_for_level(level: int) -> int:
	"""Daraja oshgani sari maksimal jon ham oshadi (100 + 25 har daraja)."""
	return 100 + max(0, int(level) - 1) * 25


def resolve_player_user(request):
	"""Foydalanuvchini aniqlash (Session, JWT, Telegram ID yoki Header orqali)."""
	# 1. Standart Django session / auth user
	if request.user and request.user.is_authenticated:
		return request.user

	# 2. Telegram ID header yoki query param
	tg_id = (
		request.headers.get("X-Telegram-ID")
		or request.data.get("telegram_id")
		or request.GET.get("tg_id")
	)
	if tg_id:
		try:
			from users.models import TelegramUser
			tg_user = TelegramUser.objects.filter(telegram_id=tg_id).select_related("auth_user").first()
			if tg_user and tg_user.auth_user:
				return tg_user.auth_user
			elif tg_user:
				# Agar auth_user ulanmagan bo'lsa, yaratib ulaymiz
				username = f"tg_{tg_id}"
				user, _ = User.objects.get_or_create(username=username, defaults={"first_name": tg_user.first_name})
				tg_user.auth_user = user
				tg_user.save(update_fields=["auth_user"])
				return user
			else:
				# Yangi telegram foydalanuvchi yaratish
				username = f"tg_{tg_id}"
				user, _ = User.objects.get_or_create(username=username)
				TelegramUser.objects.create(telegram_id=tg_id, auth_user=user)
				return user
		except Exception as e:
			print("Error resolving telegram user:", e)

	# 3. User ID header yoki request.data
	uid = request.headers.get("X-User-ID") or request.data.get("user_id")
	if uid:
		try:
			user = User.objects.filter(id=int(uid)).first()
			if user:
				return user
		except Exception:
			pass

	# 4. Sessiondagi player_user_id
	session = getattr(request, "session", None)
	session_uid = session.get("player_user_id") if session else None
	if session_uid:
		user = User.objects.filter(id=session_uid).first()
		if user:
			return user

	# 5. Fallback birinchi user yoki demo user
	demo_user, _ = User.objects.get_or_create(username="demo_hunter", defaults={"first_name": "Demo Hunter"})
	return demo_user


class ArtifactAuthView(APIView):
	"""Login, Register yoki Telegram avtomatik avtorizatsiya."""

	permission_classes = [AllowAny]

	def post(self, request):
		action = request.data.get("action", "login")

		# Telegram avto-kirish
		if action == "telegram":
			tg_id = request.data.get("telegram_id")
			first_name = request.data.get("first_name", "")
			username_tg = request.data.get("username", "")

			if not tg_id:
				return Response({"error": "telegram_id kiritilmadi"}, status=status.HTTP_400_BAD_REQUEST)

			from users.models import TelegramUser
			tg_user, created = TelegramUser.objects.get_or_create(
				telegram_id=tg_id,
				defaults={"first_name": first_name, "username": username_tg},
			)
			if not tg_user.auth_user:
				auth_username = f"tg_{tg_id}"
				auth_user, _ = User.objects.get_or_create(username=auth_username, defaults={"first_name": first_name})
				tg_user.auth_user = auth_user
				tg_user.save(update_fields=["auth_user"])

			user = tg_user.auth_user
			request.session["player_user_id"] = user.id
			profile = get_or_create_player_profile(user)

			return Response({
				"success": True,
				"user_id": user.id,
				"username": user.username,
				"first_name": tg_user.first_name,
				"character_class": profile.character_class,
				"position": {"x": profile.pos_x, "y": profile.pos_y, "z": profile.pos_z},
			})

		# Standart Login
		elif action == "login":
			username = request.data.get("username", "").strip()
			password = request.data.get("password", "").strip()
			user = authenticate(username=username, password=password)
			if not user:
				return Response({"error": "Login yoki parol noto'g'ri!"}, status=status.HTTP_401_UNAUTHORIZED)

			request.session["player_user_id"] = user.id
			profile = get_or_create_player_profile(user)

			return Response({
				"success": True,
				"user_id": user.id,
				"username": user.username,
				"character_class": profile.character_class,
				"position": {"x": profile.pos_x, "y": profile.pos_y, "z": profile.pos_z},
			})

		# Yangi hisob yaratish (Register)
		elif action == "register":
			username = request.data.get("username", "").strip()
			password = request.data.get("password", "").strip()
			if not username or not password:
				return Response({"error": "Login va parol kiritilishi shart!"}, status=status.HTTP_400_BAD_REQUEST)

			if User.objects.filter(username=username).exists():
				return Response({"error": "Ushbu login band, boshqa login tanlang!"}, status=status.HTTP_400_BAD_REQUEST)

			user = User.objects.create_user(username=username, password=password)
			request.session["player_user_id"] = user.id
			profile = get_or_create_player_profile(user)

			return Response({
				"success": True,
				"user_id": user.id,
				"username": user.username,
				"character_class": profile.character_class,
				"position": {"x": 0.0, "y": 0.0, "z": 0.0},
			})

		return Response({"error": "Noto'g'ri harakat"}, status=status.HTTP_400_BAD_REQUEST)


class ArtifactGameStateView(APIView):
	"""O'yinchi profili, saqlangan joylashuvi, inventari va barcha portallar."""

	permission_classes = [AllowAny]

	def get(self, request):
		user = resolve_player_user(request)
		if not user:
			return Response({"error": "Foydalanuvchi topilmadi"}, status=status.HTTP_401_UNAUTHORIZED)

		profile = get_or_create_player_profile(user)

		inventory_qs = PlayerInventory.objects.filter(player=profile).select_related("item")
		inventory = [
			{
				"id": item.id,
				"item_id": item.item.id,
				"name": item.item.name,
				"code": item.item.code,
				"rarity": item.item.rarity,
				"rarity_display": item.item.get_rarity_display(),
				"item_type": item.item.item_type,
				"power": item.item.power,
				"quantity": item.quantity,
				"is_equipped": item.is_equipped,
				"model_path": item.item.model_path,
				"icon_url": item.item.icon_url,
				"attributes": item.item.attributes,
			}
			for item in inventory_qs
		]

		portals_qs = GamePortal.objects.filter(is_active=True).prefetch_related("conditions", "loot_table__item")
		portals = [evaluate_portal_for_player(user, portal) for portal in portals_qs]

		calc_level, cur_xp, next_needed = calculate_level_from_xp(profile.experience)
		if calc_level != profile.level:
			profile.level = calc_level
			profile.save(update_fields=["level"])

		return Response({
			"player": {
				"id": user.id,
				"username": user.username,
				"character_class": profile.character_class,
				"character_class_display": profile.get_character_class_display(),
				"level": profile.level,
				"experience": profile.experience,
				"current_level_exp": cur_xp,
				"next_level_exp": next_needed,
				"coins": profile.coins,
				"gems": profile.gems,
				"position": {"x": profile.pos_x, "y": profile.pos_y, "z": profile.pos_z},
				"chests_opened": profile.chests_opened,
				"portals_cleared": profile.portals_cleared,
				"hp": profile.hp or max_hp_for_level(profile.level),
				"max_hp": max_hp_for_level(profile.level),
				"kills": profile.kills,
				"enemy_state": profile.enemy_state or {},
			},
			"inventory": inventory,
			"portals": portals,
		})


class SelectCharacterClassView(APIView):
	"""Qahramon kasbini tanlash va profilga mustahkamlash."""

	permission_classes = [AllowAny]

	def post(self, request):
		user = resolve_player_user(request)
		if not user:
			return Response({"error": "Foydalanuvchi topilmadi"}, status=status.HTTP_401_UNAUTHORIZED)

		chosen_class = request.data.get("character_class")
		if chosen_class not in CharacterClass.values:
			return Response(
				{"error": f"Noto'g'ri qahramon turi. Mumkin: {CharacterClass.values}"},
				status=status.HTTP_400_BAD_REQUEST,
			)

		profile = get_or_create_player_profile(user, character_class=chosen_class)
		return Response({
			"success": True,
			"character_class": profile.character_class,
			"character_class_display": profile.get_character_class_display(),
		})


class SavePlayerPositionView(APIView):
	"""O'yinchining oxirgi koordinatasi va holatini saqlash (chiqib ketishda yoki periodik)."""

	permission_classes = [AllowAny]

	def post(self, request):
		user = resolve_player_user(request)
		if not user:
			return Response({"error": "Foydalanuvchi topilmadi"}, status=status.HTTP_401_UNAUTHORIZED)

		profile = get_or_create_player_profile(user)
		try:
			profile.pos_x = float(request.data.get("x", profile.pos_x))
			profile.pos_y = float(request.data.get("y", profile.pos_y))
			profile.pos_z = float(request.data.get("z", profile.pos_z))
			char_class = request.data.get("character_class")
			if char_class and char_class in CharacterClass.values:
				profile.character_class = char_class
			profile.save(update_fields=["pos_x", "pos_y", "pos_z", "character_class"])
		except Exception as e:
			return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

		return Response({"success": True})


class EnterPortalView(APIView):
	"""Portalga kirib mukofot olish."""

	permission_classes = [AllowAny]

	def post(self, request):
		user = resolve_player_user(request)
		if not user:
			return Response({"error": "Foydalanuvchi topilmadi"}, status=status.HTTP_401_UNAUTHORIZED)

		portal_id = request.data.get("portal_id")
		if not portal_id:
			return Response({"error": "portal_id talab qilinadi"}, status=status.HTTP_400_BAD_REQUEST)

		result = enter_portal_and_claim_loot(user, portal_id=portal_id)
		if not result.get("success"):
			return Response(result, status=status.HTTP_403_FORBIDDEN)

		return Response(result)


class ArtifactCombatView(APIView):
	"""Jangovar holatni saqlash: jon, o'ldirilgan mahluqlar, tajriba va daraja.

	Klient jang natijasini yuboradi, server tajribani qo'shib darajani hisoblaydi
	va natijani bazaga saqlaydi. Bir so'rovda beriladigan tajriba cheklangan.
	"""

	permission_classes = [AllowAny]

	# Bir so'rovda olinishi mumkin bo'lgan maksimal tajriba (himoya)
	MAX_EXP_PER_REQUEST = 2000

	def post(self, request):
		user = resolve_player_user(request)
		if not user:
			return Response({"error": "Foydalanuvchi topilmadi"}, status=status.HTTP_401_UNAUTHORIZED)

		profile = get_or_create_player_profile(user)
		data = request.data or {}

		# 1. Tajriba (daraja shu yerda hisoblanadi)
		try:
			exp_gain = max(0, min(self.MAX_EXP_PER_REQUEST, int(data.get("exp_gained", 0))))
		except (TypeError, ValueError):
			exp_gain = 0
		if exp_gain:
			profile.experience += exp_gain

		new_level, cur_xp, next_needed = calculate_level_from_xp(profile.experience)
		leveled_up = new_level > profile.level
		profile.level = new_level

		# 2. Joriy jon (daraja oshgandan keyingi chegaraga moslab)
		if data.get("hp") is not None:
			try:
				profile.hp = max(0, min(max_hp_for_level(profile.level), int(data.get("hp"))))
			except (TypeError, ValueError):
				pass

		# 3. O'ldirilgan mahluqlar soni
		if data.get("kills") is not None:
			try:
				profile.kills = max(0, int(data.get("kills")))
			except (TypeError, ValueError):
				pass

		# 4. Mahluqlar holati (o'lim / 2 daqiqada qayta tiklanish vaqti)
		if isinstance(data.get("enemy_state"), dict):
			profile.enemy_state = data["enemy_state"]

		profile.save()

		return Response({
			"success": True,
			"level": profile.level,
			"experience": profile.experience,
			"current_level_exp": cur_xp,
			"next_level_exp": next_needed,
			"max_hp": max_hp_for_level(profile.level),
			"hp": profile.hp,
			"kills": profile.kills,
			"enemy_state": profile.enemy_state,
			"leveled_up": leveled_up,
		})


class ToggleEquipItemView(APIView):
	"""Buyumni taqish yoki yechish (Equip / Unequip)."""

	permission_classes = [AllowAny]

	def post(self, request):
		user = resolve_player_user(request)
		if not user:
			return Response({"error": "Foydalanuvchi topilmadi"}, status=status.HTTP_401_UNAUTHORIZED)

		item_id = request.data.get("item_id")
		inventory_id = request.data.get("inventory_id")

		profile = get_or_create_player_profile(user)
		try:
			if inventory_id:
				inv_item = PlayerInventory.objects.get(id=inventory_id, player=profile)
			else:
				inv_item = PlayerInventory.objects.get(item_id=item_id, player=profile)
		except PlayerInventory.DoesNotExist:
			return Response({"error": "Buyum inventarda topilmadi"}, status=status.HTTP_404_NOT_FOUND)

		# Holatni teskarisiga o'zgartirish
		new_state = not inv_item.is_equipped

		if new_state:
			# Agar bitta turdagi buyum bo'lsa (masalan: bitta asosiy qurol), o'sha turdagi boshqasini yechish
			same_type_items = PlayerInventory.objects.filter(
				player=profile,
				item__item_type=inv_item.item.item_type,
				is_equipped=True,
			)
			same_type_items.update(is_equipped=False)

		inv_item.is_equipped = new_state
		inv_item.save(update_fields=["is_equipped"])

		# Yangilangan butun inventarni qaytarish
		inventory_qs = PlayerInventory.objects.filter(player=profile).select_related("item")
		inventory = [
			{
				"id": item.id,
				"item_id": item.item.id,
				"name": item.item.name,
				"code": item.item.code,
				"rarity": item.item.rarity,
				"rarity_display": item.item.get_rarity_display(),
				"item_type": item.item.item_type,
				"power": item.item.power,
				"quantity": item.quantity,
				"is_equipped": item.is_equipped,
				"model_path": item.item.model_path,
				"icon_url": item.item.icon_url,
				"attributes": item.item.attributes,
			}
			for item in inventory_qs
		]

		return Response({
			"success": True,
			"equipped": inv_item.is_equipped,
			"item_id": inv_item.item.id,
			"inventory": inventory,
		})

