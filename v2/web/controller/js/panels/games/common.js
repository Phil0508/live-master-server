/* 🎮 게임 탭 공용 — 서버 시계 · 무대 뺏기 확인 · 시그니처 목록 · 옛 주소 부르기 · 칸 맞추기 · 두세 칸 단추.

   ⚠️ 다시 그릴 때 입력 중인 칸을 덮지 않는다(syncVal) — 손이 올라가 있거나, 서버 값이 그대로인데 손으로 고쳐 둔 칸은 그대로 둔다.
   ⚠️ 무대는 하나다. 슬롯 · 룰렛이 돌거나 핀볼이 굴러가는 중에 다른 판을 올리면 그 판이 방송에서 잘린다 — 한 번 묻는다(옛 qzCall). */
import { h } from '../../util.js';

export const STAGE_LABEL = {
    match: '대결', pinball: '핀볼', dicegame: '주사위', siggame: '시그뒤집기', roulette: '룰렛',
    slot: '슬롯', home_race: '퇴근빵', hell: '지옥탈출', quiz: '퀴즈',
};

/* ── 서버 시계 ── 타이머는 서버 시각(ms)으로 온다. 이 PC 시계가 어긋나 있으면 남은 시간이 통째로 틀린다.
   공용 연결(lm.serverNow)이 재 둔 차이를 쓴다. 그게 없으면(옛 client.js) GET /api/time 으로 직접 잰다(왕복 절반을 빼서). */
let lmRef = null, offset = 0, measured = false, measuring = null;
export function useLm(lm) {
    if (lm && lm !== lmRef) {
        lmRef = lm;
        // 시그니처 관리에서 등록 · 고치기 · 지우기를 하면 sig_admin.ver 가 오른다 — 받아 둔 목록을 새로 받는다(↻ 안 눌러도)
        lm.on('sig_admin', sa => {
            const v = Number(sa && sa.ver) || 0;
            if (sigVer !== null && v !== sigVer && sigRows) loadSigs(true);
            sigVer = v;
        });
    }
}
async function measure() {
    if (measuring) return measuring;
    measuring = (async () => {
        try {
            const t0 = Date.now();
            const r = await fetch('/api/time', { cache: 'no-store' });
            const t1 = Date.now();
            const d = await r.json();
            if (d && d.now) { offset = Number(d.now) - (t0 + t1) / 2; measured = true; }
        } catch (e) { /* 못 재면 이 PC 시계 그대로 — 다음에 다시 */ }
        measuring = null;
    })();
    return measuring;
}
export function serverNow() {
    if (lmRef && typeof lmRef.serverNow === 'function') return lmRef.serverNow();
    if (!measured && !measuring) measure();
    return Date.now() + offset;
}
setInterval(() => { if (!(lmRef && typeof lmRef.serverNow === 'function')) measure(); }, 5 * 60 * 1000);

/** 초 → '03:07' */
export function mmss(sec) {
    const s = Math.max(0, Math.floor(Number(sec) || 0));
    return String(Math.floor(s / 60)).padStart(2, '0') + ':' + String(s % 60).padStart(2, '0');
}

/* ── 무대 뺏기 확인 ── */
export function stageBusy(slices) {
    const st = ((slices || {}).show || {}).stage;
    if (st === 'slot') {
        const s = slices.slot || {};
        if (s.phase === 'spinning' && serverNow() < Number(s.ends_at || 0) + 300) return '슬롯이 돌고';
    }
    if (st === 'roulette') {
        const r = slices.roulette || {};
        if (r.phase === 'spinning' || r.phase === 'stopping') return '룰렛이 돌고';
    }
    if (st === 'pinball' && (slices.pinball || {}).running) return '핀볼이 굴러가고';
    return '';
}

/** target 판을 무대에 올려도 되나 — 다른 판이 한창이면 한 번 묻는다. 같은 판이면 안 묻는다. */
export async function okToTake(ctx, target, what) {
    const slices = ctx.slices || {};
    const st = (slices.show || {}).stage;
    if (st === target) return true;
    const busy = stageBusy(slices);
    if (!busy) return true;
    return ctx.confirm({
        title: `${busy} 있어요`,
        body: `지금 ${what}을(를) 띄우면 ${STAGE_LABEL[st] || st} 판이 방송 화면에서 잘립니다.\n그래도 띄울까요?`,
        ok: '그래도 띄우기', cancel: '기다리기',
    });
}

/* ── 시그니처 목록(바깥 왕복이라 서버가 10분 기억한다) ── 탭 여럿이 같이 쓴다 */
let sigRows = null, sigLoading = null, sigErr = '', sigVer = null;
export function sigsNow() { return sigRows; }
export function sigsError() { return sigErr; }
export function loadSigs(force) {
    if (sigRows && !force) return Promise.resolve(sigRows);
    if (sigLoading) return sigLoading;
    sigLoading = (async () => {
        try {
            const r = await fetch('/api/signatures', { cache: 'no-store' });
            const d = await r.json().catch(() => ({}));
            if (r.ok && d && d.status === 'success') {
                sigRows = (d.signatures || []).filter(s => s && s.id != null);
                sigErr = '';
            } else {
                sigErr = (d && d.message) || ('시그니처 목록을 못 받았어요 (' + r.status + ')');
                if (!sigRows) sigRows = [];
            }
        } catch (e) {
            sigErr = '시그니처 목록을 못 받았어요 — 서버 연결을 확인해 주세요';
            if (!sigRows) sigRows = [];
        }
        sigLoading = null;
        return sigRows;
    })();
    return sigLoading;
}

