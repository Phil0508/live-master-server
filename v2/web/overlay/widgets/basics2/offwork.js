/* 🏃 퇴근 성공 · 🔥 지옥 탈출 — popup 조각의 offwork {name, kind, at}. 대기함 카드 [송출]을 눌러야 나간다(옛 off_work_event).
   - 화면 위 1/5 지점(y 384)에 금테 유리 상자: 윗줄(금색) '🎉 퇴근을 축하합니다! 🥳' · 큰 이름 '🎉 OO 퇴근! 🏆'.
     지옥탈출이면 '😇 지옥에서 살아 돌아왔습니다!' · '🔥 OO 지옥 탈출! 🔥'. 4초(옛 showOffWorkPopup 그대로).
   - 새 at 일 때만 · 붙은 직후 통째로 받은 것은 30초 안의 것만. 방송 중이 아니어도 뜬다(옛 것과 같다). */
const HOLD_MS = 4000;

export function mount(root, lm, opts) {
    root.innerHTML = '<div class="offwork-layer"><div class="offwork-box">'
        + '<div class="offwork-sub"></div><div class="offwork-name"></div></div></div>';
    const layer = root.firstElementChild;
    const subEl = root.querySelector('.offwork-sub');
    const nameEl = root.querySelector('.offwork-name');
    let seen, timer = null;

    lm.on('popup', pop => {
        const o = pop && pop.offwork;
        if (!o || !o.at) return;
        if (o.at === seen) return;
        seen = o.at;
        if (!opts.isFresh(o.at)) return;
        const name = o.name || '선수';
        const hell = o.kind === 'hell';               // 지옥탈출 성공도 같은 팝업 — 문구만 바꾼다
        nameEl.textContent = hell ? '🔥 ' + name + ' 지옥 탈출! 🔥' : '🎉 ' + name + ' 퇴근! 🏆';
        subEl.textContent = hell ? '😇 지옥에서 살아 돌아왔습니다!' : '🎉 퇴근을 축하합니다! 🥳';
        layer.classList.add('show');
        clearTimeout(timer);
        timer = setTimeout(() => layer.classList.remove('show'), HOLD_MS);
    });
}
