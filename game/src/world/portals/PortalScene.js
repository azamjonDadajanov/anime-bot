import * as THREE from 'three';

/**
 * 3D PORTAL SAHNASI — halqa, vorteks va ochilish animatsiyasi.
 *
 * PortalScene.update(portals) chaqirilganda faqat ro'yxat o'zgarganda
 * modellar qayta quriladi: yengilgan portal yo'qoladi, yangisi ochiladi.
 */

const TIER_COLORS = {
  D: '#22c55e',
  C: '#3b82f6',
  B: '#a855f7',
  A: '#f59e0b',
  S: '#ef4444',
};

const SPAWN_TIME = 0.7;

export class PortalScene {
  constructor(scene) {
    this.group = new THREE.Group();
    scene.add(this.group);
    this.items = new Map();
    this.signature = null;
  }

  /** Portallar ro'yxati o'zgargagina modellarni sinxronlaydi */
  update(portals) {
    const list = Array.isArray(portals) ? portals : [];
    const signature = list.map((p) => `${p.portal_id}@${p.spawnSlot ?? 0}`).join('|');
    if (signature === this.signature) return;
    this.signature = signature;

    const wanted = new Map(
      list.map((p) => [`${p.portal_id}@${p.spawnSlot ?? 0}`, p])
    );

    // Artib qolgan portallarni o'chirish (yengilgan portal shu yerda yo'qoladi)
    for (const [key, item] of Array.from(this.items.entries())) {
      if (!wanted.has(key)) {
        this.group.remove(item.container);
        disposeTree(item.container);
        this.items.delete(key);
      }
    }

    // Yangi portallarni ochish
    for (const [key, portal] of wanted.entries()) {
      if (!this.items.has(key)) {
        this.items.set(key, this.#createPortal(portal));
      }
    }
  }

  #createPortal(portal) {
    const color = TIER_COLORS[portal.tier] || '#6366f1';
    const container = new THREE.Group();
    container.position.set(portal.position.x, 0, portal.position.z);
    container.scale.setScalar(0.01);

    // Asosiy halqa
    const ring = new THREE.Mesh(
      new THREE.TorusGeometry(2.0, 0.24, 16, 40),
      new THREE.MeshStandardMaterial({
        color,
        emissive: color,
        emissiveIntensity: 1.0,
        roughness: 0.2,
      })
    );
    ring.position.y = 2.4;
    container.add(ring);

    // Ichki vorteks
    const vortex = new THREE.Mesh(
      new THREE.CircleGeometry(1.8, 40),
      new THREE.MeshBasicMaterial({
        color,
        transparent: true,
        opacity: 0.65,
        side: THREE.DoubleSide,
      })
    );
    vortex.position.y = 2.4;
    container.add(vortex);

    // Pastki muhr (yerdagi yorug'lik doirasi)
    const base = new THREE.Mesh(
      new THREE.CircleGeometry(2.6, 32),
      new THREE.MeshBasicMaterial({
        color,
        transparent: true,
        opacity: 0.28,
        side: THREE.DoubleSide,
      })
    );
    base.rotation.x = -Math.PI / 2;
    base.position.y = 0.06;
    container.add(base);

    // Maydon chetidagi tashlar (markaz har doim ochiq qolinadi)
    const stoneMat = new THREE.MeshStandardMaterial({
      color: '#6b7480',
      flatShading: true,
      roughness: 0.95,
    });
    for (let i = 0; i < 5; i++) {
      const a = (i / 5) * Math.PI * 2 + 0.3;
      const r = 5.6 + Math.random() * 1.6;
      const stone = new THREE.Mesh(
        new THREE.DodecahedronGeometry(0.4 + Math.random() * 0.35, 0),
        stoneMat
      );
      stone.position.set(Math.cos(a) * r, 0.2, Math.sin(a) * r);
      stone.rotation.set(Math.random(), Math.random(), Math.random());
      stone.castShadow = true;
      container.add(stone);
    }

    const light = new THREE.PointLight(color, 6, 18);
    light.position.set(0, 2.4, 0);
    container.add(light);

    this.group.add(container);

    return { container, ring, vortex, base, light, age: 0 };
  }

  /** Har kadr: aylanish, yonqon va ochilish (scale-in) animatsiyasi */
  animate(delta) {
    for (const item of this.items.values()) {
      if (item.age < SPAWN_TIME) {
        item.age = Math.min(SPAWN_TIME, item.age + delta);
        const t = item.age / SPAWN_TIME;
        const eased = 1 - Math.pow(1 - t, 3);
        item.container.scale.setScalar(0.01 + eased * 0.99);
      }

      item.ring.rotation.z += delta * 0.9;
      item.vortex.rotation.z -= delta * 1.5;

      const pulse = 1 + Math.sin(item.age * 3 + item.ring.rotation.z) * 0.06;
      item.ring.scale.setScalar(pulse);
      item.light.intensity = 5 + Math.sin(item.ring.rotation.z * 2) * 1.6;
    }
  }

  dispose() {
    for (const item of this.items.values()) {
      this.group.remove(item.container);
      disposeTree(item.container);
    }
    this.items.clear();
    this.group.parent?.remove(this.group);
    this.signature = null;
  }
}

function disposeTree(root) {
  root.traverse((node) => {
    if (node.geometry) node.geometry.dispose();
    if (node.material) {
      if (Array.isArray(node.material)) node.material.forEach((m) => m.dispose());
      else node.material.dispose();
    }
  });
}
