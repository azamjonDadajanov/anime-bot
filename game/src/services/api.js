/**
 * Django Backend REST API Client & Auth
 * API manzili: https://api.anichopar.uz/api/game/...
 */

const getApiBase = () => {
  const envUrl = import.meta.env.VITE_API_BASE_URL;
  if (envUrl) {
    const clean = envUrl.replace(/\/+$/, '');
    return `${clean}/game`;
  }
  if (typeof window !== 'undefined' && window.location.hostname.endsWith('anichopar.uz')) {
    return 'https://api.anichopar.uz/api/game';
  }
  return '/api/game';
};

const API_BASE = getApiBase();

export function getStoredUser() {
  try {
    const raw = localStorage.getItem('artifact_hunter_user');
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}

export function setStoredUser(user) {
  try {
    localStorage.setItem('artifact_hunter_user', JSON.stringify(user));
  } catch {}
}

export function clearStoredUser() {
  try {
    localStorage.removeItem('artifact_hunter_user');
  } catch {}
}

function getAuthHeaders() {
  const headers = { 'Content-Type': 'application/json' };
  const user = getStoredUser();
  if (user?.telegram_id) {
    headers['X-Telegram-ID'] = String(user.telegram_id);
  }
  if (user?.user_id) {
    headers['X-User-ID'] = String(user.user_id);
  }
  return headers;
}

export async function loginOrRegister(action, username, password) {
  try {
    const res = await fetch(`${API_BASE}/artifact/auth/`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ action, username, password }),
    });
    const data = await res.json();
    if (data.success) {
      setStoredUser({ username: data.username, user_id: data.user_id });
    }
    return data;
  } catch (err) {
    return { success: false, error: 'Server bilan aloqa uzildi' };
  }
}

export async function autoAuthTelegram(tgUser) {
  try {
    const res = await fetch(`${API_BASE}/artifact/auth/`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        action: 'telegram',
        telegram_id: tgUser.id,
        first_name: tgUser.first_name,
        username: tgUser.username,
      }),
    });
    const data = await res.json();
    if (data.success) {
      setStoredUser({
        username: data.username,
        user_id: data.user_id,
        telegram_id: tgUser.id,
        first_name: data.first_name,
      });
    }
    return data;
  } catch (err) {
    return { success: false, error: 'Telegram auth xatosi' };
  }
}

export async function fetchGameState() {
  try {
    const res = await fetch(`${API_BASE}/artifact/state/`, {
      headers: getAuthHeaders(),
    });
    if (!res.ok) throw new Error('Failed to fetch game state');
    return await res.json();
  } catch (err) {
    console.error('fetchGameState error:', err);
    return null;
  }
}

export async function selectCharacterClass(characterClass) {
  try {
    const res = await fetch(`${API_BASE}/artifact/select-character/`, {
      method: 'POST',
      headers: getAuthHeaders(),
      body: JSON.stringify({ character_class: characterClass }),
    });
    return await res.json();
  } catch (err) {
    return { success: false };
  }
}

export async function enterPortal(portalId) {
  try {
    const res = await fetch(`${API_BASE}/artifact/enter-portal/`, {
      method: 'POST',
      headers: getAuthHeaders(),
      body: JSON.stringify({ portal_id: portalId }),
    });
    return await res.json();
  } catch (err) {
    return { success: false, error: 'Server bilan aloqa uzildi' };
  }
}

export async function savePlayerPosition(x, y, z, characterClass = null) {
  try {
    await fetch(`${API_BASE}/artifact/save-position/`, {
      method: 'POST',
      headers: getAuthHeaders(),
      body: JSON.stringify({ x, y, z, character_class: characterClass }),
    });
  } catch (err) {
    // Non-blocking
  }
}

/**
 * Jangovar holatni bazaga saqlash: tajriba (daraja), jon, o'ldirilgan
 * mahluqlar va mahluqlarning qayta tiklanish vaqti.
 * Server darajani hisoblab qaytaradi.
 */
export async function saveCombat({
  exp_gained = 0,
  hp = null,
  kills = null,
  enemy_state = null,
} = {}) {
  try {
    const res = await fetch(`${API_BASE}/artifact/combat/`, {
      method: 'POST',
      headers: getAuthHeaders(),
      body: JSON.stringify({ exp_gained, hp, kills, enemy_state }),
    });
    if (!res.ok) throw new Error('combat save failed');
    return await res.json();
  } catch (err) {
    console.error('saveCombat error:', err);
    return { success: false };
  }
}

// ─── Jang Tizimi API ─────────────────────────────────────────────────────────

/** Portalga kirib jang boshlatish */
export async function startBattle(portalId) {
  try {
    const res = await fetch(`${API_BASE}/artifact/battle/start/`, {
      method: 'POST',
      headers: getAuthHeaders(),
      body: JSON.stringify({ portal_id: portalId }),
    });
    return await res.json();
  } catch {
    return null;
  }
}

/** Keyingi to'lqinga o'tish */
export async function nextWave({ battle_id, wave_xp, wave_coins, wave_kills }) {
  try {
    const res = await fetch(`${API_BASE}/artifact/battle/next-wave/`, {
      method: 'POST',
      headers: getAuthHeaders(),
      body: JSON.stringify({ battle_id, wave_xp, wave_coins, wave_kills }),
    });
    return await res.json();
  } catch {
    return null;
  }
}

/** Jangni muvaffaqiyatli yakunlash */
export async function completeBattle({ battle_id, total_xp, total_coins, total_kills }) {
  try {
    const res = await fetch(`${API_BASE}/artifact/battle/complete/`, {
      method: 'POST',
      headers: getAuthHeaders(),
      body: JSON.stringify({ battle_id, total_xp, total_coins, total_kills }),
    });
    return await res.json();
  } catch {
    return null;
  }
}

/** Jangdan qochish */
export async function fleeBattle({ battle_id, partial_xp, partial_coins, partial_kills }) {
  try {
    const res = await fetch(`${API_BASE}/artifact/battle/flee/`, {
      method: 'POST',
      headers: getAuthHeaders(),
      body: JSON.stringify({ battle_id, partial_xp, partial_coins, partial_kills }),
    });
    return await res.json();
  } catch {
    return null;
  }
}

/** Buyumni taqish / yechish */
export async function toggleEquipItem(inventoryId, itemId) {
  try {
    const res = await fetch(`${API_BASE}/artifact/inventory/toggle-equip/`, {
      method: 'POST',
      headers: getAuthHeaders(),
      body: JSON.stringify({ inventory_id: inventoryId, item_id: itemId }),
    });
    return await res.json();
  } catch {
    return { success: false };
  }
}

/** XP tizimi: keyingi darajaga kerakli XP (frontendda hisoblash uchun) */
export function xpRequiredForLevel(level) {
  return Math.round(500 * Math.pow(level, 1.85));
}
