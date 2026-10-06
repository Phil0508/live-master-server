/* 📒 장부 탭 — 이번 방송 후원 기록 · 지난 방송 · 점수 기록(되돌린 것은 줄을 그어 보여 준다).

   서버(읽기만): GET /api/ledger?session=<id|current> · /api/sessions · /api/scores?session=<id|current>
   ⚠️ v2 는 방송을 끝내도 장부를 지우지 않는다 — 후원마다 방송 회차가 적혀 있어 회차로 골라 본다.
   다시 불러오기: 대기함 · 집계 · 점수 기록 조각이 바뀌면(새 후원 · 배정 · 되돌리기) 1초 모아서 한 번.
   탭이 닫혀 있으면 아무것도 안 한다(tabs.js 가 열린 탭만 부른다).
   목록은 줄마다 한 번 만들고, 바뀐 줄만 다시 쓴다(2,000줄까지 받아 100줄씩 보여 준다). */
import { h, won, num, signed } from '../../util.js';
import { getJSON, sessionLabel, hms } from './api.js';

const PAGE = 100;
const REFRESH_MS = 1000;
const STATUS = {
    pending: ['대기', 'warn'],
    assigned: ['배정', 'live'],
    ignored: ['무시', 'plain'],
    display: ['화면만', 'info'],
};
const SOURCE = { toonation: '투네이션', toonation_test: '시험 후원', manual: '손으로 넣음' };
const COUNTED = new Set(['pending', 'assigned', 'ignored']);     // 합계에 드는 것(서버 /api/ledger 와 같다)

/* 줄 목록 — 키(id)로 줄을 기억해 두고 바뀐 줄만 다시 쓴다 */
function keyedList(ol, fill) {
    const made = new Map();
    return function draw(items) {
        const keep = new Set(items.map(x => x.key));
        for (const [k, r] of made) if (!keep.has(k)) { r.el.remove(); made.delete(k); }
        items.forEach((it, i) => {
            let r = made.get(it.key);
            if (!r) { r = { el: h('li'), sig: '' }; made.set(it.key, r); }
            const sig = JSON.stringify(it);
            if (sig !== r.sig) { fill(r.el, it); r.sig = sig; }
            if (ol.children[i] !== r.el) ol.insertBefore(r.el, ol.children[i] || null);
        });
    };
}

