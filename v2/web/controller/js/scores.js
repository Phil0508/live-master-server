/* 🏆 점수판 — 순위 · 이름(+기여도 막대) · 점수 · 기여도 · [+점수] 칸 · 🗑 / 운영비 줄 / 🏺 모금함 줄.
   시안 B 모양(10-17 w2center): 줄 격자 40 · 이름 · 84 · 84 · 210 · 44(반 화면 · 폰은 home.css 에서 좁힌다).

   - [+점수] 칸에 숫자(5, -3)를 적고 Enter → score.add {name, delta, list}
     ⚠️ list 를 꼭 실어 보낸다 — 번외 판이 켜져 있으면 서버는 이름만 온 점수를 번외 판에 넣는다.
        본판 줄에 적은 점수는 본판(main)에, 번외 판 줄에 적은 점수는 번외 판(extra)에.
   - **기여도 숫자를 누르면** 그 줄 아래에 작은 칸이 열린다(옛 [기여도] 단추 — class cfix-btn 은 숫자 칸으로 옮겼다)
     점수는 그대로 두고 기여도만 고친다(score.add {name, delta: 0, contrib, reason: '손으로 고침'})
   - 줄 끝 🗑 → 확인 상자(점수 · 기여도가 있으면 같이 사라진다고 알림) → players.remove — 명단 고치기의 [빼기] 와 같은 길
   - 운영비 줄 → score.add {target: 'bottom', delta}
   - 🏺 모금함 줄(새) — 켜기 스위치(ops/common.js setJar — fundjar.set + show.hud 같이) · 금액(종잣돈 + 후원분) 한 번만 ·
     [+ 금액] 칸 Enter → fundjar.add {delta(원), reason: '점수판'} · 깃발 왼쪽/오른쪽(#jar-side-slot — ops/fjside.js 를 작게).
     꺼져 있으면 줄은 남기고 흐리게.
   - 머리: '점수판 · 선수 N명' · [명단] [+ 선수](기본 설정을 열고 명단 고치기로) · 번외 판 시작/끝/취소(extra.*)
   - 명단 고치기(더하기 · 이름 바꾸기 · 빼기)는 랭킹 탭 '기본 설정'(details#basic) 안으로 옮긴다 — 방송 중 이름 오타를 끝내지 않고 고칠 수 있게

   ⭐ 줄은 기여도 순으로 다시 선다. 그런데 칸에 커서가 있는 동안은 줄을 옮기지 않는다(숫자만 바꾼다) —
      적는 중에 내 줄이 다른 자리로 뛰면 다음 Enter 가 엉뚱한 사람에게 간다. 칸을 떠나면 그때 정리된다.
   ⭐ 줄은 이름으로 찾는다(몇 번째 줄인지로 찾지 않는다) — 옛 조종실은 순서가 바뀐 사이 옆 사람 이름이 바뀐 적이 있다. */
import { h, num, won, signed, parseDelta, toast } from './util.js';
import { hicon } from './homeicons.js';
import { openBasic } from './goal.js';
import { setJar, parseWon } from './panels/ops/common.js';
import { mountFjSide } from './panels/ops/fjside.js';

