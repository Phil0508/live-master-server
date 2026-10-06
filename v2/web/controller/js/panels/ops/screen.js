/* 🏦 계좌 · 🎬 시작/끝 화면.
   계좌 — account.set {bank, acc_num, name} · 방송판 계좌 자리 켜고 끄기(show.hud account)
   시작/끝 화면 — screen.set {mode:'start', title, minutes, names} · {mode:'end', title} · {mode:'off'}
     시작 전 화면: 한 줄 문구 + 카운트다운(분, 0 = 없이) + 출연자 이름(지금 명단에서 고른다)
     끝 화면: 오늘의 기록 — 방송 중엔 방송판이 지금 조각으로 그리고, 방송을 끝내는 순간 서버가 한 장 얼린다
   ⚠️ 적는 중인 칸 · 고쳐 놓고 아직 저장 안 한 칸은 서버 값으로 덮지 않는다. */
import { h, sigOf, onEnter, setVal, once, switchEl, blockHead, fill } from './common.js';

const ACC = [['bank', '은행', '예) 국민', 20], ['acc_num', '계좌번호', '예) 123456-78-901234', 40], ['name', '예금주', '예) 홍길동', 20]];

export function mountScreen(el, ctx) {
    /* ── 계좌 ── */
    const accIn = {}, dirty = new Set();
    const accSw = switchEl('방송판에 계좌 띄우기', async on => {
        const res = await ctx.run('show.hud', { key: 'account', on });
        if (res.ok) ctx.toast(on ? '계좌 자리를 켰어요' : '계좌 자리를 껐어요', on ? 'ok' : 'info');
        else accSw.input.checked = !on;
    });
    const accSave = h('button', { type: 'button', class: 'btn sm', onclick: () => once(accSave, saveAccount) }, '계좌 저장');
    const accFields = ACC.map(([k, label, ph, max]) => {
        const i = h('input', { type: 'text', maxlength: String(max), placeholder: ph, autocomplete: 'off', 'data-acc': k });
        i.addEventListener('input', () => { dirty.add(k); paintDirty(); });
        onEnter(i, () => once(accSave, saveAccount));
        accIn[k] = i;
        return h('label', { class: 'ops-field' }, h('span', null, label), i);
    });
    function paintDirty() {
        accSave.classList.toggle('pri', dirty.size > 0);
        accSave.textContent = dirty.size ? '계좌 저장 (고친 것 있음)' : '계좌 저장';
    }
    async function saveAccount() {
        const data = {};
        ACC.forEach(([k]) => { data[k] = accIn[k].value.trim(); });
        const res = await ctx.run('account.set', data);
        if (res.ok) { dirty.clear(); paintDirty(); lastAcc = ''; ctx.toast('🏦 계좌를 저장했어요', 'ok'); ctx.rerender(); }
    }

    /* ── 시작 · 끝 화면 ── */
    const scrState = h('p', { class: 'ops-now' });
    const titleIn = h('input', { type: 'text', maxlength: '40', placeholder: '한 줄 문구 (예: 오늘은 추석 특집!)', autocomplete: 'off', class: 'grow', 'aria-label': '한 줄 문구' });
    const minIn = h('input', { type: 'number', class: 'ops-num w-s', min: '0', max: '180', inputmode: 'numeric', placeholder: '0', 'aria-label': '카운트다운 분' });
    let titleDirty = false;
    titleIn.addEventListener('input', () => { titleDirty = true; });
    const namesBox = h('div', { class: 'ops-chips' });
    const off = new Set();          // 시작 화면에서 뺀 이름(새로 생긴 사람은 기본으로 넣는다)
    const nameBtns = new Map();
    const bStart = h('button', { type: 'button', class: 'btn sm', 'data-mode': 'start', onclick: () => once(bStart, () => setScreen('start')) }, '🎬 시작 전 화면');
    const bEnd = h('button', { type: 'button', class: 'btn sm', 'data-mode': 'end', onclick: () => once(bEnd, () => setScreen('end')) }, '🌙 끝 화면');
    const bOff = h('button', { type: 'button', class: 'btn sm', 'data-mode': 'off', onclick: () => once(bOff, () => setScreen('off')) }, '끄기');
    onEnter(titleIn, () => { titleIn.blur(); });

    async function setScreen(mode) {
        const data = { mode };
        if (mode !== 'off') data.title = titleIn.value.trim();
        if (mode === 'start') {
            const m = String(minIn.value || '').trim();
            if (m && !/^\d{1,3}$/.test(m)) { ctx.toast('카운트다운은 0~180 분 숫자로 적어 주세요', 'err'); minIn.focus(); return; }
            data.minutes = Math.min(180, parseInt(m || '0', 10) || 0);
            data.names = playerNames(ctx.slices).filter(n => !off.has(n));
        }
        const res = await ctx.run('screen.set', data);
        if (res.ok) {
            titleDirty = false;
            ctx.toast(mode === 'start' ? '🎬 시작 전 화면을 띄웠어요' : mode === 'end' ? '🌙 끝 화면을 띄웠어요' : '시작 · 끝 화면을 껐어요', mode === 'off' ? 'info' : 'ok');
        }
    }

    el.classList.add('ops', 'ops-screen');
    el.append(
        h('section', { class: 'ops-blk' }, blockHead('🏦 계좌', '방송판 계좌 자리에 보이는 글'),
            h('div', { class: 'ops-toprow' }, accSw.el),
            h('div', { class: 'ops-grid3' }, accFields),
            h('div', { class: 'ops-row end' }, accSave)),
        h('section', { class: 'ops-blk' }, blockHead('🎬 시작 · 끝 화면', '방송판 전체를 덮어요 — 후원 알림 · 시그니처는 그 위에 그대로 떠요'),
            scrState,
            h('div', { class: 'ops-row wrap' }, titleIn),
            h('div', { class: 'ops-row wrap' }, h('span', { class: 'ops-lbl' }, '카운트다운'), minIn, h('span', null, '분'),
                h('span', { class: 'ops-hint inline' }, '비우거나 0 이면 카운트다운 없이 문구만')),
            h('div', { class: 'ops-lbl-row' }, h('span', { class: 'ops-lbl' }, '시작 화면 출연자'), h('span', { class: 'ops-hint inline' }, '눌러서 빼거나 넣어요')),
            namesBox,
            h('div', { class: 'ops-row wrap' }, bStart, bEnd, bOff)),
    );

    function playerNames(slices) {
        return (((slices.players || {}).list) || []).map(r => r.name).filter(Boolean);
    }

    // 카운트다운 — 시작 화면이 켜져 있을 때만 1초마다 한 줄만 고친다
    let scr = {};
    const tick = setInterval(() => {
        if (!el.isConnected) { clearInterval(tick); return; }
        if (scr.mode === 'start' && scr.start_at && !el.hidden) paintScreenState();
    }, 1000);
    function paintScreenState() {
        const m = scr.mode;
        scrState.className = 'ops-now' + (m === 'start' || m === 'end' ? '' : ' off');
        if (m === 'start') {
            const left = Math.max(0, Math.round(((Number(scr.start_at) || 0) - Date.now()) / 1000));
            fill(scrState, h('b', null, '● 시작 전 화면 켜짐'),
                scr.start_at ? (left ? ` — 카운트다운 ${Math.floor(left / 60)}:${String(left % 60).padStart(2, '0')} 남음` : ' — 카운트다운 끝') : ' — 카운트다운 없음',
                scr.title ? h('span', { class: 'ops-dim' }, ' · ' + scr.title) : null);
        } else if (m === 'end') {
            fill(scrState, h('b', null, '● 끝 화면 켜짐'), scr.title ? h('span', { class: 'ops-dim' }, ' · ' + scr.title) : null);
        } else {
            scrState.replaceChildren('꺼져 있어요 — 방송판이 평소대로 보여요');
        }
        [bStart, bEnd, bOff].forEach(b => b.classList.toggle('on', b.dataset.mode === (m === 'start' || m === 'end' ? m : 'off')));
    }

    let lastAcc = '', lastScr = '', lastNames = '';
    function render(slices) {
        const a = slices.account || {};
        accSw.set(!!((slices.show || {}).hud || {}).account);
        const asig = sigOf(a.bank, a.acc_num, a.name);
        if (asig !== lastAcc) {
            lastAcc = asig;
            ACC.forEach(([k]) => {
                if (dirty.has(k) && accIn[k].value.trim() === String(a[k] || '')) dirty.delete(k);   // 서버 값이 따라왔다
                if (!dirty.has(k)) setVal(accIn[k], a[k] || '');
            });
            paintDirty();
        }

        scr = slices.screen || {};
        const ssig = sigOf(scr.mode, scr.title, scr.start_at, scr.names);
        if (ssig !== lastScr) {
            lastScr = ssig;
            if (!titleDirty) setVal(titleIn, scr.title || '');
            paintScreenState();
        }

        const names = playerNames(slices);
        const nsig = sigOf(names, [...off]);
        if (nsig !== lastNames) {
            lastNames = nsig;
            for (const n of [...off]) if (!names.includes(n)) off.delete(n);
            nameBtns.clear();
            namesBox.replaceChildren(...(names.length ? names.map(n => {
                const on = !off.has(n);
                const b = h('button', { type: 'button', class: 'ops-chip' + (on ? ' on' : ''), 'aria-pressed': String(on),
                    onclick: () => { off.has(n) ? off.delete(n) : off.add(n); lastNames = ''; ctx.rerender(); } }, h('i', { 'aria-hidden': 'true' }), n);
                nameBtns.set(n, b);
                return b;
            }) : [h('span', { class: 'ops-hint inline' }, '명단이 비어 있어요 — 이름 없이 문구만 떠요')]));
        }
    }
    return { render };
}
