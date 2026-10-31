from datetime import timedelta
import random
from django.utils import timezone
from django.db import transaction
from django.db.models import Sum

from movies.models import MediaView, TitleComment
from users.models import Subscription, SupportMessage
from .artifact_models import (
	ArtifactPlayerProfile,
	GameItem,
	GamePortal,
	PlayerInventory,
	PortalAccessLog,
	PortalCondition,
	ConditionType,
)


def get_or_create_player_profile(user, character_class=None):
	"""Foydalanuvchining o'yin profilini olish yoki yaratish."""
	profile, created = ArtifactPlayerProfile.objects.get_or_create(
		user=user,
		defaults={"character_class": character_class or "warrior"},
	)
	if character_class and profile.character_class != character_class:
		profile.character_class = character_class
		profile.save(update_fields=["character_class"])
	return profile


def check_single_condition(user, profile, condition: PortalCondition) -> dict:
	"""Bitta shartni foydalanuvchining Anichopar tizimidagi faolligiga qarab tekshirish."""
	cond_type = condition.condition_type
	target = condition.target_value
	current_value = 0
	is_met = False
	hint = condition.hint_message

	if cond_type == ConditionType.WATCH_ANIME_COUNT:
		# Ko'rilgan animelar soni
		current_value = MediaView.objects.filter(user=user).values("part__title").distinct().count()
		is_met = current_value >= target
		if not hint:
			hint = f"Anichoparda kamida {target} ta anime ko'ring (Hozir: {current_value}/{target})"

	elif cond_type == ConditionType.WATCH_ANIME_HOURS:
		# So'nggi 24 soat ichidagi ko'rishlar (har bir qism o'rtacha 20 daqiqa deb olinadi yoki soni)
		since = timezone.now() - timedelta(hours=24)
		views_24h = MediaView.objects.filter(user=user, created_at__gte=since).count()
		# Daqiqada hisoblasak: har bir view ~ 20 daqiqa
		current_value = views_24h * 20
		is_met = current_value >= target
		if not hint:
			hint = f"Bugun kamida {target} daqiqa anime tomosha qiling (Hozir: {current_value} daqiqa)"

	elif cond_type == ConditionType.WATCH_SPECIFIC_TITLE:
		# Maxsus animeni ko'rganlik
		if condition.custom_title:
			has_viewed = MediaView.objects.filter(user=user, media_part__title=condition.custom_title).exists()
			current_value = 1 if has_viewed else 0
			is_met = has_viewed
			if not hint:
				hint = f"'{condition.custom_title.title_uz or condition.custom_title.title_en}' animesini tomosha qiling"
		else:
			is_met = True

	elif cond_type == ConditionType.HAS_ACTIVE_SUBSCRIPTION:
		# VIP obuna mavjudligi
		active_sub = Subscription.objects.filter(
			user=user,
			expires_at__gt=timezone.now(),
		).exists()
		current_value = 1 if active_sub else 0
		is_met = active_sub
		if not hint:
			hint = "Ushbu elita portaliga kirish uchun VIP obunaga ega bo'lishingiz kerak"

	elif cond_type == ConditionType.COMMENT_COUNT:
		# Kommentariya / fikrlar soni
		current_value = TitleComment.objects.filter(user=user).count()
		is_met = current_value >= target
		if not hint:
			hint = f"Animelarga kamida {target} ta izoh/fikr yozing (Hozir: {current_value}/{target})"

	elif cond_type == ConditionType.BUG_REPORT_ACCEPTED:
		# Adminga xato yoki fikr yuborganlik
		current_value = SupportMessage.objects.filter(user=user).count()
		is_met = current_value >= target
		if not hint:
			hint = f"Bot orqali adminga xato yoki taklif yuboring (Hozir: {current_value}/{target})"

	elif cond_type == ConditionType.QUIZ_POINTS:
		# Viktorina ballari
		from .models import AnimeVerification
		total_pts = AnimeVerification.objects.filter(user=user).aggregate(total=Sum("points"))["total"] or 0
		current_value = total_pts
		is_met = current_value >= target
		if not hint:
			hint = f"Anime viktorinasida kamida {target} ball to'plang (Hozir: {current_value}/{target})"

	elif cond_type == ConditionType.PLAYER_LEVEL:
		current_value = profile.level
		is_met = current_value >= target
		if not hint:
			hint = f"Qahramon darajangiz kamida {target}-daraja bo'lishi kerak"

	return {
		"condition_id": condition.id,
		"condition_type": cond_type,
		"target_value": target,
		"current_value": current_value,
		"is_met": is_met,
		"hint": hint,
	}


