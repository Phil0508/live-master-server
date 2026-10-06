/* 💬 AI 에게 물어보기 — POST /api/ai/chat (화면 약속 3). 언제나 200 으로 답이 온다.
     {intent}   빠른 질문 단추 · 상황판 칸 → 서버가 사실표로 바로 센 답(⚡ 서버 계산 — 0초 · 늘 맞다 · AI 가 붐벼도 된다)
     {question, messages}  글로 물은 것 → AI(🤖 AI). AI 가 꺼졌거나 붐비면 서버 계산으로 대신(⚡, 끝에 '(… — 서버 계산으로 답했어요)')
   답 밑에 늘 꼬리표 — '⚡ 서버 계산' · '🤖 AI' · 'ℹ️ 안내'(답 대신 까닭). '모름' 도 그대로 보여 준다(숨기지 않는다).
   🗣️ 명령 꼴('하율 3점' · '슬롯 돌려' · '룰렛 돌려' · '대결 시작' · '건너뛰어' · '올클리어')은 AI 에게 안 보내고 바로 명령으로(옛 aiTryCommand).
     → AI 호출도, 분당 한도도 안 쓴다. 명령이 아니면 AI 에게 넘어간다 — 물어보는 건 여전히 AI 몫.
   한 번에 하나만 묻는다(답을 기다리는 동안 다른 단추 · 보내기는 잠깐 쉰다). */
import { h, call, replyNodes, SRC, currentNames } from './common.js';
import * as chat from './chatlog.js';
import * as ap from './autopilot.js';
import { okToTake, useLm } from '../games/common.js';

const HISTORY = 6;          // 서버는 마지막 6개만 쓴다

