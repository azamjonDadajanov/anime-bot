import * as THREE from 'three';
import { instantiate } from './modelCache';
import { addBox } from './registry';
import {
  CITY_RADIUS,
  GATE_ANGLES,
  HOUSE_RINGS,
  PLAZA_RADIUS,
  TOWN_FLOOR_RADIUS,
  WALL_HEIGHT,
  WALL_THICKNESS,
  angleSlots,
} from './constants';

/**
 * SHAHAR — devor, darvozalar, burjlar, ko'plab binolar va chiroqlar.
 *
 * Uylar ikki halqada joylashadi (qahramon balandligidan ancha katta bo'lishi
 * uchun masshtab ~2 barobar oshirildi), har bir bino markazga qarab turadi.
 */

const B = '/models/environment/buildings/blue';

// Har bir modelning o'lchami (metr, masshtab=1) va pastki nuqtasi (minY)
const BUILDING_DEFS = {
  home_A: { file: 'building_home_A_blue', size: [0.79, 0.93, 0.85], minY: 0.0, scale: 9.5 },
  home_B: { file: 'building_home_B_blue', size: [0.87, 1.28, 1.1], minY: 0.0, scale: 7.0 },
  tavern: { file: 'building_tavern_blue', size: [1.17, 1.4, 1.33], minY: 0.0, scale: 6.5 },
  blacksmith: { file: 'building_blacksmith_blue', size: [1.29, 0.99, 1.25], minY: 0.0, scale: 8.0 },
  market: { file: 'building_market_blue', size: [1.8, 0.98, 1.32], minY: 0.0, scale: 7.0 },
  church: { file: 'building_church_blue', size: [1.03, 1.65, 1.16], minY: 0.0, scale: 6.5 },
  castle: { file: 'building_castle_blue', size: [1.98, 3.98, 2.26], minY: 0.0, scale: 4.0 },
  barracks: { file: 'building_barracks_blue', size: [1.44, 1.64, 1.57], minY: 0.0, scale: 5.5 },
  archery: { file: 'building_archeryrange_blue', size: [1.67, 1.79, 1.55], minY: 0.0, scale: 5.0 },
  windmill: { file: 'building_windmill_blue', size: [1.13, 1.46, 0.79], minY: 0.0, scale: 7.0 },
  lumbermill: { file: 'building_lumbermill_blue', size: [1.37, 1.3, 1.33], minY: 0.0, scale: 6.5 },
  well: { file: 'building_well_blue', size: [0.65, 0.83, 0.75], minY: 0.0, scale: 3.6 },
  tower: { file: 'building_tower_B_blue', size: [1.2, 2.49, 1.38], minY: 0.0, scale: 4.5 },
};

// Ikkala halqadagi binolar tartibi (15° + k*30°)
const INNER_RING = [
  'home_A', 'home_B', 'tavern', 'home_A',
  'home_B', 'blacksmith', 'home_A', 'home_B',
  'market', 'home_A', 'home_B', 'home_A',
];

const OUTER_RING = [
  'church', 'home_A', 'barracks', 'home_B',
  'windmill', 'home_A', 'archery', 'castle',
  'home_B', 'lumbermill', 'home_A', 'home_B',
];

export function buildCity(group) {
  buildWalls(group);
  buildHouses(group);
  buildLamps(group);
  buildPlazaWell(group);
}

