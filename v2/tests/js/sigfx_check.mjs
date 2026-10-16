// 🎆 방송판 시그니처 연출 규칙 — node 로 순수 함수만 본다(화면 없이). v2/tests/test_sigfx.py 가 부른다.
// 하나라도 틀리면 throw → 종료 코드 1. 끝까지 오면 'ok' 와 본 개수를 찍는다.
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';
import path from 'node:path';

const here = path.dirname(fileURLToPath(import.meta.url));
const web = path.resolve(here, '..', '..', 'web', 'overlay');
const require = createRequire(import.meta.url);

const R = await import(new URL('file://' + path.join(web, 'widgets', 'sigfx', 'rules.js').replace(/\\/g, '/')).href);
const L = await import(new URL('file://' + path.join(web, 'layers.js').replace(/\\/g, '/')).href);
const SigFX = require(path.join(web, 'sigfx', 'sig-fx.js'));

let n = 0;
function eq(a, b, what) {
    n++;
    const A = JSON.stringify(a), B = JSON.stringify(b);
    if (A !== B) throw new Error(what + ' — 기대 ' + B + ' · 실제 ' + A);
}

// 1) 표의 연출 이름이 전부 연출 파일에 있다(17가지 + 진압해 = 18) · 계엄령은 표에 없다
const keys = SigFX.ITEMS.map(i => i.key);
const table = R.SIGFX_BY_AMOUNT;
eq(Object.keys(table).length, 18, '연출 표 18칸(17가지 + 09-23 진압해)');
eq(new Set(Object.values(table)).size, 18, '연출 이름 겹침 없음');
Object.entries(table).forEach(([amt, key]) => eq(keys.includes(key), true, amt + '원 연출 ' + key + ' 이 sig-fx.js 에 있다'));
eq(keys.length, 18, 'sig-fx.js 연출 18가지');
eq(table[250000], undefined, '계엄령(25만)은 표에 없다');
// 연출마다 길이가 있다(play 가 정리 시점을 잡는다)
SigFX.ITEMS.forEach(i => eq(i.dur > 0 && i.cardAt >= 0, true, i.key + ' 길이 · 카드 시점'));

// 2) 시그니처 자신의 값으로 고른다 — 후원 금액이 아니다
eq(R.sigFxKey({ sig_amount: 300000, amount: 260000 }), 'pucha', '30만 시그 = 푸차(후원 26만이어도)');
eq(R.sigFxKey({ sig_amount: 260000, amount: 300000 }), null, '표에 없는 시그 값');
eq(R.sigFxKey({ amount: 300000 }), null, 'sig_amount 없으면 연출 없음');
eq(R.sigFxKey({ sig_amount: '100009' }), 'gazua', '문자 금액도');
eq(R.sigFxKey(null), null, '빈 항목');

// 3) 계엄령 — sig_amount 가 있으면 그것만, 없으면 제목
eq(R.isMartialLaw({ sig_amount: 250000, title: '아무거나' }), true, '25만 시그 = 계엄령');
eq(R.isMartialLaw({ sig_amount: 260000, title: '계엄령' }), false, 'sig_amount 가 있으면 제목은 안 본다');
eq(R.isMartialLaw({ title: ' 계엄령 ' }), true, 'sig_amount 없는 옛 항목은 제목');
eq(R.isMartialLaw({ amount: 250000 }), false, '후원 금액만 25만');

// 4) 가운데 갈래 순서 — 경보 > 전용 연출 > 'OO업'
eq(R.titlePlan({ sig_amount: 250000 }), 'warn', '계엄령 → 경보');
eq(R.titlePlan({ sig_amount: 3000000, source: 'dice' }), 'fx', '주사위로 뽑힌 MVP 도 연출');
eq(R.titlePlan({ sig_amount: 50000, amount: 50000 }), 'banner', '5만 → 배너 갈래');
eq(R.titlePlan({ sig_amount: 250000, skip_popup: true }), 'warn', '슬롯 당첨 계엄령도 경보');

