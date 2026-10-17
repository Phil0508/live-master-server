/* 🗣️ 말로 조종 카드 — 'AI 에게 물어보기' 글칸(chat.js)과 Ctrl+K(cmdk.js)가 같이 쓴다. 서버 약속: v2/server/domain/ai_cmd.py 맨 위.
     askCommand(text)        POST /api/ai/command {text, bgm:[곡 제목…]} → {ok, status, data}
     autoClient(res)         state 'client'(BGM — 이 브라우저가 트는 것)를 받자마자 한다
     cardsView(ctx, res, o)  카드 묶음 그리기 — '🤖 밍밍에게 +5점 [실행] [취소]' · '✅ 공지를 바꿨어요 [되돌리기]' · [모두 실행]
   ⚠️ [실행] 을 사람이 눌러야 /api/cmd(ctx.run — 명령 번호 cid 가 붙는다)로 보낸다. 점수 · 대기함 · 게임은 늘 이 길이다.
   ⚠️ 바깥 글자(AI 가 만든 말 · 후원자 이름)는 h()/textContent 로만 — innerHTML 금지.
   오래된 카드(10분)는 단추를 닫는다 — 그새 대기함 · 명단이 바뀌었을 수 있다(다시 말해 달라고 한다). */
import { h, call } from './common.js';
import * as bgm from '../records/bgm.js';
import { needFor, askBig } from '../../bigok.js';   // 🛡️ 큰 금액은 한 번 더 확인 — [실행] · [모두 실행] 은 한 상자로 한 번만 묻는다(10-17 bigok)

const STALE_MS = 10 * 60 * 1000;
const CLIENT = new Set(['bgm.next', 'bgm.toggle', 'bgm.play']);

export async function askCommand(text) {
    let titles = [];
    try { titles = bgm.listState().list.map(x => String(x.title || '')).filter(Boolean).slice(0, 50); } catch (e) { /* BGM 없음 */ }
    return call('/api/ai/command', { text, bgm: titles });
}

/** BGM — 이 브라우저(조종실)가 한다. 돌려받는 값 {ok, error?} */
function runClient(card) {
    try {
        if (card.type === 'bgm.next') { bgm.next(true); return { ok: true }; }
        if (card.type === 'bgm.toggle') { bgm.toggle(); return { ok: true }; }
        if (card.type === 'bgm.play') {
            const want = String((card.data && card.data.title) || '').replace(/\s+/g, '').toLowerCase();
            const list = bgm.listState().list;
            const i = list.findIndex(x => String(x.title || '').replace(/\s+/g, '').toLowerCase().includes(want));
            if (i < 0) return { ok: false, error: 'BGM 목록에 그 곡이 없어요' };
            bgm.playAt(i, true);
            return { ok: true };
        }
    } catch (e) { return { ok: false, error: 'BGM 을 못 움직였어요' }; }
    return { ok: false, error: '모르는 BGM 명령' };
}

export function autoClient(res) {
    (res && res.cards || []).forEach(c => {
        if (c.state !== 'client') return;
        const r = runClient(c);
        c.state = r.ok ? 'ran' : 'failed';
        if (!r.ok) c.error = r.error;
    });
}

/** 카드 하나 실행 — 사람이 누른 것만 여기로 온다 */
export async function runCard(ctx, c, opts) {
    if (CLIENT.has(c.type)) return runClient(c);
    if (c.type === 'slot.spin') {                    // 슬롯은 시그니처 목록을 서버가 바깥에서 받아 와야 한다 — 옛 주소 그대로
        const r = await call('/api/slot/spin', {});
        return r.ok ? { ok: true } : { ok: false, error: (r.data && (r.data.message || r.data.error)) || '실패 (' + r.status + ')' };
    }
    return ctx.run(c.type, c.data || {}, Object.assign({ quiet: true }, opts || {}));
}

const ICON = { ask: '🤖', ran: '✅', failed: '⚠️', cancel: '✖', undone: '↩', client: '⏳', running: '⏳' };

