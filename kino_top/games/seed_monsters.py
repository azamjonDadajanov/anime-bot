"""
python manage.py shell < games/seed_monsters.py
Mahluqlar va jang tizimi uchun boshlang'ich ma'lumotlar
"""
import os, sys, django
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from games.battle_models import MonsterType

MONSTERS = [
    # ─── F-Rank: Zaif mahluqlar (D portal) ──────────────────────────────
    {
        'name': 'Mayna Goblin',   'code': 'goblin_basic',      'rank': 'F',
        'max_hp': 35,  'attack_damage': 5,  'attack_speed': 2.0,
        'move_speed': 2.8, 'attack_range': 1.5, 'aggro_range': 10.0,
        'xp_reward': 15, 'coins_reward': 3,
        'color': '#22c55e', 'scale': 0.7,
        'weapon_type': 'dagger', 'attack_style': 'melee',
        'portal_tiers': ['D', 'C'], 'is_boss': False, 'knockback': 0.2,
    },
    {
        'name': 'Mayda Ilon',     'code': 'snake_small',       'rank': 'F',
        'max_hp': 25,  'attack_damage': 8,  'attack_speed': 1.5,
        'move_speed': 3.5, 'attack_range': 1.2, 'aggro_range': 8.0,
        'xp_reward': 12, 'coins_reward': 2,
        'color': '#84cc16', 'scale': 0.5,
        'weapon_type': 'none', 'attack_style': 'charge',
        'portal_tiers': ['D'], 'is_boss': False, 'knockback': 0.0,
    },
    {
        'name': 'Yovuz Qoravoy',  'code': 'crow_evil',         'rank': 'F',
        'max_hp': 20,  'attack_damage': 6,  'attack_speed': 1.8,
        'move_speed': 4.0, 'attack_range': 1.0, 'aggro_range': 14.0,
        'xp_reward': 10, 'coins_reward': 2,
        'color': '#6b7280', 'scale': 0.45,
        'weapon_type': 'claws', 'attack_style': 'melee',
        'portal_tiers': ['D'], 'is_boss': False, 'knockback': 0.0,
    },

    # ─── E-Rank: D-C portal ────────────────────────────────────────────
    {
        'name': 'Qurolli Goblin', 'code': 'goblin_armed',      'rank': 'E',
        'max_hp': 55,  'attack_damage': 10, 'attack_speed': 1.8,
        'move_speed': 2.6, 'attack_range': 1.8, 'aggro_range': 11.0,
        'xp_reward': 25, 'coins_reward': 6,
        'color': '#16a34a', 'scale': 0.8,
        'weapon_type': 'sword', 'attack_style': 'melee',
        'portal_tiers': ['D', 'C'], 'is_boss': False, 'knockback': 0.3,
    },
    {
        'name': 'Skelet Jangchi', 'code': 'skeleton_warrior',  'rank': 'E',
        'max_hp': 65,  'attack_damage': 12, 'attack_speed': 1.6,
        'move_speed': 2.2, 'attack_range': 2.0, 'aggro_range': 12.0,
        'xp_reward': 30, 'coins_reward': 8,
        'color': '#d4d4aa', 'scale': 0.9,
        'weapon_type': 'sword', 'attack_style': 'melee',
        'portal_tiers': ['C', 'B'], 'is_boss': False, 'knockback': 0.4,
    },

    # ─── D-Rank: C portal ──────────────────────────────────────────────
    {
        'name': 'Ork Nayzaboz',   'code': 'orc_spear',         'rank': 'D',
        'max_hp': 110, 'attack_damage': 18, 'attack_speed': 2.2,
        'move_speed': 2.0, 'attack_range': 2.5, 'aggro_range': 13.0,
        'xp_reward': 55, 'coins_reward': 15,
        'color': '#92400e', 'scale': 1.2,
        'weapon_type': 'spear', 'attack_style': 'melee',
        'portal_tiers': ['C', 'B'], 'is_boss': False, 'knockback': 0.8,
    },
    {
        'name': 'Skelet Kamonchi','code': 'skeleton_archer',   'rank': 'D',
        'max_hp': 75,  'attack_damage': 15, 'attack_speed': 2.5,
        'move_speed': 1.8, 'attack_range': 10.0,'aggro_range': 16.0,
        'xp_reward': 45, 'coins_reward': 12,
        'color': '#e5e5cc', 'scale': 0.9,
        'weapon_type': 'bow', 'attack_style': 'ranged',
        'portal_tiers': ['C', 'B'], 'is_boss': False, 'knockback': 0.2,
    },

    # ─── C-Rank: B-A portal ────────────────────────────────────────────
    {
        'name': 'Qoʻngʻiroq Iblisi','code': 'demon_bell',      'rank': 'C',
        'max_hp': 180, 'attack_damage': 28, 'attack_speed': 2.0,
        'move_speed': 2.4, 'attack_range': 2.0, 'aggro_range': 15.0,
        'xp_reward': 90, 'coins_reward': 30,
        'color': '#7c3aed', 'scale': 1.1,
        'weapon_type': 'axe', 'attack_style': 'melee',
        'portal_tiers': ['B', 'A'], 'is_boss': False, 'knockback': 1.2,
    },
    {
        'name': 'Qorong\'i Sehrgar','code': 'dark_mage',       'rank': 'C',
        'max_hp': 140, 'attack_damage': 35, 'attack_speed': 3.0,
        'move_speed': 1.6, 'attack_range': 12.0,'aggro_range': 18.0,
        'xp_reward': 85, 'coins_reward': 28,
        'color': '#4c1d95', 'scale': 1.0,
        'weapon_type': 'staff', 'attack_style': 'magic',
        'portal_tiers': ['B', 'A'], 'is_boss': False, 'knockback': 0.5,
    },

    # ─── B-Rank: A-S portal ────────────────────────────────────────────
    {
        'name': 'Iblisli Ritsar', 'code': 'dark_knight',       'rank': 'B',
        'max_hp': 300, 'attack_damage': 45, 'attack_speed': 1.8,
        'move_speed': 2.0, 'attack_range': 2.2, 'aggro_range': 14.0,
        'xp_reward': 150, 'coins_reward': 60,
        'color': '#1e3a5f', 'scale': 1.3,
        'weapon_type': 'sword', 'attack_style': 'melee',
        'portal_tiers': ['A', 'S'], 'is_boss': False, 'knockback': 1.5,
    },
    {
        'name': 'Vulqon Elementali','code': 'fire_elemental',  'rank': 'B',
        'max_hp': 260, 'attack_damage': 50, 'attack_speed': 2.5,
        'move_speed': 2.8, 'attack_range': 6.0, 'aggro_range': 20.0,
        'xp_reward': 140, 'coins_reward': 55,
        'color': '#dc2626', 'scale': 1.2,
        'weapon_type': 'fire', 'attack_style': 'aoe',
        'portal_tiers': ['A', 'S'], 'is_boss': False, 'knockback': 0.8,
    },

    # ─── BOSSLAR ─────────────────────────────────────────────────────────
    {
        'name': 'Goblin Saroyshoh','code': 'goblin_king',      'rank': 'D',
        'max_hp': 250, 'attack_damage': 22, 'attack_speed': 1.5,
        'move_speed': 2.2, 'attack_range': 2.0, 'aggro_range': 18.0,
        'xp_reward': 200, 'coins_reward': 80,
        'color': '#15803d', 'scale': 1.6,
        'weapon_type': 'axe', 'attack_style': 'melee',
        'portal_tiers': ['D', 'C'], 'is_boss': True, 'knockback': 2.0,
    },
    {
        'name': 'Ork Qo\'mondoni', 'code': 'orc_commander',    'rank': 'C',
        'max_hp': 450, 'attack_damage': 40, 'attack_speed': 2.0,
        'move_speed': 1.8, 'attack_range': 2.5, 'aggro_range': 18.0,
        'xp_reward': 400, 'coins_reward': 150,
        'color': '#7c2d12', 'scale': 1.8,
        'weapon_type': 'axe', 'attack_style': 'charge',
        'portal_tiers': ['C', 'B'], 'is_boss': True, 'knockback': 3.0,
    },
    {
        'name': 'Iblis Generali',  'code': 'demon_general',    'rank': 'A',
        'max_hp': 800, 'attack_damage': 70, 'attack_speed': 1.8,
        'move_speed': 2.5, 'attack_range': 3.0, 'aggro_range': 22.0,
        'xp_reward': 900, 'coins_reward': 400,
        'color': '#7c3aed', 'scale': 2.0,
        'weapon_type': 'axe', 'attack_style': 'aoe',
        'portal_tiers': ['A'], 'is_boss': True, 'knockback': 4.0,
    },
    {
        'name': '🐉 Qorong\'i Ajdaho','code': 'dark_dragon',   'rank': 'S',
        'max_hp': 2000,'attack_damage': 120,'attack_speed': 2.2,
        'move_speed': 2.0, 'attack_range': 8.0, 'aggro_range': 30.0,
        'xp_reward': 3000, 'coins_reward': 1500,
        'color': '#0f172a', 'scale': 3.0,
        'weapon_type': 'fire', 'attack_style': 'aoe',
        'portal_tiers': ['S'], 'is_boss': True, 'knockback': 6.0,
    },
]

created = updated = 0
for m in MONSTERS:
    drop_items_data = m.pop('drop_items', [])
    obj, is_new = MonsterType.objects.update_or_create(code=m['code'], defaults=m)
    if is_new: created += 1
    else: updated += 1

print(f"✅ Mahluqlar: {created} ta yangi, {updated} ta yangilandi.")
print(f"   Jami mahluq turlari: {MonsterType.objects.count()}")
