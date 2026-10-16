/* 🔊 자동재생 차단 경고 띠 — 브라우저가 소리 있는 재생을 막으면 맨 위에 빨간 띠: '화면 아무 곳이나 클릭하세요'.
   한 번 누르면(클릭 · 키 · 터치) 시그니처 위젯(signature.js)이 소리를 살리고 이 띠를 내린다.

   ⚠️ 이 칸은 **알림창 화면(?only=alert, 옛 /alertbox)에만** 있다 — 옛 것이 그랬다:
      · 옛 방송판(overlay.html)은 2026-08-13 대표님 요청으로 띠를 아예 안 띄운다(커밋 e4303aa — OBS 는 자동재생이 열려 있어
        실제로는 거의 안 막히고, 막혀도 방송 화면에 빨간 띠가 나가면 안 된다). 소리 살리기(클릭)는 방송판에서도 그대로 된다.
      · 옛 알림창(alertbox.html)은 막히면 띠를 띄웠다.
   층: groups/sigfx.js 60(맨 위 한가운데).

   다른 위젯에 주는 것(stage.provide('autoplayWarn')): show() · hide() */
export function mount(root, lm, opts) {
    root.innerHTML = '<div class="sfx-unlock">🔊 브라우저 자동재생 차단을 해제하려면 화면 아무 곳이나 클릭하세요!</div>';
    const el = root.firstElementChild;
    opts.stage.provide('autoplayWarn', {
        show() { el.classList.add('on'); },
        hide() { el.classList.remove('on'); },
    });
}
