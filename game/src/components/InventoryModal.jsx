import React, { useState } from 'react';
import { sounds } from '../services/sound';
import { toggleEquipItem } from '../services/api';

const RARITY_THEMES = {
  common: {
    border: 'border-slate-500',
    bg: 'bg-slate-800/80',
    text: 'text-slate-300',
    badge: 'bg-slate-700 text-slate-300',
    label: 'Oddiy',
  },
  uncommon: {
    border: 'border-emerald-500',
    bg: 'bg-emerald-950/40',
    text: 'text-emerald-300',
    badge: 'bg-emerald-900/80 text-emerald-300',
    label: 'Noodatiy',
  },
  rare: {
    border: 'border-blue-500',
    bg: 'bg-blue-950/40',
    text: 'text-blue-300',
    badge: 'bg-blue-900/80 text-blue-300',
    label: 'Kamyob',
  },
  epic: {
    border: 'border-purple-500',
    bg: 'bg-purple-950/40',
    text: 'text-purple-300',
    badge: 'bg-purple-900/80 text-purple-300',
    label: 'Epik',
  },
  legendary: {
    border: 'border-amber-500',
    bg: 'bg-amber-950/40',
    text: 'text-amber-300',
    badge: 'bg-amber-900/80 text-amber-300',
    label: 'Afsonaviy',
  },
  mythic: {
    border: 'border-rose-500',
    bg: 'bg-rose-950/40',
    text: 'text-rose-300',
    badge: 'bg-rose-900/80 text-rose-300',
    label: 'Mifologik',
  },
  divine: {
    border: 'border-yellow-300',
    bg: 'bg-gradient-to-r from-purple-950 to-amber-950',
    text: 'text-yellow-300',
    badge: 'bg-yellow-500/30 text-yellow-300',
    label: 'Ilohiy',
  },
};

