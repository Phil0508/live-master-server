/* 🛫 방송 전 점검 · 🚨 방송 중 경보 · 머리줄 상태 점 — 옛 조종실 pf* (10-06, features/preflight.py) 를 옮겼다.
   대표님 10-06 "사고 막기 — 소리는 안 나도 돼" → ⚠️ 소리는 절대 내지 않는다. 눈으로만 알린다.

   서버 GET /api/preflight[?deep=1] — 읽기만 한다(로그인 쿠키).
     · 점검표가 보일 때: 5초마다 · 시그니처 목록까지(deep)
     · 그 밖에: 10초마다 · 방송 화면 · 후원 받기 · 못 보낸 후원만
   머리줄 점 두 개 — [방송 화면] [후원 받기] 초록(좋음) · 노랑(살펴볼 것) · 빨강(멈춤) · 회색(모름/없음). 누르면 까닭을 알림으로.
   경보(빨간 띠) — 방송 중에만. 방송 화면이 15초 넘게 없거나, 후원 받기가 30초 넘게 끊김/붙는 중이거나,
     못 보낸 후원이 30초 넘게 남아 있으면 머리줄 밑에 붙는다. 다시 좋아지면 저절로 내려간다.
     [알겠어요] 는 '그 건' 만 내린다 — 다시 붙었다 또 끊기면 새로 뜬다.
   점검표 — 방송 전 화면(이름 적기 옆)에 저절로 보이고, 방송 중에는 [점검] 탭에서 본다(mountChecklist).
   ⚠️ 가려진 창(OBS 뒤)에서는 브라우저가 타이머를 늦춘다 — 창이 다시 보이면 바로 한 번 묻는다. */
import { h, won } from './util.js';

const GRACE = { ov: 15000, li: 30000, sp: 30000 };
const GAP = 10000, GAP_DEEP = 5000;
const STALE_MS = 35000;          // 이만큼 답을 못 받으면 점은 '모름'(회색) — 연결 끊김은 main.js 의 띠가 알린다
const OBS_KEY = 'lm2_pf_obs_';   // + 오늘 날짜 — OBS 리플레이 버퍼 확인(오늘만 기억)

const st = {
    last: null, lastAt: 0, sig: null, err: '', busy: false, polledAt: 0,
    enabled: false, live: false,
    down: { ov: 0, li: 0, sp: 0 }, ack: { ov: -1, li: -1, sp: -1 },
    lists: new Set(),            // 점검표들 — 하나라도 보이면 deep 으로 묻는다
};

/* ── 작은 도구 ── */
export function ago(sec) {
    if (sec == null) return '';
    sec = Math.max(0, Math.round(sec));
    if (sec < 60) return sec + '초';
    if (sec < 3600) return Math.floor(sec / 60) + '분';
    return Math.floor(sec / 3600) + '시간 ' + Math.floor((sec % 3600) / 60) + '분';
}

function obsKey() {
    const t = new Date();
    return OBS_KEY + t.getFullYear() + '-' + (t.getMonth() + 1) + '-' + t.getDate();
}
function obsChecked() {
    try { return localStorage.getItem(obsKey()) === '1'; } catch (e) { return false; }
}
function obsSet(on) {
    try { localStorage.setItem(obsKey(), on ? '1' : '0'); } catch (e) { /* 개인 창 등 — 기억 못 해도 된다 */ }
}

function stale() {
    return !st.last || Date.now() - st.lastAt > STALE_MS;
}

/** 지금 상태의 단계 — ok · warn · bad · none(없음/모름) */
function levels() {
    const d = st.last;
    if (!d || stale()) return { ov: 'none', li: 'none', sp: 'none', known: false };
    const sc = d.screens || {}, li = d.listener || {};
    const ov = sc.overlay > 0 ? 'ok' : (st.live ? 'bad' : 'warn');
    const lv = li.level === 'ok' ? 'ok' : li.level === 'connecting' ? 'warn' : li.level === 'none' ? 'none' : 'bad';
    const sp = d.spool == null ? 'none' : d.spool > 0 ? 'warn' : 'ok';
    return { ov, li: lv, sp, known: true };
}

/* ── 묻기 ── */
function anyListVisible() {
    if (document.visibilityState === 'hidden') return false;
    for (const l of st.lists) if (l.visible()) return true;
    return false;
}

