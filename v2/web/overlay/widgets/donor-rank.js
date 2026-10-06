/* 🏅 후원 순위 — tallies 조각의 donors {정규화 이름: {name, total, count}} → 누적 금액 큰 순 5명.
   - 몇 명까지: look.donor_rank_limit(편집기 — 옛 donor_rank_limit, 3~10 · 기본 5).
   - '익명' 은 뺀다(look.donor_anon 이면 넣는다) · 0원은 뺀다 · 같으면 이름순(옛 것과 같다). 1·2·3 은 금 · 은 · 동 동그라미.
   - 금액은 look.donor_amount 가 false 면 안 보인다(편집기 📊 목록 개수).
   - 금액이 9자 이상(1,000,000~)이면 한 단계 작게, 이름이 길면 잘리기 전에 한 단계씩 줄인다(바닥선 27px — 폰에서 10px).
   - 줄이 바뀌면 옛 자리에서 미끄러진다(이름으로 짝을 맞춘다).
   ⚠️ 옛 것은 VIP(특별 후원자) 띠도 칠했다 — v2 에 VIP 조각이 아직 없어 안 칠한다. */
import { esc, flipSnap, flipPlay } from '../util.js';

const LIMIT = 5;                       // 기본(옛 donor_rank_limit 기본값)
const limitOf = look => Math.max(3, Math.min(10, parseInt((look || {}).donor_rank_limit, 10) || LIMIT));

export function mount(root, lm) {
    root.innerHTML = '<div class="donor-rank-board"><div class="donor-rank-header">🏅 후원 순위</div><div class="donor-rank-rows"></div></div>';
    const rowsEl = root.querySelector('.donor-rank-rows');
    let lastHtml = null;
    const keyOf = el => { const n = el.querySelector('.dr-name'); return n ? n.textContent : ''; };

    function fit() {
        rowsEl.querySelectorAll('.dr-name').forEach(n => {
            if (!n.clientWidth) return;
            let size = parseFloat(getComputedStyle(n).fontSize) || 32;
            while (n.scrollWidth > n.clientWidth + 1 && size > 27) {
                size -= 1;
                n.style.setProperty('--dr-name-size', size + 'px');
            }
            if (n.scrollWidth > n.clientWidth + 1) n.style.letterSpacing = '-0.06em';
        });
    }
    try { document.fonts && document.fonts.addEventListener && document.fonts.addEventListener('loadingdone', fit); } catch (e) {}

    function draw() {
        const t = lm.get('tallies');
        const tally = (t && t.donors) || {};
        const look = lm.get('look') || {};
        const showAmt = look.donor_amount !== false;          // 💰 금액도 보여주기(기본 켬 — 옛 donor_rank_amount)
        const withAnon = look.donor_anon === true;            // 🕶️ 익명 후원도 순위에 넣기(기본 끔 — 옛 donor_rank_anon)
        const list = Object.keys(tally)
            .filter(k => withAnon || k !== '익명')
            .map(k => ({ name: (tally[k] || {}).name || k, total: Number((tally[k] || {}).total) || 0 }))
            .filter(r => r.total > 0)
            .sort((a, b) => b.total - a.total || a.name.localeCompare(b.name))
            .slice(0, limitOf(lm.get('look')));
        const html = list.length
            ? list.map((r, i) => {
                const amtTxt = Number(r.total).toLocaleString('ko-KR');
                const room = !showAmt ? 8 : amtTxt.length >= 9 ? 4 : 5;     // 금액을 안 보이면 이름 자리가 넓다
                const len = String(r.name || '').length;
                const sz = len <= room ? 32 : (len <= room + 1 ? 29 : 27);
                return '<div class="dr-row' + (i < 3 ? ' top' + (i + 1) : '') + '">'
                    + '<span class="dr-no">' + (i + 1) + '</span>'
                    + '<span class="dr-name" style="--dr-name-size:' + sz + 'px">' + esc(r.name) + '</span>'
                    + (showAmt ? '<span class="dr-amt' + (amtTxt.length >= 9 ? ' long' : '') + '">' + amtTxt + '</span>' : '') + '</div>';
            }).join('')
            : '<div class="dr-empty">아직 후원이 없습니다</div>';
        if (html === lastHtml) return;
        const before = flipSnap(rowsEl, '.dr-row', keyOf);
        rowsEl.innerHTML = html;
        lastHtml = html;
        fit();
        try { flipPlay(rowsEl, '.dr-row', keyOf, before); } catch (e) {}
    }
    lm.on('tallies', draw);
    lm.on('look', draw);                   // 편집기에서 인원을 바꾸면 바로
}