export function mountScores(root, ctx) {
    root.innerHTML = `
        <div class="sec-head bt">
            <h2>점수판</h2><span class="bt-n"></span>
            <div class="sec-tools">
                <button class="btn xs bt-roster" type="button" title="기본 설정의 명단 고치기를 열어요">명단</button>
                <button class="btn xs bt-add" type="button" title="새 선수 더하기">＋ 선수</button>
                <button class="btn xs extra-start" type="button">번외 판 시작</button>
                <span class="extra-on" hidden>
                    <span class="tag hot">번외 판 진행 중</span>
                    <button class="btn xs pri extra-end" type="button">번외 판 끝 · 본판에 더하기</button>
                    <button class="btn xs ghost-danger extra-cancel" type="button">번외 판 취소</button>
                </span>
            </div>
        </div>
        <div class="board main-board"></div>
        <div class="extra-wrap" hidden>
            <h3 class="sub-h">번외 판 <small>— 끝내면 같은 이름의 본판에 더해집니다</small></h3>
            <div class="board extra-board"></div>
        </div>
        <details class="roster">
            <summary>명단 고치기 <small>(더하기 · 이름 바꾸기 · 빼기)</small></summary>
            <div class="roster-body">
                <form class="roster-add">
                    <input type="text" maxlength="20" placeholder="새 플레이어 이름" aria-label="새 플레이어 이름" autocomplete="off">
                    <button class="btn sm pri" type="submit">더하기</button>
                </form>
                <ul class="roster-list"></ul>
            </div>
        </details>`;

    const mainBoard = makeBoard(root.querySelector('.main-board'), 'main', ctx, true);
    const extraBoard = makeBoard(root.querySelector('.extra-board'), 'extra', ctx, false);
    const extraWrap = root.querySelector('.extra-wrap');
    const startBtn = root.querySelector('.extra-start');
    const onWrap = root.querySelector('.extra-on');
    const countEl = root.querySelector('.bt-n');

    startBtn.addEventListener('click', async () => {
        const res = await ctx.run('extra.start', {});
        if (res.ok) ctx.toast('번외 판을 시작했어요 — 대기함에서 주는 점수는 번외 판에 들어갑니다', 'ok');
    });
    root.querySelector('.extra-end').addEventListener('click', async () => {
        const ok = await ctx.confirm({ title: '번외 판을 끝낼까요?', body: '번외 판 점수 · 기여도가 같은 이름의 본판에 더해지고, 번외 판은 닫힙니다.',
            ok: '끝내고 더하기', cancel: '계속', danger: false });
        if (!ok) return;
        const res = await ctx.run('extra.end', {});
        if (res.ok) ctx.toast('번외 판 점수를 본판에 더했어요', 'ok');
    });
    root.querySelector('.extra-cancel').addEventListener('click', async () => {
        const ok = await ctx.confirm({ title: '번외 판을 취소할까요?', body: '번외 판에서 얻은 점수 · 기여도가 본판에 더해지지 않고 모두 버려집니다.',
            ok: '취소하고 버리기', cancel: '그대로 두기' });
        if (!ok) return;
        const res = await ctx.run('extra.cancel', {});
        if (res.ok) ctx.toast('번외 판을 취소했어요', 'info');
    });

    // 명단 고치기 → 랭킹 탭 '기본 설정' 안(맨 위)으로 — 노드를 옮길 뿐 이벤트는 그대로
    const rosterEl = root.querySelector('.roster');
    const basic = document.getElementById('basic');
    if (basic) {
        const sum = basic.querySelector('summary');
        if (sum) sum.after(rosterEl); else basic.prepend(rosterEl);
    }
    const roster = makeRoster(rosterEl, ctx);
    root.querySelector('.bt-roster').addEventListener('click', () => openBasic('.roster summary', '.roster'));
    root.querySelector('.bt-add').addEventListener('click', () => openBasic('.roster-add input', '.roster'));

    return {
        render(slices) {
            const P = slices.players || {};
            mainBoard.render(P.list || [], P.bottom, slices);
            const on = !!P.extra_active;
            extraWrap.hidden = !on;
            startBtn.hidden = on;
            onWrap.hidden = !on;
            if (on) extraBoard.render(P.extra || [], null, slices);
            roster.render(P.list || []);
            const t = `선수 ${num((P.list || []).length)}명`;
            if (countEl.textContent !== t) countEl.textContent = t;
        },
    };
}

/** 명단에서 빼기 — 🗑 와 명단 고치기 [빼기] 가 같이 쓴다(점수 · 기여도가 있으면 같이 사라진다고 묻는다) */
async function removePlayer(ctx, name, p) {
    p = p || {};
    const has = (p.score || 0) !== 0 || (p.contribution || 0) !== 0;
    const ok = await ctx.confirm({
        title: `'${name}' 을(를) 명단에서 뺄까요?`,
        body: has ? `점수 ${num(p.score)} · 기여도 ${num(p.contribution)} 이(가) 함께 사라집니다.` : '점수가 없는 플레이어입니다.',
        ok: '빼기', cancel: '그대로 두기',
    });
    if (!ok) return;
    const res = await ctx.run('players.remove', { name });
    if (res.ok) ctx.toast(`'${name}' 을(를) 명단에서 뺐어요`, 'info');
}

