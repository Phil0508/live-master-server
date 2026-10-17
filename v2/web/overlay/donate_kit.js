/* 🎁 후원 받기 갈래(10-17 이사) 방송판 도구 — 후원 카드 · 소액 띠 · 시그니처 카드가 같이 쓴다.
   ⚠️ 불러오기만 해서는 화면(document)을 안 건드린다 — 그래서 node 로 순수 함수를 검사한다(v2/tests/test_donate_mig.py).

   1) 🏷️ 투네이션 공식 칭호 보석 알약 · Lv(옛 overlay.html DONOR_TIERS · donorTag · donorLv — 10-08 44584ff 시안 A)
      서버가 donor_title {name, color} · donor_level 을 싣는다(리스너 후원만 · 크리에이터 칭호는 서버에서 걸러져 안 온다).
      단계(0~6)가 오를수록 앞 단계 효과를 모두 갖고 하나씩 더한다(css/donate.css .dtag 머리말).
      표에 없는 공식 칭호는 이름에 든 말(노블레스 · 다이아)로 단계를 고르고, 그것도 없으면 서버 색 단색 알약.
      ⚠️ 글자는 textContent 로만. 색은 #RRGGBB 일 때만. 칭호 그림은 투네이션 자산이라 안 쓴다(색 · 효과로만).
   2) 💬 묶음(×N) 메시지(옛 rxMsgFor — 10-11 5d179b0): 같은 사람이 같은 시그를 메시지만 바꿔 연달아 보내면 서버가 msgs 에 모은다.
      [N번 다 틀기]면 이번 차례 메시지, 한 번만 틀고 ×N 이면 놓치지 않게 다 보여 준다(4줄 + '… 외 N개').
      이어 틀기 줄(again_of)은 앞에서 튼 만큼(seq_base)을 건너뛴다.
   3) 🔁 '몇 번째 / 모두' — 서버는 '다 틀기' 때 count 를 하나씩 줄이고 replay 를 올린다 → 모두 = seq_base + count + replay */

export const DONOR_TIERS = {   // 칭호 이름(띄어쓰기 뺌) → [밝은 색, 짙은 색, 단계 0~6, 블랙 보석 결]
    '금수저': ['#FFD76A', '#C8961E', 0],
    '다이아': ['#E9FBFF', '#8FDDF5', 1],
    '블루다이아': ['#7CC0FF', '#1F5FE0', 1],
    '그린다이아': ['#6EEAB6', '#0E9F6E', 2],
    '레드다이아': ['#FF8A8A', '#C81E3A', 2],
    '골드다이아': ['#FFE08A', '#D99A00', 3],
    '블랙다이아': ['#7B7F96', '#0B0B10', 3, true],
    '노블레스': ['#E3D2FF', '#8F63E8', 4],
    '블루노블레스': ['#8FC8FF', '#2A4FD6', 4],
    '그린노블레스': ['#8BF0C4', '#0B8F64', 5],
    '레드노블레스': ['#FF9C9C', '#B3122F', 5],
    '골드노블레스': ['#FFE7A1', '#C98A00', 5],
    '블랙노블레스': ['#8D90A8', '#07070B', 6, true],
};
// 단계별 효과 — 앞 단계 것을 모두 갖고 하나씩 더한다(spk 반짝이 · orb 도는 별 · ray 빛 줄기는 덧붙이는 조각)
export const DONOR_TIER_FEATS = [[], ['g'], ['g', 'sh'], ['g', 'sh', 'gl', 'spk'], ['g', 'sh', 'gl', 'spk', 'cr', 'bd'],
    ['g', 'sh', 'gl', 'spk', 'cr', 'bd', 'orb'], ['g', 'sh', 'gl', 'spk', 'cr', 'bd', 'orb', 'rb', 'ray']];

