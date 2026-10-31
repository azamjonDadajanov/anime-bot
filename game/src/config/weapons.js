/**
 * Har bir qahramon uchun qurollar to'plami (Weapon loadouts).
 *
 * `charactrer_items/gltf` ichidagi modellar to'g'ridan-to'g'ri
 * skelet suyaklariga (handslot.r / hand.r / chest / hips) ulanadi.
 *
 * Xususiyatlar:
 *   bone      - qaysi suyakka ulanadi (topilmasa fallback suyaklar ishlatiladi)
 *   scale     - model masshtabi (qahramon 2.5 birlik bo'yligi barobarida)
 *   position  - suyak lokal koordinatasidagi siljish
 *   rotation  - suyak lokal o'qlari bo'yicha burilish (radians)
 *
 * Suyak lokal o'qlari (dam olish holati, qahramon +Z ga qaragan):
 *   handslot.r: X = o'ng/tomonga (qo'l uzilishi), Y = oldinga, Z = yuqoriga (ichkariga)
 *   handslot.l: X = ichkariga/tomonga,          Y = oldinga, Z = yuqoriga (tashqariga)
 *   chest/hips: dunyo o'qlari bilan mos
 */

const ITEM = (file) => `/models/charactrer_items/gltf/${file}.gltf`;

export const WEAPON_LOADOUTS = {
  // ⚔️ Jangchi: qilich (o'ng qo'l) + barbar qalqoni (chap qo'l)
  warrior: [
    {
      id: 'sword',
      name: 'Qilich',
      model: ITEM('sword_1handed'),
      bone: 'handslotr',
      scale: 0.6,
      position: [0, 0, 0],
      rotation: [0, 0, -Math.PI / 2],
    },
    {
      id: 'shield',
      name: 'Qalqon',
      model: ITEM('shield_round_barbarian'),
      bone: 'handslotl',
      scale: 0.78,
      position: [0, 0.05, 0],
      rotation: [-Math.PI / 2, 0, 0],
    },
  ],

  // 🔮 Sehrgar: aso (o'ng qo'l) + ochiq sehrci kitobi (chap qo'l)
  mage: [
    {
      id: 'staff',
      name: 'Sehrli aso',
      model: ITEM('staff'),
      bone: 'handslotr',
      scale: 0.95,
      position: [0, 0, 0.06],
      rotation: [Math.PI / 2, 0, 0],
    },
    {
      id: 'spellbook',
      name: 'Sehrli kitob',
      model: ITEM('spellbook_open'),
      bone: 'handslotl',
      scale: 0.85,
      position: [0, 0.04, 0.14],
      rotation: [-Math.PI / 2, 0, 0],
    },
  ],

  // 🏹 Mergan: kamon (o'ng qo'l) + tuya tupa orqada (chest)
  ranger: [
    {
      id: 'bow',
      name: 'Kamon',
      model: ITEM('bow_withString'),
      bone: 'handslotr',
      scale: 0.8,
      position: [0, 0, 0],
      rotation: [0, 0, Math.PI / 2],
    },
    {
      id: 'quiver',
      name: 'Tuya tupa',
      model: ITEM('quiver'),
      bone: 'chest',
      scale: 0.9,
      position: [-0.2, -0.04, -0.26],
      rotation: [-0.45, 0, 0.35],
    },
  ],

  // 🗡️ Qaroqchi: ikki pichoq (ikki qo'l) + tutun bombasi (kamar)
  rogue: [
    {
      id: 'dagger_r',
      name: 'Pichoq',
      model: ITEM('dagger'),
      bone: 'handslotr',
      scale: 0.62,
      position: [0, 0, 0],
      rotation: [0, 0, -Math.PI / 2],
    },
    {
      id: 'dagger_l',
      name: 'Pichoq',
      model: ITEM('dagger'),
      bone: 'handslotl',
      scale: 0.62,
      position: [0, 0, 0],
      rotation: [0, 0, Math.PI / 2],
    },
    {
      id: 'smokebomb',
      name: 'Tutun bombasi',
      model: ITEM('smokebomb'),
      bone: 'hips',
      scale: 1,
      position: [0.3, 0.03, -0.16],
      rotation: [0, 0.4, 0],
    },
  ],
};

/** Qahramon to'plamini qaytaradi (topilmaga bo'sh massiv). */
export function getLoadout(characterId) {
  return WEAPON_LOADOUTS[characterId] || [];
}

/**
 * Yedak suyaklar: ba'zi modellarda handslot bo'lmasa
 * hand -> lowerarm ketma-ketligi bilan qidiriladi.
 */
export function resolveBone(model, boneName) {
  if (!boneName) return null;
  const byKey = new Map();
  model.traverse((child) => {
    if (child.isBone) byKey.set(child.name.toLowerCase().replace(/[\s.:/[\]]/g, ''), child);
  });

  const side = boneName.slice(-1); // 'l' yoki 'r'
  const candidates = [
    boneName,
    `handslot${side}`,
    `hand${side}`,
    `wrist${side}`,
    `lowerarm${side}`,
    boneName.replace('handslot', 'hand'),
  ];

  for (const name of candidates) {
    const bone = byKey.get(name.toLowerCase().replace(/[\s.:/[\]]/g, ''));
    if (bone) return bone;
  }
  return null;
}