/* ── 후원 기록(한 회차) ── */
function donationView(ctx, session) {
    const q = h('input', { type: 'text', class: 'rc-q', placeholder: '후원자 이름으로 찾기', autocomplete: 'off', 'aria-label': '후원자 이름으로 찾기' });
    const refresh = h('button', { type: 'button', class: 'btn sm' }, '새로 고침');
    const chipsEl = h('div', { class: 'rc-chips', role: 'group', 'aria-label': '상태로 고르기' });
    const totals = h('div', { class: 'rc-totals' });
    const status = h('p', { class: 'rc-status', role: 'status' });
    const ol = h('ol', { class: 'rc-list' });
    const more = h('button', { type: 'button', class: 'btn sm rc-more', hidden: true });
    const empty = h('p', { class: 'empty', hidden: true });
    const el = h('div', { class: 'rc-view' }, h('div', { class: 'rc-bar' }, q, refresh), chipsEl, totals, status, ol, more, empty);

    let rows = [], filter = 'all', shown = PAGE, loading = false, again = false, loaded = false, err = '';
    const chips = {};
    for (const [k, label] of [['all', '전체'], ['pending', '대기'], ['assigned', '배정'], ['ignored', '무시'], ['display', '화면만']]) {
        const b = h('button', { type: 'button', class: 'rc-chip', 'data-k': k, 'aria-pressed': k === 'all' ? 'true' : 'false',
            onclick: () => { filter = k; shown = PAGE; draw(); } }, h('span', null, label), h('b', { class: 'n' }, '0'));
        chips[k] = b;
        chipsEl.append(b);
    }
    let qt = 0;
    q.addEventListener('input', () => { clearTimeout(qt); qt = setTimeout(() => { shown = PAGE; draw(); }, 150); });
    refresh.addEventListener('click', () => load());
    more.addEventListener('click', () => { shown += PAGE; draw(); });

    const drawRows = keyedList(ol, (li, r) => {
        const [label, cls] = STATUS[r.status] || [r.status, 'plain'];
        li.className = 'rc-row st-' + r.status;
        li.replaceChildren(
            h('span', { class: 'rc-time' }, r.t),
            h('div', { class: 'rc-main' },
                h('div', { class: 'rc-line' },
                    h('b', { class: 'rc-name' }, r.name || '익명'),
                    h('span', { class: 'rc-amt' }, won(r.amount)),
                    h('span', { class: 'tag ' + cls }, label),
                    r.player ? h('span', { class: 'rc-to' }, '→ ' + r.player) : null,
                    r.src ? h('span', { class: 'rc-src' }, r.src) : null),
                r.message ? h('p', { class: 'rc-msg' }, r.message) : null));
    });

    async function load() {
        if (loading) { again = true; return; }
        loading = true;
        refresh.disabled = true;
        if (!loaded) { status.textContent = '불러오는 중…'; status.dataset.lv = ''; }
        try {
            const j = await getJSON('/api/ledger?session=' + encodeURIComponent(session) + '&limit=2000');
            rows = j.rows || [];
            err = '';
            loaded = true;
        } catch (e) {
            err = e.message;
        }
        loading = false;
        refresh.disabled = false;
        draw();
        if (again) { again = false; load(); }
    }

    function draw() {
        status.textContent = err ? err : (!loaded ? '불러오는 중…' : '');
        status.dataset.lv = err ? 'bad' : '';
        status.hidden = !status.textContent;
        const cnt = { all: rows.length, pending: 0, assigned: 0, ignored: 0, display: 0 };
        const sum = { pending: 0, assigned: 0, ignored: 0, display: 0 };
        let total = 0, totalN = 0;
        for (const r of rows) {
            cnt[r.status] = (cnt[r.status] || 0) + 1;
            sum[r.status] = (sum[r.status] || 0) + (Number(r.amount) || 0);
            if (COUNTED.has(r.status)) { total += Number(r.amount) || 0; totalN++; }
        }
        for (const [k, b] of Object.entries(chips)) {
            b.querySelector('.n').textContent = num(cnt[k] || 0);
            b.setAttribute('aria-pressed', k === filter ? 'true' : 'false');
            b.classList.toggle('on', k === filter);
        }
        const qv = q.value.trim().toLowerCase();
        const pick = rows.filter(r => (filter === 'all' || r.status === filter) &&
            (!qv || String(r.name || '').toLowerCase().includes(qv)));
        let pickSum = 0;
        for (const r of pick) if (COUNTED.has(r.status) || filter === 'display') pickSum += Number(r.amount) || 0;

        // ⚠️ replaceChildren 은 null 을 'null' 글자로 넣는다 — 빈 칸은 걸러서 넘긴다
        totals.replaceChildren(...[
            h('div', { class: 'rc-total' }, h('span', { class: 'muted' }, '합계'), h('b', null, won(total)), h('span', { class: 'muted' }, `${num(totalN)}건`)),
            h('div', { class: 'rc-break' },
                h('span', null, '배정 ', h('b', null, won(sum.assigned))),
                h('span', null, '대기 ', h('b', null, won(sum.pending))),
                h('span', null, '무시 ', h('b', null, won(sum.ignored))),
                h('span', { title: '1만 원 미만 — 화면에만 띄운 후원(합계에 안 들어감)' }, '화면만 ', h('b', null, won(sum.display)), ' (합계 밖)')),
            (qv || filter !== 'all') ? h('div', { class: 'rc-picked' }, `고른 것 ${num(pick.length)}건 · ${won(pickSum)}`) : null].filter(Boolean));

        const view = pick.slice(0, shown).map(r => ({
            key: r.id, t: hms(r.at), name: r.name, amount: r.amount, status: r.status, player: r.player || '',
            message: r.message || '', src: SOURCE[r.source] || '',
        }));
        drawRows(view);
        more.hidden = pick.length <= shown;
        more.textContent = `더 보기 (${num(pick.length - shown)}건 남음)`;
        empty.hidden = !loaded || pick.length > 0;
        empty.textContent = rows.length ? '찾는 후원이 없어요' : '이 방송에 들어온 후원이 아직 없어요';
    }

    return { el, load, get loaded() { return loaded; } };
}

/* ── 점수 기록(한 회차) — 같은 묶음(ref) · 같은 사람의 점수 · 기여도는 한 줄로 ── */
const LIST_TAG = { extra: '[번외] ', jar: '[모금함] ', bottom: '' };

