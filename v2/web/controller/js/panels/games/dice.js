/* 🎲 주사위게임(부루마블식) — 말 · 굴리기 · 쉴드권 · 전용 점수판 · 판 만들기 · 칸 편집 · 황금열쇠 · 말 옮기기.

   누구 차례? = 이 화면에서만 고르는 것(굴려도 안 바뀐다 — 대표님 09-30). 안 고르면 서버의 지금 차례(pieces[turn]).
   [굴리기] dice.roll{piece?} · 눈 1~6 dice.roll{value, piece?}(현실에서 굴린 눈) — 결과 · 연출은 서버가 정한다.
   쉴드권 [사용함] dice.shield{piece, on:false} — 저절로 막지 않는다(10-03).
   전용 판 ±5 dice.board{do:'add'} · 전원 0점 dice.board{do:'reset'} · 엑셀판으로 옮기기 dice.settle(진짜 기여도로 — 되돌리기 장부에 남는다)
   판 만들기 dice.setup · 22칸 기본판 / 손그림판 dice.preset{name, tiles_only?} · 칸 dice.tile · 덱 dice.keys · 말 옮기기 dice.move · 출발로 dice.reset
   ⚠️ 시그가 재생 중이면 방송판이 가려져 굴림이 안 보인다 — 띠로 알리고, 그래도 누르면 한 번 묻는다. */
import { h, num, won, signed } from '../../util.js';
import { head, memo, syncVal, okToTake, tile, loadSigs, sigsNow, numInput, toInt, onEnter, STAGE_LABEL } from './common.js';

const TYPES = [['blank', '빈칸'], ['mission', '📜 미션'], ['sig', '🎵 시그니처'], ['score', '💯 점수'], ['key', '🔑 황금열쇠'],
    ['move', '🕳️ 이동'], ['goto', '🌀 특정 칸으로'], ['giveall', '🎁 전원 지급'], ['steal', '💰 뺏어오기']];
const UNIT = { score: '점 (음수면 차감)', move: '칸 (음수면 뒤로)', goto: '번 칸으로', giveall: '점씩 모두에게', steal: '점씩 한 사람마다' };

