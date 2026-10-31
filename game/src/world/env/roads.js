import * as THREE from 'three';
import {
  AVENUE_WIDTH,
  CITY_RADIUS,
  FOREST_PATH_END,
  FOREST_PATH_START,
  FOREST_PATH_WIDTH,
  FOREST_RING,
  GATE_ANGLES,
  PLAZA_RADIUS,
  RING_ROADS,
} from './constants';

/**
 * YO'LLAR — shahar tor manageri, halqa yo'llar, darvozalar va o'rmon yo'llari
 */
export function buildRoads(group) {
  const stoneMat = new THREE.MeshStandardMaterial({
    color: '#93a0af',
    roughness: 0.95,
    flatShading: true,
    polygonOffset: true,
    polygonOffsetFactor: -2,
  });

  const dirtMat = new THREE.MeshStandardMaterial({
    color: '#8b7350',
    roughness: 1,
    flatShading: true,
    polygonOffset: true,
    polygonOffsetFactor: -2,
  });

  // Markaziy maydon (plaza)
  const plaza = new THREE.Mesh(
    new THREE.CircleGeometry(PLAZA_RADIUS, 48),
    stoneMat
  );
  plaza.rotation.x = -Math.PI / 2;
  plaza.position.y = 0.07;
  plaza.receiveShadow = true;
  group.add(plaza);

  // Halqa yo'llar (shahar ichida)
  RING_ROADS.forEach((ring) => {
    const road = new THREE.Mesh(
      new THREE.RingGeometry(ring.inner, ring.outer, 96),
      stoneMat
    );
    road.rotation.x = -Math.PI / 2;
    road.position.y = 0.07;
    road.receiveShadow = true;
    group.add(road);
  });

  // Radius yo'llar: har bir darvodan markazga (avenue)
  GATE_ANGLES.forEach((angle) => {
    group.add(makeSegment({
      from: 0,
      to: CITY_RADIUS,
      angle,
      width: AVENUE_WIDTH,
      y: 0.075,
      material: stoneMat,
    }));
  });

  // ── O'RMON YO'LLARI ─────────────────────────────────
  // Har bir darvodan tashqariga, o'rmon halqasiga va xarita chegarasiga
  GATE_ANGLES.forEach((angle) => {
    group.add(makeSegment({
      from: FOREST_PATH_START - 1,
      to: FOREST_PATH_END,
      angle,
      width: FOREST_PATH_WIDTH,
      y: 0.055,
      material: dirtMat,
    }));
  });

  // O'rmon halqa yo'li (portallar shu yo'l bo'ylab topiladi)
  const forestRing = new THREE.Mesh(
    new THREE.RingGeometry(FOREST_RING.inner, FOREST_RING.outer, 128),
    dirtMat
  );
  forestRing.rotation.x = -Math.PI / 2;
  forestRing.position.y = 0.055;
  forestRing.receiveShadow = true;
  group.add(forestRing);
}

/**
 * `from` → `to` radiusi orasida burchak bo'yicha tekis yo'l paneli
 */
function makeSegment({ from, to, angle, width, y, material }) {
  const length = to - from;
  const middle = (from + to) / 2;

  const holder = new THREE.Group();
  holder.rotation.y = -angle;
  holder.position.set(Math.cos(angle) * middle, y, Math.sin(angle) * middle);

  const mesh = new THREE.Mesh(new THREE.PlaneGeometry(length, width), material);
  mesh.rotation.x = -Math.PI / 2;
  mesh.receiveShadow = true;
  holder.add(mesh);

  return holder;
}
