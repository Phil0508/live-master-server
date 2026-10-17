/* 🎆 시그니처 전용 연출 무대 — 10만~300만 원 시그니처마다 따로 만든 큰 연출 18가지(옛 17선 + 09-23 진압해 — 가즈아 · 참격 · CLUB OPEN …).

   연출 자체는 옛 방송판이 쓰던 파일을 **글자 하나 안 바꾸고** 그대로 쓴다: /overlay/sigfx/sig-fx.js(SigFX) · sig-fx-gl.js(SigGL 빛 · 입자).
   이 위젯은 그 파일을 불러 무대(캔버스 전체 칸)를 내주고, 시그니처 위젯(signature.js)이 부르는 약속만 만든다.
     - 무대는 방송판(1080×1920 세로)을 그대로 판으로 쓴다 — sig-fx.js 가 판 크기를 재서 좌표를 세로로 옮겨 그린다(그 파일 _fit).
     - 흔들림은 방송 내용물(#canvas)에 건다. #scale-wrapper 를 흔들면 거기 걸린 배율이 날아가 화면이 통째로 어긋난다(옛 #master-container).
     - 층은 layers.js(groups/sigfx.js)에서: 시그니처 카드(50) 위 55 — 옛 #sigfx-stage 101005 > 카드 100010.

   다른 위젯에 주는 것(stage.provide('sigfx')) — signature.js 가 부른다:
     play(item, {card}) → 연출 길이(ms) · 못 틀었으면 0(파일을 아직 못 받음 · 표에 없는 시그 · 실패 → 부르는 쪽이 'OO업' 으로 간다)
                          card = 시그니처 카드 — 연출이 카드 등장 시점을 맡는다(그동안 카드 축소는 미룬다 — rules.shrinkWait)
     stop()             지금 연출을 바로 걷는다(카드 · 흔들 대상에 걸린 애니메이션까지 되돌린다 — SigFX.stop)

   🔥 미리받기(옛 preloadSignatures) — 방송판이 켜질 때 시그니처 목록(/api/sigfx/sigs, 로그인 없이 · 그림 · 소리 · 길이만)을 받아
      사진은 바로 같이 받고(받는 김에 대표색을 뽑아 둔다) · 소리는 하나씩 차례로 캐시에 넣는다(대역폭이 한꺼번에 몰리지 않게).
      ⚠️ 사진에 crossOrigin 을 꼭 붙인다 — 안 붙이면 CORS 없는 응답이 캐시에 들어가 나중에 색을 뽑으려 다시 부를 때 캐시가 어긋난다
         (옛 것: 이것 때문에 연출 색 연동이 한 번도 안 걸렸다).
      ?monitor=1(미리보기 · 폰)은 소리 미리받기를 안 한다 — 소리를 내지 않는 창이 시그니처 음원 전부를 받을 까닭이 없다(폰 데이터). */
import { sigFxKey, SIGFX_BY_AMOUNT } from './rules.js';
import { vibrantColorFromImage } from '../fx/neon.js';

const LIB = ['/overlay/sigfx/sig-fx-gl.js', '/overlay/sigfx/sig-fx.js'];     // 빛 · 입자(SigGL)를 먼저 — 없으면 SigFX 가 예전 길로 간다
const BATON = '/vendor/sigfx/baton.webp';                                      // 🚨 진압해 경광봉 사진 — 첫 후원 때 늦게 뜨지 않게
// 🔤 연출 글꼴(/vendor/fonts/sigfx-fonts.css) — 브라우저는 글꼴을 '처음 쓸 때' 받는다. 연출은 2초 남짓이라 그때 받으면
//    그동안 기본 글씨로 보인다 → 무대가 켜질 때 미리 받아 둔다. 굵기 · 이름은 sig-fx.js 가 쓰는 그대로.
//    [글꼴, 글자] — 글자는 연출이 실제로 쓰는 것. Black Han Sans(fonts.css)는 글자 묶음으로 잘려 있어 쓰는 글자가 든 조각만 받는다
//    (가즈아는 캔버스에 그려서 그때 글꼴이 없으면 기본 글씨로 굳는다).
export const FX_FONTS = [
    ["400 40px 'Anton'", 'HOTELBOUNCEDMVP'],
    ["300 40px 'Cormorant Garamond'", 'MARTINIVPANGEL'],
    ["400 40px 'IBM Plex Sans KR'", '부티호텔바운스마티니시그니처 · 1,000,000원'],
    ["600 40px 'IBM Plex Sans KR'", '람바다'],
    ["400 40px 'Black Han Sans'", '가즈아방패참격푸차POLICE LINE · 진압 중 · 접근 금지'],
];
function warmFonts() {
    try { FX_FONTS.forEach(([f, s]) => document.fonts.load(f, s).catch(() => {})); } catch (e) {}
}

