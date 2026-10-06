/* 🃏 시그 뒤집기 — siggame 조각 + show.stage. 옛 overlay.html sgRenderGame · sgSyncTimer · sgBuild · 도장 · 올클리어를 옮겼다.

   - 보이기: show.stage == 'siggame' 이고 카드가 있을 때. 투명도 = siggame.opacity. 시작 · 끝 화면이면 내린다.
     시그니처가 도는 동안은 칸 표(hideInReaction)가 가린다. 방송 시작 전에도 뜬다(옛 것도 방송 꺼짐과 무관했다).
   - 덮인 카드는 번호만(서버가 사진 · 이름을 안 보낸다). 열린 카드 = 사진 + '이름 · 금액'.
   - 목표 = flippedAt 이 있는 카드. compact 이고 목표가 있고 까보기 중이 아니면 목표만 한 줄(싼 것부터, 같으면 번호).
   - 머리글: 왼쪽 = 앞으로 받아야 할 돈(목표 중 아직 doneAt 없는 것의 합) · 타이머 · 진행 점(max(target, 목표 수), 앞에서부터 받은 수).
     타이머: PLAYING 이면 (expiresAt − 서버 시각), 아니면 timeLeft. 남은 30초부터 빨강(urgent), 0 이면 회색 '시간 종료'(timeup).
   - 연출 신호 action(ts 가 새로울 때 한 번): PLACE 깔기(위에서 하나씩) · SHUFFLE 섞기(1~4번 연출) · PEEK 나머지 까보기(6초) ·
     ALLCLEAR 왼쪽부터 하나씩 도장 → 배너. 뒤집은 카드는 flippedAt 부터 2.6초 크게, 받은 카드는 doneAt 부터 8초 안이면 도장.
     ⚠️ 시각은 전부 서버 시계(서버가 찍은 값) — dice_kit 의 serverNow 로 잰다(옛 serverTimeOffset).
   - 까보기가 끝나면(ts + 6초) 서버가 스스로 덮는다. 여기서도 sig.peek_end 를 한 번 보낸다(로그인 없이 — ?monitor=1 은 안 보냄).
   - 이 판이 무대에 있으면 stage 모드 'game-siggame' — 후원 순위 · 최고 후원이 비킨다(옛 body.game-on). 규칙은 css/games_b.css.
   ✂️ 올클리어 클립 저장(옛 clipSave)은 stage.use('clip').allClear(ts) 한 줄 — 저장 여부 · 시각은 widgets/more/clip.js 가 정한다. */
import { esc } from '../../util.js';
import { startClock, serverNow, soundInit, sgClear, sgAllClear, sgSoundsPrepare, makeFader, coverOn } from './dice_kit.js';

const SG_POP_MS = 2600;        // 방금 뒤집은 카드가 크게 보이는 시간
const SG_SHUFFLE_MS = 1200;    // 섞기 연출 길이
const SG_PEEK_MS = 6000;       // 까보기 — 서버 PEEK_MS 와 같아야 한다
const MOTION_MS = 2200;        // 가장 긴 섞기(1.2초) + 카드별 시차 + 여유 — 이 동안만 판 밖을 자른다

function fmt(sec) {
    sec = Math.max(0, Math.floor(sec));
    return String(Math.floor(sec / 60)).padStart(2, '0') + ':' + String(sec % 60).padStart(2, '0');
}

