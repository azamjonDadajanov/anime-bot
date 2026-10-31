import * as THREE from 'three';

/**
 * Sahna, kamera, renderer va yorug'likni yaratadi.
 * (Scene / camera / renderer / lighting setup)
 */
export function createStage(container) {
  const scene = new THREE.Scene();
  scene.background = new THREE.Color('#0f172a');
  scene.fog = new THREE.FogExp2('#0f172a', 0.0072);

  const camera = new THREE.PerspectiveCamera(
    55,
    container.clientWidth / container.clientHeight,
    0.1,
    1000
  );
  camera.position.set(0, 6, -8);

  const renderer = new THREE.WebGLRenderer({
    antialias: true,
    powerPreference: 'high-performance',
  });
  renderer.setSize(container.clientWidth, container.clientHeight);
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
  renderer.shadowMap.enabled = true;
  renderer.shadowMap.type = THREE.PCFSoftShadowMap;
  container.appendChild(renderer.domElement);

  // Anime Toon yorug'lik
  const hemiLight = new THREE.HemisphereLight('#c7d2fe', '#1e293b', 1.4);
  scene.add(hemiLight);

  const dirLight = new THREE.DirectionalLight('#fef08a', 1.8);
  dirLight.position.set(35, 50, 25);
  dirLight.castShadow = true;
  dirLight.shadow.mapSize.width = 2048;
  dirLight.shadow.mapSize.height = 2048;
  dirLight.shadow.camera.near = 10;
  dirLight.shadow.camera.far = 160;
  dirLight.shadow.camera.left = -60;
  dirLight.shadow.camera.right = 60;
  dirLight.shadow.camera.top = 60;
  dirLight.shadow.camera.bottom = -60;
  dirLight.shadow.bias = -0.0004;
  scene.add(dirLight);
  scene.add(dirLight.target);

  const handleResize = () => {
    camera.aspect = container.clientWidth / container.clientHeight;
    camera.updateProjectionMatrix();
    renderer.setSize(container.clientWidth, container.clientHeight);
  };
  window.addEventListener('resize', handleResize);

  return {
    scene,
    camera,
    renderer,
    dirLight,
    /** Soya kamerasi o'yinchini kuzatadi (katta xaritada soyalar to'liq tushsin) */
    followLight(x, z) {
      dirLight.position.set(x + 35, 50, z + 25);
      dirLight.target.position.set(x, 0, z);
      dirLight.target.updateMatrixWorld();
    },
    render() {
      renderer.render(scene, camera);
    },
    dispose() {
      window.removeEventListener('resize', handleResize);
      renderer.dispose();
      if (renderer.domElement.parentNode === container) {
        container.removeChild(renderer.domElement);
      }
    },
  };
}
