/* 📣 공지 — 방송판 아래로 흐르는 안내 전광판(옛 조종실 공지 탭 · 서버 notice 조각).
   목록은 적은 순서대로 하나씩, 정한 간격마다 나온다(방송판이 서버 시계로 센다).
   명령: notice.add {text} · notice.edit {index, text} · notice.remove {index} · notice.move {index, dir}
         notice.every {period?, speed?} · notice.now {index} | {text}(목록에 안 넣고 한 번만) · show.hud {key:'notice'}
   ⚠️ 줄을 고치는 중이면 목록을 다시 그리지 않는다 — 손을 떼면 그때 맞춘다(글자가 날아가지 않게).
   ⚠️ 번호(index)로 고치는 명령이라, 묻는 사이(확인 상자) 다른 화면이 순서를 바꿨을 수 있다 → 같은 글을 다시 찾는다. */
import { h, num, sigOf, onEnter, setVal, once, switchEl, blockHead, fill } from './common.js';

const MAX = 30, LEN = 120, MIN_PERIOD = 20;
const SPEEDS = [[90, '느리게 흐름'], [130, '보통 속도'], [180, '빠르게 흐름'], [240, '아주 빠르게']];
const CHIPS = [60, 120, 180, 300, 600];

function everyText(sec) {
    sec = Math.round(sec);
    const m = Math.floor(sec / 60), r = sec % 60;
    return ((m ? m + '분' : '') + (m && r ? ' ' : '') + (r ? r + '초' : '')) || '0초';
}

