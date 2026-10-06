/* 🧩 퀴즈판 — 초성 · 사자성어. 방송판에는 네모칸만, 정답 · 분류는 조종실에만(quiz_ops 는 비공개 조각).

   [다음 문제] quiz.next{kind}(순서 맨 위 · 방송에 바로 뜬다) · [힌트 한 글자] quiz.hint · [정답 공개] quiz.reveal ·
   [퀴즈판 내리기] quiz.show{on:false} · 지금 바로 띄우기 quiz.now{kind, text}(정답 → 초성 · 초성만 → 그대로)
   다음 순서: ▲ ▼ ⤒(맨 위로) ▶(지금 띄우기) ✕(오늘은 빼기) · 섞기 = quiz.order{kind, action, answer}
   내 문제 더하기 quiz.custom{kind, text} · 비우기 quiz.custom{kind, mode:'clear'}
   ⚠️ 한글 입력 중 Enter(조합 끝내기)로 보내지 않는다 — isComposing · keyCode 229 를 거른다(반쯤 쓴 글자가 나간다).
   ⚠️ 무대를 차지하는 단추(다음 · 바로 띄우기 · ▶ · 띄우기)는 슬롯 · 룰렛 · 핀볼이 한창이면 한 번 묻는다(옛 qzCall). */
import { h } from '../../util.js';
import { head, seg, memo, okToTake, tile, onEnter } from './common.js';

const INI = 'ㄱㄲㄴㄷㄸㄹㅁㅂㅃㅅㅆㅇㅈㅉㅊㅋㅌㅍㅎ';
function initials(w) {
    return [...String(w || '')].map(c => { const k = c.charCodeAt(0) - 0xAC00; return k >= 0 && k < 11172 ? INI[Math.floor(k / 588)] : c; }).join('');
}
const KIND_LABEL = { chosung: '초성', idiom: '사자성어' };

