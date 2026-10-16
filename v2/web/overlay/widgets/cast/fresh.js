/* 💬 cast 조각 칸(say · up · fx · fx_clear) 하나를 지켜보다가 **새로 쏜 것**만 넘긴다.
   - id 가 바뀐 칸만(다른 칸이 바뀌어 조각이 통째로 와도 다시 안 터진다)
   - 지금 막 온 것만: 실시간 쪽지면 그대로, 다시 붙으며 받은 통째(snapshot)면 쏜 지 GRACE_MS 안의 것만
     (옛 것은 신호만 쐈다 — 다시 붙은 창에서 지난 연출이 또 터지면 안 된다) */
export const GRACE_MS = 3000;

export function watchCast(lm, opts, key, fn) {
    let last;                       // 처음엔 모른다(undefined) — 첫 통째에서 정한다
    lm.on('cast', c => {
        const row = c && c[key];
        const id = row ? row.id : null;
        if (id === last) return;
        last = id;
        if (!row) return;
        const at = Number(row.at) || 0;
        const now = (typeof lm.serverNow === 'function') ? lm.serverNow() : Date.now();
        if (!(opts.isFresh(at) && now - at < GRACE_MS)) return;
        try { fn(row); } catch (e) { console.error('[조종 연출]', key, e); }
    });
}