export function mountDice(el, ctx) {
    const paint = memo();
    let g = {}, pv = {}, slices = {}, pick = '';
    const myLog = [];

    const hd = head('🎲 주사위', async on => {
        if (on) {
            if (!(g.tiles || []).length) { ctx.toast('먼저 판을 깔아 주세요 — 아래 «판 만들기»', 'err'); return; }
            if (!(await okToTake(ctx, 'dicegame', '주사위판'))) return;
            const res = await ctx.run('show.stage', { stage: 'dicegame' });
            if (res.ok) ctx.toast('주사위판을 방송에 띄웠어요', 'ok');
        } else {
            const res = await ctx.run('show.stage', { stage: null });
            if (res.ok) ctx.toast('주사위판을 내렸어요 (말 자리 · 점수는 그대로)', 'info');
        }
    });

    const rxWarn = h('div', { class: 'gm-warn big', role: 'status', hidden: true }, '🎵 시그 재생 중 — 지금 굴리면 방송 화면에서 굴림이 안 보여요. 끝나고 굴려 주세요');
    const players = h('div', { class: 'gm-players' });
    const shields = h('div', { class: 'gm-row gm-shields', hidden: true });

    const rollT = tile('굴리기', '서버가 무작위로 · 고른 사람 그대로', () => roll(null), 'go');
    const eyes = h('div', { class: 'gm-tile gm-eyes' }, h('span', { class: 'gm-ts' }, '직접 굴렸으면 나온 눈'),
        h('span', { class: 'gm-eyerow' }, [1, 2, 3, 4, 5, 6].map(v => h('button', { type: 'button', class: 'gm-eye', 'aria-label': `눈 ${v}`, onclick: () => roll(v) }, String(v)))));
    const big = h('div', { class: 'gm-big' }, h('b', null, '–'), h('small', null, '마지막 눈'));
    const status = h('p', { class: 'gm-status' });

    /* 전용 점수판 */
    const board = h('div', { class: 'gm-board' });
    const log = h('ol', { class: 'gm-log' });

    /* 판 만들기 */
    const sel = (opts, label) => h('select', { class: 'gm-sel', 'aria-label': label }, opts.map(([v, t]) => h('option', { value: String(v) }, t)));
    const cols = sel([4, 5, 6, 7, 8, 9, 10].map(v => [v, v + '칸']), '가로');
    const rows = sel([3, 4, 5, 6, 7, 8].map(v => [v, v + '칸']), '세로');
    const dice = sel([[1, '1개 (1~6칸)'], [2, '2개 (2~12칸)']], '주사위 수');
    const rprice = numInput({ class: 'gm-in num w120', 'aria-label': '한 판 값(원)' });
    const lap = numInput({ class: 'gm-in num w64', 'aria-label': '한 바퀴 기여도' });
    const setupSum = h('small');
    const tilesSum = h('small');
    const keysSum = h('small');

    const tileBox = h('div', { class: 'gm-tilelist' });
    const keysTa = h('textarea', { class: 'gm-ta', rows: 6, placeholder: '한 줄에 한 장\n물 한 컵 원샷\n뒤로 3칸\n기여도 20', 'aria-label': '황금열쇠 덱' });
    const posIn = numInput({ class: 'gm-in num w64', placeholder: '0', 'aria-label': '옮길 칸 번호' });

    const foldSetup = h('details', { class: 'gm-fold' }, h('summary', null, '판 만들기 ', setupSum),
        h('div', { class: 'gm-fold-body' },
            h('div', { class: 'gm-row' }, h('span', { class: 'gm-lbl' }, '가로'), cols, h('span', { class: 'gm-lbl' }, '세로'), rows, h('span', { class: 'gm-lbl' }, '주사위'), dice),
            h('div', { class: 'gm-row' }, h('span', { class: 'gm-lbl' }, '한 판 값'), rprice, h('span', null, '원'),
                h('span', { class: 'gm-lbl' }, '한 바퀴 기여도'), lap),
            h('div', { class: 'gm-row' }, h('button', { type: 'button', class: 'btn pri', onclick: setup }, '판 만들기'),
                h('span', { class: 'gm-info' }, '같은 번호 칸 내용은 남고, 말은 전부 출발로 가요')),
            h('div', { class: 'gm-row' },
                h('button', { type: 'button', class: 'btn sm gold', onclick: () => preset('basic22') }, '22칸 기본판'),
                h('button', { type: 'button', class: 'btn sm gold', onclick: () => preset('draw22') }, '22칸 손그림판'),
                h('button', { type: 'button', class: 'btn sm', onclick: () => preset('draw22', true) }, '칸만 다시 깔기 (손그림판)'))));
    const foldTiles = h('details', { class: 'gm-fold' }, h('summary', null, '칸 편집 ', tilesSum),
        h('div', { class: 'gm-fold-body' }, h('p', { class: 'gm-info' }, '종류를 고르고 내용을 적으면 바로 저장돼요. 시그 칸 기여도 = 시그 값 − 한 판 값.'), tileBox));
    const foldKeys = h('details', { class: 'gm-fold' }, h('summary', null, '🔑 황금열쇠 덱 ', keysSum),
        h('div', { class: 'gm-fold-body' },
            h('p', { class: 'gm-info' }, '줄마다 한 장(40장까지). 열쇠 칸에 서면 서버가 무작위로 뽑아요. 뽑기 전에는 방송에 안 보여요. \'뒤로 3칸 · 앞으로 2칸 · 출발 · 파산 · 한 번 더 · 쉴드 · 원하는 곳으로 · 꽝 · 기여도 N · N등과 바꾸기\' 는 저절로 됩니다.'),
            keysTa, h('div', { class: 'gm-row' }, h('button', { type: 'button', class: 'btn sm pri', onclick: saveKeys }, '덱 저장'))));
    const foldMove = h('details', { class: 'gm-fold' }, h('summary', null, '말 직접 옮기기 · 출발로 내리기 ', h('small', null, '틀렸을 때만')),
        h('div', { class: 'gm-fold-body' },
            h('div', { class: 'gm-row' }, h('span', null, '고른 말(없으면 차례 말)을'), posIn, h('span', null, '번 칸으로'),
                h('button', { type: 'button', class: 'btn sm', onclick: move }, '옮기기')),
            h('div', { class: 'gm-row' }, h('button', { type: 'button', class: 'btn sm ghost-danger', onclick: resetPieces }, '말 전부 출발로 · 방송에서 내리기'))));
    [foldSetup, foldTiles, foldKeys, foldMove].forEach(f => f.addEventListener('toggle', () => { if (f === foldTiles && f.open) loadSigs().then(() => ctx.rerender()); ctx.rerender(); }));
    onEnter(posIn, move);

    el.append(h('div', { class: 'gm' },
        hd.el, rxWarn,
        h('div', { class: 'gm-sub' }, h('b', null, '누구 차례?'), h('span', { class: 'gm-info' }, '금색 테두리 사람이 굴려요 · 굴려도 안 바뀌어요 — 바꿀 때만 이름을 누르세요')),
        players, shields,
        h('div', { class: 'gm-tiles' }, rollT, eyes, big),
        status,
        h('div', { class: 'gm-two' },
            h('section', { class: 'gm-box' },
                h('div', { class: 'gm-sub' }, h('b', null, '🏆 주사위 점수판'), h('span', { class: 'gm-sp' }),
                    h('button', { type: 'button', class: 'btn sm ghost-danger', onclick: boardReset }, '전원 0점'),
                    h('button', { type: 'button', class: 'btn sm pri', onclick: settle }, '엑셀판으로 옮기기')),
                board,
                h('p', { class: 'gm-info' }, '칸 · 열쇠 점수는 이 판에만 쌓여요. 게임이 끝나면 [엑셀판으로 옮기기] 를 눌러야 진짜 기여도가 됩니다(마이너스도 그대로 · 되돌리기로 취소할 수 있어요).')),
            h('section', { class: 'gm-box' },
                h('div', { class: 'gm-sub' }, h('b', null, '방금 굴린 것'), h('span', { class: 'gm-info' }, '이 창에서 한 것만')),
                log)),
        foldSetup, foldTiles, foldKeys, foldMove));

    /* ── 보내기 ── */
    function rxBusy() {
        const q = slices.queue || {};
        return (q.items || []).length > 0 && !q.paused;
    }
    function who() {
        const ps = g.pieces || [];
        if (pick && ps.some(p => p.name === pick)) return pick;
        return (ps[Number(g.turn) || 0] || {}).name || '';
    }
    function addLog(m) {
        const d = new Date();
        myLog.unshift({ t: String(d.getHours()).padStart(2, '0') + ':' + String(d.getMinutes()).padStart(2, '0'), m });
        myLog.length = Math.min(myLog.length, 8);
        log.replaceChildren(...myLog.map(x => h('li', { class: 'gm-logrow' }, h('span', { class: 'gm-lt' }, x.t), h('span', { class: 'gm-lx wrap' }, x.m))));
    }
    function rollText(d) {
        const landed = d.tile && d.tile.id != null ? d.tile.id : d.to;
        let m = `[${d.piece || '?'}] ${(d.dice || []).join('+')} → ${landed}번 칸`;
        if (d.tile && d.tile.label) m += ` (${d.tile.label})`;
        if (landed !== d.to) m += ` → ${d.to}번으로`;
        if (d.scored) m += ` · ${d.scored.name} ${signed(d.scored.points)}`;
        if (d.lap) m += ' · 🎉 한 바퀴!';
        if (d.contrib) m += ` · ${d.contrib.name} 기여도 +${d.contrib.points}`;
        if (d.lap_contrib) m += ` · ${d.lap_contrib.name} 한 바퀴 +${d.lap_contrib.points}`;
        if (d.giveall && d.giveall.points) m += ` · 전원 ${signed(d.giveall.points)}`;
        if (d.steal) m += ` · 💰 ${d.steal.taker} 이(가) ${(d.steal.from || []).length}명에게서 ${d.steal.per}점씩 (+${d.steal.gain})`;
        if (d.key) m += ` · 🔑 ${d.key}${d.key_effect ? ' → ' + d.key_effect : ''}`;
        if (d.again) m += ' · 한 번 더!';
        return m;
    }
    async function roll(value) {
        if (rxBusy()) {
            const ok = await ctx.confirm({ title: '🎵 시그 재생 중이에요', body: '지금 굴리면 방송 화면에서 굴림이 안 보여요.\n시그가 끝나면 말은 이미 가 있고 카드도 지나가 있어요.\n\n그래도 굴릴까요?', ok: '그래도 굴리기', cancel: '기다리기' });
            if (!ok) return;
        }
        const data = {};
        if (pick && (g.pieces || []).some(p => p.name === pick)) data.piece = pick;
        if (value) data.value = value;
        const res = await ctx.run('dice.roll', data);
        if (!res.ok) return;
        const m = rollText(res);
        ctx.toast('🎲 ' + m, 'ok', 5000);
        if (res.note) ctx.toast('⚠️ ' + res.note, 'info', 6000);
        addLog(m);
    }
    async function useShield(n) {
        const res = await ctx.run('dice.shield', { piece: n, on: false });
        if (res.ok) ctx.toast(`🛡️ ${n} 쉴드권 사용 처리`, 'ok');
    }
    async function boardAdd(n, d) {
        const res = await ctx.run('dice.board', { do: 'add', name: n, pts: d });
        if (res.ok) ctx.toast(`🎲 ${n} ${signed(d)}점 (주사위 점수판)`, 'ok');
    }
    async function boardReset() {
        const ok = await ctx.confirm({ title: '주사위 점수판을 0점으로?', body: '주사위 전용 점수판을 전원 0점으로 되돌립니다.\n엑셀판(진짜 점수 · 기여도)은 안 건드려요.', ok: '전원 0점', cancel: '그대로 두기' });
        if (!ok) return;
        const res = await ctx.run('dice.board', { do: 'reset' });
        if (res.ok) ctx.toast('🏆 주사위 점수판을 0점으로 했어요', 'info');
    }
    async function settle() {
        const ok = await ctx.confirm({ title: '엑셀판으로 옮길까요?', body: '이 판의 점수를 엑셀판 기여도에 더하고 판을 비웁니다.\n마이너스도 그대로 옮겨져요. (점수판 되돌리기로 취소할 수 있어요)', ok: '기여도로 옮기기', cancel: '아직', danger: false });
        if (!ok) return;
        const res = await ctx.run('dice.settle', {});
        if (!res.ok) return;
        const m = (res.moved || []).map(x => `${x.name} ${signed(x.points)}`).join(' · ');
        ctx.toast(m ? `🎯 기여도로 옮겼어요 — ${m}` : '🎯 옮길 점수가 없었어요', m ? 'ok' : 'info', 6000);
        const sk = (res.skipped || []).map(x => `${x.name} ${signed(x.points)}`).join(' · ');
        if (sk) ctx.toast(`엑셀판에서 이름을 못 찾아 못 옮긴 사람: ${sk} — 점수는 주사위 판에 남겨 뒀어요`, 'err', 9000);
    }
    async function setup() {
        const c = Number(cols.value), r = Number(rows.value), d = Number(dice.value);
        const rp = rprice.value.trim() === '' ? undefined : toInt(rprice.value);
        const lc = lap.value.trim() === '' ? undefined : toInt(lap.value);
        if (rp === null || lc === null) { ctx.toast('한 판 값 · 한 바퀴 기여도는 숫자로 적어 주세요', 'err'); return; }
        if ((g.pieces || []).some(p => p.pos || p.laps)) {
            const ok = await ctx.confirm({ title: '판을 다시 깔까요?', body: '말이 전부 출발로 돌아가요. 같은 번호 칸 내용 · 전용 판 점수는 남아요.', ok: '다시 깔기', cancel: '그대로 두기' });
            if (!ok) return;
        }
        if (!(await okToTake(ctx, 'dicegame', '주사위판'))) return;
        const data = { cols: c, rows: r, dice: d };
        if (rp !== undefined) data.roll_price = rp;
        if (lc !== undefined) data.lap_contrib = lc;
        const res = await ctx.run('dice.setup', data);
        if (res.ok) ctx.toast(`🎲 테두리 ${res.tiles}칸 판을 깔았어요 — 방송에 떴어요`, 'ok');
    }
    async function preset(name, tilesOnly) {
        const what = name === 'basic22' ? '22칸 기본판' : '22칸 손그림판';
        if (tilesOnly) {
            const ok = await ctx.confirm({ title: '칸 내용만 다시 깔까요?', body: '판 크기 · 말 위치 · 점수는 그대로 두고 칸 내용만 손그림판으로 바꿉니다.\n황금열쇠 덱도 손그림판 10장으로 바뀌어요.', ok: '칸만 다시 깔기', cancel: '그대로 두기' });
            if (!ok) return;
        } else {
            if ((g.tiles || []).length) {
                const ok = await ctx.confirm({ title: `${what}을 깔까요?`, body: '8×5 테두리 22칸으로 새로 깔고 말은 전부 출발로 갑니다.' + (name === 'draw22' ? '\n황금열쇠 덱도 손그림판 10장으로 바뀌어요.' : ''), ok: '깔기', cancel: '그대로 두기' });
                if (!ok) return;
            }
            if (!(await okToTake(ctx, 'dicegame', '주사위판'))) return;
        }
        const res = await ctx.run('dice.preset', tilesOnly ? { name, tiles_only: true } : { name });
        if (!res.ok) return;
        ctx.toast(`🎲 ${what}${tilesOnly ? ' 칸' : ''}을 깔았어요 (${res.tiles}칸${res.keys ? ' · 열쇠 ' + res.keys + '장' : ''})`, 'ok');
        if ((res.missing || []).length) ctx.toast(`시그니처를 못 찾아 빈칸으로 둔 칸: ${res.missing.join(', ')} — 칸 편집에서 골라 주세요`, 'err', 9000);
    }
    async function saveKeys() {
        const keys = keysTa.value.split('\n').map(x => x.trim()).filter(Boolean);
        const res = await ctx.run('dice.keys', { keys });
        if (res.ok) { keysTa.dataset.sv = ''; ctx.toast(`🔑 황금열쇠 ${res.count}장 저장`, 'ok'); ctx.rerender(); }
    }
    async function move() {
        const pos = toInt(posIn.value);
        if (pos === null) { ctx.toast('칸 번호를 숫자로 적어 주세요', 'err'); return; }
        const data = { pos };
        if (pick && (g.pieces || []).some(p => p.name === pick)) data.piece = pick;
        const res = await ctx.run('dice.move', data);
        if (!res.ok) return;
        let m = `[${res.piece || '?'}] 말을 ${pos}번 칸으로 옮겼어요`;
        if (res.choose) m += ' · 🎯 원하는 곳으로';
        if (res.scored) m += ` · ${res.scored.name} ${signed(res.scored.points)}`;
        if (res.key) m += ` · 🔑 ${res.key}${res.key_effect ? ' → ' + res.key_effect : ''}`;
        ctx.toast(m, 'ok');
        addLog(m);
        posIn.value = '';
    }
    async function resetPieces() {
        const ok = await ctx.confirm({ title: '말을 전부 출발로?', body: '말을 출발 칸으로 되돌리고 방송 화면에서 내립니다.\n칸 구성 · 황금열쇠 덱 · 전용 판 점수는 그대로 남아요.', ok: '출발로', cancel: '그대로 두기' });
        if (!ok) return;
        const res = await ctx.run('dice.reset', {});
        if (res.ok) ctx.toast('🎲 말을 출발로 되돌렸어요', 'info');
    }

    /* ── 그리기 ── */
    function paintPlayers() {
        const ps = g.pieces || [];
        if (pick && !ps.some(p => p.name === pick)) pick = '';
        const nx = (ps[Number(g.turn) || 0] || {}).name || '';
        const pts = {};
        (g.board || []).forEach(r => { pts[r.name] = Number(r.pts) || 0; });
        if (!ps.length) { players.replaceChildren(h('span', { class: 'gm-info' }, '점수판에 선수가 있으면 여기에 말이 나와요 (판을 깔면 생겨요)')); }
        else players.replaceChildren(...ps.map(p => {
            const on = p.name === pick, next = !pick && p.name === nx;
            const pp = pts[p.name] || 0;
            return h('button', { type: 'button', class: 'gm-pl' + (on ? ' on' : '') + (next ? ' next' : ''), 'aria-pressed': String(on),
                onclick: () => { pick = pick === p.name ? '' : p.name; paintPlayers(); paintRoll(); } },
                h('b', null, p.shield ? '🛡️ ' : '', p.choose ? '🎯 ' : '', p.name),
                h('span', null, `${p.pos}번 칸 · ${signed(pp)}점${p.laps ? ' · ' + p.laps + '바퀴' : ''}`));
        }));
        const holders = ps.filter(p => p.shield);
        shields.hidden = !holders.length;
        shields.replaceChildren(h('span', { class: 'gm-lbl' }, '🛡️ 쉴드권'), ...holders.map(p => h('span', { class: 'gm-chip on' }, p.name,
            h('button', { type: 'button', class: 'btn sm', onclick: () => useShield(p.name) }, '사용함'))));
    }
    function paintRoll() {
        const n = who();
        rollT.setName((n ? n + ' ' : '') + '굴리기');
        const stage = (slices.show || {}).stage;
        const noTiles = !(g.tiles || []).length;
        const ok = !noTiles && stage === 'dicegame';
        const why = noTiles ? '판을 깔면 굴릴 수 있어요' : stage ? `지금 무대에 ${STAGE_LABEL[stage] || stage} 판이 있어요 — 주사위판을 먼저 띄우세요` : '주사위판을 방송에 띄우면 굴릴 수 있어요';
        rollT.disabled = !ok;
        rollT.title = ok ? '' : why;
        eyes.querySelectorAll('.gm-eye').forEach(b => { b.disabled = !ok; b.title = ok ? '' : why; });
        eyes.classList.toggle('off', !ok);
        rollT.classList.toggle('wait', rxBusy());
        const a = g.action || {};
        big.firstChild.textContent = a.type === 'ROLL' ? (a.dice || []).join('+') : '–';
        let st;
        if (noTiles) st = '판이 없어요 — 아래 «판 만들기» 에서 깔아 주세요';
        else if (!ok) st = why;
        else st = `판 ${g.tiles.length}칸 · 주사위 ${g.dice || 1}개 · 한 판 ${won(g.roll_price || 0)} · 한 바퀴 기여도 ${num(g.lap_contrib || 0)} · 열쇠 ${g.keys_count || 0}장`;
        if (a.type === 'ROLL') st += ` · 마지막: ${a.piece} ${(a.dice || []).join('+')} → ${a.to}번`;
        if (status.textContent !== st) status.textContent = st;
    }
    function paintBoard() {
        const rws = (g.board || []).slice().sort((a, b) => (b.pts || 0) - (a.pts || 0) || String(a.name).localeCompare(String(b.name)));
        if (!rws.length) { board.replaceChildren(h('p', { class: 'empty' }, '선수가 있으면 여기에 나와요')); return; }
        board.replaceChildren(...rws.map((r, i) => {
            const p = Number(r.pts) || 0;
            return h('div', { class: 'gm-brow' },
                h('span', { class: 'gm-rank' }, String(i + 1)),
                h('span', { class: 'gm-bn' }, r.name),
                h('b', { class: 'gm-bp' + (p > 0 ? ' up' : p < 0 ? ' down' : '') }, num(p)),
                h('span', { class: 'gm-bb' },
                    h('button', { type: 'button', class: 'btn sm', 'aria-label': `${r.name} 5점 빼기`, onclick: () => boardAdd(r.name, -5) }, '−5'),
                    h('button', { type: 'button', class: 'btn sm', 'aria-label': `${r.name} 5점 더하기`, onclick: () => boardAdd(r.name, 5) }, '+5')));
        }));
    }

    /* 칸 편집 — 줄마다 그 칸이 바뀌었을 때만 다시 그린다(고르는 중인 줄은 건드리지 않는다) */
    const tileRows = new Map();
    function contentCell(t, i, row) {
        const type = t.type || 'blank';
        const save = () => saveTile(i, row);
        if (type === 'sig') {
            const sigs = sigsNow() || [];
            const cur = t.sig && t.sig.id != null ? String(t.sig.id) : '';
            const s = h('select', { class: 'gm-sel grow', 'data-k': 'sig', 'aria-label': `${i}번 칸 시그니처` },
                h('option', { value: '' }, sigs.length ? '(시그니처 고르기)' : '시그니처 목록을 불러오는 중…'),
                sigs.map(x => h('option', { value: String(x.id), selected: String(x.id) === cur }, `${x.title || '#' + x.id} · ${won(x.amount)}`)));
            if (cur && !sigs.some(x => String(x.id) === cur)) s.append(h('option', { value: cur, selected: true }, (t.sig.title || '#' + cur) + ' (지금 칸)'));
            s.addEventListener('change', save);
            return [s];
        }
        const out = [];
        if (type !== 'score') {
            const lb = h('input', { type: 'text', class: 'gm-in grow', 'data-k': 'label', maxlength: 60, autocomplete: 'off',
                placeholder: type === 'mission' ? '미션 내용' : '표시할 글(비워도 됨)', 'aria-label': `${i}번 칸 글` });
            lb.value = t.label || '';
            lb.addEventListener('change', save);
            onEnter(lb, () => lb.blur());
            out.push(lb);
        }
        if (UNIT[type]) {
            const pt = numInput({ class: 'gm-in num w64', 'data-k': 'points', 'aria-label': `${i}번 칸 숫자` });
            pt.value = String(t.points || 0);
            pt.addEventListener('change', save);
            onEnter(pt, () => pt.blur());
            out.push(pt, h('span', { class: 'gm-info' }, UNIT[type]));
        }
        return out;
    }
    async function saveTile(i, row) {
        const type = row.type.value;
        const body = { id: i, type };
        const lb = row.cell.querySelector('[data-k=label]');
        if (lb) body.label = lb.value;
        const pt = row.cell.querySelector('[data-k=points]');
        if (pt) {
            const v = toInt(pt.value);
            if (v === null) { ctx.toast('숫자로 적어 주세요', 'err'); return; }
            body.points = v;
        }
        const sg = row.cell.querySelector('[data-k=sig]');
        if (sg) {
            if (!sg.value) return;               // 아직 안 골랐다 — 고르면 저장된다
            body.sig_id = Number(sg.value);
        }
        if (type === 'score' && !lb) body.label = (body.points > 0 ? '+' : '') + body.points + '점';
        const res = await ctx.run('dice.tile', body);
        if (res.ok) ctx.toast(`${i}번 칸 저장`, 'ok');
        row.sig = '';
        ctx.rerender();
    }
    function paintTiles() {
        const tiles = g.tiles || [];
        if (!tiles.length) { tileBox.replaceChildren(h('p', { class: 'empty' }, '아직 판이 없어요 — 위 «판 만들기» 에서 깔아 주세요')); tileRows.clear(); return; }
        if (tileBox.querySelector('.empty')) tileBox.replaceChildren();
        const sigN = (sigsNow() || []).length;
        for (const [i, r] of tileRows) if (i >= tiles.length) { r.el.remove(); tileRows.delete(i); }
        tiles.forEach((t, i) => {
            let r = tileRows.get(i);
            if (!r) {
                if (i === 0) {
                    r = { el: h('div', { class: 'gm-trow start' }, h('b', { class: 'gm-tno' }, '0'), h('span', null, '🏁 출발 (고정)')), sig: 'start' };
                } else {
                    const type = h('select', { class: 'gm-sel w150', 'aria-label': `${i}번 칸 종류` }, TYPES.map(([v, l]) => h('option', { value: v }, l)));
                    const cell = h('span', { class: 'gm-tcell' });
                    r = { el: h('div', { class: 'gm-trow' }, h('b', { class: 'gm-tno' }, String(i)), type, cell), type, cell, sig: '' };
                    type.addEventListener('change', () => {
                        // ⚠️ 고른 종류는 저장될 때까지 '초안' 으로 붙잡는다 — 안 그러면 다른 쪽지(시그 목록 도착 등)에
                        //    다시 그리면서 서버의 옛 종류로 돌아가, 시그니처를 고르기도 전에 칸이 되돌아간다
                        const cur = (g.tiles || [])[i] || {};
                        r.draft = type.value === (cur.type || 'blank') ? null : type.value;
                        r.cell.replaceChildren(...contentCell({ type: type.value, label: cur.label, points: cur.points, sig: cur.sig }, i, r));
                        if (type.value === 'blank' || type.value === 'key') saveTile(i, r);
                        else if (type.value === 'sig') loadSigs().then(() => { r.sig = ''; ctx.rerender(); });
                    });
                }
                tileRows.set(i, r);
            }
            if (i > 0) {
                if (r.draft && (t.type || 'blank') === r.draft) r.draft = null;      // 저장됐다
                const view = r.draft ? { type: r.draft, label: t.label, points: t.points, sig: t.sig } : t;
                const sig = JSON.stringify([view, sigN]);
                if (sig !== r.sig && !r.el.contains(document.activeElement)) {
                    r.type.value = view.type || 'blank';
                    r.cell.replaceChildren(...contentCell(view, i, r));
                    r.sig = sig;
                }
            }
            if (tileBox.children[i] !== r.el) tileBox.insertBefore(r.el, tileBox.children[i] || null);
        });
    }

    return {
        render(s) {
            slices = s;
            g = s.dicegame || {};
            pv = s.dicegame_private || {};
            const stage = (s.show || {}).stage;
            hd.setAir(stage === 'dicegame');
            hd.setPill((g.tiles || []).length ? `${g.tiles.length}칸` : '판 없음', (g.tiles || []).length ? '' : 'warn');
            rxWarn.hidden = !rxBusy();
            paint('players', [g.pieces, g.board, g.turn, pick], paintPlayers);
            paintRoll();
            paint('board', g.board || [], paintBoard);
            // 판 만들기 칸은 서버가 쓰는 실제 값으로(손이 올라가 있으면 그대로) — 화면이 거짓말을 하면 주사위가 조용히 두 개가 된다
            syncVal(cols, g.cols || 7);
            syncVal(rows, g.rows || 5);
            syncVal(dice, g.dice || 1);
            syncVal(rprice, g.roll_price == null ? 20000 : g.roll_price);
            syncVal(lap, g.lap_contrib == null ? 10 : g.lap_contrib);
            setupSum.textContent = (g.tiles || []).length ? `${g.cols}×${g.rows} · 테두리 ${g.tiles.length}칸 · 주사위 ${g.dice || 1}개` : '아직 판이 없어요';
            tilesSum.textContent = (g.tiles || []).length ? `${g.tiles.length}칸` : '';
            keysSum.textContent = `${g.keys_count || 0}장`;
            if (foldTiles.open) paintTiles();
            if (document.activeElement !== keysTa) {
                const want = (pv.keys || []).join('\n');
                if (keysTa.dataset.sv !== want) { keysTa.value = want; keysTa.dataset.sv = want; }
            }
        },
    };
}
