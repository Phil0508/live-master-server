/* 📱 폰 조종실 — 옛 mobile.html(폰 전용 화면)을 따로 두지 않고 이 조종실 하나를 폰에서도 쓴다(옛 주소 /mobile → 여기).
   폰 화면(900px 아래)은 controller.css 가 한 줄로 세운다 — 대기함 → 점수판 → 되돌리기(아래에 붙음) → 시그니처 대기줄 → 목표 → 기록.
   여기서 더하는 것(생김새는 css/tools_sig.css 맨 아래 묶음)
     1) 새 후원 알림 띠 — 폰에서 대기함이 화면 밖(게임 탭 등 아래쪽을 보는 중)일 때 새 후원이 오면 위에 작은 띠를 띄운다.
        누르면 대기함으로 올라간다. 대기함이 보이면 저절로 걷힌다(옛 mobile.html 의 위에서 내려오는 알림).
     2) 탭 줄 — 폰에서는 한 줄로 옆으로 밀어 본다(css). 고른 탭이 줄 밖이면 가운데로 끌어온다(세로로는 안 움직인다).
     3) 방송 전 화면 — [💿 시그니처 관리] 바로가기(/controller/sig.html). 탭은 방송 중에만 보여서, 방송 전엔 여기로 간다.
   ⚠️ 소리는 내지 않는다(대표님 10-06 '소리는 안 나도 돼'). ⚠️ 바깥 글자(이름)는 textContent 로만. */
import { h, won } from './util.js';

const PHONE = '(max-width: 899px)';

export function mountPhone(ctx) {
    const mq = window.matchMedia ? matchMedia(PHONE) : { matches: false };
    newDonationPill(ctx, mq);
    tabStrip(mq);
    setupLinks();
}

/* ── 1) 새 후원 알림 띠 ── */
function newDonationPill(ctx, mq) {
    const pendingEl = document.getElementById('pending');
    if (!pendingEl) return;
    const pill = h('button', { type: 'button', class: 'ph-new', hidden: true });
    document.body.append(pill);
    let seen = null;                 // 이미 본 후원 id
    let fresh = [];                  // 아직 못 본 새 후원 [{id, name, amount, kind, contrib}]
    let visible = true;

    function paint() {
        const show = fresh.length > 0 && !visible && mq.matches && document.body.dataset.view === 'live';
        pill.hidden = !show;
        if (!show) return;
        const d = fresh[fresh.length - 1];
        const what = d.kind === 'contrib' ? `기여도 ${d.contrib || 0}` : won(d.amount);
        pill.replaceChildren(h('span', { class: 'ph-ic', 'aria-hidden': 'true' }, '📥'),
            h('span', { class: 'ph-t' }, h('b', null, d.name || '익명'), ' ', what, fresh.length > 1 ? ` 외 ${fresh.length - 1}건` : ''),
            h('span', { class: 'ph-go' }, '대기함 ↑'));
        pill.setAttribute('aria-label', `새 후원 ${fresh.length}건 — 눌러서 대기함으로`);
    }
    function clear() { fresh = []; paint(); }

    pill.addEventListener('click', () => {
        pendingEl.scrollIntoView({ behavior: 'smooth', block: 'start' });
        clear();
    });
    if ('IntersectionObserver' in window) {
        new IntersectionObserver(es => {
            visible = es.some(e => e.isIntersecting);
            if (visible) clear(); else paint();
        }, { threshold: 0.02 }).observe(pendingEl);
    }
    ctx.lm.on('pending', list => {
        const items = Array.isArray(list) ? list : [];
        const ids = new Set(items.map(x => x.id));
        if (seen === null) { seen = ids; return; }          // 처음 받은 것은 '이미 있던 것'
        items.forEach(x => {
            if (seen.has(x.id)) return;
            seen.add(x.id);
            if (!x.type) fresh.push({ id: x.id, name: x.name, amount: x.amount, kind: x.kind, contrib: x.contrib });   // 퇴근 · 탈출 카드는 후원이 아니다
        });
        fresh = fresh.filter(x => ids.has(x.id));          // 그새 다른 기기가 처리한 것은 뺀다
        paint();
    });
    mq.addEventListener && mq.addEventListener('change', paint);
    new MutationObserver(paint).observe(document.body, { attributes: true, attributeFilter: ['data-view'] });
}

/* ── 2) 탭 줄 — 고른 탭을 줄 가운데로(가로로만) ── */
function tabStrip(mq) {
    function center(btn) {
        const bar = btn && btn.closest('.tabbar');
        if (!bar || !mq.matches || bar.scrollWidth <= bar.clientWidth) return;
        const want = btn.offsetLeft - (bar.clientWidth - btn.offsetWidth) / 2;
        bar.scrollTo({ left: Math.max(0, want), behavior: 'smooth' });
    }
    document.addEventListener('click', e => {
        const b = e.target.closest && e.target.closest('.tabbar .tab');
        if (b) center(b);
    });
    // 처음(지난번 연 탭을 기억해 연다) — 방송 화면이 그려진 뒤 한 번
    let done = false;
    const first = () => {
        if (done || document.body.dataset.view !== 'live') return;
        const on = document.querySelector('.tabbar .tab.on');
        if (!on) return;
        done = true;
        requestAnimationFrame(() => center(on));
    };
    new MutationObserver(first).observe(document.body, { attributes: true, attributeFilter: ['data-view'] });
    setTimeout(first, 500);
}

/* ── 3) 방송 전 화면 — 시그니처 관리 바로가기 ── */
function setupLinks() {
    const root = document.getElementById('v-setup');
    if (!root || root.querySelector('.ph-setup')) return;
    root.append(h('aside', { class: 'card ph-setup' },
        h('b', null, '💿 시그니처(음원 · 사진)'),
        h('p', { class: 'muted small' }, '등록 · 고치기 · 지우기는 방송 전에도 할 수 있어요. 방송 중에는 [시그니처 관리] 탭에서.'),
        h('a', { class: 'btn wide', href: '/controller/sig.html' }, '시그니처 관리 열기')));
}
