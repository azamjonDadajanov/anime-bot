/**
 * Third-person kamera: sichqoncha / touch bilan 360° aylanish va
 * qahramon orqasidan ergashish.
 */
export function createCameraRig(container) {
  const state = {
    yaw: 0, // gorizontal burchak
    pitch: 0.35, // vertikal burchak
  };

  const SENSITIVITY = 0.0055;
  const clampPitch = () => {
    state.pitch = Math.max(0.1, Math.min(1.2, state.pitch));
  };

  // ── Sichqoncha ──
  let isMouseDown = false;
  let lastX = 0;
  let lastY = 0;

  const onMouseDown = (e) => {
    isMouseDown = true;
    lastX = e.clientX;
    lastY = e.clientY;
  };

  const onMouseMove = (e) => {
    if (!isMouseDown) return;
    const dx = e.clientX - lastX;
    const dy = e.clientY - lastY;
    lastX = e.clientX;
    lastY = e.clientY;
    state.yaw -= dx * SENSITIVITY;
    state.pitch += dy * SENSITIVITY;
    clampPitch();
  };

  const onMouseUp = () => {
    isMouseDown = false;
  };

  // ── Touch (ekrning o'ng yarmi) ──
  let touchLookId = null;
  let touchLastX = 0;
  let touchLastY = 0;

  const onTouchStart = (e) => {
    for (let i = 0; i < e.touches.length; i++) {
      const t = e.touches[i];
      if (t.clientX > window.innerWidth * 0.4 && touchLookId === null) {
        touchLookId = t.identifier;
        touchLastX = t.clientX;
        touchLastY = t.clientY;
      }
    }
  };

  const onTouchMove = (e) => {
    for (let i = 0; i < e.touches.length; i++) {
      const t = e.touches[i];
      if (t.identifier === touchLookId) {
        const dx = t.clientX - touchLastX;
        const dy = t.clientY - touchLastY;
        touchLastX = t.clientX;
        touchLastY = t.clientY;
        state.yaw -= dx * 0.006;
        state.pitch += dy * 0.006;
        clampPitch();
      }
    }
  };

  const onTouchEnd = (e) => {
    for (let i = 0; i < e.changedTouches.length; i++) {
      if (e.changedTouches[i].identifier === touchLookId) {
        touchLookId = null;
      }
    }
  };

  container.addEventListener('mousedown', onMouseDown);
  window.addEventListener('mousemove', onMouseMove);
  window.addEventListener('mouseup', onMouseUp);
  container.addEventListener('touchstart', onTouchStart, { passive: true });
  container.addEventListener('touchmove', onTouchMove, { passive: true });
  container.addEventListener('touchend', onTouchEnd, { passive: true });

  return {
    get yaw() {
      return state.yaw;
    },
    get pitch() {
      return state.pitch;
    },

    /** Kamerani maqsad (qahramon) orqasida joylashtiradi */
    follow(camera, target) {
      const distance = 7.5;
      const height = 1.4 + Math.sin(state.pitch) * distance;
      const radius = Math.cos(state.pitch) * distance;

      const camX = target.x - Math.sin(state.yaw) * radius;
      const camZ = target.z - Math.cos(state.yaw) * radius;
      const camY = target.y + height;

      camera.position.set(camX, camY, camZ);
      camera.lookAt(target.x, target.y + 1.4, target.z);
    },

    dispose() {
      container.removeEventListener('mousedown', onMouseDown);
      window.removeEventListener('mousemove', onMouseMove);
      window.removeEventListener('mouseup', onMouseUp);
      container.removeEventListener('touchstart', onTouchStart);
      container.removeEventListener('touchmove', onTouchMove);
      container.removeEventListener('touchend', onTouchEnd);
    },
  };
}
