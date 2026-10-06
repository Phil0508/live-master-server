/* 🤖 자동 진행 — 금액 → 게임 줄 고치기. 서버: auto.games {rules:[{id, min, max(0 = 끝없음), game, on}]}
   · 위에서부터 처음 맞는 줄 하나만 걸린다(서버 autopilot.match_game).
   · 금액 칸은 글자 칸(쉼표 허용) — 칸을 떠날 때 '50,000' 으로 다듬는다. 최대를 비우면 끝없음.
   · 고치는 동안(저장 전)은 서버 값으로 덮지 않는다 — [저장] 이나 [되돌리기] 를 눌러야 다시 맞춘다.
   ⚠️ 하나라도 틀리면 서버가 아무것도 안 바꾼다(까닭은 빨간 알림). */
import { h, num, GAMES, rangeText } from './common.js';
import { blockHead, sigOf, fill, once, parseWon } from '../ops/common.js';

const MAX_ROWS = 20;

export function mountRules(ctx) {
    let rows = [];            // [{id, min:'글자', max:'글자', game, on}]
    let dirty = false;
    const list = h('div', { class: 'au-rules' });
    const empty = h('p', { class: 'ops-hint au-rules-empty' }, '아직 줄이 없어요 — [+ 줄 더하기] 로 금액대와 게임을 정해 주세요.');
    const addBtn = h('button', { type: 'button', class: 'btn sm', onclick: () => { rows.push({ id: '', min: '', max: '', game: 'roulette', on: true }); touch(); } }, '+ 줄 더하기');
    const saveBtn = h('button', { type: 'button', class: 'btn sm pri', onclick: () => once(saveBtn, save) }, '저장');
    const undoBtn = h('button', { type: 'button', class: 'btn sm', onclick: () => { dirty = false; last = ''; ctx.rerender(); } }, '되돌리기');
    const state = h('span', { class: 'ops-hint inline au-dirty' });
    const help = h('ul', { class: 'au-help' },
        h('li', null, h('b', null, '👀 그림자'), " — 게임은 안 하고 '이 후원이면 룰렛을 돌렸을 거예요' 만 적어요."),
        h('li', null, h('b', null, '🎡 룰렛'), ' — 무대가 비었을 때 돌리고 6초 뒤 저절로 멈춰요. 이미 돌고 있거나 다른 판(주사위 · 대결 …)이 올라가 있으면 건너뛰고 까닭을 적어요.'),
        h('li', null, h('b', null, '🎰 슬롯'), ' — 무대가 비었을 때 한 판 돌려요(당첨 시그는 평소처럼 대기줄로).'),
        h('li', null, h('b', null, '🎲 주사위'), ' — 주사위판이 무대에 있을 때, 받는 사람이 정해지면(기계든 사람이든) 그 사람 말을 굴려요. 한 판 값보다 적으면 안 굴려요.'));
    const el = h('section', { class: 'ops-blk' },
        blockHead('금액 → 게임', '위에서부터 처음 맞는 줄 하나만 · 최대를 비우면 끝없음'),
        list, empty,
        h('div', { class: 'ops-row wrap au-rules-btns' }, addBtn, h('span', { class: 'grow' }), state, undoBtn, saveBtn),
        help);

    function touch() {
        dirty = true;
        draw();
    }

    function cell(r, key, label) {
        const inp = h('input', { type: 'text', inputmode: 'numeric', autocomplete: 'off', class: 'au-amt-in', value: r[key],
            placeholder: key === 'max' ? '끝없음' : '0', 'aria-label': label });
        inp.addEventListener('input', () => { r[key] = inp.value; dirty = true; paintState(); });
        inp.addEventListener('blur', () => {
            const v = parseWon(inp.value);
            if (v != null && inp.value.trim()) { inp.value = num(v); r[key] = inp.value; }
            inp.setAttribute('aria-invalid', inp.value.trim() && v == null ? 'true' : 'false');
        });
        return inp;
    }

    function draw() {
        fill(list, rows.map((r, i) => {
            const on = h('input', { type: 'checkbox', 'aria-label': `${i + 1}번째 줄 켜기` });
            on.checked = r.on !== false;
            on.addEventListener('change', () => { r.on = on.checked; touch(); });
            const sel = h('select', { class: 'ops-select au-game-sel', 'aria-label': `${i + 1}번째 줄 게임` },
                Object.entries(GAMES).map(([k, g]) => h('option', { value: k }, `${g.icon} ${g.label}`)));
            sel.value = r.game in GAMES ? r.game : 'roulette';
            sel.addEventListener('change', () => { r.game = sel.value; touch(); });
            const del = h('button', { type: 'button', class: 'ops-mini del', title: '이 줄 지우기', 'aria-label': `${i + 1}번째 줄 지우기`,
                onclick: () => { rows.splice(i, 1); touch(); } }, '🗑');
            return h('div', { class: 'au-rule' + (r.on === false ? ' off' : '') },
                h('label', { class: 'au-rule-on' }, on, h('span', { class: 'au-rule-n' }, `${i + 1}`)),
                h('div', { class: 'au-rule-amt' }, cell(r, 'min', `${i + 1}번째 줄 최소 금액(원)`), h('span', { class: 'au-tilde' }, '~'),
                    cell(r, 'max', `${i + 1}번째 줄 최대 금액(원) — 비우면 끝없음`), h('span', { class: 'au-won' }, '원')),
                sel, del);
        }));
        empty.hidden = rows.length > 0;
        addBtn.disabled = rows.length >= MAX_ROWS;
        paintState();
    }

    function paintState() {
        state.textContent = dirty ? '● 저장 안 한 것이 있어요' : '';
        saveBtn.disabled = !dirty;
        undoBtn.hidden = !dirty;
    }

    async function save() {
        const out = [];
        for (let i = 0; i < rows.length; i++) {
            const r = rows[i];
            const mn = parseWon(r.min);
            const mx = String(r.max || '').trim() ? parseWon(r.max) : 0;
            if (mn == null) { ctx.toast(`${i + 1}번째 줄: 최소 금액을 원 단위 숫자로 적어 주세요`, 'err'); return; }
            if (mx == null) { ctx.toast(`${i + 1}번째 줄: 최대 금액을 숫자로 적거나 비워 주세요(비우면 끝없음)`, 'err'); return; }
            if (mx && mx < mn) { ctx.toast(`${i + 1}번째 줄: 최대가 최소보다 작아요`, 'err'); return; }
            out.push({ id: r.id || '', min: mn, max: mx, game: r.game, on: r.on !== false });
        }
        const res = await ctx.run('auto.games', { rules: out });
        if (!res.ok) return;
        dirty = false;
        last = '';
        ctx.toast(out.length ? `금액 게임 ${out.length}줄을 저장했어요 — ` + out.filter(x => x.on).map(x => `${rangeText(x.min, x.max)} ${GAMES[x.game].icon}`).join(' · ') : '금액 게임 줄을 모두 지웠어요', 'ok');
        ctx.rerender();
    }

    let last = '';
    function render(ap) {
        if (dirty) return;                                   // 고치는 중 — 서버 값으로 덮지 않는다
        const games = Array.isArray(ap.games) ? ap.games : [];
        const sig = sigOf(games);
        if (sig === last) return;
        last = sig;
        rows = games.map(g => ({ id: g.id, min: num(g.min || 0), max: g.max ? num(g.max) : '', game: g.game, on: g.on !== false }));
        draw();
    }
    return { el, render };
}
