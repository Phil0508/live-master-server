/* 🎨 랭킹 첫 화면(묶음 B) 선 아이콘 — 숫자 카드 · 무대 줄 · 점수판에서만 쓰는 몇 개.
   icons.js(틀 · 묶음 A)와 같은 모양 규칙(24×24 · .ico)이고, 거기 있는 이름(play · next · edit · back …)은 그쪽 것을 그대로 쓴다.
   따로 둔 까닭: 같은 SHAPES 표를 여러 갈래가 동시에 고치면 합칠 때 부딪힌다. */
import { icon as frameIcon } from './icons.js';

const NS = 'http://www.w3.org/2000/svg';

const SHAPES = {
    won: [['path', { d: 'M4 6l3.5 12L12 8l4.5 10L20 6M3 11h18' }]],
    crown: [['path', { d: 'M3 8l4.5 4 4.5-6 4.5 6L21 8l-2 11H5z', fill: 1 }]],
    bell: [['path', { d: 'M6 16v-5a6 6 0 0 1 12 0v5l2 2H4z' }], ['path', { d: 'M10 20.5h4' }]],
    flag: [['path', { d: 'M5 21V4M5 4h12l-2.5 4L17 12H5' }]],
    stage: [['rect', { x: 3, y: 4, width: 18, height: 12, rx: 2 }], ['path', { d: 'M8 20h8M12 16v4' }]],
    layers: [['path', { d: 'M12 4l9 5-9 5-9-5z' }], ['path', { d: 'M3 14l9 5 9-5' }]],
    prev: [['path', { d: 'M16 5.5v13L5 12z', fill: 1 }]],
    pause: [['rect', { x: 6, y: 5, width: 4, height: 14, rx: 1.2, fill: 1 }], ['rect', { x: 14, y: 5, width: 4, height: 14, rx: 1.2, fill: 1 }]],
    plus: [['path', { d: 'M12 5v14M5 12h14' }]],
    trash: [['path', { d: 'M4 7h16M9 7V4.5h6V7M6.5 7l1 13h9l1-13' }]],
    lock: [['rect', { x: 5, y: 11, width: 14, height: 9, rx: 2 }], ['path', { d: 'M8 11V8a4 4 0 0 1 8 0v3' }]],
    wallet: [['rect', { x: 3, y: 6, width: 18, height: 13, rx: 3 }], ['path', { d: 'M3 10h18M16 14.5h2' }]],
    jar: [['path', { d: 'M7 4h10M8.5 4v3C6.5 8 5 10 5 12.5V18a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2v-5.5C19 10 17.5 8 15.5 7V4' }]],
    users: [['circle', { cx: 9, cy: 8, r: 3.2 }], ['path', { d: 'M3 19c.6-3.3 3-5 6-5s5.4 1.7 6 5M16 5.2a3 3 0 0 1 0 5.6M18 14c1.7.6 2.8 2.2 3 5' }]],
    sliders: [['path', { d: 'M4 6h9M17 6h3M4 12h3M11 12h9M4 18h12M20 18h0' }], ['circle', { cx: 15, cy: 6, r: 2 }],
        ['circle', { cx: 9, cy: 12, r: 2 }], ['circle', { cx: 18, cy: 18, r: 2 }]],
    scale: [['path', { d: 'M12 4v16M7 20h10M5 8h14M5 8l-2.5 6a3 3 0 0 0 5 0zM19 8l-2.5 6a3 3 0 0 0 5 0z' }]],
};

/** 아이콘 하나 — 여기 없는 이름이면 틀(icons.js) 것을, 그래도 없으면 null */
export function hicon(name, cls) {
    const shape = SHAPES[name];
    if (!shape) return frameIcon(name, cls);
    const svg = document.createElementNS(NS, 'svg');
    svg.setAttribute('viewBox', '0 0 24 24');
    svg.setAttribute('class', 'ico' + (cls ? ' ' + cls : ''));
    svg.setAttribute('aria-hidden', 'true');
    svg.setAttribute('focusable', 'false');
    for (const [tag, attrs] of shape) {
        const el = document.createElementNS(NS, tag);
        for (const [k, v] of Object.entries(attrs)) if (k !== 'fill') el.setAttribute(k, String(v));
        if (attrs.fill) el.setAttribute('class', 'ico-fill');
        svg.append(el);
    }
    return svg;
}
