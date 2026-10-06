/* ✨ 테마 연출 — 테마를 입었을 때 그 테마 모양 입자(하트 · 리본 · 보석 · 금가루 …)를 조금 뿌린다(옛 overlay.html themeBurst 그대로).

   ⚠️ 예전에 '후원 터질 때 나오던 카지노 컨페티' 를 대표님 요청으로 뺐다. 그래서 **기본 테마에서는 아무것도 안 한다.**
      테마를 입었을 때만 적게 뿌리고, 큰 후원일수록 조금 커진다. 조종실 '✨ 테마 연출'(look.fx)을 끄면 테마를 입어도 안 뿌린다.
      뉴스 · 한지는 조용한 옷이라 입자가 없다(표에 없다).
   ⚠️ 폭죽 파일을 못 읽었어도 후원 알림은 그대로 떠야 한다 — 전부 try 안에서만, 실패하면 false.

   다른 위젯에 주는 것(stage.provide('fx')):
     burst(anchorEl, kind, amount) → true(뿌렸다) · false(안 뿌림 — 부른 쪽이 원래 연출을 하면 된다, 예: 핀볼 우승 폭죽)
       kind: 'donation'(후원 카드 — 금액으로 1~3단) · 'best'(최고 기록 갱신) · 'win'(핀볼 우승) — 뒤의 둘은 늘 3단
       anchorEl: 입자가 터질 화면 요소(그 가운데 · 위에서 40%)
   그리는 곳: 이 칸(1080×1920) 안의 캔버스 — 옛 것은 화면 전체 위(100006)에 그렸다. 층은 groups/fx.js(47). */
const CONFETTI_SRC = '/vendor/confetti.browser.min.js';     // canvas-confetti 1.9.3(옛 방송판과 같은 파일)
let libP = null;
function loadConfetti() {
    if (typeof window.confetti === 'function') return Promise.resolve(window.confetti);
    if (libP) return libP;
    libP = new Promise(resolve => {
        const done = () => resolve(typeof window.confetti === 'function' ? window.confetti : null);
        // 다른 위젯(게임판)이 먼저 붙인 같은 파일이 있으면 그것을 기다린다
        const have = [...document.scripts].find(s => s.getAttribute('src') === CONFETTI_SRC);
        const s = have || document.createElement('script');
        s.addEventListener('load', done, { once: true });
        s.addEventListener('error', () => resolve(null), { once: true });
        if (!have) { s.src = CONFETTI_SRC; s.async = true; document.head.appendChild(s); }
        // (이미 다 읽힌 파일이면 맨 위 줄에서 끝났다. 못 받아도 burst() 가 부를 때마다 다시 본다 — ready())
    });
    return libP;
}

// 테마 이름(look.theme) → 입자 색 · 모양 · 크기(옛 THEME_BURST 그대로 — 키만 'theme-' 를 뗐다)
const THEME_BURST = {
    rose:      { colors: ['#ff9cc2', '#ffe0ec', '#e8a5b5', '#ffffff'], shape: 'heart',  scalar: 1.7 },
    pastel:    { colors: ['#ff8fb8', '#c9a7f2', '#ffd1e3', '#ffffff'], shape: 'bow',    scalar: 1.9 },
    royal:     { colors: ['#e9bd5c', '#fff0b8', '#ff4f9a', '#9f76e6'], shape: 'gem',    scalar: 1.5 },
    chuseok:   { colors: ['#ffd76a', '#fff3c4', '#f2c230', '#ffe7a0'], shape: 'dust',   scalar: .75, moon: true },
    // 🎨 새 테마(2026-09-30) — 뉴스 · 한지는 조용한 옷이라 입자를 안 뿌린다
    hospital:  { colors: ['#13b3a1', '#ff4d5e', '#ffffff', '#bff3ea'], shape: 'cross',  scalar: 1.3 },
    halloween: { colors: ['#ff8a1f', '#8fdc5a', '#c9a3ff', '#ffb45c'], shape: 'circle', scalar: 1.2 },
    concert:   { colors: ['#a07bff', '#52e3ff', '#ffffff', '#ff7ac8'], shape: 'star',   scalar: 1.4 },
    sports:    { colors: ['#ffd400', '#ffffff', '#ff3b3b'],            shape: 'square', scalar: 1.1 },
    arcade:    { colors: ['#ffd23f', '#4ff0ff', '#ff4fd8'],            shape: 'square', scalar: 1.1 },
    mintchoco: { colors: ['#5a3526', '#3dbf94', '#c7f2e2', '#8c5a44'], shape: 'circle', scalar: 1 },
    y2k:       { colors: ['#ff9ad5', '#d6ff6b', '#dfe3ea', '#ffffff'], shape: 'star',   scalar: 1.5 },
    winter:    { colors: ['#ffffff', '#d6eaff', '#9cc8ff'],            shape: 'dust',   scalar: .8 },
};

