import { getLoadout, resolveBone } from '../../config/weapons';
import { instantiate } from '../env/modelCache';

/**
 * Qahramonga o'z qurollar to'plamini biriktiradi.
 *
 * Har bir qurol config/weapons.js da ko'rsatilgan suyakka
 * (handslot.r / hand.r / chest / hips) position + rotation bilan ulanadi.
 * Suyak topilmasa, yaqin alternativ suyak (hand -> wrist -> lowerarm) ishlatiladi.
 */
export async function equipWeapons(character, characterClassId) {
  const loadout = getLoadout(characterClassId);
  const equipped = [];

  for (const cfg of loadout) {
    const bone = resolveBone(character, cfg.bone);
    if (!bone) {
      console.warn(`[WEAPON] Suyak topilmadi: ${cfg.bone} (${cfg.id})`);
      continue;
    }

    const model = await instantiate(cfg.model);
    if (!model) {
      console.warn(`[WEAPON] Model yuklanmadi: ${cfg.model}`);
      continue;
    }

    model.scale.setScalar(cfg.scale);
    model.position.set(cfg.position[0], cfg.position[1], cfg.position[2]);
    model.rotation.set(cfg.rotation[0], cfg.rotation[1], cfg.rotation[2]);
    model.name = `weapon_${cfg.id}`;

    model.traverse((node) => {
      if (node.isMesh || node.isSkinnedMesh) {
        node.castShadow = true;
        node.receiveShadow = true;
        node.frustumCulled = false;
      }
    });

    bone.add(model);
    equipped.push({ id: cfg.id, name: cfg.name, object: model, bone });
  }

  return equipped;
}
