/* 📇 후원자 장부(donor book) — 딱지 글자 · 목록 거르기 · 막대 같은 계산만(10-17 후원자 장부 5단계).
   ⚠️ 화면(document)을 만지지 않는다 — node 로 그대로 불러 검사한다(v2/tests/test_donorbook_ui.py · js/donorbook_check.mjs).
   서버(domain/donor_book.py)가 주는 것
     비공개 조각 donor_tags  { norm_name: {pid, tag, player, n, share, club} }
     비공개 조각 donor_clubs { word: {player, confirmed} }
     GET /api/donors/book · /api/donors/person/{pid} · /api/donors/suggest
   딱지(tag): pin 📌 고정 · new 🌱 새 얼굴 · main 💛 전담팬(90% · 5번 이상) · lean 🧡 주력팬(60% 이상) · multi 🌈 여러 멤버 */

export const TAGS = {
    main: { emo: '💛', label: '전담팬', desc: '한 멤버에게 90% 이상 · 5번 이상' },
    lean: { emo: '🧡', label: '주력팬', desc: '한 멤버에게 60% 이상' },
    multi: { emo: '🌈', label: '여러 멤버', desc: '여러 멤버에게 고루' },
    new: { emo: '🌱', label: '새 얼굴', desc: '아직 3번이 안 됨' },
    pin: { emo: '📌', label: '고정', desc: '대표님이 못박은 선수' },
};
export const CLUB_EMO = '🏷️';

/* 목록 거르기 단추 — [키, 글자]. 'club' · 'sugg' · 'dormant' · 'test' 는 딱지가 아니라 다른 칸으로 고른다 */
export const FILTERS = [
    ['all', '전체'], ['main', '💛 전담'], ['lean', '🧡 주력'], ['multi', '🌈 여러 멤버'], ['new', '🌱 새 얼굴'],
    ['pin', '📌 고정'], ['club', '🏷️ 팬클럽'], ['sugg', '🔗 묶을까?'], ['dormant', '💤 쉬는 중'], ['suspect', '❓ 시험 의심'], ['test', '🧪 시험 이름'],
];

/* 조각 · 응답의 칸은 바깥에서 온 이름이 열쇠다 — '__proto__' · 'constructor' 같은 이름이 기본 속성을 집지 않게 자기 칸만 본다 */
const own = (o, k) => Object.prototype.hasOwnProperty.call(o, k);

const WHY = { key: '투네이션 번호표가 같아요', name: '닉네임이 비슷해요', bank: '계좌 입금 짝이에요' };
export const whyText = w => WHY[w] || String(w || '');

/** 서버 rules.norm_donor 와 같다 — 앞뒤 · 겹친 빈칸 정리, 끝의 '님' 떼기. 빈 것은 '익명' */
export function normDonor(name) {
    let n = String(name == null ? '' : name).split(/\s+/).filter(Boolean).join(' ');
    if (n.endsWith('님')) n = n.slice(0, -1).trim();
    return n || '익명';
}

/* 서버 rules.ANONYMOUS_NAMES 와 같다 — 이런 이름엔 딱지를 안 붙인다 */
const ANON = new Set(['', '-', '익명', '익명의 후원자', '익명후원자', '무명', '후원자', 'anonymous', 'anon', 'unknown']);
export const isAnon = name => ANON.has(String(name == null ? '' : name).trim().toLowerCase());

/** 대기함 카드 · 장부 줄 이름 → 조각의 한 칸(없으면 null). 이름이 없거나 익명이면 null */
export function tagFor(tags, name) {
    if (!tags || typeof tags !== 'object' || isAnon(name)) return null;
    const k = normDonor(name);
    const e = own(tags, k) ? tags[k] : null;
    return e && typeof e === 'object' ? e : null;
}

const cnt = n => Math.max(0, Math.floor(Number(n) || 0));
export const pct = share => Math.round(Math.max(0, Math.min(1, Number(share) || 0)) * 100);

/** 딱지 글자 — {cls, text, title} 또는 null(그릴 것 없음)
 *  main '💛밍밍 전담 · 23회' · lean '🧡밍밍 주력 · 8회' · multi '🌈 여러 멤버 · 12회' · new '🌱 새 얼굴' · pin '📌밍밍 고정' */
