/**
 * Klaviatura boshqaruvi — WASD / strelkalar / Shift (yugurish) / F yoki bo'shliq (hujum)
 */
export function createInput({ onAttack } = {}) {
  const keys = {
    w: false,
    a: false,
    s: false,
    d: false,
    shift: false,
    analogActive: false,
    analogX: 0,
    analogY: 0,
  };

  const onKeyDown = (e) => {
    const key = e.key.toLowerCase();
    if (key === 'w' || key === 'arrowup') keys.w = true;
    if (key === 's' || key === 'arrowdown') keys.s = true;
    if (key === 'a' || key === 'arrowleft') keys.a = true;
    if (key === 'd' || key === 'arrowright') keys.d = true;
    if (e.key === 'Shift') keys.shift = true;

    if ((key === 'f' || key === ' ') && !e.repeat) {
      if (key === ' ') e.preventDefault();
      onAttack && onAttack();
    }
  };

  const onKeyUp = (e) => {
    const key = e.key.toLowerCase();
    if (key === 'w' || key === 'arrowup') keys.w = false;
    if (key === 's' || key === 'arrowdown') keys.s = false;
    if (key === 'a' || key === 'arrowleft') keys.a = false;
    if (key === 'd' || key === 'arrowright') keys.d = false;
    if (e.key === 'Shift') keys.shift = false;
  };

  const onJoystick = (e) => {
    const { x, y, active } = e.detail || {};
    keys.analogActive = Boolean(active);
    keys.analogX = x || 0;
    keys.analogY = y || 0;
    if (active) {
      keys.w = y < -0.22;
      keys.s = y > 0.22;
      keys.a = x < -0.22;
      keys.d = x > 0.22;
      keys.shift = Math.sqrt(x * x + y * y) > 0.85;
    } else {
      keys.w = false;
      keys.s = false;
      keys.a = false;
      keys.d = false;
      keys.shift = false;
    }
  };

  window.addEventListener('keydown', onKeyDown);
  window.addEventListener('keyup', onKeyUp);
  window.addEventListener('game:joystick', onJoystick);

  return {
    keys,
    isMoving() {
      return keys.analogActive || keys.w || keys.a || keys.s || keys.d;
    },
    dispose() {
      window.removeEventListener('keydown', onKeyDown);
      window.removeEventListener('keyup', onKeyUp);
      window.removeEventListener('game:joystick', onJoystick);
    },
  };
}
