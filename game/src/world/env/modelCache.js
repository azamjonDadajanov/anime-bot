import * as THREE from 'three';
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js';

/**
 * GLTF modellarini bir marta yuklab, nusxalarni (clone) beruvchi kesh.
 * Bir xil model yuzlab marta ishlatilsa ham, fayl faqat bir yuklanadi.
 */
const loader = new GLTFLoader();
const templateCache = new Map();

/** Modelni (template) yuklaydi. Muvaffaqiyatsiz bo'lsa `null` qaytaradi. */
export function loadTemplate(path) {
  if (!templateCache.has(path)) {
    templateCache.set(
      path,
      new Promise((resolve) => {
        loader.load(
          path,
          (gltf) => resolve(gltf.scene),
          undefined,
          () => resolve(null)
        );
      })
    );
  }
  return templateCache.get(path);
}

/** Model nusxasini yaratadi (soyalarni yoqadi). Topilmasa `null`. */
export async function instantiate(path) {
  const template = await loadTemplate(path);
  if (!template) return null;
  const clone = template.clone(true);
  enableShadows(clone);
  return clone;
}

/** Butun daraxt ustidan soyani yoqadi */
export function enableShadows(root) {
  root.traverse((node) => {
    if (node.isMesh || node.isSkinnedMesh) {
      node.castShadow = true;
      node.receiveShadow = true;
    }
  });
  return root;
}
