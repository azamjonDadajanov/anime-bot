import * as THREE from 'three';
import { instantiate } from './modelCache';
import { addBox } from './registry';
import {
  FOREST_MAX_R,
  FOREST_MIN_R,
  GATE_ANGLES,
  MEADOWS,
  RUIN_SPOTS,
  TREE_MAX_R,
  TREE_MIN_R,
  angleDiff,
} from './constants';
import { CLEARING_RADIUS, PORTAL_CLEARINGS } from '../portals/spawnPoints';

/**
 * O'RMON — shahar devoridan tashqarida, yo'llar va portal
 * maydonchalari atrofida tartibli o'stirilgan daraxt guruhlari (claster).
 *
 * Qoidalar:
 *  - daraxtlar faqat TREE_MIN_R..TREE_MAX_R oraliqida
 *  - o'rmon halqa yo'li va darvoza yo'llari ustiga chiqmaydi
 *  - portal maydonchalari (clearing) har doim bo'sh qolinadi
 *  - harobalar atrofida ham joy qolinadi
 */

const DECOR = '/models/environment/decorations';

const TREE_MODELS = [
  { path: `${DECOR}/tree_single_A.gltf`, scale: [5.5, 7.5], half: 1.2 },
  { path: `${DECOR}/tree_single_B.gltf`, scale: [5.5, 7.5], half: 1.2 },
  { path: `${DECOR}/trees_A_medium.gltf`, scale: [4.0, 5.2], half: 2.4 },
  { path: `${DECOR}/trees_B_medium.gltf`, scale: [4.0, 5.2], half: 2.4 },
];

const CLUSTER_COUNT = 30;
const TREES_PER_CLUSTER = [4, 7];

export function buildForest(group) {
  const spots = [];
  const rng = mulberry32(20261031);

  // KATTA OCHIQ MAYDONLAR (keng, daraxtsiz hududlar)
  addMeadows(group);

  for (let c = 0; c < CLUSTER_COUNT; c++) {
    // Guruhlar xaritada teng taqsimlanadi (bir oz tasodifiy siljish bilan)
    const angle = (c / CLUSTER_COUNT) * Math.PI * 2 + (rng() - 0.5) * 0.22;
    const radius = TREE_MIN_R + 3 + rng() * (TREE_MAX_R - TREE_MIN_R - 6);

    const cx = Math.cos(angle) * radius;
    const cz = Math.sin(angle) * radius;

    const count =
      TREES_PER_CLUSTER[0] +
      Math.floor(rng() * (TREES_PER_CLUSTER[1] - TREES_PER_CLUSTER[0] + 1));

    for (let t = 0; t < count; t++) {
      const spread = 2.5 + rng() * 4.5;
      const a = rng() * Math.PI * 2;
      const x = cx + Math.cos(a) * spread;
      const z = cz + Math.sin(a) * spread;

      if (!isFreeSpot(x, z)) continue;

      const model = TREE_MODELS[Math.floor(rng() * TREE_MODELS.length)];
      const scale = model.scale[0] + rng() * (model.scale[1] - model.scale[0]);

      spots.push({ x, z, model, scale, rotation: rng() * Math.PI * 2 });
      addBox(x, z, model.half, model.half);
    }
  }

  // daraxtlarni model bo'yicha yig'ib, bitta yuklashda joylashtiramiz
  spots.forEach((spot) => {
    instantiate(spot.model.path).then((model) => {
      if (model) {
        model.position.set(spot.x, 0, spot.z);
        model.rotation.y = spot.rotation;
        model.scale.setScalar(spot.scale);
        group.add(model);
        return;
      }
      proceduralTree(group, spot.x, spot.z, spot.scale / 6);
    });
  });

  // Yo'l bo'ylab mayda butalar (yo'lni yaqqol ko'rsatadi)
  addShrubs(group, rng);
}

/** Nuqta daraxt uchun mos joymi? (yo'llar, maydonchalar va harobalar band emas) */
function isFreeSpot(x, z) {
  const r = Math.sqrt(x * x + z * z);
  if (r < TREE_MIN_R || r > TREE_MAX_R) return false;

  const a = Math.atan2(z, x);

  // Darvozadan chiqadigan o'rmon yo'llari
  for (const gate of GATE_ANGLES) {
    const arc = Math.abs(angleDiff(a, gate)) * r;
    if (arc < 4.5) return false;
  }

  // Portal maydonchalari
  for (const c of PORTAL_CLEARINGS) {
    const dx = c.x - x;
    const dz = c.z - z;
    if (Math.sqrt(dx * dx + dz * dz) < CLEARING_RADIUS + 1.5) return false;
  }

  // Harobalar atrofi
  for (const s of RUIN_SPOTS) {
    const dx = s.x - x;
    const dz = s.z - z;
    if (Math.sqrt(dx * dx + dz * dz) < 8) return false;
  }

  // Katta ochiq maydonlar (meadows) — ularda daraxt o'smaydi
  for (const m of MEADOWS) {
    const dx = m.x - x;
    const dz = m.z - z;
    if (Math.sqrt(dx * dx + dz * dz) < m.r + 1.5) return false;
  }

  // O'rmon halqa yo'li (64-69)
  if (r > FOREST_MIN_R && r < 70.5) return false;

  return true;
}

