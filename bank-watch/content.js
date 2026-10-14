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
    return { when, dep, wd, kind, memo, cols, raw: t.join('|') };
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
    if (typeof module !== 'undefined') module.exports = { norm, toWon, hashStr, gridLabels, colMap, rowFrom, keyRows, judge, newestFirst, depPayload, isRefund };
    return;
  }

  /* ══════════ 은행 화면 쪽 ══════════ */

  // 🧪 가짜 은행 화면(내 PC 의 시험 페이지)에서만 3초 간격 — 진짜 은행 주소에서는 절대 안 켜진다
  const FAST = /^(127\.0\.0\.1|localhost)$/.test(location.hostname) && /awfast=1/.test(location.search);
  const KEY = 'aw1';
  const DEF = {
    enabled: false, interval: 30, taught: '', seen: {}, found: [], baseAt: 0, baseSig: '',
    clicks: 0, lastClickAt: 0, startedAt: 0, lastOkAt: 0, logoutAt: 0, log: [], folded: false,
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

  function headerRows(table) {
    let rows = table.tHead ? Array.from(table.tHead.rows) : [];
    if (!rows.length) {
      for (const r of Array.from(table.rows)) {
        const c = Array.from(r.cells);
        if (c.length && c.every((x) => x.tagName === 'TH')) rows.push(r); else break;
      }
    }
    return rows.map((r) => Array.from(r.cells).map((c) => ({ text: c.innerText || c.textContent, colspan: c.colSpan, rowspan: c.rowSpan })));
  }
  function bodyRows(table, nHead) {
    const trs = table.tBodies && table.tBodies.length
      ? Array.from(table.tBodies).reduce((a, b) => a.concat(Array.from(b.rows)), [])
      : Array.from(table.rows).slice(nHead);
    return trs.map((r) => Array.from(r.cells))
      .filter((c) => c.length >= 3 && c.some((x) => x.tagName === 'TD'))
      .map((c) => c.map((x) => x.innerText || x.textContent));
  }

  /* 거래내역 표 찾기. ⚠️ 은행 화면은 머리줄과 몸통을 **서로 다른 표**로 나눠 두기도 한다(위 고정 · 아래 스크롤).
     머리만 있고 몸통이 없으면, 뒤따르는 표 중 칸 수가 같은 것을 몸통으로 쓴다. */
  function findTable(doc) {
    const tables = Array.from(doc.querySelectorAll('table'));
    let best = null;
    tables.forEach((tb, idx) => {
      const hr = headerRows(tb);
      if (!hr.length) return;
      const labels = gridLabels(hr);
      const m = colMap(labels);
      if (!m.ok) return;
      let body = bodyRows(tb, hr.length);
      let bodyEl = tb;
      if (!body.length) {
        for (let j = idx + 1; j < Math.min(tables.length, idx + 4); j++) {
          const b = bodyRows(tables[j], 0).filter((c) => c.length === labels.length);
          if (b.length) { body = b; bodyEl = tables[j]; break; }
        }
      }
      body = body.filter((c) => c.length === labels.length || c.length === labels.length - 1);
      const score = (m.dep >= 0 ? 3 : 0) + (m.bal >= 0 ? 2 : 0) + (m.date >= 0 ? 2 : 0) + m.memo.length + Math.min(body.length, 20) / 20;
      if (!best || score > best.score) best = { el: tb, bodyEl, labels, m, cells: body, score };
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
     ⚠️ 미래 날짜거나 날짜 모양이 아니면 손대지 않는다. 년 · 월 · 일이 따로인 고르기 칸은 아직 모른다(시험으로 확인). */
  const pad2 = (n) => String(n).padStart(2, '0');
  function rollEndDate(doc, btn) {
    const re = /^(\d{4})([.\-/]?)(\d{2})\2(\d{2})$/;
    let ins = Array.from(doc.querySelectorAll('input')).filter((i) => re.test((i.value || '').trim()) && visible(i));
    if (!ins.length) return { found: false };
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
    try {
      chrome.runtime.sendMessage({ t: 'aw-send', deposits, note: what }, (res) => {
        if (chrome.runtime.lastError || !res) { net = { why: 'ext', at: net.at, queued: net.queued }; tick(); return; }
        net = res.ok ? { why: 'ok', at: res.at, queued: res.queued } : { why: res.why, code: res.code, at: net.at, queued: res.queued };
        if (deposits.length && res.ok) note('방송 서버로 보냄 — 입금 ' + deposits.length + '건');
        tick();
      });
    } catch (e) { net = { why: 'ext', at: 0, queued: 0 }; }
  }
  // 30초에 한 번 '살아 있음' — 후원 콘솔이 '은행 확장 연결됨 · n초 전' 을 보여준다. 못 보낸 입금도 이때 다시 간다
  function beat() { if (lastFound && Date.now() - lastBeat > 25000) sendDeps([]); }
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
    const sig = f.labels.join('|');
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
    const btn = findButton(document, lastFound && lastFound.el, S.taught);
    S.lastClickAt = Date.now();
    if (!btn) {
      note('조회 버튼을 못 찾았어요 — [버튼 지정]으로 알려 주세요');
      await save(); render(); schedule(); return;
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
    schedule();                             // 화면이 새로 뜨면 이 타이머는 사라지고 boot 가 다시 건다
  }

  /* ─── 상자(그림자 DOM — 은행 화면 글꼴 · 색에 안 섞이게) ─── */
  function mountUI() {
    if (ui) return;
    const host = document.createElement('div');
    host.id = 'angel-bankwatch';
    host.style.cssText = 'position:fixed;right:12px;bottom:12px;z-index:2147483647;';
    const root = host.attachShadow({ mode: 'open' });
    root.innerHTML = `
      <style>
        .bx{width:320px;font:13px/1.5 'Malgun Gothic',sans-serif;color:#e8ecf3;background:#141821f2;border:1px solid #3a4252;border-radius:10px;box-shadow:0 6px 24px #0008;overflow:hidden}
        .hd{display:flex;align-items:center;gap:6px;padding:8px 10px;background:#1d2330;font-weight:700}
        .hd .sp{flex:1}
        .hd button{background:none;border:0;color:#9aa6bb;cursor:pointer;font-size:14px}
        .bd{padding:8px 10px;display:grid;gap:6px;max-height:60vh;overflow:auto}
        .st{padding:6px 8px;border-radius:6px;background:#22324a}
        .st.ok{background:#173b2a}.st.bad{background:#4a1f1f}.st.warn{background:#4a3b17}
        .row{display:flex;gap:6px;flex-wrap:wrap;align-items:center}
        .row button,.row select{background:#2a3242;color:#e8ecf3;border:1px solid #445066;border-radius:6px;padding:4px 8px;cursor:pointer;font:inherit}
        .row button.on{background:#2f6f4a;border-color:#3f9a66}
        .mut{color:#9aa6bb;font-size:12px}
        .dep{display:grid;grid-template-columns:auto 1fr;gap:2px 8px;padding:6px 8px;border-radius:6px;background:#1b2a1f}
        .dep b{color:#7ee2a8}
        .flash{animation:fl 1.2s ease 2}
        @keyframes fl{0%,100%{box-shadow:0 6px 24px #0008}50%{box-shadow:0 0 0 4px #7ee2a8}}
        ul{margin:0;padding-left:16px}
        .lk{padding:0 10px 8px}
        .lk .row{margin-top:6px}
        .lk input{flex:1;min-width:0;background:#0f131b;color:#e8ecf3;border:1px solid #445066;border-radius:6px;padding:4px 8px;font:inherit}
      </style>
      <div class="bx">
        <div class="hd">🏦 엔젤 입금확인 <span class="mut">0.2</span><span class="sp"></span><button data-a="fold" title="접기">▾</button></div>
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
    ui = { host, root, bx: root.querySelector('.bx'), bd: root.querySelector('.bd'), lk: root.querySelector('.lk') };
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
    if (!f) return ['거래내역 표를 못 찾았어요. 거래내역조회 화면에서 [조회]를 한 번 눌러 주세요', 'warn'];
    if (!S.enabled) return ['표를 찾았어요 · 자동 조회는 꺼져 있어요', ''];
    const next = Math.max(0, Math.round(((S.lastClickAt || now) + (FAST ? 3 : S.interval) * 1000 - now) / 1000));
    return ['자동 조회 중 · ' + S.interval + '초마다 · 다음 ' + next + '초 뒤', 'ok'];
  }
  function tick() {
    if (!ui || S.folded) return;
    const el = ui.bd.querySelector('.st');
    if (!el) return;
    const [st, cls] = status();
    el.textContent = st;
    el.className = 'st ' + cls;
    const ln = ui.bd.querySelector('.ln');
    if (ln) { const [t2, c2] = netStatus(); ln.textContent = t2; ln.className = 'st ln ' + c2; }
  }

  function render(flash) {
    if (!ui) return;
    if (S.folded) { ui.bd.style.display = 'none'; ui.lk.style.display = 'none'; return; }
    ui.bd.style.display = '';
    ui.lk.style.display = '';
    const f = lastFound;
    const now = Date.now();
    const [st, cls] = status();
    const m = f && f.m;
    const lab = (i) => (f && i >= 0 ? esc(f.labels[i]) : '<span style="color:#ff9a9a">없음</span>');
    const cols = f ? `입금칸 ${lab(m.dep >= 0 ? m.dep : m.amt)} · 잔액칸 ${lab(m.bal)} · 날짜칸 ${lab(m.date)}<br>이름/내용칸 ${m.memo.map((i) => esc(f.labels[i])).join(', ') || '<span style="color:#ff9a9a">없음</span>'} · 지금 ${f.rows.length}줄` : '';
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
      <div class="mut">${up}조회 ${S.clicks}번 · 마지막 정상 ${hhmm(S.lastOkAt)}</div>
      ${cols ? `<div class="mut">${cols}</div>` : ''}
      <div><b>새 입금</b> <span class="mut">(후원 콘솔 '계좌 입금 추천' 칸으로 보내요 — 송출은 거기서)</span></div>
      ${deps || '<div class="mut">아직 없어요. 다른 통장에서 1,000원을 보내 보세요</div>'}
      <details><summary class="mut">기록</summary><ul class="mut">${S.log.slice(0, 12).map((x) => `<li>${esc(x)}</li>`).join('')}</ul></details>
      <div class="row"><button data-a="clear">상자 기록 지우기</button></div>`;
    if (flash) { ui.bx.classList.remove('flash'); void ui.bx.offsetWidth; ui.bx.classList.add('flash'); }
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
    const a = e.target && e.target.getAttribute && e.target.getAttribute('data-a');
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
  async function boot() {
    S = await load();
    document.documentElement.setAttribute('data-aw-on', S.enabled ? '1' : '0');
    await sleep(1200);
    const f = findTable(document);
    const isTxPage = !!f || (/거래내역/.test(document.body ? document.body.innerText.slice(0, 5000) : '') && !!findButton(document, null, S.taught));
    if (!isTxPage) {
      // 이 틀에는 표가 없다. 자동 조회 중인데 로그인 화면이 떴으면 그것만 알린다(맨 위 틀에서만)
      if (S.enabled && window.top === window && looksLoggedOut()) {
        if (!S.logoutAt) { S.logoutAt = Date.now(); note('로그아웃 감지'); await save(); }
        mountUI(); bindSelect(); render();
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
    setInterval(() => { if (S && S.enabled) { tick(); beat(); } }, 1000);   // '다음 n초 뒤' 시계 · 살아 있음 신호
  }
  boot();
})();
