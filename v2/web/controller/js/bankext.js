/* 🏦 머리줄 '계좌' 칩 · 계좌 입금 띠 — 옛 controller.html #bank-chip · #bank-strips(10-16)를 옮겼다.
   대표님 10-16 "소리보단 화면으로" · "컨트롤러 창에서는 계좌 알림이 안 뜨더라" → ⚠️ 소리는 절대 내지 않는다. 눈으로만 알린다.
   alarm.js 의 틀을 그대로 쓴다 — 칩은 [방송 화면] [후원 받기] 옆 같은 점(.pf-chip · data-lv),
   띠는 상태 줄의 같은 경보 띠(alarm.js bandAdd · bandRemove — 시안 B 10-17, 머리줄 밑 따로 띠 없음).

   GET /api/bank/ext(로그인) — 은행 확장이 25초마다 서버에 실어 보낸 상자 내용 · 기다리는 명령 · 미처리 수 · 가장 새 카드.
     · 10초마다 + 비공개 조각 bank.ver 가 바뀔 때 바로(새 입금 · 송출 · 숨김). 방송판(로그인 없음)은 이 조각을 못 받는다.
   칩  — 초록 연결 · 노랑 주의 · 빨강 끊김 · 회색 꺼짐. 안 쓰는 동안(연결 전 · 3시간 조용)은 숨긴다. 글자엔 미처리 수만.
         누르면 🖥️ 시스템 탭의 은행 확장 거울 칸으로.
   빨간 띠(bank-dead) — 은행 확장 끊김(신호 90초 없음 · 확장이 스스로 '끊김' 보고) = 계좌 입금을 못 받는 중. 다시 붙으면 저절로 내려간다.
   초록 띠(bank-new) — 새 입금(가장 새 카드가 바뀌면) 25초. 처음 읽을 때는 띄우지 않는다(예전 것이 쏟아지지 않게).
   시스템 탭 거울(panels/ops/bankmirror.js)도 이 모듈이 읽은 것을 같이 쓴다(onExt). */
import { h } from './util.js';
import { judgeExt, chipView, deadBand, newBand, newestCheck, extCmdBody, NEW_BAND_MS } from './bankcore.js';
import { bandAdd, bandRemove } from './alarm.js';

const GAP = 10000;
const st = { data: null, known: null, busy: false, at: 0, enabled: false, seenVer: null, subs: new Set() };
let ui = null, ctxRef = null;

/** 지금 읽어 둔 것 {data, judge} */
export function extNow() {
    return { data: st.data, judge: judgeExt(st.data, Date.now()) };
}

/** 거울 칸 등이 새로 읽을 때마다 불린다 — 돌려받는 함수로 그만 듣는다 */
export function onExt(fn) {
    st.subs.add(fn);
    return () => st.subs.delete(fn);
}

export async function loadExt(force) {
    if (st.busy || (!force && Date.now() - st.at < GAP - 300)) return;
    st.busy = true;
    st.at = Date.now();
    try {
        const r = await fetch('/api/bank/ext', { cache: 'no-store', credentials: 'same-origin' });
        if (r.ok) {
            const d = await r.json();
            if (d && d.status === 'success') {
                st.data = d;
                const c = newestCheck(st.known, d.newest && d.newest.id);
                st.known = c.known;
                if (c.show) showNew(d.newest, d.new);
            }
        }
    } catch (e) { /* 다음에 */ }
    st.busy = false;
    for (const fn of st.subs) { try { fn(st.data); } catch (e) { console.error('[은행 확장 거울]', e); } }
    paint();
}

