/* 🎬 무대 줄 — 가운데 칸 맨 위(#stagebar) · 시안 B 묶음 B(10-17 w2center). **탭을 바꿔도 남는다**(#center 맨 위, PC 는 붙어 있음).

   [무대 이름] [덮기: 시그 리액션] │ 진행 중인 판 단추 │ 순서표: 지금 단계 · [◀] [다음 ▶ 이름] [+ 단계] [편집]

   - 무대 이름 = show.stage(ops/stage.js STAGE_NAME · games/common.js STAGE_LABEL). 비면 '무대 비어 있음'.
   - 덮기 = 시그니처가 돌고 있으면(queue.items 있고 안 멈춤) — 방송판에서 시그니처가 무대 위를 덮는다.
   - 진행 중인 판(옛 상황 띠 · 머리줄 타이머를 여기로):
       대결(match.active) ⚔ 03:12 [▶ 시작/⏸ 멈춤](match.start · match.pause) [+1분](match.add_time {sec:60})
         시계는 서버 시각(games/common.js serverNow) — 돌 때만 · 창이 보일 때만 0.25초마다(setInterval — rAF 는 가려진 창에서 멈춘다)
       시그뒤집기(무대 siggame) [올클리어](sig.allclear — 남은 카드가 있으면 시그뒤집기 탭과 같은 확인 상자)
       주사위(무대 dicegame) [🎲 굴리기](dice.roll — 주사위 탭과 같은 인자: 차례인 말 · 시그 재생 중이면 한 번 묻는다)
   - 순서표 = presets.list · show.cue_at. [◀]/[다음 ▶] show.cue {dir} · [+ 단계] preset.save {name:''} · [편집] 무대 탭(ops-stage)을 연다.
   다시 그릴 때 통째로 갈지 않는다(글자 · 숨김만 바꾼다) — 누르려던 단추가 바뀌지 않게. 소리 없음. */
import { h, num } from './util.js';
import { hicon } from './homeicons.js';
import { STAGE_NAME } from './panels/ops/stage.js';
import { STAGE_LABEL, serverNow, mmss } from './panels/games/common.js';

function setText(el, t) {
    t = String(t);
    if (el.textContent !== t) el.textContent = t;
}

async function once(btn, fn) {
    if (btn.disabled || btn.dataset.busy) return;
    btn.dataset.busy = '1';
    try { await fn(); } finally { delete btn.dataset.busy; }
}

