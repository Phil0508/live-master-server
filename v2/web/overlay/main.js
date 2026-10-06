/* 📺 v2 방송판 — 캔버스를 세우고, 층 표(layers.js)대로 칸을 만들어 위젯을 하나씩 붙인다.

   주소: /overlay/            OBS 브라우저 소스(1080×1920, 투명)
         ?monitor=1           미리보기 — 소리 끔 · 시그니처 '다 틀었다' 보고 안 함(옛 IS_MONITOR)
         ?debug=1             연결 표시(왼쪽 위)
         ?hud=best,donor_rank,-gauge   고정 자리 스위치를 이 창에서만 켜고(-는 끄고) 본다(시험 · 미리보기용)

   ⚠️ 위젯끼리는 서로의 화면(DOM)을 만지지 않는다. 같이 알아야 하는 것은 stage 로만 주고받는다:
      - stage.setMode('reaction', on)   시그니처가 도는 동안 → hideInReaction 칸을 숨긴다(옛 body.reaction-mode)
      - stage.provide(name, api) / stage.use(name)   예: 후원 카드(donationCard) — 시그니처가 틀기 전에 카드를 부탁한다
      - stage.isOn(layerId)             그 칸이 지금 보이는가(방송 중 · 스위치)
      - stage.bands(x1, x2, selfId) · stage.onLayout(fn)   그 x 구간을 지나는 판(solid)의 위아래 띠 — 게이지 딱지가 비킬 때
      - stage.alertOn(key)              알림 스위치(show.alerts.<key>, 조각이 없으면 켜짐)
      - stage.sfxOn()                   효과음 스위치(look.sfx, 값이 없으면 켜짐 — 옛 sfx_enabled). 시그니처 · 노래방 · 영상 소리는 상관없다
      - opts.isFresh(at)                이 알림을 띄워도 되나(붙은 직후 통째 받은 것은 30초 안의 것만)
*/
import { CANVAS, LAYERS } from './layers.js';
import { FRESH_MS } from './util.js';

const params = new URLSearchParams(location.search);
const MONITOR = params.get('monitor') === '1';
const DEBUG = params.get('debug') === '1';
const HUD_FORCE = {};
(params.get('hud') || '').split(',').map(s => s.trim()).filter(Boolean).forEach(k => {
    if (k[0] === '-') HUD_FORCE[k.slice(1)] = false;
    else HUD_FORCE[k.replace(/^\+/, '')] = true;
});

// ── 캔버스 배율 — 창이 1080×1920 이 아니어도 비율을 지켜 가운데에(옛 resizeOverlay) ──
const wrapper = document.getElementById('scale-wrapper');
const canvas = document.getElementById('canvas');
function resize() {
    const s = Math.min(window.innerWidth / CANVAS.w, window.innerHeight / CANVAS.h);
    wrapper.style.transform = `scale(${s})`;
    wrapper.style.left = ((window.innerWidth - CANVAS.w * s) / 2) + 'px';
    wrapper.style.top = ((window.innerHeight - CANVAS.h * s) / 2) + 'px';
}
window.addEventListener('resize', resize);
resize();

// ── 칸 자리 — z-index 는 여기서만 넣는다 ──
function place(el, L) {
    const s = L.scale || 1;
    el.style.zIndex = String(L.z);
    el.style.top = L.y + 'px';
    if (L.w) el.style.width = L.w + 'px';
    if (L.h) el.style.height = L.h + 'px';
    const a = L.anchor || 'tl';
    if (a === 'tr') {
        el.style.right = (CANVAS.w - L.x) + 'px';
        el.style.transformOrigin = 'top right';
        el.style.transform = s !== 1 ? `scale(${s})` : '';
    } else if (a === 'tc') {
        el.style.left = L.x + 'px';
        el.style.transformOrigin = 'top center';
        el.style.transform = `translateX(-50%)` + (s !== 1 ? ` scale(${s})` : '');
    } else if (a === 'cc') {
        el.style.left = L.x + 'px';
        el.style.transformOrigin = 'center';
        el.style.transform = `translate(-50%, -50%)` + (s !== 1 ? ` scale(${s})` : '');
    } else {
        el.style.left = L.x + 'px';
        el.style.transformOrigin = 'top left';
        el.style.transform = s !== 1 ? `scale(${s})` : '';
    }
}

