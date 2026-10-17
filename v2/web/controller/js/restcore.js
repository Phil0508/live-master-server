/* ☕ 휴식 모드 — 계산만(화면 안 만짐 → node 로 검사: v2/tests/test_rest_mode.py · tests/js/rest_core_test.mjs).
   대표님 10-17 — 자리를 비운 사이 계좌 입금 · 확인할 후원(보류)이 오면 돌아와서 바로 알아보게.
   ⚠️ 소리 · 진동 · 알림 권한 없음. 눈으로만(가장자리 초록 깜빡 · 가운데 카드 · 탭 제목).
   ⚠️ 입금자 실명(holder)은 쓰지 않는다 — 메모에서 나눈 추정 닉네임 · 금액만. 이름이 실명일 수 있는 경우(메모 없음 · 이름만)는 이름을 빼고 금액만. */

export const REST_KEY = 'lm2_rest';           // 이 기기(브라우저)마다 — '1' 이면 켬
export const MAX_LINES = 5;                   // 카드에 줄로 보여 줄 건수(나머지는 '외 N건')

/** 켜 둔 상태 읽기 — 개인 창 · 막힌 저장소면 끔 */
export function readRest(storage) {
    try { return !!storage && storage.getItem(REST_KEY) === '1'; } catch (e) { return false; }
}

/** 켜고 끄기 기억 — 못 적어도(개인 창) 이번 화면에서는 그대로 돈다. 적었으면 true */
export function writeRest(storage, on) {
    try { storage.setItem(REST_KEY, on ? '1' : '0'); return true; } catch (e) { return false; }
}

const won = n => Math.max(0, Math.round(Number(n) || 0)).toLocaleString('ko-KR') + '원';
// 메모가 없거나 이름만 있으면 그 이름이 입금자 실명일 수 있다(BANK_HOW no_memo · name_only)
const MAYBE_REAL = { no_memo: 1, name_only: 1, empty: 1 };

/** 카드에 써도 되는 이름(추정 닉네임) — 실명일 수 있으면 '' */
export function safeBankName(it) {
    if (!it) return '';
    const nm = String(it.name || '').trim();
    if (!nm || MAYBE_REAL[it.how]) return '';
    const holder = String(it.holder || '').trim();
    if (holder && nm.replace(/\s+/g, '') === holder.replace(/\s+/g, '')) return '';
    return nm;
}

/** 계좌 입금 한 건 → 카드 줄 */
export function bankLine(it) {
    const nm = safeBankName(it);
    return {
        kind: 'bank',
        id: 'bank:' + String((it && it.id) || ''),
        title: '🏦 계좌 입금 ' + won(it && it.amount) + (nm ? ' · ' + nm + '(추정)' : ''),
        sub: nm ? '후원 콘솔에서 [채우기] → 송출' : '이름은 후원 콘솔 카드에서 확인 → [채우기] → 송출',
    };
}

/** 확인할 후원(보류) 한 건 → 카드 줄 (투네이션 닉네임은 공개 이름이라 그대로) */
export function holdLine(it) {
    const why = it && it.auto && Array.isArray(it.auto.hold) && it.auto.hold.length ? String(it.auto.hold[0]) : '';
    return {
        kind: 'hold',
        id: 'hold:' + String((it && it.id) || ''),
        title: '🙋 확인할 후원 · ' + String((it && it.name) || '익명') + ' ' + won(it && it.amount),
        sub: why ? '보류 까닭: ' + why : '대기함에서 확인해 주세요',
    };
}

/** 은행 확장이 읽어 온 것(/api/bank/ext)에서 '새 입금' 을 고른다.
 *  st = {at, ids, n} (처음엔 null) — 처음 읽을 땐 알리지 않는다(예전 것이 쏟아지지 않게).
 *  가장 새 카드가 '본 적 없고 · 지금까지 본 것보다 늦게 들어온 것' 일 때만 알린다
 *  (맨 위 카드를 처리하면 그 밑 카드가 맨 위로 올라오는데, 그건 새 입금이 아니다).
 *  건수 = 미처리 수가 늘어난 만큼(한 번에 여러 건이 와도) — 최소 1.  돌려받는 값 {st, add, line} */
export function bankTrack(st, d) {
    const it = d && d.newest;
    const n = Math.max(0, Number(d && d.new) || 0);
    const at = Number(it && it.at) || 0;
    const id = String((it && it.id) || '');
    if (!st) return { st: { at, ids: id ? [id] : [], n }, add: 0, line: null };
    const seen = st.ids.indexOf(id) >= 0;
    if (!id || seen || at < st.at) return { st: { at: Math.max(st.at, at), ids: st.ids, n }, add: 0, line: null };
    const add = Math.max(1, n - st.n);
    return { st: { at: Math.max(st.at, at), ids: [id, ...st.ids].slice(0, 200), n }, add, line: bankLine(it) };
}

/** 대기함 보류 카드들에서 '새로 생긴 것' 을 고른다. seen = 본 id 묶음(처음엔 null — 그때 있던 것은 알리지 않는다).
 *  돌려받는 값 {seen, fresh: [카드…]} */
export function holdTrack(seen, cards, paused) {
    // 자동 진행이 '끔' 인 동안은 heldCards 가 빈 목록을 준다 — 그때 잊어버리면 다시 켤 때 남아 있던 보류가 전부 '새것' 으로 울린다.
    // 그래서 끔인 동안은 본 것을 그대로 둔다(알리지도 않는다).
    if (paused) return { seen, fresh: [] };
    const ids = (cards || []).map(c => String(c && c.id));
    if (!seen) return { seen: ids.slice(), fresh: [] };
    const fresh = (cards || []).filter(c => seen.indexOf(String(c && c.id)) < 0);
    // 처리돼 빠진 것은 잊는다(같은 번호가 다시 보류되면 또 알린다) — 지금 있는 것만 기억
    return { seen: ids.slice(), fresh };
}

/** 쌓인 알림 → 카드 · 탭 제목 글자. alert = {bank, hold, lines:[최근 먼저]} */
export function countText(a) {
    const p = [];
    if (a.bank) p.push('입금 ' + a.bank + '건');
    if (a.hold) p.push('확인할 후원 ' + a.hold + '건');
    return p.join(' · ');
}

export function titleText(a, base, on) {
    if (!on || !(a.bank || a.hold)) return base;
    return '🔔 ' + countText(a) + ' · ' + base;
}

/** 새 알림을 쌓는다(최근 것이 맨 앞) — 돌려받는 새 alert */
export function pushAlert(a, line, add) {
    const k = line.kind === 'bank' ? 'bank' : 'hold';
    const out = { bank: a.bank, hold: a.hold, lines: [line, ...a.lines.filter(l => l.id !== line.id)].slice(0, 50) };
    out[k] += Math.max(1, Number(add) || 1);
    return out;
}

export function emptyAlert() {
    return { bank: 0, hold: 0, lines: [] };
}

/** 카드에 그릴 것 — 큰 글자 한 줄(가장 최근) · 그 밖 줄(최대 MAX_LINES-1) · 남은 수 · 머리 글자 */
export function cardView(a) {
    const total = a.bank + a.hold;
    const [first, ...rest] = a.lines;
    const more = rest.slice(0, MAX_LINES - 1);
    return {
        head: total > 1 ? '🔔 새 알림 ' + total + '건 — ' + countText(a) : '🔔 새 알림',
        title: first ? first.title : '',
        sub: first ? first.sub : '',
        rest: more.map(l => l.title),
        left: Math.max(0, a.lines.length - 1 - more.length),
    };
}
