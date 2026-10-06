/* 🎚️ 편집기 설정 칸 — 옛 admin.html 편집기의 '💾 세이브 슬롯' · '🎬 시그니처 리액션 위젯' · '📊 오늘의 시그니처' · '🏅 후원 순위' 칸을 옮겼다.
   서버는 settings2.py — 숫자 · 범위 · 기본값은 옛 막대(min · max · step)와 같다.
     💾 세이브 슬롯   preset.save {name} · preset.apply {id} · preset.save {id}(덮어쓰기) · preset.rename · preset.move · preset.delete
                     (조종실 무대 탭의 '순서표' 와 같은 목록이다 — 거기서는 [다음 ▶] 으로 넘긴다)
     🎬 시그니처      sigview.set {big_scale · small_scale · shrink_delay · min_x · min_y · title_size · title_duration · title_suffix}
                     'OO업' 켜고 끄기는 알림 스위치 show.alert {key:'reaction_title'}(옛 reaction_title_enabled 와 같은 스위치)
     📊 목록 개수     look.limits {sig_tally_limit 3~12 · donor_rank_limit 3~10} · 보이기는 고정 자리 show.hud {sig_tally | donor_rank}
   ⚠️ 막대는 움직이는 동안 0.12초 모았다가 한 번 보낸다(옛 pushReac). 적는 중인 칸은 서버 값으로 덮지 않는다.
   ⚠️ [미리보기] 는 이 화면의 방송판에서만 돈다 — 서버 · 대기줄 · OBS 는 안 건드린다(옛 것은 진짜 방송판에 테스트 시그니처를 틀었다).
   ⚠️ 이름 같은 바깥 글자는 textContent 로만 넣는다. prompt · confirm 은 안 쓴다(두 번 누르기 · 칸 안에서 고치기). */
const E = window.__lmEditor;
const lm = E && E.S && E.S.lm;

const STAGE_NAME = { match: '대결', pinball: '핀볼', dicegame: '주사위', siggame: '시그뒤집기', roulette: '룰렛', slot: '슬롯',
    home_race: '퇴근빵', hell: '지옥탈출', quiz: '퀴즈' };
// 슬롯 줄 요약에 보일 고정 자리(옛 PS_SW 와 같은 다섯)
const SUM_HUD = [['sig_tally', '시그 집계'], ['donor_rank', '후원 순위'], ['best', '한 방 최고'], ['notice', '공지'], ['fundjar', '모금함']];
const NAME_MAX = 30;
const ARM_MS = 3000;
const SEND_MS = 120;

function h(tag, attrs, ...kids) {
    const el = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs || {})) {
        if (v == null || v === false) continue;
        if (k === 'class') el.className = v;
        else if (k.startsWith('on') && typeof v === 'function') el.addEventListener(k.slice(2), v);
        else el.setAttribute(k, v === true ? '' : String(v));
    }
    kids.flat().forEach(c => { if (c != null && c !== false) el.append(c instanceof Node ? c : document.createTextNode(String(c))); });
    return el;
}
function toast(msg, bad) {
    const t = document.getElementById('toast');
    if (!t) return;
    t.textContent = msg;
    t.className = 'toast' + (bad ? ' bad' : '');
    t.hidden = false;
    clearTimeout(toast.tm);
    toast.tm = setTimeout(() => { t.hidden = true; }, bad ? 4000 : 2200);
}
async function run(type, data) {
    let r;
    try { r = await lm.cmd(type, data || {}); } catch (e) { r = { ok: false, error: '보내지 못했어요 — 다시 눌러 주세요' }; }
    if (!r || !r.ok) toast((r && r.error) || '실패했어요', true);
    return r || { ok: false };
}
const typing = el => document.activeElement === el;

