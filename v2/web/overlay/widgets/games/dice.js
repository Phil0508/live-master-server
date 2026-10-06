/* 🎲 주사위판(부루마블식) — dicegame 조각 + show.stage. 옛 overlay.html dgRender · dgBuild · dgAnimateRoll 을 옮겼다.

   - 보이기: show.stage == 'dicegame' 이고 칸(tiles)이 있을 때. 시작 · 끝 화면이면 내린다(옛 body.stage-on).
     시그니처가 도는 동안은 칸 표(hideInReaction)가 가린다. 방송 시작 전에도 뜬다(옛 것도 방송 꺼짐과 무관했다).
   - 판: 테두리를 도는 고리. 0 = 왼쪽 위 모서리, 시계방향. 칸 한 변은 남는 자리(1030 − 307 = 723)와 폭 1010 에 맞춘다
     (옛 dgBuild 의 MAXW 1010 · MAXH 810 · 칸 40~160). 판은 칸 표에서 가운데(anchor tc) — 옛 '가운데로 모은다' 와 같다.
   - 굴림(ROLL): 눈 · 경로 · 열쇠 카드 · 끌려가기는 전부 서버가 정해 action 에 싣는다. 여기는 그리기만 한다.
     ⏱️ 시간표는 서버 action.plan{rollT, land, gate, afStart, afStep} — **이 굴림을 받은 때부터** 잰다(시계를 비교하지 않는다).
        plan 이 없으면(옛 저장본) 같은 식으로 여기서 계산한다(옛 dgRollPlan).
     ts 는 '이미 그린 굴림인가' 와 '20초 넘게 묵었나'(새로 연 창은 연출 없이 제자리) 에만 쓴다.
   - 손 이동(MOVE)에 tile 이 있으면('원하는 곳으로') 칸을 밝히고 카드(열쇠 칸이면 뽑기 먼저). 그 밖(PLACE · 새로 연 창 ·
     판을 다시 그림 · 무대에 다시 올라옴)은 연출 없이 서버 자리대로 선다(옛 dgRest).
   - 말 = 점수판 선수, 색은 번호 % 4(점수 띠 칩과 같은 색). 같은 칸에 셋 넘게 서면 작게 두 줄.
   - '출발 N번' = 말들의 laps 합.
   - 주사위 점수 띠(dicescore)가 이 판 바로 위에 붙도록 무대에 'diceBoard'(판 상자 재기 · 바뀌면 알림)를 내놓는다.
   - 이 판이 무대에 있으면 stage 모드 'game-dicegame' 을 켠다 → 점수판(ranking)이 비킨다(옛 rankHiddenBy.dice),
     후원 순위 · 최고 후원도 내린다(옛 body.game-on). 규칙은 css/games_b.css.
   ⚠️ 시그 칸의 시그니처는 서버가 대기줄에 play_after(= 굴림 + gate)로 넣는다 — 가리개 · 재생을 여기서 붙잡지 않는다(옛 dgBusyUntil). */
import { esc } from '../../util.js';
import { startClock, serverNow, soundInit, sfx, blip, makeFader, coverOn, isLive, canvasRect } from './dice_kit.js';

const DG_TOP = 307, DG_BOTTOM = 1030;          // 옛 기본 자리 · 아래끝(채팅 구역 위)
const GAP = 6, MAXW = 1010, MAXH = 810, CELL_CAP = 160;
const DG_SIG_BEAT = 1500, DG_CARD_BEAT = 1500, DG_KEY_DRAW = 1700;
const FRESH_ROLL_MS = 20000;

// 3×3 자리에 놓는 점 배치 (행, 열)
const DG_PIPS = { 1: [[2, 2]], 2: [[1, 3], [3, 1]], 3: [[1, 3], [2, 2], [3, 1]],
                  4: [[1, 1], [1, 3], [3, 1], [3, 3]],
                  5: [[1, 1], [1, 3], [2, 2], [3, 1], [3, 3]],
                  6: [[1, 1], [2, 1], [3, 1], [1, 3], [2, 3], [3, 3]] };