function scoreView(ctx, session) {
    const q = h('input', { type: 'text', class: 'rc-q', placeholder: '이름으로 찾기', autocomplete: 'off', 'aria-label': '이름으로 찾기' });
    const refresh = h('button', { type: 'button', class: 'btn sm' }, '새로 고침');
    const hideUndone = h('input', { type: 'checkbox' });
    const summary = h('div', { class: 'rc-totals' });
    const status = h('p', { class: 'rc-status', role: 'status' });
    const ol = h('ol', { class: 'rc-list' });
    const more = h('button', { type: 'button', class: 'btn sm rc-more', hidden: true });
    const empty = h('p', { class: 'empty', hidden: true });
    const el = h('div', { class: 'rc-view' },
        h('div', { class: 'rc-bar' }, q, refresh),
        h('label', { class: 'rc-toggle' }, hideUndone, h('span', null, '되돌린 것 빼고 보기')),
        summary, status, ol, more, empty);

    let rows = [], shown = PAGE, loading = false, again = false, loaded = false, err = '';
    let qt = 0;
    q.addEventListener('input', () => { clearTimeout(qt); qt = setTimeout(() => { shown = PAGE; draw(); }, 150); });
    hideUndone.addEventListener('change', () => { shown = PAGE; draw(); });
    refresh.addEventListener('click', () => load());
    more.addEventListener('click', () => { shown += PAGE; draw(); });

    const drawRows = keyedList(ol, (li, e) => {
        li.className = 'rc-row rc-score' + (e.undone ? ' undone' : '') + (e.neg ? ' neg' : '');
        const parts = [];
        if (e.score != null) parts.push(h('span', { class: 'rc-delta' }, signed(e.score)));
        if (e.contrib != null && e.contrib !== e.score) parts.push(h('span', { class: 'rc-cdelta' }, '기여도 ' + signed(e.contrib)));
        li.replaceChildren(
            h('span', { class: 'rc-time' }, e.t),
            h('div', { class: 'rc-main' },
                h('div', { class: 'rc-line' },
                    h('b', { class: 'rc-name' }, e.pre + e.player),
                    h('span', { class: 'rc-deltas' }, parts),
                    h('span', { class: 'tag ' + (e.don ? 'info' : 'plain') }, e.don ? '후원' : '손으로'),
                    e.undone ? h('span', { class: 'tag bad' }, '되돌림') : null),
                e.reason ? h('p', { class: 'rc-msg' }, e.reason) : null));
    });

    function merge(list) {
        const out = [], at = new Map();
        for (const r of list) {
            const k = r.ref + '|' + r.player + '|' + r.list;
            let e = at.get(k);
            if (!e) {
                e = { key: 'g' + r.id, at: r.at, t: hms(r.at), player: r.player, pre: LIST_TAG[r.list] || '', score: null, contrib: null,
                      reason: r.reason || '', don: String(r.ref || '').startsWith('don_'), undone: true, neg: false };
                at.set(k, e);
                out.push(e);
            }
            if (r.field === 'contribution') e.contrib = (e.contrib || 0) + Number(r.delta || 0);
            else e.score = (e.score || 0) + Number(r.delta || 0);
            if (!r.undone) e.undone = false;
        }
        for (const e of out) e.neg = (e.score != null ? e.score : e.contrib || 0) < 0;
        return out;
    }

    async function load() {
        if (loading) { again = true; return; }
        loading = true;
        refresh.disabled = true;
        try {
            const j = await getJSON('/api/scores?session=' + encodeURIComponent(session) + '&limit=2000');
            rows = merge(j.rows || []);
            err = '';
            loaded = true;
        } catch (e) {
            err = e.message;
        }
        loading = false;
        refresh.disabled = false;
        draw();
        if (again) { again = false; load(); }
    }

    function draw() {
        status.textContent = err ? err : (!loaded ? '불러오는 중…' : '');
        status.dataset.lv = err ? 'bad' : '';
        status.hidden = !status.textContent;
        const qv = q.value.trim().toLowerCase();
        const pick = rows.filter(e => (!hideUndone.checked || !e.undone) && (!qv || String(e.player).toLowerCase().includes(qv)));
        const undone = rows.filter(e => e.undone).length;
        summary.replaceChildren(...[
            h('div', { class: 'rc-total' }, h('span', { class: 'muted' }, '기록'), h('b', null, num(rows.length) + '줄'),
                undone ? h('span', { class: 'muted' }, `그중 되돌림 ${num(undone)}줄(줄 그음)`) : null),
            qv ? h('div', { class: 'rc-picked' }, `고른 것 ${num(pick.length)}줄`) : null].filter(Boolean));
        drawRows(pick.slice(0, shown));
        more.hidden = pick.length <= shown;
        more.textContent = `더 보기 (${num(pick.length - shown)}줄 남음)`;
        empty.hidden = !loaded || pick.length > 0;
        empty.textContent = rows.length ? '찾는 기록이 없어요' : '이 방송의 점수 기록이 아직 없어요';
    }

    return { el, load, get loaded() { return loaded; } };
}

