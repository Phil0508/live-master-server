/* 🎡 룰렛 — 멤버 돌림판 · 벌칙 룰렛. 당첨은 서버가 [정지] 순간에 정한다.

   [돌리기] roulette.spin(무대에 잠깐 올린다) → [정지!!] roulette.stop(서버가 칸 · 각도를 정함) → 다 서면 원래 무대로
   [초기화] roulette.reset · 설정 roulette.config{source, weight, custom}
   🗳️ 선관위(리모컨) roulette.pick{name} — 비공개 조각(roulette_ops)에만 적힌다. 방송판은 조작인지 알 수 없다.
   ⚠️ 서는 중에 고르면 이번 판은 이미 정해져서 다음 판부터 먹는다(서버가 next_round 로 알려 준다).
   화면 약속 5: 조종실도 ends_at + 1초에 roulette.done{round} 를 한 번 보낸다(먼저 온 하나만 받는다). */
import { h, num, clock } from '../../util.js';
import { head, seg, memo, syncVal, serverNow, okToTake, tile } from './common.js';

const PHASE = { idle: ['대기', ''], spinning: ['도는 중', 'hot'], stopping: ['서는 중', 'warn'], done: ['섰음', 'live'] };

/** 지금 설정으로 만든 판 — 서버 roulette.wheel() 과 같은 셈 */
function wheel(slices) {
    const r = slices.roulette || {};
    if (r.source === 'custom') return (r.custom || []).map(n => ({ name: n, w: 1 }));
    const p = slices.players || {};
    const rows = (p.extra_active ? p.extra : p.list) || [];
    const contrib = r.weight === 'contrib';
    return rows.map(x => ({ name: x.name, w: contrib ? Math.max(1, Math.trunc(Number(x.contribution) || 0)) : 1 }));
}

