/* 🙈 메시지 금칙어 · [가리기] — 대기함 카드 · 장부 줄이 같이 쓰는 작은 도구(10-17 mask).

   서버(domain/mask.py)가 걸린 메시지에 mask{hits, text}(방송에 나가는 가린 글)를 붙여 준다 — 원문(message)은 그대로.
   조종실은 기본으로 **가린 글**을 보여 준다(대표님이 방송 중 소리 내 읽다가 번호 · 욕을 읽지 않게) + ⚠ 딱지.
   ⚠ 딱지를 누르면 원문 보기 ↔ 가린 글(이 기기에서만, 다시 그려도 기억).
   [가리기] → mask.hide {id, on:true} — 그 후원 메시지를 방송판에서 통째로 숨긴다(떠 있는 팝업 · 시그 카드 · 대기줄에서도 바로).
   [보이기] → mask.hide {id, on:false}. 장부 · 대기함 글자는 그대로다. 소리 없음. */
import { h } from './util.js';

const HIT = { phone: '전화번호', account: '계좌번호', url: '주소', word: '금칙어' };
const reveal = new Set();          // 원문을 펼쳐 둔 후원 id
const busy = new Set();

export function hiddenSet(slices) {
    return new Set(((slices && slices.mask) || {}).hidden || []);
}

/** 서명에 넣을 것 — 가렸는지 · 원문 펼쳤는지 · 보내는 중인지 */
export function maskSig(slices, id) {
    return [hiddenSet(slices).has(id), reveal.has(id), busy.has(id)];
}

export function hitText(m) {
    const hits = (m && m.hits) || [];
    return hits.map(k => HIT[k] || k).join(' · ');
}

/** 메시지 글자 — 걸렸으면 가린 글(원문을 펼쳤으면 원문). 가린 후원이면 그대로 쓰고 흐리게는 CSS 가 한다. */
export function shownText(it) {
    const raw = String((it && it.message) || '');
    const m = it && it.mask;
    if (!m || reveal.has(it.id)) return raw;
    return String(m.text || '');
}

/** ⚠ 딱지(누르면 원문 보기 ↔ 가린 글) — 걸린 것이 없으면 null */
export function warnChip(ctx, it) {
    const m = it && it.mask;
    if (!m || !(m.hits || []).length) return null;
    const open = reveal.has(it.id);
    return h('button', {
        type: 'button', class: 'mk-warn' + (open ? ' open' : ''), 'aria-pressed': open ? 'true' : 'false',
        title: `방송 화면엔 ${hitText(m)} 부분을 ●●● 로 가려서 내보내요.\n누르면 ${open ? '가린 글' : '원문'}을 봐요 (이 기기에서만).`,
        onclick: e => { e.stopPropagation(); open ? reveal.delete(it.id) : reveal.add(it.id); ctx.rerender(); },
    }, '⚠ ', open ? '원문' : hitText(m));
}

/** [가리기] / [보이기] 단추 */
export function hideBtn(ctx, it, after) {
    if (!it || !it.id) return null;
    const on = hiddenSet(ctx.slices).has(it.id);
    return h('button', {
        type: 'button', class: 'btn xs mk-hide' + (on ? ' on' : ''), disabled: busy.has(it.id), 'aria-pressed': on ? 'true' : 'false',
        title: on ? '방송 화면에 이 후원 메시지를 다시 보여요' : '이 후원 메시지를 방송 화면에서 통째로 숨겨요 (장부 · 대기함은 그대로)',
        onclick: e => { e.stopPropagation(); toggleHide(ctx, it, !on).then(() => after && after()); },
    }, on ? '보이기' : '가리기');
}

export async function toggleHide(ctx, it, on) {
    if (busy.has(it.id)) return;
    busy.add(it.id);
    ctx.rerender();
    try {
        const res = await ctx.run('mask.hide', { id: it.id, on });
        if (res.ok) ctx.toast(on ? `🙈 ${it.name || '익명'} 메시지를 방송 화면에서 숨겼어요` : `${it.name || '익명'} 메시지를 다시 보여요`, 'info');
    } finally {
        busy.delete(it.id);
        ctx.rerender();
    }
}