/* ── 지난 방송 — 회차 목록 → 하나를 열면 그 회차의 후원 · 점수 ── */
function sessionsView(ctx) {
    const refresh = h('button', { type: 'button', class: 'btn sm' }, '새로 고침');
    const status = h('p', { class: 'rc-status', role: 'status' });
    const ol = h('ol', { class: 'rc-sessions' });
    const empty = h('p', { class: 'empty', hidden: true }, '아직 지난 방송이 없어요');
    const listBox = h('div', { class: 'rc-view' },
        h('div', { class: 'rc-bar' }, h('p', { class: 'muted small rc-lead' }, '회차를 누르면 그 방송의 후원 · 점수 기록을 봅니다.'), refresh),
        status, ol, empty);
    const detailBox = h('div', { class: 'rc-detail', hidden: true });
    const el = h('div', null, listBox, detailBox);

    let loading = false, loaded = false, list = [];
    refresh.addEventListener('click', () => load());

    const drawRows = keyedList(ol, (li, s) => {
        li.className = 'rc-srow';
        li.replaceChildren(h('button', { type: 'button', class: 'rc-sbtn', onclick: () => openDetail(s.session) },
            h('span', { class: 'rc-sname' }, sessionLabel(s.session, s.first_at), s.cur ? h('span', { class: 'tag ' + (s.live ? 'live' : 'plain') }, s.live ? '방송 중' : '이번 방송') : null),
            h('span', { class: 'rc-ssub' }, `${hms(s.first_at).slice(0, 5)} ~ ${hms(s.last_at).slice(0, 5)} · ${num(s.n)}건`),
            h('b', { class: 'rc-amt' }, won(s.total)),
            h('span', { class: 'rc-chev', 'aria-hidden': 'true' }, '›')));
    });

    async function load() {
        if (loading) return;
        loading = true;
        refresh.disabled = true;
        if (!loaded) status.textContent = '불러오는 중…';
        try {
            const j = await getJSON('/api/sessions');
            list = j.sessions || [];
            loaded = true;
            status.textContent = '';
            status.dataset.lv = '';
        } catch (e) {
            status.textContent = e.message;
            status.dataset.lv = 'bad';
        }
        loading = false;
        refresh.disabled = false;
        draw();
    }

    function draw() {
        status.hidden = !status.textContent;
        const sess = ctx.slices.session || {};
        drawRows(list.map(s => ({ key: 's' + s.session, session: s.session, first_at: s.first_at, last_at: s.last_at, n: s.n, total: s.total,
            cur: !!s.session && s.session === sess.id, live: !!sess.live && s.session === sess.id })));
        empty.hidden = !loaded || list.length > 0;
    }

    let detail = null;
    function openDetail(sid) {
        const s = list.find(x => x.session === sid) || {};
        const dv = donationView(ctx, sid);
        const sv = scoreView(ctx, sid);
        let mode = 'don';
        const segDon = h('button', { type: 'button', class: 'rc-seg-btn on', 'aria-pressed': 'true' }, '후원');
        const segSc = h('button', { type: 'button', class: 'rc-seg-btn', 'aria-pressed': 'false' }, '점수');
        const body = h('div', null, dv.el);
        function setMode(m) {
            mode = m;
            segDon.classList.toggle('on', m === 'don'); segDon.setAttribute('aria-pressed', String(m === 'don'));
            segSc.classList.toggle('on', m === 'sc'); segSc.setAttribute('aria-pressed', String(m === 'sc'));
            const v = m === 'don' ? dv : sv;
            body.replaceChildren(v.el);
            if (!v.loaded) v.load();
        }
        segDon.addEventListener('click', () => setMode('don'));
        segSc.addEventListener('click', () => setMode('sc'));
        const back = h('button', { type: 'button', class: 'btn sm', onclick: closeDetail }, '‹ 지난 방송 목록');
        detailBox.replaceChildren(
            h('div', { class: 'rc-dhead' }, back,
                h('div', { class: 'rc-dtitle' }, h('b', null, sessionLabel(sid, s.first_at)),
                    h('span', { class: 'muted small' }, `${num(s.n || 0)}건 · ${won(s.total || 0)}`))),
            h('div', { class: 'rc-seg sm', role: 'group', 'aria-label': '무엇을 볼까' }, segDon, segSc),
            body);
        detail = { sid, dv, sv, mode: () => mode };
        listBox.hidden = true;
        detailBox.hidden = false;
        dv.load();
        back.focus();
    }
    function closeDetail() {
        detail = null;
        detailBox.replaceChildren();
        detailBox.hidden = true;
        listBox.hidden = false;
        draw();
    }

    return {
        el, load, draw,
        get loaded() { return loaded; },
        /** 이번 방송 회차를 열어 보고 있으면 새 후원 · 점수를 따라 다시 불러온다 */
        refreshDetail(sid) {
            if (detail && detail.sid === sid) (detail.mode() === 'don' ? detail.dv : detail.sv).load();
        },
    };
}

