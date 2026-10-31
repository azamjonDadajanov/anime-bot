/**
 * Dunyo (open world) geometrikasi uchun umumiy konstantalar.
 * Shahar, yo'llar, o'rmon va xarita chegaralari shu yerda markazlashtirilgan.
 */

// O'yinchining markazdan maksimal masofasi (kengaytirilgan xarita)
export const WORLD_LIMIT = 115;

// ── SHAHAR ─────────────────────────────────────────────
export const CITY_RADIUS = 60; // shahar devori radiusi
export const TOWN_FLOOR_RADIUS = 61.5; // tosh pol diski radiusi
export const WALL_HEIGHT = 9;
export const WALL_THICKNESS = 2.2;
export const PLAZA_RADIUS = 13; // markaziy maydon

// Darvozalar (shahar chiqishlari) burchaklari
export const GATE_ANGLES = [0, Math.PI / 2, Math.PI, -Math.PI / 2];

// Halqa yo'llar (ichki va tashqi)
export const RING_ROADS = [
  { inner: 13, outer: 20 },
  { inner: 35, outer: 42 },
];

// Radius yo'llar (avenue) kengligi
export const AVENUE_WIDTH = 6.5;

// Uy joylashuv halqalari: radius va boshlanish burchagi
export const HOUSE_RINGS = [
  { radius: 27, count: 12, offsetDeg: 15 },
  { radius: 51, count: 12, offsetDeg: 15 },
];

// ── O'RMON ─────────────────────────────────────────────
export const FOREST_RING = { inner: 64, outer: 69 }; // o'rmon halqa yo'li
export const FOREST_PATH_START = CITY_RADIUS; // shahardan chiqadigan yo'l
export const FOREST_PATH_END = WORLD_LIMIT;
export const FOREST_PATH_WIDTH = 5;
export const FOREST_MIN_R = 62;
export const FOREST_MAX_R = 110;

// Daraxtlar shu oraliqda o'sadi (yo'l, maydoncha va ochiq maydonlar bo'sh qolinadi)
export const TREE_MIN_R = 71;
export const TREE_MAX_R = 108;

// ── KATTA OCHIQ MAYDONLAR (meadows) ───────────────────
// O'rmondagi keng, butunlay ochiq joylar — daraxtsiz holda katta
// maydonlar shu yerda joylashadi. radius 80, atrofi 17 birlik.
export const MEADOWS = [0, 60, 120, 180, 240, 300].map((d) => {
  const rad = deg(d);
  return { x: Math.cos(rad) * 82, z: Math.sin(rad) * 82, r: 17 };
});

// Qadimiy harobalar joylashuvi (o'rmon ichida, shimoli-g'arb)
export const RUIN_SPOTS = [
  { x: -69.5, z: -25.3 },
  { x: -67.5, z: -39.0 },
  { x: -57.6, z: -45.9 },
  { x: -55.6, z: -57.5 },
  { x: -45.6, z: -58.3 },
  { x: -76.1, z: -35.5 },
];

/** Ikki burchak orasidagi farqni [-PI, PI] orasida qaytaradi */
export function angleDiff(a, b) {
  let d = (a - b) % (Math.PI * 2);
  if (d > Math.PI) d -= Math.PI * 2;
  if (d < -Math.PI) d += Math.PI * 2;
  return d;
}

/** Burchak (radian) → x, z koordinatasi */
export function polar(angle, radius) {
  return { x: Math.cos(angle) * radius, z: Math.sin(angle) * radius };
}

/** Daraja → radians */
export function deg(value) {
  return (value * Math.PI) / 180;
}

/** Shunchalik burchaklarda (offset + step*k) massiv qaytaradi */
export function angleSlots(count, offsetDeg = 0) {
  const step = (Math.PI * 2) / count;
  const offset = deg(offsetDeg);
  return Array.from({ length: count }, (_, i) => offset + i * step);
}