export function mount(root, lm, opts) {
    startClock();
    soundInit(opts);
    sgSoundsPrepare();          // CLEAR 음원은 미리 받아 둔다(처음 뒤집을 때 늦지 않게)
    const stage = opts.stage;
    root.innerHTML = '<div class="gb-wrap sg-wrap"><div class="sg-op">'
        + '<div class="sg-board"><div class="sg-header">'
        +   '<span class="sg-header-title">0원</span><span class="sg-timer">10:00</span><span class="sg-progress"></span>'
        + '</div><div class="sg-grid"></div></div>'
        + '<div class="sg-allclear"><span>ALL CLEAR</span></div>'   // 판 위에 겹쳐 뜬다(자리를 차지하지 않는다)
        + '</div></div>';
    const wrap = root.firstElementChild;
    const op = root.querySelector('.sg-op');
    const board = root.querySelector('.sg-board');
    const head = root.querySelector('.sg-header');
    const totalEl = root.querySelector('.sg-header-title');
    const timerEl = root.querySelector('.sg-timer');
    const progress = root.querySelector('.sg-progress');
    const grid = root.querySelector('.sg-grid');
    const allBanner = root.querySelector('.sg-allclear');
    const fade = makeFader(wrap, stage);

    let layoutKey = null, lastActionTs = 0, timerTick = null, repaintTimer = null;
    let peekTs = 0, peekTimer = null, peekEndSent = 0, allClearTs = 0, allTimers = [];
    let wasOn = false;
    const seenDone = new Set();       // 이미 본 달성(id:doneAt) — 갱신 때마다 옛 도장이 다시 터지지 않게
    const held = new Set();           // 올클리어 연출이 붙잡고 있는 카드 — 갱신이 도장을 미리 찍지 않게

    const G = () => lm.get('siggame') || {};
    const clearAllTimers = () => { allTimers.forEach(t => clearTimeout(t)); allTimers = []; };

    function build(shown, cols) {
        const rows = Math.max(1, Math.ceil(shown.length / cols));
        const gap = 8;
        // 판(.sg-board)의 테두리 · 안쪽 여백을 뺀 실제 폭으로 카드를 잡는다(바깥 폭 700 으로 잡으면 판 밖으로 삐져나온다)
        let avail = root.offsetWidth || 700;
        const cs = getComputedStyle(board);
        const inner = board.clientWidth - (parseFloat(cs.paddingLeft) || 0) - (parseFloat(cs.paddingRight) || 0);
        if (inner > 0) avail = inner;
        const cw = Math.max(30, Math.floor((avail - gap * (cols - 1)) / cols));
        const ch = Math.round(cw * 9 / 16);              // 16:9 — 시그 사진이 가로형
        grid.style.gridTemplateColumns = 'repeat(' + cols + ', ' + cw + 'px)';
        grid.style.gridTemplateRows = 'repeat(' + rows + ', ' + ch + 'px)';
        grid.style.setProperty('--sg-cw', cw + 'px');
        grid.innerHTML = shown.map(c =>
            '<div class="sg-card" data-id="' + esc(c.id) + '"><div class="sg-inner">'
            + '<div class="sg-front"><img alt=""><div class="sg-title"></div><div class="sg-stamp"><span>CLEAR</span></div></div>'
            + '<div class="sg-back"><span class="sg-num">' + esc(c.id) + '</span></div>'
            + '</div></div>').join('');
    }

    function syncTimer(g) {
        if (timerTick) { clearInterval(timerTick); timerTick = null; }
        const t = (g && g.timer) || {};
        const paint = () => {
            const left = (t.status === 'PLAYING' && t.expiresAt) ? (t.expiresAt - serverNow()) / 1000 : (t.timeLeft || 0);
            const txt = left <= 0 && t.status === 'PLAYING' ? '시간 종료' : fmt(left);
            if (timerEl.textContent !== txt) timerEl.textContent = txt;
            // 다 됐으면 '급함(빨강)' 이 아니라 '끝남(회색)'
            head.classList.toggle('urgent', t.status === 'PLAYING' && left <= 30 && left > 0);
            head.classList.toggle('timeup', t.status === 'PLAYING' && left <= 0);
            if (left <= 0 && timerTick) { clearInterval(timerTick); timerTick = null; }
        };
        paint();
        if (t.status === 'PLAYING') timerTick = setInterval(paint, 200);
    }

    // 한 장이 방금 달성됐을 때 — 그 카드만 쾅(소리는 올클리어 때만)
    function stampOne(el, index, withSound) {
        if (!el) return;
        held.delete(el);
        el.classList.add('cleared');
        el.classList.remove('stamping');
        void el.offsetWidth;
        el.classList.add('stamping');
        if (withSound) sgClear(index);
        setTimeout(() => el.classList.remove('stamping'), 600);
    }

    // 올클리어 — 찍힌 것까지 다 걷고 왼쪽부터 0.7초마다 하나씩 다시 찍은 뒤 배너
    function playAllClear(goalCount) {
        clearAllTimers();
        const cards = [...grid.children];
        board.classList.add('allclear');
        grid.classList.add('allclear');
        cards.forEach(c => c.classList.remove('stamping'));
        held.clear();
        cards.forEach(el => {
            if (!el.classList.contains('cleared') && !el.classList.contains('done')) return;
            el.classList.remove('cleared');
            held.add(el);
        });
        const STEP = 700;
        cards.forEach((el, i) => allTimers.push(setTimeout(() => stampOne(el, i, true), 250 + i * STEP)));
        const finale = 250 + goalCount * STEP + 150;
        allTimers.push(setTimeout(() => {
            allBanner.classList.remove('on'); void allBanner.offsetWidth; allBanner.classList.add('on');
            sgAllClear();
        }, finale));
        allTimers.push(setTimeout(() => {
            allBanner.classList.remove('on');
            board.classList.remove('allclear');
            grid.classList.remove('allclear');
            held.clear();
            try { renderGame(); } catch (e) {}
        }, finale + 3200));
    }

    function sendPeekEnd(ts) {
        if (opts.monitor || peekEndSent === ts) return;
        peekEndSent = ts;
        try { lm.cmd('sig.peek_end', {}).catch(() => {}); } catch (e) {}
    }

    function renderGame() {
        const g = G();
        const cards = g.cards || [];
        const onStage = (lm.get('show') || {}).stage === 'siggame' && cards.length > 0;
        stage.setMode('game-siggame', onStage);
        fade(onStage && !coverOn(lm));
        if (!onStage) {
            clearAllTimers();
            board.classList.remove('sg-clip', 'allclear');
            allBanner.classList.remove('on');
            seenDone.clear();
            held.clear();
            grid.innerHTML = '';
            layoutKey = null;
            progress.innerHTML = '';
            if (timerTick) { clearInterval(timerTick); timerTick = null; }
            wasOn = false;
            return;
        }
        const cameBack = !wasOn;
        wasOn = true;
        op.style.opacity = g.opacity != null ? String(g.opacity) : '1';

        const now = serverNow();
        const goals = cards.filter(c => c.flippedAt);
        const target = Math.max(1, g.target || 5);
        const act = g.action || {};
        const peeking = act.type === 'PEEK' && !act.closed && (now - (act.ts || 0)) < SG_PEEK_MS;
        const compact = !!g.compact && goals.length > 0 && !peeking;
        const sortedGoals = goals.slice().sort((a, b) => ((a.amount || 0) - (b.amount || 0)) || ((a.id || 0) - (b.id || 0)));
        const shown = compact ? sortedGoals : cards;
        const cols = compact ? shown.length : Math.max(1, g.cols || 4);

        const key = (compact ? 'C' : 'F') + shown.length + '|' + cols + '|' + shown.map(c => c.id).join(',');
        if (key !== layoutKey) { layoutKey = key; build(shown, cols); }

        // 다시 올라온 판 · 새로 연 창에서는 지난 신호를 다시 틀지 않는다(서버 시계로 몇 초 안의 것만)
        let isNewAction = !!act.ts && act.ts !== lastActionTs;
        if (isNewAction) {
            lastActionTs = act.ts;
            if (cameBack && now - act.ts > MOTION_MS) isNewAction = false;
        }
        const shuffling = act.type === 'SHUFFLE' && (now - act.ts) < SG_SHUFFLE_MS;

        // 🔍 까보기 — 끝나는 때에 한 번 다시 그려 원래대로(서버도 덮는다). peek_end 도 그때 보낸다
        if (act.type === 'PEEK' && !act.closed && act.ts !== peekTs) {
            peekTs = act.ts;
            clearTimeout(peekTimer);
            const wait = Math.max(200, SG_PEEK_MS - (now - act.ts)) + 80;
            const pts = act.ts;
            peekTimer = setTimeout(() => { sendPeekEnd(pts); layoutKey = null; renderGame(); }, wait);
        }

        // 깔기 · 섞기가 도는 동안만 판 밖을 잘라낸다
        const inMotion = (act.type === 'PLACE' || act.type === 'SHUFFLE') && (now - act.ts) < MOTION_MS;
        board.classList.toggle('sg-clip', inMotion);

        // 새 판 신호면 남은 올클리어 · 까보기 예약을 걷는다(빈 판 위에 ALL CLEAR 가 뜨지 않게)
        if (isNewAction && (act.type === 'PLACE' || act.type === 'SHUFFLE')) {
            clearAllTimers();
            clearTimeout(peekTimer);
            allBanner.classList.remove('on');
            board.classList.remove('allclear');
            grid.classList.remove('allclear');
            held.clear();
            build(shown, cols);                 // 새 판은 새 카드로(옛 것은 다음 그리기에 다시 만들었다 — 연출 도중이었다)
            layoutKey = key;
        }

        const els = grid.children;
        for (let i = 0; i < els.length && i < shown.length; i++) {
            const el = els[i], c = shown[i];
            const revealed = c.state === 'REVEALED' || peeking;     // 까보기 중엔 안 뽑힌 카드도 앞면(구경용)
            const isGoal = revealed && !!c.flippedAt;
            const done = !!c.doneAt;
            // 커지는 건 뒤집는 순간에만. 시계가 어긋나 flippedAt 이 미래여도 확대로 치지 않는다
            const flipDt = c.flippedAt ? (now - c.flippedAt) : -1;
            const popped = flipDt >= 0 && flipDt < SG_POP_MS;
            el.querySelector('.sg-inner').classList.toggle('flipped', !revealed);
            // 커진 상태는 카드마다 스스로 풀리는 타이머로 — '다음 그리기' 에만 맡기면 커진 채 굳었다(옛 82초 사고)
            if (popped) {
                el.style.transform = '';
                el.classList.add('popped');
                clearTimeout(el._popTimer);
                const leftMs = Math.min(SG_POP_MS, Math.max(0, SG_POP_MS - flipDt));
                el._popTimer = setTimeout(() => { el.classList.remove('popped'); el.style.transform = 'none'; }, leftMs + 60);
            } else {
                clearTimeout(el._popTimer);
                el.classList.remove('popped');
                el.style.transform = 'none';
            }
            el.classList.toggle('done', done);
            el.classList.toggle('todo', isGoal && !done);
            if (held.has(el)) el.classList.remove('cleared');
            else el.classList.toggle('cleared', isGoal && done);

            const img = el.querySelector('.sg-front img');
            const want = revealed ? (c.image || '') : '';
            if (img.getAttribute('src') !== want) { if (want) img.setAttribute('src', want); else img.removeAttribute('src'); }
            const cap = el.querySelector('.sg-title');
            const title = revealed ? ((c.title || '') + (c.amount ? ' · ' + Number(c.amount).toLocaleString() + '원' : '')) : '';
            if (cap.textContent !== title) cap.textContent = title;

            if (isNewAction) {
                el.classList.remove('fly', 'sg-sh1', 'sg-sh2', 'sg-sh3', 'sg-sh4');
                void el.offsetWidth;
                if (act.type === 'PLACE') {
                    el.style.animationDelay = (i * 50) + 'ms';
                    el.classList.add('fly');
                } else if (act.type === 'SHUFFLE') {
                    // 흩어지는 방향은 번호와 신호 시각으로 — 매번 새로 뽑으면 후원 하나에도 카드가 튄다
                    const s1 = (act.ts + c.id * 7919) % 1000 / 1000;
                    const s2 = (act.ts + c.id * 104729) % 1000 / 1000;
                    el.style.setProperty('--tx', ((s1 - 0.5) * 280).toFixed(0) + 'px');
                    el.style.setProperty('--ty', ((s2 - 0.5) * 180).toFixed(0) + 'px');
                    el.style.animationDelay = (s1 * 100).toFixed(0) + 'ms';
                    el.classList.add('sg-sh' + (((act.animIndex || 1) - 1) % 4 + 1));
                }
            } else if (!shuffling) {
                el.classList.remove('sg-sh1', 'sg-sh2', 'sg-sh3', 'sg-sh4');
            }
        }

        // 왼쪽 = 앞으로 더 받아내야 할 돈(받아내면 줄어든다 — 사장님 규칙)
        const sum = goals.reduce((a, c) => a + (c.doneAt ? 0 : (Number(c.amount) || 0)), 0);
        const txt = sum.toLocaleString() + '원';
        if (totalEl.textContent !== txt) totalEl.textContent = txt;

        // 진행 점(●●●○○)
        const doneCount = goals.filter(c => c.doneAt).length;
        const wantDots = Math.max(target, goals.length);
        if (progress.children.length !== wantDots) progress.innerHTML = Array.from({ length: wantDots }, () => '<div class="sg-dot"></div>').join('');
        for (let k = 0; k < progress.children.length; k++) progress.children[k].classList.toggle('done', k < doneCount);

        // ── 연출 판단 ── 방금 달성된 카드만 도장(올클리어 중에는 건너뛴다)
        const allClearRunning = act.type === 'ALLCLEAR' && (now - act.ts) < 12000;
        if (!allClearRunning) {
            shown.forEach((c, i) => {
                if (!c.doneAt || !c.flippedAt) return;
                const k = c.id + ':' + c.doneAt;
                if (seenDone.has(k)) return;
                seenDone.add(k);
                if (now - c.doneAt < 8000) stampOne(els[i], goals.filter(x => x.doneAt && x.doneAt <= c.doneAt).length - 1);
            });
        }
        if (act.type === 'ALLCLEAR' && act.ts !== allClearTs && (now - act.ts) < 8000) {
            allClearTs = act.ts;
            // ✂️ 올클리어 순간 — 쇼츠 클립 예약(조건 · 시각은 widgets/more/clip.js)
            try { const clip = stage.use('clip'); if (clip) clip.allClear(act.ts); } catch (e) { /* 클립이 넘어져도 연출은 그대로 */ }
            shown.forEach(c => { if (c.doneAt) seenDone.add(c.id + ':' + c.doneAt); });
            playAllClear(goals.length);
        }

        // 시간이 지나면 저절로 풀리는 것(크게 · 섞기 · 자르기)은 그때 한 번 더 그린다
        if (repaintTimer) { clearTimeout(repaintTimer); repaintTimer = null; }
        const waits = [];
        cards.forEach(c => {
            if (c.flippedAt && now - c.flippedAt < SG_POP_MS && now >= c.flippedAt) waits.push(SG_POP_MS - (now - c.flippedAt));
            if (c.doneAt && now - c.doneAt < SG_POP_MS && now >= c.doneAt) waits.push(SG_POP_MS - (now - c.doneAt));
        });
        if (shuffling) waits.push(SG_SHUFFLE_MS - (now - act.ts));
        if (inMotion) waits.push(MOTION_MS - (now - act.ts));
        if (waits.length) repaintTimer = setTimeout(() => renderGame(), Math.max(30, Math.min.apply(null, waits) + 30));
    }

    function update() {
        try { renderGame(); syncTimer(G()); }
        catch (e) { console.error('[시그게임] 화면 갱신 실패 — 방송은 계속됩니다:', e); }
    }

    lm.on('siggame', update);
    lm.on('show', update);
    lm.on('screen', update);
}
