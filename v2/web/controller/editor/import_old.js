/* 📥 옛 배치 가져오기 — 옛 방송판의 위젯 자리 파일(layout.json, 옛 편집기가 저장한 것)을 v2 자리로 옮긴다.
   옛 것: 모든 위젯이 '왼쪽 위' 기준(left · top · scale, transform-origin top left).
   v2: 칸마다 기준점(anchor)이 다르다(점수판 · 계좌 · 퇴근빵 = 오른쪽 위 · 팝업 · 주사위판 = 가운데 위 · …) →
       기준점이 다른 칸은 **실제 크기를 재서** 바꾼다. 그래서 서버가 아니라 편집기(방송판이 떠 있는 곳)에서 한다.
   옛 규칙 그대로: __v 가 2 이상인 파일만 읽는다(옛 방송판도 그보다 옛 파일은 무시했다 — 게이지 y=1598 같은 못된 값).
                  __free 가 아니면 위아래 안전지대(115 ~ 954) 안으로 붙잡는다. 전광판(notice)은 코드가 자리를 정해 안 옮긴다.
   ⚠️ 크기가 0 인 칸(내용이 없어 쪼그라든 것)은 기준점이 왼쪽 위인 칸만 옮기고, 나머지는 '확인 필요' 로 돌려준다. */

// 옛 위젯 이름 → v2 칸 이름(layers.js id). 옛 퇴근빵 칸(home-race)은 지옥탈출도 같이 썼다.
export const OLD_TO_V2 = {
    'ranking': ['ranking'], 'gauge': ['gauge'], 'account': ['account'], 'match': ['match'], 'roulette': ['roulette'],
    'slot': ['slot'], 'dicegame': ['dicegame'], 'dgscore': ['dgscore'], 'donor-rank': ['donorRank'], 'sig-tally': ['sigTally'],
    'siggame': ['siggame'], 'home-race': ['homeRace', 'hell'], 'popup': ['scorePopup'], 'takeover': ['takeover'],
    'karaoke': ['karaoke'], 'acct_video': ['acctVideo'], 'fundjar': ['fundjar'], 'pinball': ['pinball'], 'best': ['best'],
};
const SAFE_TOP = 115, SAFE_BOT = 954, W = 1080;

/** 옛 파일 → [{oldId, id, x, y, scale, why?}] — size(id) 는 그 칸의 '배율 1' 크기 {w, h}(못 재면 null) */
export function convert(old, layersById, size) {
    if (!old || typeof old !== 'object' || Array.isArray(old)) return { error: '배치 파일(JSON 사전)이 아니에요' };
    if (!((old.__v || 0) >= 2)) return { error: '옛 판(__v 2 미만) 배치 파일이에요 — 옛 방송판도 이 파일은 안 읽었어요. 옛 편집기에서 한 번 저장한 파일을 주세요' };
    const free = !!old.__free;
    const out = [], skipped = [];
    for (const [oldId, ids] of Object.entries(OLD_TO_V2)) {
        const c = old[oldId];
        if (!c || typeof c !== 'object') continue;
        let x = Number(c.x_px) || 0, y = Number(c.y_px) || 0;
        const s = Number(c.scale) > 0 ? Number(c.scale) : 1;
        if (!free) { x = Math.min(Math.max(x, 0), W); y = Math.min(Math.max(y, SAFE_TOP), SAFE_BOT); }
        for (const id of ids) {
            const L = layersById[id];
            if (!L) { skipped.push({ oldId, id, why: 'v2 에 없는 칸' }); continue; }
            const a = L.anchor || 'tl';
            if (a === 'tl') { out.push({ oldId, id, x, y, scale: s }); continue; }
            const sz = size(id);
            if (!sz || !(sz.w > 4)) { skipped.push({ oldId, id, why: '지금 내용이 없어 크기를 못 쟀어요 — 내용이 보일 때 다시 하거나 손으로 옮겨 주세요' }); continue; }
            const w = sz.w * s, h = (sz.h || 0) * s;
            if (a === 'tr') out.push({ oldId, id, x: x + w, y, scale: s });
            else if (a === 'tc') out.push({ oldId, id, x: x + w / 2, y, scale: s });
            else if (a === 'cc') out.push({ oldId, id, x: x + w / 2, y: y + h / 2, scale: s });
            else skipped.push({ oldId, id, why: '모르는 기준점 ' + a });
        }
    }
    return { rows: out.map(r => Object.assign(r, { x: Math.round(r.x), y: Math.round(r.y), scale: Math.round(r.scale * 1000) / 1000 })), skipped };
}
