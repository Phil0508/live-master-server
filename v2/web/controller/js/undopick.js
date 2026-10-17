/* ↩ 기록에서 골라 되돌리기(undopick 10-17) — 로그 탭 · 장부 탭 점수 기록 줄마다 [↩ 되돌리기].

   - 누르면 score.undo {ref} — 그 줄의 묶음(ref)만 되돌린다. 서버는 ref 로 아무 줄이나 되돌린다(마지막 것이 아니어도).
   - ⚠️ 서버 규칙은 **묶음(ref) 단위**: 한 후원을 나눠 준 것(밍밍 +3 · 하율 +2)은 같은 ref 라 줄 하나를 눌러도 함께 되돌아간다.
     그래서 확인 상자에 '함께 되돌아가요: …' 로 무엇이 빠지는지 전부 적는다.
   - 후원(don_)을 되돌리면 그 후원은 대기함 맨 앞으로 돌아온다(서버 donation._undo_back_to_pending).
     게임 카드 · 손으로 준 점수는 점수만 빠진다.
   - 화면 안 확인 상자(confirm() 아님) · 기본 손가락은 [취소]. 두 번 눌러도 한 번: 보내는 동안 같은 ref 는 막고(busy),
     서버도 두 번째는 '이미 되돌렸거나 없는 기록' 으로 막는다.
   - 되돌린 줄은 서버 조각 logs_undone(비공개)에 남아 기록에 회색 '되돌림' 으로 보인다(단추 없음).
   - 지난 방송 줄은 못 되돌린다(서버도 409) — 이번 방송 · 방송 중에만 단추를 단다. */
import { h, signed, num, won, clock } from './util.js';

const busy = new Set();

/** 누가 줬나 딱지 — 자동 진행 · AI 가 준 줄 */
export function byLabel(by) {
    return by === 'autopilot-ai' ? '🤖 AI 가 줌' : by === 'auto' ? '🤖 자동' : '';
}

/** 기록 한 줄 → '밍밍 +5점' · '밍밍 기여도 +3' · '[번외] 밍밍 +2점' · '운영비 +5점' */
export function lineText(l) {
    const pre = l.list === 'extra' ? '[번외] ' : l.list === 'jar' ? '[모금함] ' : '';
    if (l.kind === 'contrib' || (!l.val && l.cval)) return `${pre}${l.name} 기여도 ${signed(l.cval)}`;
    let s = `${pre}${l.name} ${signed(l.val)}점`;
    if (l.cval != null && l.cval !== l.val) s += `(기여도 ${signed(l.cval)})`;
    return s;
}

/** 무엇이 되돌아가나 — slices(logs) 에서 같은 ref 를 모은다. 없으면 fallback 줄(장부 탭 /api/scores 를 묶은 것)로.
 *  돌려주는 값: { ref, lines[], at, don{name,amount}|null, isDon, by, split, staleExtra } */
export function undoPlan(slices, ref, fallback) {
    const S = slices || {};
    let rows = (S.logs || []).filter(l => l && l.ref === ref).slice().reverse();     // 서버가 넣은 순서(앞사람부터)
    if (!rows.length && fallback && fallback.length) rows = fallback.slice();
    const isDon = String(ref || '').startsWith('don_');
    const don = (rows.find(l => l.don) || {}).don || null;
    const by = (rows.find(l => l.by) || {}).by || '';
    const at = rows.length ? Math.min(...rows.map(l => Number(l.at) || 0)) : 0;
    const staleExtra = rows.some(l => l.list === 'extra') && !(S.players || {}).extra_active;
    return { ref, lines: rows.map(lineText), at, don, isDon, by, split: rows.length > 1, staleExtra, n: rows.length };
}

/** 확인 상자 머리 — '21:03 밍밍 +5점(영원 50,000원)' */
export function planTitle(p) {
    const who = p.lines.length ? p.lines[0] + (p.lines.length > 1 ? ` 외 ${p.lines.length - 1}줄` : '') : '이 기록';
    const don = p.don ? `(${p.don.name || '익명'} ${num(p.don.amount)}원)` : '';
    return `${clock(p.at)} ${who}${don}`.trim();
}

/** 상자 안 안내 줄들(글자만 — 검사가 그대로 부른다) */
export function planNotes(p) {
    const out = [];
    if (p.split) out.push(`나눠 준 ${p.isDon ? '후원이라' : '점수라'} 함께 되돌아가요: ${p.lines.join(' · ')}`);
    if (p.staleExtra) out.push('번외 판이 이미 끝나서, 되돌려도 점수는 바뀌지 않고 이 기록만 지워져요. 본판 점수는 점수판 칸에 빼기(-)로 고쳐 주세요.');
    else if (p.isDon) out.push('후원은 대기함으로 돌아가요' + (p.don ? ` — ${p.don.name || '익명'} ${won(p.don.amount)}` : ''));
    else out.push('점수만 빠져요');
    if (p.by === 'autopilot-ai') out.push('🤖 AI 가 준 점수예요 — 되돌리면 이 후원은 다시 자동으로 주지 않아요');
    else if (p.by === 'auto') out.push('🤖 자동 진행이 준 점수예요');
    return out;
}

/** 묻고 되돌린다. 돌려주는 값: 되돌렸으면 true */
export async function askUndo(ctx, ref, fallback) {
    if (!ref || busy.has(ref)) return false;
    const p = undoPlan(ctx.slices, ref, fallback);
    if (!p.n) { ctx.toast('이미 되돌렸거나 없는 기록이에요', 'info'); return false; }
    const body = h('div', { class: 'up-box' },
        h('p', { class: 'up-what' }, planTitle(p)),
        ...planNotes(p).map((t, i) => h('p', { class: 'up-note' + (i === 0 ? ' first' : '') }, t)));
    busy.add(ref);
    try {
        const ok = await ctx.confirm({ title: '되돌릴까요?', body, ok: p.staleExtra ? '기록만 지우기' : '되돌리기', cancel: '취소', cls: 'up-modal' });
        if (!ok) return false;
        const res = await ctx.run('score.undo', { ref });
        if (!res || !res.ok) return false;
        const back = p.isDon ? ' — 후원은 대기함으로 돌아갔어요' : '';
        ctx.toast(`되돌렸어요: ${p.lines.join(' · ')}${back}`, 'ok', 5000);
        return true;
    } finally {
        busy.delete(ref);
        if (ctx.rerender) ctx.rerender();
    }
}

/** 지금 이 ref 를 보내는 중인가(단추를 잠깐 잠근다) */
export const undoBusy = ref => busy.has(ref);
