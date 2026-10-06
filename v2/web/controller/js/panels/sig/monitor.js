/* 👀 방송 화면 보기 — 지금 방송판(OBS)에 나가는 화면을 조종실 안에서 본다(옛 폰 조종실 mobile.html 의 '방송 화면').

   /overlay/?monitor=1 을 작은 틀(iframe)에 띄운다. 방송판은 창 크기에 맞춰 스스로 줄어든다(1080×1920 비율).
   ⚠️ monitor=1 이 꼭 붙어야 한다 — 없으면 ① 이 화면에서 시그니처 소리가 나고 ② 시그니처를 '다 틀었다' 고 보고해
      방송에 나갈 시그니처를 이 화면이 먹는다(옛 mobile.html 에 적힌 사고). monitor=1 은 소리 끔 · 보고 안 함.
   ⚠️ 탭이 가려지면(다른 탭 · 창을 내림) 틀을 걷는다 — 안 보이는 채로 계속 받으면 폰 배터리 · 데이터를 먹는다. */
import { h } from './common.js';

const SRC = '/overlay/?monitor=1';

export function mountMonitor(el, ctx) {
    let frame = null;
    const box = h('div', { class: 'mon-box' });
    const reload = h('button', { type: 'button', class: 'btn sm' }, '↻ 새로 고침');
    const big = h('a', { class: 'btn sm', href: SRC, target: '_blank', rel: 'noopener' }, '↗ 크게 보기');
    el.classList.add('sg');
    el.append(h('section', { class: 'sg-blk' },
        h('div', { class: 'sg-bh' }, h('h3', null, '👀 방송 화면 보기'), h('span', { class: 'sg-sub' }, '미리보기 — 방송에 영향 없음')),
        h('div', { class: 'sg-bar' }, reload, big),
        box,
        h('p', { class: 'sg-hint' }, '지금 방송에 나가는 화면 그대로예요. 소리는 나지 않고, 시그니처 대기줄도 건드리지 않아요. ',
            '안 보이면 [↻ 새로 고침] — 그래도 안 보이면 OBS 쪽 방송판을 확인해 주세요(머리줄의 [화면] 점).')));

    // 방송을 끝내 '방송 전' 화면으로 가면 탭 칸 전체가 안 보인다(탭 자체는 열린 채) — 그때도 걷는다
    const offScreen = () => el.hidden || document.hidden || (document.body.dataset.view && document.body.dataset.view !== 'live');
    function show() {
        if (frame || offScreen()) return;
        frame = h('iframe', { src: SRC + '&t=' + Date.now(), title: '방송 화면 미리보기', class: 'mon-frame', allow: 'autoplay' });
        box.append(frame);
    }
    function hide() {
        if (!frame) return;
        frame.remove();
        frame = null;
    }
    reload.addEventListener('click', () => { hide(); show(); });
    new MutationObserver(() => (el.hidden ? hide() : show())).observe(el, { attributes: true, attributeFilter: ['hidden'] });
    document.addEventListener('visibilitychange', () => (offScreen() ? hide() : show()));
    new MutationObserver(() => (offScreen() ? hide() : show())).observe(document.body, { attributes: true, attributeFilter: ['data-view'] });
    show();
    return { render() { show(); } };
}