let shapesCache = null;
function burstShapes() {
    if (shapesCache) return shapesCache;
    shapesCache = {};
    try {
        const P = (typeof window.confetti === 'function' && window.confetti.shapeFromPath) ? window.confetti.shapeFromPath : null;
        if (P) {
            shapesCache.heart = P({ path: 'M12 21s-7.5-4.6-10-9.3C.4 8.3 2.3 4 6.2 4c2.2 0 3.6 1.2 5.8 3.5C14.2 5.2 15.6 4 17.8 4 21.7 4 23.6 8.3 22 11.7 19.5 16.4 12 21 12 21z' });
            shapesCache.gem = P({ path: 'M12 2 21 12 12 22 3 12z' });
            shapesCache.bow = P({ path: 'M12 11C9 6 3 5 2.5 8.5 2 12 6 14 11.5 12.5zM12 11c3-5 9-6 9.5-2.5.5 3.5-3.5 5.5-9 4z' });
            shapesCache.star = P({ path: 'M12 0c1 6 5 10 12 12-7 2-11 6-12 12-1-6-5-10-12-12C7 10 11 6 12 0z' });
            shapesCache.cross = P({ path: 'M9 3h6v6h6v6h-6v6H9v-6H3V9h6z' });
        }
    } catch (e) { /* 모양 폭죽을 못 만드는 브라우저 — 동그라미로 */ }
    shapesCache.square = 'square';   // 폭죽 기본 모양 — 스포츠 · 아케이드
    shapesCache.circle = 'circle';
    return shapesCache;
}

export function mount(root, lm, opts) {
    root.innerHTML = '<canvas class="fx-burst" aria-hidden="true"></canvas>';
    const cv = root.firstElementChild;
    let shoot = null;                // 이 캔버스 전용 폭죽(confetti.create)
    const ready = () => {
        if (shoot) return shoot;
        if (typeof window.confetti !== 'function' || typeof window.confetti.create !== 'function') return null;
        try { shoot = window.confetti.create(cv, { resize: true, useWorker: true }); } catch (e) { shoot = null; }
        return shoot;
    };
    loadConfetti().then(ready).catch(() => {});

    const themeNow = () => {
        let t = String((lm.get('look') || {}).theme || 'default');
        if (t === 'pink') t = 'rose';                                   // 'pink' = 뺀 옛 네온 핑크 → 로즈골드(main.js 와 같다)
        return t === 'default' ? '' : t;
    };
    const fxOn = () => (lm.get('look') || {}).fx !== false;            // 옛 theme_fx_enabled !== false

    function burst(anchorEl, kind, amount) {
        if (!fxOn()) return false;
        const t = THEME_BURST[themeNow()];
        if (!t) return false;
        const fire = ready();
        if (!fire) return false;
        try {
            const r = anchorEl ? anchorEl.getBoundingClientRect() : null;
            const cr = cv.getBoundingClientRect();
            if (!cr.width || !cr.height) return false;
            // 터지는 자리 = 요소 가운데 · 위에서 40% — 이 캔버스 안의 비율(옛 것은 화면 비율 — OBS 1080×1920 에서 같다)
            const ox = (r && r.width) ? (r.left + r.width / 2 - cr.left) / cr.width : 0.5;
            const oy = (r && r.height) ? (r.top + r.height * 0.4 - cr.top) / cr.height : 0.45;
            const amt = Number(amount) || 0;
            const lvl = (kind === 'donation') ? (amt >= 100000 ? 3 : (amt >= 30000 ? 2 : 1)) : 3;
            const shape = burstShapes()[t.shape];
            fire({
                particleCount: [0, 14, 30, 60][lvl] * (t.shape === 'dust' ? 2 : 1),
                spread: 55 + lvl * 20, startVelocity: 20 + lvl * 8,
                gravity: t.shape === 'dust' ? 0.45 : 0.9, ticks: 150 + lvl * 50, drift: 0,
                origin: { x: ox, y: oy }, colors: t.colors,
                shapes: shape ? [shape] : ['circle'], scalar: t.scalar,
            });
            // 🌕 추석 — 큰 후원(3만 원 이상)이나 기록 갱신 · 우승이면 보름달이 떠오른다
            if (t.moon && lvl >= 2) {
                const m = opts.stage.use('themeMoon');
                if (m) m.rise();
            }
            return true;
        } catch (e) { return false; }
    }

    opts.stage.provide('fx', { burst });
}
