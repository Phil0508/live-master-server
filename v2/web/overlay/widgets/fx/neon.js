/* 🌈 네온 테두리 — 시그니처가 나오는 동안 화면 가장자리에 빛이 흐른다(옛 overlay.html #neon-overlay 를 그대로 옮겼다).

   - 등급(움직임)은 지금 나오는 시그니처의 **후원 금액**으로(kit.neonTierClass): 흐름 · 듀얼 스윕 · 반짝임 · 점멸 · 파동 · 맥동 · 차징.
   - 색(--nc): 무지개(RAINBOW)면 기준색 하나 + 판 전체 hue-rotate(6초 한 바퀴).
              아니면 시그니처 사진의 대표색(뽑혔으면) → 없으면 조종실 조명 색(옛 syncNeonColor).
   - 속도: --nspd = 조명 속도 × 2초(옛 '한 바퀴' 환산 — 슬라이더 기본 1.5초 → 3초).
   - 🥁 비트 맞춰 점멸(30만 등급만): 음원을 **따로 한 번 더** 받아 디코딩해 박자표만 만들고, 재생 중인 소리의 시각(currentTime)을 보며
     깜빡인다. ⚠️ 재생 중인 <audio> 는 절대 건드리지 않는다 — createMediaElementSource 로 물리면 되돌릴 수 없고, 막히면
     시그니처 소리가 통째로 무음이 된다(방송 사고). 분석이 실패하면 조용히 고정 리듬 점멸(최악이 '예전과 같음').
     박자표는 주소마다 기억(40개 넘으면 비움) · 대기줄 앞 2개를 미리 분석(시작하자마자 박이 맞게) — 옛 것 그대로.
     ?monitor=1 창도 옛 것처럼 분석한다(소리는 안 낸다 — 디코딩만 하고 스피커에 잇지 않는다).

   다른 위젯에 주는 것(stage.provide('neon')) — 시그니처 위젯(signature.js)이 부른다:
     sigPlay(item, audio) → Promise<'rgb(r, g, b)' | null>   재생을 시작했다: 사진 대표색 뽑기 · 비트 맞추기 시작
                                                             (돌려주는 색은 시그니처 카드 테두리 --reac-glow 에도 쓴다 — 옛 applySignatureThemeColor)
     sigEnd()                                                끝났다 · 끊었다: 사진 색 버리기 · 비트 멈추기 */
import { lightsOf, speedOf, reactionLive, headItem, neonTierClass, TIERS, watch } from './kit.js';

