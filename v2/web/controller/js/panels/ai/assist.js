/* 🤖 대기함 쪽 AI 서포트 — pending.js 가 부르는 곳은 여기 하나다(화면 약속 1).
     sync(slices)        대기함이 바뀔 때마다: 새 후원 묻기 · '지급할까요?' 줄 정리 · 🚗 오토파일럿 · 🔔 먼저 알림
     badge(it)           카드 안 배지 + '지난 배정' 줄(없으면 null)
     sig(id)             배지가 바뀌었는지(카드를 다시 그릴지) 보는 글자
     okToGive(it, name)  오배정 경고 — 메시지가 다른 사람을 가리키면 한 번 묻는다(옛 assignPending 의 'AI 기입 검증')
     mountAsks(list, ctx, give)  '지급할까요?' 줄을 대기함 카드 목록 바로 위에 끼운다. give(id, name) = 대기함의 배정 단추와 같은 길

   배지(옛 paintAuditBadge 그대로 — '모름' 도 숨기지 않는다. 근거(why)는 늘 같이)
     tier 'auto' → '✓ 이름 (거의 확실)' · 이름 있고 확신 0.6↑ → '🤖 이름(으)로 보임' · 잠깐 막힘 → '⏳ AI 가 붐벼요'
     · 그 밖 → '❓ 누구 것인지 모르겠음'. 지난 배정 앞 3개 → '지난 배정 · 하율 3번'.
   '지급할까요?'(옛 토스트 · 마지막 모습은 대기함 안 맨 위 한 줄)
     확신 0.75↑ · 후원 1건에 한 번 · 아직 대기함에 있을 때만 · 그 이름이 지금 판 선수일 때만. [✔ 지급] = 그 사람에게 · [무시] = 줄만 닫는다.
     ⚠️ 떠 있는 상자로 띄우면 대기함 카드 단추를 덮었다(옛 조종실 실측) — 그래서 대기함 안에 끼운다.
     ⚠️ 마우스가 대기함 위에 있는 동안(얼림)은 새 줄을 끼우지 않고, 처리된 줄은 같은 높이 자리로 남긴다 — 카드가 손 밑에서 움직이지 않게. */
import { h, josaRo, currentNames, isDonation, setCtx, getCtx } from './common.js';
import * as sug from './suggest.js';
import * as ap from './autopilot.js';
import * as watch from './watch.js';
import { manWon, won } from '../../util.js';

const AUDIT_MIN_CONF = 0.6;      // 배지 '🤖 ○○로 보임' · 오배정 경고
const ASK_MIN_CONF = 0.75;       // '지급할까요?' — 행동을 권하니 배지보다 엄격하게
const ASK_SHOW = 3;              // 한 번에 보이는 '지급할까요?' 줄

const askShown = new Set();      // 후원 1건당 한 번(무시했으면 다시 안 뜬다)
const shown = new Map();         // id → {sig, ans} 카드에 지금 그려 둔 답 — 얼린 동안은 이것을 그대로 쓴다
const asks = [];                 // [{id, target}] 아직 답을 안 한 제안(들어온 순서)
let box = null, giveFn = null, lastSlices = null;
const rows = new Map();          // id → {el, ghost}

/* ── 대기함이 바뀔 때마다 ── */
// ⚠️ 여기서 무엇이 넘어져도 대기함 카드는 그려져야 한다 — 전부 감싼다(배지 없이 도는 편이 낫다)
export function sync(slices) {
    try {
        lastSlices = slices;
        const pend = slices.pending || [];
        sug.sync(pend);
        const ids = new Set(pend.map(x => x && x.id));
        for (let i = asks.length - 1; i >= 0; i--) if (!ids.has(asks[i].id)) asks.splice(i, 1);
        for (const id of [...shown.keys()]) if (!ids.has(id)) shown.delete(id);
        paintAsks();
        ap.sweep().catch(e => console.error('[오토파일럿]', e));
    } catch (e) { console.error('[AI 제안]', e); }
    try { watch.check(slices); } catch (e) { console.error('[AI 알림]', e); }
}