export function donorColor(t) { return (t && /^#[0-9A-Fa-f]{6}$/.test(String(t.color || ''))) ? t.color : '#E2B64B'; }
export function donorLum(hex) {
    const n = parseInt(String(hex).slice(1), 16);
    return (0.299 * ((n >> 16) & 255) + 0.587 * ((n >> 8) & 255) + 0.114 * (n & 255)) / 255;
}
export function donorTier(t) {
    const key = String(t.name).replace(/\s+/g, '');
    const row = DONOR_TIERS[key]
        || (key.indexOf('노블레스') >= 0 ? DONOR_TIERS['노블레스'] : key.indexOf('다이아') >= 0 ? DONOR_TIERS['다이아'] : null);
    if (row) return { c1: row[0], c2: row[1], lv: row[2], prism: !!row[3] };
    const c = donorColor(t);
    return { c1: c, c2: c, lv: 0, prism: false };
}

/* 알약의 생김새(화면 없이) — 클래스 · 색 · 글자 색 · 덧붙일 조각. 없으면 null */
export function donorTagSpec(t) {
    if (!t || !t.name) return null;
    const tr = donorTier(t);
    const f = DONOR_TIER_FEATS[tr.lv] || [];
    const has = k => f.indexOf(k) >= 0;
    return {
        cls: 'dtag' + f.map(k => ' dt-' + k).join('') + (tr.prism ? ' dt-prism' : ''),
        c1: tr.c1, c2: tr.c2, lv: tr.lv,
        ink: (donorLum(tr.c1) + donorLum(has('g') ? tr.c2 : tr.c1)) / 2 > 0.55 ? '#1b1404' : '#ffffff',
        text: String(t.name),
        crown: has('cr'), ray: has('ray'), orb: has('orb'),
        sparks: has('spk') ? (tr.lv >= 5 ? 4 : 3) : 0,
    };
}

function part(doc, cls, tag) { const e = doc.createElement(tag || 'span'); e.className = cls; return e; }
function crown(doc) {
    const NS = 'http://www.w3.org/2000/svg';
    const s = doc.createElementNS(NS, 'svg');
    s.setAttribute('viewBox', '0 0 24 24'); s.setAttribute('class', 'dt-crown'); s.setAttribute('aria-hidden', 'true');
    const p = doc.createElementNS(NS, 'path');
    p.setAttribute('d', 'M3 8l4.5 4L12 5l4.5 7L21 8l-1.8 10.5H4.8L3 8z');
    p.setAttribute('fill', '#FFD24A'); p.setAttribute('stroke', '#5a3d00'); p.setAttribute('stroke-width', '1.4'); p.setAttribute('stroke-linejoin', 'round');
    s.appendChild(p);
    return s;
}

/* 🏷️ 칭호 알약(이름 앞) — 없으면 null */
export function donorTag(t, doc) {
    const sp = donorTagSpec(t);
    if (!sp) return null;
    doc = doc || document;
    const s = part(doc, sp.cls);
    s.style.setProperty('--c1', sp.c1);
    s.style.setProperty('--c2', sp.c2);
    s.style.setProperty('--ink', sp.ink);
    if (sp.ray) s.appendChild(part(doc, 'dt-ray'));
    s.appendChild(part(doc, 'dt-fill'));
    const lbl = part(doc, 'dt-lbl');
    if (sp.crown) lbl.appendChild(crown(doc));
    const tx = part(doc, 'dt-txt');
    tx.textContent = sp.text;
    lbl.appendChild(tx);
    s.appendChild(lbl);
    for (let i = 0; i < sp.sparks; i++) s.appendChild(part(doc, 'dt-st', 'i'));
    if (sp.orb) {
        const o = part(doc, 'dt-orb');
        for (let i = 0; i < 3; i++) o.appendChild(doc.createElement('i'));
        s.appendChild(o);
    }
    return s;
}

export function donorLvText(lv) {
    const n = Math.floor(Number(lv) || 0);
    return n > 0 ? 'Lv.' + n : '';
}
/* 🏷️ 이름 옆 Lv — 없으면 null */
export function donorLv(lv, doc) {
    const t = donorLvText(lv);
    if (!t) return null;
    const s = (doc || document).createElement('span');
    s.className = 'donor-lv';
    s.textContent = t;
    return s;
}

/* 이름 칸 하나에 칭호(앞) · 이름 · Lv(뒤) — 이름은 글자로만 */
export function paintDonorName(el, name, title, level) {
    el.textContent = name;
    const tg = donorTag(title, el.ownerDocument);
    if (tg) el.prepend(tg);
    const lv = donorLv(level, el.ownerDocument);
    if (lv) el.appendChild(lv);
}

// ── 💬 묶음 메시지 ──
export const RX_MSG_LINES = 4;
const MANUAL_MSG = '수동 후원 송출';
export function sigMsgFor(it) {
    const msgs = Array.isArray(it && it.msgs) ? it.msgs : null;
    if (!msgs || msgs.length < 2) {
        const m = String((it && it.message) || '');
        return m === MANUAL_MSG ? '' : m;
    }
    if (it.play_all) {
        const i = (Number(it.seq_base) || 0) + (Number(it.replay) || 0);     // 이번 차례(0부터)
        const m = i >= 0 && i < msgs.length ? String(msgs[i] || '') : '';    // 상한(서버 30개) 넘은 차례는 비운다
        return m === MANUAL_MSG ? '' : m;
    }
    // 🙈 [N번 다 틀기]를 고르기 전에는 첫 메시지만(대표님 10-17 — 묶인 걸 묻기 전에 나머지 메시지가 드러나지 않게)
    const first = String(msgs[0] || it.message || '');
    return first === MANUAL_MSG ? '' : first;
}

// ── 🔁 몇 번째 / 모두 ──
export function comboOf(it) {
    const cnt = Number(it && it.count) || 1;
    const rep = Number(it && it.replay) || 0;
    const base = Number(it && it.seq_base) || 0;
    return { total: base + cnt + rep, nth: base + rep + 1, count: cnt, all: !!(it && it.play_all) };
}