async function poll(force) {
    if (!st.enabled) return;
    const deep = anyListVisible();
    const gap = deep ? GAP_DEEP : GAP;
    if (st.busy || (!force && Date.now() - st.polledAt < gap - 300)) return;
    st.busy = true;
    st.polledAt = Date.now();
    try {
        const r = await fetch('/api/preflight' + (deep ? '?deep=1' : ''), { cache: 'no-store', credentials: 'same-origin' });
        if (r.ok) {
            const d = await r.json();
            if (d && d.status === 'success') {
                st.last = d;
                st.lastAt = Date.now();
                st.err = '';
                if (d.sig) st.sig = d.sig;
            }
        } else {
            st.err = r.status === 401 ? '로그인이 풀렸어요' : '서버가 ' + r.status + ' 로 답했어요';
        }
    } catch (e) {
        st.err = '서버에 닿지 않아요';
    }
    st.busy = false;
    paint();
}

/* ── 그리기 — 점 · 경보 · 점검표(보이는 것만) ── */
let chips = null, alarm = null, ctxRef = null;

function paint() {
    paintChips();
    paintAlarm();
    for (const l of st.lists) if (l.visible()) l.update();
}

/* 점 — 넓은 화면은 긴 글자, 폰은 짧은 글자(.ts — '화면' · '후원' + 표시). 색이 단계를, 누르면 까닭을 알려 준다 */
function chipSet(el, lv, text, short) {
    if (el.dataset.lv !== lv) el.dataset.lv = lv;
    const t = el.querySelector('.t'), ts = el.querySelector('.ts');
    if (t.textContent !== text) t.textContent = text;
    if (ts.textContent !== short) ts.textContent = short;
    const label = text + ' — 누르면 자세히';
    if (el.getAttribute('aria-label') !== label) el.setAttribute('aria-label', label);
}

function mark(lv, known) {
    return !known ? ' ?' : lv === 'ok' ? '' : lv === 'none' ? ' —' : ' !';
}

function paintChips() {
    if (!chips) return;
    const L = levels(), d = st.last || {}, sc = d.screens || {};
    chipSet(chips.ov, L.ov, !L.known ? '방송 화면 ?' : sc.overlay > 0 ? (sc.overlay > 1 ? `방송 화면 ${sc.overlay}` : '방송 화면') : '방송 화면 없음',
        '화면' + mark(L.ov, L.known));
    chipSet(chips.li, L.li, !L.known ? '후원 받기 ?' : L.li === 'ok' ? '후원 받기' : L.li === 'warn' ? '후원 연결 중' : L.li === 'none' ? '후원 받기 —' : '후원 받기 멈춤',
        '후원' + mark(L.li, L.known));
}

function explain(k) {
    const toast = ctxRef.toast;
    const d = st.last;
    if (!d || stale()) {
        toast(st.err ? '상태를 못 받았어요 — ' + st.err : '상태를 확인하는 중이에요', 'info');
        poll(true);
        return;
    }
    const sc = d.screens || {}, li = d.listener || {};
    if (k === 'ov') {
        if (sc.overlay > 0) toast(`📺 방송 화면 붙음 — ${sc.overlay}개` + (sc.monitor ? ` · 미리보기 ${sc.monitor}개(방송엔 안 나감)` : ''), 'ok');
        else toast('📺 방송 화면(OBS)이 안 붙어 있어요 — OBS 에서 방송판 소스를 골라 [새로고침] 해 주세요' + (sc.monitor ? ` (미리보기 ${sc.monitor}개는 방송에 안 나가요)` : ''), st.live ? 'err' : 'info');
        return;
    }
    if (li.level === 'ok') {
        toast('🎧 후원 받기 연결됨' + (li.connected_sec != null ? ' · ' + ago(li.connected_sec) + '째' : '') +
            (li.last_donation_sec != null ? ' · 마지막 후원 ' + ago(li.last_donation_sec) + ' 전' : ''), 'ok');
    } else if (li.level === 'none') {
        toast('🎧 이 서버엔 후원 받기 프로그램(리스너)이 없어요' + (li.note ? ' — ' + li.note : ''), 'info');
    } else {
        toast('🎧 후원 받기 ' + (li.level === 'connecting' ? '붙는 중' : '멈춤') + (li.note ? ' — ' + li.note : ''), li.level === 'connecting' ? 'info' : 'err');
    }
}

/* 경보 — 처음 나빠진 때를 기억해 두고, 잠깐(다시 붙기 · 새로고침)은 넘어간다 */
function track(k, bad, now) {
    if (!st.live || !bad) { st.down[k] = 0; return false; }
    if (!st.down[k]) st.down[k] = st.lastAt || now;
    return now - st.down[k] >= GRACE[k] && st.ack[k] !== st.down[k];
}

