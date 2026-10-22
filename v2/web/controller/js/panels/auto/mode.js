/* 📚 학습 · ☕ 휴식 — 대표님 10-22 "이정도야": 조종실에 보이는 건 두 가지뿐.
     📚 학습(서버 mode 'shadow', 평소) — 점수는 사람이 준다. 기계도 후원마다 답을 적고 사람이 준 것과 맞춰 채점(→ 숫자 칸 · 그날 성적).
     ☕ 휴식(서버 mode 'on') — 확실한 투네 후원은 기계가 바로 준다. 애매한 것 · 계좌 입금은 초록 알림(restmode.js). 방송 끝에 저절로 학습.
   켜고 끄기는 머리줄 [☕ 휴식] 과 같은 길(./rest.js setRest — 켤 때만 화면 안 상자로 한 번 묻는다).
   고급(접어 둠 — 지금은 안 써도 된다): AI 에게도 묻기 · 🤖 AI 가 직접 배정(use_ai_assign, 기본 끔) · 금액 상한(assign_max).
     AI 직접 배정은 휴식일 때만 움직이고, AI 확신 0.9 이상 · 지금 판 선수 · 한 사람 · 상한 미만 · 애매함 없음일 때만 준다.
   서버: auto.set {mode?, use_ai?, use_ai_assign?, assign_max?} */
import { h, num, MODES, SHOWN_MODES, aiHitRate } from './common.js';
import { setRest } from './rest.js';
import { switchEl, blockHead, sigOf, fill } from '../ops/common.js';

