/**
 * XP, DARAJA VA MANA TIZIMI
 *
 * 1. XP va Daraja:
 *    - Har safar daraja oshganda keyingi darajaga chiqish uchun KO'PROQ XP talab qilinadi:
 *      Level 1: 500 XP
 *      Level 2: 675 XP
 *      Level 3: 911 XP
 *      Level 4: 1230 XP
 *      Level 5: 1661 XP ...
 *      Formula: round(500 * (1.35 ^ (level - 1)))
 *
 * 2. Mana Tizimi:
 *    - Har bir hujum Mana sarflaydi
 *    - Mana tugasa hujum to'xtaydi (hujum qilib bo'lmaydi)
 *    - Mana vaqt o'tishi bilan silliq to'ladi (regeneratsiya)
 */

export function xpRequiredForLevel(level) {
  const lvl = Math.max(1, parseInt(level, 10) || 1);
  return Math.round(500 * Math.pow(1.35, lvl - 1));
}

/**
 * Jami to'plangan XP dan:
 *  - level: joriy daraja
 *  - currentExp: ushbu darajadagi progress
 *  - neededExp: ushbu darajani tugatish uchun kerakli XP
 *  - progressPct: 0..100 foiz
 */
export function getLevelInfo(totalXp) {
  let level = 1;
  let xp = Math.max(0, Math.round(totalXp || 0));

  while (true) {
    const needed = xpRequiredForLevel(level);
    if (xp >= needed) {
      xp -= needed;
      level += 1;
    } else {
      break;
    }
  }

  const neededExp = xpRequiredForLevel(level);
  const progressPct = Math.min(100, Math.max(0, (xp / neededExp) * 100));

  return {
    level,
    currentExp: xp,
    neededExp,
    progressPct,
  };
}

/** Qahramon maksimal manasi (daraja bilan oshadi) */
export function playerMaxMana(level, characterClass) {
  const classBase = characterClass?.id === 'mage' ? 140
                  : characterClass?.id === 'ranger' ? 110
                  : characterClass?.id === 'rogue' ? 95
                  : 100; // warrior
  return classBase + Math.max(0, (level || 1) - 1) * 15;
}

/** Qahramon mana regeneratsiyasi (har soniyada qancha tiklanadi) */
export function playerManaRegen(level, characterClass) {
  const classRate = characterClass?.id === 'mage' ? 22
                  : characterClass?.id === 'rogue' ? 18
                  : characterClass?.id === 'ranger' ? 16
                  : 14; // warrior
  return classRate + Math.max(0, (level || 1) - 1) * 1.5;
}

/** Har bir zarba uchun sarflanadigan mana */
export function attackManaCost(characterClass) {
  const id = characterClass?.id || 'warrior';
  switch (id) {
    case 'mage':    return 54; // Kuchli sehr
    case 'warrior': return 26; // Og'ir qilich zarbasi
    case 'ranger':  return 35; // Kamon o'qi
    case 'rogue':   return 42; // Tezkor combo
    default:        return 56;
  }
}
