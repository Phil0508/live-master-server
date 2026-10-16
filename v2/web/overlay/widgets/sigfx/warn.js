/* 🚨 비상 경보 — 25만 원 '계엄령' 시그니처는 'OO업' 대신 이 붉은 경보가 4초 뜬다(옛 #op-fx-warn · opFxFire({kinds:['warn']})).
   붉은 사선 띠 위 · 아래로 흐르고, 'WARNING' 이 깜빡이고, 아래에 '주의 계엄령 발동'.
   ⚠️ 시그니처 재생과 따로 논다 — 경보는 제 시간(4초)에 스스로 내려간다. 다만 시그니처를 끊으면(건너뛰기 · 전체 비우기 · 대기줄 끝)
      시그니처만 사라지고 붉은 화면이 남지 않게 이 한 겹만 바로 걷는다(옛 stopReactionVisuals — 조종실 이펙트까지 지우지 않는다).
   층: layers.js(groups/sigfx.js) 58 — 전용 연출(55) · 시그니처 카드(50) 위(옛 101011 > 101005 > 100010).

   다른 위젯에 주는 것(stage.provide('sigWarn')):
     fire({message?, name?, amount?})   글자: message → '이름 · 금액' → '고액 후원 감지'(옛 순서 그대로)
     clear() */
import { formatNum } from '../../util.js';

export const WARN_MS = 4000;   // 옛 OP_FX_WARN_MS

export function mount(root, lm, opts) {
    root.innerHTML = '<div class="sfx-warn">'
        + '<div class="sfx-warn-bar top"></div>'
        + '<div class="sfx-warn-body"><div class="sfx-warn-title">⚠ WARNING ⚠</div><div class="sfx-warn-sub"></div></div>'
        + '<div class="sfx-warn-bar bottom"></div>'
        + '</div>';
    const box = root.firstElementChild;
    const sub = root.querySelector('.sfx-warn-sub');
    let timer = null;

    function clear() {
        clearTimeout(timer); timer = null;
        box.classList.remove('on');
    }
    function fire(d) {
        d = d || {};
        clear();
        const parts = [];
        const name = String(d.name || '').trim();
        const amount = parseInt(d.amount, 10) || 0;
        if (name) parts.push(name);
        if (amount > 0) parts.push(formatNum(amount) + '원');
        sub.textContent = String(d.message || '').trim() || parts.join('  ·  ') || '고액 후원 감지';
        void box.offsetWidth;
        box.classList.add('on');
        timer = setTimeout(() => { timer = null; box.classList.remove('on'); }, WARN_MS);
    }
    opts.stage.provide('sigWarn', { fire, clear });
}
