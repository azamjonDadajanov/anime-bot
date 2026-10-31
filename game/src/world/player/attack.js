import * as THREE from 'three';
import { sounds } from '../../services/sound';

const SLASH_DURATION = 0.3;
const COMBO_DELAY = 0.16; // ikkinchi zarba (combo) kechikishi

// Sehr halqasi
const SPELL_SPEED = 7.5;
const SPELL_RANGE = 9;
// O'q
const ARROW_SPEED = 22;
const ARROW_RANGE = 26;

/** Har bir qahramonning hushum uslubi */
const STYLES = {
  warrior: { kind: 'melee', color: '#fde68a' },
  mage: { kind: 'spell', color: '#c4b5fd' },
  ranger: { kind: 'arrow', color: '#86efac' },
  rogue: { kind: 'combo', color: '#fca5a5' },
};

/**
 * Hujum tizimi — qahramon uslubiga qarab turli xil hujum:
 *
 *   ⚔️ Jangchi  (melee): bitta keng yoysimon zarba, 2 m masofagacha
 *   🔮 Sehrgar  (spell): dumoloq sehr halqasi to'g'ri oldinga uchadi va aylanadi
 *   🏹 Mergan   (arrow): o'q otadi (tez uchuvchi layner)
 *   🗡️ Qaroqchi (combo): ikki zarbali combo — ikkinchisi 0.16 s keyin
 *
 * Barcha effektlar sahnada yaratiladi va o'z vaqtida o'chiriladi.
 * HUD dagi ⚔️ tugmasi yoki F / Space chaqiradi.
 */