const RECT = '<rect class="n-tube n-base" x="22" y="22" width="1036" height="1876" rx="46"';
const HTML = '<div class="neon-layer">'
    // 10만 미만 · 흐름 : 한 줄기가 테두리를 한 바퀴
    + '<svg class="nl-flow" viewBox="0 0 1080 1920">' + RECT + ' style="opacity:0.16"/>'
    +   '<g class="n-comet n-runFull" data-gen="comet" data-shape="rect" data-period="1000"></g></svg>'
    // 10만 · 듀얼 스윕 : 위 중앙에서 갈라져 아래 중앙에서 만난다(좌우 별개 경로라 대칭이 안 틀어진다)
    + '<svg class="nl-sweep" viewBox="0 0 1080 1920">' + RECT + ' style="opacity:0.18"/>'
    +   '<g class="n-comet n-runHalf" data-gen="comet" data-shape="pathR" data-period="500"></g>'
    +   '<g class="n-comet n-runHalf" data-gen="comet" data-shape="pathL" data-period="500"></g></svg>'
    // 20만 · 반짝임
    + '<svg class="nl-spark" viewBox="0 0 1080 1920">' + RECT + '/><g class="n-spark" data-gen="spark"></g></svg>'
    // 30만 · 점멸
    + '<svg class="nl-blink" viewBox="0 0 1080 1920"><g>' + RECT + '/>'
    +   '<rect class="n-tube n-core" x="22" y="22" width="1036" height="1876" rx="46"/></g></svg>'
    // 50만 · 파동 : period 200 → 물결 5개가 같은 간격으로 흐른다
    + '<svg class="nl-wave" viewBox="0 0 1080 1920">' + RECT + ' style="opacity:0.18"/>'
    +   '<g class="n-comet n-runWave" data-gen="comet" data-shape="rect" data-period="200"></g></svg>'
    // 100만 · 맥동
    + '<div class="nl-pulse"><div class="np"></div><div class="np2"></div></div>'
    // 200만 · 차징→폭발
    + '<div class="nl-charge"><svg viewBox="0 0 1080 1920">' + RECT + ' style="opacity:0.12"/>'
    +   '<path class="nchg" pathLength="500" d="M540 1898 H68 A46 46 0 0 1 22 1852 V68 A46 46 0 0 1 68 22 H540"/>'
    +   '<path class="nchg" pathLength="500" d="M540 1898 H1012 A46 46 0 0 0 1058 1852 V68 A46 46 0 0 0 1012 22 H540"/>'
    +   '<path class="nchg nchgc" pathLength="500" d="M540 1898 H68 A46 46 0 0 1 22 1852 V68 A46 46 0 0 1 68 22 H540"/>'
    +   '<path class="nchg nchgc" pathLength="500" d="M540 1898 H1012 A46 46 0 0 0 1058 1852 V68 A46 46 0 0 0 1012 22 H540"/>'
    + '</svg><div class="nboom"></div></div>'
    + '</div>';

// 빛이 달릴 길. rect = 테두리 한 바퀴(pathLength 1000) · pathR / pathL = 위 중앙에서 오른쪽 · 왼쪽으로 내려가 아래 중앙까지(각 500)
const NS = 'http://www.w3.org/2000/svg';
const SHAPES = {
    rect:  { tag: 'rect', plen: 1000, attrs: { x: 22, y: 22, width: 1036, height: 1876, rx: 46 } },
    pathR: { tag: 'path', plen: 500,  attrs: { d: 'M540 22 H1012 A46 46 0 0 1 1058 68 V1852 A46 46 0 0 1 1012 1898 H540' } },
    pathL: { tag: 'path', plen: 500,  attrs: { d: 'M540 22 H68 A46 46 0 0 0 22 68 V1852 A46 46 0 0 0 68 1898 H540' } },
};
const LAYERS = 18;     // 꼬리를 이루는 겹 수(많을수록 계단이 안 보인다)
const TAIL = 240;      // 꼬리 길이(경로 1000 기준)
// 반짝임이 튈 지점들(경로 1000 위의 위치 — 불규칙해야 자연스럽다)
const SPARK_POS = [18, 63, 104, 151, 197, 236, 288, 331, 375, 424, 466, 512, 558, 601, 649, 692, 738, 776, 823, 869, 912, 957];
const RAINBOW_BASE = '#ff1f56';

function shape(name) {
    const s = SHAPES[name] || SHAPES.rect;
    const el = document.createElementNS(NS, s.tag);
    for (const k in s.attrs) el.setAttribute(k, s.attrs[k]);
    el.setAttribute('pathLength', s.plen);    // 길이를 1000/500 으로 맞춰 둔다 → 점선 계산이 단순해진다
    return el;
}

