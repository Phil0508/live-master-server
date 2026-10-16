/* 🏦 엔젤 입금확인 (기업은행) — 시험판 0.1.0
 *
 * 하는 일: 대표님이 직접 로그인해 둔 기업은행 '거래내역조회' 화면에서
 *   ① 정해 둔 간격(기본 30초)마다 [조회] 를 대신 누르고 — 누를 때마다 로그인 12분이 다시 시작된다
 *   ② 표에서 새로 생긴 '입금' 줄만 골라
 *   ③ 화면 오른쪽 아래 작은 상자에 보여 준다.
 * ⚠️ 시험판은 **아무 데도 보내지 않는다.** 방송 서버 연결은 시험이 통과한 뒤 붙인다.
 * ⚠️ 로그인 · 비밀번호 · 이체 화면은 건드리지 않는다. 읽는 것은 거래내역 표, 누르는 것은 [조회] 하나뿐.
 * ⚠️ 표의 칸은 '자리'로 외우지 않고 **칸 제목 글자**(입금 · 잔액 · 내용 …)로 찾는다 —
 *    은행 화면이 조금 바뀌어도 덜 깨지고, 대표님 계좌 화면을 미리 보지 않고도 만들 수 있다.
 * 검사: tests/bankwatch_test.js(아래 순수 도구) · bank-watch/test/mock_ibk.html(가짜 은행 화면)
 */