/* ══════════ 💾 세이브 슬롯 ══════════ */
function mountPresets() {
    const listBox = h('div', { class: 'ps-list', id: 'ps-list' });
    const nameIn = h('input', { type: 'text', class: 'txt', maxlength: String(NAME_MAX), placeholder: '슬롯 이름 (예: 룰렛 타임, 지옥탈출)', 'aria-label': '새 슬롯 이름' });
    const saveBtn = h('button', { class: 'btn pri wide', type: 'button', id: 'ps-save-new' }, '＋ 지금 상태를 새 슬롯으로 저장');
    const card = h('section', { class: 'card ed2', id: 'ed2-presets' },
        h('h2', null, '💾 세이브 슬롯'),
        listBox,
        h('div', { class: 'ed2-row' }, nameIn),
        saveBtn,
        h('p', { class: 'muted small ed2-note' }, '슬롯에는 ', h('b', null, '위젯 자리 · 크기 + 켜고 끈 위젯 + 떠 있는 게임판'),
            '이 담겨요. 이름을 누르면 그 상태로 바로 바뀌어요(조종실 무대 탭의 순서표에서도 누를 수 있어요). ',
            '룰렛 칸 · 핀볼 명단 같은 게임 속 내용과 점수 · 테마는 안 바뀝니다. 지옥탈출 · 퇴근빵 · 대결의 진행은 그대로예요.'));

    let renaming = '', delArmed = { id: '', t: 0 }, overArmed = { id: '', t: 0 }, lastSig = '';
    const list = () => ((lm.get('presets') || {}).list || []).filter(p => p && p.id);
    const curAt = () => { const v = Number((lm.get('show') || {}).cue_at); return isFinite(v) ? v : -1; };
    const busy = new Set();

    async function once(key, fn) {
        if (busy.has(key)) return;
        busy.add(key);
        try { await fn(); } finally { busy.delete(key); }
    }
    function arm(st, id) {
        clearTimeout(st.t);
        st.id = id;
        st.t = setTimeout(() => { st.id = ''; paint(true); }, ARM_MS);
    }
    function disarm() { clearTimeout(delArmed.t); clearTimeout(overArmed.t); delArmed.id = overArmed.id = ''; }

    async function saveNew() {
        if (E.flushAll) E.flushAll();                  // 아직 안 보낸 자리부터(명령은 보낸 순서대로 처리된다)
        const r = await run('preset.save', { name: nameIn.value.trim().slice(0, NAME_MAX) });
        if (r.ok) { nameIn.value = ''; toast('💾 "' + (r.name || '슬롯') + '" 저장했어요'); }
    }
    saveBtn.addEventListener('click', () => once('new', saveNew));
    nameIn.addEventListener('keydown', e => { if (e.key === 'Enter' && !e.isComposing) once('new', saveNew); });

    async function apply(p) {
        if (E.flushAll) E.flushAll();
        const r = await run('preset.apply', { id: p.id });
        if (r.ok) toast('📺 "' + (p.name || '슬롯') + '" 으로 바꿨어요');
    }
    async function overwrite(p) {
        if (overArmed.id !== p.id) { disarm(); arm(overArmed, p.id); paint(true); return; }
        disarm();
        if (E.flushAll) E.flushAll();
        const r = await run('preset.save', { id: p.id });
        paint(true);
        if (r.ok) toast('💾 "' + (p.name || '슬롯') + '" 을 지금 상태로 덮어썼어요');
    }
    async function del(p) {
        if (delArmed.id !== p.id) { disarm(); arm(delArmed, p.id); paint(true); return; }
        disarm();
        const r = await run('preset.delete', { id: p.id });
        paint(true);
        if (r.ok) toast('🗑️ 지웠어요');
    }
    async function rename(p, input) {
        const name = input.value.trim();
        if (!name) { toast('이름을 적어 주세요', true); return; }
        const r = await run('preset.rename', { id: p.id, name });
        if (r.ok) { renaming = ''; paint(true); }
    }
    function summary(p) {
        const st = p.stage !== undefined ? p.stage : p.board;
        const on = SUM_HUD.filter(([k]) => p.hud && p.hud[k]).map(x => x[1]);
        return (STAGE_NAME[st] || '게임판 없음') + (on.length ? ' · ' + on.join(' · ') : '') + (p.old ? ' · 옛 슬롯(자리 없음)' : '');
    }

    function paint(force) {
        const ps = list(), at = curAt();
        const sig = JSON.stringify([ps.map(p => [p.id, p.name, p.stage, p.board, p.hud, p.old]), at, renaming, delArmed.id, overArmed.id]);
        if (!force && sig === lastSig) return;
        if (renaming && listBox.contains(document.activeElement) && document.activeElement.tagName === 'INPUT' && !force) return;
        lastSig = sig;
        if (!ps.length) {
            listBox.replaceChildren(h('div', { class: 'ps-empty muted small' }, '아직 저장한 슬롯이 없어요. 원하는 대로 켜고 옮긴 뒤 아래 버튼을 누르세요.'));
            return;
        }
        listBox.replaceChildren(...ps.map((p, i) => {
            if (renaming === p.id) {
                const inp = h('input', { type: 'text', class: 'txt', maxlength: String(NAME_MAX), value: p.name || '', 'aria-label': '새 이름' });
                const ok = h('button', { class: 'btn sm pri', type: 'button', onclick: () => once('rn', () => rename(p, inp)) }, '저장');
                const no = h('button', { class: 'btn sm', type: 'button', onclick: () => { renaming = ''; paint(true); } }, '그만');
                inp.addEventListener('keydown', e => {
                    if (e.key === 'Enter' && !e.isComposing) once('rn', () => rename(p, inp));
                    if (e.key === 'Escape') { renaming = ''; paint(true); }
                });
                setTimeout(() => { inp.focus(); inp.select(); }, 0);
                return h('div', { class: 'ps-row renaming', 'data-id': p.id }, inp, ok, no);
            }
            const main = h('button', { class: 'ps-main', type: 'button', title: '이 상태로 바꾸기', onclick: () => once('ap' + p.id, () => apply(p)) },
                h('span', { class: 'ps-name' }, (i + 1) + '. ' + (p.name || '')), h('span', { class: 'ps-sum' }, summary(p)));
            const up = h('button', { class: 'ps-btn', type: 'button', title: '위로', 'aria-label': '위로', disabled: i === 0,
                onclick: () => once('mv', () => run('preset.move', { id: p.id, dir: -1 })) }, '▲');
            const ov = h('button', { class: 'ps-btn' + (overArmed.id === p.id ? ' sure' : ''), type: 'button',
                title: overArmed.id === p.id ? '한 번 더 누르면 지금 상태로 덮어써요' : '지금 상태로 덮어쓰기',
                onclick: () => once('ov', () => overwrite(p)) }, overArmed.id === p.id ? '한 번 더' : '💾');
            const rn = h('button', { class: 'ps-btn', type: 'button', title: '이름 바꾸기', 'aria-label': '이름 바꾸기',
                onclick: () => { disarm(); renaming = p.id; paint(true); } }, '✏️');
            const dl = h('button', { class: 'ps-btn del' + (delArmed.id === p.id ? ' sure' : ''), type: 'button',
                title: delArmed.id === p.id ? '한 번 더 누르면 지워요(되돌릴 수 없어요)' : '지우기',
                onclick: () => once('dl', () => del(p)) }, delArmed.id === p.id ? '지울까요?' : '🗑');
            return h('div', { class: 'ps-row' + (i === at ? ' cur' : ''), 'data-id': p.id }, main, up, ov, rn, dl);
        }));
    }
    lm.on('presets', () => paint(false));
    lm.on('show', () => paint(false));
    return { card, paint };
}