/* 한 판(본판 · 번외 판) — 이름으로 줄을 찾아 숫자만 고친다 */
function makeBoard(box, listKey, ctx, isMain) {
    const head = h('div', { class: 'brow bhead', 'aria-hidden': 'true' },
        h('span', null, '순위'), h('span', null, '이름'), h('span', { class: 'c' }, '점수'), h('span', { class: 'c' }, '기여도'),
        h('span', { class: 'c' }, '점수 추가'), h('span', { class: 'c' }, isMain ? '지우기' : ''));
    const rowsBox = h('div', { class: 'brows' });
    const empty = h('p', { class: 'empty board-empty', hidden: true }, '플레이어가 없어요 — [＋ 선수] 로 더해 주세요');
    box.append(head, rowsBox);
    const rows = new Map();          // 이름 → {el, sc, ct, rank, barI, prev:{score, contribution}}

    let bottom = null, bottomPrev = null, jar = null;
    if (isMain) {
        /* 운영비 줄 */
        const input = h('input', { type: 'text', inputmode: 'numeric', enterkeyhint: 'done', placeholder: '+ 점수', 'aria-label': '운영비 점수 더하기', autocomplete: 'off' });
        bottom = h('div', { class: 'brow bottom-row' },
            h('span', { class: 'rank bic' }, hicon('wallet')), h('span', { class: 'pn' }, h('b', { class: 'nm bottom-name' }, '운영비')),
            h('span', { class: 'sc c' }, '0'), h('span', { class: 'ct c dash' }, '–'), h('span', { class: 'add' }, input),
            h('span', { class: 'lock', title: '운영비는 명단에서 뺄 수 없어요' }, hicon('lock')));
        input.addEventListener('keydown', e => onAddKey(e, input, async delta => {
            const res = await ctx.run('score.add', { target: 'bottom', delta });
            if (res.ok) ctx.toast(`운영비 ${signed(delta)}점`, 'ok');
            return res.ok;
        }));
        jar = makeJarRow(ctx);
        box.append(bottom, jar.el);
    }
    box.append(empty);
    // 칸에서 나오면 미뤄 둔 줄 정리를 한다
    box.addEventListener('focusout', () => setTimeout(ctx.rerender, 0));

    function makeRow(name) {
        const input = h('input', { type: 'text', inputmode: 'numeric', enterkeyhint: 'done', placeholder: '+ 점수', autocomplete: 'off', 'aria-label': `${name} 점수 더하기` });
        const ct = h('button', { class: 'ct c cfix-btn', type: 'button', title: '기여도만 고치기 (점수는 그대로)', 'aria-expanded': 'false', 'aria-label': `${name} 기여도 — 눌러서 고치기` });
        const fixInput = h('input', { type: 'text', inputmode: 'numeric', enterkeyhint: 'done', placeholder: '예: 3 또는 -2', autocomplete: 'off', 'aria-label': `${name} 기여도만 고치기` });
        const fixGo = h('button', { class: 'btn sm pri', type: 'button' }, '기여도 고치기');
        const fixRow = h('div', { class: 'cfix-row', hidden: true },
            h('span', { class: 'muted small' }, `${name} — 점수는 그대로 두고 기여도만`), fixInput, fixGo);
        const barI = h('i');
        const trash = isMain ? h('button', { class: 'trash', type: 'button', title: `${name} 명단에서 빼기`, 'aria-label': `${name} 명단에서 빼기` }, hicon('trash')) : h('span');
        const r = {
            el: h('div', { class: 'brow prow', 'data-name': name },
                h('span', { class: 'rank' }), h('span', { class: 'pn' }, h('b', { class: 'nm', title: name }, name), barI),
                h('span', { class: 'sc c' }), ct, h('span', { class: 'add' }, input), trash, fixRow),
            prev: null, row: null, barI,
        };
        r.rank = r.el.children[0];
        r.sc = r.el.children[2];
        r.ct = ct;
        input.addEventListener('keydown', e => onAddKey(e, input, async delta => {
            const res = await ctx.run('score.add', { name, delta, list: listKey });
            if (res.ok) ctx.toast(`${listKey === 'extra' ? '[번외] ' : ''}${name} ${signed(delta)}점`, 'ok');
            return res.ok;
        }));
        ct.addEventListener('click', () => {
            const open = fixRow.hidden;
            fixRow.hidden = !open;
            ct.setAttribute('aria-expanded', String(open));
            r.el.classList.toggle('fixing', open);
            if (open) fixInput.focus();
        });
        if (isMain) trash.addEventListener('click', () => removePlayer(ctx, name, r.row));
        const sendFix = async () => {
            const c = parseDelta(fixInput.value);
            if (c === null || c === 0) { bad(fixInput, '기여도에 더하거나 뺄 숫자를 적어 주세요 (예: 3, -2)'); return; }
            fixGo.disabled = true;
            const res = await ctx.run('score.add', { name, delta: 0, contrib: c, reason: '손으로 고침', list: listKey });
            fixGo.disabled = false;
            if (res.ok) {
                ctx.toast(`${name} 기여도 ${signed(c)} (점수는 그대로)`, 'ok');
                fixInput.value = '';
                fixRow.hidden = true;
                ct.setAttribute('aria-expanded', 'false');
                r.el.classList.remove('fixing');
            }
        };
        fixGo.addEventListener('click', sendFix);
        fixInput.addEventListener('keydown', e => { if (e.key === 'Enter' && !e.isComposing) { e.preventDefault(); sendFix(); } });
        return r;
    }

    function render(list, bot, slices) {
        const typing = box.contains(document.activeElement) && document.activeElement.tagName === 'INPUT';
        const names = new Set(list.map(p => p.name));
        for (const [n, r] of rows) if (!names.has(n)) { r.el.remove(); rows.delete(n); }
        const topC = list.reduce((m, p) => Math.max(m, Number(p.contribution) || 0), 0);
        list.forEach((p, i) => {
            let r = rows.get(p.name);
            if (!r) { r = makeRow(p.name); rows.set(p.name, r); rowsBox.append(r.el); }
            setNum(r.sc, p.score, r.prev && r.prev.score);
            setNum(r.ct, p.contribution, r.prev && r.prev.contribution);
            r.prev = { score: p.score, contribution: p.contribution };
            r.row = p;
            // 이름 밑 막대 = 기여도 / 1등 기여도
            const w = topC > 0 ? Math.max(0, Math.round((Number(p.contribution) || 0) / topC * 100)) + '%' : '0%';
            if (r.barI.style.width !== w) r.barI.style.width = w;
            if (!typing) {
                r.rank.textContent = i + 1;
                r.el.classList.toggle('first', i === 0 && !!(p.contribution || p.score));
                if (rowsBox.children[i] !== r.el) rowsBox.insertBefore(r.el, rowsBox.children[i] || null);
            }
        });
        empty.hidden = list.length > 0;
        if (bottom && bot) {
            bottom.querySelector('.bottom-name').textContent = bot.name || '운영비';
            setNum(bottom.querySelector('.sc'), bot.score, bottomPrev);
            bottomPrev = bot.score;
        }
        if (jar) jar.render(slices || {});
    }

    return { render };
}