// 답이 들어오면 — '지급할까요?' 를 띄울지 보고 오토파일럿을 한 번 더 훑는다
sug.onAnswer((id, a) => {
    if (!a || !a.target || (a.confidence || 0) < ASK_MIN_CONF || askShown.has(id)) return;
    const slices = (getCtx() || {}).slices || lastSlices || {};
    const it = (slices.pending || []).find(x => x && x.id === id);
    if (!it || !isDonation(it)) return;
    if (!currentNames(slices).includes(a.target)) return;           // 그새 선수가 바뀌었으면 권하지 않는다
    if (ap.isOn() && a.tier === 'auto' && !it.returned) return;     // 오토파일럿이 곧 줄 것 — 줄을 띄웠다 지우지 않게
    askShown.add(id);
    asks.push({ id, target: a.target });
    paintAsks();
});
sug.onAnswer(() => { ap.sweep().catch(e => console.error('[오토파일럿]', e)); });

// 🔔 시간이 지나야 걸리는 알림(3분째 대기 · 대결 30초)은 조각이 안 바뀌어도 본다
setInterval(() => {
    const ctx = getCtx();
    if (ctx && document.body.dataset.view === 'live') { try { watch.check(ctx.slices); } catch (e) { console.error('[AI 알림]', e); } }
}, 15000);

/* ── 카드 안 배지 ──
   ⚠️ 마우스가 대기함 위에 있는 동안(얼림)은 배지를 바꾸지 않는다 — 답이 와서 배지가 두 줄이 되면
      이름 단추가 아래로 밀려, 누르려던 자리에 윗줄의 다른 사람 단추가 온다(돈이 걸린 오배정). 손을 떼면 그때 바뀐다. */
export function sig(id) {
    const cur = 'ai' + sug.version(id);
    const prev = shown.get(id);
    if (prev && frozen()) return prev.sig;
    shown.set(id, { sig: cur, ans: sug.get(id) });
    return cur;
}

export function badge(it) {
    try { return makeBadge(it); } catch (e) { console.error('[AI 배지]', e); return null; }
}

function makeBadge(it) {
    if (!isDonation(it)) return null;
    const snap = shown.get(it.id);
    const s = snap ? snap.ans : sug.get(it.id);
    if (!s || s.gone || s.skipped) return null;
    let cls, main;
    const why = s.why ? h('span', { class: 'ai-why' }, ' · ' + s.why) : null;
    if (s.asking) {
        cls = 'lv-asking';
        main = ['🤖 누구 것인지 보는 중…'];
    } else if (s.target && s.tier === 'auto') {
        cls = 'lv-auto';
        main = ['✓ ', h('b', null, s.target), ' (거의 확실)'];
    } else if (s.target && (s.confidence || 0) >= AUDIT_MIN_CONF) {
        cls = 'lv-suggest';
        main = ['🤖 ', h('b', null, s.target), josaRo(s.target) + ' 보임'];
    } else if (s.retryIn) {
        // 잠깐 막힌 것뿐 — 곧 다시 묻는다. '모름' 과 섞으면 사람이 괜히 손으로 판단하러 간다
        cls = 'lv-wait';
        main = ['⏳ AI 가 붐벼요 — 곧 다시 물어봐요'];
    } else {
        // '모름' 을 숨기지 않는다. 자리를 비웠을 때 이게 쌓이는 것이 곧 할 일이다
        cls = 'lv-unknown';
        main = ['❓ 누구 것인지 모르겠음'];
    }
    const hist = (s.history || []).slice(0, 3).filter(x => x && x.name);
    return h('div', { class: 'ai-sug' },
        h('div', { class: 'ai-badge ' + cls, title: s.source ? '판단 근거: ' + s.source : null }, ...main, why),
        hist.length ? h('div', { class: 'ai-hist' }, '지난 배정 · ' + hist.map(x => `${x.name} ${x.count}번`).join(' · ')) : null);
}

/* ── 오배정 경고 ── 메시지가 '하율' 을 가리키는데 '서아' 를 누르면 한 번 묻는다. 취소하면 아무것도 안 한다 */
export async function okToGive(it, name) {
    let s = null;
    try { s = sug.get(it && it.id); } catch (e) { return true; }
    if (!s || !s.target || (s.confidence || 0) < AUDIT_MIN_CONF || s.target === name) return true;
    const ctx = getCtx();
    if (!ctx) return true;
    return ctx.confirm({
        title: '🤖 다른 사람 후원 같아요',
        body: `메시지를 보면 이 후원은 '${s.target}' 을(를) 응원하는 것 같아요.` + (s.why ? `\n(근거: ${s.why})` : '') + `\n\n그래도 '${name}' 에게 줄까요?`,
        ok: `${name}에게 주기`, cancel: '취소',
    });
}

