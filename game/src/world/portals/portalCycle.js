import { getStoredUser } from '../../services/api';
import { slotAt } from './spawnPoints';

/**
 * PORTAL TURMUSH DAVRI (portal lifecycle)
 *
 * Qoidalar:
 *  1. Portallar faqat shahardan tashqaridagi o'rmondagi maydonchalarda ochiladi.
 *  2. Bir marta yengilgan portal server cooldown'ga kiradi va xaritadan
 *     darhol yo'qoladi (client tomonda ham doimiy ravishda yashiriladi).
 *  3. O'rniga BOSHQA portal ochiladi — va u har doim YANGI maydonchada.
 *  4. Barcha portal yengilgandan keyin server ruxsat berganda yangi sikl
 *     boshlanadi: portallar qayta ochiladi, lekin yangi joylarda.
 *
 * Bir vaqtning o'zida MAX_VISIBLE ta portal ko'rinadi.
 */

const MAX_VISIBLE = 1;

function storageKey() {
  const user = getStoredUser();
  const scope = user?.user_id ? `_${user.user_id}` : '';
  return `artifact_hunter_portal_cycle_v1${scope}`;
}

function defaultState() {
  return { cycle: 1, rotation: 0, cursor: 0, cleared: {}, slots: {} };
}

function loadState() {
  try {
    const raw = localStorage.getItem(storageKey());
    if (raw) {
      const parsed = JSON.parse(raw);
      if (parsed && typeof parsed === 'object') {
        return { ...defaultState(), ...parsed };
      }
    }
  } catch (e) {}
  return defaultState();
}

function saveState(state) {
  try {
    localStorage.setItem(storageKey(), JSON.stringify(state));
  } catch (e) {}
}

/**
 * Backend portallarini o'yin dunyosidagi portal holatiga aylantiradi:
 * ko'rinadigan portallarni tanlaydi va ularning o'rmondagi
 * koordinatalarini beradi.
 */
export function prepareWorldPortals(portals) {
  if (!Array.isArray(portals) || portals.length === 0) return [];

  const state = loadState();

  // API'dan yo'qolgan portallarning yozuvlarini tozalaymiz
  const knownIds = new Set(portals.map((p) => String(p.portal_id)));
  Object.keys(state.cleared).forEach((id) => {
    if (!knownIds.has(id)) delete state.cleared[id];
  });
  Object.keys(state.slots).forEach((id) => {
    if (!knownIds.has(id)) delete state.slots[id];
  });

  // Serverda cooldown dagi portal ko'rinmaydi
  const serverReady = portals.filter((p) => !p.is_in_cooldown);

  let available = serverReady.filter(
    (p) => state.cleared[String(p.portal_id)] !== true
  );

  // Hamma portal yengildi → yangi sikl (boshqa portal, yangi joyda)
  if (serverReady.length > 0 && available.length === 0) {
    state.cleared = {};
    state.slots = {};
    state.cycle = (state.cycle || 1) + 1;
    state.rotation = (state.rotation + 1) % portals.length;
    saveState(state);
    available = serverReady.slice();
  }

  if (available.length === 0) return [];

  // Aylanma: har safar navbatdagi boshqa portal ochiladi
  const start = ((state.rotation % available.length) + available.length) % available.length;
  const ordered = available.slice(start).concat(available.slice(0, start));
  const visible = ordered.slice(0, MAX_VISIBLE);

  const result = visible.map((portal) => {
    const key = String(portal.portal_id);

    if (state.slots[key] == null) {
      state.slots[key] = state.cursor || 0;
      state.cursor = (state.cursor || 0) + 1;
    }
    const slot = slotAt(state.slots[key]);

    return {
      ...portal,
      spawnSlot: slot.index,
      position: { x: slot.x, y: 0, z: slot.z },
    };
  });

  saveState(state);
  return result;
}

/** Portal yengilganda chaqiriladi — u xaritadan butunlay olib tashlanadi. */
export function markPortalCleared(portalId) {
  if (portalId == null) return;
  const state = loadState();
  const key = String(portalId);

  state.cleared[key] = true;
  delete state.slots[key];
  state.rotation = (state.rotation + 1) % 64;
  state.cursor = (state.cursor || 0) + 1;

  saveState(state);
}

/** Faqat test/tekshiruch maqsadida: barcha portal yozuvlarini tozalaydi */
export function resetPortalCycle() {
  try {
    localStorage.removeItem(storageKey());
  } catch (e) {}
}