function build(layer) {
    layer.querySelectorAll('[data-gen="comet"]').forEach(g => {
        const period = parseInt(g.dataset.period, 10) || 1000;
        const maxLen = Math.min(TAIL, period * 0.8);
        g.textContent = '';
        for (let i = 1; i <= LAYERS; i++) {
            // 머리 쪽에 층이 촘촘 → 밝고, 꼬리로 갈수록 성겨져 자연스럽게 흐려진다
            const L = Math.max(6, maxLen * Math.pow(i / LAYERS, 1.7));
            const el = shape(g.dataset.shape);
            el.setAttribute('stroke-dasharray', L.toFixed(2) + ' ' + (period - L).toFixed(2));
            el.style.setProperty('--L', L.toFixed(2));
            el.style.stroke = (i <= 2) ? '#ffffff' : 'var(--nc)';   // 맨 앞 2겹만 흰색 = 뜨거운 머리
            el.style.opacity = 0.17;
            g.appendChild(el);
        }
    });
    layer.querySelectorAll('[data-gen="spark"]').forEach(g => {
        g.textContent = '';
        SPARK_POS.forEach((p, i) => {
            const el = shape('rect');
            el.setAttribute('stroke-dasharray', '6 994');                     // 아주 짧은 구슬 하나
            el.setAttribute('stroke-dashoffset', -p);
            el.style.animationDelay = (-(i * 0.37) % 1.6).toFixed(2) + 's';   // 음수 지연 = 처음부터 제각각
            g.appendChild(el);
        });
    });
}

// ── 🎨 사진 대표색(옛 vibrantColorFromImage · boostVibrant 그대로) ──
function vibrantColorFromImage(img) {
    const S = 40;
    const cv = document.createElement('canvas'); cv.width = S; cv.height = S;
    const ctx = cv.getContext('2d');
    ctx.drawImage(img, 0, 0, S, S);
    const data = ctx.getImageData(0, 0, S, S).data;   // CORS 로 막힌 그림이면 여기서 throw
    let wr = 0, wg = 0, wb = 0, wsum = 0, ar = 0, ag = 0, ab = 0, an = 0;
    for (let i = 0; i < data.length; i += 4) {
        const r = data[i], g = data[i + 1], b = data[i + 2], a = data[i + 3];
        if (a < 128) continue;
        ar += r; ag += g; ab += b; an++;
        const mx = Math.max(r, g, b), mn = Math.min(r, g, b);
        const sat = mx === 0 ? 0 : (mx - mn) / mx, lum = mx / 255;
        if (lum < 0.15 || lum > 0.97 || sat < 0.25) continue;   // 너무 어둡 · 밝 · 무채색은 뺀다
        const w = sat * sat;
        wr += r * w; wg += g * w; wb += b * w; wsum += w;
    }
    let r, g, b;
    if (wsum > 0) { r = wr / wsum; g = wg / wsum; b = wb / wsum; }
    else if (an > 0) { r = ar / an; g = ag / an; b = ab / an; }   // 채도 있는 색이 없으면 평균
    else return null;
    return boostVibrant(r, g, b);
}
function boostVibrant(r, g, b) {
    r /= 255; g /= 255; b /= 255;
    const mx = Math.max(r, g, b), mn = Math.min(r, g, b); let h, s, l = (mx + mn) / 2;
    if (mx === mn) { h = s = 0; }
    else {
        const d = mx - mn; s = l > 0.5 ? d / (2 - mx - mn) : d / (mx + mn);
        switch (mx) { case r: h = (g - b) / d + (g < b ? 6 : 0); break; case g: h = (b - r) / d + 2; break; default: h = (r - g) / d + 4; }
        h /= 6;
    }
    s = Math.min(1, s * 1.35 + 0.1);                 // 채도 올리기(네온답게)
    l = Math.min(0.62, Math.max(0.45, l));           // 밝기는 가운데로
    const hue2rgb = (p, q, t) => { if (t < 0) t += 1; if (t > 1) t -= 1; if (t < 1 / 6) return p + (q - p) * 6 * t; if (t < 1 / 2) return q; if (t < 2 / 3) return p + (q - p) * (2 / 3 - t) * 6; return p; };
    let R, G, B;
    if (s === 0) { R = G = B = l; }
    else { const q = l < 0.5 ? l * (1 + s) : l + s - l * s, p = 2 * l - q; R = hue2rgb(p, q, h + 1 / 3); G = hue2rgb(p, q, h); B = hue2rgb(p, q, h - 1 / 3); }
    return { r: Math.round(R * 255), g: Math.round(G * 255), b: Math.round(B * 255) };
}

