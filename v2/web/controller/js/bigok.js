/* 🛡️ 큰 금액은 한 번 더 확인(10-17 bigok) — 손이 미끄러져 큰 후원을 엉뚱한 사람에게 주는 일을 막는다.

   언제 묻나 — 사람이 점수를 주는 모든 길(ctx.run 한 곳에서 거른다):
     pending.assign {id, name|names}   대기함 선수 단추 · 추천 단추 · 나눠 주기 · 폰 서랍 · AI 카드 [실행]
       → 그 후원 금액이 기준(won) 이상이면. 기여도 카드(kind 'contrib')는 기여도가 손 점수 기준(pts) 이상이면.
     score.add {name|target:'bottom', delta, contrib?}   점수판 손 점수 · 운영비 · 기여도 고치기 · Ctrl+K '밍밍 30' · AI 카드
       → |점수| 또는 |기여도| 가 손 점수 기준(pts) 이상이면(빼기도 묻는다).
   안 묻는 것: 조종실 오토파일럿(via 'ap') · 서버 자동 진행 — 기계 쪽은 상한 이상을 이미 보류한다.
   기준: 조각 bigok {won: 200000, pts: 20}(서버 · 비공개 — PC · 폰 같은 값), 0 = 그 확인은 끔. 조각이 아직 없으면 기본값으로 묻는다(안전한 쪽).

   상자: 화면 안 확인 상자(util.js confirmBox — 기본 손가락은 [취소], Esc · 바깥 누르기 = 취소). 받을 사람 이름을 크게,
         나눠 주기면 누구에게 몇 점인지 다. [모두 실행] 처럼 여러 건이면 한 상자에 다 보이고 한 번만 묻는다.
   ⚠️ alert() · confirm() 금지 · 소리 없음 · 바깥 글자(후원자 · 선수 이름)는 textContent 로만(h()).

   쓰는 법
     guardRun(run, getSlices, ask)  run 을 감싼다(main.js) — 큰 것이면 ask([need]) 를 기다리고, 아니면 바로 run.
                                    [취소] → {ok:false, cancelled:true, error} · 명령은 안 간다.
     needFor(slices, type, data)    물어야 하면 {who, amount, kind, rows:[{name, pts, contrib}]}, 아니면 null
     askBig(ctx, needs)             상자 한 번 → true([주기]) / false
     run(type, data, {bigOk:true})  이미 물어본 길(대기함 · AI 카드 묶음)은 다시 묻지 않게 */
import { h, num, manWon, splitPoints } from './util.js';

export const DEFAULTS = Object.freeze({ won: 200000, pts: 20 });
const KINDS = new Set(['pending.assign', 'score.add']);

/** 지금 기준 — 0 이면 끔 */
export function limits(slices) {
    const b = (slices && slices.bigok) || {};
    const pick = (v, d) => (v === undefined || v === null || v === '' || !Number.isFinite(Number(v)) ? d : Math.max(0, Math.trunc(Number(v))));
    return { won: pick(b.won, DEFAULTS.won), pts: pick(b.pts, DEFAULTS.pts) };
}

const absInt = v => Math.abs(Math.trunc(Number(v) || 0));

/** 물어야 하면 설명, 아니면 null */
export function needFor(slices, type, data) {
    if (!KINDS.has(type) || !data || typeof data !== 'object') return null;
    const L = limits(slices);
    if (type === 'pending.assign') {
        if (data.via === 'ap') return null;                       // 🚗 오토파일럿(기계) — 건드리지 않는다
        const it = ((slices && slices.pending) || []).find(x => x && x.id === data.id);
        if (!it || it.type === 'off_work') return null;          // 없는 후원은 서버가 거절한다
        const names = Array.isArray(data.names) ? data.names.map(String) : (data.name != null ? [String(data.name)] : []);
        if (!names.length) return null;
        const isC = it.kind === 'contrib';
        const amount = Math.trunc(Number(it.amount) || 0);
        const total = isC ? Math.trunc(Number(it.contrib) || 0) : manWon(amount);
        const big = isC ? (L.pts > 0 && Math.abs(total) >= L.pts) : (L.won > 0 && amount >= L.won);
        if (!big) return null;
        const parts = splitPoints(total, names.length);
        return { kind: isC ? 'contrib' : 'don', who: String(it.name || '익명'), amount,
                 rows: names.map((n, i) => isC ? { name: n, pts: 0, contrib: parts[i] } : { name: n, pts: parts[i], contrib: 0 }) };
    }
    // score.add — 손으로 넣는 점수
    if (L.pts <= 0) return null;
    const d = Math.trunc(Number(data.delta) || 0), c = Math.trunc(Number(data.contrib) || 0);
    if (absInt(d) < L.pts && absInt(c) < L.pts) return null;
    const bottom = data.target === 'bottom';
    const name = bottom ? '운영비' : String(data.name || '');
    return { kind: 'hand', who: '', amount: 0, extra: !bottom && data.list === 'extra',
             rows: [{ name, pts: d, contrib: c }] };
}

