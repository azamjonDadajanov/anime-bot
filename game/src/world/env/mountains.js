import * as THREE from 'three';
import { addBox } from './registry';

/**
 * TOG'LAR — xarita chetidagi ulkan tosh massivlari.
 * O'yin maydoni (r < 115) dan tashqarida, r ≈ 135-170 oralig'ida
 * joylashgani uchun o'rmon va ochiq maydonlar hech qachon to'silmaydi.
 */

const MOUNTAINS = [
  // Shimoliy silsilasi
  { x: -28, z: -147, h: 60, spread: 30, rocks: 12 },
  { x: 42, z: -157, h: 50, spread: 26, rocks: 10 },
  { x: -87, z: -137, h: 45, spread: 24, rocks: 9 },
  { x: 95, z: -140, h: 55, spread: 26, rocks: 11 },
  { x: 0, z: -168, h: 65, spread: 32, rocks: 13 },
  // G'arbiy
  { x: -140, z: -67, h: 46, spread: 26, rocks: 10 },
  { x: -157, z: 17, h: 38, spread: 22, rocks: 8 },
  { x: -134, z: 81, h: 42, spread: 24, rocks: 9 },
  // Sharqiy
  { x: 147, z: -90, h: 40, spread: 22, rocks: 8 },
  { x: 157, z: 34, h: 36, spread: 20, rocks: 7 },
  // Janubiy
  { x: -70, z: 150, h: 44, spread: 24, rocks: 9 },
  { x: 55, z: 155, h: 48, spread: 26, rocks: 10 },
];

export function buildMountains(group) {
  const rockMat1 = new THREE.MeshStandardMaterial({
    color: '#4a5568',
    flatShading: true,
    roughness: 0.95,
  });
  const rockMat2 = new THREE.MeshStandardMaterial({
    color: '#374151',
    flatShading: true,
    roughness: 0.98,
  });
  const snowMat = new THREE.MeshStandardMaterial({
    color: '#e8edf2',
    flatShading: true,
    roughness: 0.7,
  });

  MOUNTAINS.forEach((m) => {
    const mg = new THREE.Group();

    const peak = new THREE.Mesh(
      new THREE.ConeGeometry(m.h * 0.55, m.h, 7, 3),
      rockMat1
    );
    peak.position.set(0, m.h / 2, 0);
    peak.rotation.y = Math.random() * Math.PI;
    peak.castShadow = true;
    mg.add(peak);

    const snow = new THREE.Mesh(
      new THREE.ConeGeometry(m.h * 0.22, m.h * 0.38, 6, 2),
      snowMat
    );
    snow.position.set(0, m.h * 0.81, 0);
    mg.add(snow);

    for (let i = 0; i < m.rocks; i++) {
      const angle = (i / m.rocks) * Math.PI * 2 + Math.random() * 0.5;
      const r = m.spread * (0.3 + Math.random() * 0.65);
      const h = m.h * (0.3 + Math.random() * 0.55);
      const rock = new THREE.Mesh(
        new THREE.DodecahedronGeometry(h * 0.55, 1),
        i % 2 === 0 ? rockMat1 : rockMat2
      );
      rock.position.set(Math.cos(angle) * r, h * 0.42, Math.sin(angle) * r);
      rock.rotation.set(Math.random() * 0.5, Math.random(), Math.random() * 0.5);
      rock.castShadow = true;
      mg.add(rock);
    }

    mg.position.set(m.x, 0, m.z);
    group.add(mg);

    addBox(m.x, m.z, m.spread * 0.9, m.spread * 0.9);
  });

  // Xarita chegarasidagi boyqish toshlar (fon sifatida, o'yin maydonidan tashqarida)
  for (let i = 0; i < 16; i++) {
    const angle = Math.random() * Math.PI * 2;
    const r = 135 + Math.random() * 45;
    const rx = Math.cos(angle) * r;
    const rz = Math.sin(angle) * r;
    const s = 4 + Math.random() * 9;
    const rock = new THREE.Mesh(
      new THREE.DodecahedronGeometry(s, 1),
      Math.random() > 0.5 ? rockMat1 : rockMat2
    );
    rock.position.set(rx, s * 0.7, rz);
    rock.rotation.set(Math.random(), Math.random(), Math.random());
    rock.castShadow = true;
    rock.receiveShadow = true;
    group.add(rock);
  }
}