/* ── 탭 ── */
export function mountLedger(el, ctx) {
    const tabs = [['cur', '이번 방송'], ['scores', '점수 기록'], ['past', '지난 방송']];
    const seg = h('div', { class: 'rc-seg', role: 'group', 'aria-label': '장부 고르기' });
    const label = h('span', { class: 'muted small rc-sess' });
    const body = h('div', { class: 'rc-body' });
    el.append(h('div', { class: 'sec-head' }, h('h2', null, '📒 장부'), label), seg, body);

    let mode = 'cur', sid = null;
    let cur = null, scores = null;
    const past = sessionsView(ctx);
    const btns = {};
    for (const [k, t] of tabs) {
        const b = h('button', { type: 'button', class: 'rc-seg-btn', 'aria-pressed': 'false', onclick: () => setMode(k) }, t);
        btns[k] = b;
        seg.append(b);
    }

    function views() {
        // 새 방송이 시작되면(회차가 바뀌면) 이번 방송 · 점수 기록을 새로 만든다
        const want = (ctx.slices.session || {}).id || '';
        if (want !== sid || !cur) {
            sid = want;
            cur = donationView(ctx, 'current');
            scores = scoreView(ctx, 'current');
        }
        return { cur, scores, past };
    }

    function setMode(m) {
        mode = m;
        for (const [k, b] of Object.entries(btns)) { b.classList.toggle('on', k === m); b.setAttribute('aria-pressed', String(k === m)); }
        const v = views()[m];
        if (body.firstChild !== v.el) body.replaceChildren(v.el);
        v.load();
    }

    let seen = {}, dirty = { cur: false, scores: false, past: false }, timer = 0;
    function refreshSoon() {
        clearTimeout(timer);
        timer = setTimeout(() => {
            const v = views();
            if (dirty[mode]) {
                dirty[mode] = false;
                if (mode === 'past') { v.past.load(); v.past.refreshDetail(sid); }
                else v[mode].load();
            }
        }, REFRESH_MS);
    }

    setMode('cur');

    return {
        render(slices) {
            const s = slices.session || {};
            const lbl = s.id ? (s.live ? '방송 중 · ' : '마지막 방송 · ') + sessionLabel(s.id) : '아직 방송 기록이 없어요';
            if (label.textContent !== lbl) label.textContent = lbl;
            const now = { pending: slices.pending, tallies: slices.tallies, logs: slices.logs, session: slices.session };
            const changed = k => seen[k] !== undefined && seen[k] !== now[k];
            if (changed('session') && (s.id || '') !== sid) {
                // 회차가 바뀌었다 — 지금 보는 칸을 새 회차로
                seen = now;
                if (mode !== 'past') setMode(mode);
                dirty.past = true;
                return;
            }
            if (changed('pending') || changed('tallies')) { dirty.cur = true; dirty.past = true; }
            if (changed('logs')) { dirty.scores = true; dirty.past = true; }
            seen = now;
            if (dirty[mode]) refreshSoon();
            if (mode === 'past') past.draw();
        },
    };
}
