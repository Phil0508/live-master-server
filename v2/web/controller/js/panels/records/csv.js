/* 📥 장부 엑셀(CSV) 만들기 — 장부 탭 [⬇ 엑셀] 이 부른다(옛 features/archive.py /api/archive/csv 와 같은 약속).
   - 한글이 안 깨지게 맨 앞에 BOM(엑셀이 UTF-8 을 알아보게) · 줄 끝은 \r\n.
   - = + - @ 로 시작하는 글(후원자 이름 · 메시지는 후원자가 적는 글)은 앞에 ' 를 붙여 엑셀이 수식으로 읽지 않게 —
     같은 규칙을 두 번 적지 않으려고 월별 순위의 csvCell 을 그대로 부른다(monthly.js).
   - 시각은 **한국 시각**(이 PC 시계가 어디에 맞춰져 있든) 'YYYY-MM-DD HH:MM:SS'. 옛 것도 9시간 어긋나지 않게 한국 시각으로 옮겨 내보냈다.
   - 금액 · 점수 숫자는 따옴표 없이(엑셀이 숫자로 더할 수 있게). 우리가 만든 숫자라 수식이 될 수 없다.
   화면을 안 만지는 순수 계산만 — 검사가 node 로 그대로 부른다. */
import { csvCell } from '../more/monthly.js';

export const BOM = '\ufeff';
const KST_MS = 9 * 3600 * 1000;

/** 초(또는 ms) → 한국 시각 'YYYY-MM-DD HH:MM:SS'. 없으면 '' */
export function kst(at) {
    const n = Number(at) || 0;
    if (!n) return '';
    const d = new Date((n < 1e12 ? n * 1000 : n) + KST_MS);
    const p = x => String(x).padStart(2, '0');
    return `${d.getUTCFullYear()}-${p(d.getUTCMonth() + 1)}-${p(d.getUTCDate())} ${p(d.getUTCHours())}:${p(d.getUTCMinutes())}:${p(d.getUTCSeconds())}`;
}

/** 방송 회차 번호 '20261007-2030-ab12' → '2026-10-07 20:30' (모르는 꼴이면 그대로, 빈 회차는 '방송 밖') */
export function sessionStamp(id) {
    const m = /^(\d{4})(\d{2})(\d{2})-(\d{2})(\d{2})/.exec(String(id || ''));
    if (!id) return '방송 밖';
    return m ? `${m[1]}-${m[2]}-${m[3]} ${m[4]}:${m[5]}` : String(id);
}

/** 머리줄 + 줄들 → CSV 글(BOM 포함). cells: 글은 csvCell 로, 숫자(number)는 그대로 */
export function csvText(head, rows) {
    const cell = v => (typeof v === 'number' && Number.isFinite(v)) ? String(v) : csvCell(v);
    const lines = [head.map(csvCell).join(',')].concat(rows.map(r => r.map(cell).join(',')));
    return BOM + lines.join('\r\n') + '\r\n';
}

const STATUS = { pending: '대기', assigned: '배정', ignored: '무시', display: '화면만(합계 밖)' };
const SOURCE = { toonation: '투네이션', toonation_test: '시험 후원', manual: '손으로 넣음',
    toonation_replay: '다시 보기(화면만)', toonation_dashtest: '후원 테스트(화면만)' };
const LIST = { list: '본판', extra: '번외', jar: '모금함', bottom: '운영비' };

export const DONATION_HEAD = ['회차', '시각(한국)', '후원자', '금액', '메시지', '상태', '받은 선수', '경로'];
export const SCORE_HEAD = ['회차', '시각(한국)', '선수', '판', '항목', '변화', '까닭', '후원 묶음', '되돌림'];

/** 후원 줄(/api/ledger rows) → CSV. 오래된 것이 위로(장부 순서). */
export function donationsCsv(rows) {
    const list = (rows || []).slice().sort((a, b) => (Number(a.at) || 0) - (Number(b.at) || 0) || (Number(a.id) || 0) - (Number(b.id) || 0));
    return csvText(DONATION_HEAD, list.map(r => [
        sessionStamp(r.session), kst(r.at), r.name || '익명', Math.round(Number(r.amount) || 0), r.message || '',
        STATUS[r.status] || r.status || '', r.player || '', SOURCE[r.source] || r.source || '',
    ]));
}

/** 점수 기록 줄(/api/scores rows) → CSV. 한 줄 = 기록 하나(묶지 않는다 — 정산은 원래 줄이 낫다). 오래된 것이 위로. */
export function scoresCsv(rows) {
    const list = (rows || []).slice().sort((a, b) => (Number(a.at) || 0) - (Number(b.at) || 0) || (Number(a.id) || 0) - (Number(b.id) || 0));
    return csvText(SCORE_HEAD, list.map(r => [
        sessionStamp(r.session), kst(r.at), r.player || '', LIST[r.list] || r.list || '본판',
        r.field === 'contribution' ? '기여도' : '점수', Math.round(Number(r.delta) || 0), r.reason || '',
        r.ref || '', r.undone ? '되돌림' : '',
    ]));
}

/** 파일 이름에 못 쓰는 글자를 뺀다 — '후원내역_2026-10-07 20:30' → '후원내역_2026-10-07_2030' */
export function fileName(base) {
    return String(base || '장부').replace(/[\\/:*?"<>|]+/g, '').replace(/\s+/g, '_').slice(0, 80) + '.csv';
}
