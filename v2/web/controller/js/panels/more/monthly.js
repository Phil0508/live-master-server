/* 🗓️ 월별 순위 탭 — 수요일 방송 시간(수 17:00 ~ 목 03:00)에 들어온 후원만 센 달별 후원 순위.
   옛 조종실 loadMonthly · downloadMonthlyCsv 를 옮겼다. 서버: GET /api/ranking/monthly[?month=YYYY-MM](domain/monthly.py)
   ⚠️ 계좌로 딴 날 들어온 후원은 빠진다 — 그게 대표님이 원한 셈이다(순위는 방송에 온 사람들 것).
      익명 · 순위에서 뺀 이름([👑 후원자] 탭)도 빠진다. 같은 사람은 '홍길동님' · '홍길동' 을 하나로 센다.
   달 목록은 자료가 있는 달만(없는 달을 고르면 늘 빈 표가 나온다). 엑셀(CSV)로 내려받기 — 한글이 안 깨지게 BOM,
   = + - @ 로 시작하는 이름은 앞에 ' 를 붙여 엑셀이 수식으로 읽지 않게(옛 _csv_cell 과 같다). */
import { h, num, won } from '../../util.js';
import { getJSON } from '../records/api.js';

const monthName = m => String(m || '').replace(/^(\d{4})-(\d{2})$/, (_, y, mm) => `${y}년 ${+mm}월`);

export function csvCell(v) {
    let t = v == null ? '' : String(v);
    if (/^[=+\-@]/.test(t)) t = "'" + t;
    return '"' + t.replace(/"/g, '""') + '"';
}

export function mountMonthly(el, ctx) {
    el.classList.add('mo');
    const sel = h('select', { class: 'mo-select', 'aria-label': '달 고르기' });
    const refresh = h('button', { type: 'button', class: 'btn sm' }, '새로 고침');
    const csv = h('button', { type: 'button', class: 'btn sm', disabled: true }, '⬇ 엑셀(CSV)');
    const totals = h('div', { class: 'rc-totals', hidden: true });
    const status = h('p', { class: 'rc-status', role: 'status' }, '불러오는 중…');
    const ol = h('ol', { class: 'mo-month' });
    const empty = h('p', { class: 'empty', hidden: true });
    const foot = h('p', { class: 'muted small mo-foot' });
    el.append(
        h('div', { class: 'sec-head' }, h('h2', null, '🗓️ 월별 후원 순위')),
        h('p', { class: 'muted small mo-lead' }, '수요일 방송 시간(수 17:00 ~ 목 03:00)에 들어온 후원만 셉니다. 목요일 새벽 후원은 그 수요일 방송에 붙어요. ',
            '익명 · 순위에서 뺀 이름은 빠지고, 화면에만 띄운 1만 원 미만 후원은 장부처럼 안 셉니다.'),
        h('div', { class: 'rc-bar' }, sel, refresh, csv), totals, status, ol, empty, foot);

    let data = null, loading = false;
    sel.addEventListener('change', () => load(sel.value));
    refresh.addEventListener('click', () => load(sel.value));
    csv.addEventListener('click', download);

    async function load(want) {
        if (loading) return;
        loading = true;
        refresh.disabled = true;
        status.hidden = false;
        status.dataset.lv = '';
        status.textContent = '불러오는 중…';
        try {
            data = await getJSON('/api/ranking/monthly' + (want ? '?month=' + encodeURIComponent(want) : ''));
            status.hidden = true;
        } catch (e) {
            data = null;
            status.textContent = '불러오지 못했어요: ' + e.message;
            status.dataset.lv = 'bad';
        }
        loading = false;
        refresh.disabled = false;
        draw();
    }

    function draw() {
        const d = data || { rows: [], months: [] };
        const months = d.months || [];
        sel.replaceChildren(...(months.length ? months.map(m => h('option', { value: m }, monthName(m)))
            : [h('option', { value: '' }, '(아직 방송 자료가 없어요)')]));
        if (d.month && months.includes(d.month)) sel.value = d.month;
        const rows = d.rows || [];
        csv.disabled = !rows.length;
        totals.hidden = !data;
        totals.replaceChildren(h('div', { class: 'rc-total' },
            h('span', { class: 'muted' }, monthName(d.month) || '이번 달'), h('b', null, won(d.total || 0)), h('span', { class: 'muted' }, `${num(rows.length)}명`)));
        ol.replaceChildren(...rows.map((x, i) => h('li', { class: 'mo-mrow' + (i === 0 ? ' first' : i < 3 ? ' top' : '') },
            h('span', { class: 'mo-rk' }, String(i + 1)),
            h('b', { class: 'mo-mname' }, x.name),
            h('b', { class: 'mo-mtotal' }, won(x.total)),
            h('span', { class: 'mo-msub' }, `${num(x.count)}건 · ${num(x.days)}회 방송`))));
        empty.hidden = !data || rows.length > 0;
        empty.textContent = '이 달에는 방송 중 후원이 없어요.';
        const c = d.clock || {};
        foot.textContent = data ? `창: ${d.window || ''} · 서버 시계(한국 시각) ${c.server_kst || '?'}` : '';
    }

    function download() {
        if (!data || !(data.rows || []).length) { ctx.toast('내려받을 기록이 없어요', 'info'); return; }
        const head = '순위,이름,합계,건수,방송횟수';
        const body = data.rows.map((x, i) => [i + 1, csvCell(x.name), x.total, x.count, x.days].join(',')).join('\r\n');
        const blob = new Blob(['﻿' + head + '\r\n' + body + '\r\n'], { type: 'text/csv;charset=utf-8' });
        const a = h('a', { href: URL.createObjectURL(blob), download: `월별후원순위_${data.month}.csv` });
        document.body.append(a);
        a.click();
        a.remove();
        setTimeout(() => URL.revokeObjectURL(a.href), 2000);
    }

    load('');
    return { render() { /* 장부를 읽는다 — 조각이 바뀌어도 다시 안 읽는다([새로 고침]) */ } };
}
