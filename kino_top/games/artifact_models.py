from django.conf import settings
from django.db import models

class ItemRarity(models.TextChoices):
	F_COMMON = "common", "F-Rank (Oddiy)"
	E_UNCOMMON = "uncommon", "E-Rank (Noodatiy)"
	D_RARE = "rare", "D-Rank (Kamyob)"
	C_EPIC = "epic", "C-Rank (Epik)"
	B_LEGENDARY = "legendary", "B-Rank (Afsonaviy)"
	A_MYTHIC = "mythic", "A-Rank (Mifologik)"
	S_DIVINE = "divine", "S-Rank (Ilohiy / Pasxalka)"


class ItemType(models.TextChoices):
	WEAPON = "weapon", "Qurol"
	ARMOR = "armor", "Zirh"
	ARTIFACT = "artifact", "Artefakt / Sehrli yodgorlik"
	CONSUMABLE = "consumable", "Iste'mol buyumi / Zelye"
	MATERIAL = "material", "Crafting materiali"
	PORTAL_KEY = "portal_key", "Portal kaliti"


class PortalTier(models.TextChoices):
	D_RANK = "D", "D-Rank (Boshlang'ich Portal)"
	C_RANK = "C", "C-Rank (Oddiy Portal)"
	B_RANK = "B", "B-Rank (Kamyob Sehrli Portal)"
	A_RANK = "A", "A-Rank (Afsonaviy Portal)"
	S_RANK = "S", "S-Rank (Monstr / Ilohiy Portal)"


class ConditionType(models.TextChoices):
	WATCH_ANIME_COUNT = "watch_count", "N ta anime ko'rish"
	WATCH_ANIME_HOURS = "watch_hours", "N daqiqa/soat anime ko'rish"
	WATCH_SPECIFIC_TITLE = "watch_specific", "Maxsus bitta anime ko'rish"
	HAS_ACTIVE_SUBSCRIPTION = "active_subscription", "VIP / Premium obunaga ega bo'lish"
	COMMENT_COUNT = "comment_count", "Animelarga N ta sharh/izoh yozish"
	BUG_REPORT_ACCEPTED = "bug_report", "Adminga xato xabar qilib tasdiqlatish"
	QUIZ_POINTS = "quiz_points", "Quiz o'yinida kamida N ball to'plash"
	PLAYER_LEVEL = "player_level", "Qahramon darajasi N ga yetishi"


class CharacterClass(models.TextChoices):
	MAGE = "mage", "Sehrgar (Mage)"
	RANGER = "ranger", "Mergan (Ranger)"
	ROGUE = "rogue", "Qaroqchi (Rogue)"
	WARRIOR = "warrior", "Jangchi (Warrior)"


class ArtifactPlayerProfile(models.Model):
	"""Anime Artifact Hunter o'yinchisi profili."""

	user = models.OneToOneField(
		settings.AUTH_USER_MODEL,
		on_delete=models.CASCADE,
		related_name="artifact_hunter_profile",
	)
	character_class = models.CharField(
		max_length=20,
		choices=CharacterClass.choices,
		default=CharacterClass.WARRIOR,
	)
	level = models.PositiveIntegerField(default=1)
	experience = models.PositiveBigIntegerField(default=0)
	coins = models.PositiveBigIntegerField(default=100, help_text="O'yin tangalari")
	gems = models.PositiveIntegerField(default=0, help_text="Kamyob qimmatbaho toshlar")

	pos_x = models.FloatField(default=0.0)
	pos_y = models.FloatField(default=0.0)
	pos_z = models.FloatField(default=0.0)

	chests_opened = models.PositiveIntegerField(default=0)
	portals_cleared = models.PositiveIntegerField(default=0)
	last_portal_entered_at = models.DateTimeField(null=True, blank=True)

	hp = models.PositiveIntegerField(default=0, help_text="Joriy jon (0 = to'liq)")
	kills = models.PositiveIntegerField(default=0, help_text="Yo'q qilingan mahluqlar soni")
	enemy_state = models.JSONField(
		default=dict,
		blank=True,
		help_text="Mahluqlar holati: o'lim vaqti, qayta tiklanish vaqti, joylashuv",
	)

	created_at = models.DateTimeField(auto_now_add=True)
	updated_at = models.DateTimeField(auto_now=True)

	class Meta:
		ordering = ["-level", "-experience"]

	def __str__(self) -> str:
		return f"{self.user} - Lv.{self.level} [{self.get_character_class_display()}]"


