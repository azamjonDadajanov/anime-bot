import * as THREE from 'three';

/**
 * ZONA BELGILARI — havoda osilib turuvchi 3D yozuvlar
 */
export function buildSigns(group) {
  const signs = [
    { text: '🏰 SHAHAR MARKAZI', x: 0, y: 16, z: 30 },
    { text: "🌲 SEHRLI O'RMON", x: 58, y: 14, z: 46 },
    { text: '🔮 QADIMIY HAROBALAR', x: -62, y: 14, z: -42 },
    { text: '🌿 KENG MAYDON', x: 84, y: 13, z: -20 },
    { text: '⛰️ TOGLAR', x: -30, y: 20, z: -138 },
  ];

  signs.forEach((s) => group.add(createSign(s.text, s.x, s.y, s.z)));
}

function createSign(text, x, y, z) {
  const canvas = document.createElement('canvas');
  canvas.width = 640;
  canvas.height = 160;
  const ctx = canvas.getContext('2d');

  ctx.fillStyle = 'rgba(10, 18, 40, 0.92)';
  if (ctx.roundRect) {
    ctx.beginPath();
    ctx.roundRect(8, 8, 624, 144, 24);
    ctx.fill();
  } else {
    ctx.rect(8, 8, 624, 144);
    ctx.fill();
  }

  ctx.strokeStyle = '#f59e0b';
  ctx.lineWidth = 7;
  ctx.stroke();

  ctx.fillStyle = '#fde68a';
  ctx.font = 'bold 40px Arial, sans-serif';
  ctx.textAlign = 'center';
  ctx.textBaseline = 'middle';
  ctx.fillText(text, 320, 80, 600);

  const tex = new THREE.CanvasTexture(canvas);
  const sprite = new THREE.Sprite(
    new THREE.SpriteMaterial({ map: tex, transparent: true })
  );
  sprite.position.set(x, y, z);
  sprite.scale.set(18, 4.5, 1);
  return sprite;
}