def evaluate_portal_for_player(user, portal: GamePortal) -> dict:
	"""O'yinchining bitta portal bo'yicha ochilish holatini to'liq hisoblash."""
	profile = get_or_create_player_profile(user)
	conditions = portal.conditions.all()

	condition_results = []
	all_met = True

	# Cooldown tekshiruvi
	last_access = PortalAccessLog.objects.filter(player=profile, portal=portal).order_by("-accessed_at").first()
	is_in_cooldown = False
	cooldown_remaining_sec = 0

	if last_access and portal.cooldown_minutes > 0:
		cooldown_end = last_access.accessed_at + timedelta(minutes=portal.cooldown_minutes)
		if timezone.now() < cooldown_end:
			is_in_cooldown = True
			cooldown_remaining_sec = int((cooldown_end - timezone.now()).total_seconds())

	for cond in conditions:
		res = check_single_condition(user, profile, cond)
		condition_results.append(res)
		if not res["is_met"]:
			all_met = False

	# Agar portal faol bo'lmasa yoki cooldown bo'lsa
	can_enter = portal.is_active and all_met and not is_in_cooldown

	return {
		"id": portal.id,
		"portal_id": portal.id,
		"code": portal.code,
		"name": portal.name,
		"tier": portal.tier,
		"description": portal.description,
		"position": {"x": portal.pos_x, "y": portal.pos_y, "z": portal.pos_z},
		"radius": portal.radius,
		"can_enter": can_enter,
		"is_in_cooldown": is_in_cooldown,
		"cooldown_remaining_sec": cooldown_remaining_sec,
		"conditions": condition_results,
		"loot_preview": [
			{
				"item_name": loot.item.name,
				"rarity": loot.item.rarity,
				"rarity_display": loot.item.get_rarity_display(),
				"drop_chance": loot.drop_chance_percent,
				"power": loot.item.power,
			}
			for loot in portal.loot_table.select_related("item").all()[:5]
		],
	}


@transaction.atomic
def enter_portal_and_claim_loot(user, portal_id: int) -> dict:
	"""O'yinchi portalga kirganda shartlarni qayta tekshirib, mukofot berish."""
	portal = GamePortal.objects.select_for_update().get(id=portal_id)
	profile = get_or_create_player_profile(user)

	status = evaluate_portal_for_player(user, portal)
	if not status["can_enter"]:
		return {
			"success": False,
			"error": "Portal shartlari to'liq bajarilmagan yoki qayta kirish vaqti tugamagan!",
			"status": status,
		}

	# Mukofotlar generatsiyasi
	loots = portal.loot_table.select_related("item").all()
	dropped_items = []
	total_coins = 0
	total_exp = 0

	for loot in loots:
		roll = random.uniform(0.0, 100.0)
		if roll <= loot.drop_chance_percent:
			qty = random.randint(loot.min_quantity, loot.max_quantity)
			inv, _ = PlayerInventory.objects.get_or_create(player=profile, item=loot.item)
			inv.quantity += qty
			inv.save()

			coins = random.randint(loot.coin_min, loot.coin_max)
			total_coins += coins
			total_exp += loot.exp_reward

			dropped_items.append({
				"item_id": loot.item.id,
				"name": loot.item.name,
				"rarity": loot.item.rarity,
				"rarity_display": loot.item.get_rarity_display(),
				"quantity": qty,
				"power": loot.item.power,
				"icon_url": loot.item.icon_url,
				"model_path": loot.item.model_path,
			})

	# O'yinchi balansini yangilash
	profile.coins += total_coins
	profile.experience += total_exp
	profile.portals_cleared += 1
	profile.last_portal_entered_at = timezone.now()

	# Level-up hisobi (har 500 exp = 1 daraja)
	new_level = 1 + (profile.experience // 500)
	leveled_up = new_level > profile.level
	profile.level = new_level
	profile.save()

	# Jurnalga yozish
	summary = {
		"coins": total_coins,
		"exp": total_exp,
		"items": dropped_items,
		"leveled_up": leveled_up,
	}
	PortalAccessLog.objects.create(player=profile, portal=portal, reward_summary=summary)

	return {
		"success": True,
		"portal_name": portal.name,
		"tier": portal.tier,
		"coins_earned": total_coins,
		"exp_earned": total_exp,
		"new_level": profile.level,
		"leveled_up": leveled_up,
		"dropped_items": dropped_items,
	}