// ── 무대 — 위젯끼리 약속을 주고받는 곳(화면은 안 만진다) ──
function makeStage(lm, cells) {
    const services = {};
    const modeFns = [];
    const layoutFns = [];
    const modes = {};
    let layoutQueued = false;
    const stage = {
        setMode(name, on) {
            on = !!on;
            if (modes[name] === on) return;
            modes[name] = on;
            canvas.classList.toggle(name + '-mode', on);
            modeFns.forEach(fn => { try { fn(name, on); } catch (e) { console.error(e); } });
            stage.layoutChanged();
            setTimeout(() => stage.layoutChanged(), 450);   // 숨김 · 보임 전환(0.4초)이 끝난 뒤 한 번 더 잰다
        },
        /* 칸이 보이거나 숨거나 크기가 바뀌었다 — 한 박자 모아 한 번만 알린다 */
        layoutChanged() {
            if (layoutQueued) return;
            layoutQueued = true;
            requestAnimationFrame(() => {
                layoutQueued = false;
                layoutFns.forEach(fn => { try { fn(); } catch (e) { console.error(e); } });
            });
        },
        onLayout(fn) { layoutFns.push(fn); },
        /* x1~x2 사이를 지나는 '판'(solid) 들의 위아래 띠 [[위, 아래], …] — 캔버스 좌표, 앞뒤 8px 여유.
           지금 보이는 판만(방송 꺼짐 · 스위치 꺼짐 · 시그니처 중 가려진 것은 뺀다). 판의 속은 안 본다 — 칸 상자만 잰다. */
        bands(x1, x2, selfId) {
            const cr = canvas.getBoundingClientRect();
            const sc = (cr.width / CANVAS.w) || 1;
            const reaction = canvas.classList.contains('reaction-mode');
            const out = [];
            cells.forEach(({ L, el }) => {
                if (!L.solid || L.id === selfId || el.classList.contains('off')) return;
                if (reaction && L.hideInReaction) return;
                const r = el.getBoundingClientRect();
                if (r.width < 2) return;
                // 판 모드가 CSS 로 가린 칸(예: 주사위판 동안 순위판)은 자리를 차지하지 않는다
                const cs = getComputedStyle(el);
                if (cs.visibility === 'hidden' || parseFloat(cs.opacity) < 0.05) return;
                const l = (r.left - cr.left) / sc, rr = (r.right - cr.left) / sc;
                if (rr < x1 || l > x2) return;
                out.push([(r.top - cr.top) / sc - 8, (r.bottom - cr.top) / sc + 8]);
            });
            return out;
        },
        mode(name) { return !!modes[name]; },
        onMode(fn) { modeFns.push(fn); },
        provide(name, api) { services[name] = api; },
        use(name) { return services[name] || null; },
        isOn(id) { const el = canvas.querySelector('[data-layer="' + id + '"]'); return !!el && !el.classList.contains('off'); },
        alertOn(key) {
            const sh = lm.get('show');
            return !(sh && sh.alerts && sh.alerts[key] === false);
        },
        sfxOn() {
            const lk = lm.get('look');
            return !(lk && lk.sfx === false);
        },
    };
    return stage;
}

function hudOn(L, show) {
    if (!L.hud) return true;
    if (L.hud in HUD_FORCE) return HUD_FORCE[L.hud];
    if (show && show.hud && L.hud in show.hud) return !!show.hud[L.hud];
    return L.hudDefault !== false;
}