/* 🏺 모금함 줄 — 스위치 · 깃발 왼쪽/오른쪽 · 금액 · [+ 금액] */
function makeJarRow(ctx) {
    const sw = h('input', { type: 'checkbox', class: 'sw mini', role: 'switch', 'aria-label': '모금함 방송판에 띄우기' });
    const state = h('span', { class: 'jar-st' }, '꺼짐');
    const nameEl = h('b', { class: 'nm jar-name' }, '모금함');
    const side = mountFjSide(ctx, { compact: true });
    const slot = h('span', { class: 'jar-side', id: 'jar-side-slot' }, h('span', { class: 'jar-fl' }, '깃발'), side.el);
    const amt = h('span', { class: 'jamt c', title: '' }, '0');
    const input = h('input', { type: 'text', inputmode: 'numeric', enterkeyhint: 'done', placeholder: '+ 금액', autocomplete: 'off', 'aria-label': '모금함에 금액 더하기(원 · 빼려면 -)' });
    const el = h('div', { class: 'brow jar-row off' },
        h('span', { class: 'rank bic' }, hicon('jar')),
        h('span', { class: 'jarL' }, nameEl, sw, state, slot),
        amt, h('span', { class: 'add' }, input), h('span'));
    let busy = false;
    sw.addEventListener('change', async () => {
        if (busy) return;
        busy = true;
        const want = sw.checked;
        try {
            const res = await setJar(ctx, want);
            if (res && res.ok) ctx.toast(want ? '🏺 모금함을 방송판에 띄웠어요' : '🏺 모금함을 내렸어요', 'info');
            else sw.checked = !want;
        } finally { busy = false; }
    });
    input.addEventListener('keydown', e => {
        if (e.key !== 'Enter' || e.isComposing || e.keyCode === 229) return;
        e.preventDefault();
        if (input.dataset.busy) return;
        const d = parseWon(input.value, true);
        if (!d) { bad(input, '더할 금액을 원 단위 숫자로 적어 주세요 (빼려면 -3000)'); return; }
        input.dataset.busy = '1';
        input.classList.add('sending');
        ctx.run('fundjar.add', { delta: d, reason: '점수판' }).then(res => {
            delete input.dataset.busy;
            input.classList.remove('sending');
            if (res.ok) { input.value = ''; ctx.toast(`🏺 ${d > 0 ? '+' : '−'}${won(Math.abs(d))} → 모금함`, 'ok'); }
            else input.select();
        });
    });
    return {
        el,
        render(slices) {
            const j = slices.fundjar || {};
            const on = !!j.enabled;
            if (!busy && sw.checked !== on) sw.checked = on;
            const st = on ? '켜짐' : '꺼짐';
            if (state.textContent !== st) state.textContent = st;
            el.classList.toggle('off', !on);
            const nm = j.name || '모금함';
            if (nameEl.textContent !== nm) nameEl.textContent = nm;
            const total = (Number(j.seed) || 0) + (Number(j.score) || 0);
            const t = num(total) + '원';
            if (amt.textContent !== t) amt.textContent = t;
            amt.title = `종잣돈 ${won(j.seed || 0)} + 후원 ${won(j.score || 0)}`;
            side.render(slices);
        },
    };
}