/* ══════════ 막대 하나 ══════════ */
function slider(label, min, max, step, fmt, onInput) {
    const input = h('input', { type: 'range', min: String(min), max: String(max), step: String(step) });
    const val = h('b', null, '');
    const row = h('label', { class: 'field ed2-slider' }, h('span', null, label, ' ', val), input);
    input.addEventListener('input', () => { val.textContent = fmt(Number(input.value)); onInput(Number(input.value)); });
    input.addEventListener('pointerup', () => setTimeout(() => input.blur(), 0));
    return { row, input, set(v) { if (!typing(input)) input.value = String(v); val.textContent = fmt(Number(typing(input) ? input.value : v)); } };
}
/* 모았다가 한 번 — {칸: 값} 을 0.12초 뒤 한 명령으로 */
function batcher(type) {
    let pend = {}, t = 0;
    return (k, v) => {
        pend[k] = v;
        clearTimeout(t);
        t = setTimeout(() => { const d = pend; pend = {}; run(type, d); }, SEND_MS);
    };
}

/* ══════════ 🎬 시그니처 리액션 ══════════ */
function mountSigView() {
    const send = batcher('sigview.set');
    const sec = s => (s / 1000).toFixed(1) + '초';
    const x2 = v => Number(v).toFixed(2);
    const big = slider('큰 크기', 0.5, 2.0, 0.05, x2, v => send('big_scale', v));
    const small = slider('작은 크기', 0.3, 1.5, 0.05, x2, v => send('small_scale', v));
    const delay = slider('줄어드는 시간', 500, 6000, 100, sec, v => send('shrink_delay', v));
    const num = (key, lbl) => {
        const input = h('input', { type: 'number', step: '1', inputmode: 'numeric' });
        input.addEventListener('change', () => {
            const v = parseFloat(String(input.value).replace(/,/g, ''));
            if (isFinite(v)) run('sigview.set', { [key]: v });
            else draw();
        });
        input.addEventListener('keydown', e => { if (e.key === 'Enter') input.blur(); });
        return { input, row: h('label', { class: 'field' }, h('span', null, lbl), input) };
    };
    const mx = num('min_x', '위치 X (작아졌을 때)'), my = num('min_y', '위치 Y (작아졌을 때)');
    const titleOn = h('input', { type: 'checkbox' });
    titleOn.addEventListener('change', () => run('show.alert', { key: 'reaction_title', on: titleOn.checked }));
    const suffix = h('input', { type: 'text', class: 'txt', maxlength: '6', 'aria-label': '이름 뒤에 붙는 말' });
    suffix.addEventListener('input', () => send('title_suffix', suffix.value));
    const tsize = slider('글자 크기', 60, 300, 5, v => v + 'px', v => send('title_size', v));
    const tdur = slider('노출 시간', 1000, 8000, 100, sec, v => send('title_duration', v));
    const test = h('button', { class: 'btn pri wide', type: 'button' }, '▶ 이 화면에서 미리보기');
    test.addEventListener('click', preview);

    const card = h('details', { class: 'card ed2 fold', id: 'ed2-sigview' },
        h('summary', null, h('h2', null, '🎬 시그니처 리액션')),
        big.row, small.row, delay.row,
        h('div', { class: 'xy' }, mx.row, my.row),
        h('div', { class: 'ed2-sub' },
            h('label', { class: 'chk' }, titleOn, ' 🔥 중앙에 후원자 이름 크게 표시(10만 원 이상)'),
            h('label', { class: 'field' }, h('span', null, '이름 뒤에 붙는 말 (예: 업 → "홍길동업")'), suffix),
            tsize.row, tdur.row),
        test,
        h('p', { class: 'muted small ed2-note' }, '⚡ 값을 바꾸면 방송판에 바로 적용돼요. 미리보기는 이 화면에서만 — 방송(OBS)에는 안 나가요.'));

    function draw() {
        const v = lm.get('sigview') || {};
        big.set(v.big_scale ?? 1); small.set(v.small_scale ?? 0.6); delay.set(v.shrink_delay ?? 2500);
        tsize.set(v.title_size ?? 150); tdur.set(v.title_duration ?? 3500);
        if (!typing(mx.input)) mx.input.value = String(v.min_x ?? 180);
        if (!typing(my.input)) my.input.value = String(v.min_y ?? 600);
        if (!typing(suffix)) suffix.value = typeof v.title_suffix === 'string' ? v.title_suffix : '업';
        const al = (lm.get('show') || {}).alerts || {};
        titleOn.checked = al.reaction_title !== false;
    }
    let sigImg = null;
    async function preview() {
        const w = E.frameWin && E.frameWin();
        const pv = w && w.__lmOverlay && w.__lmOverlay.stage && w.__lmOverlay.stage.use('sigPreview');
        if (!pv) { toast('방송판 미리보기가 아직 안 떴어요 — 잠시 뒤 다시 눌러 주세요', true); return; }
        if (sigImg === null) {                         // 등록된 시그니처 사진 하나(없으면 제목 판)
            sigImg = '';
            try {
                const r = await fetch('/api/signatures', { credentials: 'same-origin', cache: 'no-store' });
                const d = await r.json();
                const row = (d.signatures || []).find(x => x && x.image_url);
                if (row) sigImg = { image_url: row.image_url, title: row.title || '' };
            } catch (e) { /* 사진 없이 */ }
        }
        if (!pv.play(Object.assign({}, sigImg || {}))) toast('지금 진짜 시그니처가 나가는 중이에요 — 끝난 뒤 눌러 주세요', true);
    }
    lm.on('sigview', draw);
    lm.on('show', draw);
    return { card, draw };
}

