/* 🏦 계좌 입금 — 후원 콘솔 '계좌 입금 추천' 칸 · 머리줄 '계좌' 칩 · 계좌 띠 · 시스템 탭 거울이 같이 쓰는 계산.
   ⚠️ 화면(document)을 만지지 않는다 — node 로 그대로 불러 검사한다(v2/tests/test_bank_js.py).
   옛 manual_send.html(BANK_HOW · bankAgo · bankClock · renderBankLink · bankFill/bankMarkUsed)과
   옛 controller.html(bkxJudge · bkxPaint · bankNewStrip)의 계산을 그대로 옮겼다. */

/** 메모를 어떻게 나눴나 — 카드의 작은 딱지(글자, 색).
 *  10-17 새 순서(서버 bank_memo.smart_split): learned(배운 짝) → known_name(지난 기록) → player_strip(선수 이름 떼기) → 옛 것 */
export const BANK_HOW = {
    learned: ['✓ 배운 짝', 'ok'], known_name: ['✓ 지난 기록', 'ok'],
    player_strip: ['선수 이름 떼고 남은 말 — 확인', 'warn'],
    known: ['✓ 예전 닉네임', 'ok'], first: ['첫 낱말을 닉네임으로 — 확인', 'warn'], ai: ['AI 가 나눔 — 확인', 'warn'],
    player_cut: ['선수 이름 앞을 닉네임으로 — 확인', 'warn'], message: ['닉네임 없음 — 할 말만', 'warn'], name_only: ['이름만 — 실명일 수 있어요', 'warn'],
    no_memo: ['메모 없이 보냄 — 입금자명', 'warn'], empty: ['메모 없음', 'warn'],
};

/** 몇 초 전 → '방금' · '12초 전' · '3분 전' · '2시간 전' */
export function bankAgo(sec) {
    sec = Math.max(0, Math.round(sec || 0));
    if (sec < 10) return '방금';
    if (sec < 60) return sec + '초 전';
    if (sec < 3600) return Math.floor(sec / 60) + '분 전';
    return Math.floor(sec / 3600) + '시간 전';
}

/** 은행이 적은 시각 '2026.10.14 19:01:02' → '19:01' (없으면 '') */
export function bankClock(it) {
    const m = String((it && it.when) || '').match(/(\d{1,2}):(\d{2})(?::\d{2})?\s*$/);
    return m ? m[1].padStart(2, '0') + ':' + m[2] : '';
}

/** 카드 한 장에 그릴 것(글자만) — 화면 쪽은 이것을 h() 로 옮겨 적기만 한다 */
export function cardView(it, nowSec) {
    const how = BANK_HOW[it.how] || ['', ''];
    let tgt = null;
    if (it.target) tgt = { text: '→ ' + it.target + ' ＋? 예상', title: it.target_why || '' };
    else if (it.ai === 'pending' && it.message) tgt = { text: '예상 중…', title: '' };
    const raw = [];
    if (it.memo) raw.push('메모 원문: ' + it.memo);
    if (it.holder && it.holder !== it.name) raw.push('예금주 ' + it.holder);
    return {
        amount: Number(it.amount) || 0,
        clock: bankClock(it),
        ago: bankAgo(nowSec - (Number(it.at) || 0)),
        phone: it.source === 'phone',
        name: it.name || '',
        message: it.message || '',
        how: how[0] ? { text: how[0], cls: how[1] } : null,
        target: tgt,
        raw: raw.join(' · '),
    };
}

/** 후원 콘솔 머리의 '은행 확장 연결됨 · 방금' 칩(옛 renderBankLink) — {cls: ''|'ok'|'stale', text} */
export function linkChip(b) {
    const L = (b && b.link) || {};
    const best = [L.web, L.phone].filter(Boolean).sort((a, c) => a.age_sec - c.age_sec)[0];
    if (!b || !b.key_set) return { cls: '', text: '은행 확장 연결 전 — 오른쪽 [은행 확장 연결]' };
    if (!best) return { cls: '', text: '은행 확장 소식 없음' };
    if (best.age_sec < 90) return { cls: 'ok', text: '은행 확장 연결됨 · ' + bankAgo(best.age_sec) + (best.note ? ' · ' + best.note : '') };
    return { cls: 'stale', text: '은행 확장 소식 끊김 · 마지막 ' + bankAgo(best.age_sec) };
}