// 5) 'OO업' 글
eq(R.bannerText({ donator: '하늘님', amount: 100000 }, undefined, 100000), '하늘업', '10만 · 님 떼기 · 기본 업');
eq(R.bannerText({ donator: '하늘', amount: 99999 }, '업', 100000), '', '10만 미만은 없음');
eq(R.bannerText({ donator: '하늘', amount: 120000 }, '', 100000), '하늘', '붙는 말을 비우면 이름만');
eq(R.bannerText({ donator: '하늘', amount: 120000 }, ' 최고', 100000), '하늘 최고', '붙는 말 바꾸기');
eq(R.bannerText({ donator: '', amount: 500000 }, '업', 100000), '', '이름 없으면 없음');
eq(R.bannerText({ title: '잭팟', skip_popup: true, amount: 0, donator: '🎰 슬롯머신' }, '업', 100000), '잭팟', '슬롯 당첨 = 시그 이름(금액 상관없음 · 접미사 없음)');
eq(R.bannerText({ source: 'dice', skip_popup: true, banner: '밍밍 · 시그 칸 도착', title: '사쿠란보', amount: 0 }, '업', 100000),
   '밍밍 · 시그 칸 도착', '주사위 = 서버 banner');
eq(R.bannerText({ source: 'dice', skip_popup: true, donator: '밍밍', amount: 0 }, '업', 100000), '밍밍 · 시그 칸 도착', '주사위 banner 없으면 이름으로');
eq(R.bannerAmount({ source: 'dice', amount: 500000 }), 0, '주사위 배너 등급 금액 0');
eq(R.bannerAmount({ amount: '200000' }), 200000, '배너 등급 금액');

// 6) 카드 축소 — 연출이 붙잡고 있으면 끝난 뒤 + 0.12초
eq(R.shrinkWait(2500, 0, 1000), 2500, '연출 없음 → 설정 그대로');
eq(R.shrinkWait(2500, 1000 + 7660, 1000), 7780, 'MVP 7.66초 → 7.78초 뒤');
eq(R.shrinkWait(2500, 1000 + 1960, 1000), 2500, '짧은 연출은 설정이 이긴다');

// 7) 층 표 — 전용 연출은 카드 위, 경보는 그 위. 따로 띄우는 화면의 칸 이름이 표에 있다
const byId = Object.fromEntries(L.LAYERS.map(x => [x.id, x]));
eq(byId.sigfx.z > byId.signature.z, true, '전용 연출(55) > 시그니처 카드(50)');
eq(byId.sigWarn.z > byId.sigfx.z, true, '경보(58) > 전용 연출(55)');
eq(byId.sigfx.z > Math.max(...L.LAYERS.filter(x => x.id.startsWith('fx')).map(x => x.z)), true, '전용 연출 > 조명 · 입자');
eq(new Set(L.LAYERS.map(x => x.z)).has(56) || new Set(L.LAYERS.map(x => x.z)).has(57), false, '56 · 57 은 비워 둔다(옛 이펙트 자리)');
Object.entries(L.VIEWS).forEach(([name, v]) => {
    eq(typeof v.kind === 'string' && v.kind.length > 0, true, name + ' 이름표');
    v.layers.forEach(id => eq(!!byId[id], true, name + ' 화면 칸 ' + id + ' 이 표에 있다'));
});
eq(L.VIEWS.alert.layers.includes('signature') && L.VIEWS.alert.layers.includes('donation'), true, '알림창 = 후원 카드 + 시그니처');
eq(L.VIEWS.sig.layers, ['sigDisp'], '출연진 전광판 = 그림만');
eq(L.VIEWS.slot.layers, ['slot'], '슬롯 화면 = 슬롯만');
eq(L.LAYERS.filter(x => x.viewOnly).map(x => x.id).sort(), ['sigDisp', 'sigUnlock'], '평소 방송판에 없는 칸');

console.log('ok ' + n);
