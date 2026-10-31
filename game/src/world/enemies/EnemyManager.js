import * as THREE from 'three';
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js';
import { clone as cloneSkeleton } from 'three/examples/jsm/utils/SkeletonUtils.js';
import { CharacterAnimator } from '../player/CharacterAnimator';
import { HealthBar } from './HealthBar';
import { isBlocked } from '../env/registry';
import { resolveBone } from '../../config/weapons';
import { instantiate } from '../env/modelCache';
import {
  DEATH_ANIM_SECONDS,
  ENEMY_TYPES,
  ENEMY_LIST,
  RESPAWN_SECONDS,
  SPAWN_SPOTS,
  enemyCountForLevel,
  enemyDamage,
  enemyMaxHp,
  xpForKill,
} from '../../config/enemies';

const ENEMY_RADIUS = 0.7;
const WANDER_RADIUS = 7;

/**
 * MAHLUQLAR MENEGERI (Skeletlar)
 *
 *  - Daraja oshgani sari ko'proq mahluq paydo bo'ladi
 *  - Har biri o'z joyida (spawn nuqtasi) kezib yuradi, yaqinlashsa hujum qiladi
 *  - O'lganda 2 daqiqadan keyin o'z joyida qayta tiklanadi
 *  - Holat (o'lim vaqti, HP, joy) `state()` orqali olinadi va bazaga saqlanadi
 *  - `hitTest` / `findAt` orqali qahramon zarbalari tekshiriladi
 */
