import * as THREE from 'three';

const ATTACK_DURATION = 0.45;

const AXIS_X = new THREE.Vector3(1, 0, 0);
const AXIS_Y = new THREE.Vector3(0, 1, 0);
const AXIS_Z = new THREE.Vector3(0, 0, 1);

const lerp = (a, b, t) => a + (b - a) * t;
const easeOut = (t) => 1 - (1 - t) * (1 - t);
const easeIn  = (t) => t * t;

/**
 * Procedural Skeletal Animator
 *  - yurish / yugurish (oyoq va qo'llar)
 *  - idle nafas olish
 *  - hujum zarbasi (o'ng qo'l chiqib keyin pastga tushish + tana burilishi)
 *  - o'lim teleport animatsiyasi (tiz cho'kish → ko'tarilish → yo'q bo'lish)
 *
 * Suyak nomlari three.js GLTFLoader tomonidan normalizatsiya qilinadi
 * ("upperarm.l" -> "upperarml"), shuning uchun kalitlar nuqtasiz yozilgan.
 */
export class CharacterAnimator {
  constructor(model) {
    this.model = model;
    this.bones = {};
    this.initialQuats = {};
    this.initialPositions = {};
    this.walkCycle = 0;
    this.idleCycle = 0;

    // Hujum holati
    this.attackTime = ATTACK_DURATION;
    this.attackDuration = ATTACK_DURATION;
    this.attackSeed = 0;

    // O'lim / teleport holati
    this.isDying = false;
    this.deathTime = 0;
    this.deathDuration = 1.8; // soniya
    this.onDeathComplete = null;

    model.traverse((child) => {
      if (child.isBone) {
        const name = child.name.toLowerCase().trim().replace(/[\s.:/[\]]/g, '');
        this.bones[name] = child;
        this.initialQuats[name] = child.quaternion.clone();
        this.initialPositions[name] = child.position.clone();
      }
    });

    this.skinnedMeshes = [];
    model.traverse((child) => {
      if (child.isSkinnedMesh) {
        this.skinnedMeshes.push(child);
      }
    });
  }

  /**
   * Hujum zarbasini boshlaydi (tugma yoki F / Space).
   * force=true — combo ning ikkinchi zarbasi uchun: mavjud zarba
   * tugashini kutmay darhol qayta boshlaydi.
   */
  playAttack(force = false) {
    if (this.isDying) return false;
    if (!force && this.attackTime < this.attackDuration * 0.7) return false;
    this.attackTime = 0;
    this.attackSeed = Math.random();
    return true;
  }

  /**
   * O'lim teleport animatsiyasini boshlaydi.
   * @param {Function} onComplete — animatsiya tugagach chaqiriladi
   */
  playDeath(onComplete) {
    this.isDying = true;
    this.deathTime = 0;
    this.onDeathComplete = onComplete || null;
  }

  get isAttacking() {
    return this.attackTime < this.attackDuration;
  }

  _rot(axis, angle) {
    return new THREE.Quaternion().setFromAxisAngle(axis, angle);
  }

  _compose(base, ...parts) {
    const q = new THREE.Quaternion().copy(base);
    for (const [axis, angle] of parts) q.multiply(this._rot(axis, angle));
    return q;
  }