export function mountQuiz(el, ctx) {
    const paint = memo();
    let q = {}, ops = {}, kindSel = '', prepared = false;
    let bank = null;           // 기본 문제 [정답, 분류 · 뜻] — 한 번만 받는다(바뀌지 않는다)
    fetch('/api/quiz/bank', { cache: 'no-store' }).then(r => r.json()).then(j => {
        if (j && j.bank) { bank = j.bank; try { paintOrder(); } catch (e) { /* 아직 그릴 자리가 없으면 다음 render 때 */ } }
    }).catch(() => { /* 뜻이 없어도 순서는 보인다 */ });
    const kindNow = () => kindSel || ops.kind || 'chosung';

    const hd = head('🧩 퀴즈', async on => {
        if (on) {
            if (!(await okToTake(ctx, 'quiz', '퀴즈판'))) return;
            const res = await ctx.run('quiz.show', { on: true });
            if (res.ok) ctx.toast('퀴즈판을 방송에 띄웠어요', 'ok');
        } else {
            const res = await ctx.run('quiz.show', { on: false });
            if (res.ok) ctx.toast('퀴즈판을 내렸어요', 'info');
        }
    });
    const kindSeg = seg([['chosung', '초성'], ['idiom', '사자성어']], v => { kindSel = v; ctx.rerender(); }, '퀴즈 종류');
    const kindN = h('span', { class: 'gm-info' });

    const nowIn = h('input', { type: 'text', class: 'gm-in grow', maxlength: 24, autocomplete: 'off', enterkeyhint: 'send',
        placeholder: '지금 바로 띄울 정답 — 예: 떡볶이 → 방송엔 ㄸㅂㅇ (초성만 적어도 돼요)', 'aria-label': '지금 바로 띄울 정답' });
    onEnter(nowIn, sendNow);
    const nowBtn = h('button', { type: 'button', class: 'btn pri', onclick: sendNow }, '바로 띄우기');

    const cur = h('div', { class: 'gm-quiz-now' });
    const nextT = tile('다음 문제', '방송에 바로 떠요', next, 'go');
    const hintT = tile('힌트 한 글자', '앞에서부터 한 칸', async () => { const r = await ctx.run('quiz.hint', {}); if (r.ok) ctx.toast('💡 한 글자 열었어요', 'info'); });
    const revealT = tile('정답 공개', '칸이 금색으로', async () => { const r = await ctx.run('quiz.reveal', {}); if (r.ok) ctx.toast('정답을 공개했어요', 'info'); });
    const downT = tile('퀴즈판 내리기', '방송 화면에서', async () => { const r = await ctx.run('quiz.show', { on: false }); if (r.ok) ctx.toast('퀴즈판을 내렸어요', 'info'); });

    const orderN = h('b');
    const order = h('ol', { class: 'gm-qorder' });
    order.addEventListener('click', async e => {
        const b = e.target.closest('button[data-act]');
        const li = b && b.closest('li[data-a]');
        if (!li) return;
        const act = b.dataset.act, answer = li.dataset.a;
        if (act === 'play' && !(await okToTake(ctx, 'quiz', '퀴즈판'))) return;
        const res = await ctx.run('quiz.order', { kind: kindNow(), action: act, answer });
        if (!res.ok) return;
        if (act === 'play') ctx.toast(`지금 띄웠어요 — ${answer}`, 'ok');
        else if (act === 'remove') ctx.toast(`오늘은 뺐어요 — ${answer}`, 'info');
        else if (act === 'top') ctx.toast(`다음에 나가요 — ${answer}`, 'info');
    });

    const addTa = h('textarea', { class: 'gm-ta', rows: 5, placeholder: '떡볶이 | 음식\n일석이조 | 한 가지 일로 두 가지 이득', 'aria-label': '내 문제' });
    const addMsg = h('span', { class: 'gm-info' });
    const mineN = h('small');

    el.append(h('div', { class: 'gm' },
        hd.el,
        h('div', { class: 'gm-row' }, kindSeg.el, kindN),
        h('div', { class: 'gm-row' }, nowIn, nowBtn),
        cur,
        h('div', { class: 'gm-tiles' }, nextT, hintT, revealT, downT),
        h('section', { class: 'gm-box' },
            h('div', { class: 'gm-sub' }, h('span', { class: 'gm-lbl' }, '다음 순서 ', orderN, ' — [다음 문제] 는 맨 위부터 나가요'), h('span', { class: 'gm-sp' }),
                h('button', { type: 'button', class: 'btn sm', onclick: async () => {
                    const res = await ctx.run('quiz.order', { kind: kindNow(), action: 'shuffle' });
                    if (res.ok) ctx.toast('남은 순서를 다시 섞었어요', 'info');
                } }, '🔀 섞기')),
            order),
        h('details', { class: 'gm-fold' }, h('summary', null, '내 문제 더하기 ', mineN),
            h('div', { class: 'gm-fold-body' },
                h('p', { class: 'gm-info' }, '한 줄에 하나 — 초성: 정답 | 분류 · 사자성어: 정답 | 뜻 (위에서 고른 종류에 들어가요 · 순서 맨 끝에 붙어요)'),
                addTa,
                h('div', { class: 'gm-row' },
                    h('button', { type: 'button', class: 'btn sm pri', onclick: add }, '더하기'),
                    h('button', { type: 'button', class: 'btn sm ghost-danger', onclick: clearMine }, '내 문제 비우기'),
                    addMsg)))));

    async function next() {
        if (!(await okToTake(ctx, 'quiz', '퀴즈판'))) return;
        const res = await ctx.run('quiz.next', { kind: kindNow() });
        if (!res.ok) return;
        if (res.wrapped) ctx.toast(`${KIND_LABEL[kindNow()]} 문제를 한 바퀴 다 냈어요 — 처음부터 다시 나와요`, 'info', 5000);
    }
    async function sendNow() {
        const t = nowIn.value.trim();
        if (!t) { ctx.toast('띄울 정답(또는 초성)을 적어 주세요', 'err'); nowIn.focus(); return; }
        if (!(await okToTake(ctx, 'quiz', '퀴즈판'))) return;
        nowBtn.disabled = true;
        const res = await ctx.run('quiz.now', { kind: kindNow(), text: t });
        nowBtn.disabled = false;
        if (!res.ok) return;
        nowIn.value = '';
        nowIn.blur();
        ctx.toast(res.jamo_only ? '초성만 띄웠어요 — 정답을 몰라 힌트 · 정답 공개는 안 돼요' : `바로 띄웠어요 — ${t}`, res.jamo_only ? 'info' : 'ok');
    }
    async function add() {
        const text = addTa.value.trim();
        if (!text) { ctx.toast('더할 문제를 한 줄에 하나씩 적어 주세요', 'err'); return; }
        const res = await ctx.run('quiz.custom', { kind: kindNow(), text });
        if (!res.ok) return;
        const bad = res.bad || [];
        addMsg.textContent = `${res.added}개 더함` + (bad.length ? ` · 못 넣은 줄 ${bad.length}개(형식 확인): ${bad.join(', ')}` : '');
        if (res.added && !bad.length) addTa.value = '';
        ctx.toast(`내 문제 ${res.added}개를 더했어요`, res.added ? 'ok' : 'info');
    }
    async function clearMine() {
        const k = kindNow();
        const n = ((ops.custom || {})[k] || []).length;
        if (!n) { ctx.toast('비울 내 문제가 없어요', 'info'); return; }
        const ok = await ctx.confirm({ title: `${KIND_LABEL[k]} 내 문제 ${n}개를 비울까요?`, body: '기본 문제집은 그대로 남아요.', ok: '비우기', cancel: '그대로 두기' });
        if (!ok) return;
        const res = await ctx.run('quiz.custom', { kind: k, mode: 'clear' });
        if (res.ok) ctx.toast(`내 문제 ${res.cleared || 0}개를 비웠어요`, 'info');
    }

    function paintCur(onAir) {
        const c = ops.cur;
        if (!c) { cur.replaceChildren(h('span', { class: 'gm-info' }, '[다음 문제] 를 누르면 문제가 나오고 방송 화면 가운데에 네모칸이 떠요.')); return; }
        const tiles = q.tiles || [];
        cur.replaceChildren(
            h('div', { class: 'gm-qtiles' }, tiles.map(t => h('span', { class: 'gm-qt s-' + (t.s || 'b') }, t.s === 'b' ? '' : (t.c || '')))),
            h('div', { class: 'gm-qans' },
                h('span', null, KIND_LABEL[c.kind] || '초성', ' · '),
                c.answer ? h('span', null, '정답 ', h('b', null, c.answer)) : h('b', null, '초성만 띄움 — 정답을 몰라 힌트 · 공개는 안 돼요'),
                c.note ? h('span', null, ' · ' + c.note) : null,
                q.revealed ? h('span', { class: 'tag live' }, '공개함') : null,
                onAir ? h('span', { class: 'tag live' }, '방송 중') : h('span', { class: 'tag plain' }, '방송에 안 떠 있음')),
            h('small', { class: 'gm-info' }, '정답 · 분류는 조종실에만 보여요'));
    }
    function paintOrder() {
        const k = kindNow();
        const list = ((ops.order || {})[k]) || [];
        const notes = {};
        ((bank || {})[k] || []).forEach(x => { if (Array.isArray(x)) notes[x[0]] = x[1] || ''; });   // 기본 문제 분류 · 뜻
        (((ops.custom || {})[k]) || []).forEach(x => { if (Array.isArray(x)) notes[x[0]] = x[1] || ''; });
        orderN.textContent = list.length + '개';
        if (!list.length) { order.replaceChildren(h('li', { class: 'empty' }, '남은 문제가 없어요 — [다음 문제] 를 누르면 처음부터 다시 섞어요')); return; }
        order.replaceChildren(...list.map((a, i) => {
            const look = k === 'idiom' ? a.slice(0, 2) + '○○' : initials(a);
            return h('li', { 'data-a': a },
                h('span', { class: 'gm-qn' }, String(i + 1)),
                h('span', { class: 'gm-qa' }, a, h('small', null, look + (notes[a] ? ' · ' + notes[a] : ''))),
                h('span', { class: 'gm-qb' },
                    h('button', { type: 'button', 'data-act': 'up', title: '한 칸 위로', 'aria-label': `${a} 한 칸 위로`, disabled: i === 0 }, '▲'),
                    h('button', { type: 'button', 'data-act': 'down', title: '한 칸 아래로', 'aria-label': `${a} 한 칸 아래로`, disabled: i === list.length - 1 }, '▼'),
                    h('button', { type: 'button', 'data-act': 'top', title: '맨 위로(다음에 나감)', 'aria-label': `${a} 맨 위로`, disabled: i === 0 }, '⤒'),
                    h('button', { type: 'button', 'data-act': 'play', title: '지금 띄우기', 'aria-label': `${a} 지금 띄우기`, class: 'play' }, '▶'),
                    h('button', { type: 'button', 'data-act': 'remove', title: '오늘은 빼기', 'aria-label': `${a} 오늘은 빼기`, class: 'rm' }, '✕')));
        }));
    }

    return {
        render(s) {
            q = s.quiz || {};
            ops = s.quiz_ops || {};
            if (!prepared && s.quiz_ops) {
                prepared = true;
                const o = ops.order || {};
                if (!(o.chosung || []).length || !(o.idiom || []).length) ctx.run('quiz.prepare', {}, { quiet: true });
            }
            const onAir = (s.show || {}).stage === 'quiz';
            hd.setAir(onAir);
            hd.setPill(ops.cur ? (q.revealed ? '정답 공개함' : '문제 나감') : '', q.revealed ? 'live' : 'hot');
            const k = kindNow();
            kindSeg.set(k);
            const o = ops.order || {}, u = ops.used || {};
            kindN.textContent = `남은 ${(o[k] || []).length} · 오늘 나옴 ${(u[k] || []).length}`;
            hintT.disabled = revealT.disabled = !ops.cur || !ops.cur.answer || !!q.revealed;
            downT.disabled = !onAir;
            mineN.textContent = `${KIND_LABEL[k]} 내 문제 ${(((ops.custom || {})[k]) || []).length}개`;
            paint('cur', [ops.cur, q, onAir], () => paintCur(onAir));
            paint('order', [k, o[k], ((ops.custom || {})[k] || []).length, !!bank], paintOrder);
        },
    };
}