export function mountChat(ctx, board) {
    useLm(ctx.lm);                    // 무대 뺏기 확인(okToTake)이 서버 시계를 쓴다
    const log = h('div', { class: 'ai-log', role: 'log', 'aria-live': 'polite', 'aria-label': 'AI 와 나눈 대화' });
    const quick = h('div', { class: 'ai-quick', role: 'group', 'aria-label': '빠른 질문 (⚡ 서버 계산)' });
    const QUICK = ['rank', 'today', 'sig', 'flow'];
    const qBtns = {};
    QUICK.forEach(k => {
        qBtns[k] = h('button', { type: 'button', class: 'ai-q', onclick: () => ask(k) }, '');
        quick.append(qBtns[k]);
    });
    board.onIntents(names => QUICK.forEach(k => { qBtns[k].textContent = names[k] || k; }));

    const input = h('textarea', { class: 'ai-input', rows: '1', placeholder: '그 밖의 것은 글로 물어보세요', 'aria-label': 'AI 에게 물어볼 말', enterkeyhint: 'send' });
    const send = h('button', { type: 'button', class: 'btn pri ai-send', onclick: () => sendText() }, '보내기');
    input.addEventListener('keydown', e => {
        if (e.key !== 'Enter' || e.shiftKey || e.isComposing || e.keyCode === 229) return;    // 한글 조합 중 Enter 는 무시
        e.preventDefault();
        sendText();
    });
    input.addEventListener('input', grow);
    function grow() {
        input.style.height = 'auto';
        input.style.height = Math.min(120, input.scrollHeight + 2) + 'px';
    }
    const row = h('div', { class: 'ai-input-row' }, input, send);
    const hint = h('p', { class: 'ai-cmd-hint' }, '바로 하는 말: ', h('b', null, '하율 3점'), ' · ', h('b', null, '슬롯 돌려'), ' · ', h('b', null, '룰렛 돌려'),
        ' · ', h('b', null, '대결 시작'), ' · ', h('b', null, '건너뛰어'), ' · ', h('b', null, '올클리어'), ' — AI 를 안 거치고 바로 해요');

    let busy = false;
    const nodes = new Map();          // 대화 줄 id → 요소

    /* ── 그리기 ── */
    function bubble(r) {
        const el = h('div', { class: 'ai-msg ai-msg-' + r.role + (r.temp ? ' ai-thinking' : ''), 'data-id': r.id });
        fillBubble(el, r);
        return el;
    }
    function fillBubble(el, r) {
        el.className = 'ai-msg ai-msg-' + r.role + (r.temp ? ' ai-thinking' : '');
        if (r.role === 'ai') {
            const tag = !r.temp && SRC[r.source] ? h('span', { class: 'ai-src ai-src-' + r.source, title: SRC[r.source][1] }, SRC[r.source][0]) : null;
            el.replaceChildren(...replyNodes(r.text), ...(tag ? [tag] : []));
        } else {
            const kids = [];
            String(r.text).split('\n').forEach((ln, i) => { if (i) kids.push(h('br')); kids.push(ln); });
            el.replaceChildren(...kids);
        }
        // 🚗 끌 때 보고 — 잘못 간 것을 그 자리에서 되돌린다(이 화면을 연 동안만 단추가 있다)
        if (r.apReport && r.apReport.length) el.append(apButtons(r.apReport));
    }
    function apButtons(ids) {
        const wrap = h('div', { class: 'ai-ap-undo' });
        ids.forEach(id => {
            const e = ap.entry(id);
            if (!e) return;
            const b = h('button', { type: 'button', class: 'btn sm', disabled: e.undone || null }, e.undone ? '↩ 되돌림 — 대기함에서 다시 주세요' : `↩ ${e.donor} → ${e.target} (+${e.pts}) 되돌리기`);
            b.addEventListener('click', async () => {
                b.disabled = true;
                const ok = await ap.undo(id);
                if (ok) b.textContent = '↩ 되돌림 — 대기함에서 다시 주세요';
                else b.disabled = false;
            });
            wrap.append(b);
        });
        return wrap;
    }
    const EMPTY = () => h('div', { class: 'ai-msg ai-msg-sys ai-empty' }, '위 칸이나 아래 단추를 누르면 바로 알려줘요 · 그 밖의 것은 글로 물어보세요');

    function paintAll() {
        nodes.clear();
        const rows = chat.all();
        log.replaceChildren(...(rows.length ? rows.map(r => { const el = bubble(r); nodes.set(r.id, el); return el; }) : [EMPTY()]));
        toBottom();
    }
    function toBottom() { log.scrollTop = log.scrollHeight; }
    chat.subscribe((kind, r) => {
        if (kind === 'clear') { paintAll(); return; }
        if (kind === 'add') {
            const empty = log.querySelector('.ai-empty');
            if (empty) empty.remove();
            const el = bubble(r);
            nodes.set(r.id, el);
            log.append(el);
            while (log.children.length > 80) { const f = log.firstElementChild; nodes.delete(f.dataset.id); f.remove(); }
        } else if (kind === 'update' && nodes.has(r.id)) fillBubble(nodes.get(r.id), r);
        toBottom();
    });
    paintAll();

    function setBusy(on) {
        busy = on;
        send.disabled = on;
        Object.values(qBtns).forEach(b => { b.disabled = on; });
        board.els.grid.classList.toggle('busy', on);
    }

    /* ── 빠른 질문(상황판 칸 · 단추) ── 서버가 센 답 — AI 를 안 부른다 */
    async function ask(intent) {
        if (busy) return;
        const label = board.intents[intent] || intent;
        setBusy(true);
        chat.add('user', label);
        const box = chat.add('ai', '계산 중…', { temp: true });
        const r = await call('/api/ai/chat', { intent });
        finish(box, r);
        setBusy(false);
    }

    /* ── 글로 묻기 ── 명령 꼴이면 바로 명령, 아니면 AI */
    async function sendText() {
        if (busy) return;
        const q = input.value.trim();
        if (!q) return;
        input.value = '';
        grow();
        if (await tryCommand(q)) { input.focus(); return; }
        setBusy(true);
        const hist = chat.history(HISTORY);           // 이번 질문을 더하기 전의 직전 대화
        chat.add('user', q);
        const box = chat.add('ai', '생각 중… (AI 가 붐비면 20초쯤 걸릴 수 있어요)', { temp: true });
        const r = await call('/api/ai/chat', { question: q, messages: hist });
        finish(box, r);
        setBusy(false);
        board.refresh();                              // AI 를 불렀으니 머리의 상태 점을 바로 새로
        input.focus();
    }

    function finish(box, r) {
        if (r.ok && r.data && typeof r.data.reply === 'string') {
            chat.update(box, { text: r.data.reply || '(빈 답)', source: r.data.source || 'none', temp: false });
        } else {
            const why = r.status === 401 ? '로그인이 풀렸어요 — 새로 고쳐 다시 들어가 주세요'
                : r.status === 0 ? '서버에 닿지 않아요 — 잠시 뒤 다시 눌러 주세요'
                : `서버가 ${r.status} 로 답했어요 — 잠시 뒤 다시 눌러 주세요`;
            chat.update(box, { text: '(연결 실패) ' + why, source: 'none', temp: false });
        }
    }

    /* ── 🗣️ 명령 꼴 — 옛 aiTryCommand ── 맞으면 true(AI 를 안 부른다) */
    async function tryCommand(q) {
        const slices = ctx.slices || {};
        const said = msg => { chat.add('user', q); return chat.add('sys', msg); };
        const done = (row, msg) => chat.update(row, { text: msg });

        // '하율 3점' · '하율한테 3점 줘' · '하율 +3'
        const m = q.match(/^([가-힣A-Za-z0-9]+?)\s*(?:한테|에게)?\s*\+?(\d+)\s*점?\s*(?:줘|주기|추가)?$/);
        if (m) {
            const P = slices.players || {};
            const key = P.extra_active ? 'extra' : 'list';
            const names = currentNames(slices);
            const hit = names.filter(n => n.indexOf(m[1]) !== -1);
            if (hit.length === 1) {
                const nm = hit[0], pts = parseInt(m[2], 10);
                const row = said(`⏳ ${nm} +${pts}점…`);
                const res = await ctx.run('score.add', { name: nm, delta: pts, list: key }, { quiet: true });
                done(row, res.ok ? `✔ ${key === 'extra' ? '[번외] ' : ''}${nm} +${pts}점 — 틀렸으면 맨 위 [되돌리기]` : `⚠️ 못 줬어요 — ${res.error || '서버 전송 오류'}`);
                if (res.ok) ctx.toast(`${key === 'extra' ? '[번외] ' : ''}${nm} +${pts}점`, 'ok');
                return true;
            }
            if (hit.length > 1) { said(`⚠️ '${m[1]}' 이(가) 여럿이에요: ${hit.join(', ')} — 이름을 정확히 적어 주세요`); return true; }
            // 선수 이름이 아니면 질문으로 본다(예: '1등 3' 같은 말) — AI 에게 넘긴다
        }
        if (/^슬롯\s*(돌려|시작|고)?!?$/.test(q)) {
            if (!(await okToTake(ctx, 'slot', '슬롯머신'))) { said('🎰 슬롯은 그대로 뒀어요'); return true; }
            const row = said('🎰 슬롯을 돌려요…');
            const r = await call('/api/slot/spin', {});
            const w = r.data && r.data.winner;
            done(row, r.ok ? `🎰 돌려요${w ? ` — 당첨 ${w.title || ''}` : ''}` : `⚠️ 못 돌렸어요 — ${(r.data && (r.data.message || r.data.error)) || '실패 (' + r.status + ')'}`);
            return true;
        }
        if (/^룰렛\s*(돌려|시작|고)?!?$/.test(q)) {
            if (!(await okToTake(ctx, 'roulette', '룰렛'))) { said('🎡 룰렛은 그대로 뒀어요'); return true; }
            const row = said('🎡 룰렛을 돌려요…');
            const res = await ctx.run('roulette.spin', {}, { quiet: true });
            done(row, res.ok ? (res.already ? '🎡 이미 돌고 있어요' : '🎡 돌려요 — 룰렛 탭의 [정지!!] 로 세워요') : `⚠️ 못 돌렸어요 — ${res.error || '실패'}`);
            return true;
        }
        const mt = q.match(/^(대결|타이머)\s*(시작|정지|스톱|멈춰)?$/);
        if (mt) {
            const tm = ((slices.match || {}).timer) || {};
            const want = mt[2] ? (mt[2] === '시작' ? 'start' : 'pause') : (tm.running ? 'pause' : 'start');
            if (want === 'start' && tm.running) { said('⚔️ 대결 타이머는 이미 돌고 있어요'); return true; }
            if (want === 'pause' && !tm.running) { said('⚔️ 대결 타이머는 이미 멈춰 있어요'); return true; }
            const row = said(want === 'start' ? '⚔️ 대결 타이머를 켜요…' : '⚔️ 대결 타이머를 멈춰요…');
            const res = await ctx.run(want === 'start' ? 'match.start' : 'match.pause', {}, { quiet: true });
            done(row, res.ok ? (want === 'start' ? '⚔️ 대결 타이머 시작!' : '⚔️ 대결 타이머를 멈췄어요') : `⚠️ 못 했어요 — ${res.error || '실패'}`);
            return true;
        }
        if (/^(건너뛰|스킵|넘겨)/.test(q)) {
            const row = said('⏭ 재생 중인 시그니처를 넘겨요…');
            const res = await ctx.run('reaction.skip', {}, { quiet: true });
            done(row, res.ok ? '⏭ 넘겼어요' : `⚠️ 못 넘겼어요 — ${res.error || '실패'}`);
            return true;
        }
        if (/^올\s*클리어|^올클/.test(q)) {
            const g = slices.siggame || {};
            const left = (g.cards || []).filter(c => c && c.flippedAt && !c.doneAt).length;
            if (left > 0) {
                const ok = await ctx.confirm({ title: '올클리어 할까요?', body: `아직 ${left}장이 남아 있어요.\n남은 목표를 전부 달성 처리하고 올클리어를 터뜨립니다.`, ok: '올클리어', cancel: '아직', danger: false });
                if (!ok) { said('🃏 올클리어는 안 했어요'); return true; }
            }
            const row = said('🎉 올클리어!…');
            const res = await ctx.run('sig.allclear', {}, { quiet: true });
            done(row, res.ok ? `🎉 ALL CLEAR!${res.count ? ` (${res.count}장)` : ''}` : `⚠️ 못 했어요 — ${res.error || '실패'}`);
            return true;
        }
        return false;
    }

    return {
        els: { log, quick, row, hint },
        ask,
        scrollEnd: toBottom,
    };
}

