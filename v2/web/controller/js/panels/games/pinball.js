/* 🎱 구슬 핀볼 — 물리는 방송판이 굴리고(같은 씨앗 → 모든 화면이 같은 경기), 결과는 방송판의 첫 보고만 받는다.

   참가자 표(한 줄 = 이름 · 구슬 수) → 고치면 0.9초 뒤 저절로 pinball.setup{names:'밍밍, 양양*3', map, rule, picks, skills}
   [굴리기] pinball.start{…같은 값} · [초기화] pinball.reset(순위 지우기) · [띄우기/내리기] pinball.show{on}
   ⚠️ 굴러가는 중에는 서버가 명단 변경을 막는다(409) — 그때는 조용히 미루고, 다음 [굴리기] 가 명단을 같이 보낸다.
   ⚠️ 서버 명단으로 표를 다시 채우는 것은 손이 표에서 떠나 있고 저장할 것이 없을 때만(치는 중에 글자가 사라지지 않게). */
import { h, num } from '../../util.js';
import { head, seg, memo, syncVal, okToTake, tile, numInput, toInt, onEnter, rosterNames } from './common.js';

const MAX = 800;
const COLS = ['#ff4d6d', '#ffd166', '#4dd6a8', '#4da3ff', '#c77dff', '#ff9e4d', '#7bed9f', '#ff6ec7', '#5ee7df', '#ffe066', '#a29bfe', '#fd79a8'];
const MAPS = [[-1, '🎱 우리 코스', '먼저 6~11초 / 끝까지 14~21초 (가장 짧음)'], [0, 'Wheel of fortune', '먼저 10~17초 / 끝까지 17~31초'],
    [1, 'BubblePop', '먼저 17~21초 / 끝까지 23~27초'], [3, 'Yoru ni Kakeru', '먼저 31~45초 / 끝까지 41~61초 (가장 긺)']];

/** '밍밍, 양양*3, 밍밍' → [{밍밍,2},{양양,3}] — 같은 이름은 합친다 */
function parse(list) {
    const out = [], at = {};
    (list || []).forEach(raw => {
        let nm = String(raw || '').trim(), c = 1;
        const m = nm.match(/\*\s*(\d+)\s*$/);
        if (m) { nm = nm.slice(0, m.index).trim(); c = parseInt(m[1], 10) || 1; }
        if (!nm) return;
        if (at[nm] === undefined) { at[nm] = out.length; out.push({ name: nm, count: 0 }); }
        out[at[nm]].count = Math.min(MAX, out[at[nm]].count + c);
    });
    return out;
}

