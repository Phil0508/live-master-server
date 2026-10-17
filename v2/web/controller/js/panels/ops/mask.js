/* 🙈 메시지 거르기 — 방송 화면에 나가는 후원 메시지에서 걸린 부분을 ●●● 로(10-17 mask, 서버 domain/mask.py).
   장부 · 대기함엔 원문 그대로. 이름(닉네임)은 안 건드린다.
   - 규칙 스위치 셋: 전화번호 · 계좌번호 꼴 숫자 · 인터넷 주소/메일 → mask.rule {key, on}
   - 금칙어 목록(기본 빈 목록): 칸에 적고 [더하기] → mask.word.add {word}(쉼표로 여러 개) · 알약 × → mask.word.remove
     [추천 목록 넣기] → mask.word.recommend(흔한 욕설 몇 개) · [모두 지우기] → 화면 안 확인 상자 → mask.word.clear
   - 시험해 보기: 글을 넣으면 방송에 나갈 모습(POST /api/mask/preview — 장부에 안 적는다)
   - 지금 가린 후원 N건 — [가리기]는 대기함 카드 · 장부 줄에서 누른다. */
import { h, num, sigOf, onEnter, once, switchEl, blockHead, fill, api } from './common.js';

const RULES = [['phone', '전화번호', '010-1234-5678 · 010 1234 5678 · 02-123-4567'],
    ['account', '계좌번호 꼴 숫자', '숫자 10자리 넘게(쉼표 넣은 금액은 그대로)'],
    ['url', '인터넷 주소 · 메일', 'www · http · ○○.com · ○○.kr · 메일 주소']];
const HIT = { phone: '전화번호', account: '계좌번호', url: '주소', word: '금칙어' };