/* ══════════ 📊 목록 개수 ══════════ */
function mountLists() {
    const send = batcher('look.limits');
    const tally = slider('오늘의 시그니처(시그 집계) 표시 개수', 3, 12, 1, v => v + '개', v => send('sig_tally_limit', v));
    const donor = slider('후원 순위 표시 인원', 3, 10, 1, v => v + '명', v => send('donor_rank_limit', v));
    const hudBox = (key, lbl) => {
        const c = h('input', { type: 'checkbox' });
        c.addEventListener('change', () => run('show.hud', { key, on: c.checked }));
        return { c, row: h('label', { class: 'chk' }, c, ' ' + lbl) };
    };
    const tOn = hudBox('sig_tally', '📊 시그 집계 — 방송 화면에 표시'), dOn = hudBox('donor_rank', '🏅 후원 순위 — 방송 화면에 표시');
    const lookBox = (key, lbl) => {
        const c = h('input', { type: 'checkbox' });
        c.addEventListener('change', () => run('look.donor', { [key]: c.checked }));
        return { c, row: h('label', { class: 'chk' }, c, ' ' + lbl) };
    };
    const amt = lookBox('amount', '💰 후원 순위에 금액도 보여주기'), anon = lookBox('anon', '🕶️ 익명 후원도 순위에 넣기');
    const card = h('details', { class: 'card ed2 fold', id: 'ed2-lists' },
        h('summary', null, h('h2', null, '📊 목록 개수')),
        tOn.row, tally.row, dOn.row, donor.row, amt.row, anon.row,
        h('p', { class: 'muted small ed2-note' }, '이번 방송에 들어온 것만 셉니다. 방송 시작 · 끝 때 저절로 비워져요. 켜고 끄기는 조종실 무대 탭의 고정 자리와 같은 스위치예요.'));
    function draw() {
        const look = lm.get('look') || {};
        tally.set(look.sig_tally_limit ?? 6);
        donor.set(look.donor_rank_limit ?? 5);
        amt.c.checked = look.donor_amount !== false;
        anon.c.checked = look.donor_anon === true;
        const hud = (lm.get('show') || {}).hud || {};
        tOn.c.checked = !!hud.sig_tally;
        dOn.c.checked = !!hud.donor_rank;
    }
    lm.on('look', draw);
    lm.on('show', draw);
    return { card, draw };
}

function boot() {
    if (!lm) { console.error('[편집기 설정] 편집기 연결을 못 찾았습니다'); return; }
    const side = document.querySelector('.side');
    const props = document.getElementById('props');
    const listCard = document.querySelector('.list-card');
    if (!side || !props || !listCard) return;
    const ps = mountPresets(), sv = mountSigView(), ls = mountLists();
    side.insertBefore(ps.card, props);                     // 옛 편집기처럼 세이브 슬롯이 맨 위
    listCard.after(sv.card, ls.card);
    ps.paint(true); sv.draw(); ls.draw();
    try { if (localStorage.getItem('lm2ed:open-sigview') === '1') sv.card.open = true; } catch (e) {}
    try { if (localStorage.getItem('lm2ed:open-lists') === '1') ls.card.open = true; } catch (e) {}
    sv.card.addEventListener('toggle', () => { try { localStorage.setItem('lm2ed:open-sigview', sv.card.open ? '1' : '0'); } catch (e) {} });
    ls.card.addEventListener('toggle', () => { try { localStorage.setItem('lm2ed:open-lists', ls.card.open ? '1' : '0'); } catch (e) {} });
    window.__lmEditorSettings = { presets: ps, sigview: sv, lists: ls };      // 점검용
}
boot();
