import { sounds } from '../../services/sound';
import { savePlayerPosition } from '../../services/api';
import { WORLD_LIMIT } from '../env/constants';
import { COLLISION_BOXES } from '../env/registry';

const CHAR_RADIUS = 0.6;
const STEP_INTERVAL = 0.35;
const SAVE_INTERVAL = 4.0;

/**
 * Qahramon harakati: kamera yo'nalishi bo'yicha yurish/yugurish,
 * AABB to'siqlar, xarita chegarasi, qadam tovushi va pozitsiyani saqlash.
 */
export function createPlayerController({
  object,
  keys,
  cameraRig,
  characterClass,
  onPositionUpdate,
}) {
  let stepTimer = 0;
  let saveTimer = 0;

  const position = () => object.position;

  function moveWithCollision(dirX, dirZ, distance) {
    const startX = object.position.x;
    const startZ = object.position.z;
    const desiredX = startX + dirX * distance;
    const desiredZ = startZ + dirZ * distance;

    let blocked = false;
    for (let i = 0; i < COLLISION_BOXES.length; i++) {
      const b = COLLISION_BOXES[i];
      if (
        desiredX + CHAR_RADIUS > b.minX &&
        desiredX - CHAR_RADIUS < b.maxX &&
        desiredZ + CHAR_RADIUS > b.minZ &&
        desiredZ - CHAR_RADIUS < b.maxZ
      ) {
        blocked = true;
        break;
      }
    }

    if (!blocked) {
      object.position.x = desiredX;
      object.position.z = desiredZ;
      return;
    }

    // X bo'yicha siljish (sliding)
    const slideX = startX + dirX * distance;
    let xBlocked = false;
    for (let i = 0; i < COLLISION_BOXES.length; i++) {
      const b = COLLISION_BOXES[i];
      if (
        slideX + CHAR_RADIUS > b.minX &&
        slideX - CHAR_RADIUS < b.maxX &&
        startZ + CHAR_RADIUS > b.minZ &&
        startZ - CHAR_RADIUS < b.maxZ
      ) {
        xBlocked = true;
        break;
      }
    }

    // Z bo'yicha siljish
    const slideZ = startZ + dirZ * distance;
    let zBlocked = false;
    for (let i = 0; i < COLLISION_BOXES.length; i++) {
      const b = COLLISION_BOXES[i];
      if (
        startX + CHAR_RADIUS > b.minX &&
        startX - CHAR_RADIUS < b.maxX &&
        slideZ + CHAR_RADIUS > b.minZ &&
        slideZ - CHAR_RADIUS < b.maxZ
      ) {
        zBlocked = true;
        break;
      }
    }

    object.position.x = xBlocked ? startX : slideX;
    object.position.z = zBlocked ? startZ : slideZ;
  }

  function clampToWorld() {
    const x = object.position.x;
    const z = object.position.z;
    const dist = Math.sqrt(x * x + z * z);
    if (dist > WORLD_LIMIT) {
      const ang = Math.atan2(z, x);
      object.position.x = Math.cos(ang) * WORLD_LIMIT;
      object.position.z = Math.sin(ang) * WORLD_LIMIT;
    }
  }

  function faceMovement(dirX, dirZ, delta) {
    const targetAngle = Math.atan2(dirX, dirZ);
    let diff = targetAngle - object.rotation.y;
    while (diff < -Math.PI) diff += Math.PI * 2;
    while (diff > Math.PI) diff -= Math.PI * 2;
    object.rotation.y += diff * 12.0 * delta;
  }

  /** Har kadr chaqiriladi: { isMoving, speed } qaytaradi */
  function update(delta) {
    let forward = 0;
    let right = 0;

    if (keys.analogActive) {
      forward = -keys.analogY;
      right = -keys.analogX;
    } else {
      if (keys.w) forward += 1;
      if (keys.s) forward -= 1;
      if (keys.a) right += 1;
      if (keys.d) right -= 1;
    }

    const isMoving = keys.analogActive
      ? Math.sqrt(forward * forward + right * right) > 0.08
      : forward !== 0 || right !== 0;

    const isRunning = (keys.shift || (keys.analogActive && Math.sqrt(forward * forward + right * right) > 0.8)) && isMoving;
    const speed = (characterClass?.speed || 5.2) * (isRunning ? 2.2 : 1.0);

    if (isMoving) {
      const yaw = cameraRig.yaw;
      const fwdX = Math.sin(yaw);
      const fwdZ = Math.cos(yaw);
      const rightX = Math.cos(yaw);
      const rightZ = -Math.sin(yaw);

      let dirX = forward * fwdX + right * rightX;
      let dirZ = forward * fwdZ + right * rightZ;
      const len = Math.sqrt(dirX * dirX + dirZ * dirZ);
      if (len > 0) {
        dirX /= len;
        dirZ /= len;
      }

      moveWithCollision(dirX, dirZ, speed * delta);
      clampToWorld();
      faceMovement(dirX, dirZ, delta);

      stepTimer += delta;
      if (stepTimer > STEP_INTERVAL) {
        sounds.playSFX('step');
        stepTimer = 0;
      }
    }

    // Pozitsiyani har 4 soniyada (harakatda bo'lganda) saqlash
    saveTimer += delta;
    if (saveTimer > SAVE_INTERVAL && isMoving) {
      savePlayerPosition(
        object.position.x,
        0,
        object.position.z,
        characterClass?.id
      );
      onPositionUpdate &&
        onPositionUpdate({ x: object.position.x, y: 0, z: object.position.z });
      saveTimer = 0;
    }

    return { isMoving, speed };
  }

  return {
    update,
    position,
    saveNow() {
      savePlayerPosition(
        object.position.x,
        0,
        object.position.z,
        characterClass?.id
      );
    },
  };
}