export function mountNotice(el, ctx) {
    const sw = switchEl('방송판에 공지 띄우기', async on => {
        const res = await ctx.run('show.hud', { key: 'notice', on });
        if (res.ok) ctx.toast(on ? '공지를 켰어요 — 정한 간격마다 나와요' : '공지를 껐어요', on ? 'ok' : 'info');
        else { sw.input.checked = !on; }
    }, '켜면 정한 간격마다 저절로 하나씩 나와요');
    const status = h('p', { class: 'ops-now' });
    const minIn = h('input', { type: 'number', class: 'ops-num w-s', min: '0', max: '60', inputmode: 'numeric', 'aria-label': '간격 분' });
    const secIn = h('input', { type: 'number', class: 'ops-num w-s', min: '0', max: '59', inputmode: 'numeric', 'aria-label': '간격 초' });
    const chipBtns = CHIPS.map(s => h('button', { type: 'button', class: 'ops-chip sm', 'data-sec': s, onclick: () => setEvery(s) }, everyText(s)));
    const speedSel = h('select', { class: 'ops-select', 'aria-label': '흐르는 빠르기', title: '흐르는 빠르기 — 뜨는 시간은 글자 길이에 맞춰 저절로 정해져요' },
        SPEEDS.map(([v, n]) => h('option', { value: v }, n)));
    const list = h('ol', { class: 'ntc-list' });
    const empty = h('p', { class: 'ops-hint' }, '아직 공지가 없어요 — 아래 칸에 적고 [공지 추가]');
    const count = h('span', { class: 'ops-sub' });
    const addIn = h('input', { type: 'text', maxlength: String(LEN), autocomplete: 'off', class: 'grow',
        placeholder: '새 공지 — 예) 계좌로 보내실 때 *닉네임+플레이어* 를 적어 주세요', 'aria-label': '새 공지' });
    const addBtn = h('button', { type: 'button', class: 'btn pri sm', onclick: () => once(addBtn, add) }, '＋ 공지 추가');
    const onceBtn = h('button', { type: 'button', class: 'btn sm', title: '목록에 넣지 않고 지금 한 번만 흘려요', onclick: () => once(onceBtn, shootOnce) }, '⚡ 한 번만 띄우기');
    const donors = h('p', { class: 'ops-note gold', hidden: true });

    el.classList.add('ops', 'ops-notice');
    el.append(
        h('div', { class: 'ops-toprow' }, sw.el),
        status,
        h('section', { class: 'ops-blk' }, blockHead('간격 · 빠르기'),
            h('div', { class: 'ops-row wrap' }, minIn, h('span', null, '분'), secIn, h('span', null, '초마다 하나씩'),
                h('span', { class: 'ops-chips inline' }, chipBtns), speedSel)),
        h('section', { class: 'ops-blk' }, h('div', { class: 'ops-bh' }, h('h3', null, '공지 목록'), count), list, empty,
            h('div', { class: 'ops-row wrap ntc-add' }, addIn, addBtn, onceBtn),
            h('p', { class: 'ops-hint' }, '오른쪽 → 왼쪽으로 한 번 흐르고 사라져요. 강조할 말은 *별표* 로 감싸면 금색 굵게 나와요.')),
        donors,
    );

    /* ── 간격 · 빠르기 ── */
    async function setEvery(sec) {
        sec = Math.max(MIN_PERIOD, Math.min(3600, Math.round(Number(sec) || 0)));
        const res = await ctx.run('notice.every', { period: sec });
        if (res.ok) ctx.toast(`📣 ${everyText(sec)}마다 하나씩`, 'ok');
        lastEvery = '';
        ctx.rerender();
    }
    function everyFromInputs() {
        const m = parseInt(minIn.value, 10) || 0, s = parseInt(secIn.value, 10) || 0;
        if (m * 60 + s < MIN_PERIOD) ctx.toast(`${MIN_PERIOD}초보다 짧게는 안 돼요 — ${MIN_PERIOD}초로 맞출게요`, 'info');
        setEvery(m * 60 + s);
    }
    [minIn, secIn].forEach(i => {
        i.addEventListener('change', everyFromInputs);
        onEnter(i, () => i.blur());
    });
    speedSel.addEventListener('change', async () => {
        const res = await ctx.run('notice.every', { speed: parseInt(speedSel.value, 10) || 130 });
        if (res.ok) ctx.toast('📣 흐르는 빠르기를 바꿨어요', 'ok');
        lastEvery = '';
        ctx.rerender();
    });

    /* ── 목록 ── */
    const msgsNow = () => ((ctx.slices.notice || {}).msgs || []).slice();

    async function add() {
        const t = addIn.value.trim();
        if (!t) { addIn.focus(); return; }
        if (msgsNow().length >= MAX) { ctx.toast(`공지는 ${MAX}개까지예요`, 'err'); return; }
        const res = await ctx.run('notice.add', { text: t });
        if (res.ok) { addIn.value = ''; ctx.toast(`📣 ${msgsNow().length}번 공지를 추가했어요`, 'ok'); }
    }
    onEnter(addIn, () => once(addBtn, add));

    async function shootOnce() {
        const t = addIn.value.trim();
        if (!t) { ctx.toast('띄울 글을 칸에 적어 주세요', 'info'); addIn.focus(); return; }
        const res = await ctx.run('notice.now', { text: t });
        if (res.ok) { addIn.value = ''; ctx.toast('📣 지금 한 번 띄워요 — ' + t.slice(0, 26), 'ok'); }
    }

    // 같은 글이 지금 몇 번째인지 — 묻는 사이 순서가 바뀌었을 수 있다
    function findIndex(i, text) {
        const m = msgsNow();
        if (m[i] === text) return i;
        return m.indexOf(text);
    }

    async function edit(i, input, orig) {
        const t = input.value.replace(/\s+/g, ' ').trim();
        if (t === orig) return;
        if (!t) { input.value = orig; ctx.toast('비우려면 🗑 를 누르세요', 'info'); return; }
        const k = findIndex(i, orig);
        if (k < 0) { ctx.toast('그 사이 목록이 바뀌었어요 — 다시 고쳐 주세요', 'err'); lastList = ''; ctx.rerender(); return; }
        const res = await ctx.run('notice.edit', { index: k, text: t });
        if (res.ok) ctx.toast(`📣 ${k + 1}번 공지를 고쳤어요`, 'ok');
        else input.value = orig;
    }

    async function move(i, dir, text) {
        const k = findIndex(i, text);
        if (k < 0) return;
        await ctx.run('notice.move', { index: k, dir });
    }

    async function remove(i, text) {
        const ok = await ctx.confirm({ title: `${i + 1}번 공지를 지울까요?`, body: '"' + text.slice(0, 60) + '"', ok: '지우기', cancel: '그대로 두기' });
        if (!ok) return;
        const k = findIndex(i, text);
        if (k < 0) { ctx.toast('이미 지워진 공지예요', 'info'); return; }
        const res = await ctx.run('notice.remove', { index: k });
        if (res.ok) ctx.toast('📣 공지를 지웠어요', 'info');
    }

    async function now(i, text) {
        const k = findIndex(i, text);
        if (k < 0) return;
        const res = await ctx.run('notice.now', { index: k });
        if (res.ok) ctx.toast('📣 지금 띄워요 — ' + text.slice(0, 26), 'ok');
    }

    function row(m, i, n) {
        const input = h('input', { type: 'text', maxlength: String(LEN), value: m, 'aria-label': `${i + 1}번 공지`, title: '고치고 Enter' });
        input.addEventListener('change', () => edit(i, input, m));
        onEnter(input, () => input.blur());
        input.addEventListener('keydown', e => { if (e.key === 'Escape') { input.value = m; input.blur(); } });
        const b = (txt, title, fn, cls) => {
            const btn = h('button', { type: 'button', class: 'ops-mini' + (cls ? ' ' + cls : ''), title, 'aria-label': title, onclick: () => once(btn, fn) }, txt);
            return btn;
        };
        const up = b('↑', '앞으로', () => move(i, -1, m));
        const dn = b('↓', '뒤로', () => move(i, 1, m));
        up.disabled = i === 0;
        dn.disabled = i === n - 1;
        return h('li', { class: 'ntc-row', 'data-i': i },
            h('span', { class: 'ntc-n' }, String(i + 1)), input,
            h('span', { class: 'ntc-b' }, up, dn,
                b('⚡ 지금', '이 공지를 지금 한 번 띄워요(순서는 그대로)', () => now(i, m), 'go'),
                b('🗑', '지우기', () => remove(i, m), 'del')));
    }

    // 손을 떼면(칸 밖으로) 그동안 미뤄 둔 목록을 맞춘다
    list.addEventListener('focusout', () => setTimeout(() => ctx.rerender(), 0));

    let lastList = '', lastEvery = '', lastHead = '', lastDon = '';
    function render(slices) {
        const n = slices.notice || {};
        const msgs = n.msgs || [];
        const on = !!((slices.show || {}).hud || {}).notice;
        sw.set(on);

        const per = Math.max(MIN_PERIOD, parseInt(n.period, 10) || 300);
        const donorsList = (slices.tallies || {}).notice_donors || [];
        const head = sigOf(on, msgs.length, per, donorsList.length > 0, n.now && n.now.ts);
        if (head !== lastHead) {
            lastHead = head;
            const k = msgs.length + (donorsList.length ? 1 : 0);
            status.className = 'ops-now' + (on && msgs.length ? '' : ' off');
            if (!msgs.length) status.replaceChildren('공지가 아직 없어요 — 아래 칸에 적고 ', h('b', null, '[＋ 공지 추가]'));
            else if (!on) status.replaceChildren(h('b', null, '꺼져 있어요'), ` — 위 스위치를 켜면 ${everyText(per)}마다 1번부터 차례대로 나와요`);
            else fill(status, h('b', null, '켜짐'), ` — ${num(msgs.length)}개를 ${everyText(per)}마다 하나씩`,
                donorsList.length ? ' (소액 후원 줄 1칸 포함)' : '', ` · 한 바퀴 ${everyText(k * per)}`);
            if (n.now && n.now.ts) {
                const d = new Date(n.now.ts);
                const p = x => String(x).padStart(2, '0');
                const what = n.now.idx >= 0 ? `${n.now.idx + 1}번` : '한 번만 띄운 글';
                status.append(h('span', { class: 'ops-dim' }, ` · 마지막 바로 띄우기 ${p(d.getHours())}:${p(d.getMinutes())} (${what})`));
            }
        }

        const every = sigOf(per, n.speed);
        if (every !== lastEvery) {
            lastEvery = every;
            setVal(minIn, Math.floor(per / 60));
            setVal(secIn, per % 60);
            const sp = String(parseInt(n.speed, 10) || 130);
            if (![...speedSel.options].some(o => o.value === sp)) speedSel.append(h('option', { value: sp }, `직접 정한 빠르기 (${sp})`));
            if (document.activeElement !== speedSel) speedSel.value = sp;
            chipBtns.forEach(b => b.classList.toggle('on', Number(b.dataset.sec) === per));
        }

        const sig = sigOf(msgs);
        const ae = document.activeElement;
        const editing = !!ae && ae.tagName === 'INPUT' && list.contains(ae);     // 단추에 초점이 있는 것은 괜찮다(↑ 누른 뒤 바로 보여야 한다)
        if (sig !== lastList && !editing) {
            lastList = sig;
            list.replaceChildren(...msgs.map((m, i) => row(m, i, msgs.length)));
            empty.hidden = msgs.length > 0;
            count.textContent = `${msgs.length}/${MAX}`;
            addBtn.disabled = msgs.length >= MAX;
        }

        const dsig = sigOf(donorsList);
        if (dsig !== lastDon) {
            lastDon = dsig;
            donors.hidden = !donorsList.length;
            if (donorsList.length) {
                const last = donorsList.slice(-8);
                donors.replaceChildren('💛 ', h('b', null, `소액 후원 ${donorsList.length}건`), ' — 공지 순서 맨 끝에 한 줄로 함께 나가요',
                    h('br'), h('span', { class: 'ops-dim' }, last.map(x => `${x.name || '익명'} ${num(x.amount)}원`).join(' · ')
                        + (donorsList.length > last.length ? ` 외 ${donorsList.length - last.length}분` : '')));
            }
        }
    }
    return { render };
}
