/* 📥 대기함 — 들어온 후원을 플레이어에게 준다. 방송 중 가장 많이 누르는 곳.

   한 장(카드)에 보이는 것: 시각 · 후원자 · 금액(₩) · 몇 점짜리인지 · 메시지 · (되돌려 돌아옴 / 테스트)
   누르는 것: [플레이어 이름] → pending.assign {id, name}
              [나눠 주기] → 여러 명 고르고 → pending.assign {id, names}(서버가 똑같이 나누고 남는 점수는 앞사람부터)
              [🏺 모금함] → pending.to_jar {id} — 모금함이 켜져 있고(fundjar.enabled) 돈 카드일 때만. 금액(원) 그대로 들어간다
              [무시] → 확인 상자 → pending.ignore {id}
   카드 종류: 후원(돈) · 기여도 카드(kind:'contrib' — 점수 없이 기여도만, 서버가 나눈다)
              · 퇴근 · 탈출 카드(type:'off_work' — 목표를 넘기면 서버가 만든다) → [🚀 송출] offwork.send {id} · [치우기] 확인 → pending.ignore

   ⭐ 순서: 먼저 온 것이 위, 새로 온 것은 맨 아래에 붙는다.
      - 먼저 온 것부터 처리하는 줄서기 순서라 읽기 쉽다.
      - 새 후원이 위에 끼어들면 누르려던 카드가 통째로 밑으로 밀린다. 아래에 붙이면 이미 보이는 카드는 안 움직인다.
      (서버도 같은 순서로 준다. 되돌려 돌아온 후원만 서버가 맨 앞에 넣는다 — '되돌려 돌아옴' 표시를 붙인다.)

   ⭐ 단추가 손 밑에서 움직이지 않게(옛 조종실 freezeBtnOrder 와 같은 까닭):
      이름 단추는 기여도 순(1등부터)이다. 큰 후원 하나를 주면 순위가 바뀌어 모든 카드의 단추가 다시 줄을 선다 —
      연달아 누를 때 손이 기억한 자리에 다른 사람이 와 있으면 그대로 오배정(돈이 걸린 실수)이다.
      그래서 마우스가 대기함 안에 있는 동안(폰은 손가락이 닿은 뒤 1.5초까지)은
        1) 이름 단추 순서를 붙잡아 두고
        2) 처리된 카드는 바로 빼지 않고 같은 높이의 '✓ 처리됨' 자리로 남겨 두고(아래 카드가 위로 당겨 올라오지 않게)
        3) 새로 온 카드(되돌려 돌아온 것 포함)는 맨 아래에만 붙인다.
      손을 빼면 그때 최신 순위 · 순서로 정리된다. */
import { h, won, num, manWon, splitPoints, clock } from './util.js';
import * as ai from './panels/ai/assist.js';     // 🤖 AI 서포트 — 카드 배지 · '지급할까요?' 줄 · 🚗 오토파일럿 · 오배정 경고

const UNFREEZE_AFTER_TOUCH_MS = 1500;

