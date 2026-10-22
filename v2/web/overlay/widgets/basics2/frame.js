/* 🖼 방송 테두리 — 화면 가장자리에 씌우는 장식 틀(대표님 10-23 — 드리미나로 만든 파란 크리스탈 · 금장식, 위 간판 글자 없음).
   look.frame 이 켜져 있으면 보인다(조종실 ⚙ 설정 → 📺 무대 → 테마 칸의 [🖼 방송 테두리]).
   가운데는 그림 자체가 투명이라 방송 화면이 그대로 보인다. 칸은 층 표 맨 아래(z 1) — 점수판 · 알림 · 시그니처는 모두 테두리 위에 뜬다.
   그림: /overlay/frames/crystal.webp(1080×1920). 바꿀 때는 같은 크기 · 가운데 투명으로. */
const SRC = '/overlay/frames/crystal.webp';

export function mount(root, lm) {
    root.innerHTML = '<img class="ov-frame" alt="" draggable="false">';
    const img = root.firstElementChild;
    let on = null;
    lm.on('look', look => {
        const want = !!(look && look.frame);
        if (want === on) return;
        on = want;
        if (want && !img.getAttribute('src')) img.setAttribute('src', SRC);     // 처음 켤 때만 받는다
        img.classList.toggle('on', want);
    });
}
