import * as THREE from 'three';
import { resetRegistry, CLOUD_MESHES, COLLISION_BOXES } from './registry';
import { buildSky } from './sky';
import { buildRoads } from './roads';
import { buildCity, buildTownFloor } from './city';
import { buildForest } from './forest';
import { buildMountains } from './mountains';
import { buildRuins } from './ruins';
import { buildSigns } from './signs';

export { COLLISION_BOXES, CLOUD_MESHES };

/**
 * BUTUN DUNYO — barcha modullarni bitta joyga yig'adi.
 *
 *   osmon  → env/sky.js
 *   yer     → shahar poli + yo'llar (env/roads.js)
 *   shahar  → env/city.js      (devor, 24+ bino, chiroqlar)
 *   o'rmon  → env/forest.js    (daraxt guruhlari, portallar maydonchalari bo'sh)
 *   tog'lar → env/mountains.js
 *   harobalar → env/ruins.js
 *   belgilar → env/signs.js
 */
export function buildOpenWorld(scene) {
  resetRegistry();

  const world = new THREE.Group();
  scene.add(world);

  buildSky(scene);
  buildGround(world);
  buildTownFloor(world);
  buildRoads(world);
  buildCity(world);
  buildForest(world);
  buildMountains(world);
  buildRuins(world);
  buildSigns(world);

  return world;
}

/** Asosiy yer diski */
function buildGround(group) {
  const ground = new THREE.Mesh(
    new THREE.CylinderGeometry(195, 205, 6, 64),
    new THREE.MeshStandardMaterial({
      color: '#3a7d44',
      roughness: 0.95,
      flatShading: true,
    })
  );
  ground.position.y = -3;
  ground.receiveShadow = true;
  group.add(ground);
}