/* ── 🪞 은행 확장 거울 (옛 controller.html bkxJudge) ── */
export const EXT_DEAD_SEC = 90;              // 신호가 이만큼 없으면 끊김(빨간 띠)
export const EXT_OFF_SEC = 3 * 3600;         // 3시간 넘게 조용하면 '꺼짐' — 보채지 않는다(칩도 숨김)
export const NEW_BAND_MS = 25000;            // 새 입금 초록 띠는 25초 뒤 사라진다

function hhmm(ms) {
    if (!ms) return '-';
    const d = new Date(ms);
    return String(d.getHours()).padStart(2, '0') + ':' + String(d.getMinutes()).padStart(2, '0');
}
function dur(ms) {
    const m = Math.floor(ms / 60000);
    return m >= 60 ? Math.floor(m / 60) + '시간 ' + (m % 60) + '분' : m + '분';
}
export { hhmm as bankHHMM };

/** 확장이 어떤 상태인가 — k: none(연결 전) · off(3시간 조용) · dead(끊김) · idle(꺼짐) · warn · ok */
export function judgeExt(d, nowMs) {
    if (!d || !d.key_set) return { k: 'none', t1: '은행 확장 연결 전', t2: '후원 콘솔 [은행 확장 연결]에서 열쇠를 넣으세요' };
    const w = d.link && d.link.web;
    if (!w) return { k: 'none', t1: '은행 확장 소식 없음', t2: '스튜디오 PC에서 확장을 켜면 여기 떠요' };
    const st = w.state || {};
    if (w.age_sec > EXT_OFF_SEC) return { k: 'off', t1: '은행 확장 꺼짐', t2: '마지막 신호 ' + bankAgo(w.age_sec) };
    if (w.age_sec > EXT_DEAD_SEC) return { k: 'dead', dead: true, t1: '은행 확장 끊김 · 신호 없음 ' + bankAgo(w.age_sec).replace(' 전', ''), t2: '스튜디오 PC 크롬 · 은행 화면을 확인하세요' };
    if (st.dead) return { k: 'dead', dead: true, t1: st.status || '은행 로그아웃됨', t2: '스튜디오 PC에서 다시 로그인하세요' + (st.lastOkAt ? ' · 마지막 정상 ' + hhmm(st.lastOkAt) : '') };
    if (!st.enabled) return { k: 'idle', t1: st.status || '자동 조회 꺼짐', t2: '[자동 조회 켜기]를 누르면 25초 안에 켜져요' };
    return {
        k: st.cls === 'warn' ? 'warn' : 'ok', t1: st.status || '자동 조회 중',
        t2: '신호 ' + bankAgo(w.age_sec) + ' · 조회 ' + (st.clicks || 0) + '번' + (st.startedAt ? ' · 켜 둔 지 ' + dur((nowMs || Date.now()) - st.startedAt) : ''),
    };
}

/** 단계 → 머리줄 점 색(alarm.js 의 data-lv 와 같은 이름) */
export function extLevel(j) {
    return j.k === 'dead' ? 'bad' : j.k === 'warn' ? 'warn' : j.k === 'ok' ? 'ok' : 'none';
}

/** 머리줄 '계좌' 칩 — 안 쓰는 동안(연결 전 · 3시간 조용)은 숨긴다. 끊김은 색으로만(밑의 빨간 띠가 글로 말한다), 글자엔 미처리 수만 */
export function chipView(j, n) {
    n = Number(n) || 0;
    return {
        hidden: j.k === 'none' || j.k === 'off',
        lv: extLevel(j),
        text: '계좌' + (n && j.k !== 'dead' ? ' ' + n : ''),
        title: j.t1 + ' — ' + j.t2 + (n ? ' · 미처리 ' + n + '건' : ''),
    };
}

/** 빨간 띠(끊김) 글자 — 끊김이 아니면 null */
export function deadBand(j) {
    return j.dead ? { t: '⚠ ' + j.t1 + ' — 계좌 입금을 못 받고 있어요', s: j.t2 } : null;
}

/** 초록 띠(새 입금) 글자 */
export function newBand(it, n) {
    const nm = it.name || it.holder || '이름 없음';
    return {
        t: '🏦 계좌 입금 ' + Number(it.amount || 0).toLocaleString('ko-KR') + '원 · ' + nm + (it.message ? ' 「' + it.message + '」' : ''),
        s: (n > 1 ? '미처리 ' + n + '건 · ' : '') + '후원 콘솔에서 [채우기] → 송출',
    };
}

