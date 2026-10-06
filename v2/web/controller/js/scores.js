/* 🏆 점수판 — 순위 · 이름 · 점수 · 기여도 · [+점수] 칸.

   - [+점수] 칸에 숫자(5, -3)를 적고 Enter → score.add {name, delta, list}
     ⚠️ list 를 꼭 실어 보낸다 — 번외 판이 켜져 있으면 서버는 이름만 온 점수를 번외 판에 넣는다.
        본판 줄에 적은 점수는 본판(main)에, 번외 판 줄에 적은 점수는 번외 판(extra)에.
   - [기여도] → 그 줄 아래에 작은 칸이 열린다 — 점수는 그대로 두고 기여도만 고친다
     (score.add {name, delta: 0, contrib, reason: '손으로 고침'})
   - 맨 아래 줄 운영비 → score.add {target: 'bottom', delta}
   - 번외 판: 시작(extra.start) · 끝(extra.end = 본판에 더하기) · 취소(extra.cancel = 번외 점수 버리기)
   - 명단 고치기(접힌 칸): 플레이어 더하기 · 이름 바꾸기 · 빼기 — 방송 중 이름 오타를 끝내지 않고 고칠 수 있게

   ⭐ 줄은 기여도 순으로 다시 선다. 그런데 칸에 커서가 있는 동안은 줄을 옮기지 않는다(숫자만 바꾼다) —
      적는 중에 내 줄이 다른 자리로 뛰면 다음 Enter 가 엉뚱한 사람에게 간다. 칸을 떠나면 그때 정리된다.
   ⭐ 줄은 이름으로 찾는다(몇 번째 줄인지로 찾지 않는다) — 옛 조종실은 순서가 바뀐 사이 옆 사람 이름이 바뀐 적이 있다. */
import { h, num, signed, parseDelta, toast } from './util.js';

