"""
Jang tizimi modellari — Mahluqlar, Jangi va To'lqinlar
"""
from django.db import models
from .artifact_models import ArtifactPlayerProfile, GamePortal, GameItem, PortalTier, ItemRarity
import math


# ─── XP Formula ───────────────────────────────────────────────────────────────
def xp_required_for_level(level: int) -> int:
    """
    Har bir daraja uchun kerakli XP miqdori.
    Har safar daraja oshganda keyingi darajaga chiqish uchun koproq XP kerak bo'ladi:
    Level 1: 500, Level 2: 675, Level 3: 911, Level 4: 1230, Level 5: 1661...
    Formula: round(500 * (1.35 ** (level - 1)))
    """
    return round(500 * (1.35 ** (max(1, level) - 1)))


def calculate_level_from_xp(total_xp: int):
    """
    Jami to'plangan tajriba (total_xp) dan joriy darajani,
    joriy darajadagi XP progressini va keyingi daraja uchun kerakli XP ni hisoblaydi.
    """
    level = 1
    xp = max(0, int(total_xp or 0))
    while True:
        needed = xp_required_for_level(level)
        if xp >= needed:
            xp -= needed
            level += 1
        else:
            break
    needed_for_next = xp_required_for_level(level)
    return level, xp, needed_for_next


def total_xp_for_level(level: int) -> int:
    """Level N ga yetish uchun jami kerakli XP."""
    return sum(xp_required_for_level(i) for i in range(1, max(1, level)))


# ─── Monster Type ─────────────────────────────────────────────────────────────
class MonsterRank(models.TextChoices):
    F = 'F', 'F-Rank (Zaif)'
    E = 'E', 'E-Rank (Kuchsiz)'
    D = 'D', 'D-Rank (O\'rtacha)'
    C = 'C', 'C-Rank (Kuchli)'
    B = 'B', 'B-Rank (Xavfli)'
    A = 'A', 'A-Rank (Juda Xavfli)'
    S = 'S', 'S-Rank (Afsonaviy Boss)'


class AttackStyle(models.TextChoices):
    MELEE  = 'melee',  'Yaqin jang (Melee)'
    RANGED = 'ranged', 'Uzoq masofali (Ranged)'
    MAGIC  = 'magic',  'Sehrli hujum (Magic)'
    CHARGE = 'charge', 'Yugurish hujumi (Charge)'
    AOE    = 'aoe',    'Maydon hujumi (AoE)'


class MonsterType(models.Model):
    """
    Admin tomonidan yaratilgan mahluq turi.
    Portal Tier ga bog'liq holda qaysi arealarda paydo bo'lishi belgilanadi.
    """
    name        = models.CharField(max_length=100, help_text="Goblin, Ork, Iblisli Ritsar...")
    code        = models.SlugField(max_length=80, unique=True)
    rank        = models.CharField(max_length=2, choices=MonsterRank.choices, default=MonsterRank.F)
    description = models.TextField(blank=True)

    # Statslar
    max_hp          = models.PositiveIntegerField(default=50)
    attack_damage   = models.PositiveIntegerField(default=8,  help_text="Bir zarba zarar miqdori")
    attack_speed    = models.FloatField(default=1.8, help_text="Zarba orasidagi soniya (kichik = tezroq)")
    move_speed      = models.FloatField(default=2.5, help_text="Harakatlanish tezligi (m/s)")
    attack_range    = models.FloatField(default=1.8, help_text="Hujum masofa (metr)")
    aggro_range     = models.FloatField(default=12.0, help_text="Ko'rish/his qilish masofa")

    # XP va Tanga mukofoti
    xp_reward    = models.PositiveIntegerField(default=20)
    coins_reward = models.PositiveIntegerField(default=5)

    # Ko'rinish
    color       = models.CharField(max_length=20, default='#ef4444', help_text="Three.js rang (hex)")
    scale       = models.FloatField(default=1.0, help_text="3D o'lcham koeffitsienti")
    weapon_type = models.CharField(max_length=50, default='sword',
                                   help_text="sword, axe, bow, staff, claws, fire, none")
    attack_style = models.CharField(max_length=20, choices=AttackStyle.choices,
                                    default=AttackStyle.MELEE)

    # Qaysi portal tierlarda paydo bo'ladi (JSON ro'yxati: ["D","C","B"])
    portal_tiers = models.JSONField(default=list,
                                    help_text='["D","C","B"] — qaysi tier portallarda paydo bo\'ladi')

    # Maxsus xususiyatlar
    is_boss     = models.BooleanField(default=False)
    knockback   = models.FloatField(default=0.0, help_text="Hitda o'yinchini itarish kuchi")
    drop_items  = models.ManyToManyField(GameItem, blank=True, related_name='dropped_by_monsters',
                                         help_text="O'lganda tushishi mumkin bo'lgan buyumlar")

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['rank', 'name']

    def __str__(self):
        return f"[{self.rank}] {self.name}"

    def get_scaled_stats(self, wave: int = 1) -> dict:
        """To'lqin raqamiga qarab mahluq statslarini kuchaytirish."""
        factor = 1.0 + (wave - 1) * 0.25  # Har to'lqinda +25% kuch
        return {
            'hp':       round(self.max_hp * factor),
            'damage':   round(self.attack_damage * factor),
            'xp':       round(self.xp_reward * factor),
            'coins':    round(self.coins_reward * factor),
        }