/** 옛 주소(POST) — 답을 그대로 + 상태 번호. 서버가 준 까닭을 그대로 보여 주려고 message/error 를 같이 꺼낸다. */
export async function post(path, body) {
    try {
        const r = await fetch(path, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body || {}) });
        const d = await r.json().catch(() => ({}));
        return { status: r.status, data: d || {}, why: (d && (d.message || d.error)) || ('실패했습니다 (' + r.status + ')') };
    } catch (e) {
        return { status: 0, data: {}, why: '서버에 닿지 않습니다 — 다시 눌러 주세요' };
    }
}

/* ── 칸 맞추기 ── 손이 올라가 있거나(초점) 손으로 고쳐 둔 칸(서버 값이 그대로)은 덮지 않는다 */
export function syncVal(el, v) {
    const s = v == null ? '' : String(v);
    if (document.activeElement === el) return;
    if (el.dataset.sv === s) return;
    el.dataset.sv = s;
    el.value = s;
}

/** 그 칸의 값이 바뀌었을 때만 fn — render 마다 통째로 다시 그리지 않게 */
export function memo() {
    const seen = new Map();
    return (key, sig, fn) => {
        const s = typeof sig === 'string' ? sig : JSON.stringify(sig);
        if (seen.get(key) === s) return false;
        seen.set(key, s);
        fn();
        return true;
    };
}

/** 두세 칸 단추(하나만 켜짐) — set(v) 로 서버 값을 비춘다 */
export function seg(options, onPick, label) {
    const el = h('div', { class: 'gm-seg', role: 'radiogroup', 'aria-label': label || '' });
    const btns = options.map(([v, text, title]) => {
        const b = h('button', { type: 'button', class: 'gm-segb', 'data-v': v, role: 'radio', 'aria-checked': 'false', title: title || null,
            onclick: () => { if (!b.disabled) onPick(v); } }, text);
        el.append(b);
        return b;
    });
    return {
        el,
        set(v) { btns.forEach(b => { const on = b.dataset.v === String(v); b.classList.toggle('on', on); b.setAttribute('aria-checked', String(on)); }); },
        disable(on) { btns.forEach(b => { b.disabled = !!on; }); },
    };
}

/** 머리 줄 — 제목 · 상태 알약 · [방송에 띄우기] 단추 */
export function head(title, onAir) {
    const pill = h('span', { class: 'gm-pill' });
    const air = onAir ? h('button', { type: 'button', class: 'gm-air', 'aria-pressed': 'false', onclick: () => onAir(air.getAttribute('aria-pressed') !== 'true') },
        h('i', { 'aria-hidden': 'true' }), h('span', { class: 'gm-air-t' }, '방송에 띄우기')) : null;
    const el = h('div', { class: 'gm-head' }, h('h3', { class: 'gm-title' }, title), pill, h('span', { class: 'gm-sp' }), air);
    return {
        el, pill,
        setPill(text, kind) { pill.textContent = text || ''; pill.hidden = !text; pill.className = 'gm-pill' + (kind ? ' ' + kind : ''); },
        setAir(on, busy) {
            if (!air) return;
            air.setAttribute('aria-pressed', String(!!on));
            air.classList.toggle('on', !!on);
            air.querySelector('.gm-air-t').textContent = on ? '방송 중 · 내리기' : '방송에 띄우기';
            air.disabled = !!busy;
        },
    };
}

/** 큰 실행 단추(타일) */
export function tile(name, sub, onclick, cls) {
    const nm = h('span', { class: 'gm-tn' }, name);
    const sb = h('span', { class: 'gm-ts' }, sub || '');
    const b = h('button', { type: 'button', class: 'gm-tile' + (cls ? ' ' + cls : ''), onclick }, nm, sb);
    b.setName = t => { if (nm.textContent !== t) nm.textContent = t; };
    b.setSub = t => { if (sb.textContent !== t) sb.textContent = t; };
    return b;
}

/** 지금 무대 이름 */
export function stageOf(slices) { return ((slices || {}).show || {}).stage || null; }

/** 숫자 칸 — 글자 칸에 숫자 키패드(폰). type=number 는 휠로 값이 바뀌는 사고가 있어 쓰지 않는다 */
export function numInput(attrs) {
    return h('input', Object.assign({ type: 'text', inputmode: 'numeric', autocomplete: 'off', class: 'gm-in num' }, attrs || {}));
}

/** '1,000' · '+5' · '−3' → 정수 · 아니면 null */
export function toInt(v) {
    const t = String(v == null ? '' : v).trim().replace(/[−–—]/g, '-').replace(/[,\s]/g, '');
    if (!/^[+-]?\d{1,9}$/.test(t)) return null;
    return parseInt(t, 10);
}

/** 화면에 보이는가(탭이 열려 있고 방송 중 화면) — 시계 돌리기를 아낀다 */
export function shown(el) { return !!(el && el.isConnected && el.offsetParent !== null); }

/** Enter(한글 조합 중이 아닐 때만) */
export function onEnter(el, fn) {
    el.addEventListener('keydown', e => {
        if (e.key !== 'Enter' || e.isComposing || e.keyCode === 229) return;
        e.preventDefault();
        fn(e);
    });
}

/** 플레이어 이름(번외 판이 켜져 있으면 번외 명단) */
export function rosterNames(slices) {
    const p = (slices || {}).players || {};
    return ((p.extra_active ? p.extra : p.list) || []).map(r => String(r.name || '').trim()).filter(Boolean);
}
