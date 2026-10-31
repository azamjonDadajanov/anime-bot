import React, { useState, useEffect, useRef } from 'react';
import { CHARACTER_CLASSES } from './config/characters';
import { playerDamage, playerMaxHp } from './config/enemies';
import GameCanvas from './world/GameCanvas';
import HUD from './components/HUD';
import PortalModal from './components/PortalModal';
import InventoryModal from './components/InventoryModal';
import ProfileModal from './components/ProfileModal';
import AuthModal from './components/AuthModal';
import BattleArena from './components/BattleArena';
import {
  fetchGameState,
  selectCharacterClass,
  autoAuthTelegram,
  getStoredUser,
  saveCombat,
} from './services/api';
import { getLevelInfo, playerMaxMana } from './config/level';
import { sounds } from './services/sound';
import { markPortalCleared } from './world/portals/portalCycle';

export default function App() {
  const [user, setUser] = useState(null);
  const [gameState, setGameState] = useState(null);
  const [selectedClass, setSelectedClass] = useState(null);
  const [showClassSelect, setShowClassSelect] = useState(false);
  const [inGame, setInGame] = useState(false);
  const [activePortal, setActivePortal] = useState(null);
  const [nearPortal, setNearPortal] = useState(null);
  const [showInventory, setShowInventory] = useState(false);
  const [showProfile, setShowProfile] = useState(false);
  const [isMuted, setIsMuted] = useState(false);
  const [loading, setLoading] = useState(true);
  const [levelUpMsg, setLevelUpMsg] = useState(null);
  // ── Jang rejimi ──
  const [battlePortal, setBattlePortal] = useState(null); // null = dunyo rejimi

  // Jangovar holat (daraja, XP, jon, kills, mahluqlar) — bazaga saqlanadi
  const [combat, setCombat] = useState({
    level: 1,
    exp: 0,
    hp: 100,
    maxHp: 100,
    kills: 0,
    enemy_state: {},
  });
  const pendingRef = useRef({ exp: 0, hp: null, kills: null, enemy_state: null });
  const saveTimerRef = useRef(null);
  const savingRef = useRef(false);

  const flushCombat = async () => {
    if (savingRef.current) {
      if (saveTimerRef.current) clearTimeout(saveTimerRef.current);
      saveTimerRef.current = setTimeout(flushCombat, 1200);
      return;
    }
    const p = pendingRef.current;
    const hasData = p.exp > 0 || p.hp != null || p.kills != null || p.enemy_state != null;
    if (!hasData) return;

    const payload = {
      exp_gained: p.exp,
      hp: p.hp,
      kills: p.kills,
      enemy_state: p.enemy_state,
    };
    pendingRef.current = { exp: 0, hp: null, kills: null, enemy_state: null };

    savingRef.current = true;
    const res = await saveCombat(payload);
    savingRef.current = false;

    if (res?.success) {
      const lvlInfo = getLevelInfo(res.experience);
      setCombat((prev) => ({
        ...prev,
        level: res.level,
        exp: res.experience,
        currentExp: lvlInfo.currentExp,
        neededExp: lvlInfo.neededExp,
        progressPct: lvlInfo.progressPct,
        hp: res.hp,
        maxHp: res.max_hp,
        kills: res.kills,
        enemy_state: res.enemy_state || prev.enemy_state,
      }));
      if (res.leveled_up) {
        sounds.playSFX('craft_success');
        setLevelUpMsg(`🌟 DARAJA ${res.level}! Kuch oshdi!`);
        setTimeout(() => setLevelUpMsg(null), 3200);
      }
    }
  };

  const scheduleCombatSave = (immediate = false) => {
    if (saveTimerRef.current) clearTimeout(saveTimerRef.current);
    if (immediate) {
      flushCombat();
      return;
    }
    saveTimerRef.current = setTimeout(flushCombat, 1500);
  };

  /** GameCanvas dan keladigan jangovar o'zgarishlar (XP, jon, mana, kills, holat) */
  const handleCombatUpdate = (partial) => {
    if (!partial) return;
    const p = pendingRef.current;
    if (partial.exp_gained) p.exp += partial.exp_gained;
    if (partial.hp != null) p.hp = partial.hp;
    if (partial.maxHp != null) p.maxHp = partial.maxHp;
    if (partial.kills != null) p.kills = partial.kills;
    if (partial.enemy_state) p.enemy_state = partial.enemy_state;

    setCombat((prev) => {
      const exp = prev.exp + (partial.exp_gained || 0);
      const lvlInfo = getLevelInfo(exp);
      return {
        ...prev,
        exp,
        level: lvlInfo.level,
        currentExp: lvlInfo.currentExp,
        neededExp: lvlInfo.neededExp,
        progressPct: lvlInfo.progressPct,
        hp: partial.hp != null ? partial.hp : prev.hp,
        maxHp: partial.maxHp != null ? partial.maxHp : prev.maxHp,
        mana: partial.mana != null ? partial.mana : prev.mana,
        maxMana: partial.maxMana != null ? partial.maxMana : prev.maxMana,
        kills: partial.kills != null ? partial.kills : prev.kills,
        enemy_state: partial.enemy_state || prev.enemy_state,
      };
    });

    scheduleCombatSave(Boolean(partial.flush));
  };

  // 1. Dastlabki yuklanish va Avtomatik Auth tekshiruvi
  useEffect(() => {
    async function initAuth() {
      setLoading(true);

      // A) Telegram Mini App tekshiruvi
      const tg = window.Telegram?.WebApp;
      if (tg) {
        tg.ready();
        tg.expand();
      }
      const tgUser = tg?.initDataUnsafe?.user;

      if (tgUser?.id) {
        const authRes = await autoAuthTelegram(tgUser);
        if (authRes.success) {
          setUser(authRes);
          await loadGameState();
          setLoading(false);
          return;
        }
      }

      // B) Saqlangan foydalanuvchi tekshiruvi (localStorage)
      const stored = getStoredUser();
      if (stored) {
        setUser(stored);
        await loadGameState();
      }

      setLoading(false);
    }

    initAuth();
  }, []);

  const loadGameState = async () => {
    const data = await fetchGameState();
    if (data && data.player) {
      setGameState(data);

      // Jangovar holatni bazadan yuklash (daraja, XP, jon, mana, kills, mahluqlar)
      const lvlInfo = getLevelInfo(data.player.experience || 0);
      const lvl = data.player.level || lvlInfo.level || 1;
      setCombat({
        level: lvl,
        exp: data.player.experience || 0,
        currentExp: lvlInfo.currentExp,
        neededExp: lvlInfo.neededExp,
        progressPct: lvlInfo.progressPct,
        hp: data.player.hp || playerMaxHp(lvl),
        maxHp: data.player.max_hp || playerMaxHp(lvl),
        mana: playerMaxMana(lvl, selectedClass),
        maxMana: playerMaxMana(lvl, selectedClass),
        kills: data.player.kills || 0,
        enemy_state: data.player.enemy_state || {},
      });

      // Agar qahramon avval tanlangan bo'lsa, to'g'ridan-to'g'ri o'sha qahramon va joylashuv bilan o'yinga kirish
      if (data.player.character_class) {
        const found = Object.values(CHARACTER_CLASSES).find(
          (c) => c.id === data.player.character_class
        );
        if (found) {
          setSelectedClass(found);
          setInGame(true);
          setShowClassSelect(false);
          sounds.playBGM('BGM_VILLAGE');
          return;
        }
      }

      // Agar qahramon tanlanmagan bo'lsa
      setShowClassSelect(true);
    }
  };

  const handleLoginSuccess = async (loginData) => {
    setUser(loginData);
    await loadGameState();
  };

  const handleSelectClass = async (char) => {
    sounds.playSFX('click');
    setSelectedClass(char);
    setShowClassSelect(false);
    setInGame(true);
    sounds.playBGM('BGM_VILLAGE');

    const res = await selectCharacterClass(char.id);
    if (res.success && gameState) {
      setGameState((prev) => ({
        ...prev,
        player: {
          ...prev.player,
          character_class: char.id,
          character_class_display: res.character_class_display,
        },
      }));
    }
  };

  const handleToggleMute = () => {
    const muted = sounds.toggleMute();
    setIsMuted(muted);
  };

  // ── Portal modal o'rniga to'g'ridan jang boshlash ──
  const handleEnterPortal = (portal) => {
    sounds.playSFX('portal_activate');
    setActivePortal(null);
    setBattlePortal(portal);
  };

  // ── Jang tugagandan keyin dunyoga qaytish ──
  const handleBattleEnd = async (resultData) => {
    setBattlePortal(null);
    if (resultData && !resultData.defeat) {
      markPortalCleared(activePortal?.portal_id ?? battlePortal?.id);
    }
    // Profil ma'lumotlarini yangilash
    const freshData = await fetchGameState();
    if (freshData) {
      setGameState(freshData);
      if (freshData.player) {
        setCombat(prev => ({
          ...prev,
          level: freshData.player.level || prev.level,
          exp: freshData.player.experience || 0,
          kills: freshData.player.kills || prev.kills,
        }));
        if (resultData?.leveled_up) {
          setLevelUpMsg(`🌟 DARAJA ${freshData.player.level}! Kuch oshdi!`);
          setTimeout(() => setLevelUpMsg(null), 3500);
        }
      }
    }
  };

  const handleRewardClaimed = async () => {
    // Yengilgan portal xaritadan butunlay yo'qoladi — keyingisi BOSHQA joyda ochiladi
    if (activePortal?.portal_id != null) {
      markPortalCleared(activePortal.portal_id);
    }
    const freshData = await fetchGameState();
    if (freshData) {
      setGameState(freshData);
    }
  };

  if (loading) {
    return (
      <div className="w-screen h-screen flex flex-col items-center justify-center bg-slate-950 text-white">
        <div className="w-12 h-12 border-4 border-amber-400 border-t-transparent rounded-full animate-spin mb-4" />
        <p className="text-sm font-bold text-amber-300">O'yin yuklanmoqda...</p>
      </div>
    );
  }

  // Agar foydalanuvchi tizimga kirmagan bo'lsa (Login / Register oynasi)
  if (!user) {
    return <AuthModal onLoginSuccess={handleLoginSuccess} />;
  }

  // Agar qahramon tanlash kerak bo'lsa
  if (showClassSelect || !inGame) {
    return (
      <div className="relative z-30 w-full h-full min-h-screen flex flex-col items-center justify-center p-6 bg-slate-950 text-white select-none">
        <div className="text-center max-w-lg mb-8">
          <span className="px-3 py-1 bg-amber-500/20 text-amber-400 font-bold rounded-full text-xs uppercase tracking-wider border border-amber-500/30">
            Open World • Dynamic Portals
          </span>
          <h1 className="text-3xl sm:text-4xl font-black mt-3 text-transparent bg-clip-text bg-gradient-to-r from-amber-300 via-pink-400 to-indigo-300">
            Anime Artifact Hunter
          </h1>
          <p className="text-sm text-slate-300 mt-2">
            Salom, <span className="text-amber-400 font-bold">{user.username}</span>! Qahramoningizni tanlang:
          </p>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 max-w-xl w-full">
          {Object.values(CHARACTER_CLASSES).map((item) => (
            <button
              key={item.id}
              onClick={() => handleSelectClass(item)}
              className="group relative p-5 bg-slate-900/80 hover:bg-slate-800/90 border border-slate-700 hover:border-amber-400 rounded-2xl transition duration-200 text-left flex flex-col justify-between shadow-xl hover:shadow-amber-500/10 active:scale-95"
            >
              <div>
                <div className="flex items-center justify-between mb-2">
                  <span className="text-3xl group-hover:scale-110 transition">{item.icon}</span>
                  <span className="text-xs font-bold px-2 py-0.5 rounded bg-slate-800 text-amber-400 border border-slate-700">
                    Tezlik: {item.speed}
                  </span>
                </div>
                <h3 className="font-bold text-lg text-white group-hover:text-amber-400 transition">
                  {item.name}
                </h3>
                <p className="text-xs text-slate-400 mt-1 leading-relaxed">
                  {item.description}
                </p>
              </div>
              <div className="mt-4 text-xs font-bold text-amber-400 group-hover:translate-x-1 transition flex items-center">
                Tanlash va O'yinga Kirish &rarr;
              </div>
            </button>
          ))}
        </div>
      </div>
    );
  }

  // 3D O'yin Muhiti
  return (
    <div className="relative w-screen h-screen overflow-hidden bg-slate-950 text-white select-none">
      <GameCanvas
        characterClass={selectedClass}
        portals={gameState?.portals || []}
        combat={combat}
        onCombatUpdate={handleCombatUpdate}
        onNearPortal={(portal) => setNearPortal(portal)}
        playerPosition={gameState?.player?.position}
        onPositionUpdate={(pos) => {
          if (gameState?.player) {
            setGameState((prev) => ({
              ...prev,
              player: { ...prev.player, position: pos },
            }));
          }
        }}
      />

      <HUD
        player={gameState?.player}
        combat={combat}
        stats={{ damage: playerDamage(selectedClass, combat.level) }}
        levelUpMsg={levelUpMsg}
        onOpenProfile={() => setShowProfile(true)}
        onOpenInventory={() => setShowInventory(true)}
        onChangeCharacter={() => setShowClassSelect(true)}
        isMuted={isMuted}
        onToggleMute={handleToggleMute}
        nearPortal={nearPortal}
        onOpenPortalModal={(portal) => {
          sounds.playSFX('click');
          setActivePortal(portal);
        }}
      />

      {/* Profil Modal — o'yinchi ma'lumotlari, statlar, yutuqlar */}
      {showProfile && (
        <ProfileModal
          player={gameState?.player}
          combat={combat}
          characterClass={selectedClass}
          inventory={gameState?.inventory || []}
          onClose={() => setShowProfile(false)}
          onChangeCharacter={() => {
            setShowProfile(false);
            setShowClassSelect(true);
          }}
        />
      )}

      {/* Portal Modal — shartlar tekshiruvi, keyin jang boshlanadi */}
      {activePortal && !battlePortal && (
        <PortalModal
          portal={activePortal}
          onClose={() => setActivePortal(null)}
          onEnterBattle={handleEnterPortal}
          onRewardClaimed={handleRewardClaimed}
        />
      )}

      {/* JANG ARENA — Portal ochilganda dunyo o'rniga */}
      {battlePortal && (
        <BattleArena
          portal={battlePortal}
          combat={combat}
          characterClass={selectedClass}
          playerPosition={gameState?.player?.position}
          onBattleEnd={handleBattleEnd}
          onFlee={() => setBattlePortal(null)}
        />
      )}

      {showInventory && (
        <InventoryModal
          inventory={gameState?.inventory || []}
          characterClass={selectedClass}
          onClose={() => setShowInventory(false)}
          onInventoryUpdate={(newInv) => {
            setGameState((prev) => ({ ...prev, inventory: newInv }));
          }}
        />
      )}
    </div>
  );
}
