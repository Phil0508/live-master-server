/* ↻ 다시 송출 — 장부 줄 하나를 방송 화면에만 한 번 더(대표님 10-17 '재송출도 가능하게').

   누르는 곳: 장부 탭 이번 방송 줄마다 [↻ 다시 송출](방송 중일 때).
     ⚠️ 대기함 카드에도 [↻] 를 달아 봤더니 좁은 오른쪽 칸에서 후원자 이름이 '아…' 로 잘렸다(1440 사진) — 배정 실수가 더 무섭다.
        재송출은 이미 지나간 후원을 다시 보이는 일이라 장부 탭에만 둔다.
   1) 화면 안 확인 상자(confirm() 아님) — 사람이 알아보는 것을 크게: '영원 30,000원 · 21:03 · “밍밍화이팅”'.
      번호(#12)는 장부를 구별하는 조용한 꼬리표라 상자 아래 작은 회색 글씨로만.
   2) [띄우기] → POST /api/donation/replay {id} — 서버가 금액으로 시그니처를 다시 맞추고(명령 밖) donation.replay 를 부른다.
      점수 · 정산 · 대기함 · 후원 순위 · 시그 집계에는 안 들어간다(장부엔 '화면만' 줄 '↻ #12 다시 송출').
   기본 손가락 자리는 [취소](confirmBox) — Enter 를 습관처럼 눌러도 방송에 안 나간다. */
import { h, won, clock } from './util.js';
import { api } from './panels/ops/common.js';

const busy = new Set();

/** 다시 송출할 수 있는 장부 줄인가 — 다시 송출 기록 · 대시보드 테스트 줄은 아니다(서버 donation.NO_REPLAY_SOURCES 와 같다) */
export function canReplay(row) {
    return !!(row && row.id && String(row.id).startsWith('don_') && row.source !== 'replay' && row.source !== 'toonation_dashtest');
}

/** row: {id, name, amount, message, at(초 또는 ms), no?} — 묻고 띄운다. 돌려주는 값: 띄웠으면 true */
export async function askReplay(ctx, row) {
    if (!row || !row.id || busy.has(row.id)) return false;
    const amt = Number(row.amount) || 0;
    const msg = String(row.message || '').trim();
    const body = h('div', { class: 'rp-box' },
        h('p', { class: 'rp-who' }, h('b', null, row.name || '익명'), ' ', h('span', { class: 'rp-amt' }, amt ? won(amt) : '0원')),
        h('p', { class: 'rp-meta' }, [clock(row.at), msg ? '“' + msg + '”' : ''].filter(Boolean).join(' · ')),
        h('p', { class: 'rp-note' }, '방송 화면에 후원 팝업 · 시그니처만 한 번 더 나가요. 점수 · 정산 · 후원 순위엔 안 들어가요.'),
        row.no ? h('p', { class: 'rp-no' }, '장부 #' + row.no) : null);
    const ok = await ctx.confirm({ title: '방송 화면에 한 번 더 띄울까요?', body, ok: '띄우기', cancel: '취소', danger: false, cls: 'rp-modal' });
    if (!ok) return false;
    busy.add(row.id);
    try {
        const r = await api('/api/donation/replay', { id: row.id });
        if (!r.ok) { ctx.toast('다시 송출하지 못했어요 — ' + r.error, 'err'); return false; }
        const t = r.data.title ? ` · ${r.data.title}` : '';
        ctx.toast(`↻ ${row.name || '익명'} ${won(amt)} — 방송 화면에 한 번 더 띄웠어요${t} (점수 · 정산엔 안 들어가요)`, 'ok', 4200);
        return true;
    } finally {
        busy.delete(row.id);
    }
}