let libPromise = null;
function loadLib() {
    if (libPromise) return libPromise;
    libPromise = LIB.reduce((p, src) => p.then(() => new Promise(resolve => {
        const s = document.createElement('script');
        s.src = src;
        s.async = false;
        s.onload = () => resolve(true);
        s.onerror = () => { console.error('[시그연출] 파일을 못 받았습니다 — 시그니처는 그대로 나갑니다:', src); resolve(false); };
        document.head.appendChild(s);
    })), Promise.resolve()).then(() => typeof window.SigFX !== 'undefined');
    return libPromise;
}

export function mount(root, lm, opts) {
    root.innerHTML = '<div class="sigfx-stage"><div class="sigfx-inner"></div></div>';
    const inner = root.querySelector('.sigfx-inner');
    loadLib().then(ok => { if (ok) console.log('[시그연출] 준비됨 — ' + Object.keys(SIGFX_BY_AMOUNT).length + '가지'); });
    try { const b = new Image(); b.src = BATON; } catch (e) {}
    warmFonts();

    // ── 사진 대표색(옛 sigFxColorCache) — 미리받기 때 채워 두고, 후원이 온 순간엔 읽기만 한다 ──
    //    ⚠️ 연출은 색을 2~3개 쓴다. 대표색은 하나라 같은 색으로 채운다. CORS 로 막히면 null → 연출 기본 색.
    const colorCache = {};
    function cacheColors(url, img) {
        if (!url || colorCache[url]) return;
        try {
            const c = vibrantColorFromImage(img);
            if (!c) return;
            const rgb = `rgb(${c.r}, ${c.g}, ${c.b})`;
            colorCache[url] = [rgb, rgb, rgb];
        } catch (e) {
            colorCache[url] = null;
        }
    }
    function colorsNow(url) {
        if (!url) return null;
        if (colorCache[url] !== undefined) return colorCache[url];
        // 미리받기에 없던 새 시그니처 — 지금 받아 두고(다음 번엔 색이 붙는다) 이번은 기본 색으로 간다
        try {
            const p = new Image();
            p.crossOrigin = 'anonymous';
            p.onload = () => cacheColors(url, p);
            p.src = url;
        } catch (e) {}
        return null;
    }

    async function preload() {
        try {
            const res = await fetch('/api/sigfx/sigs', { cache: 'no-store' });
            const data = await res.json();
            const sigs = (data && data.signatures) || [];
            sigs.forEach(s => {
                if (!s.image_url) return;
                const im = new Image();
                im.crossOrigin = 'anonymous';
                im.onload = () => cacheColors(s.image_url, im);
                im.src = s.image_url;
            });
            console.log(`[미리받기] 시그니처 ${sigs.length}개 사진 받기 시작`);
            if (opts.monitor) return;
            for (const s of sigs) {
                if (!s.sound_url) continue;
                try { await fetch(s.sound_url, { cache: 'force-cache' }); } catch (e) {}
            }
            console.log('[미리받기] 시그니처 소리 받기 끝');
        } catch (e) {
            console.warn('[미리받기] 실패(무시하고 진행):', e);
        }
    }
    preload();

    function play(item, o) {
        const key = sigFxKey(item);
        const SigFX = window.SigFX;
        if (!key || !SigFX) return 0;
        try {
            const imgUrl = (item && item.image_url) || null;
            const ms = SigFX.play(key, inner, {
                shakeEl: document.getElementById('canvas'),
                image: imgUrl,
                colors: colorsNow(imgUrl),
                card: (o && o.card) || null,
            }) || 0;
            console.log('[시그연출] ' + key + ' (' + item.sig_amount + '원)' + (imgUrl ? ' · 사진 O' : ' · 사진 X'));
            return ms;
        } catch (e) {
            // 연출 하나 때문에 시그니처 재생이 멈추면 안 된다
            console.error('[시그연출] 실패 — 시그니처는 그대로 나갑니다:', e);
            return 0;
        }
    }

    function stop() {
        const SigFX = window.SigFX;
        if (SigFX && SigFX.stop) { try { SigFX.stop(inner); } catch (e) {} }
    }

    opts.stage.provide('sigfx', { play, stop, ready: loadLib });

    // 점검용(콘솔 · 헤드리스 확인): __lmSigfx.test(300000) 이나 test('mvp') — 카드 없이 연출만 한 번
    window.__lmSigfx = {
        get loaded() { return typeof window.SigFX !== 'undefined'; },
        colors: colorCache,
        table: SIGFX_BY_AMOUNT,
        test(x, image) {
            const amt = typeof x === 'number' ? x : Number(Object.keys(SIGFX_BY_AMOUNT).find(k => SIGFX_BY_AMOUNT[k] === x));
            return play({ sig_amount: amt, image_url: image || null }, {});
        },
        stop,
    };
}
