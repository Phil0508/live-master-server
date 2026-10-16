/* 🙈 조종 줄 '리액션 모드' 스위치(#ctl-rx, 시안 B) — 옛 조종실 '수동 리액션 모드' 를 옮겼다(대표님 10-17 "가끔 손으로 씀").

   켜면 서버 lights.manual = true → 방송판이 시그니처가 없어도 리액션 모드가 된다(점수판 등 위젯 숨김 · 조명).
   끄면 원래대로. 시그니처가 나오는 동안은 스위치와 상관없이 저절로 리액션 모드다(글자로 '시그 도는 중 · 자동' 이라고 보여 준다).
   방송을 끝내면 서버가 끈다. 명령은 lights.manual {on} 하나뿐(새 명령은 이것 하나 — 설계서 7장).
   ⚠️ 소리 없음. 누르는 동안(서버 답 기다림) 스위치를 다시 못 누르게 잠깐 잠근다 — 두 번 눌러 켜졌다 꺼지는 일이 없게. */
import { h } from './util.js';

export function mountRxSwitch(host, ctx) {
    if (!host) return null;
    const sw = h('input', { type: 'checkbox', class: 'sw', id: 'rx-manual', role: 'switch', 'aria-label': '수동 리액션 모드(방송판 위젯 숨김)' });
    const tb = h('b', { class: 'rx-b' }, '리액션 모드');
    const te = h('em', { class: 'rx-e' }, '꺼짐');
    const label = h('label', { class: 'rx', title: '켜면 시그니처가 없어도 방송판 위젯(점수판 등)을 숨기고 조명을 켜요. 방송을 끝내면 저절로 꺼져요.' },
        sw, h('span', { class: 't' }, tb, te));
    host.append(label);

    let busy = false;
    sw.addEventListener('change', async () => {
        if (busy) return;
        const on = sw.checked;
        busy = true;
        sw.disabled = true;
        paint();
        let res = { ok: false };
        try { res = await ctx.run('lights.manual', { on }); } finally {
            busy = false;
            sw.disabled = false;
        }
        if (res.ok) ctx.toast(on ? '🙈 리액션 모드 켜짐 — 방송판 위젯을 숨겼어요' : '리액션 모드 꺼짐 — 위젯이 다시 보여요', 'ok', 2200);
        paint();
    });

    function paint() {
        const L = (ctx.lm && ctx.lm.get('lights')) || {};
        const q = (ctx.lm && ctx.lm.get('queue')) || {};
        const on = !!L.manual;
        const sig = ((q.items || []).length > 0) && !q.paused;
        if (!busy && sw.checked !== on) sw.checked = on;
        label.classList.toggle('on', busy ? sw.checked : on);
        label.classList.toggle('auto', !on && sig);
        const t = busy ? (sw.checked ? '켜는 중…' : '끄는 중…') : on ? '켜짐 · 위젯 숨김' : sig ? '시그 도는 중 · 자동' : '꺼짐';
        if (te.textContent !== t) te.textContent = t;
    }
    if (ctx.lm) {
        ctx.lm.on('lights', paint);
        ctx.lm.on('queue', paint);
    }
    paint();
    return { render: paint };
}
