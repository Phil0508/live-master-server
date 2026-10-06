/* ✂️ 머리줄 [✂ 클립] — 옛 조종실처럼 어느 탭에서든 한 번에. 점 색 = OBS 저장 담당 상태(초록 · 노랑 · 회색).
   누르면 clip.now — 방송판(OBS)이 90초 뒤 '앞 90초 + 뒤 90초' 를 저장한다. 자세한 것은 ✂️ 클립 탭.
   OBS 상태는 서버 메모리에만 있어 GET /api/clip 으로 읽는다 — 방송 중에만 30초마다(방송 전엔 안 묻는다). */
import { h } from './util.js';
import { obsText } from './panels/more/clip.js';

export function mountClipButton(host, ctx) {
    const dot = h('i', { 'aria-hidden': 'true' });
    const btn = h('button', { type: 'button', class: 'pill clip-btn', 'data-s': 'off', title: 'OBS 상태를 확인하는 중…', hidden: true }, dot, h('span', { class: 't' }, '✂ 클립'));
    host.prepend(btn);
    let obs = null, last = 0, busy = false, live = false;

    function paint() {
        const [lv, txt] = obsText(obs);
        btn.dataset.s = lv;
        btn.title = txt.replace(' (아래 "처음 한 번만 할 것")', ' (✂️ 클립 탭 안내)') + ' — 누르면 지금 순간을 클립으로';
    }
    async function poll() {
        last = Date.now();
        try {
            const r = await fetch('/api/clip', { cache: 'no-store' });
            if (r.ok) { const d = await r.json(); obs = d.obs || null; paint(); }
        } catch (e) { /* 다음에 */ }
    }
    btn.addEventListener('click', async () => {
        if (busy) return;
        busy = true;
        btn.disabled = true;
        const res = await ctx.run('clip.now', {});
        busy = false;
        btn.disabled = false;
        if (!res.ok) return;
        obs = res.obs || obs;
        paint();
        const ok = obs && obs.alive && obs.level >= 4 && obs.rb !== false;
        ctx.toast(ok ? '✂️ 앞 90초 + 뒤 90초 — 90초 뒤에 OBS 가 저장해요' : '✂️ 목록에만 적었어요 — OBS 연결을 확인하세요(✂️ 클립 탭)', ok ? 'ok' : 'info');
    });
    setInterval(() => { if (live && Date.now() - last > 30000) poll(); }, 5000);

    return {
        render(slices, view) {
            const want = !!(slices.session || {}).live && view === 'live';
            if (want !== live) { live = want; btn.hidden = !live; if (live) poll(); }
        },
    };
}