// 눈 v 가 앞면으로 오는 회전각
const DG_ROT = { 1: [0, 0], 2: [0, -90], 3: [-90, 0], 4: [90, 0], 5: [0, 90], 6: [0, 180] };
// 면 배치: 1 앞 · 6 뒤 · 2 오른쪽 · 5 왼쪽 · 3 위 · 4 아래 (옛 값 그대로 translateZ 38px)
const DG_FACE_TF = { 1: 'rotateY(0deg)', 6: 'rotateY(180deg)', 2: 'rotateY(90deg)',
                     5: 'rotateY(-90deg)', 3: 'rotateX(90deg)', 4: 'rotateX(-90deg)' };

/* 옛 dgRollPlan — 서버가 plan 을 안 실어 보냈을 때만 쓴다(서버 dicegame.plan 과 같은 식) */
function localPlan(a) {
    a = a || {};
    const rollT = a.manual ? 380 : 250 + (a.dice || []).length * 1300;
    const land = rollT + (a.path || []).length * 300 + 120;
    const tt = (a.tile || {}).type;
    let gate = land + (tt === 'key' ? DG_KEY_DRAW : 0) + (tt === 'sig' ? DG_SIG_BEAT : DG_CARD_BEAT);
    let afStart = 0, afStep = 0;
    const af = a.after;
    if (af) {
        const p2 = af.path || [];
        afStart = tt === 'key' ? 3200 : 1500;
        afStep = af.rev && p2.length > 8 ? Math.max(90, Math.round(2400 / p2.length)) : 220;
        const afterEnd = land + afStart + p2.length * afStep + 120;
        const t2 = (af.tile || {}).type;
        gate = Math.max(gate, afterEnd + (t2 === 'key' ? DG_KEY_DRAW : 0) + DG_CARD_BEAT);
    }
    return { rollT, land, gate, afStart, afStep };
}

function tileIcon(t) {
    switch ((t && t.type) || 'blank') {
        case 'start':   return '🏁';
        case 'mission': return '📜';
        case 'sig':     return '🎵';
        case 'score':   return '💯';
        case 'key':     return '🔑';
        case 'move':    return '🕳️';
        case 'goto':    return '🌀';
        case 'giveall': return '🎁';
        case 'steal':   return '💰';
        default:        return '·';
    }
}

/* 칸 글자 — 라벨이 먼저(꽝 칸이 점수 칸으로 보이지 않게). 세 글자 이하면 한 단계 크게(dg-lbl-s) */
function lblHtml(t) {
    let s = (t && t.label) ? String(t.label) : '';
    if (!s && t && t.type === 'score' && t.points) s = (t.points > 0 ? '+' : '') + t.points + '점';
    if (!s) return '';
    const big = s.replace(/\s/g, '').length <= 3;
    return '<span class="dg-lbl' + (big ? ' dg-lbl-s' : '') + '">' + esc(s) + '</span>';
}

// 고리 번호 → 격자 칸. 0 = 왼쪽 위 모서리, 시계방향
function ringCell(i, cols, rows) {
    if (i < cols) return { c: i + 1, r: 1 };
    if (i < cols + rows - 1) return { c: cols, r: i - cols + 2 };
    if (i < 2 * cols + rows - 2) return { c: cols - (i - (cols + rows - 2)), r: rows };
    return { c: 1, r: rows - (i - (2 * cols + rows - 3)) };
}

function shapeOf(g) {
    return JSON.stringify([g.cols, g.rows, (g.tiles || []).map(t => [t && t.type, t && t.label, t && t.points])]);
}