function setNum(el, v, prev) {
    const t = num(v);
    if (el.textContent === t) return;
    el.textContent = t;
    if (prev != null && prev !== v) {
        el.classList.remove('bump-up', 'bump-down');
        void el.offsetWidth;          // 같은 반짝임을 다시 틀려면 한 번 끊어 줘야 한다
        el.classList.add(v > prev ? 'bump-up' : 'bump-down');
    }
}

/* [+점수] 칸 Enter — 보내고, 잘 되면 칸을 비우고 커서는 그대로(연달아 적기) */
function onAddKey(e, input, send) {
    if (e.key !== 'Enter' || e.isComposing) return;
    e.preventDefault();
    if (input.dataset.busy) return;
    const d = parseDelta(input.value);
    if (d === null) { bad(input, '숫자만 적어 주세요 (예: 5, -3)'); return; }
    if (d === 0) { input.value = ''; return; }
    input.dataset.busy = '1';
    input.classList.add('sending');
    Promise.resolve(send(d)).then(ok => {
        delete input.dataset.busy;
        input.classList.remove('sending');
        if (ok) input.value = '';
        else input.select();
    });
}

function bad(input, msg) {
    input.classList.remove('shake');
    void input.offsetWidth;
    input.classList.add('shake');
    input.setAttribute('aria-invalid', 'true');
    setTimeout(() => input.removeAttribute('aria-invalid'), 1500);
    toast(msg, 'err', 3000);
}

/* 명단 고치기 — 더하기 · 이름 바꾸기 · 빼기 */
function makeRoster(details, ctx) {
    const addForm = details.querySelector('.roster-add');
    const addInput = addForm.querySelector('input');
    const ul = details.querySelector('.roster-list');
    const items = new Map();

    addForm.addEventListener('submit', async e => {
        e.preventDefault();
        const name = addInput.value.trim();
        if (!name) { bad(addInput, '이름을 적어 주세요'); return; }
        const res = await ctx.run('players.add', { name });
        if (res.ok) { addInput.value = ''; ctx.toast(`${name} 을(를) 명단에 더했어요`, 'ok'); }
    });

    function makeItem(name) {
        const input = h('input', { type: 'text', maxlength: 20, autocomplete: 'off', 'aria-label': `${name} 새 이름` });
        input.value = name;
        const renameBtn = h('button', { class: 'btn sm', type: 'button' }, '이름 바꾸기');
        const delBtn = h('button', { class: 'btn sm ghost-danger', type: 'button' }, '빼기');
        const it = { el: h('li', {}, input, renameBtn, delBtn), name, input, row: null };
        const rename = async () => {
            const to = input.value.trim();
            if (!to || to === it.name) { input.value = it.name; return; }
            const res = await ctx.run('players.rename', { from: it.name, to });
            if (res.ok) ctx.toast(`'${it.name}' → '${to}' 이름을 바꿨어요 (점수 · 기여도는 그대로)`, 'ok');
            else input.value = it.name;
        };
        renameBtn.addEventListener('click', rename);
        input.addEventListener('keydown', e => { if (e.key === 'Enter' && !e.isComposing) { e.preventDefault(); rename(); } });
        delBtn.addEventListener('click', () => removePlayer(ctx, it.name, it.row));
        return it;
    }

    return {
        render(list) {
            const names = new Set(list.map(p => p.name));
            for (const [n, it] of items) if (!names.has(n)) { it.el.remove(); items.delete(n); }
            list.forEach(p => {
                let it = items.get(p.name);
                if (!it) {
                    it = makeItem(p.name);
                    items.set(p.name, it);
                    ul.append(it.el);
                }
                it.row = p;
            });
        },
    };
}
