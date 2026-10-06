/* 🏺 모금함 — 금색 깃발(옛 2026-10-03 시안 B). fundjar 조각(name · enabled · seed · score(원)).
   - 회사 종잣돈(seed) + 시청자 후원(score) 을 **만원 단위**로 크게(1,234,000원 → 123만원). 폭 108 이라 원 단위는 안 들어간다.
     반올림은 점수와 같은 규칙 — 5,000원대는 내리고 6,000원부터 올린다(옛 jarMan).
     1,000만원(4자리)부터는 글씨를 줄인다(.jar-4).
   - 금액이 **오를 때만** 깃발이 한 번 튀고 반짝 + 쨍그랑(처음 그림에서는 안 튄다).
   - 보이기: 옛 shHud('fundjar') — 옛 서버는 show.hud.fundjar 와 fundjar.enabled 를 늘 같게 맞췄다.
     v2 서버는 둘을 따로 갖고 있어서(조종실이 어느 쪽을 누를지 모른다) **둘 중 하나라도 켜져 있으면** 보인다.
     ?hud=fundjar / ?hud=-fundjar 로 이 창에서만 켜고 끌 수 있다(main.js 의 다른 칸과 같은 약속).
   - 방송 중에만(liveOnly — 옛 renderFundJar 는 '방송 꺼짐 return' 뒤에 있었다). 시그니처가 돌아도 남는다(옛 #ui-layer 밖). */
import { formatNum, restartClass } from '../../util.js';
import { sfxInit, playSfx } from './sfx.js';

function hudForce() {
    let f = null;
    (new URLSearchParams(location.search).get('hud') || '').split(',').map(s => s.trim()).forEach(k => {
        if (k === 'fundjar' || k === '+fundjar') f = true;
        else if (k === '-fundjar') f = false;
    });
    return f;
}

export const jarMan = won => Math.floor((Math.max(0, Number(won) || 0) + 4000) / 10000);

export function mount(root, lm, opts) {
    const FORCE = hudForce();
    sfxInit(opts);
    root.innerHTML = '<div class="jar-flag"><div class="jar-rod"></div><div class="jar-cloth">'
        + '<div class="jar-label">기여도<br>상금</div><div class="jar-line"></div>'
        + '<div class="jar-amt">0</div><div class="jar-unit">만원</div></div></div>';
    const flag = root.firstElementChild;
    const amtEl = root.querySelector('.jar-amt');
    let prev = null;

    function render() {
        const j = lm.get('fundjar') || {};
        const sh = lm.get('show') || {};
        const on = FORCE !== null ? FORCE : !!((sh.hud && sh.hud.fundjar) || j.enabled);
        flag.classList.toggle('on', on);
        if (!on) { prev = null; return; }
        const total = (Number(j.seed) || 0) + (Number(j.score) || 0);
        const man = jarMan(total);
        amtEl.textContent = formatNum(man);
        amtEl.classList.toggle('jar-4', man >= 1000);
        if (prev !== null && total > prev) {                 // 💰 올랐을 때만 한 번 튀고 쨍그랑 — 많이 들어오면 소리도 크게
            restartClass(flag, 'jar-pop');
            playSfx('jar-coin', Math.min(1.4, 0.8 + (total - prev) / 100000));
        }
        prev = total;
    }
    ['fundjar', 'show'].forEach(k => lm.on(k, render));
    // 새 방송이면 지난 방송 금액에서 '올랐다' 로 튀지 않게
    let sid = null;
    lm.on('session', s => {
        const id = (s && s.id) || '';
        if (sid !== null && id !== sid) prev = null;
        sid = id;
    });
}
