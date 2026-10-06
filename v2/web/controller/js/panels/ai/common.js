/* 🤖 AI 서포트 — 여러 조각이 같이 쓰는 작은 도구.
   서버 약속은 v2/server/domain/ai.py 맨 위 '화면 약속' 에 있다(배정 제안 · 상황판 · 물어보기).
   ⚠️ 바깥 글자(후원자 이름 · 메시지 · AI 답)는 전부 textContent 로 넣는다 — innerHTML 금지.
      AI 답은 '**굵게**' 와 '- ' 목록만 살린다(글자를 잘라 <b> · 목록 줄을 직접 만든다). */
import { h } from '../../util.js';

export { h };

/** 옛 주소(쿠키 로그인)로 묻기 — 답은 {ok, status, data}. 서버는 언제나 JSON 으로 답한다(못 받으면 status 0). */
export async function call(path, body) {
    try {
        const init = { method: body === undefined ? 'GET' : 'POST', credentials: 'same-origin', cache: 'no-store', headers: {} };
        if (body !== undefined) { init.headers['Content-Type'] = 'application/json'; init.body = JSON.stringify(body); }
        const r = await fetch(path, init);
        const data = await r.json().catch(() => null);
        return { ok: r.ok && !!data && data.status === 'success', status: r.status, data: data || {} };
    } catch (e) {
        return { ok: false, status: 0, data: {} };
    }
}

/** 지금 판 선수 이름 — 번외 판이 켜져 있으면 번외 판(서버 ai_facts.current_names · pending.assign 기본 판과 같다) */
export function currentNames(slices) {
    const P = (slices && slices.players) || {};
    return (P[P.extra_active ? 'extra' : 'list'] || []).map(r => String((r && r.name) || '').trim()).filter(Boolean);
}

/** 받침이 있으면 '으로', 없거나 ㄹ 받침이면 '로' — '제이양로 보임' 처럼 어색하던 것(옛 josaRo) */
export function josaRo(name) {
    const c = String(name || '').trim().slice(-1).charCodeAt(0);
    if (!(c >= 0xac00 && c <= 0xd7a3)) return '로';
    const jong = (c - 0xac00) % 28;
    return (jong === 0 || jong === 8) ? '로' : '으로';
}

/** 받침이 있으면 '을', 없으면 '를' */
export function josaEul(name) {
    const c = String(name || '').trim().slice(-1).charCodeAt(0);
    if (!(c >= 0xac00 && c <= 0xd7a3)) return '을(를)';
    return (c - 0xac00) % 28 ? '을' : '를';
}

/** 후원 카드인가 — 퇴근 · 탈출 카드(type 'off_work') · 기여도 카드(kind 'contrib')는 '누구 것인가' 를 묻지 않는다 */
export const isDonation = it => !!it && it.type !== 'off_work' && it.kind !== 'contrib';

/** 답 글자 → 화면 줄들. '**굵게**' 와 '- ' · '• ' 목록만 살린다(옛 aiFmt 와 같은 규칙, 대신 innerHTML 을 안 쓴다) */
export function replyNodes(text) {
    const out = [];
    String(text || '').split('\n').forEach((line, i, all) => {
        const li = /^\s*[-•]\s+/.exec(line);
        const body = li ? line.slice(li[0].length) : line;
        const parts = [];
        const re = /\*\*(.+?)\*\*/g;
        let at = 0, m;
        while ((m = re.exec(body))) {
            if (m.index > at) parts.push(body.slice(at, m.index));
            parts.push(h('b', null, m[1]));
            at = m.index + m[0].length;
        }
        if (at < body.length) parts.push(body.slice(at));
        if (li) out.push(h('span', { class: 'ai-li' }, parts));
        else {
            out.push(...parts);
            // 다음 줄이 목록이면 줄바꿈은 목록 줄이 대신한다
            if (i < all.length - 1 && !/^\s*[-•]\s+/.test(all[i + 1])) out.push(h('br'));
        }
    });
    return out;
}

/** 누가 답했나 — ⚡ 서버가 센 것(늘 맞다) · 🤖 AI 가 말을 다듬은 것(가끔 틀릴 수 있다) · ℹ️ 답 대신 안내 */
export const SRC = {
    calc: ['⚡ 서버 계산', '서버가 장부 · 점수판에서 바로 센 값이에요 — 늘 맞아요'],
    ai: ['🤖 AI', 'AI 가 서버가 센 사실표를 보고 말로 다듬은 답이에요 — 가끔 틀릴 수 있어요'],
    none: ['ℹ️ 안내', 'AI 도 서버 계산도 답을 만들지 못했어요 — 까닭을 그대로 보여 드려요'],
};

/** 빠른 질문 이름표 — 서버(ai_facts.INTENTS)가 주는 것과 같다. 상황판을 받기 전에 쓴다 */
export const INTENTS = {
    rank: '📊 순위', pending: '📥 대기함', goal: '🎯 목표', match: '⚔️ 대결',
    race: '🏃 퇴근빵', today: '💰 오늘 후원', sig: '🎵 시그 순위', flow: '📈 최근 흐름',
};

/** '이번 방송 후원' — 장부에서 센 숫자(GET /api/ai/board?today=1). 머리줄 칸 · AI 탭이 같이 쓴다.
 *  AI 탭이 열려 있으면 4초마다 새로 받으므로 머리줄은 따로 안 묻는다(fresh). */
export const today = {
    data: undefined,       // undefined = 아직 안 받음 · null = 서버가 못 셈 · {건수, 합계금액, 많이_쏜_사람}
    at: 0,
    subs: new Set(),
    set(v) { this.data = v; this.at = Date.now(); this.subs.forEach(fn => { try { fn(v); } catch (e) { console.error('[AI 오늘]', e); } }); },
    fresh(ms) { return this.data !== undefined && Date.now() - this.at < ms; },
};

/** 조종실 연결 묶음(ctx) — 처음 붙는 곳(대기함 · AI 탭)이 한 번 넣는다 */
let CTX = null;
export function setCtx(ctx) { if (ctx && !CTX) CTX = ctx; }
export function getCtx() { return CTX; }

/** 서버 시계(ms) — 대기함 시각(at) · 대결 끝 시각이 서버 시각이다 */
export function serverNow() {
    const lm = CTX && CTX.lm;
    return lm && typeof lm.serverNow === 'function' ? lm.serverNow() : Date.now();
}

/** AI 탭이 지금 눈에 보이는가 — 탭이 열려 있고(숨김 아님) 방송 중 화면이고 창이 가려지지 않았을 때 */
export function aiTabVisible() {
    const el = document.querySelector('.tabpanel[data-panel="ai"]');
    return !!el && !el.hidden && el.isConnected && document.body.dataset.view === 'live' && !document.hidden;
}

/** AI 탭을 연다(탭 줄의 단추를 대신 누른다 — tabs.js 를 고치지 않고) */
export function openAiTab(scroll) {
    const b = document.querySelector('.tabbar .tab[data-tab="ai"]');
    if (!b) return false;
    b.click();
    if (scroll) {
        const el = document.querySelector('.tabpanel[data-panel="ai"]');
        if (el) setTimeout(() => { try { el.scrollIntoView({ block: 'start', behavior: 'smooth' }); } catch (e) { el.scrollIntoView(); } }, 60);
    }
    return true;
}

/** 시:분:초 */
export function hms(ms) {
    const d = new Date(ms || Date.now());
    const p = x => String(x).padStart(2, '0');
    return p(d.getHours()) + ':' + p(d.getMinutes()) + ':' + p(d.getSeconds());
}