// ── 🥁 박자표(옛 getBeatMap · detectBeat 그대로) ──
const beatCache = new Map();     // 음원 주소 → Promise<{period, phase, bpm, conf} | null>
let beatCtxObj = null;
function beatCtx() {
    if (beatCtxObj === null) {
        try { beatCtxObj = new (window.AudioContext || window.webkitAudioContext)(); }
        catch (e) { beatCtxObj = false; }
    }
    return beatCtxObj || null;
}
function getBeatMap(url) {
    if (!url) return Promise.resolve(null);
    if (beatCache.has(url)) return beatCache.get(url);
    if (beatCache.size > 40) beatCache.clear();   // 긴 방송에서 쌓이지 않게
    const p = (async () => {
        const ctx = beatCtx();
        if (!ctx) return null;
        // 재생용 소리와 완전히 따로인 사본. CORS 로 막히면 throw → null → 고정 리듬
        const res = await fetch(url, { cache: 'force-cache' });
        if (!res.ok) return null;
        // decodeAudioData 는 소리판(AudioContext)이 멈춰 있어도 된다(재생이 아니라 풀기라서) — 스피커에는 잇지 않는다
        const buf = await ctx.decodeAudioData(await res.arrayBuffer());
        return detectBeat(buf);
    })().catch(() => null);
    beatCache.set(url, p);
    return p;
}
/* 에너지 상승분(온셋) → 자기상관으로 주기 → 격자 위상. 원시 온셋을 그대로 쓰면 화면이 지저분하게 떨리므로 'BPM 격자' 로 붙인다 */
function detectBeat(buf) {
    const HOP = 512;
    const sr = buf.sampleRate;
    const ch = buf.getChannelData(0);
    const ch2 = buf.numberOfChannels > 1 ? buf.getChannelData(1) : null;
    const n = Math.floor(ch.length / HOP);
    if (n < 128) return null;   // 너무 짧은 음원은 주기를 못 잰다

    // 1) 프레임 에너지의 '상승분' 만 남긴다 = 치고 들어오는 순간(드럼)만
    const env = new Float32Array(n);
    let prev = 0, mx = 0;
    for (let i = 0; i < n; i++) {
        let s = 0;
        const st = i * HOP;
        for (let j = st; j < st + HOP; j++) {
            const v = ch2 ? (ch[j] + ch2[j]) * 0.5 : ch[j];
            s += v * v;
        }
        const e = Math.sqrt(s / HOP);
        env[i] = Math.max(0, e - prev);
        if (env[i] > mx) mx = env[i];
        prev = e;
    }
    if (mx <= 0) return null;
    for (let i = 0; i < n; i++) env[i] /= mx;

    // 2) 자기상관으로 주기(=박) 찾기. 60~190 BPM 만 본다
    const fps = sr / HOP;
    const minLag = Math.max(1, Math.round(fps * 60 / 190));
    const maxLag = Math.round(fps * 60 / 60);
    if (maxLag >= n) return null;
    let bestLag = 0, bestVal = 0, sum = 0, cnt = 0;
    for (let lag = minLag; lag <= maxLag; lag++) {
        let a = 0;
        for (let i = 0; i + lag < n; i++) a += env[i] * env[i + lag];
        a /= (n - lag);
        sum += a; cnt++;
        if (a > bestVal) { bestVal = a; bestLag = lag; }
    }
    const mean = sum / Math.max(1, cnt);
    const conf = mean > 0 ? bestVal / mean : 0;   // 1에 가까우면 '주기 없음'
    // 잔잔한 발라드 · 앰비언트는 여기서 걸러진다 → 고정 리듬 점멸
    if (!bestLag || conf < 1.35) return null;

    // 3) 격자 위상: 한 주기 안에서 온셋이 가장 몰리는 자리
    let bestOff = 0, bestScore = -1;
    for (let off = 0; off < bestLag; off++) {
        let s = 0;
        for (let i = off; i < n; i += bestLag) s += env[i];
        if (s > bestScore) { bestScore = s; bestOff = off; }
    }

    // 4) 화면에서 보기 편한 속도로. 자기상관은 진짜 주기의 2배(하프타임)를 고르는 일이 잦은데,
    //    반으로 접어도 격자가 여전히 진짜 박 위에 있으므로 그대로 써도 박이 맞는다.
    let period = bestLag / fps;
    while (period > 0.85) period /= 2;
    while (period < 0.34) period *= 2;
    // bpm 은 '실제 깜빡이는 속도' 로 돌려준다(원시 감지값은 로그를 읽는 사람을 헷갈리게 한다)
    return { period, phase: bestOff / fps, bpm: Math.round(60 / period), conf };
}

