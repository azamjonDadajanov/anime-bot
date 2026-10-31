import React, { useEffect, useRef } from 'react';
import * as THREE from 'three';
import { buildOpenWorld, CLOUD_MESHES } from './env/WorldBuilder';
import { createStage } from './core/createStage';
import { createInput } from './core/input';
import { createCameraRig } from './core/cameraRig';
import { loadCharacter } from './player/loadCharacter';
import { CharacterAnimator } from './player/CharacterAnimator';
import { createPlayerController } from './player/playerController';
import { equipWeapons } from './player/weapons';
import { createAttackController } from './player/attack';
import { createPlayerHealth } from './player/playerHealth';
import { createEnemyManager } from './enemies/EnemyManager';
import { PortalScene } from './portals/PortalScene';
import { prepareWorldPortals } from './portals/portalCycle';
import {
  AUTO_TARGET_RANGE,
  playerDamage,
  RESPAWN_POINT,
} from '../config/enemies';
import {
  playerMaxMana,
  playerManaRegen,
  attackManaCost,
} from '../config/level';

const PORTAL_INTERACT_DISTANCE = 4.0;

/**
 * 3D o'yin sahnasi — barcha mantiq modullarga ajratilgan:
 *   core/     sahna, kamera, klaviatura
 *   env/      dunyo (shahar, o'rmon, tog', yo'llar)
 *   player/   qahramon, harakat, animatsiya, qurollar, hujum, jon
 *   enemies/  mahluqlar (skeletlar): spawn, jang, XP, qayta tiklanish
 *   portals/  portal sikli va 3D sahnasi
 *
 * `combat` prop orqali daraja/jon/kills holati keladi, `onCombatUpdate`
 * orqali o'zgarishlar App'ga qaytariladi va bazaga saqlanadi.
 */
