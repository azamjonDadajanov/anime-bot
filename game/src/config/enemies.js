/**
 * MAHLUQLAR (Skeletons) — konfiguratsiya va jangovar formulalar.
 *
 * Qoidalar:
 *  - 1-darajada mahluq HAR BIR sinf uchun 7 ta hujumdan keyin nolga tushadi
 *    (mahluq HP = 7 × sinfning 1-daraja kuchi)
 *  - Daraja oshgani sari qahramon kuchi va maksimal joni oshadi
 *  - Mahluq o'lganda uning "kuchiga qarab" XP beriladi
 *  - Daraja oshgani sari maydonda KO'PROQ mahluq paydo bo'ladi
 *  - O'lgan mahluq 2 daqiqadan keyin qayta tiklanadi
 */

const MODEL = (name) => `/models/sketelons/${name}.glb`;

/** Mahluq turlari (qurol, hujum usuli, kuch → zarar va XP) */
export const ENEMY_TYPES = {
  minion: {
    id: 'minion',
    name: 'Skelet Askar',
    model: MODEL('Skeleton_Minion'),
    weaponModel: '/models/sketelons_items/Skeleton_Blade.gltf',
    weaponName: 'Skelet Xanjar',
    attackStyle: 'melee_slash',
    power: 1,
    xp: 25,
    speed: 2.3,
    scale: 1.05,
    damage: 8,
    attackRange: 1.8,
    attackCooldown: 1.2,
    aggro: 14,
  },
  rogue: {
    id: 'rogue',
    name: 'Skelet Qaroqchi',
    model: MODEL('Skeleton_Rogue'),
    weaponModel: '/models/sketelons_items/Skeleton_Crossbow.gltf',
    weaponName: 'Skelet Arbalet',
    attackStyle: 'quick_shot',
    power: 2,
    xp: 55,
    speed: 3.2,
    scale: 1.1,
    damage: 13,
    attackRange: 3.5,
    attackCooldown: 1.0,
    aggro: 16,
  },
  warrior: {
    id: 'warrior',
    name: 'Skelet Jangchi',
    model: MODEL('Skeleton_Warrior'),
    weaponModel: '/models/sketelons_items/Skeleton_Axe.gltf',
    shieldModel: '/models/sketelons_items/Skeleton_Shield_Large_A.gltf',
    weaponName: 'Skelet Bolta va Qalqon',
    attackStyle: 'axe_slam',
    power: 3,
    xp: 85,
    speed: 2.5,
    scale: 1.25,
    damage: 19,
    attackRange: 2.2,
    attackCooldown: 1.2,
    aggro: 15,
  },
  mage: {
    id: 'mage',
    name: 'Skelet Sehrgar',
    model: MODEL('Skeleton_Mage'),
    weaponModel: '/models/sketelons_items/Skeleton_Staff.gltf',
    weaponName: 'Sehrli Hassa',
    attackStyle: 'dark_orb',
    power: 4,
    xp: 120,
    speed: 2.1,
    scale: 1.2,
    damage: 24,
    attackRange: 8.0,
    attackCooldown: 1.8,
    aggro: 18,
  },
};

export const ENEMY_LIST = Object.values(ENEMY_TYPES);

/** O'lgan mahluq qayta tiklanishi (soniya) — 2 daqiqa */
export const RESPAWN_SECONDS = 120;

/** O'limidan keyin model sahnada yotadi va so'nadi */
export const DEATH_ANIM_SECONDS = 1.4;

// ── SPAWN JOYLARI (shahardan tashqarida, o'rmondagi ochiq joylar) ──
const SPOT_DEFS = [
  { deg: 8, r: 70 },
  { deg: 38, r: 76 },
  { deg: 66, r: 70 },
  { deg: 95, r: 84 },
  { deg: 122, r: 74 },
  { deg: 150, r: 88 },
  { deg: 176, r: 72 },
  { deg: 205, r: 80 },
  { deg: 232, r: 70 },
  { deg: 262, r: 78 },
  { deg: 292, r: 86 },
  { deg: 320, r: 72 },
  { deg: 350, r: 82 },
  { deg: 52, r: 100 },
  { deg: 160, r: 102 },
  { deg: 275, r: 104 },
];

export const SPAWN_SPOTS = SPOT_DEFS.map((s, i) => {
  const rad = (s.deg * Math.PI) / 180;
  return { index: i, x: Math.cos(rad) * s.r, z: Math.sin(rad) * s.r };
});

// ── JANGOVAR FORMULALAR ────────────────────────────────

/** Qahramonning maksimal joni (backend max_hp_for_level bilan mos) */
export function playerMaxHp(level) {
  return 100 + Math.max(0, (level || 1) - 1) * 25;
}

/** Qahramonning zarba kuchi: daraja oshgani sari oshadi */
export function playerDamage(characterClass, level) {
  const base = characterClass?.attackPower || 20;
  return Math.round(base * (1 + Math.max(0, (level || 1) - 1) * 0.18));
}

/**
 * Mahluqning maksimal joni: 1-darajadagi qahramon uni
 * ANIQ 7 ta hujumda yo'q qiladi.
 */
export function enemyMaxHp(characterClass) {
  const base = characterClass?.attackPower || 20;
  return 7 * base;
}

/** Mahluq kuchiga qarab beriladigan XP (daraja bilan biroz oshadi) */
export function xpForKill(enemy, level) {
  const base = enemy?.xp || 20;
  return Math.round(base * (1 + Math.max(0, (level || 1) - 1) * 0.05));
}

/** Daraja oshgani sari maydondagi mahluqlar soni oshadi */
export function enemyCountForLevel(level) {
  return Math.min(3 + (level || 1), SPAWN_SPOTS.length, 14);
}

/** Mahluqning qahramonga beradigan zarari (daraja bilan ozgina oshadi) */
export function enemyDamage(enemy, level) {
  const base = enemy?.damage || 6;
  return Math.round(base * (1 + Math.max(0, (level || 1) - 1) * 0.08));
}

/** Avtomatik nishonlash masofasi (sehrgar va kamonboz uchun) */
export const AUTO_TARGET_RANGE = {
  mage: 11,
  ranger: 15,
  warrior: 0,
  rogue: 0,
};

/** O'yinchining joni qayta tiklanishi (soniya) — jangdan keyin */
export const HP_REGEN = { amount: 4, interval: 5.0, delayAfterHit: 6.0 };

/** O'limga uchraganda qayta tug'ilish nuqtasi (shahar markazi) */
export const RESPAWN_POINT = { x: 0, z: 0 };