// ─── SHAHAR DEVORI + DARVOZALAR ────────────────────────
function buildWalls(group) {
  const wallRadius = CITY_RADIUS;
  const segLen = 6.0;
  const gateGap = 11; // darvoza oralig'i (metr)
  const gateHalf = gateGap / 2 / wallRadius;

  const wallMat = new THREE.MeshStandardMaterial({
    color: '#8d9db0',
    roughness: 0.85,
    flatShading: true,
  });
  const merlonMat = new THREE.MeshStandardMaterial({
    color: '#b0c0d0',
    roughness: 0.8,
    flatShading: true,
  });
  const towerMat = new THREE.MeshStandardMaterial({
    color: '#6b7a8d',
    roughness: 0.9,
    flatShading: true,
  });

  const totalCirc = Math.PI * 2 * wallRadius;
  const segCount = Math.ceil(totalCirc / segLen);
  const aStep = (Math.PI * 2) / segCount;

  for (let i = 0; i < segCount; i++) {
    const a = i * aStep;

    // Har qanday darvozaga juda yaqin bo'lsa - segment qo'ymaymiz
    const nearGate = GATE_ANGLES.some((gate) => {
      const diff = Math.abs(((a - gate + Math.PI * 3) % (Math.PI * 2)) - Math.PI);
      return diff < gateHalf;
    });
    if (nearGate) continue;

    const wx = Math.cos(a) * wallRadius;
    const wz = Math.sin(a) * wallRadius;

    const seg = new THREE.Mesh(
      new THREE.BoxGeometry(segLen + 0.2, WALL_HEIGHT, WALL_THICKNESS),
      wallMat
    );
    seg.position.set(wx, WALL_HEIGHT / 2, wz);
    seg.rotation.y = -a + Math.PI / 2;
    seg.castShadow = true;
    seg.receiveShadow = true;
    group.add(seg);

    // Devor tishi (merlon)
    for (let m = -1; m <= 1; m++) {
      const off = m * segLen * 0.3;
      const mx = wx + Math.cos(-a + Math.PI / 2) * off;
      const mz = wz + Math.sin(-a + Math.PI / 2) * off;
      const mer = new THREE.Mesh(
        new THREE.BoxGeometry(1.4, 2.0, WALL_THICKNESS + 0.3),
        merlonMat
      );
      mer.position.set(mx, WALL_HEIGHT + 1.0, mz);
      mer.rotation.y = -a + Math.PI / 2;
      group.add(mer);
    }

    addRotatedBox(wx, wz, segLen + 0.4, WALL_THICKNESS + 1.0, -a + Math.PI / 2);
  }

  // Darvoza burjlari (har bir darvoza ikki tomonida)
  GATE_ANGLES.forEach((gate) => {
    [gate - gateHalf - 0.04, gate + gateHalf + 0.04].forEach((ta) => {
      const tx = Math.cos(ta) * wallRadius;
      const tz = Math.sin(ta) * wallRadius;

      const tw = new THREE.Mesh(new THREE.BoxGeometry(5, WALL_HEIGHT + 6, 5), towerMat);
      tw.position.set(tx, (WALL_HEIGHT + 6) / 2, tz);
      tw.castShadow = true;
      tw.receiveShadow = true;
      group.add(tw);

      const cap = new THREE.Mesh(
        new THREE.ConeGeometry(4.0, 6, 4),
        new THREE.MeshStandardMaterial({ color: '#4a5568', flatShading: true })
      );
      cap.position.set(tx, WALL_HEIGHT + 6 + 3, tz);
      cap.rotation.y = Math.PI / 4;
      cap.castShadow = true;
      group.add(cap);

      addBox(tx, tz, 3.0, 3.0);
    });
  });
}

// ─── BINOLAR (ikki halqa, ko'p uy) ────────────────────
function buildHouses(group) {
  HOUSE_RINGS.forEach((ring, ringIndex) => {
    const layout = ringIndex === 0 ? INNER_RING : OUTER_RING;
    const angles = angleSlots(ring.count, ring.offsetDeg);

    angles.forEach((angle, i) => {
      const type = layout[i % layout.length];
      const def = BUILDING_DEFS[type];
      if (!def) return;

      // Har bir uy qozonchasiga ozgina tasodifiy siljish (tabiiy ko'rinish)
      const jitter = (i % 3) * 0.6 - 0.6;
      const radius = ring.radius + jitter;
      const x = Math.cos(angle) * radius;
      const z = Math.sin(angle) * radius;
      // Bino markazga qarab tursin
      const ry = -angle - Math.PI / 2 + (i % 2 ? 0.12 : -0.12);

      placeBuilding(group, { type, x, z, ry });
    });
  });
}

function placeBuilding(group, { type, x, z, ry }) {
  const def = BUILDING_DEFS[type];
  const [w, , d] = def.size;
  const scaledW = w * def.scale;
  const scaledD = d * def.scale;

  // Aylantirilgan qutining AABB yarim o'lchamlari
  const cos = Math.abs(Math.cos(ry));
  const sin = Math.abs(Math.sin(ry));
  addBox(x, z, cos * (scaledW / 2) + sin * (scaledD / 2) + 0.4,
         sin * (scaledW / 2) + cos * (scaledD / 2) + 0.4);

  const path = `${B}/${def.file}.gltf`;
  instantiate(path).then((model) => {
    if (model) {
      model.position.set(x, -def.minY * def.scale, z);
      model.rotation.y = ry;
      model.scale.setScalar(def.scale);
      group.add(model);
      return;
    }
    fallbackBuilding(group, def, x, z, ry);
  });
}