const ALARM_TEXT = {
    ov: {
        title: '📺 방송 화면(OBS)이 서버와 끊겼어요',
        sub: () => '점수 · 후원 · 시그니처가 방송에 안 나갈 수 있어요. OBS 에서 방송판 소스를 고르고 [새로고침] 을 눌러 주세요.',
    },
    li: {
        title: () => (levels().li === 'warn' ? '🎧 후원 받기가 다시 붙는 중이에요' : '🎧 후원 받기가 멈췄어요'),
        sub: () => {
            const li = (st.last || {}).listener || {};
            return '투네이션 후원이 조종실에 안 들어올 수 있어요(리스너가 스스로 다시 붙는 중). 투네이션 알림창에는 떴는데 대기함에 없으면 후원 콘솔로 직접 넣어 주세요.' +
                (li.note ? ' — ' + li.note : '');
        },
    },
    sp: {
        title: () => `📮 서버로 못 보낸 후원 ${(st.last || {}).spool || 0}건이 기다리는 중`,
        sub: () => '서버가 받으면 저절로 들어갑니다(10초마다 다시 보냄). 오래 남아 있으면 후원 콘솔로 확인해 주세요.',
    },
};

function paintAlarm() {
    if (!alarm) return;
    const now = Date.now();
    const known = !stale();
    const L = levels();
    const show = {
        ov: track('ov', known && L.ov === 'bad', now),
        li: track('li', known && (L.li === 'bad' || L.li === 'warn'), now),
        sp: track('sp', known && L.sp === 'warn', now),
    };
    let any = false, changed = false;
    for (const k of ['ov', 'li', 'sp']) {
        const row = alarm.rows[k];
        if (row.el.hidden === show[k]) { row.el.hidden = !show[k]; changed = true; }
        if (!show[k]) continue;
        any = true;
        const tx = ALARM_TEXT[k];
        const title = typeof tx.title === 'function' ? tx.title() : tx.title;
        const since = ' · ' + ago((now - st.down[k]) / 1000) + '째';
        if (row.title.textContent !== title) row.title.textContent = title;
        if (row.since.textContent !== since) row.since.textContent = since;
        const sub = tx.sub();
        if (row.sub.textContent !== sub) row.sub.textContent = sub;
    }
    if (alarm.el.hidden === any) { alarm.el.hidden = !any; changed = true; }
    // 띠가 생기거나 없어지면 머리줄 높이가 바뀐다 → main.js 가 --hdr-h 를 다시 잰다(오른쪽 칸이 머리줄 밑에 붙게)
    if (changed && ctxRef && ctxRef.rerender) ctxRef.rerender();
}

function dismiss(k) {
    st.ack[k] = st.down[k];
    paintAlarm();
}

/* ── 머리줄에 붙이기 ──
   before: 점 두 개를 그 앞에 끼울 머리줄 칸(오른쪽 묶음) — 폰에서는 점이 로고 줄에 같이 선다 · hdrRoot: 머리줄(경보 띠도 여기 맨 아래) */