class GameItem(models.Model):
	"""Admin tomonidan yaratiladigan o'yin buyumlari va artefaktlari."""

	name = models.CharField(max_length=150, help_text="Buyum nomi (masalan: 'Zanglagan afsonaviy qilich')")
	code = models.SlugField(max_length=100, unique=True, help_text="Unikal kalit, masalan: sword_excalibur_01")
	description = models.TextField(blank=True, help_text="Buyum tarixi va tavsifi")
	item_type = models.CharField(max_length=20, choices=ItemType.choices, default=ItemType.ARTIFACT)
	rarity = models.CharField(max_length=20, choices=ItemRarity.choices, default=ItemRarity.F_COMMON)

	power = models.PositiveIntegerField(default=10, help_text="Hujum, himoya yoki artefakt kuchi")
	attributes = models.JSONField(
		default=dict,
		blank=True,
		help_text="Qo'shimcha bonuslar: {'speed_boost': 1.1, 'luck': 5, 'drop_bonus': 10}",
	)

	model_path = models.CharField(
		max_length=255,
		blank=True,
		help_text="Frontenddagi 3D GLTF/GLB yo'li (masalan: models/charactrer_items/gltf/sword_1handed.gltf)",
	)
	icon_url = models.CharField(max_length=255, blank=True, help_text="2D ikonka yo'li")

	is_sellable = models.BooleanField(default=True)
	sell_price = models.PositiveIntegerField(default=10)
	buy_price = models.PositiveIntegerField(default=50)

	created_at = models.DateTimeField(auto_now_add=True)

	class Meta:
		ordering = ["rarity", "name"]

	def __str__(self) -> str:
		return f"[{self.get_rarity_display()}] {self.name}"


class PlayerInventory(models.Model):
	"""O'yinchining shaxsiy inventari."""

	player = models.ForeignKey(
		ArtifactPlayerProfile,
		on_delete=models.CASCADE,
		related_name="inventory_items",
	)
	item = models.ForeignKey(
		GameItem,
		on_delete=models.CASCADE,
		related_name="held_by_players",
	)
	quantity = models.PositiveIntegerField(default=1)
	is_equipped = models.BooleanField(default=False)
	acquired_at = models.DateTimeField(auto_now_add=True)

	class Meta:
		ordering = ["-acquired_at"]
		constraints = [
			models.UniqueConstraint(
				fields=["player", "item"],
				name="unique_player_item",
			),
		]

	def __str__(self) -> str:
		return f"{self.player.user}: {self.item.name} x{self.quantity}"


class GamePortal(models.Model):
	"""Dunyo bo'ylab joylashgan, dinamik shartlar orqali ochiladigan portallar."""

	name = models.CharField(max_length=150, help_text="Portal nomi (masalan: 'Ajdarho Harobasi Portali')")
	code = models.SlugField(max_length=80, unique=True, help_text="Masalan: portal_dragon_ruins")
	tier = models.CharField(max_length=5, choices=PortalTier.choices, default=PortalTier.D_RANK)
	description = models.TextField(blank=True, help_text="Ushbu portal qayerga olib boradi va nima kutmoqda")

	pos_x = models.FloatField(default=0.0)
	pos_y = models.FloatField(default=0.0)
	pos_z = models.FloatField(default=0.0)
	radius = models.FloatField(default=2.5, help_text="Portalga yaqinlashish trigger masofasi (metr)")

	is_active = models.BooleanField(default=True, help_text="Admin portalni yoqishi yoki o'chirishi mumkin")
	cooldown_minutes = models.PositiveIntegerField(
		default=120,
		help_text="O'yinchi ushbu portalni yopgach, qayta kirishi uchun kerak bo'ladigan vaqt (daqiqa)",
	)

	created_at = models.DateTimeField(auto_now_add=True)

	class Meta:
		ordering = ["tier", "name"]

	def __str__(self) -> str:
		return f"[{self.get_tier_display()}] {self.name}"