/** 새 입금을 알릴까 — 처음 읽을 땐 알리지 않는다(예전 것이 쏟아지지 않게). 그 뒤 가장 새 카드가 바뀌면 알린다.
 *  known: 지금까지 본 가장 새 카드 번호(null = 아직 한 번도 안 읽음). 돌려받는 값: {known, show} */
export function newestCheck(known, id) {
    if (known === null || known === undefined) return { known: id || '', show: false };
    if (id && id !== known) return { known: id, show: true };
    return { known, show: false };
}

const CMD_NAMES = { enable: '켜기/끄기', interval: '간격', rebase: '기준 다시 잡기', press: '지금 조회' };
/** 기다리는 명령 글자 */
export function pendingText(pend) {
    return pend && pend.length ? '보낸 명령 기다리는 중: ' + pend.map(c => CMD_NAMES[c.t] || c.t).join(' · ') + ' — 확장이 25초 안에 받아요' : '';
}

/** 거울 경고 줄 */
export function extWarns(st, hasLink) {
    const out = [];
    if (st.dateOk === false) out.push('조회 기간 날짜 칸을 못 찾았어요 — 자정 뒤 입금이 안 보일 수 있어요');
    if (hasLink && st.rows === 0 && st.diag) out.push('표를 못 읽어요: ' + st.diag);
    return out;
}

/** 조종실 → 확장 명령 몸통 — enable 은 지금과 반대로 */
export function extCmdBody(t, v, st) {
    const body = { t, source: 'web' };
    if (t === 'enable') body.on = !(st && st.enabled);
    if (t === 'interval') body.sec = parseInt(v, 10);
    return body;
}

/* ── [채우기] → [송출] — '장부 기록' 체크를 원래대로 (옛 50878d1) ──
   ⚠️ [채우기] 는 장부 체크를 켠다. 채우기 전 상태를 기억했다가 송출 · 비우기 · 숨기기 · 다른 화면에서 처리된 뒤 되돌린다.
      안 그러면 켜진 채 남아, 다음에 '재생만' 하려던 수동 송출이 진짜 후원으로 장부 · 대기함에 들어간다(10-14 눌러 보다 찾음).
   돌려받는 값: 장부 체크를 이 값으로 맞춰라(true/false) · null = 그대로 둬라 */
export function makePick() {
    let pick = null;
    const api = {
        get: () => pick,
        /** 카드 하나 고르기 — 이미 고른 게 있으면 그때 기억한 '원래 상태' 를 그대로 이어 간다 */
        fill(it, ledgerNow) {
            const prevLedger = pick ? pick.prevLedger : !!ledgerNow;
            pick = { id: it.id, amount: Number(it.amount) || 0, prevLedger };
            return true;
        },
        /** 고른 것 놓기(송출 끝 · 비우기) */
        release() {
            if (!pick) return null;
            const v = !!pick.prevLedger;
            pick = null;
            return v;
        },
        /** 그 카드를 숨겼으면 놓는다 */
        releaseIf(id) { return pick && pick.id === id ? api.release() : null; },
        /** 다른 화면에서 송출 · 숨김 — 목록에서 사라졌으면 놓는다 */
        releaseIfGone(ids) { return pick && !(ids || []).includes(pick.id) ? api.release() : null; },
    };
    return api;
}

/** 송출 이름 — 계좌 입금에서 채웠는데 닉네임을 비워 두면 '수동송출' 이 아니라 '익명'(순위에서도 빠진다) */
export function sendName(typed, pick) {
    return String(typed || '').trim() || (pick ? '익명' : '수동송출');
}

/** 장부 번호(tx_id) 앞부분 — 계좌 입금에서 채운 것은 그 입금 번호를 쓴다(두 번 눌러도 장부의 tx_id 검사가 한 번만 넣는다) */
export function txBase(pick, stamp) {
    return pick ? 'manual_bank_' + pick.id : 'manual_' + stamp;
}

/** 후원 콘솔 탭 배지 — 아직 안 쓴 계좌 입금 수(비공개 조각 bank.new) */
export function bankBadge(slices) {
    const n = Number(((slices || {}).bank || {}).new) || 0;
    return n ? '🏦 ' + n : '';
}
