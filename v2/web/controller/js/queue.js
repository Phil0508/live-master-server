/* 🎵 시그니처 대기줄 — 맨 앞(첫 줄)이 방송판에서 지금 재생 중인 것.

   [건너뛰기] reaction.skip — 지금 것을 끊고 다음으로
   [멈춤 / 다시 틀기] reaction.pause {paused}
   [전부 지우기] 확인 상자 → reaction.stop
   줄마다 [빼기] reaction.remove {id} · 같은 사람이 같은 시그를 여러 번(×N) 보냈으면 [×N 다 틀기] reaction.playall {id, on}
     (끄면 ×N 묶음을 한 번만 튼다 — 서버 기본)
   소리 막대 → reaction.volume {volume 0~1} — 끄는 동안 쪽지를 쏟지 않게 0.25초 모아서 보낸다.
   ⚠️ 막대를 잡고 있는 동안에는 서버 값으로 막대를 되돌리지 않는다(손 밑에서 막대가 튀지 않게). */
import { h, won } from './util.js';

const VOL_DEBOUNCE_MS = 250;
const VOL_HOLD_MS = 1500;

export function mountQueue(root, ctx) {
    root.innerHTML = `
        <div class="box-head">
            <h2>시그니처 <span class="count-badge zero">0</span></h2>
            <span class="tag warn paused-tag" hidden>멈춤</span>
        </div>
        <div class="q-ctrl">
            <button class="btn skip-btn" type="button">건너뛰기</button>
            <button class="btn pause-btn" type="button">멈춤</button>
            <button class="btn ghost-danger stop-btn" type="button">전부 지우기</button>
        </div>
        <label class="vol"><span>소리</span><input type="range" min="0" max="100" step="1" value="50" aria-label="시그니처 소리 크기"><output>50%</output></label>
        <ol class="qlist"></ol>
        <p class="empty">기다리는 시그니처가 없어요</p>`;
    const badge = root.querySelector('.count-badge');
    const pausedTag = root.querySelector('.paused-tag');
    const skipBtn = root.querySelector('.skip-btn');
    const pauseBtn = root.querySelector('.pause-btn');
    const stopBtn = root.querySelector('.stop-btn');
    const slider = root.querySelector('input[type=range]');
    const out = root.querySelector('output');
    const ol = root.querySelector('.qlist');
    const empty = root.querySelector('.empty');
    const rows = new Map();
    let paused = false, holdUntil = 0, volTimer = 0;

    skipBtn.addEventListener('click', async () => {
        const res = await ctx.run('reaction.skip', {});
        if (res.ok) ctx.toast('지금 시그니처를 건너뛰었어요', 'info');
    });
    pauseBtn.addEventListener('click', async () => {
        const want = !paused;
        const res = await ctx.run('reaction.pause', { paused: want });
        if (res.ok) ctx.toast(want ? '시그니처를 멈췄어요' : '시그니처를 다시 틀어요', 'info');
    });
    stopBtn.addEventListener('click', async () => {
        const n = ((ctx.slices.queue || {}).items || []).length;
        const ok = await ctx.confirm({ title: '시그니처 대기줄을 전부 지울까요?', body: `재생 중인 것까지 ${n}개가 모두 빠집니다. 되돌릴 수 없어요.`,
            ok: '전부 지우기', cancel: '그대로 두기' });
        if (!ok) return;
        const res = await ctx.run('reaction.stop', {});
        if (res.ok) ctx.toast('시그니처 대기줄을 비웠어요', 'info');
    });

    slider.addEventListener('input', () => {
        holdUntil = Date.now() + VOL_HOLD_MS;
        out.textContent = slider.value + '%';
        clearTimeout(volTimer);
        volTimer = setTimeout(async () => {
            holdUntil = Date.now() + VOL_HOLD_MS;
            await ctx.run('reaction.volume', { volume: Number(slider.value) / 100 });
        }, VOL_DEBOUNCE_MS);
    });

    function makeRow(it) {
        const r = { el: h('li', { class: 'qitem', 'data-id': it.id }), sig: '' };
        return r;
    }

    function fill(r, it, isHead) {
        const label = isHead ? (paused ? '멈춤' : '재생 중') : '';
        const playAll = !!it.play_all;
        r.el.className = 'qitem' + (isHead ? ' head' : '') + (isHead && paused ? ' paused' : '');
        r.el.replaceChildren(
            h('div', { class: 'q-main' },
                isHead ? h('span', { class: 'tag ' + (paused ? 'warn' : 'live') }, label) : null,
                h('b', { class: 'q-title' }, it.title || '시그니처'),
                it.count > 1 ? h('span', { class: 'q-count' }, '×' + it.count) : null),
            h('div', { class: 'q-sub' },
                h('span', { class: 'q-who' }, it.donator || '익명'),
                it.amount ? h('span', { class: 'q-amt' }, won(it.amount)) : null),
            h('div', { class: 'q-btns' },
                it.count > 1 ? h('button', {
                    class: 'btn sm' + (playAll ? ' pri' : ''), type: 'button', 'aria-pressed': playAll ? 'true' : 'false',
                    title: playAll ? `×${it.count} 를 모두 틉니다 — 누르면 한 번만` : `×${it.count} 를 한 번만 틉니다 — 누르면 모두`,
                    onclick: async () => {
                        const res = await ctx.run('reaction.playall', { id: it.id, on: !playAll });
                        if (res.ok) ctx.toast(!playAll ? `×${it.count} 다 틀어요` : '한 번만 틀어요', 'info');
                    },
                }, playAll ? `×${it.count} 다 트는 중` : `×${it.count} 다 틀기`) : null,
                h('button', { class: 'btn sm ghost-danger', type: 'button', onclick: async () => {
                    const res = await ctx.run('reaction.remove', { id: it.id });
                    if (res.ok) ctx.toast(`'${it.title || '시그니처'}' 을(를) 대기줄에서 뺐어요`, 'info');
                } }, '빼기')));
    }

    return {
        render(slices) {
            const q = slices.queue || {};
            const items = q.items || [];
            paused = !!q.paused;
            badge.textContent = items.length;
            badge.classList.toggle('zero', !items.length);
            pausedTag.hidden = !paused;
            pauseBtn.textContent = paused ? '다시 틀기' : '멈춤';
            pauseBtn.classList.toggle('pri', paused);
            pauseBtn.setAttribute('aria-pressed', String(paused));
            skipBtn.disabled = !items.length;
            stopBtn.disabled = !items.length;
            empty.hidden = items.length > 0;
            if (Date.now() > holdUntil && q.volume != null) {
                const v = String(Math.round(Number(q.volume) * 100));
                if (slider.value !== v) slider.value = v;
                out.textContent = v + '%';
            }
            const ids = new Set(items.map(x => x.id));
            for (const [id, r] of rows) if (!ids.has(id)) { r.el.remove(); rows.delete(id); }
            items.forEach((it, i) => {
                let r = rows.get(it.id);
                if (!r) { r = makeRow(it); rows.set(it.id, r); }
                const sig = JSON.stringify([it, i === 0, paused]);
                if (sig !== r.sig) { fill(r, it, i === 0); r.sig = sig; }
                if (ol.children[i] !== r.el) ol.insertBefore(r.el, ol.children[i] || null);
            });
        },
    };
}
