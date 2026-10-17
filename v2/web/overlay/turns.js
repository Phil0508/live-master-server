/* 🚦 가운데 차례 규칙 — 후원 카드 · 시그니처 · 출연진 전광판이 '지금 누가 가운데에 설까' 를 정한다.
   화면(DOM)은 만지지 않는다 — 순수 함수만(node 로 검사한다: v2/tests/js/ovcard_check.mjs).

   ① 후원 카드 ↔ 시그니처(10-17 v2ov/card)
      옛 사고: 시그니처가 가운데 떠 있는 동안 들어온 일반 후원 카드가 시그 카드(z50) 밑(z40)에 깔려 안 보였다.
      또 시그니처는 '카드가 떠 있거나 줄이 있으면' 기다려서, 후원이 몰리면 시그가 카드 뒤로 계속 밀렸다.
      지금 규칙(cardTurn):
        - 카드가 떠 있다(사라지는 0.4초 포함)            → 'wait'   (그대로 기다린다)
        - 시그가 가운데에 있다(줄어들기 전 · 'OO업' · 전용 연출 · 계엄령 경보) → 'center' (시그가 비키면 다시 본다)
        - 시그가 틀 차례인데 카드 때문에 기다리는 중      → 'yield'  (새 카드를 꺼내기 전에 시그에 차례를 넘긴다)
        - 줄에 카드가 있다 → 'show' / 없다 → 'idle'
      ⚠️ 교착 금지: 시그는 '떠 있는 카드' 만 기다리고(줄 선 카드는 안 기다린다), 카드는 '가운데에 있는 시그' 만 기다린다.
         둘이 동시에 서로를 기다리는 때가 없다 — 시그가 가운데에 서려면 이미 시작했어야 하고, 시작한 시그는 카드를 안 기다린다.

   ② 다시 붙은 방송판의 지난 카드(pendingCards) — 서버 popup.recent(최근 카드 알림 몇 개, id 와 함께)에서
      아직 안 본 것 · 30초 안의 것만 오래된 순서로.
      🔄 새로 고침(F5 · OBS '새로 고침')은 기억(seen)이 날아간다 — 띄운 카드 열쇠를 이 창의 sessionStorage 에 적어 두고(addShown)
         다시 읽어 seen 에 넣는다. 안 그러면 30초 안의 카드가 몇 장씩 또 뜬다(옛 것은 한 칸이라 한 장이었다).
         localStorage 는 안 쓴다 — 같은 브라우저의 다른 방송판 창(OBS 소스 둘)이 서로의 카드를 지워 버린다.

   ③ 출연진 전광판(?only=sig, sigDispShow) — 방송판이 실제로 튼 것(queue.items[0].started — 서버가 아는 '지금 트는 것')을 따른다.
      신호가 없으면(옛 방송판 · 방송판이 안 켜짐) 멈춤 · play_after(서버 시계)가 지나고 STARTED_GRACE_MS 를 더 기다린 뒤에 띄운다. */

export const STARTED_GRACE_MS = 15000;     // 방송판 '시작' 신호를 기다리는 한도 — 넘으면 신호 없이도 전광판에 띄운다

/* 후원 카드가 다음에 할 일 — 'wait' · 'center' · 'yield' · 'show' · 'idle' */
export function cardTurn(s) {
    s = s || {};
    if (s.busy) return 'wait';
    if (s.sigCenter) return 'center';
    if (s.sigWants) return 'yield';
    return (Number(s.queued) || 0) > 0 ? 'show' : 'idle';
}

/* 시그니처가 가운데를 붙잡는 시간(ms, 시작부터) — 줄어드는 때(전용 연출이 있으면 그 뒤) · 'OO업' 배너 · 계엄령 경보 중 가장 늦은 것 */
export function centerHoldMs(shrinkAt, bannerMs, warnMs) {
    const n = x => { const v = Number(x); return isFinite(v) && v > 0 ? v : 0; };
    return Math.max(n(shrinkAt), n(bannerMs), n(warnMs));
}

/* 시그니처 맨 앞이 지금 시작할 수 있나(카드 사정은 빼고) — 멈춤 아님 · 이미 다 튼 것 아님 · play_after(서버 시계) 지남 */
export function sigDue(head, q, now, done) {
    if (!head) return false;
    if (q && q.paused) return false;
    if (done) return false;
    return (Number(head.play_after) || 0) <= (Number(now) || 0);
}

/* 다시 붙었을 때 띄울 지난 카드 — list 는 오래된 순. seen(Set)에 없는 것 · at 이 freshMs 안 · 시그니처가 걸린 것(sig) 아님.
   돌려주는 것: { fresh: [띄울 것…], keys: [이번에 본 열쇠 전부] } — 부르는 쪽이 keys 를 seen 에 넣는다 */
export function pendingCards(list, seen, now, freshMs) {
    const fresh = [], keys = [];
    (Array.isArray(list) ? list : []).forEach(d => {
        if (!d || typeof d !== 'object') return;
        const key = cardKey(d);
        if (!key || keys.includes(key)) return;
        keys.push(key);
        if (seen && seen.has(key)) return;
        const at = Number(d.at) || 0;
        if (!(at > 0 && (Number(now) || 0) - at < (Number(freshMs) || 0))) return;
        if (d.sig) return;                       // 시그니처가 걸린 후원 — 카드는 시그니처가 틀 때 부탁한다(이미 틀었으면 또 안 띄운다)
        fresh.push(d);
    });
    return { fresh, keys };
}

/* 띄운 카드 열쇠 목록에 하나 더(같은 것은 맨 뒤로) — 오래된 것부터 버려 max 개만. 문자열 아닌 것은 버린다 */
export function addShown(list, key, max) {
    const k = key ? String(key) : '';
    const a = (Array.isArray(list) ? list : []).filter(x => typeof x === 'string' && x && x !== k);
    if (k) a.push(k);
    const m = Number(max) || 0;
    return m > 0 ? a.slice(-m) : a;
}

export function cardKey(d) {
    if (!d) return '';
    return d.id ? String(d.id) : (d.at ? String(d.at) : '');
}

/* 출연진 전광판이 맨 앞을 지금 띄울까 — 방송판이 실제로 시작했으면(started.replay 가 같음) 곧바로.
   신호가 없으면 시작할 수 있게 된 뒤(dueSince — 이 전광판이 처음 '시작 가능' 을 본 서버 시각) STARTED_GRACE_MS 가 지나야 */
export function sigDispShow(head, q, now, dueSince, graceMs) {
    if (!head) return false;
    const st = head.started;
    if (st && typeof st === 'object' && (Number(st.replay) || 0) === (Number(head.replay) || 0)) return true;
    if (!sigDue(head, q, now, false)) return false;
    const since = Number(dueSince) || 0;
    if (!since) return false;
    const g = graceMs == null ? STARTED_GRACE_MS : Number(graceMs) || 0;
    return (Number(now) || 0) - since >= g;
}
