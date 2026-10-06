/* ⚔️ 대결판 — match 조각 + show.stage. 옛 overlay.html renderMatchWidget · renderMatchGap · updateMatchTimer 를 옮겼다.

   - 보이기: show.stage == 'match' 일 때(active 는 '대결이 열려 있나' — 무대가 잠깐 다른 판이어도 대결은 이어진다).
     방송 중에만(칸 표 liveOnly), 시그니처가 도는 동안 · 시작/끝 화면이면 내린다.
   - 타이머: running 이면 max(0, end_ms − 서버 시각), 아니면 left_ms. ceil(초) 를 mm:ss, 0 이면 '시간종료'.
     마지막 10초(running)는 빨개지며 커지고 초가 바뀔 때마다 삐 — 1초 남으면 여섯 번.
   - 끝 연출(펑 · 꽃가루 · '시간 종료!' 3초)은 판마다 한 번:
       ① running 인데 서버 시각이 end_ms 를 지나면 그때 터뜨리고 match.timeup 을 보낸다(로그인 없이 — 서버가 시각을 본다,
          너무 이르면 409 → 1초 뒤 다시. ?monitor=1 은 안 보낸다). 열쇠 = end_ms.
       ② 조종실이 match.end 로 끝내 ended_at 이 새 값이 되면(아직 안 터뜨린 판이고 방금 일이면) 그때.
     꽃가루 · 글씨는 캔버스 전체 칸(match_fx)이 그린다 — 무대의 'matchFx' 를 부른다.
   - 게이지: 몫 = max(0.05, max(0, 점수)/합), 합이 0 이면 똑같이. 카드 · 게이지 색 = 순서 i 의 M_COLS[i % 6].
     👑 빛(lead)은 서버 lead 가 하나일 때만. 격차(gap)는 서버 값 — null 이면 숨김 · 0 이면 '동점' ·
     그 밖엔 숫자 + ('1·2위 차이' | '차이') + '(gap+1)점시 역전!'. 붙었다(tight) = 합 > 0 · gap/합 ≤ 0.08.
     전선 자리 = lead[0] 칸에서 2위가 있는 쪽 모서리.
   - 순간 글씨: flash.at 이 처음 보는 값이고 실시간(또는 3초 안)이면 flash.text('역전!' · '동점!') 한 번.
   - 점수가 바뀌면 0.7초 세어 올리고, 오르면 카드가 번쩍(m-bump). 전 점수는 team.id 로 기억한다.
   - 불꽃 테두리(피버 · 수동 불꽃)는 match_fire 칸이 따로 그린다. */
import { esc, formatNum, animateVal, restartClass } from '../../util.js';
import { startClock, serverNow, soundInit, beep, explosion, makeFader, coverOn, isLive, canvasRect } from './dice_kit.js';

const M_COLS = ['#ff3b5c', '#3ba7ff', '#00e676', '#f6c453', '#b06bff', '#ff9f2e'];
const M_RGB  = ['255, 59, 92', '59, 167, 255', '0, 230, 118', '246, 196, 83', '176, 107, 255', '255, 159, 46'];
const M_TIGHT_RATIO = 0.08;