export function mount(root, lm, opts) {
    const stage = opts.stage;
    root.innerHTML = HTML;
    const layer = root.firstElementChild;
    build(layer);
    const blinkG = layer.querySelector('.nl-blink g');

    let sigColor = null;          // 지금 나오는 시그니처 사진의 대표색(없으면 조종실 색)
    let colorToken = 0, beatToken = 0;
    let beatRAF = null, beatNow = null;

    function syncColor() {
        if (layer.classList.contains('neon-rainbow')) return;           // 무지개는 hue-rotate 가 돈다 — 손대지 않는다
        const L = lightsOf(lm);
        const c = sigColor || (/^#[0-9a-f]{6}$/i.test(String(L.color || '')) ? L.color : null);   // 단색일 때만(OFF · RAINBOW 는 색이 아니다)
        if (c) layer.style.setProperty('--nc', c);
    }

    function render() {
        const L = lightsOf(lm);
        const sp = speedOf(L);
        // 네온 연출 속도. 옛 값은 conic 한 바퀴 기준이라 그대로 쓰면 혜성이 너무 빠르다 — ×2(기본 1.5초 → 한 바퀴 3초)
        layer.style.setProperty('--nspd', (sp * 2) + 's');
        const show = L.color !== 'OFF' && reactionLive(lm, stage);
        if (!show) { layer.classList.remove('active'); return; }
        const head = headItem(lm);
        const tier = neonTierClass(head && head.amount);
        // 등급이 바뀔 때만 갈아 끼운다(매번 갈면 애니메이션이 처음으로 돌아간다).
        // ⚠️ className 통째 대입 금지 — 비트 맞추기가 걸어 둔 'beat-sync' 까지 날아가 고정 점멸이 같이 살아난다
        // ⚠️ 대기줄이 막 비었으면(시그니처 모드가 꺼지기 바로 전 한 박자) 등급을 그대로 둔다 — 안 그러면 사라지는 0.4초 동안
        //    '흐름' 으로 바뀌어 보인다(옛 것은 대기줄이 비는 쪽지에 reaction_mode 꺼짐이 같이 와서 그런 일이 없었다)
        if ((head || !TIERS.some(t => layer.classList.contains(t))) && !layer.classList.contains(tier)) {
            layer.classList.remove(...TIERS);
            layer.classList.add(tier);
        }
        layer.classList.add('active');
        layer.classList.toggle('neon-rainbow', L.color === 'RAINBOW');
        if (L.color === 'RAINBOW') layer.style.setProperty('--nc', RAINBOW_BASE);   // 무지개는 판 전체를 돌리므로 기준색만
        else syncColor();                                                          // 사진 대표색 → 없으면 조명 색
        // 🥁 다음 차례 시그니처의 박자를 미리(시작하자마자 박이 맞게). 주소마다 기억해서 같은 음원은 두 번 안 푼다
        try {
            const items = ((lm.get('queue') || {}).items) || [];
            for (let i = 0; i < Math.min(2, items.length); i++) {
                const it = items[i];
                if (it && it.audio_url && neonTierClass(it.amount) === 'tier-blink') getBeatMap(it.audio_url);
            }
        } catch (e) {}
    }

    function startBeat(map, audio) {
        stopBeat();
        if (!blinkG || !audio || !map) return;
        beatNow = map;
        layer.classList.add('beat-sync');   // 먼저 CSS 점멸을 끄고 밝기를 준다
        const loop = () => {
            if (!beatNow) return;
            const t = audio.currentTime - beatNow.phase;
            const x = t >= 0 ? (t % beatNow.period) / beatNow.period : 0;
            // 박에서 확 켜지고 다음 박 전까지 빠르게 사그라든다
            blinkG.style.opacity = (0.08 + 0.92 * Math.exp(-x * 4.5)).toFixed(3);
            beatRAF = requestAnimationFrame(loop);
        };
        beatRAF = requestAnimationFrame(loop);
    }
    function stopBeat() {
        if (beatRAF) { cancelAnimationFrame(beatRAF); beatRAF = null; }
        beatNow = null;
        layer.classList.remove('beat-sync');
        if (blinkG) blinkG.style.removeProperty('opacity');   // 고정 리듬 점멸로 돌아간다
    }

    stage.provide('neon', {
        /* 시그니처가 시작될 때(옛 playReaction 의 applySignatureThemeColor + beginBeatSync) */
        sigPlay(item, audio) {
            const it = item || {};
            // 🥁 분석은 늦게 올 수 있다 — 그 사이 다음 시그니처로 넘어갔으면 버린다(토큰)
            const bt = ++beatToken;
            stopBeat();
            const L = lightsOf(lm);
            if (it.audio_url && L.color !== 'OFF' && neonTierClass(it.amount) === 'tier-blink') {   // 조명이 꺼져 있으면 분석할 까닭이 없다 · 점멸 등급만
                getBeatMap(it.audio_url).then(map => {
                    if (bt !== beatToken || !map) return;      // 다음 것으로 넘어갔거나 분석 실패 → 고정 리듬 그대로
                    console.log(`[비트] ${map.bpm} BPM, 주기 ${map.period.toFixed(3)}s, 신뢰도 ${map.conf.toFixed(2)}`);
                    startBeat(map, audio);
                });
            }
            // 🎨 새 시그니처 — 앞 사진 색은 바로 버린다(엉뚱한 색이 남지 않게)
            const ct = ++colorToken;
            sigColor = null;
            syncColor();
            if (!it.image_url) return Promise.resolve(null);
            return new Promise(resolve => {
                const probe = new Image();
                probe.crossOrigin = 'anonymous';     // 보이는 그림과 따로 — 색 뽑기 전용 사본
                probe.onload = () => {
                    if (ct !== colorToken) return resolve(null);   // 더 새 시그니처가 있다
                    try {
                        const c = vibrantColorFromImage(probe);
                        if (!c) return resolve(null);
                        sigColor = `rgb(${c.r}, ${c.g}, ${c.b})`;
                        syncColor();                                 // 화면 네온도 같은 색으로
                        resolve(sigColor);
                    } catch (e) { resolve(null); }                   // CORS 로 막힘 등 → 등급 색 그대로
                };
                probe.onerror = () => resolve(null);
                probe.src = it.image_url;
            });
        },
        /* 끝났다 · 끊었다(옛 stopReaction 의 정리) — 사진 색을 버리고 네온을 조명 색으로, 비트는 멈춘다 */
        sigEnd() {
            colorToken++;
            sigColor = null;
            syncColor();
            beatToken++;
            stopBeat();
        },
    });

    watch(lm, stage, render);
    window.__lmNeon = { layer, get sigColor() { return sigColor; }, get beat() { return beatNow; }, beatCache };   // 점검용(콘솔)
}