(function () {
  'use strict';

  /* ══════════ 순수 도구 — node 검사도 이것을 그대로 부른다 ══════════ */

  const norm = (s) => String(s == null ? '' : s).replace(/\s+/g, ' ').trim();

  // "12,000원" · "+12,000" · "-" · "" → 숫자(원). 못 읽으면 0
  function toWon(s) {
    const t = norm(s).replace(/[^0-9-]/g, '');
    if (!t || t === '-') return 0;
    const n = parseInt(t, 10);
    return isNaN(n) ? 0 : n;
  }

  // 짧은 지문(djb2) — 같은 줄인지 가리는 데만 쓴다
  function hashStr(s) {
    let h = 5381;
    const t = String(s);
    for (let i = 0; i < t.length; i++) h = ((h << 5) + h + t.charCodeAt(i)) | 0;
    return (h >>> 0).toString(36);
  }

  /* 머리줄(칸 합치기 colspan · rowspan 포함)을 칸마다 하나의 제목으로 편다.
     hrows: [[{text, colspan, rowspan}, …], …] → ['거래일시', '출금(원)', …] */
  function gridLabels(hrows) {
    const grid = [];
    hrows.forEach((cells, r) => {
      grid[r] = grid[r] || [];
      let c = 0;
      cells.forEach((cell) => {
        while (grid[r][c] !== undefined) c++;
        const cs = Math.max(1, (cell.colspan | 0) || 1);
        const rs = Math.max(1, (cell.rowspan | 0) || 1);
        for (let dr = 0; dr < rs; dr++) {
          grid[r + dr] = grid[r + dr] || [];
          for (let dc = 0; dc < cs; dc++) grid[r + dr][c + dc] = norm(cell.text);
        }
        c += cs;
      });
    });
    const n = grid.reduce((m, row) => Math.max(m, row.length), 0);
    const out = [];
    for (let c = 0; c < n; c++) {
      const parts = [];
      grid.forEach((row) => {
        const t = norm(row[c]);
        if (t && parts[parts.length - 1] !== t) parts.push(t);
      });
      out.push(parts.join(' '));
    }
    return out;
  }

  /* 칸 제목 → 어느 칸이 무엇인가.
     ⚠️ '입금자명' 은 /입금/ 에 먼저 걸리면 안 된다(금액 칸이 아니다) — 이름 칸으로 보낸다. */
  function colMap(labels) {
    const m = { date: -1, time: -1, dep: -1, wd: -1, bal: -1, amt: -1, kind: -1, memo: [] };
    labels.forEach((raw, i) => {
      const l = norm(raw);
      if (!l) return;
      if (i > 0 && norm(labels[i - 1]) === l) return;   // 합친 칸(colspan)이 펴진 둘째 자리 — 같은 칸이다
      const nameLike = /입금자|입금인|입금처|입금은행|출금처|지급처/.test(l);
      if (m.bal < 0 && /잔액|잔고/.test(l)) { m.bal = i; return; }
      if (!nameLike && m.dep < 0 && /입금|맡기신/.test(l)) { m.dep = i; return; }
      if (!nameLike && m.wd < 0 && /출금|찾으신|지급/.test(l)) { m.wd = i; return; }
      if (m.date < 0 && /일시|일자|거래일|날짜/.test(l)) { m.date = i; return; }
      if (m.time < 0 && /시간|시각/.test(l)) { m.time = i; return; }
      if (m.amt < 0 && /금액/.test(l)) { m.amt = i; return; }
      if (m.kind < 0 && /구분|종류|입출/.test(l)) { m.kind = i; return; }
      if (nameLike || /내용|적요|기재|보낸|받는|의뢰인|메모|비고|예금주|상대|통장표시|이름|성명/.test(l)) m.memo.push(i);
    });
    m.ok = (m.dep >= 0 || (m.amt >= 0 && m.kind >= 0)) && (m.bal >= 0 || m.date >= 0);
    return m;
  }

  /* 한 줄(글자 칸들) → {when, dep, wd, kind, memo[], key}.
     key 는 줄 전체 글자의 지문 + 같은 표 안에서 몇 번째로 똑같은 줄인가(#n).
     ⚠️ 잔액 칸이 있으면 같은 사람 · 같은 금액이어도 줄마다 달라진다. 없을 때를 위해 #n 을 붙인다. */
  function rowFrom(cells, m) {
    const t = cells.map(norm);
    const kind = m.kind >= 0 ? (t[m.kind] || '') : '';
    let dep = m.dep >= 0 ? toWon(t[m.dep]) : 0;
    if (m.dep < 0 && m.amt >= 0 && /입금/.test(kind)) dep = toWon(t[m.amt]);
    const wd = m.wd >= 0 ? toWon(t[m.wd]) : 0;
    const memo = m.memo.map((i) => t[i]).filter(Boolean);
    const cols = m.memo.map((i) => t[i] || '');      // 이름/내용 칸 값 — m.memo 와 같은 순서(머리글과 짝지어 서버로 보낸다)
    const when = [m.date >= 0 ? t[m.date] : '', m.time >= 0 ? t[m.time] : ''].filter(Boolean).join(' ');
    // ⚠️ 줄 지문엔 뜻 있는 칸만 — 기업 인터넷뱅킹 표는 맨 앞에 1 · 2 · 3 번호 칸이 있어서, 새 입금이 오면 모든 줄 번호가
    //    하나씩 밀린다 → 모든 줄이 '새 줄' → '표가 통째로 바뀜' 으로 기준을 새로 잡아 입금을 놓쳤다(10-14 실제 1원).
    const keep = [m.date, m.time, m.dep, m.wd, m.bal, m.amt, m.kind].concat(m.memo).filter((i) => i >= 0);
    const raw = keep.length >= 2 ? keep.map((i) => t[i] || '').join('|') : t.join('|');
    return { when, dep, wd, kind, memo, cols, raw };
  }
  function keyRows(rows) {
    const seen = {};
    rows.forEach((r) => {
      const h = hashStr(r.raw);
      seen[h] = (seen[h] || 0) + 1;
      r.key = h + '#' + (seen[h] - 1);
    });
    return rows;
  }

  /* 이번 표에서 새 줄 고르기.
     · 처음(기준 없음) → 지금 있는 줄은 전부 '본 것'으로 두고 아무것도 안 알린다(예전 입금이 쏟아지지 않게)
     · 아는 줄이 하나도 없는데 줄이 넉넉하다 → 다른 계좌 · 다른 기간으로 바뀐 표다 → 기준을 새로 잡는다 */
  // 새 입금 줄 → 방송 서버로 보낼 모양. 이름/내용 칸은 [머리글, 값] 으로 — 서버가 메모 칸 · 실명(예금주) 칸을 가른다
  // ⚠️ 번호(ref)에 시각 · 금액을 붙인다 — 줄 지문(key)은 짧아서 드물게 겹칠 수 있고, 겹치면 서버가 '같은 입금' 으로 보고 버린다
  function depPayload(r, labels, m) {
    return {
      ref: r.key + '@' + (r.when || '') + '@' + r.dep, amount: r.dep, when: r.when,
      fields: m.memo.map((i, k) => [labels[i] || '', (r.cols || [])[k] || '']).filter((x) => x[1]),
    };
  }

  /* 카드 취소 · 환불도 '입금' 줄로 들어온다(10-14 기업 인터넷뱅킹: 입금 11,800 '카카오T택시_가승인').
     후원이 아니다 → 내용에 가승인 · 취소 · 환불이 있거나, 같은 표에 같은 내용 · 같은 금액의 출금 줄이 있으면 뺀다. */
  function isRefund(r, rows) {
    const memo = (r.memo || []).join(' ');
    if (/가승인|승인취소|취소|환불/.test(memo)) return true;
    const first = (r.memo || [])[0] || '';
    return !!first && (rows || []).some((o) => o !== r && o.wd > 0 && o.wd === r.dep && ((o.memo || [])[0] || '') === first);
  }

  /* 칸 이름이 진짜 그 칸인가 — 날짜칸엔 날짜, 잔액칸엔 숫자, 입금칸엔 숫자나 빈칸. 0~1 (맞는 줄의 비율) */
  function sanity(cells, m) {
    if (!cells || !cells.length) return 0;
    const isDate = (v) => /\d{4}\D?\d{1,2}\D?\d{1,2}|\d{1,2}[./-]\d{1,2}/.test(norm(v));
    const isNum = (v) => /^-?\d+$/.test(norm(v).replace(/[,원\s]/g, ''));
    const numOrEmpty = (v) => norm(v).replace(/[,원\s]/g, '') === '' || isNum(v);
    let ok = 0;
    cells.forEach((t) => {
      if ((m.date < 0 || isDate(t[m.date])) && (m.bal < 0 || isNum(t[m.bal])) && (m.dep < 0 || numOrEmpty(t[m.dep]))) ok++;
    });
    return ok / cells.length;
  }

  function judge(rows, seen, hadBase) {
    if (!hadBase) return { baseline: true, fresh: [] };
    const fresh = rows.filter((r) => !seen[r.key]);
    if (rows.length >= 4 && fresh.length === rows.length) return { rebase: true, fresh: [] };
    return { fresh };
  }

  // 최근 거래가 위에 있나 — 아래에 있으면(오래된 순) 새 입금이 다음 쪽으로 밀려 안 보일 수 있다
  function newestFirst(rows) {
    const d = rows.map((r) => (r.when || '').replace(/[^0-9]/g, '')).filter((x) => x.length >= 8);
    if (d.length < 2) return true;
    return d[0] >= d[d.length - 1];
  }

  if (typeof window === 'undefined' || typeof document === 'undefined') {
    if (typeof module !== 'undefined') module.exports = { norm, toWon, hashStr, gridLabels, colMap, rowFrom, keyRows, judge, newestFirst, depPayload, isRefund, sanity, cmdPlan };
    return;
  }

  /* ══════════ 은행 화면 쪽 ══════════ */

  // 🧪 가짜 은행 화면(내 PC 의 시험 페이지)에서만 3초 간격 — 진짜 은행 주소에서는 절대 안 켜진다
  const FAST = /^(127\.0\.0\.1|localhost)$/.test(location.hostname) && /awfast=1/.test(location.search);
  const VER = '0.4.0';
  const STALL_MS = 150 * 1000;   // 조회를 누르는데 표가 이만큼 안 바뀌면 '끊김'(은행이 조용히 로그아웃시킨 것)
  const KEY = 'aw1';
  const DEF = {
    enabled: false, interval: 30, taught: '', seen: {}, found: [], baseAt: 0, baseSig: '',
    clicks: 0, lastClickAt: 0, startedAt: 0, lastOkAt: 0, logoutAt: 0, log: [], folded: true, v4: 0,
  };
  let S = null;
  let timer = null;
  let teach = false;
  let lastFound = null;            // 지금 찾은 표 {el, labels, m, rows}
  let ui = null;                   // 상자(그림자 DOM)
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  const load = () => new Promise((res) => {
    try { chrome.storage.local.get(KEY, (o) => res(Object.assign({}, DEF, (o && o[KEY]) || {}))); }
    catch (e) { res(Object.assign({}, DEF)); }
  });
  const save = () => new Promise((res) => {
    try { chrome.storage.local.set({ [KEY]: S }, () => res()); } catch (e) { res(); }
  });
  const hhmm = (t) => { if (!t) return '-'; const d = new Date(t); return d.toTimeString().slice(0, 8); };
  const dur = (ms) => { const m = Math.floor(ms / 60000); return m >= 60 ? Math.floor(m / 60) + '시간 ' + (m % 60) + '분' : m + '분'; };
  function note(msg) {
    S.log.unshift(hhmm(Date.now()) + ' ' + msg);
    S.log = S.log.slice(0, 30);
  }

  function visible(el) {
    if (!el || !el.getClientRects || !el.getClientRects().length) return false;
    const st = getComputedStyle(el);
    return st.visibility !== 'hidden' && st.display !== 'none';
  }

  // 칸 합치기(colspan)를 풀어 '자리' 대로 편다. 머리줄도 gridLabels 로 자리마다 펴지므로 몸통도 같은 자리 수가 되어야
  // 칸 이름과 맞는다 — 기업 인터넷뱅킹(TreeGrid) 몸통은 칸이 2자리씩 합쳐져 있다(10-14 실측: 제목 39자리 · 몸통 칸 20개).
  function spread(cells) {
    const out = [];
    cells.forEach((c) => {
      out.push(c.innerText || c.textContent || '');
      for (let k = 1; k < (c.colSpan | 0); k++) out.push('');
    });
    return out;
  }
  const cellInfo = (r) => Array.from(r.cells).map((c) => ({ text: c.innerText || c.textContent, colspan: c.colSpan, rowspan: c.rowSpan }));
  function headerRows(table) {
    let rows = table.tHead ? Array.from(table.tHead.rows) : [];
    if (!rows.length) {
      for (const r of Array.from(table.rows)) {
        const c = Array.from(r.cells);
        if (c.length && c.every((x) => x.tagName === 'TH')) rows.push(r); else break;
      }
    }
    return rows.map(cellInfo);
  }
  function bodyRows(table, skip) {
    return Array.from(table.rows).slice(skip).map((r) => Array.from(r.cells))
      .filter((c) => c.length >= 3 && c.some((x) => x.tagName === 'TD'))
      .map(spread);
  }

  /* 거래내역 표 찾기. ⚠️ 은행 화면은 머리줄과 몸통을 **서로 다른 표**로 나눠 두기도 한다(위 고정 · 아래 스크롤).
     머리만 있고 몸통이 없으면, 뒤따르는 표 중 자리 수가 같은 것을 몸통으로 쓴다.
     ⚠️ 기업 인터넷뱅킹(TreeGrid)은 진짜 칸 이름이 '머리 표'의 TD 줄에 있고, 몸통 표 맨 위 TH 줄은 칸 이름이 3칸 밀린
        크기 맞춤 줄이다(10-14 실측). 그래서 머리 후보를 여럿 만들고, 날짜칸에 날짜 · 잔액칸에 숫자가 실제로 있는 쪽을 고른다. */
  function findTable(doc) {
    const tables = Array.from(doc.querySelectorAll('table'));
    let best = null;
    tables.forEach((tb, idx) => {
      const cands = [];
      const hr = headerRows(tb);
      if (hr.length) cands.push({ hr, skip: hr.length });
      Array.from(tb.rows).slice(0, 3).forEach((r, k) => {
        if (k < hr.length) return;
        const c = Array.from(r.cells);
        if (c.length >= 3 && c.every((x) => x.tagName === 'TD')) cands.push({ hr: [cellInfo(r)], skip: k + 1 });
      });
      cands.forEach((cd) => {
        const labels = gridLabels(cd.hr);
        const m = colMap(labels);
        if (!m.ok) return;
        let body = bodyRows(tb, cd.skip).filter((c) => c.length === labels.length || c.length === labels.length - 1);
        let bodyEl = tb;
        if (!body.length) {
          for (let j = idx + 1; j < Math.min(tables.length, idx + 8); j++) {
            const b = bodyRows(tables[j], 0).filter((c) => c.length === labels.length);
            if (b.length) { body = b; bodyEl = tables[j]; break; }
          }
        }
        const sane = sanity(body, m);
        const score = (m.dep >= 0 ? 3 : 0) + (m.bal >= 0 ? 2 : 0) + (m.date >= 0 ? 2 : 0) + m.memo.length + Math.min(body.length, 20) / 20 + sane * 10;
        // 줄을 못 읽을 때 상자에 보여줄 표 모양 — 이것만 캡처해 주시면 고칠 수 있다
        const diag = '표 ' + tables.length + '개 중 ' + (idx + 1) + '번 · 제목 ' + labels.length + '자리 · 몸통 ' + body.length + '줄' + (bodyEl !== tb ? '(다른 표)' : '') + ' · 맞음 ' + Math.round(sane * 100) + '%';
        if (!best || score > best.score) best = { el: tb, bodyEl, labels, m, cells: body, score, diag };
      });
    });
    if (!best) return null;
    best.rows = keyRows(best.cells.map((c) => rowFrom(c, best.m)));
    return best;
  }

  function findButton(doc, tableEl, taught) {
    if (taught) {
      try { const el = doc.querySelector(taught); if (el && visible(el)) return el; } catch (e) {}
    }
    const cands = Array.from(doc.querySelectorAll('button, input[type=button], input[type=submit], input[type=image], a, span[role=button], div[role=button]'))
      .filter((el) => visible(el) && !el.closest('nav, header, #gnb, .gnb, #header, .header, .lnb, #lnb'))
      .filter((el) => /^조회(하기)?$/.test(norm(el.innerText || el.value || el.alt || el.getAttribute('title') || '')))
      .filter((el) => !/uf_goAfterLogin|\.jsp/.test((el.getAttribute('onclick') || '') + (el.getAttribute('href') || '')));
    if (!cands.length) return null;
    if (tableEl) {
      const before = cands.filter((el) => el.compareDocumentPosition(tableEl) & Node.DOCUMENT_POSITION_FOLLOWING);
      if (before.length) return before[before.length - 1];
    }
    return cands[0];
  }

  /* 🌙 자정 넘기기 — 방송은 새벽 3시까지다. 조회 기간 끝 날짜가 '어제'로 남아 있으면
     자정 뒤 입금이 표에 안 나온다. [조회] 앞에 있는 날짜 칸 중 마지막(=끝 날짜)이 오늘보다 앞이면 오늘로 고친다.
     ⚠️ 미래 날짜거나 날짜 모양이 아니면 손대지 않는다. 시작 날짜는 그대로 둔다(표가 통째로 바뀌지 않게). */
  const pad2 = (n) => String(n).padStart(2, '0');
  function rollEndDate(doc, btn) {
    const re = /^(\d{4})([.\-/]?)(\d{2})\2(\d{2})$/;
    let ins = Array.from(doc.querySelectorAll('input')).filter((i) => re.test((i.value || '').trim()) && visible(i));
    if (!ins.length) return rollEndSelects(doc, btn);
    if (btn) { const before = ins.filter((i) => i.compareDocumentPosition(btn) & Node.DOCUMENT_POSITION_FOLLOWING); if (before.length) ins = before; }
    const end = ins[ins.length - 1];
    const mm = end.value.trim().match(re);
    const d = new Date();
    const want = d.getFullYear() + mm[2] + pad2(d.getMonth() + 1) + mm[2] + pad2(d.getDate());
    const cur = end.value.trim();
    if (cur === want || cur.replace(/\D/g, '') > want.replace(/\D/g, '')) return { found: true, changed: false };
    end.value = want;
    end.dispatchEvent(new Event('input', { bubbles: true }));
    end.dispatchEvent(new Event('change', { bubbles: true }));
    return { found: true, changed: true, from: cur, to: want };
  }
  // 기업 인터넷뱅킹: 조회기간이 [년▾][월▾][일▾] ~ [년▾][월▾][일▾] 고르기 칸이다(10-14 실측). [조회] 앞 마지막 묶음 = 끝 날짜.
  //  (그 위 '월별조회' 는 [년▾][월▾] 둘뿐이라 묶음이 안 된다)
  function rollEndSelects(doc, btn) {
    let sels = Array.from(doc.querySelectorAll('select')).filter(visible);
    if (btn) { const before = sels.filter((x) => x.compareDocumentPosition(btn) & Node.DOCUMENT_POSITION_FOLLOWING); if (before.length) sels = before; }
    const n = (x) => parseInt(x.value, 10);
    const trip = [];
    for (let i = 0; i + 2 < sels.length; i++) {
      const y = sels[i], mo = sels[i + 1], da = sels[i + 2];
      if (/^\d{4}$/.test((y.value || '').trim()) && n(mo) >= 1 && n(mo) <= 12 && n(da) >= 1 && n(da) <= 31) trip.push([y, mo, da]);
    }
    if (!trip.length) return { found: false };
    const [y, mo, da] = trip[trip.length - 1];
    const d = new Date();
    const cur = n(y) * 10000 + n(mo) * 100 + n(da);
    const want = d.getFullYear() * 10000 + (d.getMonth() + 1) * 100 + d.getDate();
    if (cur >= want) return { found: true, changed: false };
    // ⚠️ 은행 화면은 '오늘'까지만 고르기 칸에 넣어 둔다(14일이면 1~14일). 자정을 넘기면 15일이 목록에 없어서 붙인다.
    const setTo = (x, v) => {
      let o = Array.from(x.options).find((op) => parseInt(op.value, 10) === v);
      if (!o) {
        const like = (x.options[0] && x.options[0].value) || '';
        const val = like.length === 2 ? pad2(v) : String(v);
        o = doc.createElement('option');
        o.value = val; o.textContent = val;
        x.appendChild(o);
      }
      x.value = o.value;
      x.dispatchEvent(new Event('change', { bubbles: true }));
      return parseInt(x.value, 10) === v;
    };
    const ok = setTo(y, d.getFullYear()) && setTo(mo, d.getMonth() + 1) && setTo(da, d.getDate());
    return { found: true, changed: ok, from: String(cur), to: String(want) };
  }

  function cssPath(el) {
    if (el.id) return '#' + CSS.escape(el.id);
    const parts = [];
    for (let e = el; e && e.nodeType === 1 && e !== document.body; e = e.parentElement) {
      let p = e.tagName.toLowerCase();
      if (e.id) { parts.unshift('#' + CSS.escape(e.id)); break; }
      const sib = Array.from(e.parentElement ? e.parentElement.children : []).filter((x) => x.tagName === e.tagName);
      if (sib.length > 1) p += ':nth-of-type(' + (sib.indexOf(e) + 1) + ')';
      parts.unshift(p);
    }
    return parts.join(' > ');
  }

  function looksLoggedOut() {
    return !!document.querySelector('input[type=password]') || /login|certi/i.test(location.pathname);
  }

  /* ─── 방송 서버로 보내기 (0.2) ───
     은행 화면 안에서는 우리 서버로 직접 못 보낸다(CORS) → 확장 배경(background.js)에 넘기면 배경이 보낸다.
     보내는 것: 새 입금(금액 · 시각 · 이름/내용 칸) + 30초마다 '살아 있음' 신호(빈 목록). 받는 쪽은 후원 콘솔의 추천 칸뿐. */
  const LINKKEY = 'aw-link';
  const PROD = 'https://xn--9i1b547a0ublxlz4f.xn--h32bi4v.xn--3e0b707e';   // 엔젤컴퍼니.메인.한국
  let net = { why: 'idle', at: 0, queued: 0 };
  let lastBeat = 0;
  const loadLink = () => new Promise((res) => {
    try { chrome.storage.local.get(LINKKEY, (o) => res(Object.assign({ server: PROD, key: '' }, (o && o[LINKKEY]) || {}))); }
    catch (e) { res({ server: PROD, key: '' }); }
  });
  function sendDeps(deposits) {
    lastBeat = Date.now();
    if (typeof chrome === 'undefined' || !chrome.runtime || !chrome.runtime.sendMessage) { net = { why: 'ext', at: 0, queued: 0 }; return; }
    const what = S && S.enabled ? '자동 조회 ' + S.clicks + '번' : '자동 조회 꺼짐';
    let state = null;
    try { state = snap(); } catch (e) {}
    try {
      chrome.runtime.sendMessage({ t: 'aw-send', deposits, note: what, state }, (res) => {
        if (chrome.runtime.lastError || !res) { net = { why: 'ext', at: net.at, queued: net.queued }; tick(); return; }
        net = res.ok ? { why: 'ok', at: res.at, queued: res.queued } : { why: res.why, code: res.code, at: net.at, queued: res.queued };
        if (deposits.length && res.ok) note('방송 서버로 보냄 — 입금 ' + deposits.length + '건');
        tick();
        if (res.ok && Array.isArray(res.cmds) && res.cmds.length) applyCmds(res.cmds);   // 🪞 조종실이 넣어 둔 명령
      });
    } catch (e) { net = { why: 'ext', at: 0, queued: 0 }; }
  }
  // 25초에 한 번 '살아 있음' — 후원 콘솔 · 조종실이 '은행 확장 연결됨 · n초 전' 을 보여준다. 못 보낸 입금도 이때 다시 간다.
  // ⚠️ 자동 조회가 꺼져 있어도 보낸다 — 조종실에서 켤 수 있어야 하고, 로그아웃된 것도 알려야 한다
  function beat() { if (ui && Date.now() - lastBeat > 25000) sendDeps([]); }

  /* 🪞 조종실 명령(0.4) — 순수 계산(cmdPlan)과 적용(applyCmds)을 나눠 둔다. 검사는 cmdPlan 만 부른다.
     enable(on) · interval(sec) · rebase(기준 다시 잡기) · press([조회] 한 번). 모르는 명령은 넘긴다. */
  function cmdPlan(S0, cmds) {
    const out = Object.assign({}, S0);
    const notes = [];
    let press = false, rescan = false;
    for (const c of cmds || []) {
      if (!c || typeof c !== 'object') continue;
      if (c.t === 'enable') {
        const on = !!c.on;
        if (on !== !!out.enabled) { out.enabled = on; if (on) { out.startedAt = Date.now(); out.lastClickAt = 0; } }
        notes.push('조종실에서 자동 조회 ' + (on ? '켬' : '끔'));
      } else if (c.t === 'interval') {
        const sec = parseInt(c.sec, 10);
        if ([20, 30, 60].indexOf(sec) >= 0) { out.interval = sec; notes.push('조종실에서 간격 ' + sec + '초'); }
      } else if (c.t === 'rebase') {
        out.baseAt = 0; out.baseSig = ''; rescan = true;
        notes.push('조종실에서 기준 다시 잡기 — 지금 표의 줄은 알리지 않아요');
      } else if (c.t === 'press') {
        press = true;
        notes.push('조종실에서 [조회] 한 번');
      }
    }
    return { S: out, notes, press, rescan };
  }
  async function applyCmds(cmds) {
    S = await load();
    const r = cmdPlan(S, cmds);
    S = r.S;
    r.notes.forEach(note);
    document.documentElement.setAttribute('data-aw-on', S.enabled ? '1' : '0');
    await save();
    render();
    schedule();
    if (r.rescan) { lastRowsSig = ''; await scan('change'); }
    if (r.press) await pressNow();
    sendDeps([]);                           // 바뀐 상태를 바로 조종실에 알린다(명령은 서버가 이미 지웠다 — 되돌이 없음)
  }
  function netStatus() {
    switch (net.why) {
      case 'ok': return ['방송 서버로 보냄 ✓ ' + hhmm(net.at) + (net.queued ? ' · 기다리는 입금 ' + net.queued + '건' : ''), 'ok'];
      case 'nokey': return ['열쇠를 넣어야 방송 서버로 보내요 — 아래 [방송 서버 연결]' + (net.queued ? ' (기다리는 입금 ' + net.queued + '건)' : ''), 'warn'];
      case 'key': return ['열쇠가 맞지 않아요 — 후원 콘솔 [은행 확장 연결]에서 다시 복사해 넣어 주세요', 'bad'];
      case 'net': return ['방송 서버에 연결하지 못했어요 — 30초마다 다시 보내요' + (net.queued ? ' (기다리는 입금 ' + net.queued + '건)' : ''), 'bad'];
      case 'http': return ['방송 서버가 받지 않았어요(' + net.code + ') — 30초마다 다시 보내요', 'bad'];
      case 'server': return ['보낼 서버 주소가 이상해요 — [방송 서버 연결]에서 다시 골라 주세요', 'bad'];
      case 'ext': return ['확장 배경과 연결이 끊겼어요 — 은행 화면을 새로고침해 주세요', 'bad'];
      default: return ['방송 서버: 아직 안 보냄', ''];
    }
  }

  /* ─── 표 읽기 ─── */
  // ⚠️ 은행 화면에는 1초마다 바뀌는 '남은 시간' 시계 같은 것이 있다. 그때마다 저장하면 쓰기가 폭주한다 —
  //    표 줄이 그대로면 저장하지 않고(마지막 정상 시각만 30초에 한 번) 넘긴다.
  let lastRowsSig = '';
  let lastOkSaved = 0;
  async function scan(why) {
    const f = findTable(document);
    lastFound = f;
    if (!f) { render(); return; }
    const now = Date.now();
    const rowsSig = f.rows.map((r) => r.key).join(',');
    if (why !== 'load' && rowsSig === lastRowsSig) {
      S.lastOkAt = now;
      if (now - lastOkSaved > 30000) { lastOkSaved = now; await save(); }
      tick();
      beat();
      return;
    }
    lastRowsSig = rowsSig;
    lastOkSaved = now;
    const sig = 'k2|' + f.labels.join('|');      // k2 = 번호 칸을 뺀 지문(0.3.1) — 옛 지문과 섞이지 않게 기준을 새로 잡는다
    const hadBase = S.baseAt > 0 && S.baseSig === sig;
    const j = judge(f.rows, S.seen, hadBase);
    f.rows.forEach((r) => { if (!S.seen[r.key]) S.seen[r.key] = now; });
    if (j.baseline) note('기준 잡음 — 지금 표의 ' + f.rows.length + '줄은 알리지 않아요');
    if (j.rebase) { note('표가 통째로 바뀌어(다른 계좌 · 기간?) 기준을 새로 잡았어요'); }
    if (j.baseline || j.rebase) { S.baseAt = now; S.baseSig = sig; }
    const deps = (j.fresh || []).filter((r) => r.dep > 0 && !isRefund(r, f.rows));
    if (deps.length) sendDeps(deps.map((r) => depPayload(r, f.labels, f.m)));
    else beat();
    deps.reverse().forEach((r) => {
      S.found.unshift({ at: now, when: r.when, dep: r.dep, memo: r.memo, kind: r.kind });
      note('새 입금 ' + r.dep.toLocaleString() + '원 ' + (r.memo.join(' · ') || ''));
    });
    S.found = S.found.slice(0, 50);
    S.lastOkAt = now;
    S.logoutAt = 0;
    // 오래된 지문은 버린다(3일 · 3000개)
    const keys = Object.keys(S.seen);
    if (keys.length > 3000) keys.sort((a, b) => S.seen[a] - S.seen[b]).slice(0, keys.length - 3000).forEach((k) => delete S.seen[k]);
    keys.forEach((k) => { if (now - S.seen[k] > 3 * 864e5) delete S.seen[k]; });
    await save();
    render(deps.length > 0);
  }

  /* ─── [조회] 누르기 ─── */
  function schedule() {
    clearTimeout(timer);
    if (!S.enabled) return;
    const due = (S.lastClickAt || 0) + (FAST ? 3 : S.interval) * 1000;
    timer = setTimeout(press, Math.max(1500, due - Date.now()));
  }
  async function press() {
    S = await load();                       // 새로고침 · 다른 틀이 바꿨을 수 있다
    document.documentElement.setAttribute('data-aw-on', S.enabled ? '1' : '0');
    if (!S.enabled) { render(); return; }
    await doPress();
    schedule();                             // 화면이 새로 뜨면 이 타이머는 사라지고 boot 가 다시 건다
  }
  // [조회] 한 번 — 자동 조회가 꺼져 있어도 누른다(조종실의 [지금 조회])
  async function pressNow() {
    S = await load();
    await doPress();
    if (S.enabled) schedule();
  }
  async function doPress() {
    const btn = findButton(document, lastFound && lastFound.el, S.taught);
    S.lastClickAt = Date.now();
    if (!btn) {
      note('조회 버튼을 못 찾았어요 — [버튼 지정]으로 알려 주세요');
      await save(); render(); return;
    }
    S.clicks += 1;
    try {
      const rd = rollEndDate(document, btn);
      S.dateOk = rd.found;
      if (rd.changed) note('조회 끝 날짜를 오늘로 바꿈 (' + rd.from + ' → ' + rd.to + ')');
    } catch (e) {}
    await save();
    render();
    try { btn.click(); } catch (e) { note('누르기 실패: ' + e.message); }
  }

  /* ─── 상자(그림자 DOM — 은행 화면 글꼴 · 색에 안 섞이게) ───
     0.4 '신호등 바'(대표님 10-16 시안 A): 평소엔 두 줄짜리 바 — 왼쪽 점이 신호등(초록 · 노랑 · 빨강), 오른쪽에 찾은 입금 수.
     바를 누르면 예전 상자 내용(단추 · 찾은 입금 · 기록 · 열쇠)이 펼쳐진다. 새 입금은 바 위로 초록 말풍선, 끊기면 바 전체가 빨개진다.
     색 · 글꼴은 조종실 · 후원 콘솔(ops-theme)과 같은 옷 — 조종실 거울(bankext-box)도 같은 모양으로 그린다. */
  function mountUI() {
    if (ui) return;
    const host = document.createElement('div');
    host.id = 'angel-bankwatch';
    host.style.cssText = 'position:fixed;right:12px;bottom:12px;z-index:2147483647;';
    const root = host.attachShadow({ mode: 'open' });
    root.innerHTML = `
      <style>
        .toast{position:absolute;right:0;bottom:calc(100% + 8px);width:320px;max-width:calc(100vw - 24px);box-sizing:border-box;background:#17311f;border:1px solid rgba(61,220,132,.5);color:#e8ffef;border-radius:12px;padding:9px 12px;font:800 13px/1.4 'Pretendard','Malgun Gothic',sans-serif;box-shadow:0 10px 30px rgba(0,0,0,.5);animation:up .35s ease}
        .toast small{display:block;font-weight:500;color:#9fe2b8;font-size:11.5px}
        .toast[hidden]{display:none}
        @keyframes up{from{transform:translateY(12px);opacity:0}to{transform:none;opacity:1}}
        .bx{width:320px;max-width:calc(100vw - 24px);box-sizing:border-box;font:13px/1.45 'Pretendard','Malgun Gothic',sans-serif;color:#f6f1ec;background:#221a16f2;border:1px solid rgba(255,255,255,.13);border-radius:14px;box-shadow:0 12px 40px rgba(0,0,0,.45);overflow:hidden}
        .bx.dead{background:#3a1717f5;border-color:#ff6b6b}
        .top{display:flex;align-items:center;gap:10px;padding:9px 12px;cursor:pointer;user-select:none}
        .dot{width:14px;height:14px;border-radius:50%;background:#8c8078;flex:none;box-shadow:0 0 0 4px rgba(140,128,120,.18)}
        .dot.ok{background:#3ddc84;box-shadow:0 0 0 4px rgba(61,220,132,.18)}
        .dot.warn{background:#f5a524;box-shadow:0 0 0 4px rgba(245,165,36,.2)}
        .dot.bad{background:#ff6b6b;box-shadow:0 0 0 4px rgba(255,107,107,.25);animation:blink 1s steps(2) infinite}
        .dot.pulse{animation:pulse 1s ease 3}
        @keyframes blink{50%{opacity:.35}}
        @keyframes pulse{50%{box-shadow:0 0 0 10px rgba(61,220,132,.05)}}
        .t{flex:1;min-width:0;font-weight:800;font-size:13px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
        .t small{display:block;font-weight:500;font-size:11.5px;color:#bcb0a6;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
        .bx.dead .t small{color:#f1c7c7}
        .cnt{font-weight:900;font-size:12px;padding:3px 9px;border-radius:20px;background:rgba(240,123,63,.16);color:#ff8f57;white-space:nowrap}
        .bx.dead .cnt{background:rgba(255,107,107,.2);color:#ffb3b3}
        .fold{background:none;border:0;color:#bcb0a6;cursor:pointer;padding:0 2px;font:inherit;font-size:14px}
        .bd{padding:2px 12px 10px;display:grid;gap:6px;max-height:60vh;overflow:auto;border-top:1px solid rgba(255,255,255,.08)}
        .st{padding:6px 8px;border-radius:8px;background:#2b221d;font-size:12px}
        .st.ok{background:#173b2a}.st.bad{background:#4a1f1f}.st.warn{background:#4a3b17}
        .row{display:flex;gap:6px;flex-wrap:wrap;align-items:center}
        .row button,.row select{background:#342923;color:#f6f1ec;border:1px solid rgba(255,255,255,.13);border-radius:8px;padding:4px 9px;cursor:pointer;font:inherit;font-size:12px}
        .row button.on{background:#2f6f4a;border-color:#3f9a66}
        .mut{color:#bcb0a6;font-size:12px}
        .dep{display:grid;grid-template-columns:auto 1fr;gap:2px 8px;padding:6px 8px;border-radius:8px;background:#2b221d}
        .dep b{color:#ffb36b;font-variant-numeric:tabular-nums}
        ul{margin:0;padding-left:16px}
        .lk{padding:0 12px 10px}
        .lk .row{margin-top:6px}
        .lk input{flex:1;min-width:0;background:rgba(0,0,0,.26);color:#f6f1ec;border:1px solid rgba(255,255,255,.13);border-radius:8px;padding:4px 8px;font:inherit;font-size:12px}
      </style>
      <div class="toast" hidden></div>
      <div class="bx">
        <div class="top" data-a="fold" title="누르면 펼치기 · 접기"><span class="dot"></span><span class="t"><span class="t1">엔젤 입금확인</span><small class="t2">살펴보는 중…</small></span><span class="cnt">입금 0</span><button class="fold" data-a="fold" title="펼치기 · 접기">▾</button></div>
        <div class="bd"></div>
        <div class="lk">
          <details><summary class="mut">방송 서버 연결</summary>
            <div class="mut">후원 콘솔 → 🏦 계좌 입금 추천 → [은행 확장 연결]의 열쇠를 붙여 넣으세요.</div>
            <div class="row"><input type="password" data-k="key" placeholder="열쇠 붙여 넣기" autocomplete="off"><button data-a="savekey">저장</button></div>
            <div class="row"><select data-k="server"><option value="${PROD}">방송 서버 (엔젤컴퍼니.메인.한국)</option><option value="http://127.0.0.1:5289">내 PC 시험 (127.0.0.1:5289)</option></select></div>
            <div class="mut lkmsg"></div>
          </details>
        </div>
      </div>`;
    document.documentElement.appendChild(host);
    ui = { host, root, bx: root.querySelector('.bx'), bd: root.querySelector('.bd'), lk: root.querySelector('.lk'), toast: root.querySelector('.toast') };
    root.addEventListener('click', onUiClick);
    // ⚠️ 열쇠 칸은 상자 몸통(.bd) 밖이다 — 몸통은 조회할 때마다 다시 그려져서, 안에 두면 치던 글자가 지워진다
    loadLink().then((l) => {
      ui.root.querySelector('[data-k=server]').value = l.server;
      ui.root.querySelector('[data-k=key]').placeholder = l.key ? '저장됨 ••••' + l.key.slice(-4) + ' (바꾸려면 새로 붙여 넣기)' : '열쇠 붙여 넣기';
    });
  }

  function esc(s) { return String(s == null ? '' : s).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c])); }

  // 맨 위 상태 한 줄 — 1초마다 이것만 고친다(상자 전체를 다시 그리면 고르던 목록이 닫힌다)
  function status() {
    const f = lastFound;
    const now = Date.now();
    // ⚠️ 표가 보이는데 비밀번호 칸이 있다고 로그아웃으로 보면 안 된다(조회에 계좌 비밀번호를 묻는 화면도 있다)
    if (!f && looksLoggedOut()) return ['로그아웃된 것 같아요 — 다시 로그인해 주세요' + (S.lastOkAt ? ' (마지막 정상 ' + hhmm(S.lastOkAt) + ')' : ''), 'bad'];
    // 끊김 판정 ②: 조회를 누르는데 표가 2분 넘게 그대로(또는 사라짐) — 은행이 조용히 로그아웃시켰거나 화면이 멈춘 것
    if (S.enabled && S.clicks > 0 && S.lastOkAt && now - S.lastOkAt > STALL_MS) {
      return ['조회가 안 돼요 — 표가 ' + dur(now - S.lastOkAt) + ' 넘게 ' + (f ? '안 바뀌어요' : '안 보여요') + '. 은행 화면을 봐 주세요', 'bad'];
    }
    if (!f) return ['거래내역 표를 못 찾았어요. 거래내역조회 화면에서 [조회]를 한 번 눌러 주세요', 'warn'];
    if (!S.enabled) return ['표를 찾았어요 · 자동 조회는 꺼져 있어요', ''];
    const next = Math.max(0, Math.round(((S.lastClickAt || now) + (FAST ? 3 : S.interval) * 1000 - now) / 1000));
    return ['자동 조회 중 · ' + S.interval + '초마다 · 다음 ' + next + '초 뒤', 'ok'];
  }
  // 신호등 바 두 줄 — 윗줄은 status(), 아랫줄은 방송 서버 연결 · 켜 둔 시간. dead = 입금을 못 받고 있는 상태(바 전체가 빨개진다)
  function bar() {
    const [t1, cls] = status();
    const [nt, ncls] = netStatus();
    const dead = cls === 'bad';
    let t2;
    if (dead) t2 = '입금을 못 받는 중' + (S.lastOkAt ? ' · 마지막 정상 ' + hhmm(S.lastOkAt) : '');
    else if (!lastFound) t2 = '거래내역조회 화면에서 [조회]를 한 번 눌러 주세요';
    else if (!S.enabled) t2 = '[자동 조회 켜기]를 누르거나 조종실에서 켜세요';
    else t2 = (net.why === 'ok' ? '방송 서버 ✓ ' + hhmm(net.at).slice(0, 5) : nt) + (S.startedAt ? ' · 켜 둔 지 ' + dur(Date.now() - S.startedAt) : '');
    const barCls = dead ? 'bad' : (cls === 'ok' && ncls && ncls !== 'ok') ? 'warn' : cls;
    // 바 윗줄은 320px 에 들어가게 짧게 — '다음 n초' 는 펼친 몸통(status)에만
    let top = t1;
    if (dead && !lastFound && looksLoggedOut()) top = '은행 로그아웃됨 — 다시 로그인하세요';
    else if (cls === 'ok') top = '자동 조회 중 · ' + S.interval + '초마다';
    return { t1: top, t2, cls: barCls, dead };
  }
  // 신호마다 서버에 실어 보내는 상자 내용 — 조종실 거울이 이걸로 같은 바를 그린다(메모는 40자까지 · 서버가 한 번 더 자른다)
  function snap() {
    const b = bar();
    const f = lastFound;
    return {
      v: VER, enabled: !!S.enabled, interval: S.interval, clicks: S.clicks, lastOkAt: S.lastOkAt || 0, startedAt: S.startedAt || 0,
      dateOk: S.dateOk === undefined ? null : !!S.dateOk, status: b.t1, cls: b.cls, dead: b.dead,
      loggedOut: !f && looksLoggedOut(), rows: f ? f.rows.length : 0, diag: f && !f.rows.length ? (f.diag || '') : '',
      found: S.found.slice(0, 8).map((d) => ({ at: d.at, when: d.when, dep: d.dep, memo: (d.memo || []).join(' · ').slice(0, 40) })),
      log: S.log.slice(0, 6),
    };
  }
  function paintBar() {
    if (!ui) return;
    const b = bar();
    const dot = ui.root.querySelector('.dot');
    dot.className = 'dot ' + b.cls + (dot.classList.contains('pulse') ? ' pulse' : '');
    ui.root.querySelector('.t1').textContent = b.t1;
    ui.root.querySelector('.t2').textContent = b.t2;
    ui.root.querySelector('.cnt').textContent = '입금 ' + S.found.length;
    ui.bx.classList.toggle('dead', b.dead);
  }
  function tick() {
    if (!ui) return;
    paintBar();
    const el = ui.bd.querySelector('.st');
    if (!el) return;
    const [st, cls] = status();
    el.textContent = st;
    el.className = 'st ' + cls;
    const ln = ui.bd.querySelector('.ln');
    if (ln) { const [t2, c2] = netStatus(); ln.textContent = t2; ln.className = 'st ln ' + c2; }
  }
  // 새 입금 — 바 위로 초록 말풍선 7초, 점이 세 번 고동친다
  let toastTimer = null;
  function showToast(d) {
    if (!ui || !d) return;
    const memo = Array.from(new Set(d.memo || []));   // 거래내용 · 예금주가 같은 글자면 한 번만
    ui.toast.innerHTML = '＋ ' + esc(d.dep.toLocaleString()) + '원 · ' + esc(memo.join(' · ') || '(내용 없음)')
      + '<small>후원 콘솔로 보냈어요 · ' + esc(hhmm(d.at)) + '</small>';
    ui.toast.hidden = false;
    const dot = ui.root.querySelector('.dot');
    dot.classList.remove('pulse'); void dot.offsetWidth; dot.classList.add('pulse');
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => { ui.toast.hidden = true; dot.classList.remove('pulse'); }, 7000);
  }

  function render(flash) {
    if (!ui) return;
    paintBar();
    if (flash && S.found.length) showToast(S.found[0]);
    // 접혀 있어도 몸통은 채워 둔다(보이지만 않는다) — 상태 글은 1초마다 그 자리에서 고친다
    ui.bd.style.display = S.folded ? 'none' : '';
    ui.lk.style.display = S.folded ? 'none' : '';
    const f = lastFound;
    const now = Date.now();
    const [st, cls] = status();
    const m = f && f.m;
    const lab = (i) => (f && i >= 0 ? esc(f.labels[i]) : '<span style="color:#ff9a9a">없음</span>');
    const cols = f ? `입금칸 ${lab(m.dep >= 0 ? m.dep : m.amt)} · 잔액칸 ${lab(m.bal)} · 날짜칸 ${lab(m.date)}<br>이름/내용칸 ${m.memo.map((i) => esc(f.labels[i])).join(', ') || '<span style="color:#ff9a9a">없음</span>'} · 지금 ${f.rows.length}줄${f.rows.length ? '' : '<br><span style="color:#ff9a9a">' + esc(f.diag || '') + ' · 제목: ' + f.labels.map(esc).join('|') + '</span>'}` : '';
    const order = (f && f.rows.length >= 2 && !newestFirst(f.rows)
      ? '<div class="st warn">⚠️ 오래된 거래가 위에 있어요. 정렬을 <b>최근순</b>으로 바꿔 주세요 — 새 입금이 다음 쪽으로 밀리면 못 봐요</div>' : '')
      + (S.enabled && S.clicks > 0 && S.dateOk === false
        ? '<div class="st warn">⚠️ 조회 기간 날짜 칸을 못 찾았어요. 자정이 지나면 끝 날짜가 어제로 남아 새 입금이 안 보일 수 있어요 — 이 상자를 캡처해 보내 주세요</div>' : '');
    const deps = S.found.slice(0, 8).map((d) => `<div class="dep"><b>${d.dep.toLocaleString()}원</b><span>${esc(d.memo.join(' · ') || '(내용 없음)')}</span><span class="mut">${esc(d.when || '')}</span><span class="mut">찾은 시각 ${hhmm(d.at)}</span></div>`).join('');
    const up = S.enabled && S.startedAt ? '켜 둔 지 ' + dur(now - S.startedAt) + ' · ' : '';
    const [nt, ncls] = netStatus();
    ui.bd.innerHTML = `
      <div class="st ${cls}">${esc(st)}</div>
      <div class="st ln ${ncls}">${esc(nt)}</div>
      ${order}
      <div class="row">
        <button data-a="toggle" class="${S.enabled ? 'on' : ''}">${S.enabled ? '자동 조회 끄기' : '자동 조회 켜기'}</button>
        <select data-a="interval">${[20, 30, 60].map((s) => `<option value="${s}" ${S.interval === s ? 'selected' : ''}>${s}초마다</option>`).join('')}</select>
        <button data-a="teach" title="자동으로 못 찾을 때 — 누른 뒤 은행 화면의 [조회]를 한 번 누르세요">${teach ? '은행 [조회]를 눌러 주세요…' : '버튼 지정'}</button>
      </div>
      <div class="mut">${up}조회 ${S.clicks}번 · 마지막 정상 ${hhmm(S.lastOkAt)} · 판 ${VER}</div>
      ${cols ? `<div class="mut">${cols}</div>` : ''}
      <div><b>새 입금</b> <span class="mut">(후원 콘솔 '계좌 입금 추천' 칸으로 보내요 — 송출은 거기서)</span></div>
      ${deps || '<div class="mut">아직 없어요. 다른 통장에서 1,000원을 보내 보세요</div>'}
      <details><summary class="mut">기록</summary><ul class="mut">${S.log.slice(0, 12).map((x) => `<li>${esc(x)}</li>`).join('')}</ul></details>
      <div class="row"><button data-a="clear">상자 기록 지우기</button></div>`;
  }

  async function saveLink() {
    const msg = ui.root.querySelector('.lkmsg');
    const inp = ui.root.querySelector('[data-k=key]');
    const server = ui.root.querySelector('[data-k=server]').value;
    const old = await loadLink();
    const key = inp.value.trim() || old.key;
    if (!/^[0-9a-f]{32}$/.test(key)) { msg.textContent = '열쇠 모양이 아니에요 — 후원 콘솔에서 [복사]한 32글자를 그대로 붙여 주세요'; return; }
    await new Promise((res) => { try { chrome.storage.local.set({ [LINKKEY]: { server, key } }, () => res()); } catch (e) { res(); } });
    inp.value = '';
    inp.placeholder = '저장됨 ••••' + key.slice(-4) + ' (바꾸려면 새로 붙여 넣기)';
    msg.textContent = '저장했어요 — 바로 신호를 보내 볼게요. 위 줄이 "방송 서버로 보냄 ✓" 가 되면 연결된 거예요';
    sendDeps([]);
  }

  async function onUiClick(e) {
    const hit = e.target && e.target.closest ? e.target.closest('[data-a]') : null;
    const a = hit && hit.getAttribute('data-a');
    if (!a) return;
    if (a === 'savekey') { await saveLink(); return; }
    S = await load();
    if (a === 'fold') { S.folded = !S.folded; }
    if (a === 'toggle') {
      S.enabled = !S.enabled;
      if (S.enabled) { S.startedAt = Date.now(); S.lastClickAt = 0; note('자동 조회 켬 (' + S.interval + '초마다)'); }
      else note('자동 조회 끔');
    }
    if (a === 'teach') { teach = !teach; }
    if (a === 'clear') { S.found = []; S.log = []; S.clicks = 0; note('시험 기록을 지웠어요'); }
    document.documentElement.setAttribute('data-aw-on', S.enabled ? '1' : '0');
    await save();
    render();
    schedule();
  }
  // 간격 고르기(select 는 click 이 아니라 change 로 온다)
  let selectBound = false;
  function bindSelect() {
    if (selectBound || !ui) return;
    selectBound = true;
    ui.root.addEventListener('change', async (e) => {
      if (!e.target || e.target.getAttribute('data-a') !== 'interval') return;
      S = await load();
      S.interval = parseInt(e.target.value, 10) || 30;
      note('간격 ' + S.interval + '초');
      await save(); render(); schedule();
    });
  }

  // [버튼 지정] — 다음에 은행 화면에서 누르는 것을 [조회] 로 기억한다(누르는 것 자체는 막지 않는다)
  document.addEventListener('click', async (e) => {
    if (!teach || (ui && ui.host.contains(e.target))) return;
    teach = false;
    S = await load();
    S.taught = cssPath(e.target.closest('button, input, a, [role=button]') || e.target);
    note('[조회] 버튼을 기억했어요');
    await save(); render();
  }, true);

  // page_hook.js 가 막아 둔 알림창 내용
  window.addEventListener('message', async (e) => {
    if (e.source !== window || !e.data || !e.data.__aw) return;
    S = await load();
    const msg = norm(e.data.msg);
    note('은행 알림창: ' + msg);
    if (/로그인|세션|만료|종료|로그아웃/.test(msg)) S.logoutAt = Date.now();
    await save(); render();
  });

  /* ─── 시작 ─── */
  let mo = null;
  let ticking = false;
  function startTicking() {
    if (ticking) return;
    ticking = true;
    setInterval(() => { tick(); beat(); }, 1000);   // 바 시계 · 살아 있음 신호(꺼져 있어도 — 조종실이 켤 수 있게)
  }
  async function boot() {
    S = await load();
    if (!S.v4) { S.v4 = 1; S.folded = true; await save(); }   // 0.4 신호등 바 — 처음엔 바만 보인다(누르면 펼침)
    document.documentElement.setAttribute('data-aw-on', S.enabled ? '1' : '0');
    await sleep(1200);
    const f = findTable(document);
    const isTxPage = !!f || (/거래내역/.test(document.body ? document.body.innerText.slice(0, 5000) : '') && !!findButton(document, null, S.taught));
    if (!isTxPage) {
      // 이 틀에는 표가 없다. 자동 조회 중인데 로그인 화면이 떴으면 그것만 알린다(맨 위 틀에서만)
      if (S.enabled && window.top === window && looksLoggedOut()) {
        if (!S.logoutAt) { S.logoutAt = Date.now(); note('로그아웃 감지'); await save(); }
        mountUI(); bindSelect(); render(); startTicking();   // 로그아웃 신호도 조종실에 간다
      }
      return;
    }
    mountUI();
    bindSelect();
    await scan('load');
    // 화면 일부만 바꿔 끼우는 은행이면 새로고침 없이 표가 바뀐다 — 바뀌면 0.8초 뒤 다시 읽는다
    let deb = null;
    mo = new MutationObserver((list) => {
      if (list.every((r) => ui && ui.host.contains(r.target))) return;
      clearTimeout(deb);
      deb = setTimeout(() => scan('change'), 800);
    });
    mo.observe(document.body, { childList: true, subtree: true, characterData: true });
    schedule();
    startTicking();
  }
  boot();
})();
