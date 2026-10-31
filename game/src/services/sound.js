import { AUDIO_CONFIG } from '../config/audio';

class SoundManager {
  constructor() {
    this.sfx = {};
    this.bgm = null;
    this.isMuted = false;
    this.audioCtx = null;
  }

  playSFX(name) {
    if (this.isMuted) return;
    const url = AUDIO_CONFIG[name.toUpperCase()];
    if (!url) return;

    try {
      const audio = new Audio(url);
      audio.volume = 0.5;
      audio.play().catch(() => {});
    } catch (e) {}
  }

  /**
   * Hujum zarbasi uchun WebAudio bilan generatsiya qilingan "uchib ketish" ovozi.
   * Alohida audio fayl talab qilinmaydi.
   *
   * opts.from  - boshlang'ich chastota (Hz)
   * opts.peak  - oraliq cho'qqi (Hz)
   * opts.to    - yakuniy chastota (Hz)
   * opts.duration - davomiylik (soniya)
   * opts.volume   - balandlik (0..1)
   */
  playSwing({ from = 420, peak = 2800, to = 650, duration = 0.26, volume = 0.3 } = {}) {
    if (this.isMuted) return;
    try {
      const Ctx = window.AudioContext || window.webkitAudioContext;
      if (!Ctx) return;
      if (!this.audioCtx) this.audioCtx = new Ctx();
      const ctx = this.audioCtx;
      if (ctx.state === 'suspended') ctx.resume();

      const now = ctx.currentTime;
      const f1 = Math.max(1, from);
      const f2 = Math.max(f1 + 1, peak);
      const f3 = Math.max(1, to);

      const buffer = ctx.createBuffer(1, Math.floor(ctx.sampleRate * duration), ctx.sampleRate);
      const data = buffer.getChannelData(0);
      for (let i = 0; i < data.length; i++) {
        const decay = 1 - i / data.length;
        data[i] = (Math.random() * 2 - 1) * decay * decay;
      }

      const source = ctx.createBufferSource();
      source.buffer = buffer;

      const filter = ctx.createBiquadFilter();
      filter.type = 'bandpass';
      filter.Q.value = 1.1;
      filter.frequency.setValueAtTime(f1, now);
      filter.frequency.exponentialRampToValueAtTime(f2, now + Math.min(0.09, duration * 0.4));
      filter.frequency.exponentialRampToValueAtTime(f3, now + duration);

      const gain = ctx.createGain();
      gain.gain.setValueAtTime(0.0001, now);
      gain.gain.exponentialRampToValueAtTime(Math.max(0.001, volume), now + 0.04);
      gain.gain.exponentialRampToValueAtTime(0.0001, now + duration);

      source.connect(filter);
      filter.connect(gain);
      gain.connect(ctx.destination);
      source.start(now);
      source.stop(now + duration);
    } catch (e) {}
  }

  playBGM(name = 'BGM_VILLAGE') {
    if (this.isMuted) return;
    const url = AUDIO_CONFIG[name.toUpperCase()];
    if (!url) return;

    if (this.bgm) {
      this.bgm.pause();
    }

    try {
      this.bgm = new Audio(url);
      this.bgm.loop = true;
      this.bgm.volume = 0.35;
      this.bgm.play().catch(() => {
        // Autoplay policy kutadi
      });
    } catch (e) {}
  }

  toggleMute() {
    this.isMuted = !this.isMuted;
    if (this.isMuted && this.bgm) {
      this.bgm.pause();
    } else if (!this.isMuted && this.bgm) {
      this.bgm.play().catch(() => {});
    }
    return this.isMuted;
  }
}

export const sounds = new SoundManager();