export function createAttackController({ character, animator, characterClass, hooks = {} }) {
  const classId = String(characterClass?.id || 'warrior').toLowerCase();
  const style = STYLES[classId] || STYLES.warrior;
  const cooldown = characterClass?.attackCooldown || 0.5;
  // Jangchi va qaroqchi uchun haqiqiy masofa (melee zarba uzunligi)
  const reach = classId === 'warrior' ? 2.0 : characterClass?.attackRange || 2.6;

  let scene = null;
  let timer = cooldown;
  let comboTimer = -1; // >=0 bo'lsa ikkinchi zarba kutilmoqda
  let slash = null;
  let slashTime = SLASH_DURATION;
  let slashTilt = -0.5;
  let lastDirection = { x: 0, z: 1 };
  // Avtomatik nishonlashda uriladigan yo'nalish (sehrgar / kamonboz)
  let aimDir = null;

  const projectiles = [];

  // ── Yordamchilar ──────────────────────────────────────

  function forward() {
    if (aimDir) {
      const len = Math.sqrt(aimDir.x * aimDir.x + aimDir.z * aimDir.z);
      if (len > 0.0001) return new THREE.Vector3(aimDir.x / len, 0, aimDir.z / len);
    }
    const ry = character.rotation.y;
    return new THREE.Vector3(Math.sin(ry), 0, Math.cos(ry));
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

  /** Qahramon oldidagi yoysimon zarba izi (melee / combo) */
  function spawnArc({ scale = 1, tilt = -0.5 } = {}) {
    if (!scene) return;

    const outer = reach * 0.95 * scale;
    const inner = outer * 0.15;
    const geometry = new THREE.RingGeometry(inner, outer, 30, 1, -0.8, 1.6);
    const material = new THREE.MeshBasicMaterial({
      color: style.color,
      transparent: true,
      opacity: 0.95,
      side: THREE.DoubleSide,
      depthWrite: false,
      blending: THREE.AdditiveBlending,
    });

    const mesh = new THREE.Mesh(geometry, material);
    const dir = forward();
    lastDirection = { x: dir.x, z: dir.z };

    // ── Yo'nalish (TO'G'RILANDI) ─────────────────────────
    // Halqa YERGA PARALLEL va qahramon OLDIGA qaragan vifan:
    // kameradan to'g'ri oldinga uzalayotgani ko'rinadi
    // (avvalgi versiya qahramon yonida turgan vertikal halqa edi).
    mesh.position.set(
      character.position.x + dir.x * 0.25,
      character.position.y + .7,
      character.position.z + dir.z * 0.45
    );

    // tilt — gorizontal burilish: 1-zarba biroz chapga, 2-zarba o'ngga
    const c = Math.cos(tilt);
    const s = Math.sin(tilt);
    const xAxis = new THREE.Vector3(
      dir.x * c + dir.z * s,
      0,
      -dir.x * s + dir.z * c
    );
    const zAxis = new THREE.Vector3(0, 1, 0); // normal → yuqoriga (gorizontal tekislik)
    const yAxis = new THREE.Vector3().crossVectors(zAxis, xAxis); // up × fwd
    mesh.quaternion.setFromRotationMatrix(
      new THREE.Matrix4().makeBasis(xAxis, yAxis, zAxis)
    );
    mesh.visible = true;
    mesh.frustumCulled = false;
    scene.add(mesh);

    if (slash) {
      scene.remove(slash);
      slash.geometry.dispose();
      slash.material.dispose();
    }
    slash = mesh;
    slashTime = 0;
    slashTilt = tilt;
  }

  /** 🔮 Dumoloq sehr halqasi — to'g'ri oldinga uchadi va o'z o'qi bo'yicha aylanadi */
  function spawnSpell() {
    if (!scene) return;

    const color = style.color;
    const group = new THREE.Group();

    const ring = new THREE.Mesh(
      new THREE.TorusGeometry(0.62, 0.13, 12, 36),
      new THREE.MeshStandardMaterial({
        color,
        emissive: color,
        emissiveIntensity: 1.4,
        roughness: 0.25,
        transparent: true,
        opacity: 0.95,
      })
    );
    group.add(ring);

    // Ichki yadro (shaffof disk)
    const core = new THREE.Mesh(
      new THREE.CircleGeometry(0.5, 32),
      new THREE.MeshBasicMaterial({
        color,
        transparent: true,
        opacity: 0.45,
        side: THREE.DoubleSide,
        depthWrite: false,
        blending: THREE.AdditiveBlending,
      })
    );
    group.add(core);

    // Ichki aylanuvchi kichik halqa (dumoloqlik hissi)
    const inner = new THREE.Mesh(
      new THREE.TorusGeometry(0.34, 0.07, 10, 28),
      new THREE.MeshStandardMaterial({
        color: '#ffffff',
        emissive: color,
        emissiveIntensity: 1.8,
        transparent: true,
        opacity: 0.9,
      })
    );
    inner.rotation.x = Math.PI / 3;
    group.add(inner);

    const light = new THREE.PointLight(color, 5, 9);
    group.add(light);

    launch(group, {
      speed: SPELL_SPEED,
      range: SPELL_RANGE,
      yOffset: 1.35,
      forwardOffset: 0.9,
      spin: 9,
      sound: () => sounds.playSwing({ from: 380, to: 1800, duration: 0.42, volume: 0.24 }),
      materials: [ring.material, core.material, inner.material],
    });
  }

  /** 🏹 O'q — tez oldinga uchadi */
  function spawnArrow() {
    if (!scene) return;

    const color = style.color;
    const group = new THREE.Group();

    const shaft = new THREE.Mesh(
      new THREE.CylinderGeometry(0.035, 0.035, 1.1, 8),
      new THREE.MeshStandardMaterial({ color: '#8b5a2b', roughness: 0.8 })
    );
    shaft.rotation.x = Math.PI / 2; // silindr o'qi → +Z
    group.add(shaft);

    const head = new THREE.Mesh(
      new THREE.ConeGeometry(0.09, 0.28, 8),
      new THREE.MeshStandardMaterial({
        color,
        emissive: color,
        emissiveIntensity: 0.7,
        metalness: 0.4,
        roughness: 0.3,
      })
    );
    head.rotation.x = Math.PI / 2;
    head.position.z = 0.68;
    group.add(head);

    // Yoy izi (yorqin chiziq)
    const trail = new THREE.Mesh(
      new THREE.PlaneGeometry(0.06, 1.4),
      new THREE.MeshBasicMaterial({
        color,
        transparent: true,
        opacity: 0.5,
        side: THREE.DoubleSide,
        depthWrite: false,
        blending: THREE.AdditiveBlending,
      })
    );
    trail.rotation.x = Math.PI / 2;
    trail.position.z = -0.9;
    group.add(trail);

    launch(group, {
      speed: ARROW_SPEED,
      range: ARROW_RANGE,
      yOffset: 1.35,
      forwardOffset: 0.8,
      spin: 0,
      sound: () => sounds.playSwing({ from: 900, to: 2600, duration: 0.18, volume: 0.22 }),
      materials: [trail.material],
    });
  }

  /** Effektni sahnaga chiqaradi va uchish parametrlarini saqlaydi */
  function launch(object, opts) {
    const dir = forward();
    lastDirection = { x: dir.x, z: dir.z };

    object.position.set(
      character.position.x + dir.x * opts.forwardOffset,
      character.position.y + opts.yOffset,
      character.position.z + dir.z * opts.forwardOffset
    );
    // +Z o'qi parvoz yo'nalishida bo'lsin
    object.lookAt(object.position.clone().add(dir));
    scene.add(object);
    opts.sound && opts.sound();

    projectiles.push({
      object,
      dir,
      speed: opts.speed,
      range: opts.range,
      travelled: 0,
      spin: opts.spin,
      materials: opts.materials || [],
    });
  }

  // ── Hujum zarbalari ───────────────────────────────────

  function strikeMelee() {
    animator && animator.playAttack();
    sounds.playSwing();
    spawnArc({ scale: 1, tilt: -0.3 });
    meleeDamage();
  }

  function strikeComboFirst() {
    animator && animator.playAttack();
    sounds.playSwing({ from: 700, to: 2400, duration: 0.2, volume: 0.3 });
    spawnArc({ scale: 1, tilt: -0.3 });
    meleeDamage();
    comboTimer = COMBO_DELAY;
  }

  function strikeComboSecond() {
    // Ikkinchi zarba — biroz o'ng tomonga burilgan vifan
    animator && animator.playAttack(true);
    sounds.playSwing({ from: 500, to: 3000, duration: 0.16, volume: 0.34 });
    spawnArc({ scale: 0.85, tilt: 0.3 });
    meleeDamage();
  }

  /** Qo'l zarbasi: oldidagi sektor ichidagi mahluqqa zarar beradi */
  function meleeDamage() {
    if (!hooks.meleeHit) return;
    const dir = forward();
    const target = hooks.meleeHit(
      character.position,
      dir.x,
      dir.z,
      reach
    );
    if (target) hooks.onDamage && hooks.onDamage(target);
  }

  return {
    /**
     * Zarbani boshlaydi (cooldown ichida bo'lsa false).
     * `aim` — nishon yo'nalishi {x, z} (avtomatik hujum uchun),
     * berilmasa qahramon qarash yo'nalishi ishlatiladi.
     */
    trigger(aim = null) {
      if (timer < cooldown) return false;
      if (!scene) return false;
      if (hooks.consumeMana && !hooks.consumeMana()) return false;
      timer = 0;
      aimDir = aim ? { x: aim.x, z: aim.z } : null;

      switch (style.kind) {
        case 'spell':
          animator && animator.playAttack();
          spawnSpell();
          break;
        case 'arrow':
          animator && animator.playAttack();
          sounds.playSwing({ from: 600, to: 2200, duration: 0.16, volume: 0.26 });
          spawnArrow();
          break;
        case 'combo':
          strikeComboFirst();
          break;
        case 'melee':
        default:
          strikeMelee();
          break;
      }
      return true;
    },

    get ready() {
      return timer >= cooldown;
    },

    get cooldown() {
      return cooldown;
    },

    /** Jangchi zarbasi qaysi masofagacha (metr) */
    get reach() {
      return reach;
    },

    get style() {
      return style.kind;
    },

    /** qahramon qaysi tomonga hujum qilayotgani */
    get direction() {
      return lastDirection;
    },

    update(delta) {
      timer += delta;

      // Combo: ikkinchi zarba
      if (comboTimer >= 0) {
        comboTimer -= delta;
        if (comboTimer <= 0) {
          comboTimer = -1;
          strikeComboSecond();
        }
      }

      // Zarba izi animatsiyasi
      if (slash && slashTime < SLASH_DURATION) {
        slashTime = Math.min(SLASH_DURATION, slashTime + delta);
        const t = slashTime / SLASH_DURATION;
        // Geometriya o'zi reach bo'yicha qurilgan — masshtab 0.8 → 1.1
        // (jangchi zarbasi ≈ 2 m)
        slash.scale.setScalar(0.8 + t * 0.3);
        slash.material.opacity = 0.95 * (1 - t) * (1 - t);
        if (t >= 1) slash.visible = false;
      }

      // Uchuvchi effektlar (sehr halqasi / o'q) — nishonga tekshiriladi
      for (let i = projectiles.length - 1; i >= 0; i--) {
        const p = projectiles[i];
        const step = p.speed * delta;
        p.object.position.addScaledVector(p.dir, step);
        p.travelled += step;

        // Nishonga urilish tekshiruvi
        if (hooks.projectileHit) {
          const hit = hooks.projectileHit(p.object.position, 1.0);
          if (hit) {
            hooks.onDamage && hooks.onDamage(hit);
            scene.remove(p.object);
            disposeTree(p.object);
            projectiles.splice(i, 1);
            continue;
          }
        }

        if (p.spin) {
          // Dumoloq aylanish: halqa o'z o'qi bo'yicha buriladi
          p.object.rotateZ(p.spin * delta);
          p.object.rotateX(Math.sin(p.travelled * 3) * 0.03);
        }

        // Oxirida so'nadi
        const remain = p.range - p.travelled;
        if (remain <= 0.6) {
          const k = Math.max(0, remain / 0.6);
          for (const m of p.materials) m.opacity = (m.userData.baseOpacity ?? (m.userData.baseOpacity = m.opacity)) * k;
          const s = 0.4 + 0.6 * k;
          p.object.scale.setScalar(s);
        }

        if (remain <= 0) {
          scene.remove(p.object);
          disposeTree(p.object);
          projectiles.splice(i, 1);
        }
      }
    },

    /** Effektlarni sahnaga ulash */
    attachTo(targetScene) {
      scene = targetScene;
    },

    dispose() {
      if (slash && scene) {
        scene.remove(slash);
        slash.geometry.dispose();
        slash.material.dispose();
      }
      slash = null;

      for (const p of projectiles) {
        if (scene) scene.remove(p.object);
        disposeTree(p.object);
      }
      projectiles.length = 0;
      comboTimer = -1;
      scene = null;
    },
  };
}