export function mountStagebar(root, ctx) {
    let slices = {}, tick = 0;

    /* 무대 */
    const stName = h('span', { class: 'sgb-nm' }, '무대 비어 있음');
    const cover = h('span', { class: 'sgb-cov', hidden: true, title: '시그니처가 도는 동안 방송판에서 무대 위를 덮어요' }, hicon('layers'), '덮기: 시그 리액션');
    const stageBox = h('div', { class: 'sgb-stage' }, h('span', { class: 'sgb-ic' }, hicon('stage')), stName, cover);

    /* 진행 중인 판 — 대결 */
    const mClock = h('b', { class: 'sgb-clock', 'aria-live': 'off' }, '00:00');
    const mGo = h('button', { type: 'button', class: 'btn xs pri sgb-go', title: '대결 타이머 시작 / 멈춤' }, '▶ 시작');
    const mAdd = h('button', { type: 'button', class: 'btn xs sgb-add', title: '대결 타이머 1분 더하기' }, '+1분');
    const mHeld = h('span', { class: 'sgb-held', hidden: true, title: '시그니처가 끝나면 이어서 돌아요' }, '시그 재생 중');
    const matchBox = h('div', { class: 'sgb-game sgb-match', hidden: true }, h('span', { class: 'sgb-gl' }, '⚔ 대결'), mClock, mHeld, mGo, mAdd);
    mGo.addEventListener('click', () => once(mGo, async () => {
        const t = ((slices.match || {}).timer) || {};
        const res = await ctx.run(t.running ? 'match.pause' : 'match.start', {});
        if (res.ok && !res.already) ctx.toast(t.running ? '타이머를 멈췄어요' : '타이머 시작!', 'info');
    }));
    mAdd.addEventListener('click', () => once(mAdd, async () => {
        const res = await ctx.run('match.add_time', { sec: 60 });
        if (res.ok) ctx.toast('타이머 +1분', 'info');
    }));

    /* 시그뒤집기 */
    const sgAll = h('button', { type: 'button', class: 'btn xs pri sgb-allclear' }, '올클리어');
    const sigBox = h('div', { class: 'sgb-game sgb-sig', hidden: true }, h('span', { class: 'sgb-gl' }, '🃏 시그뒤집기'), sgAll);
    sgAll.addEventListener('click', () => once(sgAll, async () => {
        const g = slices.siggame || {};
        const gs = (g.cards || []).filter(c => c.flippedAt);
        const left = gs.filter(c => !c.doneAt).length;
        if (left > 0) {
            const ok = await ctx.confirm({ title: '올클리어 할까요?', body: `아직 ${left}장이 남아 있어요.\n남은 목표를 전부 달성 처리하고 올클리어를 터뜨립니다.\n(한 방에 몰아서 쏜 후원일 때 쓰는 단추예요)`, ok: '올클리어', cancel: '아직', danger: false });
            if (!ok) return;
        }
        const res = await ctx.run('sig.allclear', {});
        if (res.ok) ctx.toast(`🎉 ALL CLEAR! (${res.count}장${res.filled ? ' · ' + res.filled + '장 한 번에 달성' : ''})`, 'ok');
    }));

    /* 주사위 */
    const dRoll = h('button', { type: 'button', class: 'btn xs pri sgb-roll' }, '🎲 굴리기');
    const dTurn = h('span', { class: 'sgb-turn' }, '');
    const diceBox = h('div', { class: 'sgb-game sgb-dice', hidden: true }, h('span', { class: 'sgb-gl' }, '주사위'), dTurn, dRoll);
    dRoll.addEventListener('click', () => once(dRoll, async () => {
        const q = slices.queue || {};
        if ((q.items || []).length > 0 && !q.paused) {
            const ok = await ctx.confirm({ title: '🎵 시그 재생 중이에요', body: '지금 굴리면 방송 화면에서 굴림이 안 보여요.\n시그가 끝나면 말은 이미 가 있고 카드도 지나가 있어요.\n\n그래도 굴릴까요?', ok: '그래도 굴리기', cancel: '기다리기' });
            if (!ok) return;
        }
        const res = await ctx.run('dice.roll', {});
        if (!res.ok) return;
        const landed = res.tile && res.tile.id != null ? res.tile.id : res.to;
        ctx.toast(`🎲 [${res.piece || '?'}] ${(res.dice || []).join('+')} → ${landed}번 칸${res.tile && res.tile.label ? ' (' + res.tile.label + ')' : ''}`, 'ok', 5000);
        if (res.note) ctx.toast('⚠️ ' + res.note, 'info', 6000);
    }));

    /* 순서표 */
    const cueNow = h('span', { class: 'sgb-cue', title: '순서표 — 지금 단계' }, '순서표 비어 있음');
    const prev = h('button', { type: 'button', class: 'btn xs sgb-prev', title: '이전 단계', 'aria-label': '순서표 이전 단계' }, hicon('prev'));
    const nextT = h('span', { class: 'sgb-nt' }, '다음');
    const next = h('button', { type: 'button', class: 'btn xs sgb-next', title: '순서표 다음 단계로' }, nextT, hicon('play'));
    const add = h('button', { type: 'button', class: 'btn xs sgb-save', title: '지금 방송 화면을 순서표 끝에 단계로 저장' }, hicon('plus'), '단계');
    const edit = h('button', { type: 'button', class: 'btn xs sgb-edit', title: '무대 탭에서 순서표 고치기' }, hicon('edit'), '편집');
    const cueBox = h('div', { class: 'sgb-cues' }, cueNow, prev, next, add, edit);
    const cue = dir => once(dir === 'next' ? next : prev, async () => {
        const res = await ctx.run('show.cue', { dir });
        if (res.ok) ctx.toast('📺 ' + (res.at + 1) + '. ' + (res.name || '단계'), 'ok');
    });
    prev.addEventListener('click', () => cue('prev'));
    next.addEventListener('click', () => cue('next'));
    add.addEventListener('click', () => once(add, async () => {
        const res = await ctx.run('preset.save', { name: '' });
        if (res.ok) ctx.toast('💾 "' + (res.name || '단계') + '" 저장했어요 — 순서표 끝에 붙었어요', 'ok');
    }));
    edit.addEventListener('click', () => { if (ctx.tabs) ctx.tabs.open('ops-stage'); });

    root.append(stageBox, matchBox, sigBox, diceBox, h('span', { class: 'sgb-sp' }), cueBox);

    function paintClock() {
        const t = ((slices.match || {}).timer) || {};
        const left = t.running ? Math.max(0, Number(t.end_ms || 0) - serverNow()) : Number(t.left_ms || 0);
        setText(mClock, mmss(Math.ceil(left / 1000)));
        mClock.classList.toggle('low', !!t.running && left <= 30000);
    }
    function clockLoop(on) {
        if (on && !tick) tick = setInterval(() => { if (!document.hidden && root.offsetParent !== null) paintClock(); }, 250);
        if (!on && tick) { clearInterval(tick); tick = 0; }
    }

    return {
        render(s) {
            slices = s || {};
            const show = slices.show || {};
            const st = show.stage || '';
            setText(stName, st ? (STAGE_NAME[st] || STAGE_LABEL[st] || st) : '무대 비어 있음');
            stName.classList.toggle('none', !st);
            const q = slices.queue || {};
            cover.hidden = !((q.items || []).length > 0 && !q.paused);

            /* 진행 중인 판 */
            const m = slices.match || {};
            const mOn = !!m.active;
            matchBox.hidden = !mOn;
            if (mOn) {
                const t = m.timer || {};
                setText(mGo, t.running ? '⏸ 멈춤' : '▶ 시작');
                mGo.classList.toggle('pri', !t.running);
                mHeld.hidden = !t.held;
                paintClock();
            }
            clockLoop(mOn && !!(m.timer || {}).running);
            sigBox.hidden = st !== 'siggame';
            diceBox.hidden = st !== 'dicegame';
            if (st === 'dicegame') {
                const g = slices.dicegame || {};
                const ps = g.pieces || [];
                const turn = (ps[Number(g.turn) || 0] || {}).name || '';      // 주사위 탭 who() 와 같은 셈
                setText(dTurn, turn ? turn + ' 차례' : '');
            }
            const busy = mOn || st === 'siggame' || st === 'dicegame';
            root.classList.toggle('has-game', busy);

            /* 순서표 */
            const ps = ((slices.presets || {}).list || []).filter(p => p && p.id);
            // 서버 settings2.cue_at 과 같은 셈 — 없거나 null 이면 -1(Number(null) 은 0 이라 '1단계' 로 잘못 보인다)
            const at = show.cue_at != null && Number.isFinite(Number(show.cue_at)) ? Math.trunc(Number(show.cue_at)) : -1;
            if (!ps.length) setText(cueNow, '순서표 비어 있음');
            else if (at < 0 || at >= ps.length) setText(cueNow, `순서표 ${num(ps.length)}단계 · 시작 전`);
            else setText(cueNow, `${at + 1}. ${ps[at].name || '단계'}`);
            cueNow.title = cueNow.textContent;
            cueNow.classList.toggle('none', !ps.length);
            prev.disabled = !(at > 0 && at < ps.length);
            const nx = ps[at + 1];
            next.disabled = !nx;
            next.classList.toggle('pri', !!nx);
            setText(nextT, nx ? '다음 · ' + (nx.name || '단계') : '다음');
            next.title = nx ? `순서표 다음 단계로 — ${at + 2}. ${nx.name || '단계'}` : '다음 단계가 없어요';
        },
    };
}
