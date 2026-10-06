/* 🧰 방송판 위젯이 같이 쓰는 작은 도구들 — 화면(DOM)은 만들지 않는다. */

export const FRESH_MS = 30000;          // 30초 넘은 알림은 안 띄운다(옛 ALERT_FRESH_MS)
export const SMALL_DON_MAX = 10000;     // 1만 원 미만은 가운데 카드 대신 맨 위 띠(옛 SMALL_DON_MAX)
export const BIG_DONATION_MIN = 100000; // 10만 원 이상 시그니처는 카드 없이 곧장 + 'OO업' 배너(옛 BIG_DONATION_MIN)

export function formatNum(n) {
    const v = Math.trunc(Number(n) || 0);
    return String(v).replace(/\B(?=(\d{3})+(?!\d))/g, ',');
}

export function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, m =>
        ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[m]));
}

/* 클래스를 떼었다 붙여 애니메이션을 처음부터 다시 — 연달아 와도 매번 뛴다 */
export function restartClass(el, cls) {
    if (!el) return;
    el.classList.remove(cls);
    void el.offsetWidth;
    el.classList.add(cls);
}

/* 숫자 세어 올리기(옛 animateVal — 0.8초, 끝으로 갈수록 느리게). 같은 칸에 새로 걸면 앞의 것은 멈춘다. */
export function animateVal(el, start, end, dur) {
    if (!el) return;
    const token = (el.__lmAnim = (el.__lmAnim || 0) + 1);
    let t0 = null;
    const step = ts => {
        if (el.__lmAnim !== token) return;
        if (t0 === null) t0 = ts;
        const p = Math.min((ts - t0) / dur, 1);
        const cur = Math.floor((1 - Math.pow(1 - p, 3)) * (end - start) + start);
        setNum(el, p < 1 ? cur : end);
        if (p < 1) requestAnimationFrame(step);
    };
    requestAnimationFrame(step);
}

/* ⚠️ 옛 판의 '+5' 딱지(popScore)는 옮기지 않았다 — 옛 animateVal 이 다음 그림(rAF)에서 innerText 로 칸을
      통째로 덮어써 딱지가 한 장면도 안 남았다. 화면에 실제로 보이던 모습(숫자만 세어 올라감)을 따른다. */
export function setNum(el, v) {
    el.textContent = formatNum(v);
}

/* 방송판 배율 — 화면 좌표(getBoundingClientRect)를 캔버스 좌표로 바꿀 때 */
export function canvasScale() {
    const w = document.getElementById('scale-wrapper');
    return (w && w.getBoundingClientRect().width / 1080) || 1;
}

/* 🔀 자리 바뀜 연출(FLIP) — 옛 rowFlipSnap/rowFlipPlay 그대로. 다시 그리기 전에 찍고, 그린 뒤 옛 자리에서 미끄러뜨린다.
   ⚠️ transform 이 아니라 top/left 로 옮긴다(줄의 다른 애니메이션 transform 과 안 싸우게). */
export function flipSnap(root, sel, keyOf) {
    const m = {};
    if (!root) return m;
    root.querySelectorAll(sel).forEach((el, i) => {
        const k = keyOf(el);
        if (!k) return;
        const r = el.getBoundingClientRect();
        if (r.width || r.height) m[k] = { x: r.left, y: r.top, i };
    });
    return m;
}
export function flipPlay(root, sel, keyOf, before) {
    if (!root || !before) return;
    const sc = canvasScale();
    root.querySelectorAll(sel).forEach((el, i) => {
        const b = before[keyOf(el)];
        if (!b) return;
        const a = el.getBoundingClientRect();
        if (!a.width && !a.height) return;
        const dx = Math.round((b.x - a.left) / sc), dy = Math.round((b.y - a.top) / sc);
        if (Math.abs(dx) < 2 && Math.abs(dy) < 2) return;
        el.classList.remove('rank-go', 'rank-up');
        el.classList.add('rank-moving');
        el.style.left = dx + 'px'; el.style.top = dy + 'px';
        void el.offsetWidth;
        el.classList.add('rank-go');
        el.style.left = ''; el.style.top = '';
        if (i < b.i) el.classList.add('rank-up');
        setTimeout(() => el.classList.remove('rank-moving', 'rank-go', 'rank-up'), 1400);
    });
}

/* 💰 게이지 합 = 운영비 + 본판 점수 합 + 보정(번외 판 · 기여도는 안 들어간다) — 서버 goal 조각 설명과 같다 */
export function gaugeTotal(players, goal) {
    const p = players || {};
    let tot = Number((p.bottom || {}).score) || 0;
    (p.list || []).forEach(b => { tot += Number(b.score) || 0; });
    tot += parseInt((goal || {}).offset, 10) || 0;
    return tot;
}

/* 🎁 후원 알림이 어디로 가나 — 옛 handleData 의 판단 순서 그대로.
   'sig'   시그니처 대기줄에 같은 사람 · 같은 금액이 있다 → 시그니처가 틀 때 카드를 띄운다(지금은 아무것도)
   'small' 화면에만(display_only) 이거나 0원 초과 1만 원 미만 → 맨 위 띠
   'card'  가운데 카드 */
export function classifyDonation(d, queue) {
    if (!d) return null;
    if (d.display_only) return 'small';
    const items = (queue && queue.items) || [];
    if (items.some(it => it.donator === d.name && Number(it.amount) === Number(d.amount))) return 'sig';
    const amt = Number(d.amount) || 0;
    if (amt > 0 && amt < SMALL_DON_MAX && !String(d.message || '').startsWith('[시그니처 신청:')) return 'small';
    return 'card';
}
