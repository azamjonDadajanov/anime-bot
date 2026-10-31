import os
import sys
import django
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "kino_top.settings")
django.setup()

from games.artifact_models import (
	GameItem,
	GamePortal,
	PortalCondition,
	PortalLootTable,
	ItemRarity,
	ItemType,
	PortalTier,
	ConditionType,
)

def seed_data():
	print("Seeding Artifact Hunter initial data...")

	# 1. Buyumlar (Items) - Har xil Rank va turlar
	items_data = [
		{
			"name": "Yog'och Qilich",
			"code": "wooden_sword",
			"description": "Boshlang'ich jangchilarning oddiy mashg'ulot qilichi.",
			"item_type": ItemType.WEAPON,
			"rarity": ItemRarity.F_COMMON,
			"power": 15,
			"model_path": "models/charactrer_items/gltf/sword_1handed.gltf",
			"sell_price": 20,
		},
		{
			"name": "O'tkir Po'lat Qilich",
			"code": "steel_sword",
			"description": "Jangda toblangan po'lat qilich.",
			"item_type": ItemType.WEAPON,
			"rarity": ItemRarity.D_RARE,
			"power": 45,
			"model_path": "models/charactrer_items/gltf/sword_2handed.gltf",
			"sell_price": 100,
		},
		{
			"name": "Ovchi Kamoni",
			"code": "hunters_bow",
			"description": "Tezkor o'q otishga moslashtirilgan egiluvchan kamon.",
			"item_type": ItemType.WEAPON,
			"rarity": ItemRarity.E_UNCOMMON,
			"power": 30,
			"model_path": "models/charactrer_items/gltf/arrow_bow.gltf",
			"sell_price": 60,
		},
		{
			"name": "Sehrgar Xassasi",
			"code": "mage_staff",
			"description": "Tabiat energiyasini o'zida jamlovchi qadimiy yog'och xassa.",
			"item_type": ItemType.WEAPON,
			"rarity": ItemRarity.D_RARE,
			"power": 50,
			"model_path": "models/charactrer_items/gltf/wand.gltf",
			"sell_price": 120,
		},
		{
			"name": "Qorong'ulik Xanjari",
			"code": "shadow_dagger",
			"description": "Soya ichidan yashirin zarba berish uchun yaratilgan.",
			"item_type": ItemType.WEAPON,
			"rarity": ItemRarity.C_EPIC,
			"power": 85,
			"model_path": "models/charactrer_items/gltf/knife.gltf",
			"sell_price": 350,
		},
		{
			"name": "Qadimiy Hokage Peshonabandi",
			"code": "relic_shinobi_band",
			"description": "Afsonaviy qishloq himoyachilarining sirlari bitilgan yodgorlik.",
			"item_type": ItemType.ARTIFACT,
			"rarity": ItemRarity.B_LEGENDARY,
			"power": 180,
			"attributes": {"speed_boost": 1.25, "luck": 15},
			"sell_price": 1000,
		},
		{
			"name": "Mifologik Ajdarho Yuragi",
			"code": "dragon_heart_core",
			"description": "Anichoparning eng buyuk sarguzashtchilariga nasib etadigan ilohiy artefakt.",
			"item_type": ItemType.ARTIFACT,
			"rarity": ItemRarity.S_DIVINE,
			"power": 500,
			"attributes": {"all_stats_boost": 2.0, "drop_chance_multiplier": 2.0},
			"sell_price": 10000,
		},
	]

	created_items = {}
	for idata in items_data:
		item, _ = GameItem.objects.update_or_create(code=idata["code"], defaults=idata)
		created_items[item.code] = item

	print(f"Items seeded: {len(created_items)}")

	# 2. Xarita Portallari (Portals)
	portals_data = [
		{
			"code": "portal_green_grove",
			"name": "🌱 Yashil Vodiy Portali",
			"tier": PortalTier.D_RANK,
			"description": "Yangi boshlovchilar uchun tinch vodiy portali. Kirish uchun bir oz anime ko'rish kifoya.",
			"pos_x": -6.0,
			"pos_y": 0.0,
			"pos_z": -8.0,
			"cooldown_minutes": 30,
			"conditions": [
				{
					"condition_type": ConditionType.WATCH_ANIME_COUNT,
					"target_value": 1,
					"hint_message": "Anichoparda kamida 1 ta anime ko'ring",
				}
			],
			"loot": [
				{"item_code": "wooden_sword", "drop_chance": 80.0, "min_qty": 1, "max_qty": 1, "coins": (50, 100)},
				{"item_code": "hunters_bow", "drop_chance": 50.0, "min_qty": 1, "max_qty": 1, "coins": (80, 150)},
			]
		},
		{
			"code": "portal_crystal_cave",
			"name": "🔮 Sehrli Kristall G'ori Portali",
			"tier": PortalTier.B_RANK,
			"description": "Sehrli quvvat bilan to'la sirli g'or. Tomosha vaqti ko'p bo'lganlarga ochiladi.",
			"pos_x": 12.0,
			"pos_y": 0.0,
			"pos_z": -10.0,
			"cooldown_minutes": 90,
			"conditions": [
				{
					"condition_type": ConditionType.WATCH_ANIME_HOURS,
					"target_value": 60,  # 60 daqiqa (1 soat)
					"hint_message": "Bugun Anichoparda 1 soat (60 daqiqa) anime tomosha qiling",
				},
				{
					"condition_type": ConditionType.COMMENT_COUNT,
					"target_value": 1,
					"hint_message": "Sevimli animengizga kamida 1 ta fikr/izoh qoldiring",
				}
			],
			"loot": [
				{"item_code": "steel_sword", "drop_chance": 60.0, "min_qty": 1, "max_qty": 1, "coins": (200, 400)},
				{"item_code": "mage_staff", "drop_chance": 50.0, "min_qty": 1, "max_qty": 1, "coins": (250, 500)},
				{"item_code": "shadow_dagger", "drop_chance": 30.0, "min_qty": 1, "max_qty": 1, "coins": (300, 600)},
			]
		},
		{
			"code": "portal_divine_dragon",
			"name": "👑 Qadimiy Ajdarho Ma'badi (S-Rank)",
			"tier": PortalTier.S_RANK,
			"description": "Eng buyuk yodgorliklar saqlanadigan ilohiy portal. Faqat VIP obunachilar va faol yordamchilarga ochiladi!",
			"pos_x": 0.0,
			"pos_y": 0.0,
			"pos_z": 15.0,
			"cooldown_minutes": 240,
			"conditions": [
				{
					"condition_type": ConditionType.HAS_ACTIVE_SUBSCRIPTION,
					"target_value": 1,
					"hint_message": "VIP obunaga ega bo'ling yoki bot orqali adminga xato haqida xabar bering",
				}
			],
			"loot": [
				{"item_code": "relic_shinobi_band", "drop_chance": 40.0, "min_qty": 1, "max_qty": 1, "coins": (1000, 2500)},
				{"item_code": "dragon_heart_core", "drop_chance": 15.0, "min_qty": 1, "max_qty": 1, "coins": (5000, 10000)},
			]
		},
	]

	for pdata in portals_data:
		portal, _ = GamePortal.objects.update_or_create(
			code=pdata["code"],
			defaults={
				"name": pdata["name"],
				"tier": pdata["tier"],
				"description": pdata["description"],
				"pos_x": pdata["pos_x"],
				"pos_y": pdata["pos_y"],
				"pos_z": pdata["pos_z"],
				"cooldown_minutes": pdata["cooldown_minutes"],
			}
		)

		# Shartlarni tozalab qayta qo'shish
		portal.conditions.all().delete()
		for cdata in pdata["conditions"]:
			PortalCondition.objects.create(
				portal=portal,
				condition_type=cdata["condition_type"],
				target_value=cdata["target_value"],
				hint_message=cdata.get("hint_message", ""),
			)

		# Mukofotlar
		portal.loot_table.all().delete()
		for ldata in pdata["loot"]:
			item = created_items.get(ldata["item_code"])
			if item:
				PortalLootTable.objects.create(
					portal=portal,
					item=item,
					drop_chance_percent=ldata["drop_chance"],
					min_quantity=ldata["min_qty"],
					max_quantity=ldata["max_qty"],
					coin_min=ldata["coins"][0],
					coin_max=ldata["coins"][1],
					exp_reward=250,
				)

	print("Portals and conditions seeded successfully!")

if __name__ == "__main__":
	seed_data()
