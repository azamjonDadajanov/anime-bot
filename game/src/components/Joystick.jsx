import React, { useRef, useState, useEffect } from 'react';

/**
 * Virtual Analog Joystick Component
 *
 * @param {Function} onMove - ({ x, y, distance, angle }) => void
 *        x: -1.0 (chap) .. +1.0 (o'ng)
 *        y: -1.0 (oldinga) .. +1.0 (orqaga)
 *        distance: 0.0 .. 1.0
 * @param {Function} onEnd  - () => void
 * @param {number} size     - doira diametri (default: 124px)
 * @param {boolean} dispatchKeys - true bo'lsa window ga keydown/keyup ham yuboradi
 */
export default function Joystick({
  onMove,
  onEnd,
  size = 124,
  dispatchKeys = true,
}) {
  const baseRef = useRef(null);
  const [knobPos, setKnobPos] = useState({ x: 0, y: 0 });
  const [isActive, setIsActive] = useState(false);
  const touchIdRef = useRef(null);
  const prevKeysRef = useRef({ w: false, s: false, a: false, d: false, shift: false });

  const radius = size / 2;
  const knobRadius = 26;
  const maxDist = radius - knobRadius; // ~36px

  // Klaviatura hodisalarini simulyatsiya qilish (100% harakat kafolati)
  const syncKeyboard = (nx, ny, dist, active) => {
    if (!dispatchKeys) return;
    const prev = prevKeysRef.current;
    const next = {
      w: active && ny < -0.25,
      s: active && ny > 0.25,
      a: active && nx < -0.25,
      d: active && nx > 0.25,
      shift: active && dist > 0.8,
    };

    const keysList = [
      { key: 'w', oldV: prev.w, newV: next.w },
      { key: 's', oldV: prev.s, newV: next.s },
      { key: 'a', oldV: prev.a, newV: next.a },
      { key: 'd', oldV: prev.d, newV: next.d },
      { key: 'Shift', oldV: prev.shift, newV: next.shift },
    ];

    keysList.forEach(({ key, oldV, newV }) => {
      if (newV && !oldV) {
        window.dispatchEvent(new KeyboardEvent('keydown', { key, bubbles: true }));
      } else if (!newV && oldV) {
        window.dispatchEvent(new KeyboardEvent('keyup', { key, bubbles: true }));
      }
    });

    prevKeysRef.current = next;
  };

  const handleStart = (clientX, clientY, identifier) => {
    touchIdRef.current = identifier;
    setIsActive(true);
    updateFromCoords(clientX, clientY);
  };

  const handleMove = (clientX, clientY) => {
    updateFromCoords(clientX, clientY);
  };

  const handleStop = () => {
    touchIdRef.current = null;
    setIsActive(false);
    setKnobPos({ x: 0, y: 0 });
    syncKeyboard(0, 0, 0, false);
    if (onEnd) onEnd();
  };

  const updateFromCoords = (clientX, clientY) => {
    if (!baseRef.current) return;
    const rect = baseRef.current.getBoundingClientRect();
    const centerX = rect.left + rect.width / 2;
    const centerY = rect.top + rect.height / 2;

    const dx = clientX - centerX;
    const dy = clientY - centerY;
    const dist = Math.sqrt(dx * dx + dy * dy);

    const clampedDist = Math.min(dist, maxDist);
    const angle = Math.atan2(dy, dx);

    const knobX = clampedDist * Math.cos(angle);
    const knobY = clampedDist * Math.sin(angle);

    setKnobPos({ x: knobX, y: knobY });

    const normX = clampedDist > 0 ? knobX / maxDist : 0;
    const normY = clampedDist > 0 ? knobY / maxDist : 0; // -1 = oldinga, +1 = orqaga
    const normDist = clampedDist / maxDist;

    syncKeyboard(normX, normY, normDist, true);

    if (onMove) {
      onMove({
        x: Number(normX.toFixed(3)),
        y: Number(normY.toFixed(3)),
        distance: Number(normDist.toFixed(3)),
        angle,
      });
    }
  };

  // ── Touch hodisalari ──
  const onTouchStart = (e) => {
    e.stopPropagation();
    const t = e.changedTouches[0];
    handleStart(t.clientX, t.clientY, t.identifier);
  };

  const onTouchMove = (e) => {
    e.stopPropagation();
    for (let i = 0; i < e.changedTouches.length; i++) {
      const t = e.changedTouches[i];
      if (t.identifier === touchIdRef.current) {
        handleMove(t.clientX, t.clientY);
        break;
      }
    }
  };

  const onTouchEnd = (e) => {
    e.stopPropagation();
    handleStop();
  };

  // ── Pointer / Mouse hodisalari ──
  const onPointerDown = (e) => {
    if (e.pointerType === 'touch') return; // Touch alohida onTouch bilan ushlanadi
    e.stopPropagation();
    e.currentTarget.setPointerCapture(e.pointerId);
    handleStart(e.clientX, e.clientY, e.pointerId);
  };

  const onPointerMove = (e) => {
    if (e.pointerType === 'touch' || touchIdRef.current !== e.pointerId) return;
    e.stopPropagation();
    handleMove(e.clientX, e.clientY);
  };

  const onPointerUp = (e) => {
    if (e.pointerType === 'touch' || touchIdRef.current !== e.pointerId) return;
    e.stopPropagation();
    handleStop();
  };

  // Komponent o'chirilganda klaviatura tugmalarini tozalash
  useEffect(() => {
    return () => {
      syncKeyboard(0, 0, 0, false);
    };
  }, []);

  return (
    <div
      ref={baseRef}
      onTouchStart={onTouchStart}
      onTouchMove={onTouchMove}
      onTouchEnd={onTouchEnd}
      onTouchCancel={onTouchEnd}
      onPointerDown={onPointerDown}
      onPointerMove={onPointerMove}
      onPointerUp={onPointerUp}
      onPointerCancel={onPointerUp}
      style={{
        width: `${size}px`,
        height: `${size}px`,
        touchAction: 'none',
      }}
      className={`relative rounded-full select-none flex items-center justify-center transition-colors duration-200 cursor-pointer ${
        isActive
          ? 'bg-slate-900/90 border-2 border-amber-400 shadow-[0_0_25px_rgba(251,191,36,0.45)]'
          : 'bg-slate-900/70 border-2 border-slate-600/80 shadow-xl'
      } backdrop-blur-md`}
    >
      {/* 4 ta yo'nalish ko'rsatkichi */}
      <span className="absolute top-1.5 text-[10px] text-slate-400 font-bold opacity-60 pointer-events-none">▲</span>
      <span className="absolute bottom-1.5 text-[10px] text-slate-400 font-bold opacity-60 pointer-events-none">▼</span>
      <span className="absolute left-2 text-[10px] text-slate-400 font-bold opacity-60 pointer-events-none">◀</span>
      <span className="absolute right-2 text-[10px] text-slate-400 font-bold opacity-60 pointer-events-none">▶</span>

      {/* Ichki markaziy chegara doirasi */}
      <div className="w-16 h-16 rounded-full border border-dashed border-slate-700/60 pointer-events-none" />

      {/* Harakatlanuvchi Joystik dastagi (Knob) */}
      <div
        style={{
          transform: `translate(${knobPos.x}px, ${knobPos.y}px)`,
          transition: isActive ? 'none' : 'transform 0.15s cubic-bezier(0.2, 0.8, 0.2, 1)',
          width: `${knobRadius * 2}px`,
          height: `${knobRadius * 2}px`,
        }}
        className={`absolute rounded-full shadow-2xl flex items-center justify-center pointer-events-none ${
          isActive
            ? 'bg-gradient-to-tr from-amber-500 via-amber-400 to-yellow-300 border-2 border-white scale-110 shadow-[0_0_20px_rgba(251,191,36,0.7)]'
            : 'bg-gradient-to-tr from-slate-700 to-slate-600 border border-slate-400/60'
        }`}
      >
        <div
          className={`w-3.5 h-3.5 rounded-full ${
            isActive ? 'bg-slate-950/80' : 'bg-slate-400/60'
          }`}
        />
      </div>
    </div>
  );
}
