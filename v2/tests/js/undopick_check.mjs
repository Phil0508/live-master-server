// ↩ 골라 되돌리기 — 확인 상자에 무엇이 적히나(undopick.js 실물을 그대로 부른다 · v2/tests/test_undopick.py 가 부른다).
// 답: 줄마다 'OK 이름' · 'BAD 이름 -- 까닭', 끝에 'DONE n'
import { fileURLToPath, pathToFileURL } from 'node:url';
import path from 'node:path';

const here = path.dirname(fileURLToPath(import.meta.url));
const js = path.resolve(here, '..', '..', 'web', 'controller', 'js');
const U = await import(pathToFileURL(path.join(js, 'undopick.js')).href);

let n = 0;
function chk(name, cond, detail) {
    n++;
    console.log((cond ? 'OK ' : 'BAD ') + name + (cond ? '' : ' -- ' + JSON.stringify(detail === undefined ? null : detail)));
}
const eq = (a, b) => JSON.stringify(a) === JSON.stringify(b);

const at = new Date(2026, 9, 21, 21, 3, 5).getTime() / 1000;      // 21:03
// 서버 logs 조각 모양 — 맨 앞이 최근. 나눠 준 후원은 같은 ref 두 줄(서버가 앞사람부터 insert(0) 해서 거꾸로 쌓인다)
const logs = [
    { at: at + 60, name: '하율', val: 2, cval: 2, before: 0, after: 2, cbefore: 0, cafter: 2, ref: 'don_split', list: 'list', don: { name: '별빛', amount: 50000 } },
    { at: at + 60, name: '밍밍', val: 3, cval: 3, before: 5, after: 8, cbefore: 5, cafter: 8, ref: 'don_split', list: 'list', don: { name: '별빛', amount: 50000 } },
    { at: at + 30, name: '서아', val: 1, cval: 1, ref: 'act_hand', list: 'list' },
    { at: at + 10, name: '채원', val: 0, cval: 3, ref: 'dg_1', list: 'list', kind: 'contrib', why: '🎲 주사위' },
    { at, name: '밍밍', val: 5, cval: 5, before: 0, after: 5, cbefore: 0, cafter: 5, ref: 'don_one', list: 'list', don: { name: '영원', amount: 50000 }, by: 'autopilot-ai' },
];
const S = { logs, players: { extra_active: false } };

const one = U.undoPlan(S, 'don_one');
chk('한 줄 후원: 머리 = 시각 이름 점수(후원자 금액)', U.planTitle(one) === '21:03 밍밍 +5점(영원 50,000원)', U.planTitle(one));
chk('한 줄 후원: 대기함으로 돌아간다고 적는다', U.planNotes(one)[0] === '후원은 대기함으로 돌아가요 — 영원 ₩50,000', U.planNotes(one));
chk('AI 가 준 줄: 딱지 · 안내', U.byLabel(one.by) === '🤖 AI 가 줌' && U.planNotes(one).some(t => t.includes('AI 가 준 점수')));
chk('한 줄: 나눔 안내 없음', !one.split && one.n === 1);

const sp = U.undoPlan(S, 'don_split');
chk('나눠 준 후원: 두 줄 모두(앞사람부터)', eq(sp.lines, ['밍밍 +3점', '하율 +2점']), sp.lines);
chk('나눠 준 후원: 함께 되돌아간다고 적는다', U.planNotes(sp)[0] === '나눠 준 후원이라 함께 되돌아가요: 밍밍 +3점 · 하율 +2점', U.planNotes(sp));
chk('나눠 준 후원: 대기함 안내도', U.planNotes(sp)[1].startsWith('후원은 대기함으로 돌아가요'));
chk('나눠 준 후원: 머리에 외 1줄', U.planTitle(sp) === '21:04 밍밍 +3점 외 1줄(별빛 50,000원)', U.planTitle(sp));

const hand = U.undoPlan(S, 'act_hand');
chk('손으로 준 점수: 점수만 빠진다', eq(U.planNotes(hand), ['점수만 빠져요']) && !hand.isDon, U.planNotes(hand));
const card = U.undoPlan(S, 'dg_1');
chk('게임 카드 기여도: 기여도 줄 · 점수만', eq(card.lines, ['채원 기여도 +3']) && eq(U.planNotes(card), ['점수만 빠져요']), card);

const ex = U.undoPlan({ logs: [{ at, name: '밍밍', val: 2, cval: 2, ref: 'act_x', list: 'extra' }], players: { extra_active: false } }, 'act_x');
chk('끝난 번외 판: 기록만 지워진다고 알린다', ex.staleExtra && U.planNotes(ex)[0].includes('기록만 지워져요'), U.planNotes(ex));

// [끝]으로 본판에 더해진 번외 줄 — 서버가 본판에서 뺀다. '기록만 · 손으로 빼기' 라고 하면 두 번 빠진다
const mg = U.undoPlan({ logs: [{ at, name: '밍밍', val: 2, cval: 2, ref: 'act_m', list: 'extra' }],
    players: { extra_active: false, extra_closed: { '밍밍': 'merged' } } }, 'act_m');
chk('[끝] 번외 판: 본판에서 빠진다고 알린다', !mg.staleExtra && mg.mergedExtra && U.planNotes(mg)[0].includes('본판 점수에서 빠져요')
    && !U.planNotes(mg).join(' ').includes('기록만'), U.planNotes(mg));
const cc = U.undoPlan({ logs: [{ at, name: '밍밍', val: 2, cval: 2, ref: 'don_c', list: 'extra' }],
    players: { extra_active: false, extra_closed: { '밍밍': 'cancelled' } } }, 'don_c');
chk('[취소] 번외 판 후원: 기록만 + 대기함', cc.staleExtra && U.planNotes(cc)[0].includes('기록만') && U.planNotes(cc)[0].includes('대기함'), U.planNotes(cc));
const live = U.undoPlan({ logs: [{ at, name: '밍밍', val: 2, cval: 2, ref: 'act_l', list: 'extra' }], players: { extra_active: true } }, 'act_l');
chk('번외 판 진행 중: 보통 안내', !live.staleExtra && !live.mergedExtra && eq(U.planNotes(live), ['점수만 빠져요']), U.planNotes(live));

const none = U.undoPlan(S, 'don_gone');
chk('없는 ref: 0줄', none.n === 0);
const fb = U.undoPlan(S, 'don_old', [{ at, name: '서아', val: 4, cval: 4, list: 'list', ref: 'don_old' }]);
chk('조각에 없는 오래된 줄: 장부 줄로 적는다', fb.n === 1 && fb.lines[0] === '서아 +4점' && fb.isDon, fb);
chk('자동 딱지', U.byLabel('auto') === '🤖 자동' && U.byLabel('') === '' && U.byLabel(undefined) === '');

console.log('DONE ' + n);
