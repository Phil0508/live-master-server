/* 🔎 Ctrl+K 찾기 — 글자 맞추기만(순수 · 화면을 안 만진다 → node 로 그대로 검사한다: v2/tests/js/cmdk_check.mjs).

   맞추는 규칙(대표님 10-24 "컨트롤 케이로 모든걸 검색")
     - 띄어쓰기 · 대소문자 · 문장부호 · 이모지는 안 본다('방송테두리' = '🖼 방송 테두리', 'bgm' = 'BGM').
     - 앞부분만 적어도 · 가운데만 적어도 찾는다. 점수는 똑같음 100 > 앞이 같음 82 > 가운데 들어 있음 58.
     - 초성: 'ㅁㅁ' → 밍밍 · 'ㅂㅅㅌㄷㄹ' → 방송 테두리. 초성과 글자를 섞어도 된다('밍ㅁ').
     - 치는 중인 마지막 글자: '미' → 밍밍(받침을 아직 안 쳤다) · '밍' → 미안(받침이 다음 글자 첫소리가 될 수 있다).
     - 여러 낱말: '모금함 깃발' — 낱말마다 이름 · 다른 말 · 설명 어딘가에 있으면 찾는다(낮은 점수).
     - 금액: '5만' · '50000' · '5만원' · '50,000원' → 50000.
   ⚠️ 매 글자마다 수천 줄(후원자 장부)을 돌린다 — 바꾼 글자(norm · 초성)는 줄마다 한 번만 만들어 기억한다(WeakMap). */

const SB = 0xac00, SE = 0xd7a3;
const CHO = 'ㄱㄲㄴㄷㄸㄹㅁㅂㅃㅅㅆㅇㅈㅉㅊㅋㅌㅍㅎ';
// 받침(종성) 번호 → 다음 글자 첫소리로 쓸 수 있는 자음(겹받침은 '') — '밍' 을 치는 중이면 '미' + 'ㅇ…' 일 수 있다
const JONG_AS_CHO = ['', 'ㄱ', 'ㄲ', '', 'ㄴ', '', '', 'ㄷ', 'ㄹ', '', '', '', '', '', '', '', 'ㅁ', 'ㅂ', '', 'ㅅ', 'ㅆ', 'ㅇ', 'ㅈ', 'ㅊ', 'ㅋ', 'ㅌ', 'ㅍ', 'ㅎ'];

const isSyl = c => c >= SB && c <= SE;
const isJamoCons = ch => CHO.indexOf(ch) !== -1 || 'ㄳㄵㄶㄺㄻㄼㄽㄾㄿㅀㅄ'.indexOf(ch) !== -1;
function parts(ch) {
    const c = ch.charCodeAt(0) - SB;
    return { cho: Math.floor(c / 588), jung: Math.floor((c % 588) / 28), jong: c % 28 };
}
/** 글자 하나의 초성(한글이 아니면 그대로) */
export function choOf(ch) {
    const c = ch.charCodeAt(0);
    return isSyl(c) ? CHO[Math.floor((c - SB) / 588)] : ch;
}
/** 글 전체의 초성 — '밍밍 5' → 'ㅁㅁ 5' */
export function cho(s) {
    let out = '';
    for (const ch of String(s || '')) out += choOf(ch);
    return out;
}

/** 견줄 글자 — 소문자 · 띄어쓰기/문장부호/이모지 빼기. 더하기 · 빼기 표시(+1분 · -1분)와 → 는 남긴다 */
export function norm(s) {
    return String(s == null ? '' : s).normalize('NFC').toLowerCase()
        .replace(/[−–—]/g, '-')
        .replace(/[^0-9a-z가-힣ㄱ-ㅎㅏ-ㅣ+\-]/g, '');
}

