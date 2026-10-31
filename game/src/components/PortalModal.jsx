import React, { useState } from 'react';
import { sounds } from '../services/sound';
import { enterPortal } from '../services/api';

export default function PortalModal({ portal, onClose, onEnterBattle, onRewardClaimed }) {
  const [loading, setLoading] = useState(false);

  if (!portal) return null;

  // Shartlar bajarilgan bo'lsa — to'g'ridan jangga
  const handleEnter = () => {
    if (!portal.can_enter) return;
    sounds.playSFX('portal_activate');
    onClose();
    if (onEnterBattle) onEnterBattle(portal);
  };

  const tierColors = {
    D: 'border-emerald-500 bg-emerald-950/80 text-emerald-300',
    C: 'border-blue-500 bg-blue-950/80 text-blue-300',
    B: 'border-purple-500 bg-purple-950/80 text-purple-300',
    A: 'border-amber-500 bg-amber-950/80 text-amber-300',
    S: 'border-rose-500 bg-rose-950/80 text-rose-300',
  };

  const tierWaves = { D: 3, C: 4, B: 5, A: 6, S: 7 };
  const waves = tierWaves[portal.tier] || 3;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 backdrop-blur-sm">
      <div className={`relative w-full max-w-md rounded-2xl border-2 p-6 shadow-2xl ${
        tierColors[portal.tier] || 'border-indigo-500 bg-slate-900/90 text-white'
      }`}>
        {/* Yopish */}
        <button onClick={onClose}
          className="absolute top-4 right-4 w-8 h-8 flex items-center justify-center rounded-full bg-slate-800/80 hover:bg-slate-700 text-slate-300">
          ✕
        </button>

        {/* Sarlavha */}
        <div className="text-center mb-4">
          <span className="inline-block px-3 py-1 text-xs font-black uppercase tracking-wider rounded-full bg-black/40 mb-2">
            Rank {portal.tier} • {waves} To'lqin
          </span>
          <h2 className="text-2xl font-black text-white">{portal.name}</h2>
          <p className="text-sm text-slate-300 mt-1">{portal.description}</p>
        </div>

        {/* Jang info */}
        <div className="bg-black/30 rounded-xl p-3 mb-4 grid grid-cols-3 gap-2 text-center">
          <div>
            <div className="text-lg font-black text-white">{waves}</div>
            <div className="text-[10px] text-slate-400">To'lqin</div>
          </div>
          <div>
            <div className="text-lg font-black text-amber-400">
              {portal.tier === 'S' ? '🐉 Boss' : portal.tier === 'A' ? '😈 Boss' : '👹 Boss'}
            </div>
            <div className="text-[10px] text-slate-400">Oxirgi</div>
          </div>
          <div>
            <div className="text-lg font-black text-purple-400">Sandiq</div>
            <div className="text-[10px] text-slate-400">Mukofot</div>
          </div>
        </div>

        {/* Shartlar */}
        <div className="my-4 space-y-2">
          <p className="text-xs font-bold text-slate-300 uppercase tracking-wider">Ochilish Shartlari:</p>
          {portal.conditions?.map((cond, idx) => (
            <div key={idx} className={`flex items-start space-x-3 p-3 rounded-xl border ${
              cond.is_met
                ? 'bg-emerald-950/40 border-emerald-500/40 text-emerald-200'
                : 'bg-rose-950/40 border-rose-500/40 text-rose-200'
            }`}>
              <span className="text-lg mt-0.5">{cond.is_met ? '✅' : '🔒'}</span>
              <div className="text-xs">
                <p className="font-semibold text-white">{cond.hint}</p>
                <p className="text-slate-400 mt-0.5">
                  Progress: <span className="text-amber-400 font-bold">{cond.current_value}</span> / {cond.target_value}
                </p>
              </div>
            </div>
          ))}
        </div>

        {/* Cooldown */}
        {portal.is_in_cooldown && (
          <div className="p-3 bg-amber-950/50 border border-amber-500/40 rounded-xl text-center text-xs text-amber-300 mb-4">
            ⏳ Portal dam olish rejimida! Qayta kirish: {Math.ceil(portal.cooldown_remaining_sec / 60)} daqiqa
          </div>
        )}

        {/* Jangga kirish tugmasi */}
        <button
          onClick={handleEnter}
          disabled={!portal.can_enter || portal.is_in_cooldown}
          className={`w-full py-3.5 rounded-xl font-black text-sm tracking-wide transition shadow-lg active:scale-95 ${
            portal.can_enter && !portal.is_in_cooldown
              ? 'bg-gradient-to-r from-red-600 via-rose-500 to-orange-500 hover:from-red-500 text-white shadow-red-500/30'
              : 'bg-slate-700 text-slate-400 cursor-not-allowed'
          }`}
        >
          {portal.can_enter && !portal.is_in_cooldown
            ? '⚔️ JANGGA KIRISH!'
            : portal.is_in_cooldown
            ? '⏳ DAM OLISH REJIMIDA'
            : '🔒 SHARTLAR TO\'LIQ EMAS'}
        </button>

        {portal.can_enter && (
          <p className="text-center text-xs text-slate-500 mt-2">
            ⚠️ Jangda o'lsangiz — faqat 30% XP va tanga saqlanadi
          </p>
        )}
      </div>
    </div>
  );
}
