/* 🃏 시그 뒤집기 — 덮어 깐 시그니처 카드 중 몇 장을 뒤집어 '목표' 로 삼고, 그 시그를 후원으로 받아내면 달성.

   고르기 POST /api/siggame/picks{picks}(시그니처 목록은 서버가 명령 밖에서 찾는다) → 깔기 sig.deal{minutes, target} →
   뒤집기 sig.flip{id}(되돌릴 수 없어 한 번 묻는다) → 받음 sig.done{id}(사람이 누른다 — 자동으로 안 찍힌다) → 올클리어 sig.allclear
   타이머 sig.timer{START|PAUSE|STOP} · 목표만 올리기 sig.lift{on} · 나머지 까보기 sig.peek · 전부 공개 sig.reveal · 치우기 sig.clear ·
   방송에 띄우기 sig.show{on} · 섞기 sig.shuffle · 투명도 sig.set{opacity}
   ⚠️ 덮인 카드의 속(정답)은 조종실에도 안 온다(siggame_deck 은 숨김 조각) — 번호만 그린다. 까보기 중에 방송판으로 가는
      속도 여기서는 그리지 않는다(화면 공유로 샌다 · 사장님도 모르는 편이 공정).
   고른 번호는 서버가 siggame_picks{ids} 로 돌려준다(저장한 것). 저장 전 고르던 것은 이 컴퓨터에 임시로 둔다(lm2_sg_picks). */
import { h, num, won } from '../../util.js';
import { head, memo, syncVal, serverNow, mmss, okToTake, tile, post, loadSigs, sigsNow, sigsError, numInput, toInt, shown, STAGE_LABEL } from './common.js';

const MAX = 36;
const KEY = 'lm2_sg_picks', KEY_SAVED = 'lm2_sg_saved';

function load(k, dflt) { try { const v = JSON.parse(localStorage.getItem(k) || 'null'); return v == null ? dflt : v; } catch (e) { return dflt; } }
function keep(k, v) { try { localStorage.setItem(k, JSON.stringify(v)); } catch (e) { /* 기억 못 해도 된다 */ } }

