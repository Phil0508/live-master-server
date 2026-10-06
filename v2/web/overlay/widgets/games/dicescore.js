/* 🎲 주사위 점수 띠 — dicegame.board(주사위 **전용** 점수판) · pieces · turn. 옛 #dgscore-container · renderDiceBoard · dgsPlace.

   - 말과 같은 색 칩을 한 줄로(7개부터 두 줄). 순서 = 점수 높은 순, 같으면 이름의 글자 번호 순(서버 파이썬 비교와 같게 —
     localeCompare 를 쓰면 'b' 와 'C' 처럼 서버와 거꾸로 서는 이름이 생겼다).
   - 지금 차례는 금테 + '차례' 꼬리표, 쉴드권은 🛡️. 점수가 바뀌면 0.8초 세어 올리고 오른 칩은 키우고 내린 칩은 살짝 줄인다.
   - 자리: 편집기에서 안 옮겼으면 주사위판 **바로 위**, 판과 같은 폭 · 같은 배율(옛 dgsPlace). 판 자리는 무대의 'diceBoard' 에 묻는다.
     옮겼으면(layout 조각에 이 칸이 있고 옛 기본 6,191 · 배율 1 이 아니면) 그 자리 그대로 — 폭만 판을 따른다.
   - 보이기: 주사위판과 같이(무대 dicegame · 칸 있음 · 시작/끝 화면 아님). */
import { esc, formatNum, animateVal } from '../../util.js';
import { makeFader, coverOn } from './dice_kit.js';

const DEF_X = 6, DEF_Y = 191;      // 옛 기본 자리 — 이 자리는 '안 옮긴 것' 으로 본다(옛 10-06 점검)

// 🔤 글자 번호(code point) 순 — 이모지 같은 큰 글자도 글자 단위로
function codeCmp(a, b) {
    const A = Array.from(String(a)), B = Array.from(String(b));
    const n = Math.min(A.length, B.length);
    for (let i = 0; i < n; i++) {
        const x = A[i].codePointAt(0), y = B[i].codePointAt(0);
        if (x !== y) return x < y ? -1 : 1;
    }
    return A.length === B.length ? 0 : (A.length < B.length ? -1 : 1);
}

export function mount(root, lm, opts) {
    const stage = opts.stage;
    root.innerHTML = '<div class="gb-wrap dgs-wrap"><div class="dg-strip"></div></div>';
    const wrap = root.firstElementChild;
    const strip = root.querySelector('.dg-strip');
    const fade = makeFader(wrap, stage);
    let rosterKey = '', prev = {};
    let hooked = false;

    function placed() {
        const o = ((lm.get('layout') || {}).widgets || {})[opts.layer.id];
        if (!o) return false;
        return !(Number(o.x) === DEF_X && Number(o.y) === DEF_Y && (Number(o.scale) || 1) === 1);
    }

    // 판 바로 위에 붙인다 — 판은 칸 표에서 가운데 정렬이라 실제 상자를 잰다
    function place() {
        const svc = stage.use('diceBoard');
        if (svc && !hooked) { hooked = true; svc.onChange(place); }
        const r = svc && svc.rect();
        if (!r) return;
        strip.style.width = Math.round(r.ow) + 'px';
        if (placed()) return;
        const k = r.k || 1;
        root.style.right = 'auto';
        root.style.left = Math.round(r.x) + 'px';
        root.style.top = Math.round(r.y - (root.offsetHeight || 116) * k) + 'px';
        root.style.transformOrigin = 'top left';
        root.style.transform = Math.abs(k - 1) > 0.001 ? 'scale(' + k + ')' : '';
    }

    function render() {
        const g = lm.get('dicegame') || {};
        const st = (lm.get('show') || {}).stage;
        const on = st === 'dicegame' && (g.tiles || []).length > 0;
        fade(on && !coverOn(lm));
        if (!on) { place(); return; }

        const rows = (Array.isArray(g.board) ? g.board : [])
            .filter(r => r && r.name)
            .map(r => ({ name: String(r.name), pts: Number(r.pts) || 0 }))
            .sort((a, b) => b.pts - a.pts || codeCmp(a.name, b.name));
        // 말 색 · 쉴드권 · 차례는 말 목록(pieces)에 있다. 색 번호는 판 위 말과 같은 규칙(번호 % 4)
        const pieces = Array.isArray(g.pieces) ? g.pieces : [];
        const color = {}, shield = {};
        pieces.forEach((p, i) => { if (p && p.name) { color[p.name] = i % 4; if (p.shield) shield[p.name] = true; } });
        const turn = ((pieces[g.turn | 0] || {}).name) || '';
        // 숫자 · 차례 · 쉴드 · 색이 바뀔 때만 다시 그린다(세어 올리던 숫자가 옛 칸과 함께 사라지지 않게)
        const key = rows.map(r => r.name + ':' + r.pts + ':' + (color[r.name] | 0) + (shield[r.name] ? 's' : '')).join('|') + '#' + turn;
        if (key !== rosterKey || strip.childElementCount !== rows.length) {
            rosterKey = key;
            const perRow = rows.length > 6 ? Math.ceil(rows.length / 2) : Math.max(1, rows.length);
            strip.style.gridTemplateColumns = 'repeat(' + perRow + ', minmax(0, 1fr))';
            strip.innerHTML = rows.map((r, i) => {
                const isTurn = r.name === turn;
                return '<div class="dgs-chip p' + (color[r.name] | 0) + (isTurn ? ' dgs-turn' : '') + '" data-name="' + esc(r.name) + '">'
                    + (isTurn ? '<span class="dgs-flag">차례</span>' : '')
                    + (shield[r.name] ? '<span class="dgs-shield" title="쉴드권">🛡️</span>' : '')
                    + '<span class="dgs-rank">' + (i + 1) + '</span><span class="dgs-txt"><span class="dgs-name">' + esc(r.name) + '</span>'
                    + '<span class="dgs-pts' + (r.pts < 0 ? ' minus' : '') + '">' + formatNum(r.pts) + '</span></span></div>';
            }).join('');
            const chips = strip.querySelectorAll('.dgs-chip');
            rows.forEach((r, i) => {
                const chip = chips[i];
                const el = chip && chip.querySelector('.dgs-pts');
                const was = prev[r.name];
                prev[r.name] = r.pts;
                if (!el || was === undefined || was === r.pts) return;
                animateVal(el, was, r.pts, 800);
                const cls = r.pts > was ? 'dgb-up' : 'dgb-down';
                chip.classList.remove('dgb-up', 'dgb-down');
                void chip.offsetWidth;
                chip.classList.add(cls);
                setTimeout(() => chip.classList.remove(cls), 900);
            });
            Object.keys(prev).forEach(n => { if (!rows.some(r => r.name === n)) delete prev[n]; });   // 판에서 빠진 사람은 기억도 지운다
        }
        requestAnimationFrame(place);
    }

    // 새 방송이면 지난 방송 점수에서 세어 내려오지 않게
    let lastSid = null;
    lm.on('session', s => {
        const sid = (s && s.id) || '';
        if (lastSid !== null && sid !== lastSid) { prev = {}; rosterKey = ''; }
        lastSid = sid;
    });
    lm.on('dicegame', render);
    lm.on('show', render);
    lm.on('screen', render);
    lm.on('layout', () => requestAnimationFrame(place));
    if (stage.onLayout) stage.onLayout(place);
}
