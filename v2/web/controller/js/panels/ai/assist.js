/* 🤖 대기함 쪽 AI 서포트 — pending.js 가 부르는 곳은 여기 하나다(화면 약속 1).
     attach(ctx)         대기함이 처음 붙을 때 한 번(연결 묶음을 넣는다)
     sync(slices)        대기함이 바뀔 때마다: 새 후원 묻기 · 🔔 먼저 알림 (🚗 오토파일럿은 10-22 ☕ 휴식으로 합쳐 뺐다)
     pick(it)            카드 한 장에 쓸 AI 판단 {level, target, text, title, more, game} (없으면 null) — 추천 단추 · AI 한 줄
     sig(id)             판단이 바뀌었는지(카드를 다시 그릴지) 보는 글자
     okToGive(it, name)  오배정 경고 — 메시지가 다른 사람을 가리키면 한 번 묻는다(옛 assignPending 의 'AI 기입 검증')

   10-17 시안 B(대표님): 어두운 '지급할까요?' 줄을 없앴다 — 같은 후원이 줄 하나 · 카드 하나로 **두 번** 보였다.
     이제 AI 가 고른 사람은 카드의 선수 단추 하나에 주황 테두리 + '추천' 딱지로만 보인다(pending.js). 누르면 다른 단추와 똑같은 길.
   판단 고르는 규칙(옛 paintAuditBadge · 자동 진행 배지 그대로 — '모름' 도 숨기지 않는다. 근거(why)는 title · 눌러 펼침)
     서버 자동 진행이 본 카드(auto) → 그 판단(autoBadge 와 같은 글자 한 줄)
     tier 'auto' → sure '거의 확실' · 이름 있고 확신 0.6↑ → maybe '아마도' · 잠깐 막힘 → wait '⏳ AI 붐빔'
     · 묻는 중 → asking 'AI 보는 중…' · 그 밖 → unknown '❓ 누구 것인지 모름'.  추천 단추는 sure · maybe 일 때만.
   ⚠️ 마우스가 대기함 위에 있는 동안(얼림)은 판단을 바꾸지 않는다 — 답이 와서 '추천' 이 다른 단추로 옮겨 가거나 줄이 늘면
      누르려던 자리에 다른 사람이 온다(돈이 걸린 오배정). 손을 떼면 그때 바뀐다. */
import { josaRo, isDonation, setCtx, getCtx } from './common.js';
import * as sug from './suggest.js';
import * as watch from './watch.js';
import { autoBadge } from '../auto/badge.js';            // 🤖 자동 진행(서버 autopilot) 판단 배지 — 글자 규칙을 그대로 빌린다

const AUDIT_MIN_CONF = 0.6;      // '아마도' · 추천 · 오배정 경고

const shown = new Map();         // id → {sig, ans} 카드에 지금 그려 둔 답 — 얼린 동안은 이것을 그대로 쓴다

export function attach(ctx) { setCtx(ctx); }

/* ── 대기함이 바뀔 때마다 ── */
// ⚠️ 여기서 무엇이 넘어져도 대기함 카드는 그려져야 한다 — 전부 감싼다(AI 줄 없이 도는 편이 낫다)
export function sync(slices) {
    try {
        const pend = slices.pending || [];
        sug.sync(pend);
        const ids = new Set(pend.map(x => x && x.id));
        for (const id of [...shown.keys()]) if (!ids.has(id)) shown.delete(id);
    } catch (e) { console.error('[AI 제안]', e); }
    try { watch.check(slices); } catch (e) { console.error('[AI 알림]', e); }
}

// 🔔 시간이 지나야 걸리는 알림(3분째 대기 · 대결 30초)은 조각이 안 바뀌어도 본다
setInterval(() => {
    const ctx = getCtx();
    if (ctx && document.body.dataset.view === 'live') { try { watch.check(ctx.slices); } catch (e) { console.error('[AI 알림]', e); } }
}, 15000);

function frozen() {
    const el = document.getElementById('pending');
    return !!(el && el.classList.contains('frozen'));
}

/* ── 카드가 다시 그려질지 ── 얼린 동안은 그려 둔 답을 그대로 */
export function sig(id) {
    const cur = 'ai' + sug.version(id);
    const prev = shown.get(id);
    if (prev && frozen()) return prev.sig;
    shown.set(id, { sig: cur, ans: sug.get(id) });
    return cur;
}

/* ── 카드 한 장의 AI 판단 ── */
export function pick(it) {
    try { return makePick(it); } catch (e) { console.error('[AI 판단]', e); return null; }
}

const LV_TEXT = { sure: '거의 확실', maybe: '아마도', unknown: '❓ 누구 것인지 모름', wait: '⏳ AI 붐빔 — 곧 다시 물어요', asking: 'AI 보는 중…' };

function histText(hist) {
    const h3 = (hist || []).slice(0, 3).filter(x => x && x.name);
    return h3.length ? '지난 배정 · ' + h3.map(x => `${x.name} ${x.count}번`).join(' · ') : '';
}

