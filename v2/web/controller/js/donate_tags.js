/* 🏷️ 대기함 카드의 투네이션 칭호 이름표 · Lv(옛 controller.html pdTitleHtml · .pd-title · .pd-lv — 10-08 176db46).
   서버가 리스너 후원에만 donor_title {name, color} · donor_level 을 대기함 카드에 싣는다(공식 칭호만 · 색은 #RRGGBB 만).
   ⚠️ 칭호 이름은 바깥 글자 — h()(textContent)로만 넣는다. 생김새는 css/donate.css. */
import { h } from './util.js';

export function titleColor(t) {
    return /^#[0-9A-Fa-f]{6}$/.test(String((t && t.color) || '')) ? t.color : '#E2B64B';
}

/* 밝은 칭호 색이면 검은 글자, 어두우면 흰 글자(옛 것과 같은 문턱 0.6) */
export function titleInk(color) {
    const n = parseInt(String(color).slice(1), 16);
    return (0.299 * ((n >> 16) & 255) + 0.587 * ((n >> 8) & 255) + 0.114 * (n & 255)) / 255 > 0.6 ? '#1b1404' : '#ffffff';
}

export function titleChip(t) {
    if (!t || !t.name) return null;
    const c = titleColor(t);
    return h('span', { class: 'pc-dtitle', style: `background:${c};color:${titleInk(c)}`, title: '투네이션 칭호' }, String(t.name));
}

export function lvChip(lv) {
    const n = Math.floor(Number(lv) || 0);
    return n > 0 ? h('span', { class: 'pc-lv', title: '투네이션 후원자 레벨' }, 'Lv.' + n) : null;
}
