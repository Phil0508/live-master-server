/* 🕘 최근 바뀐 것 — 시그니처 등록 · 고치기 · 지우기 기록과 [되살리기] · [되돌리기].

   조각(읽기만): sig_admin.log (비공개 — 조종실만 받는다, 새것이 앞)
     {lid, at, act(add|edit|delete|restore|revert), id, title, amount, before?, after?, row?, restored?, reverted?}
   [되살리기] 지운 것 → POST /api/sigadmin/restore {lid} — 파일은 남겨 두었으므로 행만 다시 넣는다(되도록 같은 번호)
   [되돌리기] 고친 것 → POST /api/sigadmin/revert {lid} — 고치기 전 값(파일 주소 포함)으로
   같은 금액이 이미 있으면 서버가 409(code:'dup') → 한 번 묻고 allow_dup 으로 다시 보낸다.
   ⚠️ 이 기록은 이 서버(v2)에서 바꾼 것만 적힌다. 옛 서버 · Supabase 화면에서 바꾼 것은 안 보인다. */
import { h, num, clock, call, once, label } from './common.js';

const SHOW = 6;
const ACT = {
    add: ['＋', '등록'], edit: ['✏️', '고침'], delete: ['🗑', '지움'], restore: ['♻️', '되살림'], revert: ['↩', '되돌림'],
};

function changes(e) {
    const b = e.before || {}, a = e.after || {};
    const out = [];
    if (b.amount !== a.amount) out.push(`금액 ${num(b.amount)}→${num(a.amount)}원`);
    if (b.title !== a.title) out.push(`제목 '${b.title || ''}'→'${a.title || ''}'`);
    if (b.duration !== a.duration) out.push(`재생 ${b.duration}→${a.duration}초`);
    if (b.image_url !== a.image_url) out.push('사진 바뀜');
    if (b.sound_url !== a.sound_url) out.push('음원 바뀜');
    return out.join(' · ');
}

function dayLabel(at) {
    const d = new Date(Number(at) * 1000);
    const t = new Date();
    if (d.toDateString() === t.toDateString()) return '오늘 ' + clock(at);
    return `${d.getMonth() + 1}/${d.getDate()} ${clock(at)}`;
}

export function mountHistory(el, ctx, { onChanged } = {}) {
    const ol = h('ol', { class: 'sg-log' });
    const more = h('button', { type: 'button', class: 'btn sm', hidden: true });
    const trashTag = h('span', { class: 'tag warn', hidden: true });
    const empty = h('p', { class: 'empty' }, '아직 바뀐 것이 없어요 — 이 조종실에서 등록 · 고치기 · 지우기를 하면 여기에 남아요');
    el.append(h('div', { class: 'sg-bh' }, h('h3', null, '🕘 최근 바뀐 것'), trashTag), ol, empty, more);
    let showAll = false, lastSig = '';
    more.addEventListener('click', () => { showAll = !showAll; lastSig = ''; render(ctx.slices); });

    async function restore(e, btn, allowDup) {
        const r = await call('/api/sigadmin/restore', { lid: e.lid, allow_dup: !!allowDup });
        if (r.ok) { ctx.toast('♻️ ' + (r.data.message || '되살렸어요') + ' — ' + label(r.data.signature || e.row), 'ok'); if (onChanged) onChanged(); return; }
        if (r.status === 409 && r.data.code === 'dup') {
            const ok = await ctx.confirm({ title: '같은 금액의 시그니처가 있어요', body: r.error + '\n\n그래도 되살릴까요?', ok: '그래도 되살리기', cancel: '그만두기', danger: false });
            if (ok) return restore(e, btn, true);
            return;
        }
        ctx.toast('되살리지 못했어요: ' + r.error, 'err');
    }
    async function revert(e, btn, allowDup) {
        if (!allowDup) {
            const ok = await ctx.confirm({
                title: '고치기 전으로 되돌릴까요?',
                body: `${label(e.after || e)}\n→ ${label(e.before)}\n(${changes(e) || '바뀐 것'})\n\n방송에도 바로 반영돼요.`,
                ok: '되돌리기', cancel: '그대로 두기', danger: false,
            });
            if (!ok) return;
        }
        const r = await call('/api/sigadmin/revert', { lid: e.lid, allow_dup: !!allowDup });
        if (r.ok) { ctx.toast('↩ ' + (r.data.message || '되돌렸어요'), 'ok'); if (onChanged) onChanged(); return; }
        if (r.status === 409 && r.data.code === 'dup') {
            const ok = await ctx.confirm({ title: '같은 금액의 시그니처가 있어요', body: r.error + '\n\n그래도 되돌릴까요?', ok: '그래도 되돌리기', cancel: '그만두기', danger: false });
            if (ok) return revert(e, btn, true);
            return;
        }
        ctx.toast('되돌리지 못했어요: ' + r.error, 'err');
    }

    function row(e) {
        const [ic, word] = ACT[e.act] || ['•', e.act];
        const main = e.after || e.row || e.before || e;
        const sub = e.act === 'edit' || e.act === 'revert' ? changes(e) : '';
        let btn = null, state = null;
        if (e.act === 'delete') {
            if (e.restored) state = h('span', { class: 'tag live' }, `되살림 #${e.restored}`);
            else {
                btn = h('button', { type: 'button', class: 'btn sm pri' }, '♻️ 되살리기');
                btn.addEventListener('click', () => once(btn, () => restore(e, btn)));
            }
        } else if (e.act === 'edit' || e.act === 'revert') {
            if (e.reverted) state = h('span', { class: 'tag plain' }, '되돌렸음');
            else if (e.before) {
                btn = h('button', { type: 'button', class: 'btn sm' }, '↩ 되돌리기');
                btn.addEventListener('click', () => once(btn, () => revert(e, btn)));
            }
        }
        const li = h('li', { class: 'sg-logrow act-' + e.act + (e.act === 'delete' && !e.restored ? ' trash' : '') },
            h('span', { class: 'sg-log-ic', 'aria-hidden': 'true' }, ic),
            h('div', { class: 'sg-log-t' },
                h('b', null, `${word} · ${label(main)}`),
                h('small', null, dayLabel(e.at) + (sub ? ' · ' + sub : ''))),
            btn || state);
        return li;
    }

    function render(slices) {
        const log = ((slices.sig_admin || {}).log) || [];
        const trash = log.filter(e => e.act === 'delete' && !e.restored);
        const view = showAll ? log : log.slice(0, SHOW);
        // 오래된 '안 되살린 지우기' 는 접혀 있어도 보이게 — 되살릴 길을 숨기지 않는다
        if (!showAll) trash.forEach(e => { if (!view.includes(e)) view.push(e); });
        const sig = JSON.stringify([view.map(e => [e.lid, e.restored, e.reverted]), showAll, log.length]);
        if (sig === lastSig) return;
        lastSig = sig;
        ol.replaceChildren(...view.map(row));
        empty.hidden = log.length > 0;
        trashTag.hidden = !trash.length;
        trashTag.textContent = `지운 것 ${trash.length}개 — 되살릴 수 있어요`;
        more.hidden = log.length <= SHOW;
        more.textContent = showAll ? '접기' : `모두 보기 (${log.length}개)`;
    }
    return { render };
}