  update(delta, isMoving, speed = 5.2) {
    const b = this.bones;
    const q0 = this.initialQuats;

    // ── O'lim teleport animatsiyasi ──────────────────────────────────────────
    if (this.isDying) {
      this.deathTime += delta;
      const t = Math.min(1, this.deathTime / this.deathDuration);
      this.#applyDeathPose(t);

      if (t >= 1 && this.onDeathComplete) {
        const cb = this.onDeathComplete;
        this.onDeathComplete = null;
        cb();
      }
      // Skeleton yangilash
      for (let i = 0; i < this.skinnedMeshes.length; i++) {
        if (this.skinnedMeshes[i].skeleton) this.skinnedMeshes[i].skeleton.update();
      }
      return;
    }

    const isRunning = speed > 8.5;
    const attacking = this.attackTime < this.attackDuration;
    if (attacking) this.attackTime += delta;

    // Qo'llarni tanadan biroz masofada, pastga qaratib ushlash burchaklari
    const armDownZ = 0.1;
    const armForwardX = -0.9;

    const skipRightArm = attacking;
    const skipTorsoTwist = attacking;

    if (isMoving) {
      // ===== HARAKATLANISH REJIMI =====
      const cycleSpeed = isRunning ? 7.0 : 4.2;
      this.walkCycle += delta * cycleSpeed;

      const swing = Math.sin(this.walkCycle);
      const legAmp = isRunning ? 0.45 : 0.28;

      const kneeBendL = Math.max(0, -Math.sin(this.walkCycle)) * (isRunning ? 0.45 : 0.2);
      const kneeBendR = Math.max(0, Math.sin(this.walkCycle)) * (isRunning ? 0.45 : 0.2);

      // OYOQLAR
      if (b.upperlegl && q0.upperlegl) {
        b.upperlegl.quaternion.slerp(this._compose(q0.upperlegl, [AXIS_X, swing * legAmp]), 0.15);
      }
      if (b.lowerlegl && q0.lowerlegl) {
        b.lowerlegl.quaternion.slerp(this._compose(q0.lowerlegl, [AXIS_X, -kneeBendL]), 0.15);
      }
      if (b.upperlegr && q0.upperlegr) {
        b.upperlegr.quaternion.slerp(this._compose(q0.upperlegr, [AXIS_X, -swing * legAmp]), 0.15);
      }
      if (b.lowerlegr && q0.lowerlegr) {
        b.lowerlegr.quaternion.slerp(this._compose(q0.lowerlegr, [AXIS_X, -kneeBendR]), 0.15);
      }

      // QO'LLAR
      const armSwingAmp = isRunning ? 0.25 : 0.12;

      if (b.upperarml && q0.upperarml) {
        b.upperarml.quaternion.slerp(
          this._compose(
            q0.upperarml,
            [AXIS_Z, -armDownZ],
            [AXIS_X, armForwardX - swing * armSwingAmp]
          ),
          0.15
        );
      }
      if (b.lowerarml && q0.lowerarml) {
        b.lowerarml.quaternion.slerp(
          this._compose(q0.lowerarml, [AXIS_X, -0.25]),
          0.15
        );
      }

      if (!skipRightArm) {
        if (b.upperarmr && q0.upperarmr) {
          b.upperarmr.quaternion.slerp(
            this._compose(
              q0.upperarmr,
              [AXIS_Z, armDownZ],
              [AXIS_X, armForwardX + swing * armSwingAmp]
            ),
            0.15
          );
        }
        if (b.lowerarmr && q0.lowerarmr) {
          b.lowerarmr.quaternion.slerp(
            this._compose(q0.lowerarmr, [AXIS_X, -0.25]),
            0.15
          );
        }
      }

      // TANA
      if (b.spine && q0.spine) {
        b.spine.quaternion.slerp(
          this._compose(q0.spine, [AXIS_X, isRunning ? 0.08 : 0.03]),
          0.1
        );
      }

      if (b.hips && this.initialPositions.hips) {
        const bounce = Math.abs(Math.sin(this.walkCycle)) * (isRunning ? 0.03 : 0.015);
        b.hips.position.y = this.initialPositions.hips.y - bounce;
      }
    } else {
      // ===== IDLE REJIM =====
      this.idleCycle += delta * 1.8;
      const breath = Math.sin(this.idleCycle);

      if (b.upperarml && q0.upperarml) {
        b.upperarml.quaternion.slerp(
          this._compose(
            q0.upperarml,
            [AXIS_Z, -armDownZ],
            [AXIS_X, armForwardX + breath * 0.015]
          ),
          0.1
        );
      }

      if (!skipRightArm && b.upperarmr && q0.upperarmr) {
        b.upperarmr.quaternion.slerp(
          this._compose(
            q0.upperarmr,
            [AXIS_Z, armDownZ],
            [AXIS_X, armForwardX + breath * 0.015]
          ),
          0.1
        );
      }

      if (b.lowerarml && q0.lowerarml) {
        b.lowerarml.quaternion.slerp(this._compose(q0.lowerarml, [AXIS_X, -0.2]), 0.1);
      }
      if (!skipRightArm && b.lowerarmr && q0.lowerarmr) {
        b.lowerarmr.quaternion.slerp(this._compose(q0.lowerarmr, [AXIS_X, -0.2]), 0.1);
      }

      ['upperlegl', 'upperlegr', 'lowerlegl', 'lowerlegr', 'spine'].forEach((name) => {
        if (b[name] && q0[name]) b[name].quaternion.slerp(q0[name], 0.1);
      });

      if (b.chest && q0.chest && !skipTorsoTwist) {
        b.chest.quaternion.slerp(this._compose(q0.chest, [AXIS_X, breath * 0.025]), 0.1);
      }

      if (b.hips && this.initialPositions.hips) {
        b.hips.position.y = THREE.MathUtils.lerp(
          b.hips.position.y,
          this.initialPositions.hips.y,
          0.1
        );
      }
    }

    // ===== HUJUM ZARBASI =====
    if (attacking) {
      this.#applyAttackPose();
    }

    for (let i = 0; i < this.skinnedMeshes.length; i++) {
      if (this.skinnedMeshes[i].skeleton) {
        this.skinnedMeshes[i].skeleton.update();
      }
    }
  }

