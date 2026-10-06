/* 🤖 자동 진행(무인 방송) 탭이 같이 쓰는 것 — 서버 약속은 v2/server/domain/autopilot.py 맨 위.
   조각 autopilot(비공개): mode · use_ai · games · stats{session, total} · log
   ⚠️ 바깥 글자(후원자 이름 · 까닭)는 전부 h()/textContent 로 — innerHTML 금지. */
import { h, num, won } from '../../util.js';

export { h, num, won };

export const MODES = {
    off: { label: '끔', icon: '⏸', desc: '기계는 아무것도 안 해요. 대기함 배지는 예전처럼 AI 제안만 보여요.' },
    shadow: { label: '그림자', icon: '👀', desc: "기계가 '했을 일' 만 적어요 — 점수는 사람이 그대로 눌러요. 2~3주 맞힌 비율을 보고 켜요." },
    on: { label: '켬', icon: '🤖', desc: '확실한 후원(거의 확실)은 기계가 바로 줘요. 애매하면 대기함에 보류로 남겨요. 금액 게임도 스스로 해요.' },
};

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
};

/** 기록 줄 판정 → [글자, 색 이름] */
export function outcomeOf(row, sid) {
    const o = row.outcome;
    if (o === 'agree') return ['✓ 맞힘', 'good'];
    if (o === 'disagree') return ['✗ 틀림', 'bad'];
    if (o === 'unknown') return ['몰라서 보류', 'hold'];
    if (o === 'ignored') return ['무시', 'dim'];
    if (o === 'auto') return [row.by === 'ap' ? '🚗 조종실 오토파일럿이 줌' : '🤖 자동으로 줌', 'auto'];
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

/** '지난 그림자 기록: 83건 중 79건 맞힘(95%)' */
export function hitLine(st, head = '지난 그림자 기록') {
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

/** 자동 진행 탭을 연다(탭 줄의 단추를 대신 누른다 — tabs.js 를 고치지 않고) */
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
