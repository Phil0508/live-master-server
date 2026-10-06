/* 🤖 배정 제안 — '이 후원은 누구 것인가' 를 서버에 묻고(POST /api/audit/suggest {id}) 답을 기억한다.
   ⚠️ AI 는 절대 점수를 바꾸지 않는다. 여기는 묻고 기억만 한다 — 배지 · '지급할까요?' · 오토파일럿이 이 답을 읽는다.

   규칙(옛 조종실 queueAudits · auditAsk 그대로, 화면 약속 1)
     · 대기함 항목마다 한 번 묻는다. 퇴근 카드 · 기여도 카드는 묻지 않는다(답 없는 질문에 AI 한도만 태운다).
     · 메시지가 없어도 묻는다 — '이 후원자는 늘 밍밍에게 갔다' 는 이력만으로 풀린다.
     · retry(AI 가 잠깐 막힘)면 20초 × n 뒤에 다시(세 번까지). 그 사이 대기함에서 빠졌으면 안 묻는다.
       그동안 배지는 '⏳ AI 가 붐벼요'. 서버에 닿지 않았을 때도 같은 규칙으로 다시 묻는다.
     · 대기함에 없는 id(404 gone) — 이미 배정 · 무시됨. 조용히 넘긴다.
     · 대기함에서 빠진 후원은 답을 버린다 — 되돌려 돌아오면(되돌리기) 새로 묻는다(서버가 '후원자 기억' 을 잊었다).
   한꺼번에 많이 들어와도 서버를 두드리지 않게 동시에 3건까지만 묻는다. */
import { call, isDonation, getCtx } from './common.js';

const MAX_RETRY = 3;
const RETRY_MS = 20000;
const PARALLEL = 3;

const answers = new Map();     // 후원 id → 답 {target, confidence, tier, source, why, history, retry, retryIn, asking, gone, skipped}
const asked = new Set();       // 물었거나 묻는 중인 id
const retries = new Map();     // id → 다시 물은 횟수
const ver = new Map();         // id → 답이 바뀐 횟수(대기함 카드가 다시 그릴지 보는 데 쓴다)
const waiting = [];            // 아직 못 보낸 id(동시 3건 넘은 것)
let flying = 0;
const listeners = new Set();   // 답이 들어올 때마다 fn(id, 답)

export function get(id) { return answers.get(id) || null; }
export function version(id) { return ver.get(id) || 0; }
export function onAnswer(fn) { listeners.add(fn); }

function bump(id) {
    ver.set(id, (ver.get(id) || 0) + 1);
}

function stillPending(id) {
    const ctx = getCtx();
    return !!ctx && ((ctx.slices || {}).pending || []).some(x => x && x.id === id);
}

/** 대기함 목록이 바뀔 때마다 — 새 후원은 묻고, 빠진 후원의 답은 버린다 */
export function sync(pend) {
    const ids = new Set();
    (pend || []).forEach(it => {
        if (!it || !it.id) return;
        ids.add(it.id);
        if (!isDonation(it) || asked.has(it.id)) return;
        asked.add(it.id);
        answers.set(it.id, { asking: true });
        bump(it.id);
        enqueue(it.id);
    });
    for (const id of [...answers.keys()]) {
        if (ids.has(id)) continue;
        answers.delete(id);
        asked.delete(id);
        retries.delete(id);
        ver.delete(id);
    }
}

function enqueue(id) {
    waiting.push(id);
    pump();
}

function pump() {
    while (flying < PARALLEL && waiting.length) {
        const id = waiting.shift();
        if (!stillPending(id)) { answers.delete(id); asked.delete(id); continue; }
        flying++;
        ask(id).finally(() => { flying--; pump(); });
    }
}

async function ask(id) {
    const r = await call('/api/audit/suggest', { id });
    if (!asked.has(id)) return;                       // 그새 대기함에서 빠졌다
    let res;
    if (r.status === 404 && r.data && r.data.gone) {
        answers.set(id, { gone: true });              // 이미 배정 · 무시됨 — 배지 없이 조용히
        bump(id);
        tell(id);
        return;
    }
    if (r.status === 401) {
        res = { target: null, confidence: 0, tier: 'unknown', why: '로그인이 풀려 못 물어봄 — 새로 고쳐 다시 들어가 주세요', history: [] };
    } else if (!r.ok) {
        // 서버에 닿지 않음 · 이상한 답 — 붐빔과 같게 조금 뒤 다시 묻는다
        res = { target: null, confidence: 0, tier: 'unknown', why: '서버에 닿지 않아 못 물어봄', history: [], retry: true };
    } else {
        const d = r.data;
        res = {
            target: d.target || null, confidence: Number(d.confidence) || 0, tier: d.tier || 'unknown',
            source: d.source || null, why: d.why || null, history: Array.isArray(d.history) ? d.history : [],
            retry: !!d.retry, skipped: !!d.skipped, cached: !!d.cached,
        };
    }
    if (res.retry) {
        const n = (retries.get(id) || 0) + 1;
        retries.set(id, n);
        if (n <= MAX_RETRY) {
            res.retryIn = true;                       // '⏳ 곧 다시 물어봐요' — '모름' 과 섞지 않는다
            setTimeout(() => {
                if (!asked.has(id) || !stillPending(id)) return;     // 그새 배정 · 무시됐으면 안 묻는다
                enqueue(id);
            }, RETRY_MS * n);
        }
    }
    answers.set(id, res);
    bump(id);
    tell(id);
}

function tell(id) {
    const a = answers.get(id);
    listeners.forEach(fn => { try { fn(id, a); } catch (e) { console.error('[AI 제안]', e); } });
    const ctx = getCtx();
    if (ctx) ctx.rerender();
}
