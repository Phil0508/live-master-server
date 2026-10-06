/* 🧭 위젯 자리 편집기 — /controller/editor/
   왼쪽에 진짜 방송판(/overlay/?monitor=1)을 1080×1920 그대로 띄우고 화면 크기에 맞게 줄여 보여 준다.
   그 위에 투명한 '유리판'(#glass)을 얹어 누르기 · 끌기를 받는다(방송판 iframe 은 마우스를 안 받는다).

   자리 약속(layers.js · overlay/main.js place() 와 같다):
     x · y 는 위젯의 '기준점(anchor)' 이 캔버스의 어디에 있나.
       tl  왼쪽 위 모서리  → style.left = x                       · style.top = y
       tr  오른쪽 위 모서리 → style.right = 1080 - x               · style.top = y
       tc  위 가운데       → style.left = x + translateX(-50%)    · style.top = y
       cc  한가운데        → style.left = x + translate(-50%,-50%) · style.top = y
     배율(scale)은 그 기준점을 붙박은 채로 커지고 작아진다(transform-origin 이 기준점) → 크기를 바꿔도 x · y 는 그대로다.
   그래서 끌기는 '지금 기준점 + 마우스가 움직인 캔버스 px' 로 끝난다. 지금 기준점은 방송판이 칸에 넣어 둔 style 에서 읽는다
   (표의 기본값 · 서버에 적힌 값 · 따라 붙는 칸(below)이 계산한 top 이 모두 거기 들어 있다).

   ⚠️ 서버에는 손을 뗄 때 한 번만 적는다(layout.set). 끄는 동안은 이 화면 안의 방송판 칸만 직접 움직인다.
      화살표 · 크기 막대는 멈춘 뒤 잠깐 기다렸다 한 번 — 마우스가 움직일 때마다 보내지 않는다.
   ⚠️ 방송판 쪽 코드는 안 고친다. 같은 출처라 iframe 안을 잴 수 있고, 방송판이 내놓은 window.__lmOverlay(점검용)에
      'layout 을 받은 뒤' 알림만 덧붙인다. */
import { CANVAS, LAYERS } from '/overlay/layers.js';
import { nameOf, ANCHOR_TEXT } from './names.js';

const $ = id => document.getElementById(id);
const SEND_KEY_MS = 400;        // 화살표 — 마지막으로 누르고 0.4초 뒤 한 번
const SEND_SLIDER_MS = 300;     // 크기 막대 — 움직임이 멈추고 0.3초 뒤 한 번(손을 떼면 바로)
const DRAG_START_PX = 3;        // 화면에서 3px 넘게 움직여야 '끌기'(그냥 누른 것은 고르기만)
const NOMINAL = { w: 320, h: 90 };   // 지금 그릴 내용이 없는 칸의 자리 표시 크기(캔버스 px, 배율 곱하기 전)
const BIG_AREA = 0.85;          // 캔버스를 거의 다 덮는 칸(시그니처 카드 칸)은 화면에서 눌러 고르지 않는다 — 목록에서만
// 서버(show.py layout.set)와 같은 울타리 — 여기서도 같이 막아야 끈 자리와 서버에 적힌 자리가 같다
const LIM = { x: [-540, 1620], y: [-960, 2880], scale: [0.2, 4] };

const layers = LAYERS.filter(L => !L.debugOnly);
const byId = new Map(layers.map(L => [L.id, L]));

const S = {
    lm: null,
    layout: {},          // 서버의 layout.widgets — 손으로 옮긴 칸만 들어 있다
    sel: null,           // 고른 칸 id
    hover: null,
    drag: null,          // 끄는 중 {id, pid, cx, cy, x0, y0, x, y, box0, moved}
    pend: {},            // id → {x?, y?, scale?} 아직 서버에 안 보낸 값
    timers: {},
    save: {},            // id → {st:'busy'|'ok'|'bad', msg}
    boxes: {},           // id → {l, t, w, h, x, y, scale, hidden, reason, empty} (캔버스 px)
    k: 0.4,              // 화면 px ÷ 캔버스 px
    sent: 0,             // 보낸 layout 명령 수(점검용)
    frameReady: false,
    showHidden: true,    // 숨은 칸(방송 꺼짐 · 스위치 꺼짐) 테두리 — 기본 켬
    showEmpty: false,    // 빈 칸(알림 · 게임판처럼 일이 생길 때만 그려지는 것) 테두리 — 기본 끔(스무 개 넘게 겹쳐 어지럽다)
    ghost: false,
};

