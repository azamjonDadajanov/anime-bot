/**
 * BattleArena — Portal jang maydoni
 * O'yinchi portalga kirganda 3D arenaga o'tadi.
 * To'lqin-to'lqin skeletlar (Minion, Rogue, Warrior, Mage, Boss) hujum qiladi.
 * To'liq o'yinchi boshqaruvi (WASD, strelkalar, yugurish, virtual joystik, kamera va hujum).
 * Boss yengilgandan so'ng: Avval Sandiq ochiladi, so'ngra zindondan chiqish so'raladi.
 */
import React, { useEffect, useRef, useState, useCallback } from 'react';
import * as THREE from 'three';
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js';
import { clone as cloneSkeleton } from 'three/examples/jsm/utils/SkeletonUtils.js';
import { CharacterAnimator } from '../world/player/CharacterAnimator';
import { sounds } from '../services/sound';
import { startBattle, nextWave, completeBattle, fleeBattle } from '../services/api';
import { playerMaxMana, playerManaRegen, attackManaCost } from '../config/level';
import { playerMaxHp, playerDamage } from '../config/enemies';
import Joystick from './Joystick';

const RANK_COLORS = {
  F: '#94a3b8', E: '#22c55e', D: '#3b82f6',
  C: '#a855f7', B: '#f59e0b', A: '#ef4444', S: '#e11d48',
};

const SKELETON_TEMPLATES = {
  minion: '/models/sketelons/Skeleton_Minion.glb',
  rogue:  '/models/sketelons/Skeleton_Rogue.glb',
  warrior:'/models/sketelons/Skeleton_Warrior.glb',
  mage:   '/models/sketelons/Skeleton_Mage.glb',
};

const SKELETON_ITEMS = {
  blade:    '/models/sketelons_items/Skeleton_Blade.gltf',
  crossbow: '/models/sketelons_items/Skeleton_Crossbow.gltf',
  axe:      '/models/sketelons_items/Skeleton_Axe.gltf',
  shield:   '/models/sketelons_items/Skeleton_Shield_Large_A.gltf',
  staff:    '/models/sketelons_items/Skeleton_Staff.gltf',
};