/** 조종실 → 확장 명령(enable · interval · rebase · press) — 확장이 다음 신호(25초 안)에 받아 간다 */
export async function extCmd(ctx, t, v) {
    const w = ((st.data || {}).link || {}).web;
    const body = extCmdBody(t, v, (w && w.state) || {});
    try {
        const r = await fetch('/api/bank/ext/cmd', { method: 'POST', credentials: 'same-origin', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
        const d = await r.json().catch(() => ({}));
        if (!r.ok) { ctx.toast(d.message || ('실패했어요 (' + r.status + ')'), 'err'); return false; }
        ctx.toast('확장에 보냈어요 — 25초 안에 반영돼요', 'ok');
        loadExt(true);
        setTimeout(() => loadExt(true), 30000);
        return true;
    } catch (e) {
        ctx.toast('통신 실패 — 다시 눌러 주세요', 'err');
        return false;
    }
}

/** 🖥️ 시스템 탭의 은행 확장 거울 칸 열기 */
export function openBankExt() {
    const b = document.querySelector('.tabbar .tab[data-tab="ops-system"]');
    if (b) b.click();
    setTimeout(() => {
        const box = document.querySelector('[data-bank-ext]');
        if (box) { try { box.scrollIntoView({ block: 'start', behavior: 'smooth' }); } catch (e) { box.scrollIntoView(); } }
    }, 120);
}

/** 💸 후원 콘솔 탭 열기 */
function openConsole() {
    const b = document.querySelector('.tabbar .tab[data-tab="ops-console"]');
    if (b) b.click();
    setTimeout(() => {
        const box = document.querySelector('.tabpanel[data-panel="ops-console"] .bank');
        if (box) { try { box.scrollIntoView({ block: 'start', behavior: 'smooth' }); } catch (e) { box.scrollIntoView(); } }
    }, 120);
}

function showNew(it, n) {
    if (!ui || !it || !st.enabled) return;
    const b = newBand(it, n);
    bandAdd('bank-new', { level: 'ok', title: b.t, sub: b.s, ttl: NEW_BAND_MS, close: true, act: { label: '후원 콘솔 열기', fn: openConsole } });
}

function paint() {
    if (!ui) return;
    const j = judgeExt(st.data, Date.now());
    const c = chipView(j, st.data ? st.data.new : 0);
    const chipHidden = c.hidden || !st.enabled;
    if (ui.chip.hidden !== chipHidden) ui.chip.hidden = chipHidden;
    if (ui.chip.dataset.lv !== c.lv) ui.chip.dataset.lv = c.lv;
    if (ui.cT.textContent !== c.text) { ui.cT.textContent = c.text; ui.cTs.textContent = c.text; }
    ui.chip.title = c.title + ' — 누르면 은행 확장 거울';
    ui.chip.setAttribute('aria-label', c.title);
    const band = deadBand(j);
    if (band && st.enabled) bandAdd('bank-dead', { level: 'bad', title: band.t, sub: band.s, act: { label: '은행 확장 보기', fn: openBankExt } });
    else bandRemove('bank-dead');
    if (!st.enabled) bandRemove('bank-new');
}

/** before: 머리줄 오른쪽 묶음(점 칩이 그 앞에 선다) · hdrRoot: 머리줄 */
export function mountBankAlarm(before, hdrRoot, ctx) {
    ctxRef = ctx;
    const cT = h('span', { class: 't', 'aria-hidden': 'true' }, '계좌');
    const cTs = h('span', { class: 'ts', 'aria-hidden': 'true' }, '계좌');
    const chip = h('button', { type: 'button', class: 'st pf-chip bank-chip', 'data-lv': 'none', hidden: true, onclick: () => openBankExt() },
        h('i', { class: 'dot', 'aria-hidden': 'true' }), cT, cTs);
    // [방송 화면] [후원 받기] 점 옆에(alarm.js 가 만든 묶음) — 없으면 오른쪽 묶음 바로 앞
    const wrap = hdrRoot.querySelector('.pf-chips');
    if (wrap) wrap.append(chip);
    else hdrRoot.insertBefore(chip, before);

    ui = { chip, cT, cTs };

    setInterval(() => { if (st.enabled) { loadExt(false); paint(); } }, 1000);
    document.addEventListener('visibilitychange', () => { if (document.visibilityState === 'visible' && st.enabled) loadExt(true); });

    return {
        render(slices, status, view) {
            const on = (view === 'setup' || view === 'live') && !!(ctx.lm && ctx.lm.authed);
            const wasOn = st.enabled;
            st.enabled = on;
            if (!on) { paint(); return; }
            // 새 입금 · 송출 · 숨김 — 비공개 조각 bank 의 번호가 오르면 바로 다시 읽는다(10초 기다리지 않게)
            const v = Number(((slices || {}).bank || {}).ver) || 0;
            const bumped = st.seenVer !== null && v !== st.seenVer;
            st.seenVer = v;
            if (!wasOn || bumped) loadExt(true);
        },
    };
}