export function mount(root, lm, opts) {
    startClock();
    soundInit(opts);
    const stage = opts.stage;
    root.innerHTML = '<div class="gb-wrap dg-wrap"><div class="dg-board">'
        + '<div class="dg-lap-banner">🎉 한 바퀴 완주!</div>'
        + '<div class="dg-grid"></div>'
        + '<div class="dg-keydraw" aria-hidden="true"></div>'
        + '<div class="dg-card"></div>'
        + '</div></div>';
    const wrap = root.firstElementChild;
    const boardEl = root.querySelector('.dg-board');
    const grid = root.querySelector('.dg-grid');
    const banner = root.querySelector('.dg-lap-banner');
    const keydraw = root.querySelector('.dg-keydraw');
    const card = root.querySelector('.dg-card');
    const fade = makeFader(wrap, stage);

    let tileEls = [];
    let diceEl = null, sumEl = null, lapsEl = null;
    let pieces = [];
    let lastShape = null, seenTs = 0, wasOn = false, onStage = false;
    let timers = [], busyUntil = 0;            // busyUntil: 연출이 끝나는 때(내 시계) — 그 전에는 말 자리를 덮어쓰지 않는다
    const after = (ms, fn) => { timers.push(setTimeout(fn, ms)); };
    const clearTimers = () => { timers.forEach(t => clearTimeout(t)); timers = []; };
    const tileAt = i => tileEls[i] || null;

    // ── 판 상자 — 점수 띠가 이 위에 붙는다 ──
    const boardFns = [];
    const notifyBoard = () => boardFns.forEach(fn => { try { fn(); } catch (e) { console.error(e); } });
    stage.provide('diceBoard', {
        /* 보일 때만 상자를 준다. {x, y, w, h, k(배율), ow(배율 빼고 잰 판 폭)} — 캔버스 좌표 */
        rect() {
            if (!onStage || wrap.style.display === 'none') return null;
            const r = canvasRect(boardEl);
            if (r.w < 2) return null;
            const ow = boardEl.offsetWidth || r.w;
            return Object.assign(r, { k: r.w / ow, ow });
        },
        visible() { return onStage && !coverOn(lm); },
        onChange(fn) { boardFns.push(fn); },
    });

    function build(g) {
        const cols = parseInt(g.cols, 10) || 7, rows = parseInt(g.rows, 10) || 5;
        // 세로는 남는 자리(옛 dgRoom) — 판 위 307 부터 채팅 구역 위 1030 까지. 점수판은 이 동안 비킨다.
        const roomH = Math.min(MAXH, Math.max(300, DG_BOTTOM - DG_TOP));
        const cell = Math.max(40, Math.min(CELL_CAP,
            Math.floor((MAXW - GAP * (cols - 1)) / cols),
            Math.floor((roomH - GAP * (rows - 1)) / rows)));
        grid.style.setProperty('--dg-cell', cell + 'px');     // 글씨 · 아이콘 · 말이 이걸 따라간다
        grid.style.gridTemplateColumns = 'repeat(' + cols + ', ' + cell + 'px)';
        grid.style.gridTemplateRows = 'repeat(' + rows + ', ' + cell + 'px)';
        const tiles = g.tiles || [];
        let html = '';
        for (let i = 0; i < tiles.length; i++) {
            const p = ringCell(i, cols, rows), t = tiles[i] || {};
            const corner = (i === 0 || i === cols - 1 || i === cols + rows - 2 || i === 2 * cols + rows - 3);
            // 왼쪽 · 오른쪽 끝 열은 이름표를 칸 안쪽으로(가운데 정렬이면 화면 밖으로 잘린다), 맨 윗줄은 칸 안쪽 위로
            const edge = (p.c === 1 ? ' dg-edge-l' : (p.c === cols ? ' dg-edge-r' : '')) + (p.r === 1 ? ' dg-edge-t' : '');
            html += '<div class="dg-tile dg-t-' + esc(t.type || 'blank') + (corner ? ' dg-corner' : '') + edge + '" data-i="' + i + '"'
                + ' style="grid-column:' + p.c + ';grid-row:' + p.r + ';">'
                + '<span class="dg-ico">' + tileIcon(t) + '</span>' + lblHtml(t) + '</div>';
        }
        html += '<div class="dg-center" style="grid-column:2 / ' + cols + ';grid-row:2 / ' + rows + ';">'
            + '<div class="dg-dice"></div><div class="dg-sum"></div><div class="dg-laps"></div></div>';
        grid.innerHTML = html;
        tileEls = [];
        grid.querySelectorAll('.dg-tile').forEach(el => { tileEls[+el.dataset.i] = el; });
        diceEl = grid.querySelector('.dg-dice');
        sumEl = grid.querySelector('.dg-sum');
        lapsEl = grid.querySelector('.dg-laps');
        stage.layoutChanged();
        requestAnimationFrame(notifyBoard);
    }

    // 🧩 말 — 붙어 있던 이름표를 전부 걷고 다시 붙인다(같은 칸에 몇이 섰는지 보고 크기를 정한다)
    function placePieces(movingName, movingPos) {
        grid.querySelectorAll('.dg-piece-wrap').forEach(w => w.remove());
        grid.querySelectorAll('.dg-tile.dg-here').forEach(t => t.classList.remove('dg-here'));
        const list = Array.isArray(pieces) ? pieces : [];
        if (!list.length) return;
        const byTile = new Map();
        list.forEach((p, i) => {
            const moving = movingName != null && p.name === movingName;
            const pos = (moving && movingPos != null) ? movingPos : (parseInt(p.pos, 10) || 0);
            if (!byTile.has(pos)) byTile.set(pos, []);
            byTile.get(pos).push({ p, i, moving });
        });
        byTile.forEach((arr, pos) => {
            const tile = tileAt(pos);
            if (!tile) return;
            tile.classList.add('dg-here');
            const w = document.createElement('span');
            w.className = 'dg-piece-wrap' + (arr.length > 2 ? ' dg-tight' : '');
            arr.forEach(o => {
                const chip = document.createElement('span');
                chip.className = 'dg-piece p' + (o.i % 4) + (o.moving ? ' dg-moving dg-hopping' : '');
                chip.textContent = o.p.name;
                w.appendChild(chip);
            });
            tile.appendChild(w);
        });
    }

    // ── 주사위 ──
    function ensureDice(n) {
        if (!diceEl || diceEl.childElementCount === n) return;
        let html = '';
        for (let k = 0; k < n; k++) {
            let faces = '';
            for (let f = 1; f <= 6; f++) {
                const pips = (DG_PIPS[f] || []).map(p => '<span class="dg-pip" style="grid-row:' + p[0] + ';grid-column:' + p[1] + ';"></span>').join('');
                faces += '<div class="dg-face" style="transform:' + DG_FACE_TF[f] + ' translateZ(38px);">' + pips + '</div>';
            }
            html += '<div class="dg-die"><div class="dg-cube">' + faces + '</div></div>';
        }
        diceEl.innerHTML = html;
    }
    const cube = () => diceEl && diceEl.querySelector('.dg-cube');

    function setSum(dice, upto) {
        if (!sumEl) return;
        const part = (dice || []).slice(0, upto);
        if (!part.length) { sumEl.textContent = ''; return; }
        sumEl.textContent = part.length > 1 ? part.join(' + ') + ' = ' + part.reduce((a, c) => a + c, 0) : String(part[0]);
    }

    // 즉시 세우기 — 안 굴릴 때(빈 눈)는 주사위를 숨긴다(자리는 그대로라 판이 안 흔들린다)
    function showDice(dice) {
        dice = dice || [];
        if (!diceEl) return;
        const idle = !dice.length;
        diceEl.classList.toggle('dg-idle', idle);
        if (idle) { setSum([], 0); return; }
        ensureDice(1);                            // 주사위는 늘 하나 — 눈이 여럿이면 여러 번 구른 것
        const c = cube();
        if (c) {
            const v = dice[dice.length - 1];
            const r = DG_ROT[v] || [0, 0];
            c.style.transition = 'none';
            c.style.transform = 'rotateX(' + r[0] + 'deg) rotateY(' + r[1] + 'deg) rotateZ(0deg)';
            void c.offsetWidth;
            c.style.transition = '';
        }
        setSum(dice, dice.length);
    }

    // 한 번 구르기 — 아무 방향에서 두세 바퀴 돌다가 v 가 앞면으로 선다(멈추는 눈은 서버 값 그대로)
    function tumbleOnce(v) {
        const c = cube();
        if (!c) return;
        const r = DG_ROT[v] || [0, 0];
        c.style.transition = 'none';
        c.style.transform = 'rotateX(' + (Math.random() * 360 - 180) + 'deg) rotateY(' + (Math.random() * 360 - 180) + 'deg)'
            + ' rotateZ(' + (Math.random() * 90 - 45) + 'deg)';
        void c.offsetWidth;
        const turnsX = 360 * (2 + Math.floor(Math.random() * 2));
        const turnsY = 360 * (2 + Math.floor(Math.random() * 2));
        c.style.transition = '';
        c.style.transform = 'rotateX(' + (r[0] + turnsX) + 'deg) rotateY(' + (r[1] + turnsY) + 'deg) rotateZ(0deg)';
    }

    // 주사위 하나가 눈 수만큼 이어 구른다 — 눈이 멈출 때마다 '4 + 2 = 6' 이 쌓인다
    function tumbleSeq(dice) {
        dice = dice || [];
        if (diceEl) diceEl.classList.remove('dg-idle');
        ensureDice(1);
        setSum([], 0);
        dice.forEach((v, k) => {
            after(k * 1300, () => tumbleOnce(v));
            after(k * 1300 + 930, () => { blip(880 + k * 120, 0.05, 0.16); setSum(dice, k + 1); });
        });
    }

    // 🔑 황금열쇠 뽑기 — 다섯 장을 펼쳐 섞고 한 장을 뒤집는다(어느 글인지는 서버가 이미 정했다 — 연출일 뿐)
    function keyDraw(done) {
        const spread = [-210, -105, 0, 105, 210], rot = [-14, -7, 0, 7, 14], PICK = 2;
        const KEY = String.fromCodePoint(0x1F511);
        keydraw.innerHTML = '';
        for (let i = 0; i < spread.length; i++) {
            const c = document.createElement('span');
            c.className = 'kd-card';
            c.style.setProperty('--kx', spread[i] + 'px');
            c.style.setProperty('--kx2', Math.round(spread[i] * 0.45) + 'px');
            c.style.setProperty('--kr', rot[i] + 'deg');
            c.style.animationDelay = (i * 45) + 'ms';
            c.textContent = KEY;
            keydraw.appendChild(c);
        }
        keydraw.classList.add('on');
        const cards = keydraw.querySelectorAll('.kd-card');
        after(1150, () => cards.forEach((c, i) => c.classList.add(i === PICK ? 'kd-pick' : 'kd-drop')));
        after(1700, () => { keydraw.classList.remove('on'); keydraw.innerHTML = ''; if (done) done(); });
    }

    // 도착 칸 카드 — 가운데에 크게 2초(대표님 10-03 '2초만')
    function showCard(act) {
        const t = act.tile || {};
        let ico = tileIcon(t), txt = esc(t.label || ''), sub = '', img = '';
        if (t.type === 'key') {
            ico = '🔑'; txt = esc(act.key || '');
            sub = act.key_effect ? ('황금열쇠 · ' + esc(act.key_effect)) : '황금열쇠';
            if (act.key_kind === 'shield') {           // 🛡️ '획득!' 만 크게 — 쓰는 것은 진행자가 정한다
                ico = '🛡️'; txt = '쉴드권 획득!';
                sub = '황금열쇠' + (act.piece ? ' · ' + esc(act.piece) : '');
            }
        } else if (t.type === 'score') {
            // 라벨이 제목, 점수는 아래줄(꽝! / +2점). 0 이면 '+0점' 이라 쓰지 않는다. 오르는 것은 기여도라고 그대로 말한다
            const pts = t.points ? ((t.points > 0 ? '+' : '') + t.points + '점') : '';
            txt = t.label ? esc(t.label) : (pts || '꽝!');
            const who = act.scored ? esc(act.scored.name) + ' 기여도 ' + (act.scored.points > 0 ? '+' : '') + act.scored.points
                                   : esc(act.score_note || '');
            sub = t.label ? (who || pts) : who;
        } else if (t.type === 'sig') {
            sub = '시그니처 재생!';
            if (t.image) img = '<img src="' + esc(t.image) + '" alt="">';
        } else if (t.type === 'giveall') {
            const ga = act.giveall || {};
            sub = ga.points ? ('전원 ' + (ga.points > 0 ? '+' : '') + ga.points + '점') : '';
            txt = txt || '전원 지급';
        } else if (t.type === 'steal') {
            const st = act.steal || {};
            sub = st.taker
                ? (esc(st.taker) + ' +' + esc(st.gain) + '점 · ' + esc((st.from || []).join(', ')) + ' 각 −' + esc(st.per))
                : esc(act.score_note || '');
            txt = txt || ('각 플레이어에게서 ' + (Number(t.points) || 0) + '점씩');
        } else if (t.type === 'start') {
            txt = txt || '출발!';
        } else if (!txt) {
            txt = '빈 칸';
        }
        card.innerHTML = '<div class="dg-card-ico">' + ico + '</div>'
            + (txt ? '<div class="dg-card-txt">' + txt + '</div>' : '') + img
            + (sub ? '<div class="dg-card-sub">' + sub + '</div>' : '');
        card.classList.add('show');
        after(2000, () => card.classList.remove('show'));
    }

    // 이전 굴림이 남긴 강조를 직접 걷는다(타이머에 맡기면 다음 굴림의 clearTimers 가 그 타이머까지 지워 칸이 영영 밝았다)
    function clearMarks() {
        grid.querySelectorAll('.dg-tile.dg-land, .dg-tile.dg-hop').forEach(t => t.classList.remove('dg-land', 'dg-hop'));
    }

    // 🧍 연출 없이 서버 자리대로 — 새로 연 창 · 판을 다시 그린 직후 · 무대에 다시 올라왔을 때
    function rest() {
        clearTimers();
        busyUntil = 0;
        clearMarks();
        placePieces(null, null);
        showDice([]);
        card.classList.remove('show');
        banner.classList.remove('show');
        keydraw.classList.remove('on');
        keydraw.innerHTML = '';
    }

    function landSound(t) {
        const tt = (t || {}).type, pt = Number((t || {}).points) || 0;
        return tt === 'sig' ? 'dice-sig' : tt === 'key' ? 'dice-key'
            : (tt === 'score' && pt > 0) ? 'dice-score' : tt === 'score' ? 'dice-miss' : 'dice-step';
    }

    function animateRoll(act) {
        clearTimers();
        clearMarks();
        card.classList.remove('show');
        const plan = (act.plan && typeof act.plan.land === 'number') ? act.plan : localPlan(act);
        busyUntil = Date.now() + Math.max(plan.gate, plan.land + 4200);
        // ① 주사위 — 현실에서 굴렸으면(manual) 화면에서 또 구르지 않고 나온 눈만 크게
        if (act.manual) { showDice(act.dice); blip(1040, 0.05, 0.16); }
        else { tumbleSeq(act.dice); sfx('dice-roll'); }
        // ② 다 구른 뒤에 말이 한 칸씩 총총
        (act.path || []).forEach((pos, k) => {
            after(plan.rollT + k * 300, () => {
                placePieces(act.piece, pos);
                blip(500 + k * 30, 0.05, 0.16);
                const t = tileAt(pos);
                if (t) { t.classList.add('dg-hop'); after(260, () => t.classList.remove('dg-hop')); }
            });
        });
        // 다 끝나면 주사위는 다시 숨긴다
        after(plan.land + 4200, () => showDice([]));
        // ③ 도착 — 칸 강조 + 카드(+ 한 바퀴 배너)
        after(plan.land, () => {
            const t = tileAt(act.to);
            if (t) { t.classList.add('dg-land'); after(4200, () => t.classList.remove('dg-land')); }
            const tt = (act.tile || {}).type;
            sfx(landSound(act.tile));
            if (tt !== 'sig' && tt !== 'key' && tt !== 'score') blip(1040, 0.05, 0.16);
            if (tt === 'key') keyDraw(() => showCard(act));
            else showCard(act);
            if (act.lap) {
                banner.classList.add('show');
                after(3200, () => banner.classList.remove('show'));
                after(120, () => sfx('dice-start'));
            }
            // 🕳️ 싱크홀 · 블랙홀 · 열쇠 이동 — 카드를 읽을 틈을 준 뒤에 끌고 간다(블랙홀은 거꾸로, 길면 빠르게)
            const af = act.after;
            if (!af) return;
            const p2 = af.path || [];
            const START = plan.afStart, STEP = plan.afStep;
            after(START, () => sfx('dice-miss'));
            p2.forEach((pos, k) => {
                after(START + k * STEP, () => {
                    placePieces(act.piece, pos);
                    blip(320 + k * 20, 0.05, 0.16);
                    const t2 = tileAt(pos);
                    if (t2) { t2.classList.add('dg-hop'); after(200, () => t2.classList.remove('dg-hop')); }
                });
            });
            after(START + p2.length * STEP + 120, () => {
                placePieces(act.piece, af.to);
                const t3 = tileAt(af.to);
                if (t3) { t3.classList.add('dg-land'); after(3000, () => t3.classList.remove('dg-land')); }
                // 끌려간 자리의 칸도 제 일을 한다 — 카드를 다시(열쇠면 뽑기 연출부터)
                const t2 = af.tile || {};
                if (t2.type && t2.type !== 'blank' && t2.type !== 'start') {
                    sfx(t2.type === 'sig' ? 'dice-step' : landSound(t2));
                    const showAfter = () => showCard({ tile: t2, key: af.key, scored: af.scored, score_note: af.note,
                                                       key_effect: af.key_effect, key_kind: af.key_kind, piece: act.piece,
                                                       giveall: af.giveall, steal: af.steal });
                    if (t2.type === 'key') keyDraw(showAfter); else showAfter();
                }
            });
        });
    }

    function render() {
        const g = lm.get('dicegame') || {};
        const st = (lm.get('show') || {}).stage;
        onStage = st === 'dicegame' && (g.tiles || []).length > 0;
        stage.setMode('game-dicegame', onStage);
        fade(onStage && !coverOn(lm));
        if (!onStage) {
            clearTimers();
            busyUntil = 0;
            wasOn = false;
            notifyBoard();
            return;
        }
        const cameBack = !wasOn;               // 다른 판이 올랐다 내려와 주사위판이 다시 올라왔다
        wasOn = true;
        const shape = shapeOf(g);
        const rebuilt = shape !== lastShape;
        if (rebuilt) { lastShape = shape; build(g); }
        pieces = Array.isArray(g.pieces) ? g.pieces : [];   // 판을 안 다시 그려도 말 목록은 매번(이름 바꿈 · 손 이동)
        const act = g.action || {};
        const ts = Number(act.ts) || 0;
        // 실시간으로 막 온 굴림은 늘 새것. 통째로 받은 것(새로 연 창 · 다시 붙음)은 서버 시계로 20초 안의 것만
        const fresh = !!ts && (isLive(opts) || serverNow() - ts < FRESH_ROLL_MS);
        if (act.type === 'ROLL' && ts !== seenTs && fresh) {
            seenTs = ts;
            if (rebuilt || cameBack) placePieces(act.piece, act.from);    // 새로 그린 판엔 말이 없다 — 출발 자리에 먼저 세운다
            animateRoll(act);
        } else if (act.type === 'MOVE' && act.tile && ts !== seenTs && fresh) {
            // 🎯 '원하는 곳으로' — 굴림 연출 없이 말을 세우고 그 칸을 밝히고 카드만
            seenTs = ts;
            clearTimers();
            clearMarks();
            placePieces(null, null);
            showDice([]);
            busyUntil = Date.now() + 4200;
            const lt = tileAt(act.to);
            if (lt) { lt.classList.add('dg-land'); after(4200, () => lt.classList.remove('dg-land')); }
            if ((act.tile || {}).type === 'key') keyDraw(() => showCard(act)); else showCard(act);
        } else if (ts !== seenTs || rebuilt || cameBack) {
            seenTs = ts;
            rest();
        } else if (Date.now() > busyUntil) {
            placePieces(null, null);           // 연출 중이 아니면 말 자리를 서버 값으로(이름 바꿈 · 명단 바뀜)
        }
        const laps = pieces.reduce((a, p) => a + (parseInt(p.laps, 10) || 0), 0);
        if (lapsEl) lapsEl.textContent = laps ? ('출발 ' + laps + '번') : '';
        notifyBoard();
    }

    lm.on('dicegame', render);
    lm.on('show', render);
    lm.on('screen', render);
    if (stage.onLayout) stage.onLayout(notifyBoard);
}
