/* 🤖 자동 진행 — 모드 스위치(끔 · 그림자 · 켬) + AI 에게도 묻기.
   [켬] 은 돈이 걸린 일이라 화면 안 상자로 한 번 묻는다 — 그림자 기록(맞힌 비율)을 먼저 보여 준다.
   서버: auto.set {mode?, use_ai?} */
import { h, num, MODES, hitRate, hitLine } from './common.js';
import { switchEl, blockHead, sigOf, fill } from '../ops/common.js';

export function mountMode(ctx) {
    const now = h('p', { class: 'ops-now au-now', 'aria-live': 'polite' });
    const btns = {};
    const seg = h('div', { class: 'au-seg', role: 'radiogroup', 'aria-label': '자동 진행 모드' },
        Object.entries(MODES).map(([k, m]) => {
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
    }, 'AI 는 혼자서는 절대 자동으로 주지 않아요(최대 0.88) — 배지에 이름을 보여 줄 뿐이에요');
    const aiNote = h('span', { class: 'ops-hint inline' }, 'AI 는 혼자서 자동으로 주지 않아요 — 배지에 이름만 보여 줘요. AI 가 꺼진 서버면 저절로 안 불러요.');
    const el = h('section', { class: 'ops-blk au-mode' },
        blockHead('🤖 자동 진행', '후원 → 누구 점수인지 · 금액 게임을 기계가'),
        now, seg,
        h('div', { class: 'ops-row wrap au-ai' }, ai.el, aiNote));

    let busy = false;
    async function pick(mode) {
        const ap = ctx.slices.autopilot || {};
        if (busy || ap.mode === mode) return;
        if (mode === 'on') {
            const st = (ap.stats || {}).total || {};
            const r = hitRate(st);
            const lines = [hitLine(st) + '.'];
            if (r) lines.push(`틀림 ${num(st.disagree || 0)}건 · 몰라서 보류 ${num(st.unknown || 0)}건 · 무시 ${num(st.ignored || 0)}건`);
            else lines.push('⚠️ 맞힌 비율을 모르는 채로 켜는 거예요. 그림자로 먼저 며칠 돌려 보시는 걸 권해요.');
            if (r && r.pct < 95) lines.push(`⚠️ 맞힌 비율이 95% 보다 낮아요 — 틀리게 주는 일이 ${100 - r.pct}% 쯤 생길 수 있어요.`);
            lines.push('', '켜면 그다음 들어오는 후원부터:', '· 확실한 것(거의 확실)만 기계가 바로 점수를 줘요', '· 애매한 것은 대기함에 "🤖 몰라서 보류" 로 남아요',
                '· 금액 게임 줄이 있으면 기계가 돌려요', '잘못 갔으면 평소처럼 [되돌리기] — 후원이 대기함으로 돌아와요.');
            const ok = await ctx.confirm({ title: '🤖 자동 진행을 켤까요?', body: lines.join('\n'), ok: '켜기', cancel: '그대로 두기', danger: false });
            if (!ok) return;
        }
        busy = true;
        Object.values(btns).forEach(b => { b.disabled = true; });
        const res = await ctx.run('auto.set', { mode });
        busy = false;
        Object.values(btns).forEach(b => { b.disabled = false; });
        if (res.ok) {
            const m = MODES[mode];
            ctx.toast(`${m.icon} 자동 진행: ${m.label}` + (mode === 'on' ? ' — 확실한 후원은 기계가 바로 줘요' : mode === 'shadow' ? " — 기계는 '했을 일' 만 적어요" : ''), mode === 'on' ? 'ok' : 'info');
        }
        last = '';
        ctx.rerender();
    }

    let last = '';
    function render(ap) {
        const mode = ap.mode || 'off';
        const sig = sigOf(mode, ap.use_ai !== false, (ap.stats || {}).total);
        if (sig === last) return;
        last = sig;
        Object.entries(btns).forEach(([k, b]) => {
            const on = k === mode;
            b.classList.toggle('on', on);
            b.setAttribute('aria-checked', on ? 'true' : 'false');
        });
        const m = MODES[mode] || MODES.off;
        el.dataset.mode = mode;
        if (mode === 'on') fill(now, '지금 ', h('b', null, '🤖 켬'), ' — 확실한 후원은 기계가 바로 줘요 · 애매한 건 대기함에 보류');
        else if (mode === 'shadow') fill(now, '지금 ', h('b', null, '👀 그림자'), " — 기계는 '했을 일' 만 적어요 · ", h('span', { class: 'ops-dim' }, hitLine((ap.stats || {}).total, '지금까지')));
        else fill(now, '지금 ', h('b', null, '⏸ 끔'), ' — ', h('span', { class: 'ops-dim' }, m.desc));
        now.classList.toggle('off', mode === 'off');
        ai.set(ap.use_ai !== false);
    }
    return { el, render };
}
