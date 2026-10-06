/* 📊 시그 집계 — 이번 방송에 어떤 시그니처가 몇 번 나왔나(옛 renderSigTally 그대로).
   tallies.sigs {시그 id: {title, image_url, amount, count, donors}} → 많이 나온 순(같으면 비싼 순) 위에서 몇 개.
   몇 개까지: look.sig_tally_limit(편집기 — 옛 sig_tally_limit, 기본 6). 판은 206px — 글씨를 줄이면 폰에서 못 읽어 '시그 집계' 로 부른다.
   켜고 끄기: 고정 자리 hud.sig_tally(무대 탭). */
import { esc, formatNum } from '../util.js';

const LIMIT_DEFAULT = 6;

export function mount(root, lm) {
    root.innerHTML = '<div class="sig-tally-board"><div class="sig-tally-header">🎵 시그 집계</div><div class="st-rows"></div></div>';
    const rowsEl = root.querySelector('.st-rows');
    let lastHtml = null;

    function draw() {
        const t = lm.get('tallies') || {};
        const look = lm.get('look') || {};
        const limit = Math.max(3, Math.min(12, parseInt(look.sig_tally_limit, 10) || LIMIT_DEFAULT));
        const tally = t.sigs || {};
        const list = Object.keys(tally).map(k => tally[k])
            .filter(r => r && (r.count || 0) > 0)
            .sort((a, b) => (b.count - a.count) || ((b.amount || 0) - (a.amount || 0)))
            .slice(0, limit);
        const html = list.map(r => '<div class="st-row">'
            + (r.image_url ? '<img src="' + esc(r.image_url) + '" alt="">' : '<div class="st-noimg"></div>')
            + '<div class="st-shade"></div>'
            + '<div class="st-count">' + (r.count | 0) + '개</div>'
            + '<div class="st-title">' + esc(r.title || '') + '</div>'
            + '<div class="st-amt">' + formatNum(r.amount || 0) + '</div></div>').join('');
        if (html === lastHtml) return;
        rowsEl.innerHTML = html;
        lastHtml = html;
    }
    lm.on('tallies', draw);
    lm.on('look', draw);
}