export function mountSiggame(el, ctx) {
    const paint = memo();
    let g = {}, slices = {};
    let picks = new Set((load(KEY, []) || []).map(Number).filter(Number.isFinite));
    let saved = Number(load(KEY_SAVED, 0)) || 0;

    const hd = head('🃏 시그뒤집기', async on => {
        if (on) {
            if (!(await okToTake(ctx, 'siggame', '시그뒤집기'))) return;
            const res = await ctx.run('sig.show', { on: true });
            if (res.ok) ctx.toast(res.cards ? '카드판을 방송에 띄웠어요' : '띄웠지만 깔린 카드가 없어요 — «새 판 준비» 에서 카드를 깔아 주세요', res.cards ? 'ok' : 'info');
        } else {
            const res = await ctx.run('sig.show', { on: false });
            if (res.ok) ctx.toast('카드판을 내렸어요 (판은 그대로)', 'info');
        }
    });
    const why = h('div', { class: 'gm-warn', hidden: true });

    const clk = h('div', { class: 'gm-clock sm' }, '10:00');
    const clkT = h('div', { class: 'gm-tile static' }, h('span', { class: 'gm-ts' }, '남은 시간'), clk);
    const playT = tile('▶ 시작', '타이머', async () => {
        const t = g.timer || {};
        const res = await ctx.run('sig.timer', { action: t.status === 'PLAYING' ? 'PAUSE' : 'START' });
        if (res.ok) ctx.toast(t.status === 'PLAYING' ? '타이머를 멈췄어요' : '타이머 시작!', 'info');
    }, 'go');
    const backT = tile('처음 시간으로', '새 판 준비에 적어 둔 시간', async () => {
        const mi = toInt(minIn.value);
        const res = await ctx.run('sig.timer', mi === null ? { action: 'STOP' } : { action: 'STOP', minutes: mi });
        if (res.ok) ctx.toast('타이머를 처음 시간으로 되돌렸어요', 'info');
    });
    const acT = tile('올클리어', '카드를 먼저 뒤집어 주세요', allclear, 'ok');
    const big = h('div', { class: 'gm-big' }, h('b', null, '0/0'), h('small', null, '받음'));
    const strip = h('p', { class: 'gm-status' });

    const boardEl = h('div', { class: 'gm-cards' });
    const remain = h('span', { class: 'gm-info strong' });
    const goals = h('div', { class: 'gm-goals' });
    const goalCnt = h('span', { class: 'gm-info strong' });

    const liftB = h('button', { type: 'button', class: 'btn sm', onclick: lift }, '목표만 올리기');
    const peekB = h('button', { type: 'button', class: 'btn sm', onclick: peek }, '🔍 나머지 까보기');
    const revealB = h('button', { type: 'button', class: 'btn sm', onclick: reveal }, '남은 카드 전부 공개');
    const clearB = h('button', { type: 'button', class: 'btn sm ghost-danger', onclick: clear }, '판 치우기');

    /* 새 판 준비 */
    const targetIn = numInput({ class: 'gm-in num w64', 'aria-label': '뒤집을 장수' });
    const minIn = numInput({ class: 'gm-in num w64', 'aria-label': '시간(분)' });
    minIn.value = String(load('lm2_sg_min', 10));
    minIn.addEventListener('change', () => keep('lm2_sg_min', toInt(minIn.value) ?? 10));
    const opacity = h('input', { type: 'range', min: '10', max: '100', step: '5', class: 'gm-range', 'aria-label': '판 투명도' });
    const opOut = h('output', null, '100%');
    let opTimer = 0, opHold = 0;
    opacity.addEventListener('input', () => {
        opHold = Date.now() + 1500;
        opOut.textContent = opacity.value + '%';
        clearTimeout(opTimer);
        opTimer = setTimeout(() => ctx.run('sig.set', { opacity: Number(opacity.value) / 100 }), 300);
    });
    const prepSum = h('small');
    const pickSum = h('span', { class: 'gm-info' });
    const search = h('input', { type: 'search', class: 'gm-in grow', placeholder: '이름 또는 금액으로 찾기', autocomplete: 'off', 'aria-label': '시그니처 찾기' });
    search.addEventListener('input', () => paintPicker(true));
    const grid = h('div', { class: 'gm-sigs' });
    const prep = h('details', { class: 'gm-fold' }, h('summary', null, '새 판 준비 ', prepSum),
        h('div', { class: 'gm-fold-body' },
            h('div', { class: 'gm-row' }, h('span', { class: 'gm-lbl' }, '뒤집을 장수'), targetIn, h('span', { class: 'gm-lbl' }, '시간(분)'), minIn,
                h('button', { type: 'button', class: 'btn pri', onclick: deal }, '카드 깔기'),
                h('button', { type: 'button', class: 'btn sm', onclick: shuffle }, '🔀 섞기')),
            h('div', { class: 'gm-row' }, h('span', { class: 'gm-lbl' }, '판 투명도'), opacity, opOut),
            h('div', { class: 'gm-sub' }, h('b', null, '깔 시그니처 고르기'), pickSum),
            h('div', { class: 'gm-row' }, search,
                h('button', { type: 'button', class: 'btn sm', onclick: () => autoPick(16) }, '🔀 무작위 16장'),
                h('button', { type: 'button', class: 'btn sm', onclick: () => { picks.clear(); keep(KEY, []); paintPicker(true); } }, '해제'),
                h('button', { type: 'button', class: 'btn sm pri', onclick: savePicks }, '저장')),
            grid));
    prep.addEventListener('toggle', () => { if (prep.open) loadSigs().then(() => paintPicker(true)); });

    el.append(h('div', { class: 'gm' },
        hd.el, why,
        h('div', { class: 'gm-tiles' }, clkT, playT, backT, acT, big),
        strip,
        h('div', { class: 'gm-two wide-left' },
            h('section', { class: 'gm-box' }, h('div', { class: 'gm-sub' }, h('b', null, '카드판 · 눌러서 뒤집기'), remain), boardEl),
            h('section', { class: 'gm-box' }, h('div', { class: 'gm-sub' }, h('b', null, '받아야 할 시그니처'), goalCnt),
                h('p', { class: 'gm-info' }, '시그니처가 실제로 재생되는 순간 «받음» 을 눌러 주세요. 그때 방송 화면에 도장이 찍혀요.'), goals)),
        h('div', { class: 'gm-row' }, liftB, peekB, revealB, h('span', { class: 'gm-sp' }), clearB),
        prep));

    /* ── 보내기 ── */
    async function flip(c) {
        if (c.state === 'REVEALED') { ctx.toast(`${c.id}번은 이미 뒤집혀 있어요`, 'info'); return; }
        const cards = g.cards || [];
        const flipped = cards.filter(x => x.flippedAt).length;
        const ok = await ctx.confirm({ title: `${c.id}번 카드를 뒤집을까요?`, body: `뒤집으면 이번 판의 목표가 되고 되돌릴 수 없어요.\n(지금 ${flipped}/${g.target || 5}장)`, ok: '뒤집기', cancel: '취소', danger: false });
        if (!ok) return;
        const res = await ctx.run('sig.flip', { id: c.id });
        if (!res.ok) return;
        if (res.already) ctx.toast(`${c.id}번은 이미 뒤집혔어요`, 'info');
        else ctx.toast(`🃏 ${c.id}번 → ${res.title || ''} ${won(res.amount)}` + (res.remaining_flips > 0 ? ` (${res.remaining_flips}장 더)` : ' (다 뒤집었어요)'), 'ok', 5000);
    }
    async function toggleDone(c) {
        const res = await ctx.run('sig.done', { id: c.id });
        if (res.ok) ctx.toast(res.done ? `✔ ${c.id}번 받음` : `${c.id}번 받음 취소`, 'info');
    }
    async function allclear() {
        const gs = (g.cards || []).filter(c => c.flippedAt);
        const left = gs.filter(c => !c.doneAt).length;
        if (left > 0) {
            const ok = await ctx.confirm({ title: '올클리어 할까요?', body: `아직 ${left}장이 남아 있어요.\n남은 목표를 전부 달성 처리하고 올클리어를 터뜨립니다.\n(한 방에 몰아서 쏜 후원일 때 쓰는 단추예요)`, ok: '올클리어', cancel: '아직', danger: false });
            if (!ok) return;
        }
        const res = await ctx.run('sig.allclear', {});
        if (res.ok) ctx.toast(`🎉 ALL CLEAR! (${res.count}장${res.filled ? ' · ' + res.filled + '장 한 번에 달성' : ''})`, 'ok');
    }
    async function lift() {
        const on = !g.compact;
        const res = await ctx.run('sig.lift', { on });
        if (res.ok) ctx.toast(on ? '🃏 목표만 올렸어요' : '🃏 판 전체로 되돌렸어요', 'info');
    }
    async function peek() {
        const res = await ctx.run('sig.peek', {});
        if (res.ok) ctx.toast(`🔍 나머지 ${res.count || 0}장을 6초 보여 줘요`, 'info');
    }
    async function reveal() {
        const ok = await ctx.confirm({ title: '남은 카드를 전부 공개할까요?', body: '게임이 끝난 뒤 쓰는 단추예요. 목표에는 안 들어가요.', ok: '전부 공개', cancel: '취소', danger: false });
        if (!ok) return;
        const res = await ctx.run('sig.reveal', {});
        if (res.ok) ctx.toast('남은 카드를 전부 공개했어요', 'info');
    }
    async function clear() {
        const ok = await ctx.confirm({ title: '판을 치울까요?', body: '카드 · 달성 기록 · 타이머를 비우고 방송에서 내립니다.\n고른 시그니처는 그대로 남아요.', ok: '판 치우기', cancel: '그대로 두기' });
        if (!ok) return;
        const res = await ctx.run('sig.clear', {});
        if (res.ok) ctx.toast('판을 치웠어요', 'info');
    }
    async function deal() {
        const cards = g.cards || [];
        if (cards.length) {
            const f = cards.filter(c => c.flippedAt).length;
            const ok = await ctx.confirm({ title: '카드를 다시 깔까요?', body: `이미 ${cards.length}장이 깔려 있어요${f ? ` (뒤집은 카드 ${f}장)` : ''}.\n새로 깔면 지금 판과 달성 기록이 모두 사라져요.`, ok: '다시 깔기', cancel: '그대로 두기' });
            if (!ok) return;
        }
        if (!(await okToTake(ctx, 'siggame', '시그뒤집기'))) return;
        const data = {};
        const mi = toInt(minIn.value), tg = toInt(targetIn.value);
        if (mi !== null) data.minutes = mi;
        if (tg !== null) data.target = tg;
        const res = await ctx.run('sig.deal', data);
        if (res.ok) { ctx.toast(`${res.count}장을 깔았어요 (${res.cols}×${res.rows} · 뒤집을 장수 ${res.target})`, 'ok'); prep.open = false; }
    }
    async function shuffle() {
        if (!(g.cards || []).length) { ctx.toast('먼저 카드를 깔아 주세요', 'err'); return; }
        const ok = await ctx.confirm({ title: '다시 섞을까요?', body: '자리를 다시 섞고 전부 덮어요. 달성 기록도 초기화됩니다.', ok: '섞기', cancel: '그대로 두기' });
        if (!ok) return;
        const res = await ctx.run('sig.shuffle', {});
        if (res.ok) ctx.toast('자리를 다시 섞었어요', 'info');
    }
    async function savePicks() {
        if (!picks.size) { ctx.toast('시그니처를 하나 이상 골라 주세요', 'err'); return; }
        const r = await post('/api/siggame/picks', { picks: [...picks] });
        if (r.status === 200 && r.data.ok) {
            saved = r.data.count || picks.size;
            keep(KEY_SAVED, saved);
            if ((r.data.missing || []).length) ctx.toast(`${r.data.missing.length}장은 목록에 없어 빠졌어요 (저장 ${r.data.count}장)`, 'info', 6000);
            else ctx.toast(`저장했어요 (${r.data.count}장) — 이제 [카드 깔기]`, 'ok');
            ctx.rerender();
        } else {
            ctx.toast(r.why, 'err');
        }
    }
    async function autoPick(n) {
        const all = usable(await loadSigs());
        if (all.length < n) { ctx.toast(`시그니처가 ${n}장보다 적어요 (${all.length}장)`, 'err'); return; }
        const a = all.slice();
        for (let i = a.length - 1; i > 0; i--) { const j = Math.floor(Math.random() * (i + 1)); [a[i], a[j]] = [a[j], a[i]]; }
        picks = new Set(a.slice(0, n).map(x => Number(x.id)));
        keep(KEY, [...picks]);
        paintPicker(true);
        ctx.toast(`${n}장을 무작위로 골랐어요 — [저장] 을 눌러 주세요`, 'info');
    }
    /** 카드에 쓸 수 있는 것 — 사진 있는 것만(옛 것과 같다). 사진 있는 게 하나도 없으면 전부 */
    function usable(all) {
        const rows = (all || []).slice().sort((a, b) => (a.amount || 0) - (b.amount || 0));
        const withImg = rows.filter(x => String(x.image_url || '').trim());
        return withImg.length ? withImg : rows;
    }

    /* ── 그리기 ── */
    function paintPicker(force) {
        pickSum.textContent = (picks.size ? `${picks.size}장 고름` : '아직 안 골랐어요') + (saved ? ` · 저장된 것 ${saved}장` : '');
        if (!prep.open) return;
        const all = sigsNow();
        const q = search.value.trim().toLowerCase();
        paint('grid', [all ? all.length : -1, [...picks], q, force ? Math.random() : 0], () => {
            if (!all) { grid.replaceChildren(h('p', { class: 'empty' }, '시그니처 목록을 불러오는 중…')); return; }
            const list0 = usable(all);
            const list = q ? list0.filter(x => String(x.title || '').toLowerCase().includes(q) || String(x.amount || '').includes(q)) : list0;
            if (!list.length) { grid.replaceChildren(h('p', { class: 'empty' }, all.length ? '찾는 시그니처가 없어요' : (sigsError() || '등록된 시그니처가 없어요'))); return; }
            grid.replaceChildren(...list.map(x => {
                const id = Number(x.id), on = picks.has(id);
                return h('button', { type: 'button', class: 'gm-sig' + (on ? ' on' : ''), 'aria-pressed': String(on), onclick: () => {
                    if (picks.has(id)) picks.delete(id);
                    else { if (picks.size >= MAX) { ctx.toast(`카드는 ${MAX}장까지예요`, 'err'); return; } picks.add(id); }
                    keep(KEY, [...picks]);
                    paintPicker(true);
                } },
                x.image_url ? h('img', { src: x.image_url, alt: '', loading: 'lazy' }) : h('span', { class: 'gm-noimg' }, '🎵'),
                h('span', { class: 'gm-sig-t' }, on ? '✓ ' : '', x.title || '시그니처'),
                h('span', { class: 'gm-sig-a' }, won(x.amount)));
            }));
        });
    }

    function paintBoard() {
        const cards = g.cards || [];
        const cols = Math.max(1, Number(g.cols) || 4);
        if (!cards.length) {
            boardEl.style.removeProperty('--cols');
            boardEl.replaceChildren(h('p', { class: 'empty' }, '아직 카드가 없어요 — 아래 «새 판 준비» 에서 [카드 깔기]'));
            remain.textContent = '';
            return;
        }
        boardEl.style.setProperty('--cols', String(cols));
        boardEl.replaceChildren(...cards.map(c => {
            const open = c.state === 'REVEALED', done = !!c.doneAt;
            return h('button', { type: 'button', class: 'gm-card' + (open ? ' open' : '') + (done ? ' done' : ''),
                title: open ? (c.title || '') : `${c.id}번 뒤집기`, 'aria-label': open ? `${c.id}번 ${c.title || ''}` : `${c.id}번 카드 뒤집기`, onclick: () => flip(c) },
                open && c.image ? h('img', { src: c.image, alt: '' }) : null,
                h('span', { class: 'gm-cno' }, String(c.id)),
                done ? h('span', { class: 'gm-ck' }, '✔') : null);
        }));
        remain.textContent = `뒤집음 ${cards.filter(c => c.flippedAt).length} / ${g.target || 5}`;
    }
    function paintGoals() {
        const cards = g.cards || [];
        const gs = cards.filter(c => c.flippedAt);
        const done = gs.filter(c => c.doneAt).length;
        goalCnt.textContent = gs.length ? `달성 ${done} / ${gs.length}` : '';
        big.firstChild.textContent = `${done}/${gs.length}`;
        if (!gs.length) { goals.replaceChildren(h('p', { class: 'empty' }, '아직 뒤집은 카드가 없어요')); return; }
        goals.replaceChildren(...gs.map(c => {
            const ok = !!c.doneAt;
            return h('div', { class: 'gm-goal' + (ok ? ' done' : '') },
                c.image ? h('img', { src: c.image, alt: '' }) : h('span', { class: 'gm-noimg sm' }, '🎵'),
                h('b', { class: 'gm-gno' }, `${c.id}번`),
                h('span', { class: 'gm-gt' }, c.title || ''),
                h('span', { class: 'gm-ga' }, won(c.amount)),
                h('button', { type: 'button', class: 'btn sm' + (ok ? ' okb' : ''), 'aria-pressed': String(ok), onclick: () => toggleDone(c) }, ok ? '✔ 받음' : '아직'));
        }));
    }
    function paintClock() {
        const t = g.timer || {};
        const playing = t.status === 'PLAYING';
        const left = playing && t.expiresAt ? (Number(t.expiresAt) - serverNow()) / 1000 : Number(t.timeLeft || 0);
        const txt = mmss(left);
        if (clk.textContent !== txt) clk.textContent = txt;
        clk.classList.toggle('hot', playing && left > 0 && left <= 30);
        clk.classList.toggle('over', playing && left <= 0);
    }
    setInterval(() => { if (shown(clk) && (g.timer || {}).status === 'PLAYING') paintClock(); }, 250);

    let prepState = null;
    return {
        render(s) {
            slices = s;
            g = s.siggame || {};
            // 서버에 저장된 고르기 — 이 컴퓨터에 고르던 게 없으면 그걸로 시작한다(다른 기기에서 고른 것도 이어진다)
            const sp = (s.siggame_picks || {}).ids;
            if (Array.isArray(sp)) {
                saved = sp.length;
                if (!picks.size && sp.length) { picks = new Set(sp.map(Number).filter(Number.isFinite)); keep(KEY, [...picks]); }
            }
            const cards = g.cards || [];
            const stage = (s.show || {}).stage;
            const onAir = stage === 'siggame';
            hd.setAir(onAir);
            const target = Number(g.target) || 5;
            const flipped = cards.filter(c => c.flippedAt).length;
            const doneN = cards.filter(c => c.doneAt).length;
            let ph, kind = 'warn';
            if (!cards.length) ph = saved ? '② 카드를 까세요' : '① 시그니처를 고르세요';
            else if (flipped < target) { ph = `③ 카드를 뒤집으세요 (${flipped}/${target})`; kind = 'hot'; }
            else if (doneN < flipped) { ph = `④ 후원을 기다리는 중 (${doneN}/${flipped})`; kind = 'hot'; }
            else { ph = '🎉 전부 달성!'; kind = 'live'; }
            hd.setPill(ph, kind);
            const msg = onAir && !cards.length ? '⚠️ 방송에는 떠 있지만 깔린 카드가 없어요 — 아래 «새 판 준비» 에서 [카드 깔기]'
                : !onAir && cards.length ? `카드는 깔려 있지만 방송 화면에는 안 보여요${stage ? ` (지금 무대: ${STAGE_LABEL[stage] || stage})` : ''} — 위 [방송에 띄우기]` : '';
            why.textContent = msg;
            why.hidden = !msg;
            // 새 판 준비 — 카드가 없으면 펼치고, 깔면 접는다(바뀔 때만 — 게임 중에 펼쳐 본 것을 닫지 않게)
            const empty = !cards.length;
            if (prepState !== empty) { prepState = empty; prep.open = empty; if (empty) loadSigs().then(() => paintPicker(true)); }
            prepSum.textContent = `${picks.size}장 고름 · 뒤집을 ${target}장 · ${toInt(minIn.value) ?? 10}분`;
            syncVal(targetIn, target);
            if (Date.now() > opHold) { const ov = String(Math.round((Number(g.opacity) || 1) * 100)); if (opacity.value !== ov) opacity.value = ov; opOut.textContent = ov + '%'; }
            paint('board', [cards.map(c => [c.id, c.state, !!c.flippedAt, !!c.doneAt, c.state === 'REVEALED' ? c.image : '']), g.cols, target], paintBoard);
            paint('goals', cards.filter(c => c.flippedAt).map(c => [c.id, c.title, c.amount, c.image, !!c.doneAt]), paintGoals);
            const t = g.timer || {};
            playT.setName(t.status === 'PLAYING' ? '⏸ 멈춤' : '▶ 시작');
            playT.classList.toggle('go', t.status !== 'PLAYING');
            paintClock();
            const left = flipped - doneN;
            acT.disabled = !flipped;
            acT.setName(flipped && !left ? '올클리어 터뜨리기' : '올클리어');
            acT.setSub(!flipped ? '카드를 먼저 뒤집어 주세요' : left > 0 ? `남은 ${left}장 한 번에 달성` : '전부 받았어요');
            strip.textContent = !cards.length ? '카드가 없어요 — 아래 «새 판 준비» 에서 깔아 주세요'
                : flipped < target ? `뒤집을 카드 ${target - flipped}장 남음 · 받을 시그 ${left}개`
                : left ? `받을 시그 ${left}개 남음 · 앞으로 받을 돈 ${won(cards.filter(c => c.flippedAt && !c.doneAt).reduce((a, c) => a + (Number(c.amount) || 0), 0))}`
                : '전부 받았어요 — [올클리어] 를 터뜨리세요';
            const canLift = flipped > 0 && flipped <= 5;
            liftB.textContent = g.compact ? '판 전체로' : '목표만 올리기';
            liftB.disabled = !g.compact && !canLift;
            liftB.title = g.compact ? '판 전체로 되돌립니다' : flipped > 5 ? `목표가 ${flipped}장이라 못 올려요 (한 줄에 5장까지)` : flipped ? '목표만 한 줄로 올립니다' : '먼저 카드를 뒤집어 주세요';
            const rest = cards.filter(c => !c.flippedAt).length;
            peekB.disabled = !rest;
            revealB.disabled = !cards.some(c => c.state !== 'REVEALED');
            clearB.disabled = !cards.length;
            paintPicker(false);
        },
    };
}
