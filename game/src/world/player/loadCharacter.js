import * as THREE from 'three';
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js';

const CHARACTER_SCALE = 1.2;

/**
 * Qahramon GLB modelini yuklaydi, unga klass teksturasini bog'laydi
 * va boshlang'ich joylashuviga qo'yadi. Muvaffaqiyatsiz bo'lsa `null`.
 */
export function loadCharacter({ modelUrl, textureUrl, position }) {
  return new Promise((resolve) => {
    const loader = new GLTFLoader();

    let charTexture = null;
    if (textureUrl) {
      charTexture = new THREE.TextureLoader().load(textureUrl);
      charTexture.flipY = false;
      charTexture.colorSpace = THREE.SRGBColorSpace;
    }

    loader.load(
      modelUrl,
      (gltf) => {
        const char = gltf.scene;
        char.scale.setScalar(CHARACTER_SCALE);
        char.position.set(position.x, 0.05, position.z);

        // SkinnedMesh materialiga teksturani ulaymiz (materialni almashtirmasdan)
        char.traverse((child) => {
          if (child.isMesh || child.isSkinnedMesh) {
            child.castShadow = true;
            child.receiveShadow = true;
            if (charTexture && child.material) {
              child.material.map = charTexture;
              child.material.roughness = 0.7;
              child.material.metalness = 0.1;
              child.material.needsUpdate = true;
            }
          }
        });

        resolve(char);
      },
      undefined,
      (err) => {
        console.error('GLB character load error:', err);
        resolve(null);
      }
    );
  });
}

export { CHARACTER_SCALE };