export default function InventoryModal({
  inventory: initialInventory = [],
  characterClass,
  onClose,
  onInventoryUpdate,
}) {
  const [inventory, setInventory] = useState(initialInventory);
  const [filterTab, setFilterTab] = useState('recommended'); // recommended | all | equipped
  const [selectedItem, setSelectedItem] = useState(null);
  const [loadingId, setLoadingId] = useState(null);

  const currentClassId = characterClass?.id || 'warrior';

  // Buyum ushbu qahramonga mos keladimi?
  const isRecommendedForClass = (item) => {
    const classTag = item.attributes?.class_tag;
    if (classTag) return classTag === currentClassId;

    // Item code yoki nomiga qarab
    const name = (item.name || '').toLowerCase();
    const code = (item.code || '').toLowerCase();

    if (currentClassId === 'warrior') {
      return name.includes('qilich') || name.includes('bolta') || name.includes('qalqon') ||
             code.includes('sword') || code.includes('axe') || code.includes('shield');
    }
    if (currentClassId === 'mage') {
      return name.includes('xassa') || name.includes('sehr') || name.includes('kitob') || name.includes('amulet') ||
             code.includes('staff') || code.includes('spellbook') || code.includes('wand') || code.includes('mage');
    }
    if (currentClassId === 'ranger') {
      return name.includes('kamon') || name.includes('arbalet') || name.includes('o\'q') ||
             code.includes('bow') || code.includes('crossbow') || code.includes('quiver');
    }
    if (currentClassId === 'rogue') {
      return name.includes('xanjar') || name.includes('soya') || name.includes('bomba') ||
             code.includes('dagger') || code.includes('shadow') || code.includes('knife');
    }
    return true;
  };

  // Taqish yoki yechish (Equip / Unequip)
  const handleToggleEquip = async (item) => {
    sounds.playSFX('click');
    setLoadingId(item.id);

    const res = await toggleEquipItem(item.id, item.item_id);
    setLoadingId(null);

    if (res?.success && res.inventory) {
      setInventory(res.inventory);
      if (selectedItem?.id === item.id) {
        const updated = res.inventory.find((i) => i.id === item.id);
        setSelectedItem(updated || null);
      }
      sounds.playSFX('craft_success');
      onInventoryUpdate && onInventoryUpdate(res.inventory);
    } else {
      // Optimistik yangilash
      const updated = inventory.map((i) => {
        if (i.id === item.id) return { ...i, is_equipped: !i.is_equipped };
        if (i.item_type === item.item_type && !item.is_equipped) {
          return { ...i, is_equipped: false }; // Boshqasini yechish
        }
        return i;
      });
      setInventory(updated);
      sounds.playSFX('craft_success');
      onInventoryUpdate && onInventoryUpdate(updated);
    }
  };

  // Filtrlangan ro'yxat
  const displayedItems = inventory.filter((item) => {
    if (filterTab === 'equipped') return item.is_equipped;
    if (filterTab === 'recommended') return isRecommendedForClass(item);
    return true; // all
  });

  const equippedItems = inventory.filter((i) => i.is_equipped);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/75 backdrop-blur-md animate-fadeIn">
      <div className="relative w-full max-w-2xl rounded-3xl bg-slate-900/95 border border-slate-700/80 p-5 text-white shadow-2xl flex flex-col max-h-[92vh]">
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

        {/* Sarlavha & Qahramon info */}
        <div className="flex items-center space-x-3 pb-3 border-b border-slate-800">
          <div className="text-3xl p-2 bg-slate-800 rounded-2xl">🎒</div>
          <div>
            <div className="flex items-center gap-2">
              <h2 className="text-lg sm:text-xl font-black">Anjomlar va Qurollar Xazinasi</h2>
              <span className="px-2 py-0.5 rounded-full bg-purple-500/20 border border-purple-500/40 text-[10px] font-bold text-purple-300">
                {characterClass?.icon} {characterClass?.name || 'Qahramon'}
              </span>
            </div>
            <p className="text-xs text-slate-400">
              Jami buyumlar: <span className="text-amber-400 font-bold">{inventory.length}</span> ta •
              Taqilgan: <span className="text-emerald-400 font-bold">{equippedItems.length}</span> ta
            </p>
          </div>
        </div>

        {/* Taqilgan Uyalar (Equipped Loadout Bar) */}
        <div className="py-2.5 px-3 my-2 bg-slate-950/70 rounded-2xl border border-slate-800 flex items-center gap-2 overflow-x-auto">
          <span className="text-[10px] font-black uppercase text-slate-400 whitespace-nowrap pl-1">
            Taqilgan:
          </span>

          {equippedItems.length === 0 ? (
            <span className="text-xs text-slate-500 italic">Hech qanday anjom taqilmagan. Quyidan qurol tanlang!</span>
          ) : (
            equippedItems.map((item) => (
              <div
                key={item.id}
                onClick={() => setSelectedItem(item)}
                className="flex items-center gap-1.5 px-2.5 py-1 bg-slate-800/90 border border-emerald-500/60 rounded-xl text-xs cursor-pointer hover:bg-slate-700 transition flex-shrink-0"
              >
                <span>{item.item_type === 'weapon' ? '⚔️' : item.item_type === 'armor' ? '🛡️' : '🔮'}</span>
                <span className="font-bold text-white max-w-[120px] truncate">{item.name}</span>
                <span className="text-emerald-400 text-[10px] font-black">+{item.power}</span>
              </div>
            ))
          )}
        </div>

        {/* Filtr tablari */}
        <div className="flex gap-1.5 border-b border-slate-800 pb-2">
          <button
            onClick={() => setFilterTab('recommended')}
            className={`px-3 py-1.5 rounded-xl text-xs font-bold transition flex items-center gap-1 ${
              filterTab === 'recommended'
                ? 'bg-amber-500 text-slate-950 shadow-md'
                : 'bg-slate-800/80 text-slate-400 hover:text-white'
            }`}
          >
            <span>⭐</span> {characterClass?.name || 'Qahramon'} uchun
          </button>

          <button
            onClick={() => setFilterTab('all')}
            className={`px-3 py-1.5 rounded-xl text-xs font-bold transition ${
              filterTab === 'all'
                ? 'bg-purple-600 text-white shadow-md'
                : 'bg-slate-800/80 text-slate-400 hover:text-white'
            }`}
          >
            Barchasi ({inventory.length})
          </button>

          <button
            onClick={() => setFilterTab('equipped')}
            className={`px-3 py-1.5 rounded-xl text-xs font-bold transition flex items-center gap-1 ${
              filterTab === 'equipped'
                ? 'bg-emerald-600 text-white shadow-md'
                : 'bg-slate-800/80 text-slate-400 hover:text-white'
            }`}
          >
            <span>🛡️</span> Taqilganlar ({equippedItems.length})
          </button>
        </div>

        {/* Buyumlar to'plami (Grid) */}
        <div className="flex-1 overflow-y-auto pr-1 py-3 min-h-[220px]">
          {displayedItems.length === 0 ? (
            <div className="p-8 text-center bg-slate-800/40 rounded-2xl border border-dashed border-slate-700 my-4">
              <span className="text-3xl block mb-2">🧭</span>
              <p className="text-sm text-slate-300 font-bold">Ushbu bo'limda buyumlar yo'q.</p>
              <p className="text-xs text-slate-500 mt-1">
                Portallarni tozalab sandiqdan qurol va zirhlar yutib oling!
              </p>
            </div>
          ) : (
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5">
              {displayedItems.map((item) => {
                const theme = RARITY_THEMES[item.rarity] || RARITY_THEMES.common;
                const isSelected = selectedItem?.id === item.id;
                const isRec = isRecommendedForClass(item);

                return (
                  <div
                    key={item.id}
                    onClick={() => setSelectedItem(item)}
                    className={`relative p-3 rounded-2xl border transition-all duration-200 cursor-pointer flex flex-col justify-between ${
                      item.is_equipped
                        ? 'border-emerald-500 bg-emerald-950/30 ring-1 ring-emerald-500/50'
                        : isSelected
                        ? 'border-amber-400 bg-slate-800 ring-2 ring-amber-400/40 shadow-lg'
                        : `${theme.border} ${theme.bg} hover:border-slate-400`
                    }`}
                  >
                    {/* Taqilgan belgisi */}
                    {item.is_equipped && (
                      <span className="absolute -top-2 -right-2 px-2 py-0.5 bg-emerald-500 text-slate-950 font-black text-[9px] rounded-full uppercase shadow">
                        ✓ Taqilgan
                      </span>
                    )}

                    <div>
                      {/* Yuqori: Tur & Rank & Soni */}
                      <div className="flex items-center justify-between mb-1.5">
                        <span className={`text-[10px] font-black uppercase px-2 py-0.5 rounded-full ${theme.badge}`}>
                          {item.rarity_display || theme.label}
                        </span>

                        <div className="flex items-center gap-1">
                          {isRec && filterTab !== 'recommended' && (
                            <span className="text-[10px] bg-amber-500/20 text-amber-300 px-1.5 py-0.2 rounded font-bold">
                              ★ Mos
                            </span>
                          )}
                          <span className="text-[10px] font-bold bg-black/40 px-1.5 py-0.5 rounded text-slate-300">
                            x{item.quantity}
                          </span>
                        </div>
                      </div>

                      {/* Buyum nomi va quvvati */}
                      <div className="flex items-start justify-between gap-1">
                        <h4 className="font-bold text-sm text-white line-clamp-1">
                          {item.name}
                        </h4>
                      </div>

                      <div className="flex items-center gap-3 mt-1 text-xs">
                        <span className="text-amber-300 font-bold">
                          ⚡ +{item.power} Quvvat
                        </span>
                        <span className="text-slate-400 text-[10px]">
                          {item.item_type === 'weapon' ? '⚔️ Qurol' : item.item_type === 'armor' ? '🛡️ Zirh' : '🔮 Artefakt'}
                        </span>
                      </div>

                      {/* Atributlar */}
                      {item.attributes && Object.keys(item.attributes).length > 0 && (
                        <div className="mt-1.5 text-[10px] text-purple-300 bg-black/30 px-2 py-1 rounded-lg">
                          {Object.entries(item.attributes)
                            .filter(([k]) => k !== 'class_tag')
                            .map(([k, v]) => `${k.replace('_', ' ')}: +${v}`)
                            .join(' • ')}
                        </div>
                      )}
                    </div>

                    {/* Tugma: Taqish / Yechish */}
                    <div className="mt-2.5 pt-2 border-t border-slate-700/50 flex items-center justify-between">
                      <span className="text-[10px] text-slate-400">
                        {item.is_equipped ? 'Hozir ishlatilmoqda' : 'Inventarda mavjud'}
                      </span>

                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          handleToggleEquip(item);
                        }}
                        disabled={loadingId === item.id}
                        className={`px-3 py-1 rounded-xl text-xs font-black transition active:scale-95 ${
                          item.is_equipped
                            ? 'bg-red-900/60 hover:bg-red-800 text-red-200 border border-red-700/60'
                            : 'bg-emerald-600 hover:bg-emerald-500 text-white shadow-md'
                        }`}
                      >
                        {loadingId === item.id ? '...' : item.is_equipped ? 'Yechish' : 'Taqish'}
                      </button>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>

        {/* Pastki: Yopish */}
        <div className="pt-2 border-t border-slate-800 flex justify-end">
          <button
            onClick={() => {
              sounds.playSFX('click');
              onClose();
            }}
            className="w-full sm:w-auto px-6 py-2.5 bg-slate-800 hover:bg-slate-700 font-bold rounded-xl text-sm transition"
          >
            Yopish
          </button>
        </div>
      </div>
    </div>
  );
}
