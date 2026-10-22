/* 🙋 확인할 후원 띠 — 대표님 10-17 "금액은 조금이라도 애매하면 보류로 놓고 나를 호출해야 해".
   서버 자동 진행(autopilot)이 기계로 안 주고 '⏸ 보류' 로 남긴 카드(auto.hold 가 있는 것)가 대기함에 있으면
   상태 줄 경보 띠(alarm.js bandAdd — PC 상태 줄 가운데 · 폰 상태 점 밑)에 '🙋 확인할 후원 N건' + [보기](대기함으로).
   ⚠️ 소리는 절대 내지 않는다(대표님 규칙 — 경보 소리 금지). 처리하면(대기함에서 빠지면) 띠가 저절로 내려간다.
   ☕ 휴식(자동 진행 '켬')일 때만 띄운다 — 10-22 대표님 정리: 평소(📚 학습)엔 사람이 다 정하니 띠가 필요 없다. */
import { bandAdd, bandRemove } from '../../alarm.js';

const KEY = 'ap-hold';

/** 순수 — 대기함 → 보류 카드들(검사용) */
export function heldCards(slices) {
    const ap = (slices && slices.autopilot) || {};
    if (ap.mode !== 'on') return [];
    return ((slices && slices.pending) || []).filter(it => {
        const a = it && it.auto;
        return a && typeof a === 'object' && !a.asking && Array.isArray(a.hold) && a.hold.length && it.kind !== 'contrib';
    });
}

function openPending() {
    // 폰 서랍이 있으면 그쪽이 듣고 펼친다(kpis.js 와 같은 길) — 없으면 대기함으로 굴려 간다
    const ev = new CustomEvent('lm-drawer', { detail: { open: 'full' }, cancelable: true });
    if (!window.dispatchEvent(ev)) return;
    const card = document.querySelector('#pending .pcard.hold') || document.getElementById('pending');
    if (card) try { card.scrollIntoView({ block: 'center', behavior: 'smooth' }); } catch (e) { card.scrollIntoView(); }
}

let last = '';
export function syncHoldBand(slices, view) {
    const list = view === 'live' ? heldCards(slices) : [];
    const sig = list.map(it => it.id + ':' + it.auto.hold[0]).join('|');
    if (sig === last) return;
    last = sig;
    if (!list.length) { bandRemove(KEY); return; }
    const it = list[0];
    const won = Number(it.amount || 0).toLocaleString('ko-KR');
    bandAdd(KEY, {
        level: 'warn',
        title: `🙋 확인할 후원 ${list.length}건`,
        sub: `${it.name || '익명'} ${won}원 — ${it.auto.hold[0]}` + (list.length > 1 ? ` · 외 ${list.length - 1}건` : ''),
        act: { label: '보기', fn: openPending },
    });
}