const signed = n => (n < 0 ? '−' + num(-n) : '+' + num(n));

/** 한 줄 글 — '밍밍 +50점' · '밍밍 기여도 +3' */
export function rowText(r) {
    const bits = [];
    if (r.pts) bits.push(signed(r.pts) + '점');
    if (r.contrib) bits.push('기여도 ' + signed(r.contrib));
    return bits.join(' · ') || '0점';
}

/** 상자 제목 — '영원 500,000원 → 밍밍에게 50점 줄까요?' */
export function titleOf(needs) {
    if (needs.length > 1) return `큰 점수 ${needs.length}건 — 모두 줄까요?`;
    const n = needs[0];
    const minus = n.rows.some(r => r.pts < 0 || r.contrib < 0);
    const verb = minus ? '뺄까요?' : '줄까요?';
    if (n.kind === 'hand') {
        const r = n.rows[0];
        return `${r.name}${n.extra ? ' (번외)' : ''} ${rowText(r)} — ${verb}`;      // '밍밍 +30점 — 줄까요?' · '밍밍 −30점 — 뺄까요?'
    }
    // 기여도 카드(주사위 · 슬롯 결과)는 돈이 0원 — '0원' 은 빼고 '슬롯 → 밍밍에게 기여도 25 줄까요?'
    const head = n.amount > 0 ? `${n.who} ${num(n.amount)}원 → ` : `${n.who} → `;
    if (n.rows.length > 1) return head + `${n.rows.length}명에게 나눠 ${verb}`;
    const r = n.rows[0];
    return head + `${r.name}에게 ${rowText(r).replace(/^\+/, '').replace(/^기여도 \+/, '기여도 ')} ${verb}`;     // '영원 500,000원 → 밍밍에게 50점 줄까요?'
}

/** 상자 속 — 받을 사람 이름을 크게, 나눠 주기면 사람마다 한 줄 */
export function bodyOf(needs) {
    const blocks = needs.map(n => {
        const from = n.kind === 'hand'
            ? h('p', { class: 'bk-from' }, '손으로 넣는 점수', n.extra ? ' · 번외 판' : null)
            : h('p', { class: 'bk-from' }, h('b', null, n.who),
                n.amount > 0 ? [' · ', h('span', { class: 'bk-amt' }, num(n.amount) + '원')] : null,
                n.kind === 'contrib' ? ' · 기여도 카드' : null);
        const rows = h('ul', { class: 'bk-rows' }, n.rows.map(r => h('li', { class: 'bk-row' },
            h('b', { class: 'bk-name' }, r.name), h('span', { class: 'bk-pts' + (r.pts < 0 || r.contrib < 0 ? ' minus' : '') }, rowText(r)))));
        return h('div', { class: 'bk-one' }, from, rows);
    });
    return h('div', { class: 'bk-box' }, blocks,
        h('p', { class: 'bk-q' }, '받을 사람이 맞는지 한 번 더 봐 주세요. 아니면 [취소] — 점수는 그대로예요.'));
}

/** 상자 한 번 — true([주기]) / false([취소] · Esc · 바깥) */
export function askBig(ctx, needs) {
    if (!needs || !needs.length) return Promise.resolve(true);
    const minus = needs.every(n => n.rows.every(r => r.pts <= 0 && r.contrib <= 0));
    return ctx.confirm({ title: titleOf(needs), body: bodyOf(needs), ok: minus ? '빼기' : '주기', cancel: '취소', danger: false, cls: 'bigok' });
}

export const CANCELLED = Object.freeze({ ok: false, cancelled: true, error: '취소했어요 — 점수는 그대로예요' });

