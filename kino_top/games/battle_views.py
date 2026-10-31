"""
Jang tizimi API viewlari
"""
import random
from datetime import datetime, timedelta

from django.db import transaction
from django.utils import timezone
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from .artifact_views import resolve_player_user
from .artifact_models import ArtifactPlayerProfile, GamePortal, GameItem, PlayerInventory
from .battle_models import BattleSession, BattleStatus, MonsterType, xp_required_for_level, calculate_level_from_xp
from .portal_engine import evaluate_portal_for_player, get_or_create_player_profile


class StartBattleView(APIView):
    """
    Portal ochilish shartlari bajarilganda va o'yinchi kirmoqchi bo'lganda chaqiriladi.
    Yangi BattleSession yaratadi va 1-to'lqin mahluqlarini qaytaradi.
    """
    permission_classes = [AllowAny]

    def post(self, request):
        user = resolve_player_user(request)
        if not user:
            return Response({'error': 'Autentifikatsiya talab etiladi'}, status=401)

        portal_id = request.data.get('portal_id')
        if not portal_id:
            first_portal = GamePortal.objects.filter(is_active=True).first()
            if first_portal:
                portal_id = first_portal.id
            else:
                return Response({'error': 'portal_id kiritilishi shart'}, status=400)

        try:
            portal = GamePortal.objects.get(id=portal_id, is_active=True)
            player = get_or_create_player_profile(user)
        except (GamePortal.DoesNotExist, ValueError):
            return Response({'error': f'Portal (id={portal_id}) topilmadi'}, status=404)

        # Portal shartlarini tekshirish (user birinchi argument!)
        portal_status = evaluate_portal_for_player(user, portal)
        if not portal_status.get('can_enter'):
            return Response({
                'error': 'Portal shartlari bajarilmagan',
                'conditions': portal_status.get('conditions', [])
            }, status=403)

        # Eski aktiv sessiyani yopish
        BattleSession.objects.filter(
            player=player, status=BattleStatus.ACTIVE
        ).update(status=BattleStatus.FLED)

        # Portal tier ga qarab to'lqinlar soni
        waves_map = {'D': 3, 'C': 4, 'B': 5, 'A': 6, 'S': 7}
        waves_total = waves_map.get(portal.tier, 3)

        battle = BattleSession.objects.create(
            player=player,
            portal=portal,
            waves_total=waves_total,
        )

        # 1-to'lqin mahluqlari
        wave_monsters = battle.get_wave_monsters(1)

        return Response({
            'battle_id': battle.id,
            'portal_name': portal.name,
            'portal_tier': portal.tier,
            'waves_total': waves_total,
            'current_wave': 1,
            'monsters': wave_monsters,
            'arena_radius': 20,
        })


class NextWaveView(APIView):
    """Joriy to'lqin tamom bo'lgandan keyin keyingi to'lqin mahluqlarini beradi."""
    permission_classes = [AllowAny]

    def post(self, request):
        user = resolve_player_user(request)
        if not user:
            return Response({'error': 'Autentifikatsiya talab etiladi'}, status=401)

        battle_id = request.data.get('battle_id')
        wave_xp    = request.data.get('wave_xp', 0)
        wave_coins = request.data.get('wave_coins', 0)
        wave_kills = request.data.get('wave_kills', 0)

        try:
            player = ArtifactPlayerProfile.objects.get(user=user)
            battle = BattleSession.objects.get(id=battle_id, player=player,
                                               status=BattleStatus.ACTIVE)
        except (ArtifactPlayerProfile.DoesNotExist, BattleSession.DoesNotExist):
            return Response({'error': 'Jang sessiyasi topilmadi'}, status=404)

        # To'lqin statistikasini yig'ish
        battle.waves_completed += 1
        battle.xp_earned    += int(wave_xp)
        battle.coins_earned += int(wave_coins)
        battle.kills        += int(wave_kills)
        battle.save()

        next_wave = battle.waves_completed + 1

        if next_wave > battle.waves_total:
            # Barcha to'lqinlar tamom — g'alaba!
            return Response({'all_waves_done': True, 'battle_id': battle.id})

        monsters = battle.get_wave_monsters(next_wave)
        return Response({
            'battle_id': battle.id,
            'current_wave': next_wave,
            'waves_total': battle.waves_total,
            'monsters': monsters,
        })


