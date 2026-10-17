/* 🎬 엔딩 크레딧 — credits 조각(공개)을 그린다. 영화 엔딩처럼 아래에서 위로 천천히, 끝까지 가면 마무리 글에서 멈춘다.
   - 켜지면 캔버스 전체를 **불투명**하게 덮는다(다른 칸은 가려진다) · stage.setMode('credits') — 위에 뜨던 점수 팝업 · 1등 탈환 ·
     목표 달성 · 퇴근 · UP 자막은 css/credits.css 가 내린다. 후원 카드 · 소액 띠 · 시그니처 · 한마디는 위에 그대로(끝 화면과 같은 규칙).
   - 받는 것은 이름(닉네임)과, 조종실에서 '금액 보이기' 를 켰을 때만 금액 — 실명 · 계좌 · 메시지는 조각에 없다.
   - 자리 셈은 flow.js 한 곳(서버 시계 기준). 글씨는 테마 글꼴(--face-*)을 따라간다.
   ⚠️ 바깥 글자는 전부 esc() 로. */
import { serverNow, startClock } from '../basics2/clock.js';
import { posAt, shiftY, stopAt } from './flow.js';

function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, m => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[m]));
}
const won = n => Number(n || 0).toLocaleString('ko-KR') + '원';

function groupHtml(g) {
    const names = (g.names || []).map(r => '<li><b>' + esc(r.name) + '</b>'
        + (r.total != null ? '<span>' + won(r.total) + '</span>' : '') + '</li>').join('');
    const head = g.kind === 'member'
        ? '<div class="cr-gl">♥ 마음을 보내 주신 분</div><div class="cr-gt">' + esc(g.title) + '</div>'
        : '<div class="cr-gt' + (g.kind === 'etc' ? ' soft' : '') + '">' + esc(g.title) + '</div>';
    return '<section class="cr-grp cr-' + esc(g.kind) + '">' + head + '<ul class="cr-names">' + names + '</ul></section>';
}

function rollHtml(c) {
    const groups = c.groups || [];
    const count = Number(c.count) || 0, anon = Number(c.anon) || 0;
    const sub = count ? '오늘 후원해 주신 ' + count.toLocaleString('ko-KR') + '분' : '';
    return '<div class="cr-head"><div class="cr-kick">ENDING CREDITS</div>'
        + '<div class="cr-title">' + esc(c.title || '오늘 함께해 주셔서 감사합니다') + '</div>'
        + (sub ? '<div class="cr-sub">' + esc(sub) + '</div>' : '') + '</div>'
        + groups.map(groupHtml).join('')
        + (anon ? '<div class="cr-anon">이름 없이 함께해 주신 ' + anon.toLocaleString('ko-KR') + '분도 고맙습니다</div>' : '')
        + (!groups.length && !anon ? '<div class="cr-anon">함께해 주신 모든 분께 고맙습니다</div>' : '')
        + '<div class="cr-outro">' + esc(c.outro || '다음 방송에서 또 만나요 ♥') + '</div>';
}

export function mount(root, lm, opts) {
    startClock(lm);
    root.innerHTML = '<div class="cr-root" aria-hidden="true"><div class="cr-bg"></div><div class="cr-view"><div class="cr-roll"></div></div></div>';
    const box = root.firstElementChild;
    const roll = root.querySelector('.cr-roll');
    let html = null, cur = {}, stop = 0, raf = 0, iv = 0, lastY = null;

    function measure() {
        const out = roll.querySelector('.cr-outro');
        const mid = out ? out.offsetTop + out.offsetHeight / 2 : 0;
        stop = stopAt(roll.offsetHeight, mid);
    }
    function paint() {
        const y = Math.round(shiftY(posAt(cur, serverNow(), stop)) * 2) / 2;
        if (y !== lastY) { roll.style.transform = 'translate3d(0,' + y + 'px,0)'; lastY = y; }
        box.classList.toggle('at-end', posAt(cur, serverNow(), stop) >= stop - 0.5);
    }
    function loop() {
        raf = 0;
        if (!cur.on) return;
        paint();
        raf = requestAnimationFrame(loop);
    }
    function run(on) {
        if (on) {
            if (!raf) raf = requestAnimationFrame(loop);
            // 가려진 창에서는 rAF 가 멈춘다 — 0.5초마다 한 번은 자리를 맞춘다(돌아왔을 때 튀지 않게)
            if (!iv) iv = setInterval(() => { if (cur.on) paint(); }, 500);
        } else {
            if (raf) { cancelAnimationFrame(raf); raf = 0; }
            if (iv) { clearInterval(iv); iv = 0; }
        }
    }

    function render() {
        cur = lm.get('credits') || {};
        const on = !!cur.on;
        const h = on ? rollHtml(cur) : '';
        if (h !== html) {
            roll.innerHTML = h;
            html = h;
            lastY = null;
            if (on) measure();
        }
        box.classList.toggle('show', on);
        opts.stage.setMode('credits', on);
        if (on) { measure(); paint(); }
        run(on);
    }

    // 글꼴이 늦게 들어오면 높이가 바뀐다 — 다 받은 뒤 한 번 더 잰다
    try { document.fonts && document.fonts.ready.then(() => { if (cur.on) { measure(); paint(); } }); } catch (e) {}
    const safe = () => { try { render(); } catch (e) { console.error('[엔딩 크레딧] 그리기 실패 — 방송은 계속됩니다:', e); } };
    lm.on('credits', safe);
    lm.on('look', () => { try { if (cur.on) setTimeout(() => { measure(); paint(); }, 50); } catch (e) {} });
    window.__lmCredits = { pos: () => posAt(cur, serverNow(), stop), stop: () => stop };     // 점검용(콘솔)
}