export function mountPending(root, ctx) {
    root.innerHTML = `
        <div class="box-head">
            <h2>대기함 <span class="count-badge" aria-live="polite">0</span></h2>
            <span class="frozen-hint" hidden>마우스를 빼면 정리돼요</span>
        </div>
        <p class="extra-note" hidden>번외 판이 켜져 있어요 — 지금 주는 점수는 <b>번외 판</b>에 들어갑니다.</p>
        <div class="plist"></div>
        <p class="empty">기다리는 후원이 없어요</p>`;
    const list = root.querySelector('.plist');
    const badge = root.querySelector('.count-badge');
    const hint = root.querySelector('.frozen-hint');
    const emptyMsg = root.querySelector('.empty');
    const extraNote = root.querySelector('.extra-note');
    // 🤖 '지급할까요?' 줄은 카드 목록 바로 위 — [✔ 지급] 은 이름 단추와 같은 길(assign)로 준다
    ai.mountAsks(list, ctx, (id, name) => { const it = (ctx.slices.pending || []).find(x => x.id === id); return it ? assign(it, [name]) : undefined; });

    const cards = new Map();    // 후원 id → {el, sig, ghost}
    const busy = new Set();     // 보내는 중인 후원 id
    const split = new Map();    // 나눠 주기 고르는 중: 후원 id → Set(이름)
    const doneLabel = new Map();// 처리됨 자리에 쓸 글자(내가 누른 것)
    let frozen = false, frozenOrder = null, lastOrder = [], touchTimer = 0;

    /* ── 얼리기 ── */
    function freeze(on) {
        if (on === frozen) return;
        frozen = on;
        frozenOrder = on ? lastOrder.slice() : null;
        root.classList.toggle('frozen', on);
        if (!on) ctx.rerender();
    }
    root.addEventListener('pointerenter', e => { if (e.pointerType === 'mouse') freeze(true); });
    root.addEventListener('pointerleave', e => { if (e.pointerType === 'mouse') freeze(false); });
    root.addEventListener('touchstart', () => { clearTimeout(touchTimer); freeze(true); }, { passive: true });
    root.addEventListener('touchend', () => {
        clearTimeout(touchTimer);
        touchTimer = setTimeout(() => freeze(false), UNFREEZE_AFTER_TOUCH_MS);
    }, { passive: true });

    function mergeOrder(frozenNames, names) {
        const have = new Set(names);
        const out = frozenNames.filter(n => have.has(n));
        names.forEach(n => { if (!out.includes(n)) out.push(n); });   // 얼린 뒤 새로 생긴 사람은 맨 뒤에
        return out;
    }

    /* ── 그리기 ── */
    function render(slices) {
        const pend = slices.pending || [];
        ai.sync(slices);                               // 🤖 새 후원 묻기 · 제안 줄 정리 · 오토파일럿 · 먼저 알림(안에서 감싼다)
        const P = slices.players || {};
        const key = P.extra_active ? 'extra' : 'list';
        const names = (P[key] || []).map(r => r.name);
        lastOrder = names;
        const order = frozen && frozenOrder ? mergeOrder(frozenOrder, names) : names;

        badge.textContent = pend.length;
        badge.classList.toggle('zero', !pend.length);
        extraNote.hidden = !P.extra_active;
        root.classList.toggle('has-items', pend.length > 0);

        const jarOn = !!(slices.fundjar && slices.fundjar.enabled);
        const jarName = (slices.fundjar && slices.fundjar.name) || '모금함';
        const ids = new Set(pend.map(x => x.id));
        for (const [id, c] of cards) {
            if (ids.has(id)) continue;
            busy.delete(id);
            split.delete(id);
            if (frozen) { if (!c.ghost) toGhost(id, c); }
            else { c.el.remove(); cards.delete(id); doneLabel.delete(id); }
        }
        pend.forEach(it => {
            let c = cards.get(it.id);
            if (c && c.ghost) {                       // 처리됐다가 되돌려 돌아왔다(얼린 동안) — 그 자리에서 다시 살린다
                c.ghost = false;
                c.sig = '';
                c.el.classList.remove('ghost');
                c.el.style.minHeight = '';
                c.el.inert = false;
            }
            if (!c) {
                c = { el: h('article', { class: 'pcard', 'data-id': it.id }), sig: '', ghost: false };
                cards.set(it.id, c);
                list.append(c.el);                     // 새것은 일단 맨 아래(얼려 있으면 그대로 둔다)
            }
            const sel = split.get(it.id);
            const sig = JSON.stringify([it, order, busy.has(it.id), sel ? [...sel] : null, jarOn, jarName, ai.sig(it.id)]);
            if (sig !== c.sig) { fill(c.el, it, order, jarOn ? jarName : ''); c.sig = sig; }
        });
        if (!frozen) {
            // 서버 순서대로 — 이미 제자리면 옮기지 않는다(옮기면 마우스가 올라간 단추가 깜빡인다)
            pend.forEach((it, i) => {
                const el = cards.get(it.id).el;
                if (list.children[i] !== el) list.insertBefore(el, list.children[i] || null);
            });
        }
        const ghosts = [...cards.values()].some(c => c.ghost);
        hint.hidden = !ghosts;
        emptyMsg.hidden = pend.length > 0 || ghosts;
    }

    function toGhost(id, c) {
        const hgt = c.el.getBoundingClientRect().height;      // offsetHeight 는 정수라 1px 씩 밀린다
        c.ghost = true;
        c.el.style.minHeight = hgt + 'px';
        c.el.className = 'pcard ghost';
        c.el.inert = true;
        c.el.replaceChildren(h('div', { class: 'ghost-msg' }, '✓ ', doneLabel.get(id) || '처리됨'));
    }

    function pointsOf(it) {
        return it.kind === 'contrib' ? Number(it.contrib) || 0 : manWon(it.amount);
    }

    function fill(el, it, order, jar) {
        if (it.type === 'off_work') { fillOff(el, it); return; }
        const isC = it.kind === 'contrib';
        const pts = pointsOf(it);
        const isBusy = busy.has(it.id);
        const sel = split.get(it.id);
        el.className = 'pcard' + (isC ? ' contrib' : '') + (isBusy ? ' busy' : '') + (sel ? ' splitting' : '') + (it.returned ? ' returned' : '');

        const head = h('div', { class: 'pc-head' },
            h('span', { class: 'pc-time' }, clock(it.at)),
            h('b', { class: 'pc-name' }, it.name || '익명'),
            isC ? h('span', { class: 'pc-amt' }, '기여도 카드')
                : h('span', { class: 'pc-amt' }, won(it.amount)),
            h('span', { class: 'pc-pts' + (pts ? '' : ' zero'), title: isC ? '점수 없이 기여도만 오릅니다' : '1만 원 = 1점 (6천 원부터 올림)' },
                isC ? '기여도 ' + num(pts) : pts + '점'));
        const tags = [];
        if (it.returned) tags.push(h('span', { class: 'tag ret' }, '↩ 되돌려 돌아옴'));
        if (it.test) tags.push(h('span', { class: 'tag test', title: '투네이션 테스트 계정으로 들어온 후원이에요' }, '🧪 테스트 계정'));
        if (it.orig_name && it.orig_name !== it.name) tags.push(h('span', { class: 'tag plain' }, '원래 이름: ' + it.orig_name));
        const msg = it.message ? h('p', { class: 'pc-msg' }, it.message) : null;

        // 🏺 모금함 — 켜져 있을 때 · 돈 카드일 때만(기여도 카드는 돈이 아니라 넣을 것이 없다)
        const jarBtn = jar && !isC ? h('button', { class: 'btn sm jar', type: 'button', disabled: isBusy, title: `${won(it.amount)} 을(를) ${jar}에 넣어요 (점수 아님)`,
            onclick: () => toJar(it, jar) }, '🏺 ', jar) : null;
        let btns, foot;
        if (!order.length) {
            btns = h('p', { class: 'muted small' }, '플레이어가 없어요 — 점수판 아래 [명단 고치기]에서 더해 주세요');
            foot = h('div', { class: 'pc-foot' }, jarBtn, ignoreBtn(it, isBusy));
        } else if (sel) {
            btns = h('div', { class: 'pc-players' }, order.map(n => h('button', {
                class: 'pbtn pick' + (sel.has(n) ? ' on' : ''), type: 'button', 'aria-pressed': sel.has(n) ? 'true' : 'false',
                disabled: isBusy, onclick: () => { sel.has(n) ? sel.delete(n) : sel.add(n); ctx.rerender(); },
            }, sel.has(n) ? '✓ ' : '', n)));
            const chosen = order.filter(n => sel.has(n));      // 단추 순서 = 서버에 보내는 순서(남는 점수는 앞사람부터)
            const parts = splitPoints(pts, chosen.length);
            const preview = chosen.length
                ? chosen.map((n, i) => `${n} ${parts[i]}`).join(' · ') + (isC ? ' (기여도)' : '점')
                : '나눌 사람을 눌러서 골라 주세요';
            foot = h('div', { class: 'pc-foot' },
                h('span', { class: 'split-preview' }, preview),
                h('button', { class: 'btn sm', type: 'button', disabled: isBusy, onclick: () => { split.delete(it.id); ctx.rerender(); } }, '취소'),
                h('button', { class: 'btn sm pri', type: 'button', disabled: isBusy || chosen.length < 2,
                    onclick: () => assign(it, chosen) }, chosen.length >= 2 ? `${chosen.length}명에게 나눠 주기` : '2명 이상 골라 주세요'));
        } else {
            btns = h('div', { class: 'pc-players' }, order.map(n => h('button', {
                class: 'pbtn', type: 'button', disabled: isBusy, title: `${n}에게 ${isC ? '기여도 ' + pts : pts + '점'}`,
                onclick: () => assign(it, [n]),
            }, n)));
            foot = h('div', { class: 'pc-foot' },
                isBusy ? h('span', { class: 'sending' }, '보내는 중…') : null,
                jarBtn,
                order.length > 1 ? h('button', { class: 'btn sm', type: 'button', disabled: isBusy,
                    onclick: () => { split.set(it.id, new Set()); ctx.rerender(); } }, '나눠 주기') : null,
                ignoreBtn(it, isBusy));
        }
        // ⚠️ replaceChildren 은 null 을 'null' 글자로 넣는다 — 빈 것은 걸러서 넘긴다
        el.replaceChildren(...[head, tags.length ? h('div', { class: 'pc-tags' }, tags) : null, msg, ai.badge(it), btns, foot].filter(Boolean));
    }

    /* 🏃 퇴근 · 🔥 탈출 카드 — 점수 단추 없이 [송출] · [치우기]만 */
    function fillOff(el, it) {
        const isBusy = busy.has(it.id);
        const hell = it.kind === 'hell';
        el.className = 'pcard offwork' + (isBusy ? ' busy' : '');
        el.replaceChildren(
            h('div', { class: 'pc-head' },
                h('span', { class: 'pc-time' }, clock(it.at)),
                h('b', { class: 'pc-name' }, it.name || ''),
                h('span', { class: 'pc-amt' }, (hell ? '🔥 ' : '🏃 ') + (it.message || (hell ? '탈출 성공' : '퇴근 성공')))),
            h('div', { class: 'pc-tags' }, h('span', { class: 'tag off' }, hell ? '지옥탈출 목표 달성' : '퇴근빵 목표 달성')),
            h('p', { class: 'muted small' }, '[송출] 을 누르면 방송판에 연출이 나가요 — 점수는 그대로예요'),
            h('div', { class: 'pc-foot' },
                isBusy ? h('span', { class: 'sending' }, '보내는 중…') : null,
                h('button', { class: 'btn sm ghost-danger', type: 'button', disabled: isBusy, onclick: () => dismissOff(it) }, '치우기'),
                h('button', { class: 'btn sm pri', type: 'button', disabled: isBusy, onclick: () => sendOff(it) }, '🚀 송출')));
    }

    function ignoreBtn(it, isBusy) {
        return h('button', { class: 'btn sm ghost-danger', type: 'button', disabled: isBusy, onclick: () => ignore(it) }, '무시');
    }

    /* ── 보내기 ── */
    async function assign(it, names) {
        if (busy.has(it.id) || !names.length) return;
        // 🤖 오배정 경고 — 메시지가 다른 사람을 가리키면 한 번 묻는다(취소하면 아무것도 안 한다)
        if (names.length === 1 && !(await ai.okToGive(it, names[0]))) return;
        if (busy.has(it.id)) return;                   // 묻는 사이 다른 단추로 이미 보냈다
        const isC = it.kind === 'contrib';
        const parts = splitPoints(pointsOf(it), names.length);
        const what = names.map((n, i) => `${n} ${isC ? '기여도 ' : ''}+${parts[i]}${isC ? '' : '점'}`).join(' · ');
        doneLabel.set(it.id, what);
        busy.add(it.id);
        ctx.rerender();
        const data = names.length === 1 ? { id: it.id, name: names[0] } : { id: it.id, names };
        const res = await ctx.run('pending.assign', data);
        busy.delete(it.id);
        if (res.ok) {
            split.delete(it.id);
            if (res.already) ctx.toast('이미 처리된 후원이에요 (다른 화면에서 먼저 줬어요)', 'info');
            else ctx.toast(`${what} — ${it.name} ${isC ? '' : won(it.amount)}`.trim(), 'ok');
        } else {
            doneLabel.delete(it.id);
        }
        ctx.rerender();
    }

    async function toJar(it, jarName) {
        if (busy.has(it.id)) return;
        doneLabel.set(it.id, `🏺 ${jarName} +${won(it.amount)}`);
        busy.add(it.id);
        ctx.rerender();
        const res = await ctx.run('pending.to_jar', { id: it.id });
        busy.delete(it.id);
        if (res.ok) {
            if (res.already) ctx.toast('이미 처리된 후원이에요 (다른 화면에서 먼저 했어요)', 'info');
            else ctx.toast(`🏺 ${it.name} ${won(it.amount)} → ${jarName}`, 'ok');
        } else doneLabel.delete(it.id);
        ctx.rerender();
    }

    async function sendOff(it) {
        if (busy.has(it.id)) return;
        const what = it.kind === 'hell' ? '탈출' : '퇴근';
        doneLabel.set(it.id, `🚀 ${it.name} ${what} 송출함`);
        busy.add(it.id);
        ctx.rerender();
        const res = await ctx.run('offwork.send', { id: it.id });
        busy.delete(it.id);
        if (res.ok) {
            if (res.already) ctx.toast('이미 송출했거나 치운 카드예요', 'info');
            else ctx.toast(`🚀 ${it.name} ${what} 연출을 방송판에 보냈어요`, 'ok');
        } else doneLabel.delete(it.id);
        ctx.rerender();
    }

    async function dismissOff(it) {
        if (busy.has(it.id)) return;
        const ok = await ctx.confirm({
            title: '이 카드를 치울까요?',
            body: `${it.name} · ${it.kind === 'hell' ? '지옥 탈출' : '퇴근 성공'}\n방송판에 연출을 보내지 않고 대기함에서 뺍니다.\n목표를 다시 정해 넘기기 전에는 이 사람 카드가 다시 생기지 않아요.`,
            ok: '치우기', cancel: '그대로 두기',
        });
        if (!ok) return;
        doneLabel.set(it.id, '치움');
        busy.add(it.id);
        ctx.rerender();
        const res = await ctx.run('pending.ignore', { id: it.id });
        busy.delete(it.id);
        if (res.ok) ctx.toast(`${it.name} 카드를 치웠어요`, 'info');
        else doneLabel.delete(it.id);
        ctx.rerender();
    }

    async function ignore(it) {
        const ok = await ctx.confirm({
            title: '이 후원을 무시할까요?',
            body: `${it.name} · ${it.kind === 'contrib' ? '기여도 ' + num(it.contrib) : won(it.amount)}\n아무에게도 점수를 주지 않고 대기함에서 뺍니다.`,
            ok: '무시하기', cancel: '그대로 두기',
        });
        if (!ok) return;
        doneLabel.set(it.id, '무시함');
        busy.add(it.id);
        ctx.rerender();
        const res = await ctx.run('pending.ignore', { id: it.id });
        busy.delete(it.id);
        if (res.ok) ctx.toast(`무시했어요 — ${it.name} ${it.kind === 'contrib' ? '' : won(it.amount)}`.trim(), 'info');
        else doneLabel.delete(it.id);
        ctx.rerender();
    }

    return { render };
}
