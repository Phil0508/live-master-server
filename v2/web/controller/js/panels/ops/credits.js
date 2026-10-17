/* 🎬 엔딩 크레딧 — '계좌 · 화면' 탭 맨 아래 칸(screen.js 가 붙인다). 서버 credits.py.
   [🎬 엔딩 크레딧 띄우기] credits.show · [⏸ 멈춤 / ▶ 이어서] credits.pause · [⏮ 처음부터] credits.restart · [내리기] credits.hide
   · [🔄 다시 만들기] credits.build · 제목 · 마무리 글 · 금액 보이기 · 속도는 credits.set.
   미리보기 = 비공개 조각 credits_ops(만든 때 · 몇 명 · 멤버별 몇 명 · 그 뒤 바뀐 것). 명단을 펼치면 이름(+금액)을 본다.
   ⚠️ 방송 중에 띄울 때만 화면 안 확인 상자 한 번(방송판 전체를 덮으니까). 소리 없음. */
import { h, num, sigOf, onEnter, setVal, once, switchEl, blockHead, fill } from './common.js';
import { confirmBox, clock } from '../../util.js';

const SPEED = [['slow', '느림'], ['normal', '보통'], ['fast', '빠름']];

export function mountCredits(el, ctx) {
    const state = h('p', { class: 'ops-now off', id: 'cr-state' });
    const summary = h('div', { class: 'cr-sum', id: 'cr-sum' });
    const stale = h('p', { class: 'ops-note warn', hidden: true, id: 'cr-stale' });
    const list = h('div', { class: 'cr-list' });
    const fold = h('details', { class: 'cr-fold' }, h('summary', null, '명단 펼쳐 보기'), list);

    const titleIn = h('input', { type: 'text', maxlength: '40', placeholder: '오늘 함께해 주셔서 감사합니다', autocomplete: 'off', class: 'grow', 'aria-label': '크레딧 맨 위 제목', id: 'cr-title' });
    const outroIn = h('input', { type: 'text', maxlength: '60', placeholder: '다음 방송에서 또 만나요 ♥', autocomplete: 'off', class: 'grow', 'aria-label': '크레딧 마무리 글', id: 'cr-outro' });
    const dirty = new Set();
    async function saveText(k, input) {
        const res = await ctx.run('credits.set', { [k]: input.value.trim() });
        if (res.ok) { dirty.delete(k); ctx.toast(k === 'title' ? '제목을 바꿨어요' : '마무리 글을 바꿨어요', 'ok'); }
    }
    [['title', titleIn], ['outro', outroIn]].forEach(([k, i]) => {
        i.addEventListener('input', () => dirty.add(k));
        i.addEventListener('change', () => { if (dirty.has(k)) saveText(k, i); });
        onEnter(i, () => i.blur());
    });

    const amtSw = switchEl('금액 보이기', async on => {
        const res = await ctx.run('credits.set', { show_amount: on });
        if (res.ok) ctx.toast(on ? '이름 옆에 금액도 보여요' : '이름만 보여요', 'info');
        else amtSw.input.checked = !on;
    }, '끄면 이름(닉네임)만 — 기본은 꺼짐');

    const speedBtns = SPEED.map(([v, label]) => h('button', {
        type: 'button', class: 'ops-chip sm', 'data-speed': v, 'aria-pressed': 'false',
        onclick: e => once(e.currentTarget, async () => {
            const res = await ctx.run('credits.set', { speed: v });
            if (res.ok) ctx.toast('흐르는 속도: ' + label, 'info');
        }),
    }, label));

    const bShow = h('button', { type: 'button', class: 'btn pri', id: 'cr-show', onclick: () => once(bShow, show) }, '🎬 엔딩 크레딧 띄우기');
    const bPause = h('button', { type: 'button', class: 'btn', id: 'cr-pause', onclick: () => once(bPause, pause) }, '⏸ 멈춤');
    const bRestart = h('button', { type: 'button', class: 'btn', id: 'cr-restart', onclick: () => once(bRestart, restart) }, '⏮ 처음부터');
    const bHide = h('button', { type: 'button', class: 'btn', id: 'cr-hide', onclick: () => once(bHide, hide) }, '내리기');
    const bBuild = h('button', { type: 'button', class: 'btn sm', id: 'cr-build', onclick: () => once(bBuild, rebuild) }, '🔄 명단 다시 만들기');

    function textData() {
        const d = {};
        if (dirty.has('title')) d.title = titleIn.value.trim();
        if (dirty.has('outro')) d.outro = outroIn.value.trim();
        return d;
    }
    async function show() {
        const s = ctx.slices || {};
        if ((s.session || {}).live) {
            const ok = await confirmBox({ title: '엔딩 크레딧을 띄울까요?', body: '방송판 전체를 크레딧이 덮어요(후원 알림 · 시그니처는 그 위에 그대로 떠요).',
                ok: '띄우기', danger: false });
            if (!ok) return;
        }
        const res = await ctx.run('credits.show', textData());
        if (res.ok) { dirty.clear(); ctx.toast('🎬 엔딩 크레딧을 띄웠어요' + (res.count != null ? ' — ' + num(res.count) + '명' : ''), 'ok'); }
    }
    async function pause() {
        const res = await ctx.run('credits.pause', {});
        if (res.ok) ctx.toast(res.paused ? '⏸ 멈췄어요' : '▶ 이어서 흘러요', 'info');
    }
    async function restart() {
        const res = await ctx.run('credits.restart', {});
        if (res.ok) ctx.toast('⏮ 처음부터 다시 흘러요', 'info');
    }
    async function hide() {
        const res = await ctx.run('credits.hide', {});
        if (res.ok) ctx.toast('크레딧을 내렸어요', 'info');
    }
    async function rebuild() {
        const res = await ctx.run('credits.build', textData());
        if (res.ok) { dirty.clear(); ctx.toast('🔄 명단을 새로 만들었어요 — ' + num(res.count || 0) + '명', 'ok'); }
    }

    el.append(h('section', { class: 'ops-blk cr-blk', id: 'credits-blk' },
        blockHead('🎬 엔딩 크레딧', '오늘 후원해 주신 분 전원을 아래에서 위로 — 멤버별로 묶어요'),
        state,
        h('div', { class: 'ops-row wrap cr-btns' }, bShow, bPause, bRestart, bHide),
        summary, stale, fold,
        h('div', { class: 'ops-row wrap' }, h('span', { class: 'ops-lbl' }, '맨 위 제목'), titleIn),
        h('div', { class: 'ops-row wrap' }, h('span', { class: 'ops-lbl' }, '마무리 글'), outroIn),
        h('div', { class: 'ops-row wrap' }, amtSw.el, h('span', { class: 'ops-lbl' }, '속도'), h('div', { class: 'ops-chips inline' }, speedBtns)),
        h('div', { class: 'ops-row wrap' }, bBuild,
            h('span', { class: 'ops-hint inline' }, '띄울 때의 명단을 얼려 둬요 — 그 뒤 들어온 후원은 [다시 만들기]를 눌러야 들어가요')),
        h('p', { class: 'ops-hint' }, "익명 · 순위에서 뺀 이름 · 후원 테스트 · 다시 보기/다시 송출은 빠져요. 순서표 단계로 쓰려면 크레딧을 띄운 채 무대 탭에서 [+ 단계]를 누르세요."),
    ));

    let lastSig = '', lastList = '';
    function render(slices) {
        const c = slices.credits || {};
        const o = slices.credits_ops || {};
        amtSw.set(!!c.show_amount);
        if (!dirty.has('title')) setVal(titleIn, c.title || '');
        if (!dirty.has('outro')) setVal(outroIn, c.outro || '');
        speedBtns.forEach(b => { const on = b.dataset.speed === (c.speed || 'normal'); b.classList.toggle('on', on); b.setAttribute('aria-pressed', String(on)); });

        const sig = sigOf(c.on, c.paused, c.speed, o.built, o.built_at, o.stale, o.count, o.anon, (o.groups || []).map(g => [g.title, (g.names || []).length]));
        if (sig !== lastSig) {
            lastSig = sig;
            const spd = (SPEED.find(x => x[0] === c.speed) || SPEED[1])[1];
            state.className = 'ops-now' + (c.on ? '' : ' off');
            if (c.on) fill(state, h('b', null, c.paused ? '⏸ 크레딧 멈춤' : '● 크레딧 흐르는 중'), ' · ' + spd);
            else state.replaceChildren('꺼져 있어요 — 누르면 맨 처음부터 흘러요');
            bPause.textContent = c.on && c.paused ? '▶ 이어서' : '⏸ 멈춤';
            bPause.disabled = !c.on;
            bHide.disabled = !c.on;
            bShow.textContent = c.on ? '🎬 크레딧 떠 있음 (다시 띄우기)' : '🎬 엔딩 크레딧 띄우기';

            if (o.built) {
                const gs = o.groups || [];
                fill(summary,
                    h('div', { class: 'cr-total' }, h('b', null, num(o.count || 0) + '명'),
                        o.anon ? h('span', { class: 'ops-dim' }, ' · 이름 없는 후원 ' + num(o.anon) + '건') : null,
                        o.built_at ? h('span', { class: 'ops-dim' }, ' · ' + clock(o.built_at / 1000) + ' 에 만든 명단') : null),
                    gs.length ? h('div', { class: 'ops-chips cr-gchips' }, gs.map(g => h('span', { class: 'cr-gchip' + (g.kind !== 'member' ? ' soft' : '') },
                        g.title, h('b', null, ' ' + num((g.names || []).length))))) : h('p', { class: 'ops-hint' }, '아직 이름을 올릴 후원이 없어요'));
            } else {
                fill(summary, h('p', { class: 'ops-hint' }, '띄우면 지금 장부로 명단을 만들어요 — [다시 만들기]로 미리 볼 수도 있어요'));
            }
            stale.hidden = !(o.built && o.stale);
            if (o.built && o.stale) fill(stale, '명단을 만든 뒤 후원 · 배정이 바뀌었어요 — 넣으려면 [🔄 명단 다시 만들기]');
        }
        const lsig = sigOf(o.built_at, o.groups, !!c.show_amount);
        if (lsig !== lastList) {
            lastList = lsig;
            const gs = o.groups || [];
            fill(list, gs.length ? gs.map(g => h('div', { class: 'cr-lg' },
                h('div', { class: 'cr-lt' }, g.title + ' · ' + num((g.names || []).length) + '명'),
                h('div', { class: 'cr-ln' }, (g.names || []).map(r => h('span', null, r.name, c.show_amount ? h('i', null, ' ' + num(r.total) + '원') : null))))) :
                [h('p', { class: 'ops-hint' }, o.built ? '명단이 비어 있어요' : '아직 만들지 않았어요')]);
        }
    }
    return { render };
}