export function mountPinball(el, ctx) {
    const paint = memo();
    let g = {}, slices = {}, saveT = 0, dirty = false;

    const hd = head('🎱 핀볼', async on => {
        if (on && !(await okToTake(ctx, 'pinball', '핀볼'))) return;
        const res = await ctx.run('pinball.show', { on });
        if (res.ok) ctx.toast(on ? '핀볼판을 방송에 띄웠어요' : '핀볼판을 내렸어요', on ? 'ok' : 'info');
    });

    const goT = tile('굴리기', '판 · 규칙', start, 'go');
    const resetT = tile('초기화', '순위 지우기', async () => { const r = await ctx.run('pinball.reset', {}); if (r.ok) ctx.toast('핀볼 순위를 지웠어요', 'info'); });
    const big = h('div', { class: 'gm-big' }, h('b', null, '0'), h('small', null, '구슬'));
    const state = h('div', { class: 'gm-status gm-pbstate' });

    const ruleSeg = seg([['first', '먼저 들어온 사람'], ['last', '끝까지 남은 사람']], v => setOpt({ rule: v }), '이기는 규칙');
    const picksIn = numInput({ class: 'gm-in num w64', 'aria-label': '몇 명 뽑기' });
    const step = d => { const v = Math.max(1, Math.min(MAX - 1, (toInt(picksIn.value) || 1) + d)); picksIn.value = String(v); setOpt({ picks: v }); };
    picksIn.addEventListener('change', () => { const v = toInt(picksIn.value); if (v !== null && v >= 1) setOpt({ picks: v }); });
    onEnter(picksIn, () => picksIn.blur());
    const skills = h('button', { type: 'button', class: 'btn sm', 'aria-pressed': 'false', title: '구슬이 가끔 주변을 확 밀쳐 순위가 뒤집혀요. 진지한 추첨이면 꺼 두세요.',
        onclick: () => setOpt({ skills: !g.skills }) }, '밀어내기');
    const maps = h('div', { class: 'gm-maps' }, MAPS.map(([v, nm, sub]) => h('button', { type: 'button', class: 'gm-map', 'data-v': String(v), onclick: () => setOpt({ map: v }) },
        h('b', null, nm), h('span', null, sub))));

    const rowsBox = h('div', { class: 'gm-pbrows' });
    const totalEl = h('span', { class: 'gm-info' });
    const savedEl = h('span', { class: 'gm-info' }, '고치면 바로 저장돼요');
    const bulk = h('textarea', { class: 'gm-ta', rows: 3, placeholder: '예) 밍밍, 양양*3, 예지랑', 'aria-label': '이름 한꺼번에' });

    el.append(h('div', { class: 'gm' },
        hd.el,
        h('div', { class: 'gm-tiles' }, goT, resetT, big),
        state,
        h('section', { class: 'gm-box' },
            h('div', { class: 'gm-row' }, h('span', { class: 'gm-lbl' }, '이기는 규칙'), ruleSeg.el),
            h('div', { class: 'gm-row' }, h('span', { class: 'gm-lbl' }, '몇 명 뽑기'),
                h('button', { type: 'button', class: 'btn sm gm-stepb', 'aria-label': '하나 줄이기', onclick: () => step(-1) }, '−'), picksIn,
                h('button', { type: 'button', class: 'btn sm gm-stepb', 'aria-label': '하나 늘리기', onclick: () => step(1) }, '+'),
                skills),
            h('span', { class: 'gm-lbl' }, '판 고르기 (6명 · 5판 실측)'), maps),
        h('section', { class: 'gm-box' },
            h('div', { class: 'gm-sub' }, h('b', null, '참가자'), totalEl),
            rowsBox,
            h('div', { class: 'gm-row' },
                h('button', { type: 'button', class: 'btn sm', onclick: () => { addRow('', 1, true); } }, '＋ 사람 추가'),
                h('button', { type: 'button', class: 'btn sm', onclick: fillPlayers }, '지금 선수 넣기'),
                h('span', { class: 'gm-sp' }), savedEl)),
        h('details', { class: 'gm-fold' }, h('summary', null, '글로 한꺼번에 넣기 ', h('small', null, '쉼표 · 줄바꿈, 양양*3 도 돼요')),
            h('div', { class: 'gm-fold-body' }, bulk, h('div', { class: 'gm-row' }, h('button', { type: 'button', class: 'btn sm', onclick: fromText }, '표로 옮기기'))))));

    /* ── 표 ── */
    function readRows() {
        return [...rowsBox.querySelectorAll('.gm-pbrow')].map(r => ({
            name: (r.querySelector('.pb-n').value || '').replace(/[,\n\r*]+/g, ' ').trim().slice(0, 20),
            count: Math.max(1, Math.min(MAX, toInt(r.querySelector('.pb-c').value) || 1)),
        })).filter(x => x.name);
    }
    function namesText() { return readRows().map(x => x.count > 1 ? `${x.name}*${x.count}` : x.name).join(', '); }
    function paintTotal() {
        const rows = readRows();
        const n = rows.reduce((a, x) => a + x.count, 0);
        totalEl.textContent = `구슬 ${num(n)}개 / ${MAX}개` + (n > MAX ? ' — 넘는 것은 빠져요' : '');
        totalEl.classList.toggle('bad', n > MAX);
        const at = {}; let ci = 0;
        rowsBox.querySelectorAll('.gm-pbrow').forEach(r => {
            const nm = (r.querySelector('.pb-n').value || '').trim();
            const c = Math.max(1, toInt(r.querySelector('.pb-c').value) || 1);
            let col = 'transparent';
            if (nm) { if (at[nm] === undefined) at[nm] = ci++; col = COLS[at[nm] % COLS.length]; }
            r.querySelector('.pb-dot').style.background = col;
            const bar = r.querySelector('.pb-share i');
            bar.style.width = (nm && n ? Math.min(100, c / n * 100) : 0) + '%';
            bar.style.background = col;
        });
    }
    function addRow(name, count, focus) {
        const n = h('input', { type: 'text', class: 'gm-in pb-n', maxlength: 20, placeholder: '이름', autocomplete: 'off', 'aria-label': '참가자 이름' });
        n.value = name || '';
        const c = numInput({ class: 'gm-in num pb-c', 'aria-label': '구슬 수' });
        c.value = String(count || 1);
        const bump = d => { c.value = String(Math.max(1, Math.min(MAX, (toInt(c.value) || 1) + d))); changed(); };
        const row = h('div', { class: 'gm-pbrow' },
            h('span', { class: 'pb-dot', title: '방송판 구슬 색' }), n,
            h('span', { class: 'pb-share', title: '전체 구슬 중 이 사람 몫' }, h('i')),
            h('button', { type: 'button', class: 'btn sm gm-stepb', 'aria-label': '구슬 하나 빼기', onclick: () => bump(-1) }, '−'), c,
            h('button', { type: 'button', class: 'btn sm gm-stepb', 'aria-label': '구슬 하나 더', onclick: () => bump(1) }, '+'),
            h('button', { type: 'button', class: 'icon-btn gm-del', title: '이 사람 빼기', 'aria-label': '이 사람 빼기', onclick: () => { row.remove(); changed(); } }, '✕'));
        [n, c].forEach(i => i.addEventListener('input', changed));
        onEnter(n, () => { const nx = row.nextElementSibling; if (nx) nx.querySelector('.pb-n').focus(); else addRow('', 1, true); });
        rowsBox.append(row);
        if (focus) n.focus();
        paintTotal();
    }
    function setRows(items) {
        rowsBox.replaceChildren();
        (items || []).forEach(x => addRow(x.name, x.count));
        if (!items || !items.length) addRow('', 1);
        paintTotal();
    }
    function changed() {
        paintTotal();
        dirty = true;
        savedEl.textContent = '저장하는 중…';
        clearTimeout(saveT);
        saveT = setTimeout(save, 900);
    }
    async function save() {
        if (g.running) { savedEl.textContent = '굴러가는 중 — 다음 [굴리기] 때 같이 들어가요'; return; }
        const res = await ctx.run('pinball.setup', { names: namesText() }, { quiet: true });
        dirty = false;
        savedEl.textContent = res.ok ? '저장됨 ✓' : `저장 못 함 — ${res.error || '다시 고쳐 보세요'}`;
    }
    function fillPlayers() {
        const names = rosterNames(slices);
        if (!names.length) { ctx.toast('올라와 있는 선수가 없어요', 'err'); return; }
        setRows(names.map(n => ({ name: n, count: 1 })));
        changed();
    }
    function fromText() {
        const items = parse(String(bulk.value || '').split(/[,\n\r]+/));
        if (!items.length) { ctx.toast('옮길 이름이 없어요', 'err'); return; }
        setRows(items);
        bulk.value = '';
        changed();
        ctx.toast('🎱 표로 옮겼어요', 'ok');
    }

    /* ── 보내기 ── */
    async function setOpt(part) {
        if (g.running) { ctx.toast('굴러가는 중에는 바꿀 수 없어요 — 끝난 뒤에', 'err'); return; }
        const res = await ctx.run('pinball.setup', Object.assign({ names: namesText() }, part));
        if (res.ok) { dirty = false; clearTimeout(saveT); savedEl.textContent = '저장됨 ✓'; }
    }
    async function start() {
        if (!(await okToTake(ctx, 'pinball', '핀볼'))) return;
        clearTimeout(saveT);
        const data = { names: namesText(), map: g.map == null ? -1 : g.map, rule: g.rule || 'first', picks: g.picks || 1, skills: !!g.skills };
        const res = await ctx.run('pinball.start', data);
        if (res.ok) { dirty = false; savedEl.textContent = '저장됨 ✓'; ctx.toast('🎱 굴려요!', 'ok'); }
    }

    function paintState() {
        const n = (g.names || []).length, nb = (g.balls || []).length;
        const mp = MAPS.find(x => x[0] === Number(g.map == null ? -1 : g.map)) || MAPS[0];
        const rname = g.rule === 'last' ? '끝까지 남기' : '먼저 골인';
        const picks = Math.max(1, Number(g.picks) || 1);
        const kids = [h('div', null, '판 ', h('b', null, mp[1]), ' · ', h('b', null, `${rname} ${picks}명`), ` · 참가자 ${n}명`,
            nb && nb !== n ? ` (구슬 ${nb}개)` : '', g.skills ? ' · 밀어내기 켜짐' : '')];
        const r = g.result || [];
        if (g.running) kids.push(h('div', { class: 'gm-hot' }, '굴러가는 중… 방송 화면에서 구슬이 떨어지고 있어요. 끝나면 여기에 순위가 떠요.'));
        else if (r.length) {
            const w = (g.winners && g.winners.length) ? g.winners : r;
            kids.push(h('div', { class: 'gm-win' }, '🏆 1등 ', h('b', null, w[0])));
            if (w.length > 1) kids.push(h('div', { class: 'gm-info' }, w.slice(1, 20).map((x, i) => `${i + 2}위 ${x}`).join(' · ') + (w.length > 20 ? ` 외 ${w.length - 20}명` : '')));
        } else kids.push(h('div', { class: 'gm-info' }, n ? '[굴리기] 를 누르면 시작해요' : '참가자를 넣고 [굴리기] 를 누르세요'));
        if ((slices.show || {}).stage !== 'pinball') kids.push(h('div', { class: 'gm-info' }, '방송 화면에 안 떠 있어요 — 굴리면 저절로 떠요'));
        state.replaceChildren(...kids);
        goT.setSub(g.running ? '굴러가는 중…' : `${mp[1]} · ${rname} ${picks}명`);
        big.firstChild.textContent = String(nb || n);
    }

    let first = true;
    return {
        render(s) {
            slices = s;
            g = s.pinball || {};
            hd.setAir((s.show || {}).stage === 'pinball');
            hd.setPill(g.running ? '굴러가는 중' : (g.winners || []).length ? '결과 나옴' : '', g.running ? 'hot' : 'live');
            ruleSeg.set(g.rule === 'last' ? 'last' : 'first');
            syncVal(picksIn, Math.max(1, Number(g.picks) || 1));
            skills.classList.toggle('on', !!g.skills);
            skills.setAttribute('aria-pressed', String(!!g.skills));
            skills.textContent = g.skills ? '밀어내기 켜짐' : '밀어내기 꺼짐';
            maps.querySelectorAll('.gm-map').forEach(b => b.classList.toggle('on', b.dataset.v === String(g.map == null ? -1 : g.map)));
            goT.disabled = !!g.running;
            // 서버 명단 → 표(손이 표에 없고 · 저장할 것이 없고 · 서버 것이 다를 때만)
            const want = parse(g.names || []);
            const have = readRows();
            if (!rowsBox.children.length || ((first || (!dirty && !rowsBox.contains(document.activeElement))) && JSON.stringify(want) !== JSON.stringify(have))) {
                setRows(want);
            }
            first = false;
            paint('state', [g.names, g.balls ? g.balls.length : 0, g.map, g.rule, g.picks, g.skills, g.running, g.result, g.winners, (s.show || {}).stage], paintState);
        },
    };
}