export function mount(root, lm, opts) {
    startClock();
    soundInit(opts);
    const stage = opts.stage;
    root.innerHTML = '<div class="gb-wrap match-box"><div class="match-wrapper">'
        + '<div class="m-timer-pill">00:00</div>'
        + '<div class="m-front"><div class="m-gauge"></div><div class="m-front-line"></div>'
        +   '<div class="m-front-mark"><div class="m-front-tail"></div>'
        +     '<div class="m-front-num"><span class="m-fn">0</span><span class="unit">차이</span></div>'
        +     '<div class="m-front-hint"></div></div></div>'
        + '<div class="m-cards"></div>'
        + '<div class="m-flash">역전!</div>'
        + '</div></div>';
    const wrap = root.firstElementChild;
    const timerEl = root.querySelector('.m-timer-pill');
    const front = root.querySelector('.m-front');
    const gauge = root.querySelector('.m-gauge');
    const line = root.querySelector('.m-front-line');
    const mark = root.querySelector('.m-front-mark');
    const numEl = root.querySelector('.m-fn');
    const unitEl = root.querySelector('.m-front-num .unit');
    const hintEl = root.querySelector('.m-front-hint');
    const cardsEl = root.querySelector('.m-cards');
    const flashEl = root.querySelector('.m-flash');
    const fade = makeFader(wrap, stage);

    let teamKey = null, prevScores = {}, prevGap = null, seenFlashAt = null;
    let lastBeepSec = -1, exploded = 0, seenEndedAt = null, timeupFor = 0, timeupTries = 0, timeupTimer = null;
    let onStage = false;

    // 격차 숫자 — 세대 번호로 낡은 애니메이션이 '동점' 을 덮어쓰지 못하게(옛 animateGap)
    const bumpGen = el => { el.dataset.gen = (+el.dataset.gen || 0) + 1; return +el.dataset.gen; };
    function animateGap(el, start, end, dur) {
        const my = bumpGen(el);
        let t0 = null;
        const step = ts => {
            if (+el.dataset.gen !== my) return;
            if (!t0) t0 = ts;
            const p = Math.min((ts - t0) / dur, 1);
            el.textContent = formatNum(Math.floor((1 - Math.pow(1 - p, 3)) * (end - start) + start));
            if (p < 1) requestAnimationFrame(step);
        };
        requestAnimationFrame(step);
    }

    function renderBoard(m) {
        const teams = m.teams || [];
        const key = teams.map(t => t.id).join('|');
        if (key !== teamKey) {
            teamKey = key;
            prevGap = null;
            gauge.innerHTML = teams.map((t, i) =>
                '<div class="m-seg" style="--c:' + M_COLS[i % 6] + '; --rgb:' + M_RGB[i % 6] + ';"><span class="m-seg-amt">0</span></div>').join('');
            cardsEl.innerHTML = teams.map((t, i) =>
                '<div class="m-card" style="--c:' + M_COLS[i % 6] + '; --rgb:' + M_RGB[i % 6] + ';">'
                + '<span class="m-crown">👑</span>'
                + '<span class="m-card-id"><span class="m-card-name">' + esc(t.name || '') + '</span><span class="m-card-members"></span></span>'
                + '<span class="m-card-amt">0</span></div>').join('');
        }
        const segs = gauge.children, cards = cardsEl.children;
        const lead = Array.isArray(m.lead) ? m.lead : [];
        const hiId = lead.length === 1 ? lead[0] : null;          // 👑 혼자 1등일 때만 빛
        let total = 0;
        teams.forEach(t => { total += Math.max(0, Number(t.score) || 0); });
        const fracs = [];
        teams.forEach((t, i) => {
            const sc = Number(t.score) || 0;
            const seg = segs[i], card = cards[i];
            if (!seg || !card) return;
            const nameEl = card.querySelector('.m-card-name');
            if (nameEl.textContent !== (t.name || '')) nameEl.textContent = t.name || '';
            const memEl = card.querySelector('.m-card-members');
            const mem = (m.link && m.link !== 'off') ? (t.members || []).filter(Boolean).join(' · ') : '';
            if (memEl.textContent !== mem) memEl.textContent = mem;
            const frac = total > 0 ? Math.max(0.05, Math.max(0, sc) / total) : (1 / Math.max(1, teams.length));
            fracs.push(frac);
            seg.style.flex = frac.toFixed(4);
            seg.classList.toggle('lead', t.id === hiId);
            card.classList.toggle('lead', t.id === hiId);
            const amtEl = card.querySelector('.m-card-amt'), segAmt = seg.querySelector('.m-seg-amt');
            const pv = prevScores[t.id];
            if (pv !== undefined && pv !== sc) {
                animateVal(amtEl, pv, sc, 700);
                animateVal(segAmt, pv, sc, 700);
                if (sc > pv) { restartClass(card, 'm-bump'); setTimeout(() => card.classList.remove('m-bump'), 700); }
            } else if (pv === undefined || amtEl.textContent === '0') {
                amtEl.textContent = formatNum(sc);
                segAmt.textContent = formatNum(sc);
            }
            prevScores[t.id] = sc;
        });
        renderGap(m, teams, total, fracs);
    }

    function renderGap(m, teams, total, fracs) {
        const lead = Array.isArray(m.lead) ? m.lead : [];
        const gap = (m.gap === null || m.gap === undefined) ? null : Number(m.gap);
        if (teams.length < 2 || !lead.length || gap === null) {
            front.classList.remove('on', 'tight');
            gauge.classList.remove('tight');
            prevGap = null;
            return;
        }
        const leadIdx = teams.findIndex(t => t.id === lead[0]);
        let secondIdx = -1;
        teams.forEach((t, i) => {
            if (i === leadIdx) return;
            if (secondIdx < 0 || (Number(t.score) || 0) > (Number(teams[secondIdx].score) || 0)) secondIdx = i;
        });
        // 전선 = 1등 칸에서 추격자가 있는 쪽 모서리
        const sum = fracs.reduce((a, f) => a + f, 0) || 1;
        const upto = secondIdx > leadIdx ? leadIdx : leadIdx - 1;
        let acc = 0;
        for (let i = 0; i <= upto; i++) acc += fracs[i] || 0;
        const pct = (acc / sum * 100).toFixed(2) + '%';
        mark.style.left = pct;
        line.style.left = pct;
        if (gap === 0) {
            bumpGen(numEl);
            numEl.textContent = '동점';
            unitEl.style.display = 'none';
            hintEl.textContent = '';
        } else {
            unitEl.style.display = '';
            unitEl.textContent = teams.length > 2 ? '1·2위 차이' : '차이';
            if (prevGap !== null && prevGap !== gap) animateGap(numEl, prevGap, gap, 700);
            else { bumpGen(numEl); numEl.textContent = formatNum(gap); }
            hintEl.textContent = formatNum(gap + 1) + '점시 역전!';
        }
        prevGap = gap;
        const tight = total > 0 && (gap / total) <= M_TIGHT_RATIO;
        front.classList.add('on');
        front.classList.toggle('tight', tight);
        gauge.classList.toggle('tight', tight);
    }

    function flashMaybe(m) {
        const f = m.flash;
        const at = f && Number(f.at);
        if (!at) return;
        if (seenFlashAt === at) return;
        const first = seenFlashAt === null;
        seenFlashAt = at;
        if (!onStage) return;
        if (!isLive(opts) && (first || serverNow() - at > 3000)) return;   // 다시 붙어 받은 옛 글씨 · 처음 그림은 안 띄운다
        flashEl.textContent = f.text || '';
        restartClass(flashEl, 'go');
    }

    // 💥 끝 연출 — 꽃가루 · 글씨는 캔버스 전체 칸(match_fx)
    function boom() {
        explosion();
        const fx = stage.use('matchFx');
        if (fx) {
            const r = canvasRect(timerEl);
            try { fx.boom(r.x + r.w / 2, r.y + r.h / 2); } catch (e) {}
        }
    }

    function sendTimeup(endMs) {
        if (opts.monitor) return;
        if (timeupFor !== endMs) { timeupFor = endMs; timeupTries = 0; }
        clearTimeout(timeupTimer);
        const go = () => {
            const m = lm.get('match') || {};
            const t = m.timer || {};
            if (!t.running || Number(t.end_ms) !== endMs || timeupTries >= 8) return;    // 이미 끝났거나 다른 판이다
            timeupTries++;
            Promise.resolve(lm.cmd('match.timeup', {})).then(r => {
                if (!r || !r.ok) timeupTimer = setTimeout(go, 1000);               // 너무 이르다(409) · 끊김 — 1초 뒤 다시
            }).catch(() => { timeupTimer = setTimeout(go, 1000); });
        };
        go();
    }

    function tick() {
        const m = lm.get('match') || {};
        if (!m.active) return;
        const t = m.timer || {};
        const running = !!t.running;
        const left = running ? Math.max(0, (Number(t.end_ms) || 0) - serverNow()) : (Number(t.left_ms) || 0);
        const sec = Math.ceil(left / 1000);
        const mmss = String(Math.floor(sec / 60)).padStart(2, '0') + ':' + String(sec % 60).padStart(2, '0');
        if (left <= 0) {
            timerEl.removeAttribute('style');
            if (timerEl.textContent !== '시간종료') timerEl.textContent = '시간종료';
            const endMs = Number(t.end_ms) || 0;
            if (running && endMs && exploded !== endMs) {
                exploded = endMs;
                if (onStage && !coverOn(lm)) boom();
                sendTimeup(endMs);
            }
            return;
        }
        if (running && left <= 10000) {
            const k = (10000 - left) / 10000;
            timerEl.style.backgroundColor = 'rgba(255, ' + (255 * (1 - k)) + ', ' + (255 * (1 - k)) + ', 0.5)';
            timerEl.style.boxShadow = '0 0 ' + (k * 40) + 'px rgba(255, 0, 0, ' + k + ')';
            timerEl.style.color = 'rgb(255, ' + (255 * (1 - k)) + ', ' + (255 * (1 - k)) + ')';
            timerEl.style.transform = 'scale(' + (1 + k * 0.3) + ')';
            if (sec !== lastBeepSec && onStage) {
                if (sec > 1) beep(800 + (10 - sec) * 20, 'sine', 0.1, 0.2);
                else if (sec === 1) for (let i = 0; i < 6; i++) setTimeout(() => beep(1200, 'square', 0.08, 0.15), i * 150);
            }
            lastBeepSec = sec;
        } else {
            timerEl.removeAttribute('style');
            lastBeepSec = -1;
        }
        if (timerEl.textContent !== mmss) timerEl.textContent = mmss;
    }

    function render() {
        const m = lm.get('match') || {};
        onStage = (lm.get('show') || {}).stage === 'match';
        fade(onStage && !coverOn(lm));
        // ② 조종실이 끝냈다(ended_at 새 값) — 아직 안 터뜨린 판이고 방금 일이면
        const ea = Number((m.timer || {}).ended_at) || 0;
        if (seenEndedAt === null) seenEndedAt = ea;
        else if (ea && ea !== seenEndedAt) {
            seenEndedAt = ea;
            const endMs = Number((m.timer || {}).end_ms) || 0;
            const fresh = isLive(opts) || serverNow() - ea < 5000;
            if (fresh && exploded !== ea && exploded !== endMs && onStage && !coverOn(lm)) { exploded = ea; boom(); }
        } else if (!ea) seenEndedAt = 0;
        if (!onStage) { prevGap = null; teamKey = null; prevScores = {}; return; }   // 껐다 켜면 새 판 — 옛 1등을 기억한 채 '역전!' 이 안 뜨게
        renderBoard(m);
        flashMaybe(m);
        tick();
    }

    lm.on('match', render);
    lm.on('show', render);
    lm.on('screen', render);
    setInterval(tick, 100);
}