class PortalCondition(models.Model):
	"""Admin tomonidan har bir portal uchun o'rnatiladigan maxsus ochilish shartlari."""

	portal = models.ForeignKey(
		GamePortal,
		on_delete=models.CASCADE,
		related_name="conditions",
	)
	condition_type = models.CharField(
		max_length=30,
		choices=ConditionType.choices,
		default=ConditionType.WATCH_ANIME_COUNT,
	)
	target_value = models.PositiveIntegerField(
		default=1,
		help_text="Kerakli qiymat: masalan 5 ta anime, 60 daqiqa, 2 ta izoh, 1 ta xato xabari",
	)
	custom_title = models.ForeignKey(
		"movies.MediaTitle",
		on_delete=models.SET_NULL,
		null=True,
		blank=True,
		related_name="required_by_portals",
		help_text="Agar shart aynan bitta anime ko'rish bo'lsa, shu yerdan tanlanadi",
	)
	hint_message = models.CharField(
		max_length=300,
		blank=True,
		help_text="Shart bajarilmaganda foydalanuvchiga ko'rsatiladigan qiziqarli ko'rsatma",
	)

	created_at = models.DateTimeField(auto_now_add=True)

	class Meta:
		ordering = ["portal", "id"]

	def __str__(self) -> str:
		return f"{self.portal.name} - {self.get_condition_type_display()} (Qiymat: {self.target_value})"


class PortalLootTable(models.Model):
	"""Portaldan tushadigan mukofotlar ehtimolligi va hajmi."""

	portal = models.ForeignKey(
		GamePortal,
		on_delete=models.CASCADE,
		related_name="loot_table",
	)
	item = models.ForeignKey(
		GameItem,
		on_delete=models.CASCADE,
		related_name="dropped_by_portals",
	)
	drop_chance_percent = models.FloatField(
		default=100.0,
		help_text="Tushish ehtimolligi (0.1% dan 100.0% gacha)",
	)
	min_quantity = models.PositiveIntegerField(default=1)
	max_quantity = models.PositiveIntegerField(default=1)

	coin_min = models.PositiveIntegerField(default=50)
	coin_max = models.PositiveIntegerField(default=200)
	exp_reward = models.PositiveIntegerField(default=100)

	class Meta:
		ordering = ["portal", "-drop_chance_percent"]

	def __str__(self) -> str:
		return f"{self.portal.name} -> {self.item.name} ({self.drop_chance_percent}%)"


class PortalAccessLog(models.Model):
	"""Foydalanuvchining portalni ochishi va mukofot olish jurnali."""

	player = models.ForeignKey(
		ArtifactPlayerProfile,
		on_delete=models.CASCADE,
		related_name="portal_logs",
	)
	portal = models.ForeignKey(
		GamePortal,
		on_delete=models.CASCADE,
		related_name="player_access_logs",
	)
	reward_summary = models.JSONField(default=dict, blank=True)
	accessed_at = models.DateTimeField(auto_now_add=True)

	class Meta:
		ordering = ["-accessed_at"]

	def __str__(self) -> str:
		return f"{self.player.user} -> {self.portal.name} at {self.accessed_at.strftime('%Y-%m-%d %H:%M')}"