export function mountMode(ctx) {
    const now = h('p', { class: 'ops-now au-now', 'aria-live': 'polite' });
    const btns = {};
    const seg = h('div', { class: 'au-seg', role: 'radiogroup', 'aria-label': '학습 · 휴식' },
        SHOWN_MODES.map(k => {
            const m = MODES[k];
            const b = h('button', { type: 'button', class: 'au-segb', 'data-mode': k, role: 'radio', 'aria-checked': 'false',
                onclick: () => pick(k) },
                h('span', { class: 'au-segi', 'aria-hidden': 'true' }, m.icon),
                h('b', null, m.label),
                h('small', null, m.desc));
            btns[k] = b;
            return b;
        }));
    const ai = switchEl('AI 에게도 묻기', async on => {
        const res = await ctx.run('auto.set', { use_ai: on });
        if (res.ok) ctx.toast(on ? '🤖 이름 · 별명 · 이력으로 못 풀면 AI 에게도 물어요' : '이름 · 별명 · 이력으로만 판단해요 (AI 안 부름)', 'info');
        last = '';
        ctx.rerender();
    }, 'AI 는 혼자서는 절대 자동으로 주지 않아요(최대 0.88) — 카드에 이름을 보여 줄 뿐이에요');
    const aiNote = h('span', { class: 'ops-hint inline' }, "AI 가 꺼진 서버면 저절로 안 불러요. 아래 'AI 가 직접 배정' 을 켜야만 AI 가 스스로 줘요.");
    const aiAssign = switchEl('🤖 AI 가 직접 배정 (확신 0.9 이상)', async on => {
        const ap = ctx.slices.autopilot || {};
        if (on) {
            const r = aiHitRate((ap.stats || {}).total);
            const lines = [r ? `AI 채점(지금까지): ${num(r.judged)}건 중 ${num(r.hit)}건 맞힘(${r.pct}%).` : '⚠️ 아직 AI 채점 기록이 없어요 — 학습으로 먼저 쌓아 보시는 걸 권해요.',
                '', '켜면 ☕ 휴식일 때:', '· 이름 · 별명 · 이력으로 확실하지 않은 후원을 AI 에게 한 번 물어요',
                `· AI 확신 0.9 이상 · 지금 판 선수 · 한 사람 · ${num(ap.assign_max || 100000)}원 미만일 때만 AI 가 줘요`,
                '· 조금이라도 애매하면(선수 둘 · 나눔 말 · 금액 다름 · 만 원 경계 · 계좌 · 연속 후원 …) 안 주고 초록 알림으로 불러요',
                '잘못 갔으면 평소처럼 [되돌리기] — 후원이 대기함으로 돌아와요.'];
            const ok = await ctx.confirm({ title: '🤖 AI 가 직접 배정할까요?', body: lines.join('\n'), ok: '켜기', cancel: '그대로 두기', danger: false });
            if (!ok) { aiAssign.set(false); last = ''; ctx.rerender(); return; }
        }
        const res = await ctx.run('auto.set', { use_ai_assign: on });
        if (res.ok) ctx.toast(on ? '🤖 확실한 것(0.9↑)은 AI 도 직접 줘요 — ☕ 휴식일 때만' : 'AI 는 이제 직접 안 줘요(카드에 이름만)', 'info');
        last = '';
        ctx.rerender();
    }, '☕ 휴식일 때만 움직여요. 📚 학습에서는 AI 가 했을 일만 따로 채점해요.');
    const capIn = h('input', { type: 'text', inputmode: 'numeric', class: 'au-cap', 'aria-label': '기계가 줄 수 있는 금액 상한(원)', title: '이 금액 이상은 기계(규칙 · AI)가 절대 안 주고 초록 알림으로 불러요' });
    capIn.addEventListener('change', async () => {
        const v = capIn.value.replace(/[^0-9]/g, '');
        const res = await ctx.run('auto.set', { assign_max: Number(v) || 0 });
        if (res.ok) ctx.toast(`기계는 ${num(res.assign_max)}원 미만만 줘요 — 그 이상은 사람이`, 'info');
        last = '';
        ctx.rerender();
    });
    const aiScore = h('p', { class: 'ops-hint au-aiscore', 'aria-live': 'polite' });
    const adv = h('details', { class: 'au-adv' },
        h('summary', null, '고급 — 지금은 안 써도 돼요 (AI 에게도 묻기 · AI 직접 배정 · 금액 상한)'),
        h('div', { class: 'ops-row wrap au-ai' }, ai.el, aiNote),
        h('div', { class: 'ops-row wrap au-ai' }, aiAssign.el, h('label', { class: 'au-capl' }, '금액 상한 ', capIn, '원 미만만')),
        aiScore);
    const el = h('section', { class: 'ops-blk au-mode' },
        blockHead('📚 학습 · ☕ 휴식', '평소엔 학습 — 자리를 비울 땐 휴식'),
        now, seg, adv);

    let busy = false;
    async function pick(mode) {
        const ap = ctx.slices.autopilot || {};
        if (busy || ap.mode === mode) return;
        busy = true;
        Object.values(btns).forEach(b => { b.disabled = true; });
        try { await setRest(ctx, mode === 'on'); } finally {
            busy = false;
            Object.values(btns).forEach(b => { b.disabled = false; });
        }
        last = '';
        ctx.rerender();
    }

    let last = '';
    function render(ap) {
        const mode = ap.mode || 'off';
        const sig = sigOf(mode, ap.use_ai !== false, ap.use_ai_assign, ap.assign_max, (ap.stats || {}).total);
        if (sig === last) return;
        last = sig;
        Object.entries(btns).forEach(([k, b]) => {
            const on = k === mode;
            b.classList.toggle('on', on);
            b.setAttribute('aria-checked', on ? 'true' : 'false');
        });
        el.dataset.mode = mode;
        if (mode === 'on') fill(now, '지금 ', h('b', null, '☕ 휴식'), ' — 확실한 투네 후원은 기계가 줘요 · 애매한 것 · 계좌 입금은 초록 알림 · 방송이 끝나면 저절로 학습');
        else if (mode === 'shadow') fill(now, '지금 ', h('b', null, '📚 학습'), ' — 점수는 사람이 줘요 · 기계는 후원마다 답만 적고 채점해요');
        else fill(now, '지금 ', h('b', null, '⏸ 끔'), ' — 기계가 아무것도 안 해요 · 위에서 📚 학습을 누르면 다시 채점해요');
        now.classList.toggle('off', mode === 'off');
        ai.set(ap.use_ai !== false);
        aiAssign.set(!!ap.use_ai_assign);
        if (document.activeElement !== capIn) capIn.value = num(ap.assign_max || 100000);
        const tot = (ap.stats || {}).total || {};
        const r = aiHitRate(tot);
        fill(aiScore, h('b', null, 'AI 채점'), ' — ',
            r ? `AI 가 줬을 ${num(r.judged)}건 중 ${num(r.hit)}건 맞힘(${r.pct}%)` : '아직 채점된 게 없어요',
            ` · AI 보류 ${num(tot.ai_held || 0)} · AI 가 줌 ${num(tot.ai_done || 0)} · 되돌림 ${num(tot.ai_undone || 0)}`,
            h('br'), h('span', { class: 'ops-dim' }, r && r.judged >= 30 && r.pct >= 95
                ? '✓ AI 맞힌 비율이 충분히 쌓였어요 — 켜도 좋아요'
                : 'AI 맞힌 비율이 쌓이면 켜세요 (30건 넘게 · 95% 이상 권장)'));
    }
    return { el, render };
}