function fallbackBuilding(group, def, x, z, ry) {
  const [w, h, d] = def.size;
  const sw = w * def.scale;
  const sh = h * def.scale;
  const sd = d * def.scale;

  const body = new THREE.Mesh(
    new THREE.BoxGeometry(sw, sh, sd),
    new THREE.MeshStandardMaterial({ color: '#5a7a9a', flatShading: true })
  );
  body.position.set(x, sh / 2, z);
  body.rotation.y = ry;
  body.castShadow = true;
  body.receiveShadow = true;
  group.add(body);

  const roof = new THREE.Mesh(
    new THREE.ConeGeometry(Math.max(sw, sd) * 0.75, sh * 0.5, 4),
    new THREE.MeshStandardMaterial({ color: '#8b3a3a', flatShading: true })
  );
  roof.position.set(x, sh + sh * 0.25, z);
  roof.rotation.y = ry + Math.PI / 4;
  roof.castShadow = true;
  group.add(roof);
}

// ─── KO'CHA CHIROQLARI ────────────────────────────────
function buildLamps(group) {
  const poleMat = new THREE.MeshStandardMaterial({ color: '#2d3748' });
  const lampMat = new THREE.MeshStandardMaterial({
    color: '#fbbf24',
    emissive: '#fbbf24',
    emissiveIntensity: 0.9,
  });

  const spots = [];
  // Ichki halqa (markaz atrofi) — chiroqlar yoritadi
  angleSlots(8, 22.5).forEach((a) => spots.push({ r: 21, a, light: a === Math.PI / 4 || a === (5 * Math.PI) / 4 }));
  // Tashqi halqa — faqat ko'rinish
  angleSlots(8, 22.5).forEach((a) => spots.push({ r: 43, a, light: false }));

  spots.forEach(({ r, a, light }) => {
    const x = Math.cos(a) * r;
    const z = Math.sin(a) * r;

    const pole = new THREE.Mesh(new THREE.CylinderGeometry(0.2, 0.26, 8, 6), poleMat);
    pole.position.set(x, 4, z);
    pole.castShadow = true;
    group.add(pole);

    const ball = new THREE.Mesh(new THREE.SphereGeometry(0.6, 8, 8), lampMat);
    ball.position.set(x, 8.4, z);
    group.add(ball);

    if (light) {
      const pl = new THREE.PointLight('#ffe8a0', 5, 22);
      pl.position.set(x, 8.2, z);
      group.add(pl);
    }

    addBox(x, z, 0.5, 0.5);
  });
}

// ─── MARKAZIY MAYDON — quduq ──────────────────────────
function buildPlazaWell(group) {
  const x = PLAZA_RADIUS * 0.6;
  const z = PLAZA_RADIUS * 0.45;

  placeBuilding(group, { type: 'well', x, z, ry: -Math.atan2(z, x) - Math.PI / 2 });
}

// ─── Yordamchi: aylantirilgan qutini to'siqga qo'shish ─
function addRotatedBox(x, z, w, d, ry) {
  const cos = Math.abs(Math.cos(ry));
  const sin = Math.abs(Math.sin(ry));
  addBox(x, z, cos * (w / 2) + sin * (d / 2), sin * (w / 2) + cos * (d / 2));
}

/**
 * Shahar poli diski — endi CHIM (yashil), tosh faqat yo'llarda,
 * maydonda va devor ostida qoladi. Shahar ko'proq ochiq, yashil
 * va keng ko'rinadi.
 */
export function buildTownFloor(group) {
  const floor = new THREE.Mesh(
    new THREE.CylinderGeometry(TOWN_FLOOR_RADIUS, TOWN_FLOOR_RADIUS, 0.5, 64),
    new THREE.MeshStandardMaterial({
      color: '#4f9448',
      roughness: 0.95,
      flatShading: true,
    })
  );
  floor.position.y = -0.21; // yuza taxminan y = 0.04 da turadi
  floor.receiveShadow = true;
  group.add(floor);
}