export function createEnemyManager({
  scene,
  characterClass,
  getLevel,
  onKill,
  onPlayerHit,
  onStateChange,
}) {
  const loader = new GLTFLoader();
  const templateCache = new Map();
  const enemies = [];
  const projectiles = [];
  let disposed = false;

  function spawnEnemyProjectile(enemy, targetPos, dmg) {
    const isMage = enemy.type.id === 'mage';

    let mesh;
    if (isMage) {
      mesh = new THREE.Mesh(
        new THREE.SphereGeometry(0.32, 10, 10),
        new THREE.MeshStandardMaterial({
          color: '#7e22ce',
          emissive: '#a855f7',
          emissiveIntensity: 1.8,
          roughness: 0.3,
        })
      );
    } else {
      mesh = new THREE.Mesh(
        new THREE.CylinderGeometry(0.04, 0.04, 0.85, 6),
        new THREE.MeshStandardMaterial({ color: '#78350f', roughness: 0.8 })
      );
      mesh.rotation.x = Math.PI / 2;
    }

    const startX = enemy.model.position.x;
    const startY = 1.35;
    const startZ = enemy.model.position.z;
    mesh.position.set(startX, startY, startZ);
    mesh.castShadow = true;
    scene.add(mesh);

    const dx = targetPos.x - startX;
    const dz = targetPos.z - startZ;
    const len = Math.sqrt(dx * dx + dz * dz) || 1;
    const dir = new THREE.Vector3(dx / len, 0, dz / len);

    mesh.lookAt(targetPos.x, startY, targetPos.z);

    projectiles.push({
      mesh,
      dir,
      speed: isMage ? 8.5 : 15.0,
      damage: dmg,
      enemy,
      traveled: 0,
      maxRange: enemy.type.attackRange * 1.3,
    });
  }

  // ── Model shablonlarini yuklash (har xil tur uchun bir marta) ──
  function loadTemplate(path) {
    if (!templateCache.has(path)) {
      templateCache.set(
        path,
        new Promise((resolve) => {
          loader.load(path, (gltf) => resolve(gltf.scene), undefined, () => resolve(null));
        })
      );
    }
    return templateCache.get(path);
  }

  /** Boshlang'ich ro'yxat: daraja uchun kerakli sonida mahluq */
  async function init(savedState = {}) {
    const level = getLevel();
    const count = enemyCountForLevel(level);
    const maxHp = enemyMaxHp(characterClass);

    const jobs = [];
    for (let i = 0; i < count; i++) {
      const type = ENEMY_LIST[i % ENEMY_LIST.length];
      jobs.push(spawn(type, SPAWN_SPOTS[i % SPAWN_SPOTS.length], maxHp, savedState));
    }
    await Promise.all(jobs);

    // Daraja oshganda qo'shimcha mahluqlar keyingi `syncCount` chaqiruvida qo'shiladi
    applySavedState(savedState);
    return enemies.length;
  }

  async function spawn(type, spot, maxHp, savedState) {
    if (disposed) return;
    const template = await loadTemplate(type.model);
    if (disposed || !template) return;

    const model = cloneSkeleton(template);
    model.scale.setScalar(type.scale);
    model.position.set(spot.x, 0, spot.z);
    model.rotation.y = Math.random() * Math.PI * 2;
    model.traverse((node) => {
      if (node.isMesh || node.isSkinnedMesh) {
        node.castShadow = true;
        node.receiveShadow = true;
        node.frustumCulled = false;
      }
    });

    scene.add(model);

    const hpBar = new HealthBar(1.7);
    hpBar.sprite.position.set(spot.x, 3.1 * type.scale, spot.z);
    scene.add(hpBar.sprite);

    // Mahluq quroli va qalqonini biriktirish
    if (type.weaponModel) {
      const rHand = resolveBone(model, 'handslotr') || resolveBone(model, 'handr');
      if (rHand) {
        instantiate(type.weaponModel).then((wModel) => {
          if (wModel && !disposed) {
            wModel.scale.setScalar(0.7);
            wModel.rotation.set(0, 0, -Math.PI / 2);
            rHand.add(wModel);
          }
        }).catch(() => {});
      }
    }
    if (type.shieldModel) {
      const lHand = resolveBone(model, 'handslotl') || resolveBone(model, 'handl');
      if (lHand) {
        instantiate(type.shieldModel).then((sModel) => {
          if (sModel && !disposed) {
            sModel.scale.setScalar(0.75);
            sModel.rotation.set(-Math.PI / 2, 0, 0);
            lHand.add(sModel);
          }
        }).catch(() => {});
      }
    }

    const enemy = {
      id: `${type.id}_${spot.index}`,
      type,
      spot,
      model,
      animator: new CharacterAnimator(model),
      hpBar,
      hp: maxHp,
      maxHp,
      dead: false,
      deadUntil: 0,
      deathT: 0,
      attackTimer: Math.random() * type.attackCooldown,
      wander: { x: spot.x, z: spot.z },
      wanderTimer: 0,
      level: getLevel(),
    };

    enemies.push(enemy);
  }

  /** Bazadan kelgan holatni qo'llash (o'lim vaqtlari, HP) */
  function applySavedState(state) {
    if (!state) return;
    const now = Date.now() / 1000;
    for (const e of enemies) {
      const s = state[e.id];
      if (!s) continue;
      if (s.dead_until && s.dead_until > now) {
        e.dead = true;
        e.deadUntil = s.dead_until;
        e.deathT = DEATH_ANIM_SECONDS; // model yotgan holatda
        e.model.rotation.x = -Math.PI / 2;
        e.model.visible = false;
        e.hpBar.show(false);
      } else if (typeof s.hp === 'number' && s.hp > 0 && s.hp < e.maxHp) {
        e.hp = s.hp;
      }
    }
  }

  /** Daraja oshganda mahluqlar sonini yangilash */
  function syncCount() {
    const want = enemyCountForLevel(getLevel());
    if (enemies.length >= want) return;
    const maxHp = enemyMaxHp(characterClass);
    for (let i = enemies.length; i < want; i++) {
      const type = ENEMY_LIST[i % ENEMY_LIST.length];
      spawn(type, SPAWN_SPOTS[i % SPAWN_SPOTS.length], maxHp, {});
    }
  }

  // ── JANG ──────────────────────────────────────────────

  /** Berilgan nuqtadagi tirik mahluqni qaytaradi (qurol zarbasi uchun) */
  function findAt(pos, radius = 1.1) {
    for (const e of enemies) {
      if (e.dead) continue;
      const dx = e.model.position.x - pos.x;
      const dz = e.model.position.z - pos.z;
      if (dx * dx + dz * dz <= (radius + ENEMY_RADIUS) * (radius + ENEMY_RADIUS)) return e;
    }
    return null;
  }

  /**
   * oldindagi yo'nalish bo'yicha qo'l zarbasi: reach masofasida
   * va sektor ichidagi birinchi mahluq
   */
  function hitTest(pos, dirX, dirZ, reach, angleCos = 0.35) {
    let best = null;
    let bestD = Infinity;
    for (const e of enemies) {
      if (e.dead) continue;
      const dx = e.model.position.x - pos.x;
      const dz = e.model.position.z - pos.z;
      const d = Math.sqrt(dx * dx + dz * dz);
      if (d > reach + ENEMY_RADIUS || d >= bestD) continue;
      if (d > 0.001) {
        const dot = (dx / d) * dirX + (dz / d) * dirZ;
        if (dot < angleCos) continue;
      }
      best = e;
      bestD = d;
    }
    return best;
  }

  /** Eng yaqin tirik mahluq (avtomatik nishonlash uchun) */
  function nearestAlive(pos, maxRange = Infinity) {
    let best = null;
    let bestD = maxRange;
    for (const e of enemies) {
      if (e.dead) continue;
      const dx = e.model.position.x - pos.x;
      const dz = e.model.position.z - pos.z;
      const d = Math.sqrt(dx * dx + dz * dz);
      if (d < bestD) {
        bestD = d;
        best = e;
      }
    }
    return best ? { enemy: best, distance: bestD } : null;
  }

  /** Zarba berish (qaytargan qiymat: XP yoki 0) */
  function applyDamage(enemy, damage) {
    if (!enemy || enemy.dead) return 0;
    enemy.hp -= Math.max(1, damage);
    enemy.hpBar.set(enemy.hp / enemy.maxHp);
    enemy.hpBar.show(true);

    if (enemy.hp <= 0) {
      kill(enemy);
      return xpForKill(enemy.type, getLevel());
    }
    return 0;
  }

  function kill(enemy) {
    enemy.dead = true;
    enemy.deadUntil = Date.now() / 1000 + RESPAWN_SECONDS;
    enemy.deathT = 0;
    enemy.hp = 0;
    enemy.hpBar.show(false);
    onStateChange && onStateChange();
    onKill && onKill({ id: enemy.id, type: enemy.type });
  }

  // ── HARAKAT ───────────────────────────────────────────

  function moveToward(enemy, tx, tz, speed, delta) {
    const p = enemy.model.position;
    const dx = tx - p.x;
    const dz = tz - p.z;
    const dist = Math.sqrt(dx * dx + dz * dz);
    if (dist < 0.05) return false;

    const stepX = (dx / dist) * speed * delta;
    const stepZ = (dz / dist) * speed * delta;

    const nx = p.x + stepX;
    const nz = p.z + stepZ;

    // To'siqlar (uy, devor, daraxt) — har bir o'qni alohida sinash
    if (!isBlocked(nx, p.z, ENEMY_RADIUS)) p.x = nx;
    if (!isBlocked(p.x, nz, ENEMY_RADIUS)) p.z = nz;

    // Xarita chegarasi
    const r = Math.sqrt(p.x * p.x + p.z * p.z);
    if (r > 108) {
      p.x = (p.x / r) * 108;
      p.z = (p.z / r) * 108;
    }

    // Yuzlanish
    const targetAngle = Math.atan2(dx, dz);
    let diff = targetAngle - enemy.model.rotation.y;
    while (diff < -Math.PI) diff += Math.PI * 2;
    while (diff > Math.PI) diff -= Math.PI * 2;
    enemy.model.rotation.y += diff * 8 * Math.min(1, delta * 10);

    return true;
  }

  function update(delta, playerPos, onStateChangeDirty) {
    const level = getLevel();

    for (const e of enemies) {
      // ── O'lim animatsiyasi va qayta tiklanish ──
      if (e.dead) {
        if (e.model.visible) {
          e.deathT = Math.min(DEATH_ANIM_SECONDS, e.deathT + delta);
          const t = e.deathT / DEATH_ANIM_SECONDS;
          e.model.rotation.x = -Math.PI / 2 * t; // yiqilish
          e.model.position.y = -1.2 * t; // yer ostiga cho'mish
          if (t >= 1) e.model.visible = false;
        }

        const now = Date.now() / 1000;
        if (now >= e.deadUntil) {
          // QAYTA TIKLANISH (2 daqiqa)
          e.dead = false;
          e.hp = enemyMaxHp(characterClass);
          e.maxHp = e.hp;
          e.model.visible = true;
          e.model.rotation.x = 0;
          e.model.position.set(e.spot.x, 0, e.spot.z);
          e.hpBar.set(1);
          e.hpBar.show(false);
          e.attackTimer = e.type.attackCooldown;
          onStateChangeDirty && onStateChangeDirty();
        }
        continue;
      }

      const p = e.model.position;
      const dx = playerPos.x - p.x;
      const dz = playerPos.z - p.z;
      const dist = Math.sqrt(dx * dx + dz * dz);

      let isMoving = false;

      if (dist <= e.type.aggro) {
        if (dist > e.type.attackRange) {
          isMoving = moveToward(e, playerPos.x, playerPos.z, e.type.speed, delta);
        } else {
          // Hujum
          const targetAngle = Math.atan2(dx, dz);
          let diff = targetAngle - e.model.rotation.y;
          while (diff < -Math.PI) diff += Math.PI * 2;
          while (diff > Math.PI) diff -= Math.PI * 2;
          e.model.rotation.y += diff * 10 * Math.min(1, delta * 10);

          e.attackTimer -= delta;
          if (e.attackTimer <= 0) {
            e.attackTimer = e.type.attackCooldown;
            e.animator.playAttack();
            const dmg = enemyDamage(e.type, level);

            // Sehrgar va Kamonchi masofadan snaryad otadi
            if (e.type.attackStyle === 'dark_orb' || e.type.attackStyle === 'quick_shot') {
              spawnEnemyProjectile(e, playerPos, dmg);
            } else {
              onPlayerHit && onPlayerHit(dmg, e);
            }
          }
        }
      } else {
        // Kechirish (wander) — o'z joyi atrofida
        e.wanderTimer -= delta;
        if (e.wanderTimer <= 0) {
          e.wanderTimer = 3 + Math.random() * 4;
          const a = Math.random() * Math.PI * 2;
          const r = Math.random() * WANDER_RADIUS;
          e.wander.x = e.spot.x + Math.cos(a) * r;
          e.wander.z = e.spot.z + Math.sin(a) * r;
        }
        isMoving = moveToward(e, e.wander.x, e.wander.z, e.type.speed * 0.55, delta);
      }

      e.animator.update(delta, isMoving, isMoving ? e.type.speed : 0);

      // HP chizig'i baland joyda turadi
      e.hpBar.sprite.position.set(p.x, 3.1 * e.type.scale + 0.3, p.z);
    }

    // ── Mahluq snaryadlari harakati va o'yinchiga urilishi ──
    for (let i = projectiles.length - 1; i >= 0; i--) {
      const pr = projectiles[i];
      const step = pr.speed * delta;
      pr.mesh.position.addScaledVector(pr.dir, step);
      pr.traveled += step;

      const pdx = pr.mesh.position.x - playerPos.x;
      const pdz = pr.mesh.position.z - playerPos.z;
      const pdist = Math.sqrt(pdx * pdx + pdz * pdz);

      if (pdist < 1.15) {
        // O'yinchiga urildi!
        onPlayerHit && onPlayerHit(pr.damage, pr.enemy);
        scene.remove(pr.mesh);
        pr.mesh.geometry?.dispose();
        pr.mesh.material?.dispose();
        projectiles.splice(i, 1);
        continue;
      }

      if (pr.traveled >= pr.maxRange) {
        scene.remove(pr.mesh);
        pr.mesh.geometry?.dispose();
        pr.mesh.material?.dispose();
        projectiles.splice(i, 1);
      }
    }
  }

  /** Bazaga saqlash uchun holat */
  function state() {
    const out = {};
    for (const e of enemies) {
      out[e.id] = {
        dead_until: e.dead ? Math.round(e.deadUntil) : 0,
        spot: e.spot.index,
        hp: Math.max(0, Math.round(e.hp)),
      };
    }
    return out;
  }

  function dispose() {
    disposed = true;
    for (const pr of projectiles) {
      scene.remove(pr.mesh);
      pr.mesh.geometry?.dispose();
      pr.mesh.material?.dispose();
    }
    projectiles.length = 0;

    for (const e of enemies) {
      scene.remove(e.model);
      scene.remove(e.hpBar.sprite);
      e.hpBar.dispose();
    }
    enemies.length = 0;
  }

  return {
    init,
    update,
    syncCount,
    state,
    applySavedState,
    applyDamage,
    findAt,
    hitTest,
    nearestAlive,
    dispose,
    get count() {
      return enemies.length;
    },
    get alive() {
      return enemies.filter((e) => !e.dead).length;
    },
    /** XP hisoblash uchun (o'ldirilgan mahluq kuchi) */
    xpOf: (enemy) => xpForKill(enemy.type, getLevel()),
    ENEMY_TYPES,
  };
}
