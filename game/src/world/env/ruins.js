import * as THREE from 'three';
import { addBox } from './registry';
import { RUIN_SPOTS } from './constants';

/**
 * QADIMIY HAROBALAR — o'rmon ichidagi vayron devor va singan ustunlar.
 * (Portal maydonchalari bu oraliqdan tashqarida joylashgan)
 */
export function buildRuins(group) {
  const ruinMat = new THREE.MeshStandardMaterial({
    color: '#6b7280',
    flatShading: true,
    roughness: 0.9,
  });
  const ruinDark = new THREE.MeshStandardMaterial({
    color: '#4b5563',
    flatShading: true,
    roughness: 0.95,
  });

  RUIN_SPOTS.forEach((spot, index) => {
    const wallH = 5 + Math.random() * 7;
    const wallW = 6 + Math.random() * 8;
    const ry = (index / RUIN_SPOTS.length) * Math.PI + Math.random() * 0.6;

    const wall = new THREE.Mesh(new THREE.BoxGeometry(wallW, wallH, 1.6), ruinMat);
    wall.position.set(spot.x, wallH / 2, spot.z);
    wall.rotation.y = ry;
    wall.castShadow = true;
    wall.receiveShadow = true;
    group.add(wall);

    // Singan ustun
    const colH = 4 + Math.random() * 5;
    const cx = spot.x + (Math.random() - 0.5) * 7;
    const cz = spot.z + (Math.random() - 0.5) * 6;
    const col = new THREE.Mesh(
      new THREE.CylinderGeometry(0.6, 0.8, colH, 6),
      ruinDark
    );
    col.position.set(cx, colH / 2, cz);
    col.rotation.z = (Math.random() - 0.5) * 0.35;
    col.castShadow = true;
    group.add(col);

    // Devorning aylantirilgan AABB yarim o'lchamlari
    const cos = Math.abs(Math.cos(ry));
    const sin = Math.abs(Math.sin(ry));
    addBox(
      spot.x,
      spot.z,
      cos * (wallW / 2) + sin * 1.0 + 0.4,
      sin * (wallW / 2) + cos * 1.0 + 0.4
    );
    addBox(cx, cz, 1.1, 1.1);
  });
}