async function boot() {
    const layers = LAYERS.filter(L => !L.debugOnly || DEBUG);
    // 1) 위젯 파일을 먼저 다 받는다 — 하나가 깨져도 나머지는 뜬다(옛 것은 한 파일이라 한 곳이 깨지면 다 멈췄다)
    const mods = await Promise.allSettled(layers.map(L => import('./widgets/' + L.widget + '.js')));

    // 2) 그다음 연결 — 붙이기 전에 모든 위젯이 듣고 있어야 '처음 통째(snapshot)' 와 '그 뒤 쪽지(patch)' 를 가린다
    const lm = LM.connect({ kind: 'overlay', monitor: MONITOR });
    let streaming = false;          // true = 지금 오는 것은 실시간 쪽지 / false = 붙은 직후 통째
    lm.onStatus(s => { streaming = (s === 'live'); });
    const isFresh = at => {
        if (streaming) return true;                 // 실시간으로 막 온 알림
        const ms = Number(at) || 0;                 // 통째로 받은 것 — 다시 붙었을 때 지난 알림이 터지지 않게
        return ms > 0 && Date.now() - ms < FRESH_MS;
    };
    const cells = [];
    const stage = makeStage(lm, cells);

    // 3) 칸 만들기 · 위젯 붙이기(표 순서대로)
    layers.forEach((L, i) => {
        const el = document.createElement('div');
        el.className = 'layer layer-' + L.id + (L.hideInReaction ? ' hide-in-reaction' : '');
        el.dataset.layer = L.id;
        place(el, L);
        canvas.appendChild(el);
        cells.push({ L, el });
        const m = mods[i];
        if (m.status !== 'fulfilled' || typeof m.value.mount !== 'function') {
            console.error('[방송판] 위젯을 못 불렀습니다:', L.widget, m.reason || '');
            return;
        }
        try {
            m.value.mount(el, lm, { monitor: MONITOR, debug: DEBUG, stage, layer: L, isFresh });
        } catch (e) {
            console.error('[방송판] 위젯 붙이기 실패:', L.widget, e);
        }
    });

    // 4) 보이기 · 숨기기 — 방송 중인가 · 고정 자리 스위치
    const refresh = () => {
        const live = !!(lm.get('session') || {}).live;
        const show = lm.get('show');
        cells.forEach(({ L, el }) => {
            const on = (!L.liveOnly || live) && hudOn(L, show);
            el.classList.toggle('off', !on);
        });
        stage.layoutChanged();
    };
    lm.on('session', refresh);
    lm.on('show', refresh);
    refresh();

    // 5) 따라 붙는 칸(below) — 기준 칸의 크기가 바뀌면(사람 수 · 줄 수) 그 아래로 다시 붙인다. 자리만 바꾼다(위젯 속은 안 만진다)
    cells.filter(c => c.L.below).forEach(c => {
        const ref = cells.find(x => x.L.id === c.L.below);
        if (!ref) return;
        const follow = () => {
            if (c.placed) return;                                  // 편집기에서 손으로 옮긴 칸은 따라가지 않는다
            const h = ref.el.offsetHeight * (ref.L.scale || 1);   // 숨김(visibility)이어도 자리는 잡혀 있어 잴 수 있다
            if (h > 0) c.el.style.top = Math.round(ref.el.offsetTop + h + (c.L.gap || 8)) + 'px';
            stage.layoutChanged();
        };
        c.follow = follow;                                         // 자리 쪽지(applyLayout) 뒤에도 다시 붙는다
        try { new ResizeObserver(follow).observe(ref.el); } catch (e) {}
        follow();
    });
    // 판(solid) 크기가 바뀌면 — 게이지 딱지 같은 것이 다시 비킨다
    try {
        const ro = new ResizeObserver(() => stage.layoutChanged());
        cells.forEach(({ L, el }) => { if (L.solid) ro.observe(el); });
    } catch (e) {}

    // 6) 편집기에서 옮긴 자리(layout 조각) — 표의 기본 자리(x · y · scale)를 칸마다 덮어쓴다.
    //    ⚠️ 기준점(anchor)은 표 그대로다 — 편집기도 같은 표(layers.js)를 보고 같은 기준으로 적는다.
    const applyLayout = () => {
        const lay = (lm.get('layout') || {}).widgets || {};
        cells.forEach(c => {
            const o = lay[c.L.id];
            const L2 = Object.assign({}, c.L);
            if (o) {
                ['x', 'y', 'scale'].forEach(k => { if (typeof o[k] === 'number' && isFinite(o[k])) L2[k] = o[k]; });
            }
            c.placed = !!o;
            c.el.style.left = c.el.style.right = '';
            place(c.el, L2);
        });
        // ⚠️ 표 자리로 되돌린 '따라 붙는 칸' 은 기준 칸 아래로 다시 붙인다(안 그러면 점수판을 옮긴 뒤 계좌 · 후원 순위가 어긋났다)
        cells.forEach(c => { if (c.follow && !c.placed) c.follow(); });
        stage.layoutChanged();
    };
    lm.on('layout', applyLayout);

    // 7) 테마 — look.theme 이름을 캔버스에 붙인다(옛 applyTheme: theme-<이름> · themed · 밝은 판이면 themed-light)
    const LIGHT = ['hospital', 'news', 'mintchoco', 'hanji', 'winter', 'pastel'];
    let themeNow = '';
    lm.on('look', look => {
        let t = String((look && look.theme) || 'default');
        if (t === 'pink') t = 'rose';
        const want = t === 'default' ? '' : t;
        if (want === themeNow) return;
        [...canvas.classList].filter(c => c.startsWith('theme-')).forEach(c => canvas.classList.remove(c));
        themeNow = want;
        if (want) canvas.classList.add('theme-' + want);
        canvas.classList.toggle('themed', !!want);
        canvas.classList.toggle('themed-light', !!want && LIGHT.includes(want));
        document.body.dataset.theme = want || 'default';
    });

    window.__lmOverlay = { lm, stage, monitor: MONITOR };     // 점검용(콘솔)
}

boot().catch(e => console.error('[방송판] 시작 실패:', e));