class CompleteBattleView(APIView):
    """
    Barcha to'lqinlar yutilganda chaqiriladi.
    XP, tanga beradi, sandiq ochadi va profil yangilaydi.
    """
    permission_classes = [AllowAny]

    def post(self, request):
        user = resolve_player_user(request)
        if not user:
            return Response({'error': 'Autentifikatsiya talab etiladi'}, status=401)

        battle_id  = request.data.get('battle_id')
        final_xp   = int(request.data.get('total_xp', 0))
        final_coins = int(request.data.get('total_coins', 0))
        final_kills = int(request.data.get('total_kills', 0))

        try:
            player = ArtifactPlayerProfile.objects.get(user=user)
            battle = BattleSession.objects.get(id=battle_id, player=player,
                                               status=BattleStatus.ACTIVE)
        except (ArtifactPlayerProfile.DoesNotExist, BattleSession.DoesNotExist):
            return Response({'error': 'Jang sessiyasi topilmadi'}, status=404)

        with transaction.atomic():
            # XP va tanga qo'shish + daraja oshirish
            old_level = player.level
            player.experience += final_xp
            player.coins      += final_coins
            player.kills      += final_kills
            player.portals_cleared += 1

            # Sandiq loot
            chest_rewards = []
            loot_table = battle.portal.loot_table.all()

            if loot_table.exists():
                for loot in loot_table:
                    roll = random.uniform(0, 100)
                    if roll <= loot.drop_chance_percent:
                        qty = random.randint(loot.min_quantity, loot.max_quantity)
                        inv, _ = PlayerInventory.objects.get_or_create(
                            player=player, item=loot.item,
                            defaults={'quantity': 0}
                        )
                        inv.quantity += qty
                        inv.save()
                        chest_rewards.append({
                            'item_name': loot.item.name,
                            'rarity': loot.item.rarity,
                            'quantity': qty,
                            'icon': loot.item.icon_url,
                        })
                        final_coins += random.randint(loot.coin_min, loot.coin_max)
                        final_xp    += loot.exp_reward

            # Bonus tangalar loot dan
            player.coins += (final_coins - int(request.data.get('total_coins', 0)))
            player.experience += (final_xp - int(request.data.get('total_xp', 0)))

            # Daraja hisoblash (Eksponentsial formula)
            new_level, cur_xp, next_needed = calculate_level_from_xp(player.experience)
            leveled_up = new_level > old_level
            levels_gained = max(0, new_level - old_level)
            player.level = new_level

            # Sessiya yopish
            battle.status        = BattleStatus.WON
            battle.waves_completed = battle.waves_total
            battle.xp_earned     = final_xp
            battle.coins_earned  = final_coins
            battle.kills         = final_kills
            battle.chest_opened  = True
            battle.chest_rewards = chest_rewards
            battle.ended_at      = timezone.now()
            battle.save()

            player.last_portal_entered_at = timezone.now()
            player.save()

        return Response({
            'success': True,
            'battle_id': battle.id,
            'xp_earned': final_xp,
            'coins_earned': final_coins,
            'kills': final_kills,
            'chest_rewards': chest_rewards,
            'new_level': player.level,
            'new_experience': player.experience,
            'current_level_exp': cur_xp,
            'xp_for_next_level': next_needed,
            'leveled_up': leveled_up,
            'levels_gained': levels_gained,
        })


class FleeBattleView(APIView):
    """O'yinchi jangdan qochganda chaqiriladi — progressni yo'qotadi."""
    permission_classes = [AllowAny]

    def post(self, request):
        user = resolve_player_user(request)
        if not user:
            return Response({'error': 'Autentifikatsiya talab etiladi'}, status=401)

        battle_id = request.data.get('battle_id')
        partial_xp    = int(request.data.get('partial_xp', 0))
        partial_coins = int(request.data.get('partial_coins', 0))
        partial_kills = int(request.data.get('partial_kills', 0))

        try:
            player = ArtifactPlayerProfile.objects.get(user=user)
            battle = BattleSession.objects.get(id=battle_id, player=player,
                                               status=BattleStatus.ACTIVE)
        except (ArtifactPlayerProfile.DoesNotExist, BattleSession.DoesNotExist):
            return Response({'error': 'Topilmadi'}, status=404)

        with transaction.atomic():
            # Qochganda faqat 30% XP va tangani saqlab qoladi
            saved_xp    = round(partial_xp * 0.3)
            saved_coins = round(partial_coins * 0.3)

            player.experience += saved_xp
            player.coins      += saved_coins
            player.kills      += partial_kills

            # Daraja tekshiruvi (Eksponentsial)
            new_level, cur_xp, next_needed = calculate_level_from_xp(player.experience)
            player.level = new_level
            player.save()

            battle.status      = BattleStatus.FLED
            battle.xp_earned   = saved_xp
            battle.coins_earned = saved_coins
            battle.kills       = partial_kills
            battle.ended_at    = timezone.now()
            battle.save()

        return Response({
            'fled': True,
            'saved_xp': saved_xp,
            'saved_coins': saved_coins,
            'message': f"Qochib ketdingiz. {saved_xp} XP va {saved_coins} tanga saqlab qolindi (30%).",
        })


class GetMonsterTypesView(APIView):
    """Admin tomonidan yaratilgan barcha mahluqlar ro'yxati (frontend uchun)."""
    permission_classes = [AllowAny]

    def get(self, request):
        monsters = MonsterType.objects.all().values(
            'id', 'name', 'code', 'rank', 'max_hp', 'attack_damage',
            'attack_speed', 'move_speed', 'attack_range', 'aggro_range',
            'xp_reward', 'coins_reward', 'color', 'scale',
            'weapon_type', 'attack_style', 'is_boss', 'knockback', 'portal_tiers',
        )
        return Response(list(monsters))
