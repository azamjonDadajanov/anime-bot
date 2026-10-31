import React from 'react';
import { sounds } from '../services/sound';
import { getLevelInfo, playerMaxMana, playerManaRegen, attackManaCost } from '../config/level';
import { playerMaxHp, playerDamage } from '../config/enemies';

export default function ProfileModal({
  player,
  combat,
  characterClass,
  inventory = [],
  onClose,
  onChangeCharacter,
}) {
  if (!player && !combat) return null;

  const exp = combat?.exp ?? player?.experience ?? 0;
  const levelInfo = getLevelInfo(exp);
  const level = combat?.level ?? player?.level ?? levelInfo.level ?? 1;

  const maxHp = playerMaxHp(level);
  const currentHp = Math.min(maxHp, Math.max(0, Math.round(combat?.hp ?? player?.hp ?? maxHp)));

  const maxMana = playerMaxMana(level, characterClass);
  const currentMana = Math.min(maxMana, Math.max(0, Math.round(combat?.mana ?? maxMana)));
  const manaRegen = playerManaRegen(level, characterClass);
  const manaCost = attackManaCost(characterClass);

  // Inventardan taqilgan bonuslarni hisoblash
  const equippedItems = inventory.filter((i) => i.is_equipped);
  let equipDamageBonus = 0;
  let equipDefenseBonus = 0;
  equippedItems.forEach((item) => {
    equipDamageBonus += Number(item.attributes?.damage_bonus || 0);
    equipDefenseBonus += Number(item.attributes?.defense_bonus || 0);
    if (item.item_type === 'weapon') equipDamageBonus += Math.round(item.power * 0.2);
    if (item.item_type === 'armor') equipDefenseBonus += Math.round(item.power * 0.2);
  });

  const baseDamage = playerDamage(characterClass, level);
  const totalDamage = baseDamage + equipDamageBonus;

  const hpPct = Math.max(0, Math.min(100, (currentHp / maxHp) * 100));
  const manaPct = Math.max(0, Math.min(100, (currentMana / maxMana) * 100));

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/75 backdrop-blur-md animate-fadeIn">
      <div className="relative w-full max-w-lg rounded-3xl bg-slate-900/95 border border-slate-700/80 p-6 text-white shadow-2xl overflow-hidden max-h-[92vh] flex flex-col">
        {/* Dekorativ orqa nur */}
        <div className="absolute -top-20 -right-20 w-44 h-44 bg-purple-600/20 rounded-full blur-3xl pointer-events-none" />
        <div className="absolute -bottom-20 -left-20 w-44 h-44 bg-amber-600/20 rounded-full blur-3xl pointer-events-none" />

        {/* Yopish tugmasi */}
        <button
          onClick={() => {
            sounds.playSFX('click');
            onClose();
          }}
          className="absolute top-4 right-4 z-10 w-9 h-9 flex items-center justify-center rounded-full bg-slate-800/80 hover:bg-slate-700 text-slate-300 transition"
        >
          ✕
        </button>

        {/* Qahramon Sarlavhasi (Header) */}
        <div className="flex items-center space-x-4 pb-4 border-b border-slate-800">
          <div className="w-16 h-16 rounded-2xl bg-gradient-to-tr from-purple-600 via-indigo-600 to-amber-500 p-0.5 shadow-xl flex-shrink-0">
            <div className="w-full h-full bg-slate-950 rounded-[14px] flex items-center justify-center text-3xl">
              {characterClass?.icon || '⚔️'}
            </div>
          </div>

          <div className="flex-1 min-w-0">
            <div className="flex items-center space-x-2">
              <h2 className="text-xl font-black text-white truncate">
                {player?.username || 'Hunter'}
              </h2>
              <span className="px-2 py-0.5 rounded-md bg-amber-500/20 border border-amber-500/40 text-[10px] font-black text-amber-300 uppercase tracking-wider">
                Lv.{level}
              </span>
            </div>

            <p className="text-sm font-bold text-purple-300">
              {characterClass?.name || player?.character_class_display || 'Anime Ovchi'}
            </p>
            <p className="text-xs text-slate-400 truncate mt-0.5">
              {characterClass?.description || 'Afsonaviy artefaktlar qidiruvchisi'}
            </p>
          </div>
        </div>

        {/* Skrollanadigan tanasi */}
        <div className="overflow-y-auto space-y-4 py-4 pr-1 flex-1">
          {/* 🌟 Tajriba (XP) progress */}
          <div className="bg-slate-800/60 rounded-2xl p-3 border border-slate-700/60">
            <div className="flex justify-between items-center text-xs mb-1 font-bold">
              <span className="text-slate-300 flex items-center gap-1">
                ⭐ Tajriba (XP)
              </span>
              <span className="text-amber-400">
                {levelInfo.currentExp} / {levelInfo.neededExp} XP ({Math.round(levelInfo.progressPct)}%)
              </span>
            </div>
            <div className="w-full h-2.5 bg-slate-900 rounded-full overflow-hidden">
              <div
                className="h-full bg-gradient-to-r from-amber-500 to-emerald-400 rounded-full transition-all duration-500"
                style={{ width: `${levelInfo.progressPct}%` }}
              />
            </div>
            <div className="text-[10px] text-slate-400 mt-1 flex justify-between">
              <span>Jami to'plangan: {exp} XP</span>
              <span>Keyingi darajaga: {levelInfo.neededExp - levelInfo.currentExp} XP</span>
            </div>
          </div>

          {/* ❤️ Jon & ⚡ Mana barlari */}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            {/* Jon */}
            <div className="bg-slate-800/60 rounded-2xl p-3 border border-slate-700/60">
              <div className="flex justify-between items-center text-xs mb-1 font-bold">
                <span className="text-rose-400 flex items-center gap-1">❤️ Jon (HP)</span>
                <span className="text-white tabular-nums">{currentHp} / {maxHp}</span>
              </div>
              <div className="w-full h-2 bg-slate-900 rounded-full overflow-hidden">
                <div
                  className="h-full bg-gradient-to-r from-rose-500 to-emerald-400 rounded-full transition-all duration-300"
                  style={{ width: `${hpPct}%` }}
                />
              </div>
              <p className="text-[10px] text-slate-400 mt-1">Har daraja: +25 maksimal jon</p>
            </div>

            {/* Mana */}
            <div className="bg-slate-800/60 rounded-2xl p-3 border border-slate-700/60">
              <div className="flex justify-between items-center text-xs mb-1 font-bold">
                <span className="text-sky-400 flex items-center gap-1">⚡ Mana</span>
                <span className="text-sky-300 tabular-nums">{currentMana} / {maxMana}</span>
              </div>
              <div className="w-full h-2 bg-slate-900 rounded-full overflow-hidden">
                <div
                  className="h-full bg-gradient-to-r from-sky-600 to-cyan-400 rounded-full transition-all duration-300"
                  style={{ width: `${manaPct}%` }}
                />
              </div>
              <p className="text-[10px] text-slate-400 mt-1">Regen: +{manaRegen}/sek | Sarf: -{manaCost}/zarba</p>
            </div>
          </div>

          {/* ⚔️ Jangovar Statlar Grid */}
          <div>
            <h3 className="text-xs font-black uppercase tracking-wider text-slate-400 mb-2">
              Jangovar Ko'rsatkichlar
            </h3>
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
              <div className="bg-slate-800/80 rounded-xl p-2.5 border border-slate-700 text-center">
                <div className="text-[10px] text-slate-400 font-bold">⚔️ Zarba Kuchi</div>
                <div className="text-base font-black text-rose-400 mt-0.5">{totalDamage}</div>
                {equipDamageBonus > 0 && (
                  <div className="text-[9px] text-emerald-400 font-bold">+{equipDamageBonus} quroldan</div>
                )}
              </div>

              <div className="bg-slate-800/80 rounded-xl p-2.5 border border-slate-700 text-center">
                <div className="text-[10px] text-slate-400 font-bold">🛡️ Mudofaa</div>
                <div className="text-base font-black text-blue-400 mt-0.5">
                  {equipDefenseBonus > 0 ? equipDefenseBonus : 10}
                </div>
                <div className="text-[9px] text-slate-400">Zirh / Qalqon</div>
              </div>

              <div className="bg-slate-800/80 rounded-xl p-2.5 border border-slate-700 text-center">
                <div className="text-[10px] text-slate-400 font-bold">🏃 Tezlik</div>
                <div className="text-base font-black text-amber-300 mt-0.5">
                  {characterClass?.speed || 5.2}
                </div>
                <div className="text-[9px] text-slate-400">birlik / sek</div>
              </div>

              <div className="bg-slate-800/80 rounded-xl p-2.5 border border-slate-700 text-center">
                <div className="text-[10px] text-slate-400 font-bold">⚡ Hujum Sarfi</div>
                <div className="text-base font-black text-sky-400 mt-0.5">{manaCost}</div>
                <div className="text-[9px] text-slate-400">mana / zarba</div>
              </div>
            </div>
          </div>

          {/* 🏆 O'yin Yutuqlari */}
          <div>
            <h3 className="text-xs font-black uppercase tracking-wider text-slate-400 mb-2">
              O'yin Yutuqlari & Resurslar
            </h3>
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
              <div className="bg-slate-800/50 rounded-xl p-2 border border-slate-700/60 text-center">
                <div className="text-lg font-black text-amber-400">
                  🪙 {player?.coins ?? 0}
                </div>
                <div className="text-[10px] text-slate-400">Oltin Tanga</div>
              </div>

              <div className="bg-slate-800/50 rounded-xl p-2 border border-slate-700/60 text-center">
                <div className="text-lg font-black text-emerald-400">
                  💀 {combat?.kills ?? player?.kills ?? 0}
                </div>
                <div className="text-[10px] text-slate-400">Mahluq O'ldi</div>
              </div>

              <div className="bg-slate-800/50 rounded-xl p-2 border border-slate-700/60 text-center">
                <div className="text-lg font-black text-purple-400">
                  🌀 {player?.portals_cleared ?? 0}
                </div>
                <div className="text-[10px] text-slate-400">Portal Yengildi</div>
              </div>

              <div className="bg-slate-800/50 rounded-xl p-2 border border-slate-700/60 text-center">
                <div className="text-lg font-black text-cyan-400">
                  📦 {player?.chests_opened ?? 0}
                </div>
                <div className="text-[10px] text-slate-400">Sandiq Ochildi</div>
              </div>
            </div>
          </div>
        </div>

        {/* Pastki Harakatlar */}
        <div className="pt-3 border-t border-slate-800 flex gap-2">
          {onChangeCharacter && (
            <button
              onClick={() => {
                sounds.playSFX('click');
                onClose();
                onChangeCharacter();
              }}
              className="flex-1 py-3 px-4 bg-gradient-to-r from-purple-700 to-indigo-700 hover:from-purple-600 hover:to-indigo-600 rounded-2xl font-black text-white text-xs sm:text-sm transition active:scale-95 shadow-lg flex items-center justify-center gap-1.5"
            >
              🔄 Qahramonni O'zgartirish
            </button>
          )}

          <button
            onClick={() => {
              sounds.playSFX('click');
              onClose();
            }}
            className="py-3 px-5 bg-slate-800 hover:bg-slate-700 rounded-2xl font-bold text-slate-300 text-xs sm:text-sm transition active:scale-95"
          >
            Yopish
          </button>
        </div>
      </div>
    </div>
  );
}