# ─── Battle Session ────────────────────────────────────────────────────────────
class BattleStatus(models.TextChoices):
    ACTIVE = 'active', 'Jang davom etmoqda'
    WON    = 'won',    'G\'alaba qozonildi'
    LOST   = 'lost',   'Mag\'lubiyat'
    FLED   = 'fled',   'Qochib ketildi'


class BattleSession(models.Model):
    """
    O'yinchi portalga kirganda yaratiladi.
    Jang holati va natijasi saqlanadi.
    """
    player  = models.ForeignKey(ArtifactPlayerProfile, on_delete=models.CASCADE,
                                 related_name='battles')
    portal  = models.ForeignKey(GamePortal, on_delete=models.CASCADE,
                                 related_name='battle_sessions')
    status  = models.CharField(max_length=10, choices=BattleStatus.choices,
                                default=BattleStatus.ACTIVE)

    waves_total     = models.PositiveIntegerField(default=3)
    waves_completed = models.PositiveIntegerField(default=0)

    # Jangt atamasida yig'ilgan mukofotlar
    xp_earned    = models.PositiveIntegerField(default=0)
    coins_earned = models.PositiveIntegerField(default=0)
    kills        = models.PositiveIntegerField(default=0)

    # Sandiq ochildi mi?
    chest_opened  = models.BooleanField(default=False)
    chest_rewards = models.JSONField(default=list, blank=True)

    # Jang vaqti
    started_at = models.DateTimeField(auto_now_add=True)
    ended_at   = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-started_at']

    def __str__(self):
        return f"{self.player} vs {self.portal.name} [{self.status}]"

    def get_wave_monsters(self, wave_num: int) -> list:
        """
        Berilgan to'lqin raqami uchun mahluqlar ro'yxatini qaytaradi.
        Portal tier ga qarab turli xil mahluqlar.
        """
        tier = self.portal.tier
        all_mons = list(MonsterType.objects.all())
        mons = [m for m in all_mons if tier in (m.portal_tiers or [])]
        if not mons:
            mons = [m for m in all_mons if m.rank == 'F']
        if not mons:
            mons = all_mons

        result = []
        base_count = 3 + wave_num * 2  # Wave 1: 5, Wave 2: 7, Wave 3: 9

        # Boss to'lqini (oxirgi to'lqin)
        if wave_num == self.waves_total:
            bosses = [m for m in mons if m.is_boss]
            if bosses:
                boss = bosses[0]
                stats = boss.get_scaled_stats(wave_num)
                result.append({
                    'id': f'boss_{boss.id}',
                    'monster_id': boss.id,
                    'name': boss.name,
                    'rank': boss.rank,
                    'hp': stats['hp'],
                    'max_hp': stats['hp'],
                    'damage': stats['damage'],
                    'xp': stats['xp'],
                    'coins': stats['coins'],
                    'attack_speed': boss.attack_speed,
                    'attack_range': boss.attack_range,
                    'move_speed': boss.move_speed,
                    'attack_style': boss.attack_style,
                    'weapon_type': boss.weapon_type,
                    'color': boss.color,
                    'scale': boss.scale * 1.5,
                    'is_boss': True,
                    'knockback': boss.knockback,
                })
                base_count = max(1, base_count - 3)  # Boss bor, oddiy kam

        # Oddiy mahluqlar
        regular = [m for m in mons if not m.is_boss]
        if not regular:
            regular = mons

        import random
        for i in range(base_count):
            mon = random.choice(regular)
            stats = mon.get_scaled_stats(wave_num)
            angle = (i / base_count) * 3.14159 * 2
            result.append({
                'id': f'w{wave_num}_m{i}_{mon.id}',
                'monster_id': mon.id,
                'name': mon.name,
                'rank': mon.rank,
                'hp': stats['hp'],
                'max_hp': stats['hp'],
                'damage': stats['damage'],
                'xp': stats['xp'],
                'coins': stats['coins'],
                'attack_speed': mon.attack_speed,
                'attack_range': mon.attack_range,
                'move_speed': mon.move_speed,
                'attack_style': mon.attack_style,
                'weapon_type': mon.weapon_type,
                'color': mon.color,
                'scale': mon.scale,
                'is_boss': False,
                'knockback': mon.knockback,
                # Joylashtirish burchagi
                'spawn_angle': angle,
            })

        return result
