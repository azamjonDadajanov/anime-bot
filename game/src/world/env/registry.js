/**
 * Dunyo ustida paydo bo'lgan texnik reestrlar:
 *  - COLLISION_BOXES: harakat to'sig'i (AABB)
 *  - CLOUD_MESHES: harakatlanuvchi bulutlar
 */
export const COLLISION_BOXES = [];
export const CLOUD_MESHES = [];

export function resetRegistry() {
  COLLISION_BOXES.length = 0;
  CLOUD_MESHES.length = 0;
}

/** Markaz va yarim o'lchamlari bo'yicha to'siq qo'shadi */
export function addBox(x, z, halfW, halfD) {
  COLLISION_BOXES.push({
    minX: x - halfW,
    maxX: x + halfW,
    minZ: z - halfD,
    maxZ: z + halfD,
  });
}

/** Nuqta A to'siq ichida ekanini tekshiradi (radius bilan) */
export function isBlocked(x, z, radius = 0) {
  for (let i = 0; i < COLLISION_BOXES.length; i++) {
    const b = COLLISION_BOXES[i];
    if (
      x + radius > b.minX &&
      x - radius < b.maxX &&
      z + radius > b.minZ &&
      z - radius < b.maxZ
    ) {
      return true;
    }
  }
  return false;
}