export function chipText(e) {
    if (!e || !e.tag || !own(TAGS, e.tag)) return null;
    const t = TAGS[e.tag];
    const n = cnt(e.n), p = String(e.player || '').trim();
    const share = pct(e.share);
    let text;
    if (e.tag === 'main' || e.tag === 'lean') {
        if (!p) return null;                       // 누구 팬인지 모르면 그리지 않는다
        text = `${t.emo}${p} ${e.tag === 'main' ? '전담' : '주력'} · ${n}회`;
    } else if (e.tag === 'pin') {
        if (!p) return null;
        text = `${t.emo}${p} 고정`;
    } else if (e.tag === 'multi') {
        text = `${t.emo} ${t.label}` + (n ? ` · ${n}회` : '');
    } else {
        text = `${t.emo} ${t.label}`;
    }
    const lines = [`${t.label} — ${t.desc}`];
    if (n) lines.push(p && e.tag !== 'new' ? `기억 ${n}번 중 ${p} ${share}%` : `기억 ${n}번`);
    return { cls: 'dk-tag t-' + e.tag, text, title: lines.join('\n') };
}

/** 팬클럽 딱지 — 확정된 팬클럽 말이 닉네임에 있을 때. 딱지와 같은 선수를 이미 말하고 있으면(전담 · 주력 · 고정) 안 붙인다 */
export function clubText(e) {
    if (!e || !e.club) return null;
    const c = String(e.club).trim();
    if (!c) return null;
    if ((e.tag === 'main' || e.tag === 'lean' || e.tag === 'pin') && String(e.player || '').trim() === c) return null;
    return { cls: 'dk-tag t-club', text: `${CLUB_EMO}${c} 팬클럽`, title: `닉네임에 ${c} 팬클럽 말이 들어 있어요` };
}

/** 이름 옆에 붙일 딱지들 — [{cls, text, title}] (0~2개) */
export function chipsFor(tags, name) {
    const e = tagFor(tags, name);
    return [chipText(e), clubText(e)].filter(Boolean);
}

/** 화면 다시 그리기 판단용 — 그 이름의 딱지가 바뀌었나 */
export function tagSig(tags, name) {
    const e = tagFor(tags, name);
    return e ? [e.pid, e.tag, e.player, cnt(e.n), pct(e.share), e.club || ''].join('|') : '';
}

/* ── 후원자 목록(⚙ 설정 → 후원자 목록) ── */

/** 찾기 글자 비교 — 빈칸 · 대소문자 무시 */
const fold = s => String(s == null ? '' : s).toLowerCase().replace(/\s+/g, '');

/** 한 사람이 거르기 키에 맞나 */
export function matchFilter(p, f) {
    if (!p) return false;
    const test = !!p.test;
    if (f === 'test') return test;
    if (test) return false;                         // 시험 이름은 '🧪 시험 이름' 에서만 보인다
    if (!f || f === 'all') return true;
    if (f === 'club') return !!p.club;
    if (f === 'sugg') return cnt(p.sugg) > 0;
    if (f === 'dormant') return !!p.dormant;
    if (f === 'suspect') return !!p.suspect;           // 숫자만 · Player N 같은 이름 — 지우지 않고 표시만(대표님 확인)
    if (f === 'pin') return p.tag === 'pin' || !!p.pin;
    return p.tag === f;
}

/** 찾기 — 보이는 이름 · 예전 닉네임 · 선수 · 팬클럽 */
export function matchQuery(p, q) {
    const k = fold(q);
    if (!k) return true;
    const hay = [p.label, p.player, p.club, p.pin, ...(Array.isArray(p.names) ? p.names.map(x => (x && typeof x === 'object') ? x.name : x) : [])];
    return hay.some(s => s && fold(s).includes(k));
}

const SORTS = {
    recent: (a, b) => (Number(b.last_at) || 0) - (Number(a.last_at) || 0),
    won: (a, b) => (Number(b.total_won) || 0) - (Number(a.total_won) || 0),
    n: (a, b) => cnt(b.n) - cnt(a.n),
};
export const SORT_LABELS = [['recent', '최근 온 순'], ['won', '많이 준 순'], ['n', '자주 온 순']];

/** 거르기 · 찾기 · 줄 세우기 — 원본 배열은 그대로 둔다. 같으면 이름(가나다) 순 */
export function filterPersons(persons, { filter = 'all', q = '', sort = 'recent' } = {}) {
    const by = SORTS[sort] || SORTS.recent;
    return (Array.isArray(persons) ? persons : [])
        .filter(p => matchFilter(p, filter) && matchQuery(p, q))
        .sort((a, b) => by(a, b) || String(a.label || '').localeCompare(String(b.label || ''), 'ko'));
}