/* ── '지급할까요?' 줄 ── */
export function mountAsks(list, ctx, give) {
    setCtx(ctx);
    giveFn = give || null;
    box = h('div', { class: 'ai-asks', 'aria-live': 'polite' });
    list.before(box);
}

function frozen() {
    return !!(box && box.closest('.frozen'));
}

function paintAsks() {
    if (!box) return;
    const slices = (getCtx() || {}).slices || lastSlices || {};
    const pend = slices.pending || [];
    const want = asks.slice(0, ASK_SHOW).map(a => a.id);
    const hold = frozen();
    // 빠진 줄 — 얼려 있으면 같은 높이 자리로 남기고, 아니면 지운다
    for (const [id, r] of rows) {
        if (want.includes(id)) continue;
        if (hold) {
            if (!r.ghost) {
                r.el.style.minHeight = r.el.getBoundingClientRect().height + 'px';
                r.el.className = 'ai-ask ghost';
                r.el.inert = true;
                r.el.replaceChildren(h('span', null, '✓ 정리됨'));
                r.ghost = true;
            }
        } else { r.el.remove(); rows.delete(id); }
    }
    asks.slice(0, ASK_SHOW).forEach(a => {
        if (rows.has(a.id) && !rows.get(a.id).ghost) return;
        if (hold) return;                                      // 손이 대기함 위에 있다 — 새 줄은 손을 뗀 뒤에
        const it = pend.find(x => x && x.id === a.id);
        if (!it) return;
        const old = rows.get(a.id);
        if (old) old.el.remove();
        const el = makeAsk(it, a.target);
        box.append(el);
        rows.set(a.id, { el, ghost: false });
    });
    let more = box.querySelector('.ai-ask-more');
    const extra = asks.length - ASK_SHOW;
    if (extra > 0 && !hold) {
        if (!more) { more = h('p', { class: 'ai-ask-more' }); box.append(more); }
        more.textContent = `🤖 제안 ${extra}건 더 — 카드의 배지를 보세요`;
        box.append(more);
    } else if (more && !hold) more.remove();
}

function makeAsk(it, target) {
    const pts = manWon(it.amount);
    return h('div', { class: 'ai-ask', 'data-id': it.id },
        h('div', { class: 'ai-ask-tx' },
            h('span', { class: 'ai-ask-src' }, `🤖 ${it.name || '익명'}님 · ${won(it.amount)}`),
            h('span', { class: 'ai-ask-q' }, h('b', null, target), `에게 ${pts}점 줄까요?`)),
        h('div', { class: 'ai-ask-btns' },
            h('button', { type: 'button', class: 'btn sm pri', onclick: () => accept(it.id, target) }, '✔ 지급'),
            h('button', { type: 'button', class: 'btn sm', onclick: () => dismiss(it.id) }, '무시')));
}

function dismiss(id) {
    const i = asks.findIndex(a => a.id === id);
    if (i >= 0) asks.splice(i, 1);
    paintAsks();
}

async function accept(id, target) {
    dismiss(id);
    const ctx = getCtx();
    if (!ctx) return;
    const slices = ctx.slices || {};
    const it = (slices.pending || []).find(x => x && x.id === id);
    if (!it) { ctx.toast('이미 처리된 후원이에요', 'info'); return; }
    // ⚠️ 누르는 순간 다시 본다 — 줄이 떠 있는 사이 선수가 바뀌었을 수 있다
    if (!currentNames(slices).includes(target)) { ctx.toast(`'${target}' 이(가) 지금 판에 없어요 — 카드에서 직접 골라 주세요`, 'err'); return; }
    if (giveFn) { await giveFn(id, target); return; }
    const res = await ctx.run('pending.assign', { id, name: target });
    if (res.ok && !res.already) ctx.toast(`${target} +${manWon(it.amount)}점 — ${it.name} ${won(it.amount)}`, 'ok');
}
