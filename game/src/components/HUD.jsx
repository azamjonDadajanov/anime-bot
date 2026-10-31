import React from 'react';
import { sounds } from '../services/sound';
import { getLevelInfo } from '../config/level';
import Joystick from './Joystick';

export default function HUD({
  player,
  combat,
  stats,
  levelUpMsg,
  onOpenProfile,
  onOpenInventory,
  onChangeCharacter,
  isMuted,
  onToggleMute,
  nearPortal,
  onOpenPortalModal,
}) {
  const triggerKey = (key, isDown) => {
    window.dispatchEvent(
      new KeyboardEvent(isDown ? 'keydown' : 'keyup', { key, bubbles: true })
    );
  };

  const exp = combat?.exp || 0;
  const levelInfo = getLevelInfo(exp);
  const level = combat?.level || levelInfo.level || 1;
  const hp = Math.max(0, Math.round(combat?.hp || 0));
  const maxHp = combat?.maxHp || 100;
  const mana = Math.max(0, Math.round(combat?.mana ?? 100));
  const maxMana = combat?.maxMana || 100;

  const currentExp = combat?.currentExp ?? levelInfo.currentExp;
  const neededExp = combat?.neededExp ?? levelInfo.neededExp;
  const expPct = combat?.progressPct ?? levelInfo.progressPct;

  const hpPct = Math.max(0, Math.min(100, (hp / maxHp) * 100));
  const manaPct = Math.max(0, Math.min(100, (mana / maxMana) * 100));
  const hasMana = mana >= 12;

  return (
    <div className="absolute inset-0 pointer-events-none flex flex-col justify-between p-4 z-20">
      {/* Yuqori Panel */}
      <div className="flex items-center justify-between w-full pointer-events-auto">
        {/* Chap: Qahramon darajasi, joni, manasi va tajribasi — bosilganda Profil Modali */}
        <div
          onClick={() => {
            sounds.playSFX('click');
            onOpenProfile && onOpenProfile();
          }}
          className="flex items-center space-x-3 bg-slate-900/85 backdrop-blur border border-slate-700/80 hover:border-amber-400/80 px-4 py-2.5 rounded-2xl shadow-lg cursor-pointer transition active:scale-95 group"
          title="O'yinchi profilini ochish"
        >
          <div className="w-11 h-11 rounded-xl bg-gradient-to-tr from-amber-500 to-amber-300 flex items-center justify-center text-slate-950 font-black text-base shadow group-hover:scale-105 transition">
            Lv.{level}
          </div>
          <div>
            <div className="flex items-center space-x-2">
              <span className="font-bold text-sm text-white group-hover:text-amber-300 transition">
                {player?.character_class_display || 'Qahramon'}
              </span>
              <span className="text-xs text-amber-400 font-semibold">
                [{player?.username || 'Hunter'}]
              </span>
              <span className="text-[10px] bg-slate-800 text-slate-400 px-1.5 py-0.5 rounded border border-slate-700 group-hover:border-amber-500/50">
                ℹ️ Profil
              </span>
            </div>

            {/* ❤️ JON */}
            <div className="flex items-center space-x-1.5 mt-1">
              <span className="text-[10px] leading-none">❤️</span>
              <div className="w-24 sm:w-32 h-2 bg-slate-800 rounded-full overflow-hidden">
                <div
                  className="h-full transition-all duration-300"
                  style={{
                    width: `${hpPct}%`,
                    background:
                      hpPct > 55 ? '#4ade80' : hpPct > 25 ? '#fbbf24' : '#f87171',
                  }}
                />
              </div>
              <span className="text-[10px] font-bold text-slate-300 tabular-nums">
                {hp}/{maxHp}
              </span>
            </div>

            {/* ⚡ MANA */}
            <div className="flex items-center space-x-1.5 mt-1">
              <span className="text-[10px] leading-none">⚡</span>
              <div className="w-24 sm:w-32 h-2 bg-slate-800 rounded-full overflow-hidden">
                <div
                  className="h-full transition-all duration-200"
                  style={{
                    width: `${manaPct}%`,
                    background: 'linear-gradient(90deg, #0284c7 0%, #38bdf8 100%)',
                  }}
                />
              </div>
              <span className="text-[10px] font-bold text-sky-300 tabular-nums">
                {mana}/{maxMana}
              </span>
            </div>

            {/* ⭐ TAJRIBA (Har darajada ko'proq kerak bo'ladi) */}
            <div className="flex items-center space-x-1.5 mt-1">
              <span className="text-[10px] leading-none">⭐</span>
              <div className="w-24 sm:w-32 h-1.5 bg-slate-800 rounded-full overflow-hidden">
                <div
                  className="h-full bg-amber-400 transition-all duration-300"
                  style={{ width: `${expPct}%` }}
                />
              </div>
              <span className="text-[10px] font-bold text-amber-300 tabular-nums">
                {currentExp}/{neededExp}
              </span>
            </div>
          </div>
        </div>

        {/* O'ng: Tangalar, Kills, Kuch, Kasb almashtirish, Inventar va Ovoz */}
        <div className="flex items-center space-x-2">
          <div className="flex items-center space-x-1.5 bg-slate-900/85 backdrop-blur border border-slate-700/80 px-3 py-2 rounded-2xl shadow-lg text-amber-400 font-bold text-xs sm:text-sm">
            <span>🪙</span>
            <span>{player?.coins?.toLocaleString() || 100}</span>
          </div>

          <div
            className="flex items-center space-x-1.5 bg-slate-900/85 backdrop-blur border border-slate-700/80 px-3 py-2 rounded-2xl shadow-lg text-xs sm:text-sm font-bold"
            title="O'ldirilgan mahluqlar"
          >
            <span>💀</span>
            <span className="text-rose-300">{combat?.kills || 0}</span>
          </div>

          <div
            className="hidden sm:flex items-center space-x-1.5 bg-slate-900/85 backdrop-blur border border-slate-700/80 px-3 py-2 rounded-2xl shadow-lg text-xs sm:text-sm font-bold"
            title="Zarba kuchi (daraja oshgani sari oshadi)"
          >
            <span>⚔️</span>
            <span className="text-rose-300">{stats?.damage || 0}</span>
          </div>

          <button
            onClick={onChangeCharacter}
            className="px-3 py-2 bg-slate-900/85 hover:bg-slate-800 backdrop-blur border border-slate-700/80 rounded-2xl shadow-lg text-xs font-bold text-slate-200 transition active:scale-95 flex items-center space-x-1"
            title="Qahramonni almashtirish"
          >
            <span>🔄</span>
            <span className="hidden sm:inline">Qahramon</span>
          </button>

          <button
            onClick={() => {
              sounds.playSFX('click');
              onOpenInventory();
            }}
            className="w-10 h-10 flex items-center justify-center bg-slate-900/85 hover:bg-slate-800 backdrop-blur border border-slate-700/80 rounded-2xl shadow-lg text-lg transition active:scale-95"
            title="Inventar"
          >
            🎒
          </button>

          <button
            onClick={onToggleMute}
            className="w-10 h-10 flex items-center justify-center bg-slate-900/85 hover:bg-slate-800 backdrop-blur border border-slate-700/80 rounded-2xl shadow-lg text-base transition active:scale-95"
            title="Ovoz"
          >
            {isMuted ? '🔇' : '🔊'}
          </button>
        </div>
      </div>

      {/* Daraja oshdi xabari */}
      {levelUpMsg && (
        <div className="absolute top-24 left-1/2 -translate-x-1/2 animate-bounce-subtle">
          <div className="px-6 py-3 bg-gradient-to-r from-amber-400 to-yellow-200 text-slate-950 font-black rounded-2xl shadow-2xl text-sm border-2 border-white/40">
            {levelUpMsg}
          </div>
        </div>
      )}

      {/* Markaziy: Yaqin atrofdagi portal haqida xabar */}
      {nearPortal && (
        <div className="self-center pointer-events-auto animate-bounce-subtle">
          <button
            onClick={() => {
              sounds.playSFX('click');
              onOpenPortalModal(nearPortal);
            }}
            className="px-6 py-3.5 bg-gradient-to-r from-indigo-600 via-purple-600 to-pink-600 hover:from-indigo-500 hover:to-pink-500 border border-white/30 rounded-2xl shadow-2xl font-black text-white text-sm flex items-center space-x-2 active:scale-95 transition"
          >
            <span className="text-xl">🌌</span>
            <span>{nearPortal.name} [Tekshirish]</span>
          </button>
        </div>
      )}

      {/* Pastki Qism: Mobil Virtual Joystik & Hujum */}
      <div className="flex justify-between items-end w-full">
        {/* Virtual Joystik (Telefonda qulay analog boshqaruv) */}
        <div className="pointer-events-auto select-none touch-none pb-1 pl-1">
          <Joystick
            size={128}
            onMove={({ x, y }) => {
              window.dispatchEvent(
                new CustomEvent('game:joystick', { detail: { x, y, active: true } })
              );
            }}
            onEnd={() => {
              window.dispatchEvent(
                new CustomEvent('game:joystick', { detail: { x: 0, y: 0, active: false } })
              );
            }}
          />
        </div>

        {/* O'ng: Hujum tugmasi + Xarita haqida ma'lumot */}
        <div className="flex flex-col items-end gap-2 pointer-events-auto">
          <button
            onPointerDown={() => {
              if (!hasMana) {
                sounds.playSFX('click');
                return;
              }
              sounds.playSFX('click');
              triggerKey('f', true);
              triggerKey('f', false);
            }}
            disabled={!hasMana}
            className={`w-16 h-16 rounded-full border-2 border-white/30 shadow-2xl text-3xl flex flex-col items-center justify-center select-none active:scale-90 transition ${
              hasMana
                ? 'bg-gradient-to-br from-rose-500 to-red-700 hover:from-rose-400 hover:to-red-600 cursor-pointer'
                : 'bg-slate-800 text-slate-500 border-slate-700 opacity-60 cursor-not-allowed'
            }`}
            title={hasMana ? "Hujum qilish (F / Space)" : "Mana tugadi! Tiklanishini kuting"}
          >
            <span>⚔️</span>
            {!hasMana && <span className="text-[8px] font-black text-sky-400 -mt-1 leading-none">NO MANA</span>}
          </button>
          <div className="bg-slate-900/80 backdrop-blur px-3 py-1.5 rounded-xl border border-slate-800 text-[11px] text-slate-400">
            📍 Joylashuv: <span className="text-amber-300 font-semibold">{Math.round(player?.position?.x || 0)}, {Math.round(player?.position?.z || 0)}</span> (Avto-saqlanadi)
          </div>
        </div>
      </div>
    </div>
  );
}