export default function BattleArena({
  portal,
  combat,
  characterClass,
  playerPosition,
  onBattleEnd,
  onFlee,
}) {
  const mountRef = useRef(null);
  const playerLevel = combat?.level || 1;

  // Portal kirish bonusi: barcha statlar 30% oshadi
  const PORTAL_BUFF = 3;

  // Statlar (30% buffed)
  const maxHpVal   = Math.round(playerMaxHp(playerLevel) * PORTAL_BUFF);
  const maxManaVal = Math.round(playerMaxMana(playerLevel, characterClass) * PORTAL_BUFF);
  const manaCost   = attackManaCost(characterClass); // mana sarfi o'zgarmaydi

  // Jang bosqichlari: loading | fighting | wave_clear | chest_ready | chest_opened | defeat
  const [battlePhase, setBattlePhase] = useState('loading');
  const [battleId, setBattleId]       = useState(null);
  const [waveNum, setWaveNum]          = useState(1);
  const [wavesTotal, setWavesTotal]    = useState(3);
  const [playerHp, setPlayerHp]        = useState(maxHpVal);
  const [playerMana, setPlayerMana]    = useState(maxManaVal);
  const [attackCooldown, setAttackCooldown] = useState(false);
  const [totalXp, setTotalXp]          = useState(0);
  const [totalCoins, setTotalCoins]    = useState(0);
  const [totalKills, setTotalKills]    = useState(0);
  const [chestRewards, setChestRewards]= useState([]);
  const [resultData, setResultData]    = useState(null);
  const [waveMessage, setWaveMessage]  = useState('');
  const [openingChest, setOpeningChest]= useState(false);

  // Three.js refs
  const sceneRef      = useRef(null);
  const cameraRef     = useRef(null);
  const rendererRef   = useRef(null);
  const charRef       = useRef(null);
  const animRef       = useRef(null);
  const enemiesRef    = useRef([]);
  const clockRef      = useRef(new THREE.Clock());
  const animIdRef     = useRef(null);
  const templatesRef  = useRef({});
  const itemsCacheRef = useRef({});

  // Harakat va kirish (WASD / Joystik)
  const keysRef = useRef({
    forward: false, backward: false, left: false, right: false, shift: false,
  });
  const analogRef = useRef({ x: 0, y: 0, active: false });
  const triggerAttackRef = useRef(null); // stale closure oldini olish uchun

  // State refs
  const battleIdRef      = useRef(null);
  const wavesTotalRef    = useRef(3);
  const waveNumRef       = useRef(1);
  const playerHpRef      = useRef(maxHpVal);
  const playerManaRef    = useRef(maxManaVal);
  const totalXpRef       = useRef(0);
  const totalCoinsRef    = useRef(0);
  const totalKillsRef    = useRef(0);
  const phaseRef         = useRef('loading');
  const attackCdRef      = useRef(false);
  const cameraYaw        = useRef(Math.PI);
  const cameraOrbit      = useRef(false);
  const camLastX         = useRef(0);

  // ─── Skelet 3D modellari yuklash va keshlashtirish ───────────────────────
  const getSkeletonTemplate = async (typeKey) => {
    if (templatesRef.current[typeKey]) return templatesRef.current[typeKey];
    const loader = new GLTFLoader();
    const url = SKELETON_TEMPLATES[typeKey] || SKELETON_TEMPLATES.minion;
    return new Promise((resolve) => {
      loader.load(
        url,
        (gltf) => {
          templatesRef.current[typeKey] = gltf.scene;
          resolve(gltf.scene);
        },
        undefined,
        () => resolve(null)
      );
    });
  };

  const getItemModel = async (itemKey) => {
    if (itemsCacheRef.current[itemKey]) return itemsCacheRef.current[itemKey].clone();
    const loader = new GLTFLoader();
    const url = SKELETON_ITEMS[itemKey];
    if (!url) return null;
    return new Promise((resolve) => {
      loader.load(
        url,
        (gltf) => {
          itemsCacheRef.current[itemKey] = gltf.scene;
          resolve(gltf.scene.clone());
        },
        undefined,
        () => resolve(null)
      );
    });
  };

  // ─── HP Canvas Sprite yaratish ──────────────────────────────────────────
  const createHpSprite = (monsterData, scaleMultiplier) => {
    const canvas = document.createElement('canvas');
    canvas.width = 128;
    canvas.height = 24;
    const ctx = canvas.getContext('2d');
    const tex = new THREE.CanvasTexture(canvas);
    const sprite = new THREE.Sprite(new THREE.SpriteMaterial({ map: tex, transparent: true }));
    const s = scaleMultiplier || 1.0;
    sprite.position.y = (monsterData.is_boss ? 3.6 : 2.4) * s;
    sprite.scale.set(1.9 * s, 0.42 * s, 1);
    return { sprite, canvas, ctx, tex };
  };

  const updateEnemyHpBar = (enemyObj) => {
    const { hpCtx, hpCanvas, hpTex, currentHp, maxHp, monster } = enemyObj;
    if (!hpCtx) return;
    const pct = Math.max(0, currentHp / (maxHp || 1));
    hpCtx.clearRect(0, 0, 128, 24);

    // Orqa fon
    hpCtx.fillStyle = '#111827';
    hpCtx.fillRect(0, 4, 128, 16);

    // HP to'ldirish
    const hpColor = pct > 0.6 ? '#22c55e' : pct > 0.3 ? '#f59e0b' : '#ef4444';
    hpCtx.fillStyle = hpColor;
    hpCtx.fillRect(0, 4, Math.round(128 * pct), 16);

    // Matn
    hpCtx.fillStyle = RANK_COLORS[monster.rank] || '#fff';
    hpCtx.font = 'bold 9px sans-serif';
    hpCtx.textAlign = 'center';
    hpCtx.fillText(`[${monster.rank}] ${monster.name} ${currentHp}/${maxHp}`, 64, 15);

    if (hpTex) hpTex.needsUpdate = true;
  };

  // ─── Skelet Mahluqini sahnaga yasash ─────────────────────────────────────
  const createSkeletonEnemy = async (monsterData) => {
    let typeKey = 'minion';
    let weaponKey = 'blade';
    let shieldKey = null;

    const wType = monsterData.weapon_type || '';
    const mName = monsterData.name || '';

    if (wType === 'staff' || mName.includes('Sehr') || mName.includes('Mage')) {
      typeKey = 'mage';
      weaponKey = 'staff';
    } else if (wType === 'bow' || wType === 'crossbow' || mName.includes('Kamon') || mName.includes('Qaroqchi')) {
      typeKey = 'rogue';
      weaponKey = 'crossbow';
    } else if (wType === 'axe' || mName.includes('Jangchi') || monsterData.is_boss) {
      typeKey = 'warrior';
      weaponKey = 'axe';
      shieldKey = 'shield';
    }

    let scaleMultiplier = 1.05;
    if (monsterData.is_boss || monsterData.rank === 'S') {
      scaleMultiplier = 2.65; // Katta va dahshatli Boss!
    } else if (monsterData.rank === 'A') {
      scaleMultiplier = 1.95;
    } else if (monsterData.rank === 'B') {
      scaleMultiplier = 1.65;
    } else if (monsterData.rank === 'C') {
      scaleMultiplier = 1.4;
    } else if (monsterData.rank === 'D') {
      scaleMultiplier = 1.25;
    } else if (monsterData.rank === 'E') {
      scaleMultiplier = 1.15;
    }

    const template = await getSkeletonTemplate(typeKey);
    const model = template ? cloneSkeleton(template) : new THREE.Group();
    model.scale.setScalar(scaleMultiplier);

    model.traverse((n) => {
      if (n.isMesh || n.isSkinnedMesh) {
        n.castShadow = true;
        n.receiveShadow = true;
        n.frustumCulled = false;
        if (monsterData.is_boss && n.material) {
          n.material = n.material.clone();
          n.material.color = new THREE.Color('#7f1d1d');
        }
      }
    });

    const rHand = model.getObjectByName('handslotr') || model.getObjectByName('handr');
    if (rHand && weaponKey) {
      const wMesh = await getItemModel(weaponKey);
      if (wMesh) {
        wMesh.scale.setScalar(0.7);
        wMesh.rotation.set(0, 0, -Math.PI / 2);
        rHand.add(wMesh);
      }
    }

    const lHand = model.getObjectByName('handslotl') || model.getObjectByName('handl');
    if (lHand && shieldKey) {
      const sMesh = await getItemModel(shieldKey);
      if (sMesh) {
        sMesh.scale.setScalar(0.75);
        sMesh.rotation.set(-Math.PI / 2, 0, 0);
        lHand.add(sMesh);
      }
    }

    if (monsterData.is_boss) {
      const aura = new THREE.Mesh(
        new THREE.TorusGeometry(1.2 * scaleMultiplier, 0.08 * scaleMultiplier, 8, 32),
        new THREE.MeshBasicMaterial({ color: '#ef4444', transparent: true, opacity: 0.85 })
      );
      aura.rotation.x = Math.PI / 2;
      aura.position.y = 0.1;
      model.add(aura);
      model.userData.aura = aura;
    }

    const { sprite, canvas, ctx, tex } = createHpSprite(monsterData, scaleMultiplier);
    model.add(sprite);

    const animator = new CharacterAnimator(model);
    const hp = Number(monsterData.hp || monsterData.max_hp || 60);

    const enemyObj = {
      model,
      animator,
      hpSprite: sprite,
      hpCanvas: canvas,
      hpCtx: ctx,
      hpTex: tex,
      currentHp: hp,
      maxHp: hp,
      monster: { ...monsterData },
      damage: Number(monsterData.damage ?? monsterData.attack_damage ?? 12),
      attackRange: Number(monsterData.attack_range || (typeKey === 'mage' || typeKey === 'rogue' ? 9.0 : 2.2)),
      speed: Number(monsterData.move_speed || 2.4),
      attackSpeed: Number(monsterData.attack_speed || 1.3),
      attackTimer: Math.random() * 1.0,
      isDead: false,
      deathTimer: 0,
    };

    updateEnemyHpBar(enemyObj);
    return enemyObj;
  };

  // ─── Sahna qurish va Loop ────────────────────────────────────────────────
  useEffect(() => {
    const container = mountRef.current;
    if (!container) return;

    // Scene
    const scene = new THREE.Scene();
    scene.background = new THREE.Color('#0a0a14');
    scene.fog = new THREE.FogExp2('#0a0a14', 0.022);
    sceneRef.current = scene;

    // Camera
    const camera = new THREE.PerspectiveCamera(
      60,
      container.clientWidth / container.clientHeight,
      0.1,
      300
    );
    cameraRef.current = camera;

    // Renderer
    const renderer = new THREE.WebGLRenderer({ antialias: true });
    renderer.setSize(container.clientWidth, container.clientHeight);
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.shadowMap.enabled = true;
    renderer.shadowMap.type = THREE.PCFSoftShadowMap;
    renderer.domElement.style.touchAction = 'none';
    container.appendChild(renderer.domElement);
    rendererRef.current = renderer;

    // Yorug'lik
    scene.add(new THREE.AmbientLight('#475569', 2.0));
    const dLight = new THREE.DirectionalLight('#c084fc', 3.2);
    dLight.position.set(12, 25, 12);
    dLight.castShadow = true;
    scene.add(dLight);

    // Arena zamini (doira)
    const arenaFloor = new THREE.Mesh(
      new THREE.CircleGeometry(22, 48),
      new THREE.MeshStandardMaterial({ color: '#1e1b4b', roughness: 0.85 })
    );
    arenaFloor.rotation.x = -Math.PI / 2;
    arenaFloor.receiveShadow = true;
    scene.add(arenaFloor);

    // Arena devor halqasi
    const wallRing = new THREE.Mesh(
      new THREE.TorusGeometry(21.5, 0.7, 8, 48),
      new THREE.MeshStandardMaterial({
        color: '#581c87',
        emissive: '#3b0764',
        emissiveIntensity: 0.5,
        flatShading: true,
      })
    );
    wallRing.rotation.x = Math.PI / 2;
    wallRing.position.y = 1.0;
    scene.add(wallRing);

    // Ustunlar va kristallar
    for (let i = 0; i < 8; i++) {
      const a = (i / 8) * Math.PI * 2;
      const px = Math.cos(a) * 20;
      const pz = Math.sin(a) * 20;

      const pillar = new THREE.Mesh(
        new THREE.CylinderGeometry(0.35, 0.45, 4.5, 6),
        new THREE.MeshStandardMaterial({ color: '#6b21a8', flatShading: true })
      );
      pillar.position.set(px, 2.2, pz);
      scene.add(pillar);

      const crystal = new THREE.Mesh(
        new THREE.OctahedronGeometry(0.55, 0),
        new THREE.MeshStandardMaterial({
          color: '#c084fc',
          emissive: '#9333ea',
          emissiveIntensity: 1.0,
        })
      );
      crystal.position.set(px, 4.8, pz);
      scene.add(crystal);

      const ptL = new THREE.PointLight('#a855f7', 1.8, 12);
      ptL.position.set(px, 4.8, pz);
      scene.add(ptL);
    }

    // ── Qahramon yuklash ──
    const loader = new GLTFLoader();
    const modelUrl = characterClass?.model || '/models/characters/swordman.glb';
    loader.load(modelUrl, (gltf) => {
      const char = gltf.scene;
      char.scale.setScalar(1.2);
      char.position.set(0, 0, 4);
      char.traverse((n) => {
        if (n.isMesh || n.isSkinnedMesh) {
          n.castShadow = true;
          n.receiveShadow = true;
        }
      });
      scene.add(char);
      charRef.current = char;
      animRef.current = new CharacterAnimator(char);
    });

    // ── Klaviatura Tinglovchilari (WASD / Shift) ──
    const onKeyDown = (e) => {
      const k = e.key.toLowerCase();
      if (k === 'w' || k === 'arrowup')    keysRef.current.forward = true;
      if (k === 's' || k === 'arrowdown')  keysRef.current.backward = true;
      if (k === 'a' || k === 'arrowleft')  keysRef.current.left = true;
      if (k === 'd' || k === 'arrowright') keysRef.current.right = true;
      if (k === 'shift')                   keysRef.current.shift = true;
      // triggerAttackRef orqali har doim yangi versiyani chaqiramiz
      if (k === ' ' || k === 'enter')      triggerAttackRef.current?.();
    };

    const onKeyUp = (e) => {
      const k = e.key.toLowerCase();
      if (k === 'w' || k === 'arrowup')    keysRef.current.forward = false;
      if (k === 's' || k === 'arrowdown')  keysRef.current.backward = false;
      if (k === 'a' || k === 'arrowleft')  keysRef.current.left = false;
      if (k === 'd' || k === 'arrowright') keysRef.current.right = false;
      if (k === 'shift')                   keysRef.current.shift = false;
    };

    window.addEventListener('keydown', onKeyDown);
    window.addEventListener('keyup', onKeyUp);

    // ── Kamera burish (Mouse — desktop, Touch — mobil o'ng tomon) ──
    const onMouseDown = (e) => {
      cameraOrbit.current = true;
      camLastX.current = e.clientX;
    };
    const onMouseUp = () => {
      cameraOrbit.current = false;
    };
    const onMouseMove = (e) => {
      if (!cameraOrbit.current) return;
      cameraYaw.current -= (e.clientX - camLastX.current) * 0.007;
      camLastX.current = e.clientX;
    };

    // Touch kamera orbit — faqat window levelda (canvas-da EMAS)
    // Joystik chap tomonda (< 50%) => u yerda orbit yo'q
    const onWindowTouchStart = (e) => {
      // Joystik hududi emas va faqat 1 ta barmoq bilan
      const t = e.changedTouches[0];
      if (t.clientX < window.innerWidth * 0.5) return; // chap = joystik
      if (e.touches.length === 1) {
        cameraOrbit.current = true;
        camLastX.current = t.clientX;
      }
    };
    const onWindowTouchMove = (e) => {
      if (!cameraOrbit.current) return;
      const t = e.changedTouches[0];
      cameraYaw.current -= (t.clientX - camLastX.current) * 0.008;
      camLastX.current = t.clientX;
    };
    const onWindowTouchEnd = () => {
      cameraOrbit.current = false;
    };

    // Canvas-da FAQAT mouse (desktop) orbit
    renderer.domElement.addEventListener('mousedown', onMouseDown);
    window.addEventListener('mouseup', onMouseUp);
    window.addEventListener('mousemove', onMouseMove);
    // Touch — window dan, canvas-dan EMAS (joystik bilan conflict bo'lmasin)
    window.addEventListener('touchstart', onWindowTouchStart, { passive: true });
    window.addEventListener('touchmove', onWindowTouchMove, { passive: true });
    window.addEventListener('touchend', onWindowTouchEnd);

    // Resize
    const onResize = () => {
      camera.aspect = container.clientWidth / container.clientHeight;
      camera.updateProjectionMatrix();
      renderer.setSize(container.clientWidth, container.clientHeight);
    };
    window.addEventListener('resize', onResize);

    // ── Animation Loop ──
    const animate = () => {
      animIdRef.current = requestAnimationFrame(animate);
      const delta = Math.min(clockRef.current.getDelta(), 0.08);

      // Kristallar aylanishi
      scene.children.forEach((c) => {
        if (c.geometry?.type === 'OctahedronGeometry') c.rotation.y += delta * 1.5;
      });

      // Mana regeneratsiyasi
      const mRegen = playerManaRegen(playerLevel, characterClass);
      if (playerManaRef.current < maxManaVal) {
        playerManaRef.current = Math.min(maxManaVal, playerManaRef.current + mRegen * delta);
        setPlayerMana(Math.round(playerManaRef.current));
      }

      const char = charRef.current;
      if (char) {
        // ── O'yinchini Boshqarish (Harakat: Joystik yoki WASD) ──
        let moveX = 0;
        let moveZ = 0;
        const keys = keysRef.current;
        const analog = analogRef.current;

        const sinY = Math.sin(cameraYaw.current);
        const cosY = Math.cos(cameraYaw.current);

        if (analog.active) {
          const ax = analog.x; // -1 (chap) .. +1 (o'ng)
          const ay = analog.y; // -1 (oldinga) .. +1 (orqaga)
          moveX = sinY * (-ay) + cosY * (-ax);
          moveZ = cosY * (-ay) - sinY * (-ax);
        } else {
          if (keys.forward)  { moveX += sinY; moveZ += cosY; }
          if (keys.backward) { moveX -= sinY; moveZ -= cosY; }
          if (keys.left)     { moveX += cosY; moveZ -= sinY; }
          if (keys.right)    { moveX -= cosY; moveZ += sinY; }
        }

        const len = Math.sqrt(moveX * moveX + moveZ * moveZ);
        const isMoving = len > 0.01;
        const baseSpeed = characterClass?.speed || 5.2;
        const isRunning = keys.shift || (analog.active && Math.sqrt(analog.x**2 + analog.y**2) > 0.8);
        const moveSpeed = isRunning ? baseSpeed * 1.45 : baseSpeed;

        // O'yinchi harakati (yuklanish yoki mag'lubiyat bo'lmagan barcha paytda ishlaydi)
        if (isMoving && phaseRef.current !== 'loading' && phaseRef.current !== 'defeat') {
          const step = moveSpeed * delta;
          char.position.x += (moveX / len) * step;
          char.position.z += (moveZ / len) * step;

          // Arena chegarasi (Radius: 20)
          const distFromCenter = Math.sqrt(char.position.x ** 2 + char.position.z ** 2);
          if (distFromCenter > 20) {
            const angle = Math.atan2(char.position.z, char.position.x);
            char.position.x = Math.cos(angle) * 20;
            char.position.z = Math.sin(angle) * 20;
          }

          char.rotation.y = Math.atan2(moveX, moveZ);
        }

        // Animator yangilash — o'lim animatsiyasi ham shu yerda ishlaydi
        if (animRef.current) {
          const dying = animRef.current.isDying;
          // O'lim paytida harakat bekor — faqat animator update
          animRef.current.update(delta, dying ? false : isMoving, dying ? 0 : (isMoving ? moveSpeed : 0));
        }

        // Kamera ergashishi
        const camDist = 7.5;
        const camH = 3.8;
        const cx = char.position.x - Math.sin(cameraYaw.current) * camDist;
        const cz = char.position.z - Math.cos(cameraYaw.current) * camDist;
        camera.position.set(cx, char.position.y + camH, cz);
        camera.lookAt(char.position.x, char.position.y + 1.4, char.position.z);

        // Mahluqlar AI yangilash
        if (phaseRef.current === 'fighting') {
          updateSkeletonsAI(delta, char);
        }
      }

      renderer.render(scene, camera);
    };
    animate();

    initBattle();

    return () => {
      cancelAnimationFrame(animIdRef.current);
      window.removeEventListener('keydown', onKeyDown);
      window.removeEventListener('keyup', onKeyUp);
      renderer.domElement.removeEventListener('mousedown', onMouseDown);
      window.removeEventListener('mouseup', onMouseUp);
      window.removeEventListener('mousemove', onMouseMove);
      window.removeEventListener('touchstart', onWindowTouchStart);
      window.removeEventListener('touchmove', onWindowTouchMove);
      window.removeEventListener('touchend', onWindowTouchEnd);
      window.removeEventListener('resize', onResize);
      if (container.contains(renderer.domElement)) container.removeChild(renderer.domElement);
      renderer.dispose();
    };
  }, []);

  // ─── Mahluqlar AI va Hujum Mantiqi ───────────────────────────────────────
  const updateSkeletonsAI = (delta, char) => {
    let allDead = true;

    enemiesRef.current.forEach((enemy) => {
      if (enemy.isDead) {
        enemy.deathTimer += delta;
        enemy.model.position.y -= delta * 1.5;
        enemy.model.scale.setScalar(Math.max(0, enemy.model.scale.x - delta * 0.8));
        if (enemy.deathTimer > 1.4) {
          sceneRef.current?.remove(enemy.model);
        }
        return;
      }

      allDead = false;
      const dx = char.position.x - enemy.model.position.x;
      const dz = char.position.z - enemy.model.position.z;
      const dist = Math.sqrt(dx * dx + dz * dz);

      enemy.model.rotation.y = Math.atan2(dx, dz);

      if (enemy.model.userData.aura) {
        enemy.model.userData.aura.rotation.y += delta * 2;
      }

      if (dist > enemy.attackRange) {
        const step = enemy.speed * delta;
        enemy.model.position.x += (dx / dist) * step;
        enemy.model.position.z += (dz / dist) * step;

        const edist = Math.sqrt(enemy.model.position.x ** 2 + enemy.model.position.z ** 2);
        if (edist > 20.5) {
          const ea = Math.atan2(enemy.model.position.z, enemy.model.position.x);
          enemy.model.position.x = Math.cos(ea) * 20.5;
          enemy.model.position.z = Math.sin(ea) * 20.5;
        }

        enemy.animator.update(delta, true, enemy.speed);
      } else {
        enemy.animator.update(delta, false, 0);

        enemy.attackTimer -= delta;
        if (enemy.attackTimer <= 0) {
          enemy.attackTimer = enemy.attackSpeed;
          enemy.animator.playAttack();

          const dmg = enemy.damage;
          playerHpRef.current = Math.max(0, Math.round(playerHpRef.current - dmg));
          setPlayerHp(playerHpRef.current);
          sounds.playSFX('enemy_hit');

          if (playerHpRef.current <= 0) {
            handleDefeat();
          }
        }
      }
    });

    if (allDead && phaseRef.current === 'fighting' && enemiesRef.current.length > 0) {
      handleWaveClear();
    }
  };

  // ─── To'lqinni maydonga joylash ──────────────────────────────────────────
  const spawnWave = useCallback(async (monsters, waveN) => {
    enemiesRef.current.forEach((e) => sceneRef.current?.remove(e.model));
    enemiesRef.current = [];

    const arenaR = 17;
    for (let idx = 0; idx < monsters.length; idx++) {
      const mon = monsters[idx];
      const angle = (idx / monsters.length) * Math.PI * 2;
      const r = arenaR * (0.75 + Math.random() * 0.25);

      const enemyObj = await createSkeletonEnemy(mon);
      enemyObj.model.position.set(Math.cos(angle) * r, 0, Math.sin(angle) * r);
      sceneRef.current?.add(enemyObj.model);
      enemiesRef.current.push(enemyObj);
    }

    waveNumRef.current = waveN;
    setWaveNum(waveN);
    setWaveMessage(`⚔️ ${waveN}-to'lqin! ${monsters.length} ta dushman paydo bo'ldi!`);
    setTimeout(() => setWaveMessage(''), 2500);
    phaseRef.current = 'fighting';
    setBattlePhase('fighting');
  }, []);

  // ─── Jangni Boshlash ─────────────────────────────────────────────────────
  const initBattle = useCallback(async () => {
    setBattlePhase('loading');
    phaseRef.current = 'loading';
    const portalId = portal?.portal_id ?? portal?.id;
    if (!portalId) {
      console.error('Portal ID topilmadi:', portal);
      onFlee();
      return;
    }

    const res = await startBattle(portalId);
    if (res?.battle_id) {
      battleIdRef.current = res.battle_id;
      wavesTotalRef.current = res.waves_total;
      setBattleId(res.battle_id);
      setWavesTotal(res.waves_total);

      playerHpRef.current = maxHpVal;
      setPlayerHp(maxHpVal);

      setWaveMessage(`🌀 ${res.portal_name} portali ochildi!`);
      setTimeout(() => spawnWave(res.monsters, 1), 1200);
    } else {
      console.warn('Jang boshlanmadi:', res);
      onFlee();
    }
  }, [portal, spawnWave, onFlee, maxHpVal]);

  // ─── Qahramon Hujumi (Attack) ────────────────────────────────────────────
  const triggerAttack = useCallback(() => {
    if (phaseRef.current !== 'fighting' || attackCdRef.current) return;
    if (playerManaRef.current < manaCost) {
      sounds.playSFX('click');
      return;
    }

    playerManaRef.current = Math.max(0, playerManaRef.current - manaCost);
    setPlayerMana(Math.round(playerManaRef.current));

    attackCdRef.current = true;
    setAttackCooldown(true);
    setTimeout(() => {
      attackCdRef.current = false;
      setAttackCooldown(false);
    }, 450);

    if (animRef.current) {
      animRef.current.playAttack();
    }
    sounds.playSFX('swing');

    const char = charRef.current;
    if (!char) return;

    const hitRange = characterClass?.id === 'mage' || characterClass?.id === 'ranger' ? 12.0 : 3.4;
    const dmg = Math.round(playerDamage(characterClass, playerLevel) * PORTAL_BUFF);

    enemiesRef.current.forEach((enemy) => {
      if (enemy.isDead) return;
      const dx = enemy.model.position.x - char.position.x;
      const dz = enemy.model.position.z - char.position.z;
      const dist = Math.sqrt(dx * dx + dz * dz);

      if (dist <= hitRange) {
        enemy.currentHp = Math.max(0, enemy.currentHp - dmg);
        updateEnemyHpBar(enemy);
        sounds.playSFX('enemy_hit');

        enemy.model.traverse((n) => {
          if (n.isMesh && n.material) {
            const orig = n.material.color.getHex();
            n.material.color.set('#ffffff');
            setTimeout(() => { if (n.material) n.material.color.setHex(orig); }, 120);
          }
        });

        if (enemy.currentHp <= 0) {
          enemy.isDead = true;
          totalXpRef.current += enemy.monster.xp || 30;
          totalCoinsRef.current += enemy.monster.coins || 10;
          totalKillsRef.current += 1;
          setTotalXp(totalXpRef.current);
          setTotalCoins(totalCoinsRef.current);
          setTotalKills(totalKillsRef.current);
          sounds.playSFX('enemy_death');
        }
      }
    });
  }, [characterClass, playerLevel, manaCost]);

  // triggerAttackRef — useEffect closure-dagi stale muammoni oldini oladi
  triggerAttackRef.current = triggerAttack;

  // ─── To'lqin Yakunlanishi ────────────────────────────────────────────────
  const handleWaveClear = useCallback(async () => {
    phaseRef.current = 'wave_clear';
    setBattlePhase('wave_clear');
    setWaveMessage(`✨ To'lqin tozalindi!`);
    sounds.playSFX('craft_success');

    if (waveNumRef.current >= wavesTotalRef.current) {
      // Barcha to'lqinlar va Boss mag'lub etildi!
      setTimeout(() => handleVictory(), 1600);
    } else {
      const res = await nextWave({
        battle_id: battleIdRef.current,
        wave_xp: 0,
        wave_coins: 0,
        wave_kills: 0,
      });

      if (res?.monsters) {
        setTimeout(() => {
          setWaveMessage('');
          spawnWave(res.monsters, res.current_wave);
        }, 2200);
      } else {
        setTimeout(() => handleVictory(), 1600);
      }
    }
  }, [spawnWave]);

  // ─── 1-BOSQICH: Boss Yengildi — Sandiq Paydo Bo'ladi ─────────────────────
  const handleVictory = useCallback(async () => {
    phaseRef.current = 'chest_ready';
    setBattlePhase('chest_ready');
    setWaveMessage('👑 BOSS YENGILDI! Xazina Sandig\'i paydo bo\'ldi!');
    sounds.playSFX('craft_success');
  }, []);

  // ─── 2-BOSQICH: Foydalanuvchi Sandiqni Ochadi ───────────────────────────
  const handleOpenChest = async () => {
    if (openingChest) return;
    setOpeningChest(true);
    sounds.playSFX('chest_open');

    const res = await completeBattle({
      battle_id: battleIdRef.current,
      total_xp: totalXpRef.current,
      total_coins: totalCoinsRef.current,
      total_kills: totalKillsRef.current,
    });

    setOpeningChest(false);
    if (res?.success) {
      setChestRewards(res.chest_rewards || []);
      setResultData(res);
      phaseRef.current = 'chest_opened';
      setBattlePhase('chest_opened');
      sounds.playSFX('craft_success');
    }
  };

  // ─── Mag'lubiyat ─────────────────────────────────────────────────────────
  const handleDefeat = useCallback(async () => {
    if (phaseRef.current === 'defeat' || phaseRef.current === 'chest_opened') return;
    phaseRef.current = 'defeat';
    setBattlePhase('defeat');
    sounds.playSFX('defeat');

    // ── Teleport o'lim effekti ──────────────────────────────────────────────
    const char = charRef.current;
    const scene = sceneRef.current;

    if (char && scene && animRef.current) {
      // 1) Portal halqa (torus) — qahramon atrofida paydo bo'ladi
      const portalRing = new THREE.Mesh(
        new THREE.TorusGeometry(1.2, 0.12, 12, 48),
        new THREE.MeshStandardMaterial({
          color: '#818cf8',
          emissive: '#6366f1',
          emissiveIntensity: 3.5,
          transparent: true,
          opacity: 0.9,
        })
      );
      portalRing.position.copy(char.position);
      portalRing.position.y += 0.1;
      portalRing.rotation.x = Math.PI / 2;
      scene.add(portalRing);

      // 2) Portal yoritgichi
      const portalLight = new THREE.PointLight('#818cf8', 8, 10);
      portalLight.position.copy(char.position);
      portalLight.position.y += 1.0;
      scene.add(portalLight);

      // 3) Uchayotgan particle-lar (12 ta kichik shar)
      const particles = [];
      for (let i = 0; i < 12; i++) {
        const pMesh = new THREE.Mesh(
          new THREE.SphereGeometry(0.07, 6, 6),
          new THREE.MeshStandardMaterial({
            color: '#c7d2fe',
            emissive: '#818cf8',
            emissiveIntensity: 4,
            transparent: true,
            opacity: 1,
          })
        );
        const angle = (i / 12) * Math.PI * 2;
        pMesh.position.set(
          char.position.x + Math.cos(angle) * 1.2,
          char.position.y + 0.1,
          char.position.z + Math.sin(angle) * 1.2
        );
        pMesh.userData.angle = angle;
        pMesh.userData.speed = 0.8 + Math.random() * 0.5;
        pMesh.userData.riseSpeed = 1.2 + Math.random() * 0.8;
        scene.add(pMesh);
        particles.push(pMesh);
      }

      // 4) Effekt animatsiyasi (1.8 sek davomida update qilamiz)
      const startTime = performance.now();
      const EFFECT_DURATION = 1800;
      const animateEffect = () => {
        const elapsed = performance.now() - startTime;
        const t = Math.min(1, elapsed / EFFECT_DURATION);

        // Halqa kengayadi va yuqoriga ko'tariladi
        const ringScale = 1 + t * 2.5;
        portalRing.scale.set(ringScale, ringScale, ringScale);
        portalRing.position.y = char.position.y + 0.1 + t * 3.0;
        portalRing.material.opacity = Math.max(0, 0.9 - t * 1.1);
        portalRing.rotation.z += 0.04;

        // Yoritgich intensivligi o'zgaradi
        portalLight.intensity = Math.max(0, 8 * (1 - t));
        portalLight.position.y = char.position.y + 1.0 + t * 3.0;

        // Particle-lar spiral bo'ylab ko'tariladi
        particles.forEach((p) => {
          p.userData.angle += p.userData.speed * 0.04;
          const r = 1.2 + t * 0.8;
          p.position.x = char.position.x + Math.cos(p.userData.angle) * r;
          p.position.z = char.position.z + Math.sin(p.userData.angle) * r;
          p.position.y = char.position.y + t * p.userData.riseSpeed * 3.5;
          p.material.opacity = Math.max(0, 1 - t * 1.3);
        });

        if (t < 1) {
          requestAnimationFrame(animateEffect);
        } else {
          // Tozalash
          scene.remove(portalRing);
          scene.remove(portalLight);
          particles.forEach((p) => scene.remove(p));
        }
      };
      requestAnimationFrame(animateEffect);

      // 5) Qahramon animatsiyasi — tiz cho'kib teleport
      animRef.current.playDeath(() => {
        // Animatsiya tugagach model ko'rinmaydi
        if (charRef.current) charRef.current.visible = false;
      });
    }

    // Backend-ga yuborish
    const res = await fleeBattle({
      battle_id: battleIdRef.current,
      partial_xp: Math.round(totalXpRef.current * 0.3),
      partial_coins: Math.round(totalCoinsRef.current * 0.3),
      partial_kills: totalKillsRef.current,
    });

    setResultData({
      defeat: true,
      saved_xp: res?.saved_xp || Math.round(totalXpRef.current * 0.3),
      saved_coins: res?.saved_coins || Math.round(totalCoinsRef.current * 0.3),
      kills: totalKillsRef.current,
    });
  }, []);

  // ── UI Ko'rsatkichlar ──
  const hpPct = Math.max(0, Math.min(100, (playerHp / maxHpVal) * 100));
  const manaPct = Math.max(0, Math.min(100, (playerMana / maxManaVal) * 100));
  const hpColor = hpPct > 55 ? '#22c55e' : hpPct > 25 ? '#f59e0b' : '#ef4444';
  const hasMana = playerMana >= manaCost;

  return (
    <div className="fixed inset-0 z-50 flex flex-col bg-slate-950 select-none">
      {/* 3D Canvas */}
      <div ref={mountRef} className="absolute inset-0" />

      {/* ── HUD Overlay ── */}
      <div className="relative z-10 pointer-events-none flex flex-col justify-between h-full p-3 sm:p-4">
        {/* Yuqori Panel */}
        <div className="flex items-center justify-between gap-2 pointer-events-auto">
          {/* Jon va Mana */}
          <div className="bg-slate-900/90 border border-slate-700/80 rounded-2xl px-3.5 py-2 min-w-[170px] shadow-lg backdrop-blur">
            <div className="flex justify-between text-[10px] text-slate-300 font-bold mb-0.5">
              <span>❤️ Jon <span className="ml-1 text-[9px] font-black text-yellow-300 bg-yellow-900/60 border border-yellow-500/60 rounded px-1">⚡+30%</span></span>
              <span style={{ color: hpColor }} className="tabular-nums">
                {playerHp} / {maxHpVal}
              </span>
            </div>
            <div className="w-full h-2 bg-slate-800 rounded-full overflow-hidden mb-1.5">
              <div
                className="h-full rounded-full transition-all duration-200"
                style={{ width: `${hpPct}%`, backgroundColor: hpColor }}
              />
            </div>

            <div className="flex justify-between text-[10px] text-sky-400 font-bold mb-0.5">
              <span>⚡ Mana</span>
              <span className="text-sky-300 tabular-nums">
                {playerMana} / {maxManaVal}
              </span>
            </div>
            <div className="w-full h-1.5 bg-slate-800 rounded-full overflow-hidden">
              <div
                className="h-full rounded-full transition-all duration-200"
                style={{
                  width: `${manaPct}%`,
                  background: 'linear-gradient(90deg, #0284c7 0%, #38bdf8 100%)',
                }}
              />
            </div>
          </div>

          {/* To'lqin Statusi */}
          <div className="bg-slate-900/90 border border-purple-600/80 rounded-2xl px-4 py-2 text-center shadow-lg backdrop-blur">
            <div className="text-[10px] font-black text-purple-300 uppercase tracking-wider">
              ⚔️ To'lqin
            </div>
            <div className="text-xl font-black text-white">
              {waveNum} <span className="text-purple-400 text-xs">/ {wavesTotal}</span>
            </div>
          </div>

          {/* XP & Tanga */}
          <div className="bg-slate-900/90 border border-slate-700/80 rounded-2xl px-3.5 py-2 text-right shadow-lg backdrop-blur">
            <div className="text-xs font-bold text-amber-400">🪙 {totalCoins}</div>
            <div className="text-xs font-bold text-emerald-400 mt-0.5">⭐ {totalXp} XP</div>
            <div className="text-[10px] text-slate-400">💀 {totalKills} o'ldi</div>
          </div>
        </div>

        {/* To'lqin Xabari */}
        {waveMessage && (
          <div className="self-center px-6 py-2.5 bg-purple-900/90 border border-purple-500 rounded-2xl text-white font-black text-xs sm:text-sm shadow-2xl animate-pulse">
            {waveMessage}
          </div>
        )}

        {/* ── Pastki Panel: Virtual Joystik + Hujum + Qochish ── */}
        <div className="flex items-end justify-between pointer-events-auto">
          {/* Virtual Joystik (Mobil analog boshqaruv) */}
          <div className="pointer-events-auto select-none touch-none pb-1 pl-1">
            <Joystick
              size={120}
              dispatchKeys={false}
              onMove={({ x, y, distance }) => {
                analogRef.current = { x, y, active: true };
                keysRef.current.shift = distance > 0.8;
              }}
              onEnd={() => {
                analogRef.current = { x: 0, y: 0, active: false };
                keysRef.current.forward  = false;
                keysRef.current.backward = false;
                keysRef.current.left     = false;
                keysRef.current.right    = false;
                keysRef.current.shift    = false;
              }}
            />
          </div>

          {/* O'rtada: Qochish tugmasi */}
          {battlePhase === 'fighting' && (
            <button
              onClick={() => {
                sounds.playSFX('click');
                handleDefeat();
              }}
              className="px-3.5 py-2.5 bg-slate-800/80 border border-rose-800/80 hover:bg-rose-950/60 rounded-xl text-rose-300 font-bold text-xs transition active:scale-95 shadow"
            >
              🏃 Qoch (30% saqla)
            </button>
          )}

          {/* Hujum Tugmasi */}
          <button
            onPointerDown={triggerAttack}
            disabled={attackCooldown || !hasMana || battlePhase !== 'fighting'}
            className={`w-20 h-20 sm:w-24 sm:h-24 rounded-full border-4 font-black shadow-2xl transition-all active:scale-90 flex flex-col items-center justify-center ${
              !hasMana
                ? 'bg-slate-800 border-slate-700 text-slate-500 opacity-60 cursor-not-allowed'
                : attackCooldown
                ? 'bg-slate-700 border-slate-600 text-slate-400 opacity-70'
                : 'bg-rose-600 border-rose-400 text-white hover:bg-rose-500 shadow-rose-500/40'
            }`}
          >
            <div className="text-xl sm:text-2xl">{attackCooldown ? '⏳' : !hasMana ? '⚡' : '⚔️'}</div>
            <div className="text-[9px] font-bold mt-0.5 leading-none">
              {!hasMana ? 'NO MANA' : 'HUJUM'}
            </div>
            <div className="text-[8px] text-sky-300 mt-0.5">-{manaCost} ⚡</div>
          </button>
        </div>
      </div>

      {/* ── 1-BOSQICH: SANDIQNI OCHISH OYNASI (BOSS YENGILGANDA) ── */}
      {battlePhase === 'chest_ready' && (
        <div className="absolute inset-0 z-50 flex items-center justify-center p-4 bg-black/75 backdrop-blur-md animate-fadeIn">
          <div className="w-full max-w-sm bg-gradient-to-b from-slate-900 to-purple-950/90 border-2 border-amber-400 rounded-3xl p-6 text-white text-center shadow-[0_0_50px_rgba(251,191,36,0.35)]">
            <div className="text-6xl mb-3 animate-bounce">📦</div>
            <span className="px-3 py-1 bg-amber-500/20 text-amber-300 font-black text-[10px] rounded-full uppercase tracking-wider border border-amber-400/40">
              👑 Boss Yengildi!
            </span>
            <h2 className="text-2xl font-black mt-2 text-transparent bg-clip-text bg-gradient-to-r from-amber-300 via-yellow-200 to-amber-400">
              Qadimiy Xazina Sandig'i
            </h2>
            <p className="text-xs text-slate-300 mt-1.5 leading-relaxed">
              Zindon to'liq tozalandi! Nodir qurollar va boyliklarni qo'lga kiritish uchun sandiqni oching:
            </p>

            <div className="bg-slate-900/80 rounded-2xl p-3 my-4 border border-slate-700/80 text-xs">
              <div className="text-slate-400 mb-1">To'plangan o'ljalar:</div>
              <div className="flex justify-around font-black">
                <span className="text-amber-400">🪙 +{totalCoins} Tanga</span>
                <span className="text-emerald-400">⭐ +{totalXp} XP</span>
                <span className="text-purple-400">💀 {totalKills} Mahluq</span>
              </div>
            </div>

            <button
              onClick={handleOpenChest}
              disabled={openingChest}
              className="w-full py-4 bg-gradient-to-r from-amber-500 via-amber-400 to-yellow-400 hover:from-amber-400 hover:to-yellow-300 text-slate-950 font-black text-base rounded-2xl shadow-[0_0_25px_rgba(251,191,36,0.5)] transition active:scale-95 flex items-center justify-center gap-2"
            >
              {openingChest ? (
                <>
                  <div className="w-5 h-5 border-2 border-slate-950 border-t-transparent rounded-full animate-spin" />
                  <span>Sandiq ochilmoqda...</span>
                </>
              ) : (
                <>
                  <span>✨</span>
                  <span>SANDIQNI OCHISH</span>
                  <span>✨</span>
                </>
              )}
            </button>
          </div>
        </div>
      )}

      {/* ── 2-BOSQICH: SANDIQ OCHILDI — ENDI ZINDONDAN CHIQISH MUMKIN ── */}
      {battlePhase === 'chest_opened' && resultData && (
        <div className="absolute inset-0 z-50 flex items-center justify-center p-4 bg-black/85 backdrop-blur-md animate-fadeIn">
          <div className="w-full max-w-sm bg-slate-900/95 border-2 border-purple-500/80 rounded-3xl p-6 text-white text-center shadow-2xl">
            <div className="text-5xl mb-2 animate-pulse">🎉</div>
            <h2 className="text-2xl font-black text-transparent bg-clip-text bg-gradient-to-r from-amber-300 via-emerald-300 to-purple-300">
              Sandiq Muvaffaqiyatli Ochildi!
            </h2>
            <p className="text-xs text-slate-400 mt-0.5">
              Sovg'alar profilingizga va sumkangizga qo'shildi!
            </p>

            {/* Mukofotlar */}
            <div className="grid grid-cols-3 gap-2 my-3">
              <div className="bg-slate-800 rounded-xl p-2">
                <div className="text-amber-400 font-black">
                  {resultData.coins_earned || totalCoins}
                </div>
                <div className="text-slate-400 text-[10px]">🪙 Tanga</div>
              </div>
              <div className="bg-slate-800 rounded-xl p-2">
                <div className="text-emerald-400 font-black">
                  {resultData.xp_earned || totalXp}
                </div>
                <div className="text-slate-400 text-[10px]">⭐ XP</div>
              </div>
              <div className="bg-slate-800 rounded-xl p-2">
                <div className="text-rose-400 font-black">
                  {resultData.kills || totalKills}
                </div>
                <div className="text-slate-400 text-[10px]">💀 O'ldi</div>
              </div>
            </div>

            {/* Sandiq Sovg'alari */}
            {chestRewards.length > 0 ? (
              <div className="mb-4 text-left">
                <div className="text-amber-400 font-bold text-xs mb-1.5 flex items-center gap-1">
                  🎁 Sandiqdan chiqqan buyumlar:
                </div>
                <div className="space-y-1.5 max-h-36 overflow-y-auto pr-1">
                  {chestRewards.map((r, i) => (
                    <div
                      key={i}
                      className="flex items-center justify-between bg-slate-800/90 border border-slate-700 rounded-xl px-3 py-1.5 text-xs shadow-sm"
                    >
                      <div className="flex items-center gap-1.5">
                        <span>⚔️</span>
                        <span className="font-bold text-white truncate max-w-[170px]">{r.item_name}</span>
                      </div>
                      <span className="text-amber-300 font-black">×{r.quantity}</span>
                    </div>
                  ))}
                </div>
              </div>
            ) : (
              <div className="text-xs text-slate-400 bg-slate-800/50 rounded-xl p-2.5 mb-4">
                💎 Qo'shimcha oltin va tajriba olindi!
              </div>
            )}

            {/* Zindondan Chiqish Tugmasi (Faqat sandiq ochilgandan keyin ko'rinadi) */}
            <button
              onClick={() => onBattleEnd(resultData)}
              className="w-full py-3.5 bg-gradient-to-r from-purple-600 via-indigo-600 to-purple-600 hover:from-purple-500 hover:to-indigo-500 rounded-2xl font-black text-white text-sm shadow-[0_0_20px_rgba(168,85,247,0.4)] transition active:scale-95"
            >
              🌍 Zindondan Chiqish (Dunyoga Qaytish)
            </button>
          </div>
        </div>
      )}

      {/* ── MAG'LUBIYAT EKRANI ── */}
      {battlePhase === 'defeat' && resultData && (
        <div className="absolute inset-0 z-50 flex items-center justify-center p-4 bg-black/85 backdrop-blur-md animate-fadeIn">
          <div className="w-full max-w-sm bg-slate-900/95 border-2 border-rose-600/80 rounded-3xl p-6 text-white text-center shadow-2xl">
            <div className="text-5xl mb-2">💀</div>
            <h2 className="text-2xl font-black text-rose-400">Mag'lubiyat!</h2>
            <p className="text-xs text-slate-400 mt-1 mb-4">
              Zindon dushmanlari kuchlilik qildi. Qochib qutulgan o'ljalaringiz:
            </p>
            <div className="grid grid-cols-2 gap-2 mb-4">
              <div className="bg-slate-800 rounded-xl p-2.5">
                <div className="text-amber-400 font-bold">🪙 {resultData.saved_coins || 0}</div>
                <div className="text-slate-400 text-[10px]">Saqlangan Tanga</div>
              </div>
              <div className="bg-slate-800 rounded-xl p-2.5">
                <div className="text-emerald-400 font-bold">⭐ {resultData.saved_xp || 0}</div>
                <div className="text-slate-400 text-[10px]">Saqlangan XP</div>
              </div>
            </div>
            <button
              onClick={() => onBattleEnd(resultData)}
              className="w-full py-3 bg-slate-800 hover:bg-slate-700 text-white font-black text-sm rounded-2xl transition active:scale-95 border border-slate-700"
            >
              🌍 Dunyoga Qaytish
            </button>
          </div>
        </div>
      )}

      {/* ── YUKLANISH EKRANI ── */}
      {battlePhase === 'loading' && (
        <div className="absolute inset-0 z-20 flex flex-col items-center justify-center bg-black/85">
          <div className="w-14 h-14 border-4 border-purple-500 border-t-transparent rounded-full animate-spin mb-4" />
          <p className="text-purple-300 font-bold text-base">{portal?.name}</p>
          <p className="text-slate-400 text-xs mt-1">Skeletlar to'dasi jamlanmoqda...</p>
        </div>
      )}
    </div>
  );
}
