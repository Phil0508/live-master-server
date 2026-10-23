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

/* 💙🏦✋ 어디서 온 후원인가(10-24 대표님 '계좌랑 투네 구분') — 대기함 카드 · 시그니처 대기열 · 장부.
   via: 'toon'(투네이션) · 'bank'(후원 콘솔에서 계좌 입금 카드로 보낸 것) · 'hand'(그 밖의 손 송출). 생김새는 css/donate.css(.src-chip) */
const SRC = {
    toon: ['💙 투네', '투네이션으로 들어온 후원'],
    bank: ['🏦 계좌', '계좌 입금 — 후원 콘솔에서 계좌 카드로 보낸 것'],
    hand: ['✋ 손', '후원 콘솔에서 손으로 넣은 것'],
};
export function srcChip(via) {
    const s = SRC[via];
    return s ? h('span', { class: 'src-chip src-' + via, title: s[1] }, s[0]) : null;
}
/** 장부 줄 → via(장부엔 via 칸이 없다 — tx_id · source 로 가린다). 모르면 '' */
export function viaOfRow(r) {
    const tx = String((r && r.tx_id) || '');
    const src = String((r && r.source) || '');
    if (tx.startsWith('manual_bank_')) return 'bank';
    if (tx.startsWith('toon_') || src === 'toonation') return 'toon';
    if (src === 'manual') return 'hand';
    return '';
}

export function lvChip(lv) {
    const n = Math.floor(Number(lv) || 0);
    return n > 0 ? h('span', { class: 'pc-lv', title: '투네이션 후원자 레벨' }, 'Lv.' + n) : null;
}
