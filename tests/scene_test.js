/* 🎬 모드별 배치 — 방송판이 모드를 제대로 고르고, 그 모드 자리만 덮어 끼우는가.
 *
 * 대표님 2026-09-22: "룰렛 모드에서 원하는 위치를 저장하고, 시그뒤집기 전용 위치도 저장하고".
 * 편집기에서 모드를 골라 옮긴 위젯은 배치 파일의 __scenes[모드] 에 적히고, 방송판은 그 게임이
 * 떠 있을 때 그 자리를 쓴다.
 *
 * overlay.html 의 layoutSceneOf · layoutWithScene 를 그대로 꺼내 돌린다(베끼지 않는다).
 */
'use strict';
const fs = require('fs');
const path = require('path');
const OK = [], BAD = [];
function chk(name, cond, detail) {
  (cond ? OK : BAD).push(name);
  console.log((cond ? '  [OK] ' : '  [!!] ') + name + (detail !== undefined && detail !== '' ? '  -- ' + String(detail).slice(0, 110) : ''));
}
const OV = fs.readFileSync(path.join(__dirname, '..', 'overlay.html'), 'utf8');
const AD = fs.readFileSync(path.join(__dirname, '..', 'admin.html'), 'utf8');

function cut(src, head) {
  const at = src.indexOf(head);
  if (at < 0) throw new Error('못 찾음: ' + head);
  let i = src.indexOf('{', at), d = 0;
  for (let j = i; j < src.length; j++) {
    if (src[j] === '{') d++;
    else if (src[j] === '}') { d--; if (d === 0) return src.slice(at, j + 1); }
  }
}
const lsAt = OV.indexOf('const LAY_SCENES = ');
const lsLine = OV.slice(lsAt, OV.indexOf(';', lsAt) + 1);
const code = lsLine + '\n' + cut(OV, 'function layoutSceneOf(d)') + '\n' + cut(OV, 'function layoutWithScene(ly, scene)')
  + '\n;({ layoutSceneOf, layoutWithScene })';
const { layoutSceneOf, layoutWithScene } = eval(code);

console.log('='.repeat(74)); console.log('① 지금 모드 고르기'); console.log('='.repeat(74));
chk('아무것도 안 떠 있으면 기본', layoutSceneOf({}) === '');
chk('룰렛', layoutSceneOf({ roulette_enabled: true }) === 'roulette');
chk('시그뒤집기', layoutSceneOf({ siggame: { enabled: true } }) === 'siggame');
chk('주사위', layoutSceneOf({ dicegame: { enabled: true } }) === 'dicegame');
chk('핀볼', layoutSceneOf({ pinball: { enabled: true } }) === 'pinball');
chk('대결', layoutSceneOf({ match_data: { active: true } }) === 'match');
chk('지옥탈출', layoutSceneOf({ hell: { on: true } }) === 'race');
chk('퇴근빵', layoutSceneOf({ home_race_enabled: true }) === 'race');
chk('슬롯은 켜졌다고 적혀 있을 때만(옛 저장본 빈칸은 아님)', layoutSceneOf({ slot_enabled: true }) === 'slot' && layoutSceneOf({}) === '');
chk('룰렛이 시그뒤집기 위에 뜨면 룰렛 모드', layoutSceneOf({ roulette_enabled: true, siggame: { enabled: true } }) === 'roulette');
chk('지옥탈출 중에 룰렛을 돌리면 룰렛 모드', layoutSceneOf({ roulette_enabled: true, hell: { on: true } }) === 'roulette');

console.log(); console.log('='.repeat(74)); console.log('② 그 모드 자리만 덮어 끼운다'); console.log('='.repeat(74));
const ly = { __v: 2, account: { x_px: 6, y_px: 115, scale: 1 }, gauge: { x_px: 1000, y_px: 200, scale: 1 },
             __scenes: { roulette: { account: { x_px: 300, y_px: 1500, scale: 1 } } } };
const r = layoutWithScene(ly, 'roulette');
chk('룰렛 모드면 계좌가 룰렛 자리로', r.account.x_px === 300 && r.account.y_px === 1500);
chk('룰렛 모드에 안 적힌 위젯은 기본 자리 그대로', r.gauge.x_px === 1000);
chk('기본 모드면 그대로', layoutWithScene(ly, '').account.x_px === 6);
chk('저장한 게 없는 모드면 그대로', layoutWithScene(ly, 'siggame').account.x_px === 6);
chk('원본 배치는 안 바뀐다', ly.account.x_px === 6);
chk('판 번호(__v) 는 그대로 넘어간다', r.__v === 2);
chk('이상한 값이 적혀 있어도 안 터진다', layoutWithScene({ __scenes: { roulette: 'x' } }, 'roulette').__scenes.roulette === 'x'
    && layoutWithScene({ __scenes: { roulette: { account: null } } }, 'roulette').account === undefined);

console.log(); console.log('='.repeat(74)); console.log('③ 방송판 · 편집기가 이어져 있는가'); console.log('='.repeat(74));
chk('방송판: 모드가 바뀌면 배치를 다시 먹인다', OV.includes('if (sc !== layScene) { layScene = sc; if (lastLayoutData) applyLayout(lastLayoutData); }'));
chk('방송판: applyLayout 이 모드 자리를 덮어 끼운다', OV.includes('ly = layoutWithScene(ly, layForced !== null ? layForced : layScene);'));
chk('편집기 무대는 편집 중인 모드를 따른다', OV.includes('window.setLayoutSceneForced') && AD.includes('w.setLayoutSceneForced(edScene'));
chk('편집기: 모드 고르는 칸', AD.includes('id="scene-pick"') && AD.includes('window.setScene'));
chk('편집기: 모드 편집 중엔 기본 배치를 안 건드리고 다른 것만 적는다', AD.includes('if (same) delete sc[el.id]; else sc[el.id] = p;'));
chk('편집기: 모드 변수는 var (TDZ 로 편집기가 멈추지 않게)', AD.includes("var edScene = '';"));
const optIds = (AD.match(/<option value="([a-z]+)">/g) || []).map(s => s.slice(15, -2));
const scenes = eval(lsLine.replace('const LAY_SCENES = ', '(').replace(/;$/, ')'));
chk('편집기 모드 목록 = 방송판 모드 목록', scenes.every(s => optIds.includes(s)), optIds.join(','));

console.log('='.repeat(74));
console.log('통과 ' + OK.length + ' · 실패 ' + BAD.length);
BAD.forEach(n => console.log('   [실패] ' + n));
console.log('='.repeat(74));
process.exit(BAD.length ? 1 : 0);