/** run 감싸기 — 큰 것은 묻고, [취소]면 명령을 안 보낸다 */
export function guardRun(run, getSlices, ask, onCancel) {
    return async function guarded(type, data, opts = {}) {
        if (!(opts && opts.bigOk)) {
            let need = null;
            try { need = needFor(getSlices(), type, data); } catch (e) { need = null; }
            if (need && !(await ask([need]))) {
                if (onCancel) onCancel(need);
                return { ...CANCELLED };
            }
        }
        return run(type, data, opts);
    };
}

/* ── ⚙ 설정 화면 칸 — '🛡️ 큰 금액 확인' (settings_menu.js 가 '이 기기' 위에 붙인다) ──
   후원 금액 기준(원) · 손 점수 기준(점) · [저장] → bigok.set. 0 = 묻지 않음. 서버 조각이라 PC · 폰이 같은 값. */
const parseNum = v => {
    const t = String(v == null ? '' : v).replace(/[,\s원점]/g, '');
    return /^\d{1,9}$/.test(t) ? parseInt(t, 10) : null;
};

export function stateText(L) {
    const a = L.won > 0 ? `후원 ${num(L.won)}원 이상` : null;
    const b = L.pts > 0 ? `손 점수 ${num(L.pts)}점 이상` : null;
    if (!a && !b) return '지금은 꺼져 있어요 — 큰 금액도 바로 들어가요';
    return `지금: ${[a, b].filter(Boolean).join(' · ')}이면 한 번 더 물어요`;
}

export function mountBigokSettings(ctx) {
    const wonIn = h('input', { type: 'text', inputmode: 'numeric', id: 'bigok-won', autocomplete: 'off', 'aria-label': '후원 금액 기준(원)', placeholder: '200,000' });
    const ptsIn = h('input', { type: 'text', inputmode: 'numeric', id: 'bigok-pts', autocomplete: 'off', 'aria-label': '손 점수 기준(점)', placeholder: '20' });
    const save = h('button', { type: 'button', class: 'btn sm pri', id: 'bigok-save' }, '저장');
    const now = h('p', { class: 'muted small bk-now' });
    const el = h('section', { class: 'st-grp st-bigok', 'data-zone': 'bigok' },
        h('h3', null, '🛡️ 큰 금액 확인'),
        h('div', { class: 'bk-set' },
            h('label', { class: 'bk-f' }, h('span', null, '후원 금액'), wonIn, h('span', { class: 'bk-u' }, '원 이상')),
            h('label', { class: 'bk-f' }, h('span', null, '손 점수'), ptsIn, h('span', { class: 'bk-u' }, '점 이상')),
            save),
        now,
        h('p', { class: 'muted small' }, '점수를 줄 때 이 기준을 넘으면 받을 사람 · 점수를 크게 보여 주고 [주기] [취소] 로 한 번 더 물어요. 0 이면 묻지 않아요.'));
    let shown = null;
    const fmt = n => (n ? num(n) : '0');
    function render() {
        const L = limits(ctx.slices);
        const key = L.won + '|' + L.pts;
        const t = stateText(L);
        if (now.textContent !== t) now.textContent = t;
        if (key === shown) return;
        // 입력 중인 칸은 덮지 않는다
        if (document.activeElement !== wonIn) wonIn.value = fmt(L.won);
        if (document.activeElement !== ptsIn) ptsIn.value = fmt(L.pts);
        shown = key;
    }
    wonIn.addEventListener('blur', () => { const n = parseNum(wonIn.value); if (n !== null) wonIn.value = fmt(n); });
    async function send() {
        const won = parseNum(wonIn.value), pts = parseNum(ptsIn.value);
        if (won === null || pts === null) { ctx.toast('숫자만 적어 주세요 (예: 200,000 · 20, 끄려면 0)', 'err'); return; }
        save.disabled = true;
        const res = await ctx.run('bigok.set', { won, pts });
        save.disabled = false;
        if (res && res.ok) { shown = null; ctx.toast(stateText({ won, pts }).replace(/^지금: /, ''), 'ok'); render(); }
    }
    save.addEventListener('click', send);
    for (const i of [wonIn, ptsIn]) i.addEventListener('keydown', e => { if (e.key === 'Enter' && !e.isComposing) { e.preventDefault(); send(); } });
    render();
    return { el, render };
}