const clamp = (v, lo, hi) => Math.max(lo, Math.min(hi, v));
const r2 = v => Math.round(v * 100) / 100;
const clampX = v => clamp(Math.round(v), LIM.x[0], LIM.x[1]);
const clampY = v => clamp(Math.round(v), LIM.y[0], LIM.y[1]);
const clampS = v => clamp(r2(v), LIM.scale[0], LIM.scale[1]);
const esc = s => String(s == null ? '' : s).replace(/[&<>"']/g, m => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[m]));
const store = {
    get(k, d) { try { const v = localStorage.getItem('lm2ed:' + k); return v === null ? d : v === '1'; } catch (e) { return d; } },
    set(k, v) { try { localStorage.setItem('lm2ed:' + k, v ? '1' : '0'); } catch (e) {} },
};

// ── 방송판 iframe ──
const frame = $('frame');
const fwin = () => { try { return frame.contentWindow; } catch (e) { return null; } };
const fdoc = () => { try { return frame.contentDocument; } catch (e) { return null; } };
function cellEl(id) {
    const d = fdoc();
    return d ? d.querySelector('[data-layer="' + String(id).replace(/["\\]/g, '\\$&') + '"]') : null;
}

/* 지금 기준점(x · y) — 방송판이 칸에 넣어 둔 style 그대로 읽는다 */
function readPos(L, el) {
    const a = L.anchor || 'tl';
    const st = el ? el.style : {};
    const x = a === 'tr' ? CANVAS.w - parseFloat(st.right) : parseFloat(st.left);
    const y = parseFloat(st.top);
    return { x: isFinite(x) ? x : L.x, y: isFinite(y) ? y : L.y };
}

/* 지금 배율 — 안 보낸 값 → 서버에 적힌 값 → 표의 값 */
function scaleOf(L) {
    const p = S.pend[L.id], o = S.layout[L.id];
    if (p && typeof p.scale === 'number') return p.scale;
    if (o && typeof o.scale === 'number') return o.scale;
    return L.scale || 1;
}

/* 이 화면 안의 방송판 칸만 직접 옮긴다 — overlay/main.js place() 와 **같은 식**이어야 한다(z · w · h 는 안 건드림).
   ⚠️ place() 를 고치면 여기도 같이. */
function livePlace(el, L, x, y, s) {
    if (!el) return;
    const a = L.anchor || 'tl';
    const st = el.style;
    st.top = y + 'px';
    if (a === 'tr') {
        st.left = '';
        st.right = (CANVAS.w - x) + 'px';
        st.transformOrigin = 'top right';
        st.transform = s !== 1 ? `scale(${s})` : '';
    } else if (a === 'tc') {
        st.right = '';
        st.left = x + 'px';
        st.transformOrigin = 'top center';
        st.transform = 'translateX(-50%)' + (s !== 1 ? ` scale(${s})` : '');
    } else if (a === 'cc') {
        st.right = '';
        st.left = x + 'px';
        st.transformOrigin = 'center';
        st.transform = 'translate(-50%, -50%)' + (s !== 1 ? ` scale(${s})` : '');
    } else {
        st.right = '';
        st.left = x + 'px';
        st.transformOrigin = 'top left';
        st.transform = s !== 1 ? `scale(${s})` : '';
    }
}

// ── 재기 — 칸이 화면에서 실제로 차지하는 네모(캔버스 px) ──
/* 안에 '그려진' 것들의 합 — 칸 상자(offsetWidth)만 보면 밖으로 떠 있는 자식(게이지 금액 딱지 — 막대 왼쪽 108px 밖)을
   못 센다(옛 편집기 2026-09-16). 보이는 것 = 펼쳐져 있고(display) · visibility 가 visible · 자기와 조상의 opacity 가 0 이 아닌 것.
   숨은 칸(.off · 시그니처 중)은 칸 통째로 visibility:hidden · opacity 0 이라 그때는 칸 자신의 숨김은 빼고 '켜지면 보일 것' 을 잰다.
   아무것도 안 그려져 있으면(게임판이 무대에 없음 · 알림이 없음) 칸 상자, 그것도 0 이면 기준점에 놓은 자리 표시 네모. */
function measure(L, el, cr, k, reaction, V) {
    const off = el.classList.contains('off') || (reaction && !!L.hideInReaction);
    let l = Infinity, t = Infinity, rr = -Infinity, b = -Infinity, has = false;
    const zero = new Set();                 // opacity 0 인 것과 그 자손(opacity 는 자식이 되살릴 수 없다)
    const kids = el.getElementsByTagName('*');
    const n = Math.min(kids.length, 800);
    for (let i = 0; i < n; i++) {
        const e = kids[i];
        const c = V.getComputedStyle(e);
        if (zero.has(e.parentElement) || parseFloat(c.opacity) === 0) { zero.add(e); continue; }
        if (c.display === 'none' || c.position === 'fixed') continue;
        if (!off && c.visibility !== 'visible') continue;
        const x = e.getBoundingClientRect();
        if (x.width < 1 || x.height < 1) continue;
        has = true;
        if (x.left < l) l = x.left;
        if (x.top < t) t = x.top;
        if (x.right > rr) rr = x.right;
        if (x.bottom > b) b = x.bottom;
    }
    const pos = readPos(L, el);
    const sc = scaleOf(L);
    let box;
    if (has) {
        box = { l: (l - cr.left) / k, t: (t - cr.top) / k, w: (rr - l) / k, h: (b - t) / k, empty: false };
    } else {
        const r = el.getBoundingClientRect();
        box = r.width >= 1 && r.height >= 1
            ? { l: (r.left - cr.left) / k, t: (r.top - cr.top) / k, w: r.width / k, h: r.height / k, empty: true }
            : nominal(L, pos, sc);
    }
    box.x = pos.x; box.y = pos.y; box.scale = sc;
    box.hidden = off;
    box.reason = reasonOf(L, el, reaction);
    return box;
}

/* 지금 그릴 것이 없는 칸 — 기준점에 맞춰 놓은 자리 표시 네모 */
function nominal(L, pos, sc) {
    const w = NOMINAL.w * sc, h = NOMINAL.h * sc, a = L.anchor || 'tl';
    const l = a === 'tr' ? pos.x - w : (a === 'tc' || a === 'cc') ? pos.x - w / 2 : pos.x;
    const t = a === 'cc' ? pos.y - h / 2 : pos.y;
    return { l, t, w, h, empty: true };
}

function hudOn(L, show) {
    if (!L.hud) return true;
    if (show && show.hud && L.hud in show.hud) return !!show.hud[L.hud];
    return L.hudDefault !== false;
}

function reasonOf(L, el, reaction) {
    const sess = (S.lm && S.lm.get('session')) || {};
    const show = S.lm && S.lm.get('show');
    if (L.liveOnly && !sess.live) return '방송 꺼짐';
    if (L.hud && !hudOn(L, show)) return '스위치 꺼짐';
    if (reaction && L.hideInReaction) return '시그니처 도는 중';
    if (el.classList.contains('off')) return '숨김';
    return '';
}

function measureAll() {
    const d = fdoc();
    const cv = d && d.getElementById('canvas');
    if (!cv) return;
    const V = d.defaultView;
    const cr = cv.getBoundingClientRect();
    const k = (cr.width / CANVAS.w) || 1;
    const reaction = cv.classList.contains('reaction-mode');
    layers.forEach(L => {
        if (S.drag && S.drag.id === L.id && S.drag.moved) return;     // 끄는 중엔 손이 옮긴 상자 그대로
        const el = cellEl(L.id);
        S.boxes[L.id] = el ? measure(L, el, cr, k, reaction, V) : null;
    });
}
let measureQ = 0;
function measureSoon() {
    if (measureQ) return;
    measureQ = setTimeout(() => { measureQ = 0; measureAll(); renderSoon(); }, 40);
}

// ── 서버에 적기 ──
function setPend(id, v) { S.pend[id] = Object.assign(S.pend[id] || {}, v); }
function schedule(id, ms) {
    clearTimeout(S.timers[id]);
    S.timers[id] = setTimeout(() => flush(id), ms);
    S.save[id] = { st: 'busy', msg: '잠시 뒤 저장…' };
    renderSoon();
}
async function flush(id) {
    if (!id) return;
    clearTimeout(S.timers[id]);
    delete S.timers[id];
    const p = S.pend[id];
    if (!p) return;
    delete S.pend[id];
    const data = Object.assign({ id }, p);
    S.sent++;
    S.save[id] = { st: 'busy', msg: '저장하는 중…' };
    renderSoon();
    const r = await S.lm.cmd('layout.set', data);
    if (r && r.ok) {
        S.save[id] = { st: 'ok', msg: '저장됨 ✓ 방송판이 따라왔어요' };
    } else {
        const msg = (r && r.error) || '저장하지 못했어요';
        S.save[id] = { st: 'bad', msg };
        toast(nameOf(id) + ' — ' + msg, true);
        revertToSaved(id);
    }
    renderSoon();
}
function flushAll() { Object.keys(S.pend).forEach(flush); }

/* 저장에 실패하면 이 화면의 칸을 서버에 적힌 자리로 되돌린다(표의 기본 + 서버 값) */
function revertToSaved(id) {
    const L = byId.get(id), el = cellEl(id);
    if (!L || !el || S.pend[id]) return;
    const o = S.layout[id] || {};
    livePlace(el, L, typeof o.x === 'number' ? o.x : L.x, typeof o.y === 'number' ? o.y : L.y,
        typeof o.scale === 'number' ? o.scale : (L.scale || 1));
    measureSoon();
}

/* 방송판이 layout 을 받아 자리를 다시 잡은 직후 — 아직 안 보낸 값 · 끄는 중인 자리를 다시 얹는다
   (다른 위젯이 저장되면 방송판은 모든 칸을 다시 놓는다 → 그대로 두면 방금 화살표로 옮긴 칸이 잠깐 튄다) */
function reapplyLive() {
    Object.keys(S.pend).forEach(id => {
        const L = byId.get(id), el = cellEl(id), p = S.pend[id];
        if (!L || !el) return;
        const pos = readPos(L, el);
        livePlace(el, L, typeof p.x === 'number' ? p.x : pos.x, typeof p.y === 'number' ? p.y : pos.y, scaleOf(L));
    });
    const d = S.drag;
    if (d && d.moved) {
        const L = byId.get(d.id);
        livePlace(cellEl(d.id), L, d.x, d.y, scaleOf(L));
    }
}

// ── 고르기 · 옮기기 · 크기 ──
function select(id, fromCanvas) {
    if (id === S.sel) return;
    if (S.sel) flush(S.sel);              // 앞의 것을 기다리지 말고 바로 저장
    S.sel = id || null;
    S.confirmAll = false;
    renderSoon();
    if (id && fromCanvas) {
        const row = document.querySelector('.wrow[data-id="' + id + '"]');
        if (row && row.scrollIntoView) row.scrollIntoView({ block: 'nearest' });
    }
}

function nudge(id, dx, dy) {
    const L = byId.get(id), el = cellEl(id);
    if (!L || !el) return;
    const pos = readPos(L, el);
    const x = clampX(pos.x + dx), y = clampY(pos.y + dy);
    livePlace(el, L, x, y, scaleOf(L));
    setPend(id, { x, y });
    shiftBox(id, x - pos.x, y - pos.y, x, y);
    schedule(id, SEND_KEY_MS);
}

function shiftBox(id, dx, dy, x, y) {
    const b = S.boxes[id];
    if (!b) return;
    S.boxes[id] = Object.assign({}, b, { l: b.l + dx, t: b.t + dy, x, y });
    renderSoon();
}

function setXY(id, x, y) {
    const L = byId.get(id), el = cellEl(id);
    if (!L || !el) return;
    const pos = readPos(L, el);
    x = clampX(x); y = clampY(y);
    livePlace(el, L, x, y, scaleOf(L));
    setPend(id, { x, y });
    shiftBox(id, x - pos.x, y - pos.y, x, y);
    flush(id);
}

function applyScale(id, s, waitMs) {
    const L = byId.get(id), el = cellEl(id);
    if (!L || !el) return;
    s = clampS(s);
    const pos = readPos(L, el);
    livePlace(el, L, pos.x, pos.y, s);
    const v = { scale: s };
    const o = S.layout[id] || {}, p = S.pend[id] || {};
    // 따라 붙는 칸(below — 후원 순위): 방송판은 '손으로 옮긴 칸은 따라가지 않고 표의 y' 를 쓴다.
    // 크기만 적으면 표의 y 로 튀므로, 지금 보이는 자리도 같이 적는다(그 자리에 붙박인다).
    if (L.below && typeof o.y !== 'number' && typeof p.y !== 'number') { v.x = Math.round(pos.x); v.y = Math.round(pos.y); }
    setPend(id, v);
    if (waitMs) schedule(id, waitMs); else flush(id);
    measureSoon();
}

async function resetOne(id) {
    if (!id) return;                       // ⚠️ id 없이 보내면 서버는 '전부' 되돌린다
    clearTimeout(S.timers[id]);
    delete S.timers[id];
    delete S.pend[id];
    S.sent++;
    S.save[id] = { st: 'busy', msg: '되돌리는 중…' };
    renderSoon();
    const r = await S.lm.cmd('layout.reset', { id });
    S.save[id] = r && r.ok ? { st: 'ok', msg: '기본 자리로 돌아갔어요' } : { st: 'bad', msg: (r && r.error) || '되돌리지 못했어요' };
    if (!(r && r.ok)) toast(S.save[id].msg, true);
    measureSoon();
}

async function resetAll() {
    Object.keys(S.timers).forEach(id => clearTimeout(S.timers[id]));
    S.timers = {};
    S.pend = {};
    S.confirmAll = false;
    S.sent++;
    const r = await S.lm.cmd('layout.reset', { all: true });
    if (r && r.ok) toast('모든 위젯이 기본 자리로 돌아갔어요');
    else toast((r && r.error) || '되돌리지 못했어요', true);
    S.save = {};
    measureSoon();
}

// ── 유리판(누르기 · 끌기) ──
const glass = $('glass');
const inner = $('stage-inner');

function toCanvas(e) {
    const r = inner.getBoundingClientRect();
    return { x: (e.clientX - r.left) / S.k, y: (e.clientY - r.top) / S.k };
}
function pickable(id) {
    const b = S.boxes[id];
    if (!b) return false;
    if (id === S.sel) return true;
    if (b.hidden && !S.showHidden) return false;
    if (!b.hidden && b.empty && !S.showEmpty) return false;     // 안 보이는 빈 칸이 눌리면 안 된다(목록에서 고르면 된다)
    return b.w * b.h < BIG_AREA * CANVAS.w * CANVAS.h;
}
function hit(id, p) {
    const b = S.boxes[id];
    if (!b) return false;
    const pad = 4 / S.k;                   // 화면 4px 여유 — 얇은 막대(게이지)도 잡히게
    return p.x >= b.l - pad && p.x <= b.l + b.w + pad && p.y >= b.t - pad && p.y <= b.t + b.h + pad;
}
/* 누른 자리의 칸 — 고른 칸이 그 자리에 있으면 그것.
   아니면 ① 지금 보이는 것 먼저(눈에 보이는 판을 눌렀는데 그 위의 빈 칸이 잡히면 안 된다) ② 그중 가장 작은 것(큰 판 위의 작은 딱지).
   빈 칸 · 숨은 칸은 그 자리에 보이는 것이 없을 때만 — 겹쳐 있으면 목록에서 고른 뒤 끌면 된다(고른 칸이 먼저 잡힌다). */
function pick(p) {
    if (S.sel && pickable(S.sel) && hit(S.sel, p)) return S.sel;
    let best = null, key = [2, Infinity];
    layers.forEach(L => {
        if (!pickable(L.id) || !hit(L.id, p)) return;
        const b = S.boxes[L.id];
        const k = [b.hidden || b.empty ? 1 : 0, Math.max(1, b.w * b.h)];
        if (k[0] < key[0] || (k[0] === key[0] && k[1] < key[1])) { key = k; best = L.id; }
    });
    return best;
}

glass.addEventListener('pointerdown', e => {
    if (e.button !== 0 || !S.frameReady) return;
    if (document.activeElement && document.activeElement.blur) document.activeElement.blur();   // 화살표가 입력칸으로 가지 않게
    const p = toCanvas(e);
    const id = pick(p);
    if (!id) { select(null); return; }
    select(id, true);
    const L = byId.get(id), el = cellEl(id);
    if (!L || !el) return;
    const pos = readPos(L, el);
    S.drag = { id, pid: e.pointerId, cx: e.clientX, cy: e.clientY, x0: pos.x, y0: pos.y, x: pos.x, y: pos.y,
        box0: Object.assign({}, S.boxes[id]), moved: false };
    try { glass.setPointerCapture(e.pointerId); } catch (x) {}
    e.preventDefault();
});

glass.addEventListener('pointermove', e => {
    const d = S.drag;
    if (!d) {
        if (!S.frameReady) return;
        const id = pick(toCanvas(e));
        glass.classList.toggle('can-grab', !!id);
        if (id !== S.hover) { S.hover = id; renderSoon(); }
        return;
    }
    if (e.pointerId !== d.pid) return;
    const sx = e.clientX - d.cx, sy = e.clientY - d.cy;
    if (!d.moved && Math.hypot(sx, sy) < DRAG_START_PX) return;
    d.moved = true;
    glass.classList.add('dragging');
    const L = byId.get(d.id);
    const x = clampX(d.x0 + sx / S.k), y = clampY(d.y0 + sy / S.k);
    if (x === d.x && y === d.y) return;
    d.x = x; d.y = y;
    livePlace(cellEl(d.id), L, x, y, scaleOf(L));          // 이 화면의 방송판만 — 서버에는 아직 안 보낸다
    const b = d.box0;
    S.boxes[d.id] = Object.assign({}, b, { l: b.l + (x - d.x0), t: b.t + (y - d.y0), x, y });
    renderSoon();
});

function endDrag(e, cancel) {
    const d = S.drag;
    if (!d || e.pointerId !== d.pid) return;
    S.drag = null;
    glass.classList.remove('dragging');
    try { glass.releasePointerCapture(e.pointerId); } catch (x) {}
    if (!d.moved) return;
    if (cancel) {                           // 끌다가 끊김(폰 스크롤 등) — 원래 자리로
        const L = byId.get(d.id);
        livePlace(cellEl(d.id), L, d.x0, d.y0, scaleOf(L));
        measureSoon();
        return;
    }
    if (d.x !== d.x0 || d.y !== d.y0) {
        setPend(d.id, { x: d.x, y: d.y });
        flush(d.id);                         // 손을 뗄 때 한 번
    }
    measureSoon();
}
glass.addEventListener('pointerup', e => endDrag(e, false));
glass.addEventListener('pointercancel', e => endDrag(e, true));
glass.addEventListener('pointerleave', () => { if (!S.drag && S.hover) { S.hover = null; renderSoon(); } });

document.addEventListener('keydown', e => {
    if (document.body.dataset.view !== 'edit') return;
    const tg = e.target;
    if (tg && (tg.tagName === 'INPUT' || tg.tagName === 'TEXTAREA' || tg.tagName === 'SELECT' || tg.isContentEditable)) return;
    if (e.key === 'Escape') { if (S.confirmAll) { S.confirmAll = false; renderSoon(); } else select(null); return; }
    if (!S.sel || S.drag) return;
    const dir = { ArrowLeft: [-1, 0], ArrowRight: [1, 0], ArrowUp: [0, -1], ArrowDown: [0, 1] }[e.key];
    if (!dir) return;
    e.preventDefault();
    const step = e.shiftKey ? 10 : 1;
    nudge(S.sel, dir[0] * step, dir[1] * step);
});

// ── 오른쪽: 고른 위젯 · 목록 ──
const inX = $('in-x'), inY = $('in-y'), inScale = $('in-scale');

function readNum(input) {
    const v = parseFloat(String(input.value).replace(/,/g, ''));
    return isFinite(v) ? v : null;
}
[inX, inY].forEach(inp => {
    inp.addEventListener('change', () => {
        const id = S.sel, L = byId.get(id);
        if (!L) return;
        const pos = readPos(L, cellEl(id));
        const x = inp === inX ? readNum(inX) : pos.x;
        const y = inp === inY ? readNum(inY) : pos.y;
        if (x === null || y === null) { renderSoon(); return; }
        setXY(id, x, y);
    });
    inp.addEventListener('keydown', e => { if (e.key === 'Enter') inp.blur(); });
});
inScale.addEventListener('input', () => { if (S.sel) applyScale(S.sel, parseFloat(inScale.value), SEND_SLIDER_MS); });
inScale.addEventListener('change', () => { if (S.sel) flush(S.sel); });
inScale.addEventListener('pointerup', () => setTimeout(() => inScale.blur(), 0));      // 놓은 뒤 화살표는 다시 '옮기기'
document.querySelectorAll('[data-scale]').forEach(b => b.addEventListener('click', () => {
    if (S.sel) applyScale(S.sel, parseFloat(b.dataset.scale), 0);
}));
$('btn-reset-one').addEventListener('click', () => resetOne(S.sel));
$('btn-reset-all').addEventListener('click', () => { S.confirmAll = !S.confirmAll; renderSoon(); });
$('btn-reset-all-no').addEventListener('click', () => { S.confirmAll = false; renderSoon(); });
$('btn-reset-all-yes').addEventListener('click', resetAll);
$('btn-reload').addEventListener('click', () => location.reload());

const togHidden = $('tog-hidden'), togEmpty = $('tog-empty'), togGhost = $('tog-ghost');
S.showHidden = store.get('hidden', true);
S.showEmpty = store.get('empty', false);
S.ghost = store.get('ghost', false);
togHidden.checked = S.showHidden;
togEmpty.checked = S.showEmpty;
togGhost.checked = S.ghost;
togHidden.addEventListener('change', () => { S.showHidden = togHidden.checked; store.set('hidden', S.showHidden); renderSoon(); });
togEmpty.addEventListener('change', () => { S.showEmpty = togEmpty.checked; store.set('empty', S.showEmpty); renderSoon(); });
togGhost.addEventListener('change', () => { S.ghost = togGhost.checked; store.set('ghost', S.ghost); applyGhost(); measureSoon(); });

/* 숨은 칸을 이 화면의 방송판에서만 흐리게 그린다(OBS · 다른 방송판에는 아무 영향 없음) */
function applyGhost() {
    const d = fdoc();
    if (!d || !d.head) return;
    let st = d.getElementById('lm2ed-ghost');
    if (S.ghost && !st) {
        st = d.createElement('style');
        st.id = 'lm2ed-ghost';
        st.textContent = 'html #canvas .layer.off, html #canvas.reaction-mode .layer.hide-in-reaction'
            + ' { visibility: visible !important; opacity: 0.35 !important; }';
        d.head.appendChild(st);
    } else if (!S.ghost && st) {
        st.remove();
    }
}

const wlist = $('wlist');
wlist.addEventListener('click', e => {
    const row = e.target.closest('.wrow');
    if (row) select(row.dataset.id);
});
wlist.addEventListener('keydown', e => {
    if (e.key !== 'Enter' && e.key !== ' ') return;
    const row = e.target.closest('.wrow');
    if (row) { e.preventDefault(); select(row.dataset.id); }
});

function stateOf(id) {
    const b = S.boxes[id];
    if (!S.frameReady) return { cls: '', text: '' };
    if (!b) return { cls: 'off', text: '방송판에 없음' };
    if (b.hidden) return { cls: 'off', text: b.reason || '숨김' };
    if (b.empty) return { cls: '', text: '지금 내용 없음' };
    return { cls: 'on', text: '보이는 중' };
}
const fmt = v => (Math.round(v * 10) / 10).toString();

/* 줄은 칸마다 한 번 만들고 글자 · 꼴만 고친다 — 통째로 다시 그리면 누르는 사이에 줄이 바뀌어 클릭이 사라진다 */
const rows = new Map();
function rowOf(L) {
    let r = rows.get(L.id);
    if (r) return r;
    const li = document.createElement('li');
    li.className = 'wrow';
    li.dataset.id = L.id;
    li.setAttribute('role', 'option');
    li.tabIndex = 0;
    li.innerHTML = '<span class="nm">' + esc(nameOf(L.id)) + '</span><span class="pos"></span>'
        + '<span class="chip moved" hidden>옮김</span><span class="chip st" hidden></span>';
    wlist.appendChild(li);
    r = { li, pos: li.querySelector('.pos'), moved: li.querySelector('.moved'), st: li.querySelector('.st'), sig: '' };
    rows.set(L.id, r);
    return r;
}
function renderList() {
    layers.forEach(L => {
        const r = rowOf(L);
        const b = S.boxes[L.id];
        const st = stateOf(L.id);
        const moved = !!S.layout[L.id] || !!S.pend[L.id];
        const pos = b ? fmt(b.x) + ', ' + fmt(b.y) : '';
        const sel = L.id === S.sel;
        const sig = [sel, b && b.hidden, pos, moved, st.cls, st.text].join('|');
        if (sig === r.sig) return;
        r.sig = sig;
        r.li.classList.toggle('sel', sel);
        r.li.classList.toggle('hid', !!(b && b.hidden));
        r.li.setAttribute('aria-selected', String(sel));
        r.pos.textContent = pos;
        r.moved.hidden = !moved;
        r.st.hidden = !st.text || st.cls === 'on';
        r.st.textContent = st.text;
        r.st.className = 'chip st ' + st.cls;
    });
    const moved = Object.keys(S.layout).length;
    $('moved-count').textContent = String(moved);
    $('btn-reset-all').disabled = !moved && !Object.keys(S.pend).length;
    $('confirm-all').hidden = !S.confirmAll;
}

function renderProps() {
    const id = S.sel, L = byId.get(id);
    $('empty-sel').hidden = !!L;
    $('sel-body').hidden = !L;
    if (!L) return;
    const b = S.boxes[id];
    const st = stateOf(id);
    $('sel-name').textContent = nameOf(id);
    const chip = $('sel-state');
    chip.textContent = st.text;
    chip.className = 'chip ' + st.cls;
    chip.hidden = !st.text;
    const a = L.anchor || 'tl';
    $('sel-anchor').textContent = '기준점: ' + (ANCHOR_TEXT[a] || a) + ' · 기본 자리 ' + L.x + ', ' + L.y
        + (L.below ? ' (기본은 ' + nameOf(L.below) + ' 아래에 붙어 따라감)' : '');
    const sc = scaleOf(L);
    if (b && document.activeElement !== inX) inX.value = String(Math.round(b.x));
    if (b && document.activeElement !== inY) inY.value = String(Math.round(b.y));
    if (document.activeElement !== inScale) inScale.value = String(sc);
    $('scale-val').textContent = sc.toFixed(2) + '배';
    const can = !!b;
    [inX, inY, inScale].forEach(i => { i.disabled = !can; });
    document.querySelectorAll('[data-scale]').forEach(x => { x.disabled = !can; });
    $('btn-reset-one').disabled = !S.layout[id] && !S.pend[id];
    const sv = S.save[id];
    const el = $('save-state');
    el.textContent = sv ? sv.msg : (S.layout[id] ? '옮겨 둔 자리예요' : '기본 자리예요');
    el.className = 'save-state small' + (sv && sv.st === 'ok' ? ' ok' : sv && sv.st === 'bad' ? ' bad' : '');
}

// 유리판 그림 — 칸마다 div 하나를 다시 쓴다
const gEls = new Map();
function renderGlass() {
    const seen = new Set();
    layers.forEach(L => {
        const id = L.id, b = S.boxes[id];
        const isSel = id === S.sel, isHover = id === S.hover && !isSel;
        let show = !!b && (isSel || isHover || (b.hidden && S.showHidden) || (!b.hidden && b.empty && S.showEmpty));
        if (show && !isSel && b.w * b.h >= BIG_AREA * CANVAS.w * CANVAS.h) show = false;   // 캔버스를 다 덮는 칸은 고를 때만
        if (!show) return;
        seen.add(id);
        let g = gEls.get(id);
        if (!g) {
            g = document.createElement('div');
            g.className = 'gbox';
            g.innerHTML = '<span class="gtag"></span>';
            glass.appendChild(g);
            gEls.set(id, g);
        }
        g.style.left = b.l + 'px';
        g.style.top = b.t + 'px';
        g.style.width = Math.max(2, b.w) + 'px';
        g.style.height = Math.max(2, b.h) + 'px';
        g.classList.toggle('hid', !!b.hidden);
        g.classList.toggle('emp', !b.hidden && !!b.empty);
        g.classList.toggle('sel', isSel);
        g.classList.toggle('hover', isHover);
        g.classList.toggle('flip', b.t < 40);
        g.classList.toggle('right', b.l + b.w / 2 > CANVAS.w / 2);
        const tag = g.firstChild;
        const showTag = isSel || isHover;
        tag.hidden = !showTag;
        if (showTag) {
            let t = nameOf(id);
            if (isSel) t += ' · x ' + fmt(b.x) + ' · y ' + fmt(b.y) + (b.scale !== 1 ? ' · ' + b.scale.toFixed(2) + '배' : '');
            if (b.hidden) t += ' · ' + (b.reason || '숨김');
            if (tag.textContent !== t) tag.textContent = t;
        }
    });
    gEls.forEach((g, id) => { if (!seen.has(id)) { g.remove(); gEls.delete(id); } });
    // 기준점 표시 — 고른 칸의 x · y 가 가리키는 점
    let pin = glass.querySelector('.gpin');
    const b = S.sel && S.boxes[S.sel];
    if (b) {
        if (!pin) { pin = document.createElement('div'); pin.className = 'gpin'; glass.appendChild(pin); }
        pin.style.left = b.x + 'px';
        pin.style.top = b.y + 'px';
    } else if (pin) {
        pin.remove();
    }
}

function renderPills() {
    const sess = (S.lm && S.lm.get('session')) || {};
    const p = $('pill-live');
    p.hidden = document.body.dataset.view !== 'edit';
    p.textContent = sess.live ? '● 방송 중' : '방송 꺼짐';
    p.className = 'pill' + (sess.live ? ' live' : '');
}

let renderQ = 0;
function renderSoon() {
    if (renderQ) return;
    renderQ = requestAnimationFrame(() => { renderQ = 0; render(); });
}
function render() {
    renderGlass();
    renderList();
    renderProps();
    renderPills();
}

// ── 무대 크기 — 남는 자리에 1080×1920 을 비율 그대로 ──
const wrap = $('stage-wrap'), box = $('stage-box'), hint = $('stage-hint');
function fit() {
    const cs = getComputedStyle(wrap);
    const W = wrap.clientWidth - parseFloat(cs.paddingLeft) - parseFloat(cs.paddingRight);
    const H = wrap.clientHeight - parseFloat(cs.paddingTop) - parseFloat(cs.paddingBottom) - (hint.offsetHeight || 0) - 8;
    const k = Math.max(0.05, Math.min(W / CANVAS.w, H / CANVAS.h));
    S.k = k;
    box.style.width = Math.floor(CANVAS.w * k) + 'px';
    box.style.height = Math.floor(CANVAS.h * k) + 'px';
    inner.style.transform = `scale(${k})`;
    glass.style.setProperty('--k', (1 / k).toFixed(4));
    renderSoon();
}
try { new ResizeObserver(fit).observe(wrap); } catch (e) { window.addEventListener('resize', fit); }

// ── 시작 ──
function setView(v) { document.body.dataset.view = v; if (v === 'edit') fit(); renderPills(); }

function toast(msg, bad) {
    const t = $('toast');
    t.textContent = msg;
    t.className = 'toast' + (bad ? ' bad' : '');
    t.hidden = false;
    clearTimeout(toast.tm);
    toast.tm = setTimeout(() => { t.hidden = true; }, bad ? 4000 : 2200);
}

function startFrame() {
    frame.addEventListener('load', waitOverlay);
    frame.src = '/overlay/?monitor=1';
}
function waitOverlay() {
    const t0 = Date.now();
    const tick = () => {
        const w = fwin(), d = fdoc();
        const ov = w && w.__lmOverlay;
        if (ov && d && d.querySelector('[data-layer]')) { hookOverlay(ov); return; }
        if (Date.now() - t0 < 20000) setTimeout(tick, 100);
        else toast('방송판을 불러오지 못했어요 — 새로고침해 주세요', true);
    };
    tick();
}
function hookOverlay(ov) {
    S.frameReady = true;
    // ⚠️ 방송판의 applyLayout 이 먼저 등록돼 있다 → 이 알림은 방송판이 자리를 다시 잡은 '뒤' 에 온다
    ov.lm.on('layout', () => { reapplyLive(); measureSoon(); });
    ov.lm.on('session', measureSoon);
    ov.lm.on('show', measureSoon);
    if (ov.stage) {
        if (ov.stage.onMode) ov.stage.onMode(measureSoon);
        if (ov.stage.onLayout) ov.stage.onLayout(measureSoon);
    }
    applyGhost();
    measureAll();
    render();
}

/* 3번에 한 번 정도(0.3초) 다시 잰다 — 판 줄 수 · 알림 · 애니메이션으로 크기가 바뀌어도 테두리가 따라가게.
   편집 화면에서 소리가 나지 않게 미리보기의 소리도 끈다(방송판은 ?monitor=1 이라 시그니처는 이미 꺼져 있다). */
setInterval(() => {
    if (!S.frameReady || document.hidden) return;
    if (!S.drag) measureAll();
    const d = fdoc();
    if (d) d.querySelectorAll('audio, video').forEach(m => { if (!m.muted) m.muted = true; });
    renderSoon();
}, 300);

// 창을 닫거나 다른 탭으로 가면 기다리던 값을 바로 보낸다
document.addEventListener('visibilitychange', () => { if (document.hidden) flushAll(); });
window.addEventListener('pagehide', flushAll);

function boot() {
    const lm = LM.connect({ kind: 'editor' });
    S.lm = lm;
    let started = false;
    lm.onStatus(st => {
        const c = $('pill-conn');
        c.textContent = st === 'live' ? '연결됨' : st === 'down' ? '끊김 — 다시 붙는 중' : '연결 중…';
        c.className = 'pill' + (st === 'live' ? ' ok' : st === 'down' ? ' bad' : '');
        if (st !== 'live') return;
        if (!lm.authed) { setView('login'); return; }
        setView('edit');
        if (!started) { started = true; startFrame(); }
    });
    lm.on('layout', l => {
        S.layout = (l && l.widgets && typeof l.widgets === 'object') ? l.widgets : {};
        Object.keys(S.save).forEach(id => { if (S.save[id].st === 'ok' && !S.layout[id] && !S.pend[id]) delete S.save[id]; });
        renderSoon();
    });
    lm.on('session', renderSoon);
    lm.on('show', renderSoon);
}

// 점검용(콘솔 · 자동 검사) — 화면 동작에는 안 쓴다
window.__lmEditor = {
    S, layers, select: id => select(id), measureAll,
    flushAll,               // 🎚️ settings.js — 슬롯 저장 전에 아직 안 보낸 자리를 먼저 보낸다(명령은 보낸 순서대로 처리된다)
    frameWin: fwin,         // 🎚️ settings.js — 미리보기 방송판(시그니처 미리보기)
    box: id => S.boxes[id] || null,
    stageRect: () => { const r = inner.getBoundingClientRect(); return { left: r.left, top: r.top, k: S.k }; },
};

boot();
