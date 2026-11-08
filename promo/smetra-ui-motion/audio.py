"""Builds the soundtrack: own minimal 120 BPM bed + synthesized UI SFX placed on the
timeline events (out/events.json) + the ElevenLabs voice, with music ducked under speech.
Also writes the SRT from out/subs.json.  Run: python -I audio.py"""
import json, subprocess, sys, wave
from pathlib import Path
import numpy as np

HERE = Path(__file__).resolve().parent
OUT = HERE / 'out'
FF = sys.argv[1] if len(sys.argv) > 1 else 'ffmpeg'
SR, DUR = 48000, 30.5
N = int(SR * DUR)
BPM, PHASE = 120, 0.2          # half-beat grid fitted to the key clicks
BEAT = 60 / BPM
rng = np.random.default_rng(7)  # fixed seed: deterministic noise
t_all = np.arange(N) / SR


def db(x): return 10 ** (x / 20)


def lp(x, fc):                  # one-pole low-pass
    a = np.exp(-2 * np.pi * fc / SR); y = np.empty_like(x); s = 0.0
    for i, v in enumerate(x): s = (1 - a) * v + a * s; y[i] = s
    return y


def hp(x, fc): return x - lp(x, fc)


def place(buf, sig, t, gain=1.0):
    i = int(round(t * SR))
    if i >= len(buf): return
    j = min(len(buf), i + len(sig)); buf[i:j] += sig[:j - i] * gain


def env_ad(n, a, d):
    k = np.arange(n) / SR
    return np.minimum(1, k / max(a, 1e-4)) * np.exp(-np.maximum(0, k - a) / d)


def midi(m): return 440 * 2 ** ((m - 69) / 12)


# ───────── music bed ─────────
music = np.zeros(N)
chords = [[53, 57, 60, 64], [57, 60, 64, 67], [48, 55, 59, 64], [55, 59, 62, 64]]   # Fmaj7 Am7 Cmaj7 G6
bar = 4 * BEAT
pad = np.zeros(N)
for b in range(int(DUR / (2 * bar)) + 2):
    t0 = PHASE + b * 2 * bar - 2 * bar if b else 0.0
    t0 = PHASE + (b - 1) * 2 * bar
    ch = chords[b % 4]
    n = int(2 * bar * SR * 1.25); k = np.arange(n) / SR
    e = np.minimum(1, k / 0.9) * np.minimum(1, np.maximum(0, (2 * bar * 1.25 - k) / 0.9))
    s = sum(np.sin(2 * np.pi * midi(m) * k * (1 + d)) for m in ch for d in (-0.0018, 0.0021)) / 8
    s += 0.35 * np.sin(2 * np.pi * midi(ch[0] - 12) * k)
    place(pad, s * e, max(0, t0))
music += lp(pad, 1400) * 0.55