function makePick(it) {
    if (!isDonation(it)) return null;
    const snap = shown.get(it.id);
    const s = snap ? snap.ans : sug.get(it.id);
    if (!s || s.gone || s.skipped) return null;
    const hist = histText(s.history);
    if (s.auto) return autoPick(s.auto, s.history, hist);
    let level;
    if (s.asking) level = 'asking';
    else if (s.target && s.tier === 'auto') level = 'sure';
    else if (s.target && (s.confidence || 0) >= AUDIT_MIN_CONF) level = 'maybe';
    else if (s.retryIn) level = 'wait';          // 잠깐 막힌 것뿐 — '모름' 과 섞으면 사람이 괜히 손으로 판단하러 간다
    else level = 'unknown';                      // '모름' 을 숨기지 않는다. 자리를 비웠을 때 이게 쌓이는 것이 곧 할 일이다
    const target = (level === 'sure' || level === 'maybe') ? s.target : '';
    const text = target ? `${target} ${LV_TEXT[level]}` : LV_TEXT[level];
    const more = [s.target && !target ? `${s.target}${josaRo(s.target)} 보이지만 확신이 낮아요` : '', s.why ? '까닭: ' + s.why : '', hist].filter(Boolean).join(' · ');
    return { level, target, text, more, title: [text, more, s.source ? '판단 근거: ' + s.source : ''].filter(Boolean).join('\n'), game: null };
}

// 서버 자동 진행이 판단한 카드 — 글자는 autoBadge(자동 진행 탭과 같은 말) 를 한 줄로
function autoPick(a, history, hist) {
    const node = autoBadge(a, history);
    const badge = node && node.querySelector('.ai-badge');
    const whyEl = badge && badge.querySelector('.ai-why');
    const why = whyEl ? whyEl.textContent.replace(/^\s*·\s*/, '') : '';
    if (whyEl) whyEl.remove();
    const text = badge ? badge.textContent.trim() : '🤖 자동 진행';
    const gameEl = node && node.querySelector('.au-cgame');
    const conf = Number(a.confidence) || 0;
    let level;
    const hold = Array.isArray(a.hold) && a.hold.length && (a.mode === 'on' || a.check);
    if (a.asking) level = 'asking';
    else if (hold) level = 'hold';                   // ⏸ 보류 — 확인해 주세요(추천 단추를 안 띄운다)
    else if (a.retry && !a.target) level = 'wait';
    else if (a.act && a.target && a.mode !== 'on') level = 'sure';
    else if (a.target && conf >= AUDIT_MIN_CONF) level = 'maybe';
    else level = a.mode === 'on' ? 'held' : 'unknown';
    const target = (level === 'sure' || level === 'maybe') ? a.target : '';
    const more = [hold ? '보류 까닭: ' + a.hold.join(' · ') : (why ? '까닭: ' + why : ''), hist].filter(Boolean).join(' · ');
    // 그림자('자동이라면')로 고른 사람이 있으면 다른 카드와 같은 말('밍밍 거의 확실') — 자동 진행 말은 title 로. 켬 · 보류는 autoBadge 말 그대로
    const plain = a.mode !== 'on' && !!target;
    // ⏸ 보류 카드는 위 주황 띠(pending.js)가 '보류 — 확인해 주세요 + 까닭' 을 이미 말한다 — 여기서는 기계가 본 이름만 짧게
    const holdText = level === 'hold' ? (a.target ? `${a.target}${josaRo(a.target)} 보임 · 까닭 보기` : '까닭 보기') : '';
    return {
        level, target, text: holdText || (plain ? `${target} ${LV_TEXT[level]}` : text), more, auto: !plain,
        title: [text, more, a.source ? '판단 근거: ' + a.source : '', '학습 · 휴식 탭에서 기록을 볼 수 있어요'].filter(Boolean).join('\n'),
        game: gameEl ? { text: gameEl.textContent, cls: gameEl.className } : null,
    };
}

/* ── 오배정 경고 ── 메시지가 '하율' 을 가리키는데 '서아' 를 누르면 한 번 묻는다. 취소하면 아무것도 안 한다 */
export async function okToGive(it, name) {
    let s = null;
    try { s = sug.get(it && it.id); } catch (e) { return true; }
    if (!s || !s.target || (s.confidence || 0) < AUDIT_MIN_CONF || s.target === name) return true;
    const ctx = getCtx();
    if (!ctx) return true;
    return ctx.confirm({
        title: '🤖 다른 사람 후원 같아요',
        body: `메시지를 보면 이 후원은 '${s.target}' 을(를) 응원하는 것 같아요.` + (s.why ? `\n(근거: ${s.why})` : '') + `\n\n그래도 '${name}' 에게 줄까요?`,
        ok: `${name}에게 주기`, cancel: '취소',
    });
}

