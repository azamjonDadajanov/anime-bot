import { deg } from '../env/constants';

/**
 * PORTALLAR QAYIDA OCHILADI — shahardan tashqaridagi o'rmondagi maydonchalar.
 *
 * Har bir maydoncha shahar devoridan tashqarida, o'rmon halqa yo'li
 * bo'ylab (r = 92) joylashgan. Maydonchalar markazlashgan holda
 * dumaloq yo'ldan bir oz tashqarida turadi, ya'ni portallar shahar
 * ichida HECH qachon paydo bo'lmaydi.
 *
 * Har bir maydoncha (clearing) bir martalik: portali yo'q qilingandan
 * keyin u maydoncha ishlatilmaydi va keyingi portal BOSHQA maydonchada
 * ochiladi.
 */

export const CLEARING_RADIUS = 11;

// O'rmon halqa yo'li bilan to'qnashmaydigan, ammo unga yaqin
// nuqtalar. 195°-240° oraliq qoldirilgan (u yerda qadimiy harobalar).
// Maydonchalar kengaytirilgan xaritada (WORLD_LIMIT=115) chuqurroq
// o'rmon ichida, r=92 masofada joylashgan.
const CLEARING_ANGLES_DEG = [15, 45, 75, 105, 135, 165, 255, 285, 315, 345];
const CLEARING_RADIUS_DIST = 92;

export const PORTAL_CLEARINGS = CLEARING_ANGLES_DEG.map((a, idx) => {
  const rad = deg(a);
  return {
    index: idx,
    angle: rad,
    x: Math.cos(rad) * CLEARING_RADIUS_DIST,
    z: Math.sin(rad) * CLEARING_RADIUS_DIST,
  };
});

/** Keyingi (ishlatilmagan) maydonchani qaytaradi — skobka (cursor) bo'yicha */
export function slotAt(cursor) {
  return PORTAL_CLEARINGS[cursor % PORTAL_CLEARINGS.length];
}

/** Nuqtaning qaysi maydonchaga yaqinligini (agar yaqin bo'lsa) qaytaradi */
export function findClearing(x, z) {
  for (const c of PORTAL_CLEARINGS) {
    const dx = c.x - x;
    const dz = c.z - z;
    if (Math.sqrt(dx * dx + dz * dz) <= CLEARING_RADIUS) return c;
  }
  return null;
}