export function mountAlarm(before, hdrRoot, ctx) {
    ctxRef = ctx;
    const mk = (k, label, short, title) => {
        const b = h('button', { type: 'button', class: 'pill pf-chip', 'data-lv': 'none', title, onclick: () => explain(k) },
            h('i', { 'aria-hidden': 'true' }), h('span', { class: 't', 'aria-hidden': 'true' }, label), h('span', { class: 'ts', 'aria-hidden': 'true' }, short));
        return b;
    };
    chips = {
        ov: mk('ov', '방송 화면 ?', '화면 ?', '방송 화면(OBS)이 서버에 붙어 있나 — 누르면 자세히'),
        li: mk('li', '후원 받기 ?', '후원 ?', '투네이션 후원을 받아 오는 프로그램이 살아 있나 — 누르면 자세히'),
    };
    chips.wrap = h('span', { class: 'pf-chips', hidden: true }, chips.ov, chips.li);
    hdrRoot.insertBefore(chips.wrap, before);

    const row = k => {
        const r = { title: h('b'), since: h('span', { class: 'pf-since', 'aria-hidden': 'true' }), sub: h('small') };
        // 폰에서는 설명을 한 줄로 접어 둔다 — 글자를 누르면 펼친다(머리줄과 같이 위에 붙어 있어 화면을 덜 가리게)
        const txt = h('div', { class: 'pf-txt', onclick: () => r.el.classList.toggle('open') }, h('div', { class: 'pf-head' }, r.title, r.since), r.sub);
        r.el = h('div', { class: 'pf-row', 'data-k': k, hidden: true }, txt,
            h('button', { type: 'button', class: 'btn sm pf-ack', onclick: () => dismiss(k) }, '알겠어요'));
        return r;
    };
    alarm = { rows: { ov: row('ov'), li: row('li'), sp: row('sp') } };
    alarm.el = h('div', { class: 'pf-alarm', role: 'alert', hidden: true }, alarm.rows.ov.el, alarm.rows.li.el, alarm.rows.sp.el);
    hdrRoot.append(alarm.el);

    // 방송 전 화면(이름 적기) 옆에 점검표 — setup.js 는 건드리지 않고, 그 화면 칸(#v-setup)에 카드 하나를 더 붙인다
    const preHost = h('section', { class: 'card pf-pre', 'aria-label': '방송 전 점검' });
    const pre = mountChecklist(preHost, ctx, { pre: true });

    setInterval(() => { if (st.enabled) { poll(false); paintAlarm(); } }, 1000);
    document.addEventListener('visibilitychange', () => { if (document.visibilityState === 'visible') poll(true); });

    return {
        render(slices, status, view) {
            const on = view === 'setup' || view === 'live';
            const wasOn = st.enabled;
            st.enabled = on;
            st.live = !!(slices.session && slices.session.live);
            chips.wrap.hidden = !on;
            if (!on) { if (!alarm.el.hidden) { alarm.el.hidden = true; } return; }
            if (view === 'setup') {
                const host = document.getElementById('v-setup');
                if (host && preHost.parentNode !== host) host.append(preHost);
            }
            if (!wasOn) poll(true);
            else paint();
            pre.render();
        },
    };
}

/* ── 점검표 — 줄 여섯: 방송 화면 · 후원 받기 · 못 보낸 후원 · 시그니처 목록(deep) · 저장소 · OBS 리플레이 버퍼 ──
   줄은 한 번 만들고 글자 · 색만 바꾼다(체크 칸을 누르던 손이 날아가지 않게). */