  /**
   * O'lim / Teleport animatsiyasi (3 bosqich):
   *  0.0–0.35  → Tiz cho'kish: dizlar bukiladi, bosh egadi, qo'llar pastga
   *  0.35–0.70 → Ko'tarilish: butun model Y bo'ylab yuqoriga ko'tariladi + aylanadi
   *  0.70–1.00 → Yo'q bo'lish: model scale 0 ga tushadi (teleport effekti)
   */
  #applyDeathPose(t) {
    const b = this.bones;
    const q0 = this.initialQuats;
    const p0 = this.initialPositions;

    if (t < 0.35) {
      // Bosqich 1: Tiz cho'kish
      const k = easeOut(t / 0.35);

      // Dizlar bukiladi
      if (b.upperlegl && q0.upperlegl) {
        b.upperlegl.quaternion.slerp(this._compose(q0.upperlegl, [AXIS_X, lerp(0, 1.2, k)]), 0.2);
      }
      if (b.upperlegr && q0.upperlegr) {
        b.upperlegr.quaternion.slerp(this._compose(q0.upperlegr, [AXIS_X, lerp(0, 1.2, k)]), 0.2);
      }
      if (b.lowerlegl && q0.lowerlegl) {
        b.lowerlegl.quaternion.slerp(this._compose(q0.lowerlegl, [AXIS_X, lerp(0, -1.4, k)]), 0.2);
      }
      if (b.lowerlegr && q0.lowerlegr) {
        b.lowerlegr.quaternion.slerp(this._compose(q0.lowerlegr, [AXIS_X, lerp(0, -1.4, k)]), 0.2);
      }

      // Bosh egadi
      if (b.head && q0.head) {
        b.head.quaternion.slerp(this._compose(q0.head, [AXIS_X, lerp(0, 0.6, k)]), 0.15);
      }

      // Qo'llar pastga tushadi
      if (b.upperarml && q0.upperarml) {
        b.upperarml.quaternion.slerp(this._compose(q0.upperarml, [AXIS_X, lerp(-0.9, 0.4, k)]), 0.15);
      }
      if (b.upperarmr && q0.upperarmr) {
        b.upperarmr.quaternion.slerp(this._compose(q0.upperarmr, [AXIS_X, lerp(-0.9, 0.4, k)]), 0.15);
      }

      // Hips pastga tushadi (cho'kish)
      if (b.hips && p0.hips) {
        b.hips.position.y = THREE.MathUtils.lerp(p0.hips.y, p0.hips.y - 0.35, k);
      }

    } else if (t < 0.70) {
      // Bosqich 2: Ko'tarilish va aylanish — model pozitsiyasi bilan ishlaydi
      const k = easeIn((t - 0.35) / 0.35);

      // Qo'llar ikki yonga yoyiladi (teleport pozi)
      if (b.upperarml && q0.upperarml) {
        b.upperarml.quaternion.slerp(
          this._compose(q0.upperarml, [AXIS_Z, lerp(-0.4, -1.4, k)], [AXIS_X, lerp(0.4, -0.3, k)]),
          0.18
        );
      }
      if (b.upperarmr && q0.upperarmr) {
        b.upperarmr.quaternion.slerp(
          this._compose(q0.upperarmr, [AXIS_Z, lerp(0.4, 1.4, k)], [AXIS_X, lerp(0.4, -0.3, k)]),
          0.18
        );
      }

      // Bosh yuqoriga qarash
      if (b.head && q0.head) {
        b.head.quaternion.slerp(this._compose(q0.head, [AXIS_X, lerp(0.6, -0.4, k)]), 0.15);
      }

      // Dizlar to'g'rilanadi
      if (b.upperlegl && q0.upperlegl) {
        b.upperlegl.quaternion.slerp(this._compose(q0.upperlegl, [AXIS_X, lerp(1.2, 0, k)]), 0.18);
      }
      if (b.upperlegr && q0.upperlegr) {
        b.upperlegr.quaternion.slerp(this._compose(q0.upperlegr, [AXIS_X, lerp(1.2, 0, k)]), 0.18);
      }
      if (b.lowerlegl && q0.lowerlegl) {
        b.lowerlegl.quaternion.slerp(this._compose(q0.lowerlegl, [AXIS_X, lerp(-1.4, 0, k)]), 0.18);
      }
      if (b.lowerlegr && q0.lowerlegr) {
        b.lowerlegr.quaternion.slerp(this._compose(q0.lowerlegr, [AXIS_X, lerp(-1.4, 0, k)]), 0.18);
      }

      // Model yuqoriga ko'tariladi
      this.model.position.y = lerp(0, 2.8, k);
      // Model Y bo'ylab aylana boshlaydi
      this.model.rotation.y += 0.06;

    } else {
      // Bosqich 3: Yo'q bo'lish — scale 0 ga
      const k = easeIn((t - 0.70) / 0.30);
      const sc = Math.max(0, 1 - k);
      this.model.scale.setScalar(sc * 1.2);
      this.model.position.y = lerp(2.8, 4.5, k);
      this.model.rotation.y += 0.12;
    }
  }

  /**
   * Hujum: ko'tarish (windup) -> kesish (chop) -> qaytish.
   * O'ng qo'l + tana burilishi birga ishlaydi.
   */
  #applyAttackPose() {
    const t = Math.min(1, this.attackTime / this.attackDuration);
    const b = this.bones;
    const q0 = this.initialQuats;

    const baseX = -0.9;
    const baseZ = 0.1;
    const baseElbow = -0.2;

    let raise;
    let swing;
    let elbow;
    let twist;

    if (t < 0.3) {
      // Windup: qo'l yuqoriga/orqaga ko'tariladi (deyarli YON tomonga chiqmaydi)
      const k = easeOut(t / 0.3);
      raise = lerp(baseX, 1.7, k);
      swing = lerp(baseZ, -0.18, k);
      elbow = lerp(baseElbow, -1.0, k);
      twist = lerp(0, 0.18, k);
    } else if (t < 0.62) {
      // Kesish (chop): qo'l TO'G'RI OLDINGA, sagittal tekislikda tushadi
      const k = easeOut((t - 0.3) / 0.32);
      raise = lerp(1.7, -1.8, k);
      swing = lerp(-0.18, 0.2, k);
      elbow = lerp(-1.0, 0.05, k);
      twist = lerp(0.18, -0.2, k);
    } else {
      // Qaytish
      const k = (t - 0.62) / 0.38;
      raise = lerp(-1.8, baseX, k);
      swing = lerp(0.2, baseZ, k);
      elbow = lerp(0.05, baseElbow, k);
      twist = lerp(-0.2, 0, k);
    }

    if (b.upperarmr && q0.upperarmr) {
      b.upperarmr.quaternion.slerp(
        this._compose(q0.upperarmr, [AXIS_Z, swing], [AXIS_X, raise]),
        0.55
      );
    }
    if (b.lowerarmr && q0.lowerarmr) {
      b.lowerarmr.quaternion.slerp(
        this._compose(q0.lowerarmr, [AXIS_X, elbow]),
        0.55
      );
    }
    if (b.chest && q0.chest) {
      b.chest.quaternion.slerp(
        this._compose(q0.chest, [AXIS_Z, twist], [AXIS_X, t > 0.3 && t < 0.7 ? 0.12 : 0]),
        0.4
      );
    }
    if (b.spine && q0.spine) {
      b.spine.quaternion.slerp(
        this._compose(q0.spine, [AXIS_Z, twist * 0.4]),
        0.4
      );
    }
  }
}