export function mountMask(el, ctx) {
    const sws = RULES.map(([key, label, hint]) => {
        const sw = switchEl(label, async on => {
            const res = await ctx.run('mask.rule', { key, on });
            if (res.ok) ctx.toast(on ? `${label} — 방송 화면에서 가려요` : `${label} — 이제 가리지 않아요`, on ? 'ok' : 'info');
            else sw.input.checked = !on;
        }, hint);
        return { key, sw, row: h('div', { class: 'mk-rule' }, sw.el, h('span', { class: 'ops-sub' }, hint)) };
    });
    const addIn = h('input', { type: 'text', maxlength: '120', autocomplete: 'off', class: 'grow', placeholder: '가릴 낱말 — 쉼표로 여러 개', 'aria-label': '가릴 낱말' });
    const addBtn = h('button', { type: 'button', class: 'btn pri sm', onclick: () => once(addBtn, add) }, '＋ 더하기');
    const recBtn = h('button', { type: 'button', class: 'btn sm', title: '흔한 욕설 몇 개를 한 번에 넣어요 (넣은 뒤 빼도 돼요)', onclick: () => once(recBtn, recommend) }, '추천 목록 넣기');
    const clrBtn = h('button', { type: 'button', class: 'btn sm ghost-danger', onclick: () => once(clrBtn, clearAll) }, '모두 지우기');
    const chips = h('div', { class: 'mk-chips' });
    const empty = h('p', { class: 'ops-hint' }, '아직 금칙어가 없어요 — 칸에 적거나 [추천 목록 넣기]');
    const count = h('span', { class: 'ops-sub' });
    const tryIn = h('input', { type: 'text', maxlength: '300', autocomplete: 'off', class: 'grow', placeholder: '예) 연락줘 010-1234-5678', 'aria-label': '시험해 볼 메시지' });
    const tryOut = h('p', { class: 'mk-try-out', 'aria-live': 'polite' });
    const hidNote = h('p', { class: 'ops-note', hidden: true });

    el.classList.add('ops', 'ops-mask');
    el.append(
        h('p', { class: 'ops-hint mk-lead' }, '방송 화면에 나가는 후원 메시지(팝업 · 시그니처 카드 · 소액 띠 · 출연진 전광판)에서 걸린 부분을 ●●● 로 바꿔요. ',
            h('b', null, '장부 · 대기함엔 원문 그대로'), '예요. 후원자 이름(닉네임)은 안 건드려요.'),
        h('section', { class: 'ops-blk' }, blockHead('저절로 가리는 것'), sws.map(s => s.row)),
        h('section', { class: 'ops-blk' }, h('div', { class: 'ops-bh' }, h('h3', null, '금칙어'), count),
            chips, empty,
            h('div', { class: 'ops-row wrap mk-add' }, addIn, addBtn),
            h('div', { class: 'ops-row wrap' }, recBtn, clrBtn),
            h('p', { class: 'ops-hint' }, '글자 사이에 숫자 · 기호를 끼워도 잡아요(시1발 · 시.발). 띄어 쓴 것은 안 잡아요 — 다른 말을 가리지 않게.')),
        h('section', { class: 'ops-blk' }, blockHead('시험해 보기', '방송에 이렇게 나가요'),
            h('div', { class: 'ops-row wrap' }, tryIn), tryOut),
        h('section', { class: 'ops-blk' }, blockHead('후원 하나만 가리기'),
            h('p', { class: 'ops-hint' }, '대기함 카드 · 장부 줄의 [가리기] 를 누르면 그 후원 메시지를 방송 화면에서 통째로 숨겨요. 떠 있는 팝업 · 시그니처 카드에서도 바로 사라져요. [보이기] 로 되돌려요.'),
            hidNote),
    );

    const M = () => ctx.slices.mask || {};

    async function add() {
        const v = addIn.value.trim();
        if (!v) { ctx.toast('가릴 낱말을 적어 주세요', 'info'); addIn.focus(); return; }
        const res = await ctx.run('mask.word.add', { word: v });
        if (!res.ok) return;
        addIn.value = '';
        const n = (res.added || []).length;
        ctx.toast(n ? `🙈 ${res.added.join(' · ')} — 방송 화면에서 가려요` : '이미 목록에 있어요', n ? 'ok' : 'info');
        runTry();
    }
    onEnter(addIn, () => once(addBtn, add));

    async function recommend() {
        const res = await ctx.run('mask.word.recommend', {});
        if (!res.ok) return;
        const n = (res.added || []).length;
        ctx.toast(n ? `추천 금칙어 ${n}개를 넣었어요 — 알약 × 로 뺄 수 있어요` : '추천 목록은 이미 다 들어가 있어요', n ? 'ok' : 'info');
        runTry();
    }

    async function clearAll() {
        const n = (M().words || []).length;
        if (!n) { ctx.toast('지울 금칙어가 없어요', 'info'); return; }
        const ok = await ctx.confirm({ title: '금칙어를 모두 지울까요?', body: `${num(n)}개를 지워요. 전화번호 · 계좌 · 주소 가리기는 그대로예요.`, ok: '모두 지우기', cancel: '그대로 두기' });
        if (!ok) return;
        const res = await ctx.run('mask.word.clear', {});
        if (res.ok) ctx.toast('금칙어를 모두 지웠어요', 'info');
        runTry();
    }

    async function removeWord(w, btn) {
        await once(btn, async () => {
            const res = await ctx.run('mask.word.remove', { word: w });
            if (res.ok) ctx.toast(`'${w}' 를 뺐어요`, 'info');
            runTry();
        });
    }

    /* 시험해 보기 — 적는 대로(0.3초 쉬면) 서버에 묻는다 */
    let tryT = 0, tryN = 0;
    function runTry() {
        clearTimeout(tryT);
        tryT = setTimeout(async () => {
            const text = tryIn.value;
            const my = ++tryN;
            if (!text.trim()) { fill(tryOut); tryOut.className = 'mk-try-out'; return; }
            const r = await api('/api/mask/preview', { text });
            if (my !== tryN) return;
            if (!r.ok) { fill(tryOut, '확인하지 못했어요 — ' + r.error); tryOut.className = 'mk-try-out bad'; return; }
            const hits = r.data.hits || [];
            tryOut.className = 'mk-try-out' + (hits.length ? ' hit' : ' clean');
            fill(tryOut, h('span', { class: 'mk-try-k' }, hits.length ? '⚠ ' + hits.map(k => HIT[k] || k).join(' · ') : '✓ 그대로 나가요'),
                h('span', { class: 'mk-try-t' }, r.data.text || ''));
        }, 300);
    }
    tryIn.addEventListener('input', runTry);

    let last = '';
    return {
        render() {
            const m = M();
            const words = m.words || [];
            const rules = m.rules || {};
            const hid = (m.hidden || []).length;
            const s = sigOf(words, rules, hid);
            if (s === last) return;
            last = s;
            sws.forEach(({ key, sw }) => sw.set(rules[key] !== false));
            fill(chips, words.map(w => {
                const b = h('button', { type: 'button', class: 'mk-x', title: `'${w}' 빼기`, 'aria-label': `${w} 빼기` }, '×');
                b.addEventListener('click', () => removeWord(w, b));
                return h('span', { class: 'mk-chip' }, h('span', { class: 'mk-w' }, w), b);
            }));
            empty.hidden = words.length > 0;
            clrBtn.disabled = !words.length;
            count.textContent = words.length ? `${num(words.length)}개` : '';
            hidNote.hidden = !hid;
            hidNote.textContent = hid ? `🙈 지금 가린 후원 ${num(hid)}건 — 방송 화면엔 그 메시지가 안 나가요` : '';
        },
    };
}