/** Katta ochiq maydonlarning ko'rinishi (yorqinroq chang log'i diski) */
function addMeadows(group) {
  const mat = new THREE.MeshStandardMaterial({
    color: '#5aa34c',
    roughness: 0.95,
    flatShading: true,
    polygonOffset: true,
    polygonOffsetFactor: -1,
  });

  MEADOWS.forEach((m) => {
    const disc = new THREE.Mesh(new THREE.CircleGeometry(m.r, 40), mat);
    disc.rotation.x = -Math.PI / 2;
    disc.position.set(m.x, 0.03, m.z);
    disc.receiveShadow = true;
    group.add(disc);

    // Chet bo'ylab qirrali tashlar (maydon chegarasini ko'rsatadi)
    const rimMat = new THREE.MeshStandardMaterial({
      color: '#4b8f41',
      flatShading: true,
      roughness: 0.95,
    });
    for (let i = 0; i < 10; i++) {
      const a = (i / 10) * Math.PI * 2;
      const s = 0.7 + ((i * 37) % 10) / 10;
      const tuft = new THREE.Mesh(new THREE.DodecahedronGeometry(s, 0), rimMat);
      tuft.position.set(m.x + Math.cos(a) * (m.r - 1), s * 0.5, m.z + Math.sin(a) * (m.r - 1));
      tuft.rotation.set(i * 0.7, i * 1.3, i * 0.4);
      tuft.scale.y = 0.6;
      tuft.castShadow = true;
      group.add(tuft);
    }
  });
}

/** Yo'l chetidagi mayda butalar */
function addShrubs(group, rng) {
  const shrubMat = new THREE.MeshStandardMaterial({
    color: '#2f7a3f',
    flatShading: true,
    roughness: 0.9,
  });

  for (let i = 0; i < 60; i++) {
    const gate = GATE_ANGLES[i % GATE_ANGLES.length];
    const side = i % 2 === 0 ? 1 : -1;
    const along = 62 + rng() * 45;
    const offset = (3.6 + rng() * 2.5) * side;

    const x = Math.cos(gate) * along - Math.sin(gate) * offset;
    const z = Math.sin(gate) * along + Math.cos(gate) * offset;
    if (!isFreeSpot(x, z)) continue;

    const s = 0.6 + rng() * 0.8;
    const shrub = new THREE.Mesh(new THREE.DodecahedronGeometry(s, 0), shrubMat);
    shrub.position.set(x, s * 0.7, z);
    shrub.rotation.set(rng(), rng() * 3, rng());
    shrub.castShadow = true;
    shrub.scale.y = 0.75;
    group.add(shrub);
  }
}

/** Model yuklanmasa — protsedural daraxt */
function proceduralTree(group, x, z, scale = 1) {
  const trunkM = new THREE.MeshStandardMaterial({ color: '#5c3d1e', roughness: 0.9 });
  const leaf1M = new THREE.MeshStandardMaterial({ color: '#1a6b2e', flatShading: true, roughness: 0.8 });
  const leaf2M = new THREE.MeshStandardMaterial({ color: '#2d8a45', flatShading: true, roughness: 0.8 });

  const trH = 8 * scale;
  const trR = 0.6 * scale;
  const trunk = new THREE.Mesh(new THREE.CylinderGeometry(trR * 0.7, trR, trH, 7), trunkM);
  trunk.position.set(x, trH / 2, z);
  trunk.castShadow = true;
  group.add(trunk);

  const leafCount = 2 + Math.floor(Math.random() * 2);
  for (let l = 0; l < leafCount; l++) {
    const lr = (3.5 + Math.random() * 2.5) * scale;
    const leaf = new THREE.Mesh(
      new THREE.DodecahedronGeometry(lr, 1),
      l % 2 === 0 ? leaf1M : leaf2M
    );
    leaf.position.set(
      x + (Math.random() - 0.5) * 2 * scale,
      trH + lr * 0.5 + l * lr * 0.4 - lr * 0.3,
      z + (Math.random() - 0.5) * 2 * scale
    );
    leaf.rotation.set(Math.random(), Math.random(), Math.random());
    leaf.castShadow = true;
    group.add(leaf);
  }
}

/** Barqaror tasodifiy sonlar generatori (har doim bir xil natija) */
function mulberry32(seed) {
  let a = seed >>> 0;
  return function () {
    a |= 0;
    a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}
