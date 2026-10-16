/* ⏪ [방송 끝] 되돌리기 — 방송을 실수로 끝냈을 때, 방송 전 화면 맨 위에 뜨는 상자 (sturdy 10-17).
   서버 session.undo_end(domain/endundo.py) — 끝내기 직전의 점수판 · 대기함 · 점수 기록 · 시그니처 대기줄 · 무대 · 게임판으로.
   - 끝낸 지 12시간 안이고 아직 새 방송을 시작하지 않았을 때만 보인다(endundo 조각 ready · until).
   - 한 번 묻고(확인 상자) 되살린다. 끝낸 뒤 들어온 후원은 대기함에 이어 붙는다 — 후원 장부는 처음부터 그대로다.
   옛 것: 조종실 타임머신의 '방송 종료 자동 백업' [복구 ↩️]. */
import { clock, num } from './util.js';

/** 보일지 · 무슨 글을 쓸지 — 화면 없이 도는 순수 함수(node 로 검사: v2/tests/test_sturdy_endundo.py) */
export function endUndoView(e, nowSec) {
    e = e || {};
    const at = Number(e.at) || 0, until = Number(e.until) || 0;
    if (!e.ready || !at || (until && nowSec > until)) return { show: false };
    const ago = Math.max(0, Math.floor((nowSec - at) / 60));
    const agoTxt = ago < 1 ? '방금' : ago < 60 ? `${ago}분 전` : `${Math.floor(ago / 60)}시간 ${ago % 60}분 전`;
    const bits = [`${clock(at)}에 끝냄(${agoTxt})`];
    if (e.players) bits.push(`플레이어 ${e.players}명`);
    if (e.score_total) bits.push(`점수 합 ${num(e.score_total)}`);
    if (e.pending) bits.push(`대기함 ${e.pending}건`);
    if (e.queue) bits.push(`시그니처 대기줄 ${e.queue}개`);
    const body = [
        '끝내기 직전으로 돌아가 다시 [방송 중] 이 됩니다.',
        '점수판 · 대기함 · 점수 기록 · 시그니처 대기줄 · 무대가 끝내기 전 그대로 돌아와요.',
        '끝낸 뒤에 들어온 후원은 대기함 뒤에 이어 붙어요. 후원 장부는 처음부터 그대로예요.',
    ];
    if (e.pending) body.push(`대기함 ${e.pending}건도 다시 나타나요.`);
    return { show: true, detail: bits.join(' · '), body: body.join('\n') };
}

export function mountEndUndo(root, ctx) {
    const box = document.createElement('div');
    box.className = 'endundo-box';
    box.hidden = true;
    box.innerHTML = `
        <b class="eu-t">⏪ 방금 끝낸 방송을 되살릴 수 있어요</b>
        <span class="eu-d"></span>
        <button class="btn big wide eu-btn" type="button">방송 끝 되돌리기</button>`;
    root.prepend(box);
    const detail = box.querySelector('.eu-d');
    const btn = box.querySelector('.eu-btn');
    let busy = false;

    const nowSec = () => (ctx.lm && ctx.lm.serverNow ? ctx.lm.serverNow() : Date.now()) / 1000;

    btn.addEventListener('click', async () => {
        if (busy) return;
        const v = endUndoView((ctx.slices || {}).endundo, nowSec());
        if (!v.show) return;
        const ok = await ctx.confirm({ title: '방송 끝을 되돌릴까요?', body: v.body, ok: '되돌리기', cancel: '그대로 두기', danger: false });
        if (!ok) return;
        busy = true;
        btn.disabled = true;
        btn.textContent = '되살리는 중…';
        const res = await ctx.run('session.undo_end', {});
        busy = false;
        btn.disabled = false;
        btn.textContent = '방송 끝 되돌리기';
        if (res.ok) ctx.toast('방송을 끝내기 직전으로 되살렸어요 — 다시 방송 중이에요', 'ok');
    });

    return {
        render(slices) {
            const v = endUndoView((slices || {}).endundo, nowSec());
            box.hidden = !v.show;
            if (v.show && detail.textContent !== v.detail) detail.textContent = v.detail;
        },
    };
}