export function mountScores(root, ctx) {
    root.innerHTML = `
        <div class="sec-head">
            <h2>점수판</h2>
            <div class="sec-tools">
                <button class="btn sm extra-start" type="button">번외 판 시작</button>
                <span class="extra-on" hidden>
                    <span class="tag hot">번외 판 진행 중</span>
                    <button class="btn sm pri extra-end" type="button">번외 판 끝 · 본판에 더하기</button>
                    <button class="btn sm ghost-danger extra-cancel" type="button">번외 판 취소</button>
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

    const roster = makeRoster(root.querySelector('.roster'), ctx);

    return {
        render(slices) {
            const P = slices.players || {};
            mainBoard.render(P.list || [], P.bottom);
            const on = !!P.extra_active;
            extraWrap.hidden = !on;
            startBtn.hidden = on;
            onWrap.hidden = !on;
            if (on) extraBoard.render(P.extra || [], null);
            roster.render(P.list || []);
        },
    };
}

/* 한 판(본판 · 번외 판) — 이름으로 줄을 찾아 숫자만 고친다 */
function makeBoard(box, listKey, ctx, withBottom) {
    box.innerHTML = `
        <div class="brow bhead" aria-hidden="true">
            <span>순위</span><span>이름</span><span class="r">점수</span><span class="r">기여도</span><span>점수 더하기</span><span></span>
        </div>
        <div class="brows"></div>
        ${withBottom ? `<div class="brow bottom-row">
            <span class="rank"></span><span class="nm bottom-name">운영비</span><span class="sc r">0</span><span class="ct r"></span>
            <span class="add"><input type="text" inputmode="numeric" enterkeyhint="done" placeholder="+점수" aria-label="운영비 점수 더하기" autocomplete="off"></span><span></span>
        </div>` : ''}
        <p class="empty board-empty" hidden>플레이어가 없어요</p>`;
    const rowsBox = box.querySelector('.brows');
    const rows = new Map();          // 이름 → {el, sc, ct, rank, prev:{score, contribution}}
    const bottom = withBottom ? box.querySelector('.bottom-row') : null;
    let bottomPrev = null;

    if (bottom) {
        const input = bottom.querySelector('input');
        input.addEventListener('keydown', e => onAddKey(e, input, async delta => {
            const res = await ctx.run('score.add', { target: 'bottom', delta });
            if (res.ok) ctx.toast(`운영비 ${signed(delta)}점`, 'ok');
            return res.ok;
        }));
    }
    // 칸에서 나오면 미뤄 둔 줄 정리를 한다
    box.addEventListener('focusout', () => setTimeout(ctx.rerender, 0));

    function makeRow(name) {
        const input = h('input', { type: 'text', inputmode: 'numeric', enterkeyhint: 'done', placeholder: '+점수', autocomplete: 'off', 'aria-label': `${name} 점수 더하기` });
        const fixBtn = h('button', { class: 'cfix-btn', type: 'button', title: '점수는 그대로, 기여도만 고치기', 'aria-expanded': 'false' }, '기여도');
        const fixInput = h('input', { type: 'text', inputmode: 'numeric', enterkeyhint: 'done', placeholder: '예: 3 또는 -2', autocomplete: 'off', 'aria-label': `${name} 기여도만 고치기` });
        const fixGo = h('button', { class: 'btn sm pri', type: 'button' }, '기여도 고치기');
        const fixRow = h('div', { class: 'cfix-row', hidden: true },
            h('span', { class: 'muted small' }, `${name} — 점수는 그대로 두고 기여도만`), fixInput, fixGo);
        const r = {
            el: h('div', { class: 'brow prow', 'data-name': name },
                h('span', { class: 'rank' }), h('span', { class: 'nm' }, name), h('span', { class: 'sc r' }), h('span', { class: 'ct r' }),
                h('span', { class: 'add' }, input), fixBtn, fixRow),
            prev: null,
        };
        r.rank = r.el.children[0];
        r.sc = r.el.children[2];
        r.ct = r.el.children[3];
        input.addEventListener('keydown', e => onAddKey(e, input, async delta => {
            const res = await ctx.run('score.add', { name, delta, list: listKey });
            if (res.ok) ctx.toast(`${listKey === 'extra' ? '[번외] ' : ''}${name} ${signed(delta)}점`, 'ok');
            return res.ok;
        }));
        fixBtn.addEventListener('click', () => {
            const open = fixRow.hidden;
            fixRow.hidden = !open;
            fixBtn.setAttribute('aria-expanded', String(open));
            r.el.classList.toggle('fixing', open);
            if (open) fixInput.focus();
        });
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
                fixBtn.setAttribute('aria-expanded', 'false');
                r.el.classList.remove('fixing');
            }
        };
        fixGo.addEventListener('click', sendFix);
        fixInput.addEventListener('keydown', e => { if (e.key === 'Enter' && !e.isComposing) { e.preventDefault(); sendFix(); } });
        return r;
    }

    function render(list, bot) {
        const typing = box.contains(document.activeElement) && document.activeElement.tagName === 'INPUT';
        const names = new Set(list.map(p => p.name));
        for (const [n, r] of rows) if (!names.has(n)) { r.el.remove(); rows.delete(n); }
        list.forEach((p, i) => {
            let r = rows.get(p.name);
            if (!r) { r = makeRow(p.name); rows.set(p.name, r); rowsBox.append(r.el); }
            setNum(r.sc, p.score, r.prev && r.prev.score);
            setNum(r.ct, p.contribution, r.prev && r.prev.contribution);
            r.prev = { score: p.score, contribution: p.contribution };
            if (!typing) {
                r.rank.textContent = i + 1;
                r.el.classList.toggle('first', i === 0 && !!(p.contribution || p.score));
                if (rowsBox.children[i] !== r.el) rowsBox.insertBefore(r.el, rowsBox.children[i] || null);
            }
        });
        box.querySelector('.board-empty').hidden = list.length > 0;
        if (bottom && bot) {
            bottom.querySelector('.bottom-name').textContent = bot.name || '운영비';
            setNum(bottom.querySelector('.sc'), bot.score, bottomPrev);
            bottomPrev = bot.score;
        }
    }

    return { render };
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
        delBtn.addEventListener('click', async () => {
            const p = it.row || {};
            const has = (p.score || 0) !== 0 || (p.contribution || 0) !== 0;
            const ok = await ctx.confirm({
                title: `'${it.name}' 을(를) 명단에서 뺄까요?`,
                body: has ? `점수 ${num(p.score)} · 기여도 ${num(p.contribution)} 이(가) 함께 사라집니다.` : '점수가 없는 플레이어입니다.',
                ok: '빼기', cancel: '그대로 두기',
            });
            if (!ok) return;
            const res = await ctx.run('players.remove', { name: it.name });
            if (res.ok) ctx.toast(`'${it.name}' 을(를) 명단에서 뺐어요`, 'info');
        });
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