export function mountChecklist(el, ctx, opts = {}) {
    const sum = h('span', { class: 'pf-sum' }, '확인하는 중…');
    const again = h('button', { type: 'button', class: 'btn sm', onclick: () => { poll(true); ctx.toast('다시 확인하는 중이에요', 'info', 1500); } }, '다시 확인');
    const ul = h('ul', { class: 'pf-items' });
    el.classList.add('pf-card');
    // ⚠️ append(null) 은 'null' 글자를 넣는다 — 빈 칸은 걸러서 넘긴다
    el.append(...[
        h('div', { class: 'pf-top' },
            h('h2', null, '🛫 방송 전 점검'), sum, again),
        opts.pre ? h('p', { class: 'muted small pf-lead' }, '방송 시작 전에 한 번 훑어 보세요. 5초마다 저절로 다시 확인합니다.') : null,
        ul].filter(Boolean));

    const rows = {};
    const mkRow = k => {
        const r = { ic: h('span', { class: 'pf-ic', 'aria-hidden': 'true' }), title: h('b'), sub: h('small'), key: '' };
        r.el = h('li', { class: 'pf-item', 'data-k': k }, r.ic, h('div', { class: 'pf-t' }, r.title, r.sub));
        ul.append(r.el);
        rows[k] = r;
    };
    ['ov', 'li', 'sp', 'sig', 'store'].forEach(mkRow);
    // OBS 리플레이 버퍼 — 사람이 확인하고 체크(오늘만 기억)
    const obsBox = h('input', { type: 'checkbox' });
    obsBox.checked = obsChecked();
    obsBox.addEventListener('change', () => { obsSet(obsBox.checked); for (const l of st.lists) l.update(); });
    const obs = { ic: h('span', { class: 'pf-ic', 'aria-hidden': 'true' }, '🎬') };
    obs.el = h('li', { class: 'pf-item', 'data-k': 'obs' }, obs.ic,
        h('div', { class: 'pf-t' },
            h('label', { class: 'pf-check' }, obsBox, h('b', null, 'OBS 리플레이 버퍼 180초 확인했어요')),
            h('small', null, '클립 앞뒤 90초를 남기려면 필요해요(OBS 설정 → 출력 → 리플레이 버퍼). 오늘만 기억합니다.')));
    ul.append(obs.el);

    function set(k, lv, icon, title, sub) {
        const r = rows[k];
        const key = lv + '|' + icon + '|' + title + '|' + (sub || '');
        if (r.key === key) return;
        r.key = key;
        r.el.className = 'pf-item' + (lv ? ' ' + lv : '');
        r.ic.textContent = icon;
        r.title.textContent = title;
        r.sub.textContent = sub || '';
        r.sub.hidden = !sub;
    }

    function update() {
        const d = st.last;
        const now = obsChecked();
        if (obsBox.checked !== now && document.activeElement !== obsBox) obsBox.checked = now;
        obs.el.className = 'pf-item ' + (obsBox.checked ? 'ok' : 'warn');
        if (!d) {
            for (const k of Object.keys(rows)) set(k, '', '⏳', '확인하는 중…', '');
            sum.textContent = st.err || '확인하는 중…';
            sum.dataset.lv = st.err ? 'bad' : '';
            return;
        }
        const sc = d.screens || {}, li = d.listener || {}, sg = st.sig, so = d.storage || {};
        const others = [];
        if (sc.monitor) others.push('미리보기 ' + sc.monitor + '개(방송엔 안 나감)');
        if (sc.controller) others.push('조종실 ' + sc.controller + '개');
        if (sc.overlay > 0) set('ov', 'ok', '✅', `방송 화면(OBS) 붙음 — ${sc.overlay}개`, others.join(' · '));
        else set('ov', st.live ? 'bad' : 'warn', st.live ? '❌' : '⚠️', '방송 화면(OBS)이 아직 안 붙었어요',
            'OBS 를 켜고 방송판 소스를 [새로고침] 해 주세요' + (others.length ? ' · 지금 붙은 것: ' + others.join(' · ') : ''));

        if (li.level === 'ok') set('li', 'ok', '✅', '후원 받기(투네이션) 연결됨' + (li.connected_sec != null ? ' — ' + ago(li.connected_sec) + '째' : ''),
            li.last_donation_sec != null ? '마지막 후원 ' + ago(li.last_donation_sec) + ' 전' : '');
        else if (li.level === 'connecting') set('li', 'warn', '⏳', '후원 받기 — 투네이션에 붙는 중', li.note || '');
        else if (li.level === 'none') set('li', '', '➖', '후원 받기 프로그램(리스너)이 이 서버엔 없어요', '투네이션 알림창으로 받는 중이면 괜찮아요');
        else set('li', 'bad', '❌', '후원 받기가 멈췄어요', (li.note ? li.note + ' — ' : '') + '리스너가 스스로 다시 붙습니다. 계속되면 알려 주세요');

        if (d.spool == null) set('sp', '', '➖', '못 보낸 후원 — 대기줄 파일을 못 읽었어요', '');
        else if (d.spool > 0) set('sp', 'warn', '📮', `서버로 못 보낸 후원 ${d.spool}건 대기 중`, '서버가 받으면 저절로 들어갑니다(10초마다 다시 보냄)');
        else set('sp', 'ok', '✅', '못 보낸 후원 없음', '');

        if (!sg) set('sig', '', '⏳', '시그니처 목록 확인하는 중…', '');
        else if (sg.ok) set('sig', 'ok', '✅', `시그니처 목록 ${sg.count}개 — 제일 싼 ${sg.cheapest != null ? won(sg.cheapest) : '?'}`, '');
        else set('sig', 'bad', '❌', sg.count === 0 && !sg.note ? '시그니처 목록이 비어 있어요' : '시그니처 목록을 못 받았어요',
            (sg.note ? sg.note + ' — ' : '') + '후원은 들어오지만 시그니처가 안 나갈 수 있어요');

        set('store', so.ok ? 'ok' : 'bad', so.ok ? '✅' : '❌', so.ok ? '저장소 정상' : '저장소가 답하지 않아요',
            so.ok ? (so.ms != null ? so.ms + 'ms' : '') : (so.error || ''));

        let todo = 0;
        for (const r of Object.values(rows)) if (/\b(bad|warn)\b/.test(r.el.className)) todo++;
        if (!obsBox.checked) todo++;
        const s = stale() ? (st.err || '오래된 정보예요 — 다시 확인하는 중') : todo ? `확인할 것 ${todo}개` : '모두 준비됐어요';
        if (sum.textContent !== s) sum.textContent = s;
        sum.dataset.lv = stale() ? 'bad' : todo ? 'warn' : 'ok';
    }

    const api = {
        visible: () => !!el.isConnected && el.offsetParent !== null,
        update,
        render() {
            update();
            // 처음 보이거나(탭을 열었다) 시그니처 확인을 아직 안 했으면 바로 한 번 묻는다
            if (api.visible() && (!st.sig || Date.now() - st.polledAt > GAP_DEEP)) poll(true);
        },
    };
    st.lists.add(api);
    update();
    return api;
}