/** 카드 묶음. o.onChange() — 상태가 바뀌면(대화 기록에 남기려고) 부른다. o.compact — Ctrl+K 상자(좁게) */
export function cardsView(ctx, res, o = {}) {
    const cards = (res && res.cards) || [];
    const stale = res && res.at && Date.now() - res.at > STALE_MS;
    const wrap = h('div', { class: 'aic' + (o.compact ? ' compact' : '') });
    const changed = () => { if (o.onChange) o.onChange(); paint(); };
    let busy = false;

    async function exec(list) {
        if (busy) return;
        busy = true;
        // 🛡️ 큰 금액 · 큰 점수가 하나라도 있으면 먼저 한 상자로 묻는다 — [취소] 면 이 묶음은 하나도 안 보낸다
        const bigs = list.map(c => { try { return needFor(ctx.slices, c.type, c.data || {}); } catch (e) { return null; } }).filter(Boolean);
        if (bigs.length && !(await askBig(ctx, bigs))) {
            list.forEach(c => { c.state = 'cancel'; });
            busy = false;
            changed();
            return;
        }
        list.forEach(c => { c.state = 'running'; });
        paint();
        for (const c of list) {
            const r = await runCard(ctx, c, { bigOk: true });
            c.state = r && r.ok ? 'ran' : 'failed';
            if (!(r && r.ok)) c.error = (r && r.error) || '실패';
            else if (r.already) c.note = '이미 돼 있었어요';
        }
        busy = false;
        changed();
    }
    async function undo(c) {
        if (busy || !c.undo) return;
        busy = true;
        paint();
        const r = await ctx.run(c.undo.type, c.undo.data || {}, { quiet: true });
        busy = false;
        if (r.ok) c.state = 'undone';
        else c.error = '되돌리지 못했어요 — ' + (r.error || '실패');
        changed();
    }

    function row(c) {
        const st = c.state || 'ask';
        const kids = [h('span', { class: 'aic-i', 'aria-hidden': 'true' }, ICON[st] || '•'),
            h('span', { class: 'aic-t' }, c.text || c.type)];
        if (st === 'ran' && c.safe && !c.byHand) kids.push(h('small', { class: 'aic-by' }, 'AI 가 바로 함'));
        if (st === 'failed' && c.error) kids.push(h('small', { class: 'aic-err' }, c.error));
        if (st === 'cancel') kids.push(h('small', { class: 'aic-by' }, '취소함'));
        if (st === 'undone') kids.push(h('small', { class: 'aic-by' }, '되돌림'));
        if (c.note) kids.push(h('small', { class: 'aic-by' }, c.note));
        const btns = [];
        if (st === 'ask' && !stale) {
            btns.push(h('button', { type: 'button', class: 'btn xs pri', disabled: busy || null,
                onclick: () => { c.byHand = true; exec([c]); } }, '실행'));
            btns.push(h('button', { type: 'button', class: 'btn xs', disabled: busy || null,
                onclick: () => { c.state = 'cancel'; changed(); } }, '취소'));
        }
        if (st === 'ran' && c.undo && !stale) {
            btns.push(h('button', { type: 'button', class: 'btn xs', disabled: busy || null, title: c.undo.text || '바로 앞 값으로',
                onclick: () => undo(c) }, '되돌리기'));
        }
        return h('li', { class: 'aic-row s-' + st + (c.safe ? ' safe' : '') }, h('span', { class: 'aic-l' }, ...kids),
            btns.length ? h('span', { class: 'aic-b' }, ...btns) : null);
    }

    function paint() {
        const asks = cards.filter(c => (c.state || 'ask') === 'ask');
        const parts = [];
        if (res.reply) parts.push(h('p', { class: 'aic-reply' }, res.reply));
        if (cards.length) parts.push(h('ul', { class: 'aic-list' }, ...cards.map(row)));
        if (asks.length >= 2 && !stale) {
            parts.push(h('div', { class: 'aic-all' },
                h('button', { type: 'button', class: 'btn sm pri', disabled: busy || null,
                    onclick: () => { asks.forEach(c => { c.byHand = true; }); exec(asks); } }, `모두 실행 (${asks.length})`),
                h('button', { type: 'button', class: 'btn sm', disabled: busy || null,
                    onclick: () => { asks.forEach(c => { c.state = 'cancel'; }); changed(); } }, '모두 취소')));
        }
        if (res.note) parts.push(h('p', { class: 'aic-note' }, res.note));
        if (res.dropped && res.dropped.length) {
            parts.push(h('p', { class: 'aic-note bad', title: res.dropped.map(d => `${d.type}: ${d.why}`).join('\n') },
                `🚫 AI 가 낸 것 중 ${res.dropped.length}개는 안전 검사에서 버렸어요 — ${res.dropped[0].why}`));
        }
        if (stale && cards.some(c => (c.state || 'ask') === 'ask')) parts.push(h('p', { class: 'aic-note' }, '오래된 제안이라 단추를 닫았어요 — 다시 말해 주세요'));
        wrap.replaceChildren(...parts);
    }
    paint();
    return wrap;
}

/** 대화 기록 한 줄 요약(저장용 글자) */
export function summary(res) {
    const cs = (res && res.cards) || [];
    return cs.length ? cs.map(c => c.text).join(' · ') : (res && res.reply) || '';
}
