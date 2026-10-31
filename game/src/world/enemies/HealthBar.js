import * as THREE from 'three';

const CANVAS_W = 128;
const CANVAS_H = 20;

/**
 * Mahluqning boshida osilib turuvchi jon (HP) chizig'i.
 * CanvasTexture orqali chiziladi, qiymat o'zgargandagina qayta chiziladi.
 */
export class HealthBar {
  constructor(worldWidth = 1.6) {
    this.canvas = document.createElement('canvas');
    this.canvas.width = CANVAS_W;
    this.canvas.height = CANVAS_H;
    this.ctx = this.canvas.getContext('2d');
    this.lastFrac = -1;

    this.texture = new THREE.CanvasTexture(this.canvas);
    this.texture.colorSpace = THREE.SRGBColorSpace;

    this.sprite = new THREE.Sprite(
      new THREE.SpriteMaterial({
        map: this.texture,
        transparent: true,
        depthTest: false,
      })
    );
    this.sprite.scale.set(worldWidth, worldWidth * (CANVAS_H / CANVAS_W), 1);
    this.sprite.renderOrder = 10;
    this.sprite.visible = false;
  }

  /** frac: 0..1 — o'zgarganda qayta chizadi */
  set(frac) {
    const f = Math.max(0, Math.min(1, frac));
    if (Math.abs(f - this.lastFrac) < 0.01) return;
    this.lastFrac = f;

    const ctx = this.ctx;
    const w = CANVAS_W;
    const h = CANVAS_H;

    ctx.clearRect(0, 0, w, h);

    // Fon (qora ramka)
    ctx.fillStyle = 'rgba(8, 10, 20, 0.85)';
    roundRect(ctx, 1, 1, w - 2, h - 2, 6);
    ctx.fill();

    // To'ldirish
    const inner = (w - 6) * f;
    if (inner > 0.5) {
      ctx.fillStyle = f > 0.55 ? '#4ade80' : f > 0.25 ? '#fbbf24' : '#f87171';
      roundRect(ctx, 3, 3, inner, h - 6, 4);
      ctx.fill();
    }

    this.texture.needsUpdate = true;
  }

  show(visible) {
    this.sprite.visible = visible;
  }

  dispose() {
    this.texture.dispose();
    this.sprite.material.dispose();
  }
}

function roundRect(ctx, x, y, w, h, r) {
  const radius = Math.min(r, w / 2, h / 2);
  ctx.beginPath();
  ctx.moveTo(x + radius, y);
  ctx.lineTo(x + w - radius, y);
  ctx.quadraticCurveTo(x + w, y, x + w, y + radius);
  ctx.lineTo(x + w, y + h - radius);
  ctx.quadraticCurveTo(x + w, y + h, x + w - radius, y + h);
  ctx.lineTo(x + radius, y + h);
  ctx.quadraticCurveTo(x, y + h, x, y + h - radius);
  ctx.lineTo(x, y + radius);
  ctx.quadraticCurveTo(x, y, x + radius, y);
  ctx.closePath();
}
