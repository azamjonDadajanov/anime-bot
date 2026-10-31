import React, { useState } from 'react';
import { loginOrRegister } from '../services/api';

export default function AuthModal({ onLoginSuccess }) {
  const [isRegister, setIsRegister] = useState(false);
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!username.trim() || !password.trim()) {
      setError('Login va parolni to\'ldiring!');
      return;
    }

    setLoading(true);
    setError('');
    const action = isRegister ? 'register' : 'login';
    const res = await loginOrRegister(action, username, password);
    setLoading(false);

    if (res.success) {
      onLoginSuccess && onLoginSuccess(res);
    } else {
      setError(res.error || 'Xatolik yuz berdi!');
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/85 backdrop-blur-md">
      <div className="w-full max-w-sm rounded-3xl bg-slate-900 border border-amber-500/30 p-6 shadow-2xl text-white">
        <div className="text-center mb-6">
          <span className="text-3xl block mb-1">⚔️</span>
          <h2 className="text-2xl font-black text-amber-400">
            {isRegister ? 'Yangi O\'yinchi' : 'Tizimga Kirish'}
          </h2>
          <p className="text-xs text-slate-400 mt-1">
            Qahramoningiz va dunyodagi o'rningiz xavfsiz saqlanadi
          </p>
        </div>

        {error && (
          <div className="mb-4 p-3 bg-rose-950/70 border border-rose-500/50 rounded-xl text-xs text-rose-300 text-center">
            {error}
          </div>
        )}

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-xs font-semibold text-slate-300 mb-1">
              Foydalanuvchi Logini (Username)
            </label>
            <input
              type="text"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              placeholder="Masalan: hunter_ninja"
              className="w-full px-4 py-2.5 rounded-xl bg-slate-800 border border-slate-700 text-white placeholder-slate-500 text-sm focus:outline-none focus:border-amber-400"
            />
          </div>

          <div>
            <label className="block text-xs font-semibold text-slate-300 mb-1">
              Parol
            </label>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="••••••••"
              className="w-full px-4 py-2.5 rounded-xl bg-slate-800 border border-slate-700 text-white placeholder-slate-500 text-sm focus:outline-none focus:border-amber-400"
            />
          </div>

          <button
            type="submit"
            disabled={loading}
            className="w-full py-3 bg-gradient-to-r from-amber-500 to-amber-600 hover:from-amber-400 hover:to-amber-500 text-slate-950 font-black rounded-xl text-sm transition shadow-lg active:scale-95 disabled:opacity-50"
          >
            {loading ? 'Tekshirilmoqda...' : isRegister ? 'Ro\'yxatdan O\'tish' : 'O\'yinga Kirish'}
          </button>
        </form>

        <div className="mt-5 text-center">
          <button
            onClick={() => {
              setIsRegister(!isRegister);
              setError('');
            }}
            className="text-xs text-amber-400 hover:underline"
          >
            {isRegister
              ? 'Akkauntingiz bormi? Tizimga kiring'
              : 'Akkauntingiz yo\'qmi? Yangi ochish'}
          </button>
        </div>
      </div>
    </div>
  );
}
