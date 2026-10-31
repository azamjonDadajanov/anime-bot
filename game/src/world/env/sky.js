import * as THREE from 'three';
import { CLOUD_MESHES } from './registry';

/**
 * OSMON — sky dome, quyosh va harakatlanuvchi bulutlar
 */
export function buildSky(scene) {
  const skyGeo = new THREE.SphereGeometry(400, 32, 16);
  skyGeo.scale(-1, 1, 1);

  // Gradient texture — pastdan yuqoriga ko'k
  const skyCanvas = document.createElement('canvas');
  skyCanvas.width = 2;
  skyCanvas.height = 256;
  const skyCtx = skyCanvas.getContext('2d');
  const grad = skyCtx.createLinearGradient(0, 0, 0, 256);
  grad.addColorStop(0.0, '#0a1628');
  grad.addColorStop(0.3, '#1a3a6e');
  grad.addColorStop(0.65, '#4a90d9');
  grad.addColorStop(0.85, '#f4a460');
  grad.addColorStop(1.0, '#c0b090');
  skyCtx.fillStyle = grad;
  skyCtx.fillRect(0, 0, 2, 256);

  const skyTex = new THREE.CanvasTexture(skyCanvas);
  const skyMat = new THREE.MeshBasicMaterial({ map: skyTex, side: THREE.BackSide });
  const skyDome = new THREE.Mesh(skyGeo, skyMat);
  skyDome.rotation.x = Math.PI / 2;
  scene.add(skyDome);

  // QUYOSH
  const sun = new THREE.Mesh(
    new THREE.SphereGeometry(8, 16, 16),
    new THREE.MeshBasicMaterial({ color: '#fffde4' })
  );
  sun.position.set(120, 160, -200);
  scene.add(sun);

  const sunGlow = new THREE.PointLight('#fff8e1', 1.2, 500);
  sunGlow.position.copy(sun.position);
  scene.add(sunGlow);

  const halo = new THREE.Mesh(
    new THREE.CircleGeometry(20, 32),
    new THREE.MeshBasicMaterial({ color: '#fffae0', transparent: true, opacity: 0.15 })
  );
  halo.position.copy(sun.position);
  halo.lookAt(0, 0, 0);
  scene.add(halo);

  buildClouds(scene);
}

function buildClouds(scene) {
  const cloudMat = new THREE.MeshStandardMaterial({
    color: '#ffffff',
    roughness: 1,
    metalness: 0,
    transparent: true,
    opacity: 0.88,
    flatShading: true,
  });

  const cloudConfigs = [
    { x: 60, y: 80, z: -80, scale: 18, count: 7 },
    { x: -90, y: 90, z: -50, scale: 22, count: 8 },
    { x: 20, y: 75, z: 100, scale: 15, count: 6 },
    { x: -30, y: 95, z: -120, scale: 25, count: 9 },
    { x: 110, y: 85, z: 40, scale: 20, count: 7 },
    { x: -60, y: 70, z: 80, scale: 16, count: 6 },
    { x: 40, y: 100, z: -160, scale: 28, count: 10 },
    { x: -120, y: 88, z: 10, scale: 19, count: 7 },
  ];

  cloudConfigs.forEach((cfg) => {
    const cloudGroup = new THREE.Group();
    cloudGroup.position.set(cfg.x, cfg.y, cfg.z);

    for (let i = 0; i < cfg.count; i++) {
      const r = cfg.scale * (0.5 + Math.random() * 0.7);
      const blob = new THREE.Mesh(new THREE.SphereGeometry(r, 7, 5), cloudMat.clone());
      blob.position.set(
        (Math.random() - 0.5) * cfg.scale * 2.5,
        (Math.random() - 0.5) * cfg.scale * 0.4,
        (Math.random() - 0.5) * cfg.scale * 1.5
      );
      blob.scale.set(1, 0.55, 0.75);
      cloudGroup.add(blob);
    }

    cloudGroup.userData.driftSpeed = 0.4 + Math.random() * 0.8;
    cloudGroup.userData.driftDir = Math.random() > 0.5 ? 1 : -1;
    scene.add(cloudGroup);
    CLOUD_MESHES.push(cloudGroup);
  });
}
