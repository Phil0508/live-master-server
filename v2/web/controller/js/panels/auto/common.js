/* 📚 학습 · ☕ 휴식(서버 자동 진행) 탭이 같이 쓰는 것 — 서버 약속은 v2/server/domain/autopilot.py 맨 위.
   10-22 대표님 정리: 조종실에 보이는 건 두 가지 — 📚 학습(mode 'shadow', 평소) · ☕ 휴식(mode 'on'). 'off' 는 검사 · 비상용.
   조각 autopilot(비공개): mode · use_ai · games · stats{session, total} · log · days(방송마다 그날 성적)
   ⚠️ 바깥 글자(후원자 이름 · 까닭)는 전부 h()/textContent 로 — innerHTML 금지. */
import { h, num, won } from '../../util.js';

export { h, num, won };

export const MODES = {
    shadow: { label: '학습', icon: '📚', desc: '평소 — 점수는 사람이 줘요. 기계도 후원마다 답을 적어 두고, 사람이 준 것과 맞춰 채점해요.' },
    on: { label: '휴식', icon: '☕', desc: '자리 비울 때 — 확실한 투네 후원은 기계가 바로 점수를 넣어요. 애매한 것 · 계좌 입금은 초록 알림으로 불러요. 방송이 끝나면 저절로 꺼져요.' },
    off: { label: '끔', icon: '⏸', desc: '기계가 아무것도 안 해요(검사 · 비상용 — 조종실엔 단추가 없어요).' },
};
export const SHOWN_MODES = ['shadow', 'on'];

export const GAMES = {
    roulette: { label: '룰렛', icon: '🎡' },
    slot: { label: '슬롯', icon: '🎰' },
    dice: { label: '주사위', icon: '🎲' },
};

/** 기계가 스스로 안 준 까닭(서버 autopilot.HELD 와 같다) */
export const HELD = {
    unsure: '확실하지 않아서',
    returned: '되돌려 돌아온 후원이라 사람이 다시 정해요',
    test: '시험 후원이라 자동으로 안 줘요',
    failed: '자동으로 주려다 막혔어요',
    retry: 'AI 가 붐벼 조금 뒤 다시 물어봐요',
    check: '애매해서 사람이 확인해요',
};

/** 기록 줄 판정 → [글자, 색 이름] */
export function outcomeOf(row, sid) {
    const o = row.outcome;
    if (o === 'agree') return ['✓ 맞힘', 'good'];
    if (o === 'disagree') return ['✗ 틀림', 'bad'];
    if (o === 'unknown') return ['몰라서 보류', 'hold'];
    if (o === 'held') return ['⏸ 애매해서 보류', 'hold'];
    if (o === 'ignored') return ['무시', 'dim'];
    if (o === 'auto') return [row.by === 'ap' ? '🚗 옛 오토파일럿이 줌' : row.by === 'autopilot-ai' ? '🤖 AI 가 줌' : '☕ 휴식 — 기계가 줌', 'auto'];
    if (row.sid && sid && row.sid !== sid) return ['방송 끝 — 처리 안 됨', 'dim'];
    return ['처리 전', 'wait'];
}

/** 맞힌 비율 — 기계가 '줬을 것' 중 사람이 같은 사람에게 준 비율. 채점된 게 없으면 null */
export function hitRate(st) {
    const s = st || {};
    const judged = (Number(s.agree) || 0) + (Number(s.disagree) || 0);
    if (!judged) return null;
    return { hit: Number(s.agree) || 0, judged, pct: Math.round((Number(s.agree) || 0) * 100 / judged) };
}

/** 📚 학습 점수 — 기계의 1순위 답(확실하든 아니든) 중 사람도 같은 사람에게 준 비율. 채점된 게 없으면 null */
export function guessRate(st) {
    const s = st || {};
    const hit = Number(s.guess_hit) || 0, judged = hit + (Number(s.guess_miss) || 0);
    return judged ? { hit, judged, pct: Math.round(hit * 100 / judged) } : null;
}

/** 사람이 정한 것 중 기계가 답을 못 낸 수(몰라서) — 사람이 준 것 전부 − 기계가 답을 낸 것 */
export function noAnswer(st) {
    const s = st || {};
    const human = ['agree', 'disagree', 'unknown', 'held'].reduce((n, k) => n + (Number(s[k]) || 0), 0);
    return Math.max(0, human - (Number(s.guess_hit) || 0) - (Number(s.guess_miss) || 0));
}

/** AI 맞힌 비율 — AI 가 '줬을 것'(확신 0.9↑) 중 사람도 같은 사람에게 준 비율 */
export function aiHitRate(st) {
    const s = st || {};
    const hit = Number(s.ai_agree) || 0, judged = hit + (Number(s.ai_disagree) || 0);
    return judged ? { hit, judged, pct: Math.round(hit * 100 / judged) } : null;
}

/** '확실했던 것: 83건 중 79건 맞힘(95%)' — 휴식이었다면 기계가 혼자 줬을 것의 채점 */
export function hitLine(st, head = '확실했던 것') {
    const r = hitRate(st);
    if (!r) return `${head}: 아직 채점된 게 없어요`;
    return `${head}: ${num(r.judged)}건 중 ${num(r.hit)}건 맞힘(${r.pct}%)`;
}

/** 시:분 (ms) */
export function hm(ms) {
    const n = Number(ms) || 0;
    if (!n) return '';
    const d = new Date(n);
    const p = x => String(x).padStart(2, '0');
    return p(d.getHours()) + ':' + p(d.getMinutes());
}

/** 학습 · 휴식 탭을 연다(탭 줄의 단추를 대신 누른다 — tabs.js 를 고치지 않고) */
export function openAutoTab() {
    const b = document.querySelector('.tabbar .tab[data-tab="auto"]');
    if (!b) return false;
    b.click();
    const el = document.querySelector('.tabpanel[data-panel="auto"]');
    if (el) setTimeout(() => { try { el.scrollIntoView({ block: 'start', behavior: 'smooth' }); } catch (e) { el.scrollIntoView(); } }, 60);
    return true;
}

/** 금액 범위 글자 — 50,000원 이상 · 10,000 ~ 19,999원 */
export function rangeText(min, max) {
    const a = Number(min) || 0, b = Number(max) || 0;
    if (!b) return `${num(a)}원 이상`;
    return `${num(a)} ~ ${num(b)}원`;
}