// 글자 하나 맞추기 — 같음 · 초성 · (마지막 글자만) 치는 중
function chEq(n, hch, next, last) {
    if (n === hch) return true;
    if (isJamoCons(n)) return isSyl(hch.charCodeAt(0)) && choOf(hch) === n;
    if (!last || !isSyl(n.charCodeAt(0)) || !isSyl(hch.charCodeAt(0))) return false;
    const a = parts(n), b = parts(hch);
    if (a.cho !== b.cho || a.jung !== b.jung) return false;
    if (a.jong === 0) return true;                                        // '미' → '밍'
    // '밍' → '미안': 받침 ㅇ 이 다음 글자 첫소리
    return b.jong === 0 && !!next && JONG_AS_CHO[a.jong] !== '' && choOf(next) === JONG_AS_CHO[a.jong];
}
/** 느슨하게 찾기 — 찾은 자리(없으면 -1) */
export function looseIndex(hay, needle) {
    const H = [...hay], N = [...needle];
    if (!N.length || N.length > H.length) return -1;
    outer: for (let i = 0; i + N.length <= H.length; i++) {
        for (let j = 0; j < N.length; j++) {
            if (!chEq(N[j], H[i + j], H[i + j + 1], j === N.length - 1)) continue outer;
        }
        return i;
    }
    return -1;
}

/** 맞춤 점수(0 = 안 맞음) — hay · needle 은 norm 된 글자 */
export function hit(hay, needle) {
    if (!needle || !hay) return 0;
    if (hay === needle) return 100;
    const i = hay.indexOf(needle);
    if (i === 0) return 82;
    if (i > 0) return 58;
    const k = looseIndex(hay, needle);
    if (k < 0) return 0;
    // 전부 초성이고 길이가 같다('ㅁㅁ' ↔ 밍밍) → 거의 똑같음
    if ([...needle].length === [...hay].length) return 78;
    return k === 0 ? 70 : 46;
}

/** 금액 읽기 — '5만' · '5만원' · '50,000' · '₩50000' · '1.5만' → 원. 숫자 꼴이 아니면 0 */
export function wonOf(q) {
    const t = String(q || '').replace(/[\s,₩원]/g, '');
    let m = t.match(/^(\d+(?:\.\d+)?)만(?:(\d+)천)?$/);
    if (m) return Math.round(parseFloat(m[1]) * 10000 + (m[2] ? parseInt(m[2], 10) * 1000 : 0));
    m = t.match(/^(\d+)천$/);
    if (m) return parseInt(m[1], 10) * 1000;
    m = t.match(/^\d{3,9}$/);
    return m ? parseInt(t, 10) : 0;
}

/* ── 줄 하나의 바꾼 글자 기억 ── e = { title, kw?, sub? } → { t, k[], s, all } */
const memo = new WeakMap();
export function prep(e) {
    let p = memo.get(e);
    if (p) return p;
    const t = norm(e.title);
    const k = String(e.kw || '').split(/\s+/).map(norm).filter(Boolean);
    const s = norm(e.sub);
    p = { t, k, s, all: [t, ...k, s].join('|') };
    memo.set(e, p);
    return p;
}

/** 줄 하나의 점수 — 이름이 제일 세고, 다른 말(kw)은 0.8 배 · 설명(sub)에만 있으면 30. q: 사람이 적은 그대로 */
export function scoreEntry(e, q, fq) {
    fq = fq == null ? norm(q) : fq;
    if (!fq) return 0;
    const p = prep(e);
    let best = hit(p.t, fq);
    if (best >= 100) return best;
    for (const k of p.k) {
        const v = Math.round(hit(k, fq) * 0.8);          // 다른 말이 똑같아도(80) 이름 앞이 같은 것(82)보다는 아래
        if (v > best) best = v;
    }
    if (best < 30 && fq.length >= 2 && p.s && p.s.indexOf(fq) !== -1) best = 30;
    if (!best) {
        // 여러 낱말 — 낱말마다 어딘가에 있으면
        const toks = String(q || '').split(/\s+/).map(norm).filter(Boolean);
        if (toks.length > 1 && toks.every(w => p.all.indexOf(w) !== -1 || looseIndex(p.all, w) !== -1)) best = 40;
    }
    return best;
}