export default function GameCanvas({
  characterClass,
  portals = [],
  combat,
  onCombatUpdate,
  onNearPortal,
  playerPosition,
  onPositionUpdate,
}) {
  const mountRef = useRef(null);
  const portalsRef = useRef(portals);
  portalsRef.current = portals;
  const combatRef = useRef(combat);
  combatRef.current = combat;

  useEffect(() => {
    const container = mountRef.current;
    if (!container) return;

    let disposed = false;
    let lastLevel = combatRef.current?.level || 1;
    let kills = combatRef.current?.kills || 0;

    // ── Sahna / kamera / yorug'lik ──
    const stage = createStage(container);
    const { scene, camera } = stage;

    // ── Dunyo: shahar, yo'llar, o'rmon, tog', harobalar ──
    buildOpenWorld(scene);

    // ── Portallar: faqat shahardan tashqarida, siklda birma-bir ochiladi ──
    const portalScene = new PortalScene(scene);
    let worldPortals = [];
    let portalsKey = null;

    const syncPortals = () => {
      const key = JSON.stringify(
        portalsRef.current.map((p) => [p.portal_id, p.is_in_cooldown ? 1 : 0])
      );
      if (key === portalsKey) return;
      portalsKey = key;
      worldPortals = prepareWorldPortals(portalsRef.current);
      portalScene.update(worldPortals);
    };
    syncPortals();

    const level = () => combatRef.current?.level || 1;

    // ── O'yinchining joni ──
    const health = createPlayerHealth({
      level: level(),
      onChange: (hp, maxHp) => onCombatUpdate && onCombatUpdate({ hp, maxHp }),
      onDeath: () => {},
    });
    if (typeof combatRef.current?.hp === 'number') {
      health.restore(combatRef.current.hp);
    }
    health.setLevel(level());

    // ── Mahluqlar (skeletlar) ──
    const enemies = createEnemyManager({
      scene,
      characterClass,
      getLevel: level,
      onPlayerHit: (dmg) => {
        health.damage(dmg);
      },
      onStateChange: () => {
        onCombatUpdate && onCombatUpdate({ enemy_state: enemies.state() });
      },
    });
    enemies.init(combatRef.current?.enemy_state || {}).catch(() => {});

    /** Qahramon mahluqqa zarar berdi (hujum natijasi) */
    const damageEnemy = (enemy) => {
      const xp = enemies.applyDamage(enemy, playerDamage(characterClass, level()));
      if (xp > 0) {
        kills += 1;
        onCombatUpdate &&
          onCombatUpdate({
            exp_gained: xp,
            kills,
            enemy_state: enemies.state(),
          });
      }
    };

    // ── Kirish (klaviatura) va kamera boshqaruvi ──
    let attack = null;
    const input = createInput({
      onAttack: () => {
        if (attack) attack.trigger();
      },
    });
    const cameraRig = createCameraRig(container);

    // ── Qahramon: model + suyak animator + qurollar + harakat + hujum ──
    let animator = null;
    let controller = null;
    let currentMana = combat?.mana ?? playerMaxMana(level(), characterClass);
    let maxMana = playerMaxMana(level(), characterClass);
    let manaTick = 0;

    loadCharacter({
      modelUrl: characterClass?.model || '/models/characters/swordman.glb',
      textureUrl: characterClass?.texture,
      position: {
        x: Number(playerPosition?.x) || 0,
        z: Number(playerPosition?.z) || 0,
      },
    }).then((char) => {
      if (disposed || !char) return;

      scene.add(char);

      animator = new CharacterAnimator(char);
      controller = createPlayerController({
        object: char,
        keys: input.keys,
        cameraRig,
        characterClass,
        onPositionUpdate,
      });

      attack = createAttackController({
        character: char,
        animator,
        characterClass,
        hooks: {
          // Hujum mana sarflaydi: agar mana yetmasa false qaytaradi
          consumeMana: () => {
            const cost = attackManaCost(characterClass);
            if (currentMana < cost) return false;
            currentMana -= cost;
            onCombatUpdate && onCombatUpdate({ mana: currentMana, maxMana });
            return true;
          },
          // Qo'l zarbasi (jangchi / qaroqchi)
          meleeHit: (pos, dx, dz, reach) =>
            enemies.hitTest(pos, dx, dz, reach, 0.3),
          // Uchuvchi zarba (sehr halqasi / o'q)
          projectileHit: (pos, radius) => enemies.findAt(pos, radius),
          onDamage: damageEnemy,
        },
      });
      attack.attachTo(scene);

      // Har bir qahramon o'z qurollar to'plamini oladi (config/weapons.js)
      equipWeapons(char, characterClass?.id).catch(() => {});
    });

    // ── Animatsiya sikli ──
    let animationId;
    const clock = new THREE.Clock();
    let lastNearId = undefined;

    const animate = () => {
      animationId = requestAnimationFrame(animate);
      const delta = Math.min(clock.getDelta(), 0.1);

      syncPortals();
      portalScene.animate(delta);

      // Daraja oshdi → mahluqlar soni va maksimal jon oshadi
      const currentLevel = level();
      if (currentLevel !== lastLevel) {
        lastLevel = currentLevel;
        health.setLevel(currentLevel);
        enemies.syncCount();
      }

      // Bulutlar suzib yuradi
      for (const cloud of CLOUD_MESHES) {
        cloud.position.x += delta * cloud.userData.driftSpeed * cloud.userData.driftDir;
        if (cloud.position.x > 220) cloud.position.x = -220;
        if (cloud.position.x < -220) cloud.position.x = 220;
      }

      // O'yinchining joni: tiklanish / qayta tug'ilish
      const healthResult = health.update(delta);
      if (healthResult === 'respawned' && controller) {
        const pos = controller.position();
        pos.x = RESPAWN_POINT.x;
        pos.z = RESPAWN_POINT.z;
      }

      let playerPos = null;

      if (controller && animator) {
        if (!health.isDead) {
          const { isMoving, speed } = controller.update(delta);
          animator.update(delta, isMoving, speed);
        } else {
          animator.update(delta, false, 0);
        }

        playerPos = controller.position();
      }

      // Mana tiklanishi (regeneratsiya)
      maxMana = playerMaxMana(currentLevel, characterClass);
      const regen = playerManaRegen(currentLevel, characterClass);
      if (currentMana < maxMana) {
        currentMana = Math.min(maxMana, currentMana + regen * delta);
        manaTick += delta;
        if (manaTick > 0.25) {
          manaTick = 0;
          onCombatUpdate && onCombatUpdate({ mana: currentMana, maxMana });
        }
      }

      // Mahluqlar harakati, jangi va qayta tiklanishi
      const enemyPos = playerPos || {
        x: Number(playerPosition?.x) || 0,
        z: Number(playerPosition?.z) || 0,
      };
      enemies.update(delta, enemyPos);

      if (attack) {
        attack.update(delta);

        // ── Sehrgar va kamonboz: avtomatik nishonlash ──
        const autoRange = AUTO_TARGET_RANGE[characterClass?.id] || 0;
        if (autoRange > 0 && !health.isDead) {
          const found = enemies.nearestAlive(enemyPos, autoRange);
          if (found) {
            const dx = found.enemy.model.position.x - enemyPos.x;
            const dz = found.enemy.model.position.z - enemyPos.z;
            const d = Math.sqrt(dx * dx + dz * dz) || 1;
            attack.trigger({ x: dx / d, z: dz / d });
          }
        }
      }

      if (controller && animator) {
        const pos = controller.position();
        cameraRig.follow(camera, pos);
        stage.followLight(pos.x, pos.z);

        // Yaqin portalni aniqlash (faqat o'zgarganda chaqiriladi)
        let nearest = null;
        let minD = PORTAL_INTERACT_DISTANCE;
        for (const p of worldPortals) {
          const dx = p.position.x - pos.x;
          const dz = p.position.z - pos.z;
          const d = Math.sqrt(dx * dx + dz * dz);
          if (d < minD) {
            minD = d;
            nearest = p;
          }
        }
        const nearId = nearest ? nearest.portal_id : null;
        if (nearId !== lastNearId) {
          lastNearId = nearId;
          onNearPortal && onNearPortal(nearest);
        }
      }

      stage.render();
    };

    animate();

    const onBeforeUnload = () => {
      if (controller) controller.saveNow();
      onCombatUpdate &&
        onCombatUpdate({
          hp: Math.round(health.hp),
          enemy_state: enemies.state(),
          flush: true,
        });
    };
    window.addEventListener('beforeunload', onBeforeUnload);

    return () => {
      disposed = true;
      cancelAnimationFrame(animationId);
      window.removeEventListener('beforeunload', onBeforeUnload);
      if (controller) controller.saveNow();
      input.dispose();
      cameraRig.dispose();
      if (attack) attack.dispose();
      enemies.dispose();
      portalScene.dispose();
      stage.dispose();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [characterClass?.id]);

  return (
    <div
      ref={mountRef}
      className="w-full h-full relative cursor-grab active:cursor-grabbing select-none"
    />
  );
}
