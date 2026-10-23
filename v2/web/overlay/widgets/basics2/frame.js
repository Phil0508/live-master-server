/* 🖼 방송 테두리 — 화면 가장자리에 씌우는 장식 틀(대표님 10-23 — 드리미나로 만든 파란 크리스탈 · 금장식, 위 간판 글자 없음).
   look.frame 이 켜져 있으면 보인다(조종실 ⚙ 설정 → 📺 무대 → 테마 칸의 [🖼 방송 테두리]).
   가운데는 그림 자체가 투명이라 방송 화면이 그대로 보인다. 칸은 층 표 맨 아래(z 1) — 점수판 · 알림 · 시그니처는 모두 테두리 위에 뜬다.
   그림: /overlay/frames/crystal.webp(1080×1920). 바꿀 때는 같은 크기 · 가운데 투명으로.
   🏦🐉 stage.provide('frame') — hold(on): 계좌 대형 연출 '용 + 테두리' 세트(10-24)에서 그 시그니처가 도는 동안만 씌운다
   (widgets/signature.js). 스위치가 켜져 있거나 · 붙잡혀 있으면 보인다. 붙잡힐 때 바로 뜨게 6초 뒤 그림을 미리 받아 둔다. */
const SRC = '/overlay/frames/crystal.webp';
const PRELOAD_MS = 6000;

export function mount(root, lm, opts) {
    root.innerHTML = '<img class="ov-frame" alt="" draggable="false">';
    const img = root.firstElementChild;
    let look = false, held = false, on = null;
    const load = () => { if (!img.getAttribute('src')) img.setAttribute('src', SRC); };
    function apply() {
        const want = look || held;
        if (want === on) return;
        on = want;
        if (want) load();                                   // 처음 켤 때 받는다(아직 안 받았으면)
        img.classList.toggle('on', want);
    }
    lm.on('look', l => { look = !!(l && l.frame); apply(); });
    setTimeout(load, PRELOAD_MS);
    if (opts && opts.stage) opts.stage.provide('frame', { hold(v) { held = !!v; apply(); } });
}