export function mountRoulette(el, ctx) {
    const paint = memo();
    let r = {}, ops = {}, slices = {}, remoteOpen = false;
    const doneSent = new Set();

    const hd = head('🎡 룰렛', async on => {
        if (on) {
            if (!(await okToTake(ctx, 'roulette', '룰렛'))) return;
            const res = await ctx.run('show.stage', { stage: 'roulette' });
            if (res.ok) ctx.toast('룰렛판을 방송에 띄웠어요', 'ok');
        } else {
            const back = (slices.show || {}).ret || null;
            const res = await ctx.run('show.stage', { stage: back });
            if (res.ok) ctx.toast('룰렛판을 내렸어요', 'info');
        }
    });
    const srcLine = h('p', { class: 'gm-status' });

    const spinT = tile('돌리기', '방송에 저절로 뜨고, 다 서면 원래 화면으로', spin, 'go');
    const stopT = tile('정지!!', '누르는 순간 당첨이 정해져요', stop, 'stop');
    const resetT = tile('초기화', '판 · 선관위를 비워요', reset);
    const remoteT = tile('🗳️ 선관위', '당첨 칸 미리 고르기', () => { remoteOpen = !remoteOpen; paintRemote(true); }, 'gold');

    const result = h('div', { class: 'gm-result', hidden: true });

    const srcSeg = seg([['bj', '멤버(점수판)'], ['custom', '직접 입력']], async v => {
        if (v === r.source) return;
        const res = await ctx.run('roulette.config', { source: v });
        if (res.ok) ctx.toast(v === 'custom' ? '직접 입력 칸으로 돌려요 (같은 확률)' : '점수판 멤버로 돌려요', 'ok');
    }, '룰렛 칸');
    const wSeg = seg([['equal', '같은 확률'], ['contrib', '기여도 비례']], async v => {
        if (v === r.weight) return;
        const res = await ctx.run('roulette.config', { weight: v });
        if (res.ok) ctx.toast(v === 'contrib' ? '기여도가 클수록 칸이 넓어요' : '모두 같은 확률이에요', 'ok');
    }, '확률');
    const custom = h('textarea', { class: 'gm-ta', rows: 5, placeholder: '한 줄에 하나\n벌칙 1\n벌칙 2', 'aria-label': '직접 입력 칸' });
    const customSave = h('button', { type: 'button', class: 'btn sm pri', onclick: async () => {
        const items = custom.value.split('\n').map(x => x.trim()).filter(Boolean);
        if (!items.length) { ctx.toast('칸을 하나 이상 적어 주세요', 'err'); return; }
        const res = await ctx.run('roulette.config', { custom: items });
        if (res.ok) { custom.dataset.sv = ''; ctx.toast(`칸 ${items.length}개를 저장했어요 — 다음 [돌리기] 부터`, 'ok'); ctx.rerender(); }
    } }, '칸 저장');
    const customBox = h('div', { class: 'gm-col', hidden: true }, h('span', { class: 'gm-lbl' }, '직접 입력 칸 (한 줄에 하나 · 30개까지 · 같은 이름을 여러 줄 적으면 칸이 넓어져요)'), custom,
        h('div', { class: 'gm-row' }, customSave));

    const remoteBox = h('section', { class: 'gm-box gold', hidden: true });
    const remoteGrid = h('div', { class: 'gm-picks' });
    const remoteNote = h('p', { class: 'gm-info' });
    remoteBox.append(h('div', { class: 'gm-sub' }, h('b', null, '🗳️ 선거관리위원회'), h('span', { class: 'gm-info' }, '조종실에만 보여요 · 방송판에는 안 나가요')),
        h('p', { class: 'gm-info' }, '[정지] 를 누르기 전에 칸을 골라 두면 그 칸에 자연스럽게 감속해 섭니다. [초기화] · 방송 시작/끝에 풀려요.'),
        remoteGrid, remoteNote);

    const hist = h('ol', { class: 'gm-log' });

    el.append(h('div', { class: 'gm' },
        hd.el, srcLine,
        h('div', { class: 'gm-tiles' }, spinT, stopT, resetT, remoteT),
        result,
        remoteBox,
        h('section', { class: 'gm-box' },
            h('div', { class: 'gm-sub' }, h('b', null, '설정'), h('span', { class: 'gm-info' }, '다음 [돌리기] 부터 적용 — 도는 판은 그대로')),
            h('div', { class: 'gm-row' }, h('span', { class: 'gm-lbl' }, '칸'), srcSeg.el),
            h('div', { class: 'gm-row' }, h('span', { class: 'gm-lbl' }, '확률'), wSeg.el),
            customBox),
        h('section', { class: 'gm-box' }, h('div', { class: 'gm-sub' }, h('b', null, '지난 결과'), h('span', { class: 'gm-info' }, '최근 20판 · 조종실에만')), hist)));

    async function spin() {
        if (!(await okToTake(ctx, 'roulette', '룰렛'))) return;
        const res = await ctx.run('roulette.spin', {});
        if (res.ok) ctx.toast(res.already ? '이미 돌고 있어요' : '🎡 돌려요 — [정지!!] 를 누르면 섭니다', 'info');
    }
    async function stop() {
        const res = await ctx.run('roulette.stop', {});
        if (res.ok && !res.already) ctx.toast(`🎡 당첨: ${res.name} — 방송판은 4초쯤 뒤에 서요`, 'ok', 5000);
    }
    async function reset() {
        if (r.phase === 'spinning' || r.phase === 'stopping') {
            const ok = await ctx.confirm({ title: '도는 룰렛을 초기화할까요?', body: '판을 멈추고 원래 화면으로 돌아갑니다. 선관위로 정해 둔 칸도 풀려요.', ok: '초기화', cancel: '그대로 두기' });
            if (!ok) return;
        }
        const res = await ctx.run('roulette.reset', {});
        if (res.ok) ctx.toast('룰렛을 초기화했어요', 'info');
    }

    function paintRemote(force) {
        remoteBox.hidden = !remoteOpen;
        remoteT.classList.toggle('on', remoteOpen);
        remoteT.setSub(remoteOpen ? '닫기' : (ops.pick ? `정해 둠: ${ops.pick}` : '당첨 칸 미리 고르기'));
        if (!remoteOpen) return;
        const items = r.phase === 'spinning' ? (r.items || []) : wheel(slices);
        const total = items.reduce((a, x) => a + x.w, 0) || 1;
        paint('remote', [items, ops.pick, r.phase, force ? Math.random() : 0], () => {
            const pick = ops.pick || null;
            const cells = [h('button', { type: 'button', class: 'gm-pick' + (!pick ? ' on' : ''), onclick: () => choose('') }, '🎯 랜덤 (무조작)')];
            const seen = new Set();
            items.forEach(it => {
                if (seen.has(it.name)) return;          // 같은 이름 칸이 여럿이면 한 번만(서버가 그중 하나에 세운다)
                seen.add(it.name);
                const w = items.filter(x => x.name === it.name).reduce((a, x) => a + x.w, 0);
                cells.push(h('button', { type: 'button', class: 'gm-pick' + (pick === it.name ? ' on' : ''), onclick: () => choose(it.name) },
                    h('b', null, it.name), h('small', null, (w / total * 100).toFixed(1) + '%')));
            });
            remoteGrid.replaceChildren(...cells);
        });
        remoteNote.textContent = r.phase === 'stopping' ? '지금 판은 이미 정해졌어요 — 고르면 다음 판부터 먹어요'
            : !items.length ? '칸이 없어요 — 선수를 넣거나 직접 입력 칸을 적어 주세요' : '';
    }

    async function choose(name) {
        const res = await ctx.run('roulette.pick', { name });
        if (!res.ok) return;
        if (!name) ctx.toast('선관위: 무조작(랜덤)으로 돌려요', 'info');
        else ctx.toast(res.next_round ? `선관위: ${name} — 다음 판부터` : `선관위: ${name} 에 섭니다`, 'ok');
    }

    function scheduleDone() {
        if (r.phase !== 'stopping' || !r.stop || doneSent.has(r.round)) return;
        doneSent.add(r.round);
        const rnd = r.round;
        const wait = Math.max(0, Number(r.stop.ends_at || 0) + 1000 - serverNow());
        setTimeout(() => { ctx.run('roulette.done', { round: rnd }, { quiet: true }); }, wait);
    }

    return {
        render(s) {
            slices = s;
            r = s.roulette || {};
            ops = s.roulette_ops || {};
            const stage = (s.show || {}).stage;
            hd.setAir(stage === 'roulette');
            const ph = PHASE[r.phase] || PHASE.idle;
            hd.setPill(ph[0], ph[1]);
            const p = s.players || {};
            const items = (r.phase === 'spinning' || r.phase === 'stopping') ? (r.items || []) : wheel(s);
            srcLine.textContent = (r.source === 'custom' ? '⚙️ 직접 입력 칸' : p.extra_active ? '⚡ 번외 판 멤버' : '🟢 본판 멤버')
                + ` · 칸 ${items.length}개 · ` + (r.weight === 'contrib' ? '기여도 비례' : '같은 확률')
                + (ops.pick ? ` · 🗳️ 정해 둠: ${ops.pick}` : '');
            const spinning = r.phase === 'spinning', stopping = r.phase === 'stopping';
            spinT.hidden = spinning;
            stopT.hidden = !spinning;
            spinT.disabled = stopping;
            spinT.setSub(stopping ? '서는 중이에요 — 다 서면 다시' : '방송에 저절로 뜨고, 다 서면 원래 화면으로');
            srcSeg.set(r.source || 'bj');
            wSeg.set(r.weight || 'equal');
            wSeg.disable(r.source === 'custom');
            customBox.hidden = r.source !== 'custom';
            if (document.activeElement !== custom) {
                const want = (r.custom || []).join('\n');
                if (custom.dataset.sv !== want) { custom.value = want; custom.dataset.sv = want; }
            }
            const last = (ops.history || [])[0];
            paint('result', [last, r.phase, r.round], () => {
                if (!last) { result.hidden = true; return; }
                result.hidden = false;
                const live = stopping && last.round === r.round;
                result.className = 'gm-result' + (live ? ' live' : '') + (last.cancelled ? ' cancelled' : '');
                result.replaceChildren(
                    h('span', { class: 'gm-lbl' }, live ? '이번 판 당첨 (방송판은 곧 섭니다)' : `${last.round}판 당첨`),
                    h('b', null, last.name),
                    last.picked ? h('span', { class: 'tag warn' }, '🗳️ 선관위') : null,
                    last.cancelled ? h('span', { class: 'tag plain' }, '초기화로 취소') : null);
            });
            paint('hist', ops.history || [], () => {
                const rows = (ops.history || []).slice(0, 8);
                hist.replaceChildren(...(rows.length ? rows.map(x => h('li', { class: 'gm-logrow' },
                    h('span', { class: 'gm-lt' }, clock(x.at, true)),
                    h('span', { class: 'gm-lx' }, `${x.round}판 · `, h('b', null, x.name)),
                    x.picked ? h('span', { class: 'tag warn' }, '🗳️') : null,
                    x.cancelled ? h('span', { class: 'tag plain' }, '취소') : null))
                    : [h('li', { class: 'empty' }, '아직 돌린 판이 없어요')]));
            });
            paintRemote(false);
            scheduleDone();
        },
    };
}
