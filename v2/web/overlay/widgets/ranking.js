/* 🏆 점수판(옛 엑셀판) — players 조각.
   - 두 칸(왼쪽 · 오른쪽)에 '플레이어 · 점수 · 기여도' 머리줄. 넷이면 2×2, 여섯이면 3×2(사람 수에 맞춰 나눈다).
   - 순서는 서버가 정해 보낸다(기여도 큰 순). 순위 = 줄 번호 + 1. 1·2·3 은 금 · 은 · 동 배지, 1등 줄은 금빛 바탕.
   - 사람이 바뀌거나 순서가 바뀌면 다시 그리고 줄이 옛 자리에서 미끄러진다. 숫자만 바뀌면 0.8초 동안 세어 올린다.
   - 번외 판이 켜져 있으면(extra_active) 같은 자리에 번외 판을 분홍 옷으로 그린다(옛 것도 번외 판이 이 자리를 썼다).
   - 운영비(bottom) 줄은 옛 방송판에서 뺐다(점수는 게이지 합에만 들어간다) — 여기도 안 그린다. */
import { esc, setNum, animateVal, flipSnap, flipPlay } from '../util.js';

const HEAD = '<div class="excel-header"><div></div><div>플레이어</div><div>점수</div><div>기여도</div></div>';

export function mount(root, lm) {
    root.innerHTML = '<div class="excel-board"><div class="excel-grid-container">'
        + '<div class="excel-col">' + HEAD + '<div class="rk-rows"></div></div>'
        + '<div class="excel-col">' + HEAD + '<div class="rk-rows"></div></div>'
        + '</div></div>';
    const board = root.querySelector('.excel-board');
    const [colL, colR] = root.querySelectorAll('.rk-rows');
    let lastKey = null, lastExtra = null;
    let rowsByName = new Map();
    let prev = {};                                  // 이름 → {score, contrib} — 세어 올리기의 출발점
    const keyOf = el => el.dataset.name || '';

    function rowHtml(b, i) {
        if (!b) return '<div class="excel-row"><div class="r-rank">-</div><div class="r-name"></div><div class="r-score"></div><div class="r-contrib"></div></div>';
        const cls = i < 3 ? ' rank-' + (i + 1) : '';
        return '<div class="excel-row' + cls + '" data-name="' + esc(b.name) + '"><div class="r-rank">' + (i + 1) + '</div>'
            + '<div class="r-name">' + esc(b.name) + '</div><div class="r-score"></div><div class="r-contrib"></div></div>';
    }

    function render(p) {
        p = p || {};
        const extra = !!p.extra_active;
        const rows = ((extra ? p.extra : p.list) || []).slice(0, 10);
        board.classList.toggle('is-extra', extra);
        board.classList.toggle('big-num', rows.some(b => (Number(b.contribution) || 0) >= 1000000));
        if (extra !== lastExtra) { lastExtra = extra; lastKey = null; prev = {}; }

        const key = rows.map(b => b.name).join('|');
        if (key !== lastKey) {
            lastKey = key;
            const before = flipSnap(root, '.excel-row[data-name]', keyOf);
            const half = Math.max(1, Math.ceil(rows.length / 2));
            let l = '', r = '';
            for (let i = 0; i < half; i++) l += rowHtml(rows[i], i);
            for (let i = half; i < half * 2; i++) r += rowHtml(rows[i], i);
            colL.innerHTML = l;
            colR.innerHTML = r;
            rowsByName = new Map();
            root.querySelectorAll('.excel-row[data-name]').forEach(el => rowsByName.set(el.dataset.name, el));
            // 새 줄에는 지금 숫자를 바로 적는다(아래에서 바뀐 것만 세어 올린다)
            rowsByName.forEach((el, name) => {
                const pv = prev[name];
                el.querySelector('.r-score').textContent = '';
                el.querySelector('.r-contrib').textContent = '';
                if (pv) { setNum(el.querySelector('.r-score'), pv.score); setNum(el.querySelector('.r-contrib'), pv.contrib); }
            });
            try { flipPlay(root, '.excel-row[data-name]', keyOf, before); } catch (e) {}
        }

        rows.forEach(b => {
            const el = rowsByName.get(String(b.name));
            if (!el) return;
            const sc = Number(b.score) || 0, cb = Number(b.contribution) || 0;
            const pv = prev[b.name];
            const scEl = el.querySelector('.r-score'), cbEl = el.querySelector('.r-contrib');
            if (!pv) {
                setNum(scEl, sc); setNum(cbEl, cb);
            } else {
                if (sc !== pv.score) animateVal(scEl, pv.score, sc, 800);
                else if (!scEl.textContent) setNum(scEl, sc);
                if (cb !== pv.contrib) animateVal(cbEl, pv.contrib, cb, 800);
                else if (!cbEl.textContent) setNum(cbEl, cb);
            }
            prev[b.name] = { score: sc, contrib: cb };
        });
    }

    // 새 방송이면 지난 방송 숫자에서 세어 내려오지 않게 출발점을 버린다
    let lastSid = null;
    lm.on('session', s => {
        const sid = (s && s.id) || '';
        if (lastSid !== null && sid !== lastSid) { prev = {}; lastKey = null; }
        lastSid = sid;
    });
    lm.on('players', render);
}