/** 거르기 단추 숫자 — {all, main, …} */
export function filterCounts(persons) {
    const out = {};
    for (const [k] of FILTERS) out[k] = 0;
    for (const p of Array.isArray(persons) ? persons : []) for (const [k] of FILTERS) if (matchFilter(p, k)) out[k]++;
    return out;
}

/* ── 후원자 카드 ── */

/** 멤버별 횟수 막대 — players {이름: n} → [{name, n, pct, w}] 많은 순. w = 가장 많은 사람 대비 폭(%) */
export function playerBars(players) {
    const rows = Object.entries(players && typeof players === 'object' ? players : {})
        .map(([name, n]) => ({ name, n: cnt(n) })).filter(r => r.n > 0)
        .sort((a, b) => b.n - a.n || a.name.localeCompare(b.name, 'ko'));
    const total = rows.reduce((s, r) => s + r.n, 0);
    const top = rows.length ? rows[0].n : 0;
    return rows.map(r => ({ ...r, pct: total ? Math.round(r.n * 100 / total) : 0, w: top ? Math.max(4, Math.round(r.n * 100 / top)) : 0 }));
}

/** 최근 후원 한 줄의 받은 사람 — player 글자 · players 배열 둘 다 받는다 */
export function recentTo(r) {
    if (!r) return '';
    const list = Array.isArray(r.players) ? r.players : (Array.isArray(r.player) ? r.player : (r.player ? [r.player] : []));
    return list.map(x => String(x || '').trim()).filter(Boolean).join(' · ');
}

/** 마지막으로 온 날 — '오늘' · '어제' · '5일 전' · '3달 전' · '1년 넘게'. at 은 초나 ms. now 는 ms */
export function relDay(at, now = Date.now()) {
    const n = Number(at) || 0;
    if (!n) return '';
    const ms = n < 1e12 ? n * 1000 : n;
    const d0 = new Date(ms), d1 = new Date(now);
    const day = x => Math.floor((Date.UTC(x.getFullYear(), x.getMonth(), x.getDate())) / 86400000);
    const diff = day(d1) - day(d0);
    if (diff <= 0) return '오늘';
    if (diff === 1) return '어제';
    if (diff < 31) return diff + '일 전';
    if (diff < 365) return Math.floor(diff / 30) + '달 전';
    return '1년 넘게';
}

/** 날짜 — '2026.10.07' (at 은 초나 ms) */
export function ymd(at) {
    const n = Number(at) || 0;
    if (!n) return '';
    const d = new Date(n < 1e12 ? n * 1000 : n);
    const p = x => String(x).padStart(2, '0');
    return `${d.getFullYear()}.${p(d.getMonth() + 1)}.${p(d.getDate())}`;
}

/* ── 팬클럽 사전 ── */

/** donor_clubs 조각 → [{word, player, confirmed, no, n, share}] — 추정(확인 기다림)이 위, 그다음 가나다.
 *  no = 대표님이 '팬클럽 말 아님' 으로 정한 것(confirmed 인데 선수 없음 — 서버 다시 채우기가 후보로 또 안 올린다).
 *  n · share = 추정의 근거(그 말이 든 닉네임들의 기억 수 · 가장 많은 선수 비율 — 서버가 주면) */
export function clubRows(clubs) {
    return Object.entries(clubs && typeof clubs === 'object' ? clubs : {})
        .map(([word, v]) => {
            const player = (v && v.player) || '', confirmed = !!(v && v.confirmed);
            return { word, player, confirmed, no: confirmed && !player, n: cnt(v && v.n), share: Number(v && v.share) || 0 };
        })
        .sort((a, b) => (a.confirmed - b.confirmed) || (a.no - b.no) || a.word.localeCompare(b.word, 'ko'));
}

/** 확인 기다리는 추정 수 */
export const clubGuessCount = clubs => clubRows(clubs).filter(r => !r.confirmed && r.player).length;

/** 📌 고정을 보여 줄까 — 서버가 pin_on:false 를 주면 숨긴다(대표님 답 대기 — 서버 한 곳에서 끈다). 안 주면 보인다 */
export function pinOn(j) {
    return !(j && (j.pin_on === false || j.pin_off === true));
}

/** 열린 제안 목록 응답 — 모양이 조금 달라도 배열로 */
export function suggestList(j) {
    if (Array.isArray(j)) return j;
    if (!j || typeof j !== 'object') return [];
    for (const k of ['suggest', 'rows', 'items', 'open']) if (Array.isArray(j[k])) return j[k];
    return [];
}
