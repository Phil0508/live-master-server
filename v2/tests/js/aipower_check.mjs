// 🙋 '확인할 후원' 띠 · 🗣️ 말로 조종 카드 — 조종실 실물 파일을 node 로 화면 없이(v2/tests/test_ai_power.py 가 부른다).
// 답: 줄마다 'OK 이름' · 'BAD 이름 -- 까닭', 끝에 'DONE n'
import { fileURLToPath, pathToFileURL } from 'node:url';
import path from 'node:path';

const here = path.dirname(fileURLToPath(import.meta.url));
const js = path.resolve(here, '..', '..', 'web', 'controller', 'js');
const load = p => import(pathToFileURL(path.join(js, p)).href);

const HB = await load('panels/auto/holdband.js');
const CARDS = await load('panels/ai/cards.js');

let n = 0;
function chk(name, cond, detail) {
    n++;
    console.log((cond ? 'OK ' : 'BAD ') + name + (cond ? '' : ' -- ' + JSON.stringify(detail === undefined ? null : detail)));
}
const card = (id, auto, extra) => Object.assign({ id, name: 'n' + id, amount: 15000, auto }, extra || {});
const S = (mode, pending) => ({ autopilot: { mode }, pending });
const held = { hold: ['점수가 딱 떨어지지 않는 금액'], check: ['점수가 딱 떨어지지 않는 금액'], held: 'check' };

chk('보류 카드만 센다', HB.heldCards(S('on', [card('a', held), card('b', { target: '하율', act: true }), card('c', null)])).map(x => x.id).join() === 'a');
chk('판단 중은 안 센다', HB.heldCards(S('on', [card('a', Object.assign({ asking: true }, held))])).length === 0);
chk('자동 진행 끔이면 띠 없음', HB.heldCards(S('off', [card('a', held)])).length === 0);
chk('📚 학습(그림자)에서는 띠 없음 — 사람이 다 정한다(10-22)', HB.heldCards(S('shadow', [card('a', held)])).length === 0);
chk('기여도 카드는 안 센다', HB.heldCards(S('on', [card('a', held, { kind: 'contrib' })])).length === 0);
chk('빈 까닭 목록은 안 센다', HB.heldCards(S('on', [card('a', { hold: [] })])).length === 0);
chk('요약 글자', CARDS.summary({ cards: [{ text: '하율에게 +5점' }, { text: '⚔️ 대결 타이머 시작' }] }) === '하율에게 +5점 · ⚔️ 대결 타이머 시작');
chk('요약 — 카드 없으면 답', CARDS.summary({ cards: [], reply: '누구에게요?' }) === '누구에게요?');
// [실행] 없이 점수 명령이 나가는 길이 없는지 — autoClient 는 BGM(조종실 쪽)만 한다
const res = { cards: [{ type: 'score.add', data: { name: '하율', delta: 5 }, state: 'client' }] };
CARDS.autoClient(res);
chk('autoClient 는 BGM 아닌 것을 실행 못 한다', res.cards[0].state === 'failed', res.cards[0]);
console.log('DONE ' + n);