kick = np.zeros(N); n = int(0.32 * SR); k = np.arange(n) / SR
kb = np.sin(2 * np.pi * (48 * k + 60 * (1 - np.exp(-k / 0.03)) * 0.03)) * np.exp(-k / 0.12)
hat_n = int(0.05 * SR); hat = hp(rng.standard_normal(hat_n), 6000) * env_ad(hat_n, 0.001, 0.012)
pl = np.zeros(N)
beat_i = 0
while PHASE + beat_i * BEAT < DUR:
    tb = PHASE + beat_i * BEAT
    if 2.1 < tb < 25.9:
        if beat_i % 2 == 0: place(kick, kb, tb, 0.55)
        if tb > 4.1: place(kick, hat, tb + BEAT / 2, 0.06)
    if 8.1 < tb < 25.9:          # soft pluck arpeggio in eighths
        ch = chords[int((tb - PHASE) // (2 * bar)) % 4]
        for h in range(2):
            m = ch[(beat_i * 2 + h) % 4] + 12
            pn = int(0.4 * SR); kk = np.arange(pn) / SR
            place(pl, np.sin(2 * np.pi * midi(m) * kk) * np.exp(-kk / 0.16) * np.minimum(1, kk / 0.004), tb + h * BEAT / 2, 0.09)
    beat_i += 1
music += kick + lp(pl, 3000)
music *= np.clip((DUR - 0.2 - t_all) / 2.2, 0, 1) ** 1.5            # gentle tail, no abrupt cut
music *= np.clip(t_all / 0.6, 0, 1)

# ───────── SFX: soft, close, tactile (ASMR) ─────────
# Everything is low-passed and rounded: no bright beeps, short transients, warm low body.
sfx = np.zeros((N, 2))
def kk(d): n = int(d * SR); return n, np.arange(n) / SR
def bp(x, lo, hi): return lp(hp(x, lo), hi)
def pink(n):
    w = rng.standard_normal(n); f = np.fft.rfft(w); f /= np.sqrt(np.maximum(1, np.arange(len(f)))); return np.fft.irfft(f, n) * 12
def tap():                       # velvet trackpad tap: muted low body + rounded tick
    n, k = kk(0.09)
    body = np.sin(2 * np.pi * 165 * k * (1 - 0.25 * k / 0.09)) * np.exp(-k / 0.022)
    tock = np.sin(2 * np.pi * 780 * k) * np.exp(-k / 0.009)
    tr = lp(rng.standard_normal(n), 2200) * np.exp(-k / 0.003)
    return lp(0.9 * body + 0.35 * tock + 0.5 * tr, 3200)
def key(v):                      # soft tactile keyboard "thock" with a quiet release
    n, k = kk(0.16); f = 128 * (1 + 0.09 * v)
    down = np.sin(2 * np.pi * f * k) * np.exp(-k / 0.018) + 0.45 * bp(rng.standard_normal(n), 900, 3800) * np.exp(-k / 0.0045)
    up = np.zeros(n); r = int((0.075 + 0.02 * v) * SR)
    up[r:] = 0.3 * bp(rng.standard_normal(n - r), 1200, 3600) * np.exp(-k[:n - r] / 0.003)
    return lp(down + up, 4200) * (0.75 + 0.25 * abs(v))
def air(d, lo=250, hi=1400):    # gentle breath of air for transitions
    n, k = kk(d); e = np.sin(np.pi * np.clip(k / d, 0, 1)) ** 2.2
    return bp(pink(n), lo, hi) * e
def bubble():                    # soft bubble pop for the draft appearing
    n, k = kk(0.12); f = 260 + 420 * (1 - np.exp(-k / 0.018))
    return np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-k / 0.035) * np.minimum(1, k / 0.002)
def wood(f):                     # tiny wooden tick for rolling digits
    n, k = kk(0.05)
    return lp(np.sin(2 * np.pi * f * k) * np.exp(-k / 0.006) + 0.3 * lp(rng.standard_normal(n), 3000) * np.exp(-k / 0.002), 3500)
def kalimba(f, d=1.2):           # warm plucked tine: fundamental + soft inharmonic partial
    n, k = kk(d)
    s = np.sin(2 * np.pi * f * k) * np.exp(-k / (0.45 * d)) + 0.18 * np.sin(2 * np.pi * f * 5.4 * k) * np.exp(-k / 0.04)
    return lp(s * np.minimum(1, k / 0.003), 5000)
def paper(d=0.55):               # paper sliding out: band-limited noise with grainy crinkle
    n, k = kk(d); e = np.sin(np.pi * np.clip(k / d, 0, 1)) ** 1.6
    grain = 0.55 + 0.45 * lp(np.abs(rng.standard_normal(n)), 60) / 0.8
    return bp(rng.standard_normal(n), 1100, 5200) * e * grain
def put(sig, t, g, pan=0.0):     # constant-power pan
    a = (pan + 1) * np.pi / 4
    i = int(round(t * SR))
    if i >= N: return
    j = min(N, i + len(sig)); s = sig[:j - i] * g
    sfx[i:j, 0] += s * np.cos(a); sfx[i:j, 1] += s * np.sin(a)
evs = json.load(open(OUT / 'events.json'))
for n_, ev in enumerate(evs):
    t, ty = ev['t'], ev['type']
    v = np.sin(n_ * 12.9898) * 0.5   # deterministic per-event variation
    if ty == 'click': put(tap(), t, db(-15), 0.15)
    elif ty == 'key': put(key(v), t, db(-19), 0.1 * v)
    elif ty == 'tick': put(wood(1700 + 300 * v), t, db(-26), 0.25)
    elif ty == 'whoosh': put(air(ev.get('d', 0.5) + 0.15), t - 0.12, db(-27), -0.1)
    elif ty == 'menu': put(air(0.2, 600, 2600), t - 0.02, db(-29), 0.2); put(tap(), t + 0.01, db(-24), 0.2)
    elif ty == 'pop': put(bubble(), t, db(-21), 0)
    elif ty == 'paper': put(paper(), t, db(-28), -0.05)
    elif ty == 'confirm': put(kalimba(659.3, 0.9), t, db(-25), -0.15); put(kalimba(987.8, 1.0), t + 0.11, db(-27), 0.15)
    elif ty == 'chime':
        for i_, (f, dt) in enumerate([(523.25, 0), (659.3, 0.09), (783.99, 0.18), (1046.5, 0.3)]):
            put(kalimba(f, 2.2), t + dt, db(-24 - 2 * i_), -0.3 + 0.2 * i_)
# small soft room: exponentially decaying noise IR, ~12% wet
ir_n = int(0.45 * SR); ir = lp(rng.standard_normal(ir_n), 3500) * np.exp(-np.arange(ir_n) / SR / 0.11); ir /= np.sqrt(np.sum(ir ** 2))
L = 1 << int(np.ceil(np.log2(N + ir_n)))
for ch in range(2):
    wet = np.fft.irfft(np.fft.rfft(sfx[:, ch], L) * np.fft.rfft(np.roll(ir, ch * 37), L), L)[:N]
    sfx[:, ch] += 0.12 * wet

# ───────── voice ─────────
raw = subprocess.run([FF, '-v', 'error', '-i', str(HERE / 'assets/voice.mp3'), '-ac', '1', '-ar', str(SR), '-f', 'f32le', '-'], capture_output=True, check=True).stdout
voice = np.zeros(N); v = np.frombuffer(raw, np.float32).astype(np.float64)[:N]; voice[:len(v)] = v

# ducking: smoothed speech envelope pulls the music down ~7 dB
envv = np.sqrt(lp(voice ** 2, 6))
duck = 1 - 0.55 * np.clip(envv / 0.05, 0, 1)
duck = lp(duck, 3)
mix_m = music * db(-17) * duck
st = np.stack([voice + mix_m, voice + mix_m], 1) + sfx
pk = np.max(np.abs(st)); st *= min(1.0, db(-1.5) / pk)
mix = st.mean(1)
pcm = (np.clip(st, -1, 1) * 32767).astype('<i2')
with wave.open(str(OUT / 'mix.wav'), 'wb') as w:
    w.setnchannels(2); w.setsampwidth(2); w.setframerate(SR); w.writeframes(pcm.tobytes())
print('peak dBFS', 20 * np.log10(np.max(np.abs(st))), 'sfx peak', 20 * np.log10(np.max(np.abs(sfx))), 'music rms', 20 * np.log10(np.sqrt(np.mean(mix_m ** 2)) + 1e-9),
      'voice rms', 20 * np.log10(np.sqrt(np.mean(voice[voice != 0] ** 2))))

# ───────── SRT ─────────
def ts(x): h = int(x // 3600); m = int(x % 3600 // 60); s = x % 60; return f'{h:02d}:{m:02d}:{int(s):02d},{int(round((s % 1) * 1000)):03d}'
subs = json.load(open(OUT / 'subs.json', encoding='utf8'))
srt = '\n'.join(f'{i}\n{ts(a)} --> {ts(min(b, DUR))}\n{txt}\n' for i, (a, b, txt) in enumerate(subs, 1))
(OUT / 'smetra-ui-motion.srt').write_text(srt, encoding='utf-8')
