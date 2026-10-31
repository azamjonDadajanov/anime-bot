import { HP_REGEN, playerMaxHp, RESPAWN_POINT } from '../../config/enemies';

/**
 * O'YICHINING JONI (HP)
 *
 *  - Maksimal jon daraja bilan oshadi: 100 + (daraja-1) × 25
 *  - Mahluq urganida kamayadi, jang tugagach sekin tiklanadi
 *  - 0 ga tushsa, shahar markazida to'liq jon bilan qayta tug'iladi
 *  - Har o'zgarish `onChange` orqali chaqiriladi (HUD va bazaga saqlash)
 */
export function createPlayerHealth({ level = 1, onChange, onDeath }) {
  let maxHp = playerMaxHp(level);
  let hp = maxHp;
  let lastHitAt = -999;
  let regenTimer = 0;
  let dead = false;
  let respawnTimer = 0;

  function emit() {
    onChange && onChange(Math.round(hp), maxHp);
  }

  return {
    get hp() {
      return hp;
    },
    get maxHp() {
      return maxHp;
    },
    get isDead() {
      return dead;
    },

    /** Daraja oshganda maksimal jon oshadi, joriy jon proporsional qoladi */
    setLevel(newLevel) {
      const newMax = playerMaxHp(newLevel);
      if (newMax !== maxHp) {
        const ratio = maxHp > 0 ? hp / maxHp : 1;
        maxHp = newMax;
        hp = Math.min(maxHp, Math.max(1, Math.round(newMax * ratio)));
        emit();
      }
    },

    /** Bazadan olingan joriy joni qo'llash */
    restore(value) {
      if (typeof value === 'number' && value > 0) {
        hp = Math.min(maxHp, value);
        dead = hp <= 0;
        emit();
      }
    },

    /** Mahluq zarbasi */
    damage(amount) {
      if (dead) return;
      hp -= Math.max(1, amount);
      lastHitAt = performance.now() / 1000;
      if (hp <= 0) {
        hp = 0;
        dead = true;
        respawnTimer = 1.6;
        onDeath && onDeath();
      }
      emit();
    },

    /**
     * Har kadr: tiklanish va qayta tug'ilish.
     * Qayta tug'ilgan bo'lsa 'respawned' qaytaradi (kamera/joylashuv uchun).
     */
    update(delta) {
      if (dead) {
        respawnTimer -= delta;
        if (respawnTimer <= 0) {
          dead = false;
          hp = maxHp;
          emit();
          return 'respawned';
        }
        return null;
      }

      const now = performance.now() / 1000;
      if (now - lastHitAt >= HP_REGEN.delayAfterHit && hp < maxHp) {
        regenTimer += delta;
        if (regenTimer >= HP_REGEN.interval) {
          regenTimer = 0;
          hp = Math.min(maxHp, hp + HP_REGEN.amount);
          emit();
        }
      }
      return null;
    },

    /** Qayta tug'ilish nuqtasi */
    respawnPoint: RESPAWN_POINT,

    healFull() {
      hp = maxHp;
      dead = false;
      emit();
    },
  };
}
