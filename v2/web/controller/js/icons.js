/* 🎨 선 아이콘 — 시안 B(두 줄 머리)의 왼쪽 줄 · 조종 줄 그림을 한 곳에 모았다.
   글자(innerHTML)로 넣지 않고 하나씩 만든다(createElementNS) — 바깥 글자가 섞일 길이 없다.
   모양: 24×24 · 선 굵기 1.9 · 끝 둥글게(controller.css 의 .ico). 칠한 곳은 fill:1 로 표시.
   icon('match') → <svg class="ico">…</svg> · 없는 이름이면 null(그 자리는 이모지 등으로 대신한다). */

const NS = 'http://www.w3.org/2000/svg';

// [모양, 속성] 목록 — 탭 id 와 같은 이름 + 조종 줄에서 쓰는 몇 개
const SHAPES = {
    home: [['path', { d: 'M4 20v-7h4.5v7M9.75 20V5h4.5v15M15.5 20v-10H20v10' }]],
    bgm: [['path', { d: 'M9 18V6l11-2v12' }], ['circle', { cx: 6.5, cy: 18, r: 2.5 }], ['circle', { cx: 17.5, cy: 16, r: 2.5 }]],
    match: [['path', { d: 'M5 4l9 9M4 9l5-5M19 4l-9 9M20 9l-5-5M7 15l-3 3 2 2 3-3M17 15l3 3-2 2-3-3' }]],
    roulette: [['circle', { cx: 12, cy: 12, r: 8.5 }], ['circle', { cx: 12, cy: 12, r: 2 }], ['path', { d: 'M12 3.5V10M12 14v6.5M3.5 12H10M14 12h6.5' }]],
    slot: [['rect', { x: 3, y: 5, width: 18, height: 14, rx: 3 }], ['path', { d: 'M9 5v14M15 5v14' }]],
    dice: [['rect', { x: 4, y: 4, width: 16, height: 16, rx: 4 }], ['circle', { cx: 9, cy: 9, r: 1.3, fill: 1 }],
        ['circle', { cx: 12, cy: 12, r: 1.3, fill: 1 }], ['circle', { cx: 15, cy: 15, r: 1.3, fill: 1 }]],
    siggame: [['rect', { x: 3, y: 7, width: 11, height: 14, rx: 2 }], ['path', { d: 'M8 7V5a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2h-5' }]],
    quiz: [['rect', { x: 3, y: 4, width: 18, height: 15, rx: 3 }], ['path', { d: 'M9.5 9.5a2.5 2.5 0 1 1 3.4 2.3c-.6.3-.9.8-.9 1.4' }], ['path', { d: 'M12 16v.1' }]],
    races: [['path', { d: 'M12 21c-3.9 0-6-2.6-6-6 0-3 2-4.8 3-7 1 1.8 2 2.4 3 2.4 0-3 1-5.4 3-7.4 0 4 3 6 3 11 0 4-2.5 7-6 7z' }]],
    pinball: [['circle', { cx: 12, cy: 12, r: 8.5 }], ['circle', { cx: 9.5, cy: 9.5, r: 2.2 }]],
    logs: [['path', { d: 'M9 6h11M9 12h11M9 18h11M4.5 6v.1M4.5 12v.1M4.5 18v.1' }]],
    'ops-console': [['path', { d: 'M21 3L3 10.5l7 3 3 7z' }], ['path', { d: 'M10 13.5L21 3' }]],
    sigdisp: [['rect', { x: 3, y: 4, width: 18, height: 12, rx: 2 }], ['path', { d: 'M8 20h8M12 16v4' }]],
    settings: [['circle', { cx: 12, cy: 12, r: 3 }],
        ['path', { d: 'M12 2.5v3M12 18.5v3M2.5 12h3M18.5 12h3M5.3 5.3l2.1 2.1M16.6 16.6l2.1 2.1M5.3 18.7l2.1-2.1M16.6 7.4l2.1-2.1' }]],
    restore: [['path', { d: 'M12 4v11M7.5 10.5L12 15l4.5-4.5M4 19.5h16' }]],
    // 조종 줄 · 띠
    ext: [['path', { d: 'M7 17L17 7M9 7h8v8' }]],
    alarm: [['path', { d: 'M12 3.5L2.5 20h19z', fill: 1 }], ['path', { d: 'M12 10v4.5M12 17.3v.1', class: 'ico-cut' }]],
    clip: [['circle', { cx: 6, cy: 7, r: 2.6 }], ['circle', { cx: 6, cy: 17, r: 2.6 }], ['path', { d: 'M8.2 8.4L20 17M8.2 15.6L20 7' }]],
    edit: [['path', { d: 'M4 20h4L19 9l-4-4L4 16z' }]],
    more: [['circle', { cx: 5, cy: 12, r: 2, fill: 1 }], ['circle', { cx: 12, cy: 12, r: 2, fill: 1 }], ['circle', { cx: 19, cy: 12, r: 2, fill: 1 }]],
    play: [['path', { d: 'M8 5.5v13l11-6.5z', fill: 1 }]],
    next: [['path', { d: 'M5 5.5v13l10-6.5z', fill: 1 }], ['path', { d: 'M18 5.5v13' }]],
    stop: [['rect', { x: 6, y: 6, width: 12, height: 12, rx: 2.5, fill: 1 }]],
    logout: [['path', { d: 'M14 4h5v16h-5M10 8l-4 4 4 4M6 12h10' }]],
    back: [['path', { d: 'M15 5l-7 7 7 7' }]],
    search: [['circle', { cx: 10.5, cy: 10.5, r: 6.5 }], ['path', { d: 'M15.5 15.5L20.5 20.5' }]],     // 🔍 찾기(Ctrl+K — cmdk.js)
};

/** 아이콘 하나 — 없는 이름이면 null */
export function icon(name, cls) {
    const shape = SHAPES[name];
    if (!shape) return null;
    const svg = document.createElementNS(NS, 'svg');
    svg.setAttribute('viewBox', '0 0 24 24');
    svg.setAttribute('class', 'ico' + (cls ? ' ' + cls : ''));
    svg.setAttribute('aria-hidden', 'true');
    svg.setAttribute('focusable', 'false');
    for (const [tag, attrs] of shape) {
        const el = document.createElementNS(NS, tag);
        for (const [k, v] of Object.entries(attrs)) if (k !== 'fill' && k !== 'class') el.setAttribute(k, String(v));
        const c = ((attrs.class || '') + (attrs.fill ? ' ico-fill' : '')).trim();
        if (c) el.setAttribute('class', c);
        svg.append(el);
    }
    return svg;
}

export function hasIcon(name) { return !!SHAPES[name]; }
