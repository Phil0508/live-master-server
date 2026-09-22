# -*- coding: utf-8 -*-
"""🎱 구슬 핀볼 — 만들면서 밟은 것들이 도로 풀리지 않게 못을 박는다.

서버가 없어도 도는 검사다(소스를 읽어 확인한다). 물리가 진짜로 잘 굴러가는지는
브라우저에서 재야 해서 여기서 못 본다 — 대신 **그때 얻은 결론**을 지킨다.

만들면서 실제로 밟은 것 (2026-09-16)
  ① 구슬이 못 위에 얹혀 안 내려왔다. 6개 중 3개가 영영 멈췄다.
     → 속도를 보고 갈수록 세게 미는 '끼임 풀기'를 넣었다.
  ② 레일을 못밭 한가운데 놓았더니 V자 덫이 생겼다. 손으로 세게 밀어도 안 빠졌다.
     → 구역을 나눴다(못밭 / 바람개비 / 레일 / 깔때기가 안 겹치게).
  ③ 공정하지 않았다. 40판에서 3번 자리는 0승, 2·5·6번은 10~11승(기대값 6.7).
     → 출발 자리를 매 판 섞는다. 고친 뒤 120판에서 16~24회(기대값 20)로 고르게 나왔다.
"""
import io
import json, subprocess, tempfile
import os
import re
import sys

sys.stdout.reconfigure(encoding='utf-8')
ROOT = (os.environ.get('LM_PROJECT_ROOT')
        or os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')))

OV = io.open(os.path.join(ROOT, 'overlay.html'), 'rb').read().replace(b'\x00', b'').decode('utf-8')
SRV = io.open(os.path.join(ROOT, 'server.py'), encoding='utf-8', errors='replace').read()
AD = io.open(os.path.join(ROOT, 'admin.html'), encoding='utf-8', errors='replace').read()
CTL = io.open(os.path.join(ROOT, 'controller.html'), encoding='utf-8', errors='replace').read()

ok = bad = 0


def chk(name, cond, extra=''):
    global ok, bad
    if cond:
        ok += 1
        print('  [OK] %s%s' % (name, ('  -- ' + str(extra)) if extra else ''))
    else:
        bad += 1
        print('  [!!] %s%s' % (name, ('  -- ' + str(extra)) if extra else ''))


print('=' * 74)
print('① 화면이 여럿이어도 결과는 하나인가')
print('=' * 74)
# ⚠️ OBS 와 미리보기가 같이 떠 있으면 각자 물리를 굴린다. 둘로 막는다.
chk('서버가 판마다 씨앗을 준다', "'seed'" in SRV and 'random.randint' in SRV)
chk('방송판이 씨앗 난수를 쓴다 (mulberry32)', 'function pbRng(' in OV)

# ⚠️ 여기가 핵심이다. 물리에 Math.random 이 한 번이라도 섞이면 화면마다 다른 경기가 된다.
def _nocomment(t):
    """주석을 걷어낸다 — '쓰지 말 것' 이라고 적어둔 주석이 검사에 걸리면 안 된다."""
    t = re.sub(r'/\*[\s\S]*?\*/', ' ', t)
    return re.sub(r'(?m)^\s*//.*$', ' ', t)


_pb = _nocomment(OV[OV.find('function pbRng('):OV.find('function pbShowWinner(')])
chk('물리에 Math.random 을 안 쓴다 (씨앗만 쓴다)', 'Math.random' not in _pb,
    '섞여 있으면 화면마다 다른 경기가 된다')
chk('끼임 풀기도 씨앗 난수를 쓴다', 'pbRandom' in OV and 'pbRandom()' in OV)

# ⚠️ 그래도 갈릴 수 있다. 그래서 서버가 먼저 온 것 하나만 받는다(룰렛과 같은 문지기).
_res = SRV[SRV.find('def api_pinball_result('):SRV.find('def api_pinball_reset(')]
chk('굴러가는 중일 때만 결과를 받는다', "if not g.get('running')" in _res)
chk('받는 즉시 문을 닫는다 (다음 보고는 409)', "g['running'] = False" in _res)
chk('지난 판의 결과를 가려낸다 (round_id)', 'round_id' in _res and '409' in _res)
chk('방송판은 한 번만 보고한다', 'if (pbReported) return;' in OV)

print()
print('=' * 74)
print('② 방송판이 결과를 보낼 수 있는가')
print('=' * 74)
# ⚠️ 오버레이는 로그인 세션이 없다. 무인증 목록에 없으면 결과가 영영 안 들어온다.
#    (룰렛 /api/roulette/winner 이 같은 이유로 거기 있다)
chk("'/api/pinball/result' 가 무인증 목록에 있다", "'/api/pinball/result'" in SRV)
# ⚠️ 그렇다고 아무나 결과를 심을 수 있으면 안 된다 — 위 ① 의 문지기가 막는다.
chk('시작·명단은 로그인이 필요하다 (목록에 없다)',
    "'/api/pinball/start'" not in SRV.split('method_exempt')[0].split('exempt_routes')[-1])

print()
print('=' * 74)
print('③ 서버가 상태를 지키는가')
print('=' * 74)
_so = re.search(r'SERVER_OWNED = \((.*?)\)', SRV, re.S)
chk('조종실이 통째로 덮어쓰지 못한다', bool(_so) and "'pinball'" in _so.group(1))
_pd = re.search(r'PATCH_DENY = frozenset\(\((.*?)\)\)', SRV, re.S)
chk('설정 패치로도 못 건드린다', bool(_pd) and "'pinball'" in _pd.group(1))
# ⚠️ 게임판 넷은 같은 자리를 쓴다. 빠지면 주사위판 위에 겹쳐 떠서 둘 다 못 읽는다.
chk('다른 게임판과 자리를 다툰다', "'pinball')" in SRV and "_solo_board(state, 'pinball')" in SRV)
chk('옛 저장본에도 칸을 채운다', 'def _pinball_state(' in SRV and 'setdefault' in SRV)
chk('방송 시작·종료 때 걷는다', "_pb.update({'enabled': False, 'running': False" in SRV)
# ⚠️ 이름 수가 아니라 **펼친 구슬 수**로 세야 한다.
#    '밍밍, 양양*2' 는 이름은 둘인데 구슬은 셋이고,
#    거꾸로 '양양' 하나만 있으면 이름은 하나라 막혀야 한다.
chk('구슬이 둘은 돼야 굴린다',
    "if len(_pinball_expand(g['names'])) < 2:" in SRV
    and '구슬이 둘 이상이어야 합니다' in SRV)

print()
print('=' * 74)
print('④ 굴러가다 멈추지 않는가')
print('=' * 74)
# 🩹 2026-09-22 원본과 같은 엔진(box2d)으로 갈아타며 원본(marble.update)의 흔들기를 그대로 쓴다:
#    5초 동안 거의 안 움직이면(한 걸음 이동² < 0.00001) 아무 쪽으로 툭 친다.
chk('끼인 구슬을 흔든다 (원본 흔들기)', 'function pbShake(' in OV and 'pbShake();' in OV)
chk('5초 거의 안 움직이면 (원본 STUCK_DELAY)', 'const PB_STUCK_MS = 5000' in OV and 'dx * dx + dy * dy < 0.00001' in OV)
chk('흔드는 방향도 씨앗 난수', 'pbRandom() * 10 - 5' in OV)
# ⚠️ 그래도 안 끝나면 강제로 끝낸다. 안 그러면 방송이 그 판에 갇힌다.
chk('아무리 오래 걸려도 끝난다', 'PB_MAX_MS' in OV)
# ⚠️ 화면이 드물게 그려지면 따라잡기 한도에 막혀 물리가 굶는다(실측: 8로 뒀더니 14초에 68px).
_g = re.search(r'guard\+\+ < (\d+)', OV)
chk('따라잡기 한도가 넉넉하다', bool(_g) and int(_g.group(1)) >= 16,
    (_g.group(1) + '걸음') if _g else '못 찾음')

print()
print('=' * 74)
print('⑤ 공정한가')
print('=' * 74)
# ⚠️ 코스 생김새 때문에 어떤 자리는 유리하다. 받은 순서대로 세우면 그 유불리가
#    사람에게 고정된다(실측: 3번 자리 0승). 매 판 섞어 아무에게도 안 붙게 한다.
_mk = _nocomment(OV[OV.find('function pbMakeBalls('):OV.find('function pbStop(')])
chk('출발 자리를 섞는다', 'who' in _mk and 'who[i] = who[j]' in _mk)
chk('섞을 때도 씨앗 난수를 쓴다', 'rng()' in _mk and 'Math.random' not in _mk)
# ⚠️ 자리만 섞어선 모자랐다. 물리 엔진은 **먼저 넣은 물체부터** 밀어내기를 푸는데,
#    명단 순서대로 넣으면 그 유불리가 사람에게 고정된다
#    (실측 300판: 명단 첫째·둘째가 62·66승인데 셋째는 37승. 기대값 50).
#    자리 순서로 만들면 유불리가 자리에 붙고, 자리는 매 판 섞인다.
chk('물리에 넣는 순서도 자리 기준이다', 'who.map(function (i, slot)' in _mk)
# 🎲 가져온 맵은 생김새도 출발 자리도 고정이라, 무게를 안 흔들면 **매 판 똑같은 경기**가
#    된다(실측: Wheel of fortune 이 24판 내내 5.4초). 원본도 구슬 무게를 1～2배로 흔든다.
chk('구슬 무게를 매 판 다르게 준다 (원본: 1~2배)', 'body.CreateFixture(cs, 1 + rng())' in _mk)

print()
print('=' * 74)
print('⑥ 편집기·조종실에 제대로 붙었는가')
print('=' * 74)
# ⚠️ 셋이 한 벌이다. 하나라도 빠지면 조용히 어긋난다.
_lay = re.search(r'const LAY_IDS = \[([\s\S]*?)\];', OV)
chk('방송이 자리를 읽는다 (LAY_IDS)', bool(_lay) and "'pinball'" in _lay.group(1))
chk('편집기 목록에 있다 (widgetNames)', "'pinball':" in AD)
chk('편집기에서 끌 수 있다 (손잡이)', 'class="widget" id="pinball"' in AD)
# ⚠️ widgetNames 를 빠뜨리면 목록에 안 뜰 뿐 아니라 display 를 켜주는 코드가 이 사전을
#    훑으므로 영영 안 보인다 — 모금함이 그랬다(2026-09-15).
_m = re.search(r'<div class="widget" id="pinball"[^>]*style="left:(\d+)px; top:(\d+)px', AD)
_o = re.search(r'id="pinball-container"[^>]*style="[^"]*left: (\d+)px; top: (\d+)px', OV)
chk('편집기와 방송판의 기본 자리가 같다',
    bool(_m) and bool(_o) and _m.groups() == _o.groups(),
    ('편집기 %s / 방송판 %s' % (_m.groups() if _m else '?', _o.groups() if _o else '?')))

chk('조종실에 탭이 있다', 'tab-pinball' in CTL)
chk('조종실이 전용 주소로만 부른다', "'/api/pinball/' + path" in CTL)
chk('주기 갱신에 물려 있다', 'pbcSync()' in CTL)
# ⚠️ 조종실에는 escText 가 없다(escapeHTML 이다). 만들 때 실제로 이걸로 한 번 깨졌다.
chk('이름을 안전하게 넣는다', 'escText(' not in CTL)
# ⚠️ 1초마다 다시 그리므로, 치는 중에 덮으면 글자가 사라진다(진행봇 주소 칸과 같은 이유).
chk('치는 중에 명단을 안 덮어쓴다', 'document.activeElement !== t' in CTL)

print()
print('=' * 74)
print('⑦ 판을 고를 수 있는가')
print('=' * 74)
"""🗺️ 판 넷은 원본(lazygyu/roulette, MIT)에서 가져왔다. 우리 물리(matter.js)는
   원본(box2d)과 달라 **맵마다 걸리는 시간이 크게 다르다** — 실측 3~48초, 한 판은
   가끔 안 끝난다. 그래서 씨앗으로 정하지 않고 **사람이 고른다.**
   ⚠️ 화면이 여럿이어도 같은 판을 봐야 하므로 서버 상태에 적는다(씨앗과 같은 이유)."""
chk('서버 상태에 고른 판이 있다', '"map": -1' in SRV)
chk('범위를 벗어난 값은 우리 코스로 떨어진다', 'def _pinball_map(' in SRV and 'PINBALL_MAPS' in SRV)
chk('시작할 때도 판을 받는다', "g['map'] = _pinball_map(body.get('map'))" in SRV)
chk('방송판이 고른 판을 쓴다 (씨앗으로 안 정한다)',
    'function pbStart(names, seed, mapIdx' in OV and 'mapIdx >= 0' in OV)
# ⚠️ 맵 파일을 못 읽었거나 -1 이면 우리 코스로 굴러야 한다. 방송이 빈 화면이 되면 안 된다.
chk('판을 못 쓰면 우리 코스로 굴린다', 'if (!st) st = pbStageOwn(rng);' in OV)
chk('조종실에 고르는 칸이 있다', 'id="pb-map"' in CTL and 'pbcSetMap' in CTL)
# ⚠️ 목록에 걸리는 시간을 적어 둔다. 모르고 고르면 방송 흐름이 끊긴다.
#    규칙마다 크게 다르므로 둘 다 적는다(실측 400판 중앙값).
chk('걸리는 시간을 규칙별로 적어 뒀다',
    CTL.count('먼저 ') >= 5 and CTL.count('끝까지 ') >= 5)

_mj2 = os.path.join(ROOT, 'vendor', 'pinball-maps.js')
chk('맵 파일이 있다', os.path.exists(_mj2),
    ('%dKB' % (os.path.getsize(_mj2) // 1024)) if os.path.exists(_mj2) else '없음')
if os.path.exists(_mj2):
    _mh = io.open(_mj2, encoding='utf-8', errors='replace').read(2000)
    # ⚠️ MIT 조건이다. 지우면 라이선스 위반이다.
    chk('원저작권 표기를 남겼다', 'Copyright (c) 2022 LazyGyu' in _mh and 'MIT License' in _mh)
    chk('출처를 적어 뒀다', 'lazygyu/roulette' in _mh)
# ⚠️ 'Marble Roulette / 마블 룰렛' 은 원저자의 상표다. 우리 이름으로 쓰면 안 된다.
chk('상표를 우리 이름으로 안 쓴다',
    '마블 룰렛' not in CTL and '마블 룰렛' not in OV and 'Marble Roulette' not in CTL)
# 🔴 구슬 크기는 **원본이 못박아 둔 0.25 미터**를 따른다(physics-box2d: set_m_radius(0.25)).
#    ⚠️ 예전에 0.17 로 줄였다가 "공이 너무 작다"는 말을 들었다. 줄이면 못 사이는 잘 빠지지만
#       원본이 의도한 판이 아니게 된다. 끼는 건 크기가 아니라 pbShake 로 푼다.
chk('구슬 크기가 원본과 같다 (0.25m)', 'pbR = 0.25 * pbSC;' in OV)

print()
print('=' * 74)
print('⑧ 가져온 판을 원본과 똑같이 짓는가')
print('=' * 74)
"""🗺️ 원본 맵을 옮길 때 네 군데서 틀렸었다. 전부 실측으로 드러난 것이라
   하나씩 못을 박아 둔다 — 다시 틀리면 판이 통째로 이상해진다."""

_bm = _nocomment(OV[OV.find('function pbBuildStage('):OV.find('function pbStageFromMap(')])
# 2026-09-22 부터 원본과 **같은 엔진(box2d)** 이다. 원본 physics-box2d.createEntities 를 그대로 옮긴다.
# ⚠️ box2d 의 SetAsBox 는 **반너비·반높이**를 받는다 — 원본 값 그대로 넣는다(matter 때는 두 배로 넣었다).
chk('상자는 반너비 그대로 넣는다 (SetAsBox)', 's.SetAsBox(sh.width || .1, sh.height || .1, c, sh.rotation || 0)' in _bm)
# ⚠️ rotation 은 숫자가 30·45·90 이라 도처럼 보이지만 **라디안 그대로** 쓴다.
chk('각도를 라디안 그대로 쓴다', 'Math.PI / 180' not in _bm)
chk('꺾은선은 두께 0 선으로 — 원본과 같다', 'edge.SetTwoSided(v1, v2)' in _bm)
# 💥 원본은 life 가 있는 물체를 구슬이 닿는 순간 없앤다(physics-box2d.step).
#    단단하게 깔았더니 Yoru ni Kakeru 는 구슬이 120초를 갇혔었다.
chk('닿으면 깨지는 물체를 표시한다', 'pop: (Number(pr.life) || 0) > 0' in _bm)
chk('깨진 것을 걸음이 끝난 뒤 치운다', 'function pbPopCheck(' in OV and 'pbPopCheck();' in OV)
chk('닿아 있는지 본다 (원본 IsTouching)', 'c.IsTouching()' in OV)
chk('중력값이 원본과 같다 (10 m/s²)', 'const PB_G_MPS2 = 10' in OV and 'new B.b2World(pbVec(0, PB_G_MPS2))' in OV)
chk('도는 장애물은 box2d 가 돌린다 (kinematic)', 'B.b2_kinematicBody' in _bm and 'body.SetAngularVelocity(' in _bm)
# 🚿 원본 맵은 꼭대기가 좁은 통로다 — 원본과 같은 자리에서 떨어뜨린다.
chk('원본과 같은 자리에서 떨어뜨린다', 'mx = 10.25 + (slot % 10) * 0.6' in OV)
chk('가져온 맵이면 통로 자리를 쓴다', 'if (pbSpawn) {' in OV)

print()
print('=' * 74)
print('⑨ 이기는 규칙을 고를 수 있는가')
print('=' * 74)
"""🏆 먼저 골인 / 끝까지 남기. 원본의 winnerRange 를 두 가지로 줄여 옮긴 것이다.
   ⚠️ 규칙이 도착 순서의 **어느 쪽 끝**을 우승자로 읽을지를 정한다. 여기가 어긋나면
      진 사람을 우승자로 발표한다 — 방송에서 절대 나면 안 되는 사고다."""
chk('서버가 규칙을 들고 있다', '"rule": "first"' in SRV)
chk('모르는 값은 먼저 골인으로 떨어진다',
    'def _pinball_rule(' in SRV and "PINBALL_RULES = ('first', 'last')" in SRV)
chk('시작할 때도 규칙을 받는다', "g['rule'] = _pinball_rule(body.get('rule'))" in SRV)
chk('방송판이 서버 규칙을 읽는다', "pbRule = (g.rule === 'last') ? 'last' : 'first';" in OV)
chk('끝까지 남기면 마지막 사람이 우승이다',
    'function pbWinnersOf(' in OV and 'order.slice(order.length - k).reverse()' in OV)
chk('조종실에 규칙 고르는 칸이 있다', 'id="pb-rule"' in CTL and 'pbcSetRule' in CTL)
chk('고른 규칙을 되비춘다', "g.rule === 'last'" in CTL)

# ⚠️ 필요한 등수까지만 나오면 끝이다(원본도 같다). 안 그러면 뒤처진 구슬을 하염없이 기다린다.
chk('승부가 갈리면 일찍 끝낸다',
    "const decided = (pbRule === 'last') ? (left <= 1) : (pbFinish.length >= pbPicks);" in OV)
# ⚠️ 갈린 즉시 끊지 않는다 — 들어가는 장면은 보여줘야 한다.
chk('끝나는 장면을 잠깐 보여준다', 'now - pbOverAt > 700' in OV)

print()
print('=' * 74)
print('⑩ 카메라가 주인공을 따라가는가')
print('=' * 74)
"""🎥 원본은 판 전체를 멀리서 보여주지 않는다. **주인공 구슬**을 쫓아가며 결승선 앞에서
   확 당기고 느려진다. 우리는 멀리서 내려다보기만 해서 "공이 너무 작다"는 말을 들었다."""
# ⚠️ 원본의 targetIndex = 당첨등수 - 골인한수. 이 한 줄로 규칙이 바뀌면 주인공도 바뀐다.
chk('규칙에 따라 주인공이 바뀐다',
    'function pbTargetIdx(' in OV
    and "(pbRule === 'last') ? (pbBalls.length - 1) : (pbPicks - 1)" in OV)
chk('결승선 앞에서 확대한다', 'PB_ZOOM_MAX' in OV and 'PB_ZOOM_TH' in OV)
chk('결승선 앞에서 느려진다', 'function pbSlowFactor(' in OV and 'PB_SLOW_MIN' in OV)
# ⚠️ 슬로모션이 물리 걸음의 **크기**를 바꾸면 화면마다 결과가 갈릴 수 있다.
#    걸음은 그대로 두고 띄엄띄엄 민다.
chk('슬로모션이 물리 걸음 크기를 안 바꾼다',
    'pbWorld.Step(PB_STEP / 1000, 6, 2)' in OV and 'pbAcc += dt * pbSlowFactor();' in OV)
# ⚠️ 확대하면 글씨·테두리도 같이 커져 구슬을 덮는다. 화면 기준 굵기를 지켜야 한다.
chk('글씨 굵기가 확대에 안 딸려간다', '(19 / Z).toFixed(2)' in OV)

print()
print('=' * 74)
print('⑪ 어떤 판이든 반드시 끝나는가')
print('=' * 74)
"""🚨 방송이 한 판에 갇히면 안 된다. 실측에서 Pot of greed · 끝까지 남기 는
   아무도 못 나아간 채 215초를 버틴 판이 있었다."""
chk('아무도 못 나아가면 그 자리 순위로 끝낸다',
    'function pbStallWatch(' in OV and 'const stalled = pbStall > PB_STALL_STEPS' in OV)
# ⚠️ 구슬 **저마다의** 최고 깊이로 봐야 한다. 전체 최고값으로 보면 앞선 구슬이 골인해
#    사라진 뒤로는 값이 안 늘어 늘 '정체'로 읽힌다.
chk('구슬마다 따로 잰다', 'b.pbTop === undefined' in OV)
# ⚠️ 정상 판의 최장 정체는 7초였다. 20초면 멀쩡한 판은 안 끊는다(한 걸음 10ms).
chk('정상 판을 끊지 않을 만큼 넉넉하다', 'const PB_STALL_STEPS = 100 * 20;' in OV)
chk('걸음 수 상한도 있다', 'PB_MAX_STEPS' in OV)

print()
print('=' * 74)
print('⑫ 원본에서 더 가져온 것들')
print('=' * 74)
"""📦 원본(lazygyu/roulette)을 끝까지 훑어 쓸모 있는 것만 골라 넣었다.
   광고·영상녹화·미니맵·구슬 사진은 일부러 안 가져왔다."""

# 🎱 양양*3 — 많이 후원한 분에게 표를 더 주는 쓰임이다.
#    ⚠️ 펼치는 곳은 **서버 한 군데뿐**이어야 한다. 방송판과 서버가 따로 세면
#       조종실에 보이는 개수와 실제 구슬 수가 어긋난다.
chk('여러 번 참가를 펼친다 (양양*3)', 'def _pinball_expand(' in SRV)
chk('펼치는 곳은 저장할 때 한 군데뿐',
    "g['balls'] = _pinball_expand(g.get('names'))" in SRV
    and SRV.count('_pinball_expand(g') <= 2)
chk('한 사람이 무한히 넣지 못한다', 'PINBALL_COUNT_MAX' in SRV)
chk('방송판은 펼친 목록을 굴린다', '(g.balls && g.balls.length) ? g.balls' in OV)
chk('조종실이 *3 을 알려준다', '*3' in CTL)

# 🏅 여러 명 뽑기 — 원본의 winnerRange 를 옮긴 것이다.
# ⚠️ 사람 수만큼 다 뽑으면 경기가 아니다. 최소 한 명은 남긴다.
chk('몇 명 뽑을지 서버가 들고 있다', '"picks": 1' in SRV and 'def _pinball_picks(' in SRV)
chk('다 뽑아버리지 못한다', 'hi = max(1, int(total) - 1)' in SRV)
chk('조종실에 뽑는 칸이 있다', 'id="pb-picks"' in CTL and 'pbcSetPicks' in CTL)

# 🔍 출발 순간에는 더 당긴다 — 안 그러면 이름이 서로 겹쳐 안 읽힌다.
chk('출발 때 당겨 보여준다', 'const PB_ZOOM_START = 3;' in OV and 'PB_ZOOM_START,' in OV)
# ⚠️ 우리 코스는 판이 화면 폭 전체라, 가장자리에 뿌리면 출발 순간 화면 밖에 있다.
chk('우리 코스도 화면 안에서 출발한다', 'const PB_SPAWN_BAND = PB_W - 320;' in OV)

# 🎉 우승 폭죽 — 원본도 당첨자가 나오면 입자를 쏴다.
# ⚠️ 폭죽은 방송판에 이미 들어 있는 것을 쓴다(새로 받아오지 않는다).
chk('우승 폭죽을 터트린다', 'function pbBoom(' in OV and 'pbBoom();' in OV)
chk('폭죽이 없어도 판은 끝난다', "typeof confetti !== 'function'" in OV)
# ⚠️ 폭죽은 화면 전체 좌표를 쓴다. 위젯 자리를 재서 그 한가운데에서 터져야 한다.
chk('폭죽이 위젯 자리를 따라간다', "getElementById('pinball-container')" in OV
    and 'getBoundingClientRect()' in OV)

# 💢 밀어내기 — 원본의 Impact 스킬.
# ⚠️ 원본은 Math.random 을 쓴다. 그대로 가져오면 화면마다 다른 경기가 된다.
_sk = _nocomment(OV[OV.find('function pbImpact('):OV.find('function pbStallWatch(')])
chk('밀어내기가 있다', 'function pbImpact(' in OV and 'function pbSkills(' in OV)
chk('밀어내기도 씨앗 난수를 쓴다', 'pbRandom()' in _sk and 'Math.random' not in _sk)
chk('범위·세기가 원본과 같다 (10m · 0.81×5)', 'PB_SKILL_R_M * PB_SKILL_R_M' in OV and 'const k = 0.81 * 5;' in OV)
# ⚠️ 상금이 걸린 추첨이면 꺼야 한다.
chk('조종실에서 끌 수 있다', 'id="pb-skills"' in CTL and '"skills": True' in SRV)
chk('옆 구슬이 어디서 시작하든 어긋나게 굴린다', 'pbCool: 1 + Math.floor(rng() * PB_SKILL_COOL)' in OV)

print()
print('=' * 74)
print('⑬ 실전에서 나온 세 가지 (2026-09-16)')
print('=' * 74)
"""대표님 실전 테스트: ① 벽을 뻐고 밖으로 튵겨나감 ② 줌될 때 프레임이 떨어짐
   ③ 카메라가 엉뛱한 구슬을 따라감. 세 개 다 재현해서 고쳤다."""

# 🚧 벽 뚫기 — matter 때 실전에서 벽을 뚫고 튕겨 나갔다. 2026-09-22 원본과 같은 box2d 로 갈아탔다.
#    box2d 는 연속 충돌 검사가 기본이라 안 뚫는다. 옛 대책(속도 상한 · 조각내기 · 훑기)은 걷었다 —
#    구슬이 '턱' 멈칫하던 원인이었다(대표님: "부드럽지 않게 흘러간다").
chk('원본과 같은 엔진(box2d)', 'new B.b2World(' in OV and 'Matter.' not in OV)
chk('옛 뚫림 대책을 걷었다', 'function pbSweep(' not in OV and 'function pbCapSpeed(' not in OV and 'PB_SUB' not in OV)
chk('원본과 같은 걸음 (10ms · 6/2)', 'const PB_STEP = 10;' in OV and 'pbWorld.Step(PB_STEP / 1000, 6, 2)' in OV)
chk('손으로 빼내는 장치는 안 쓴다', 'function pbEject(' not in OV and 'pbEject();' not in OV)

# 🎬 끊김 — 슬로모션은 걸음을 건너뛰어 만든다. 0.25배면 4프레임에 한 번만 움직여 뛝뛝 끊겼다.
#    물리는 그대로 두고 **그림만** 사이를 채운다 — 결과는 한 치도 안 바뀜다.
chk('그릴 때 걸음 사이를 채운다 (보간)', 'function pbPos(' in OV and 'b.pbPx = b.position.x' in OV and 'pbAlpha = pbAcc / PB_STEP;' in OV)
chk('구슬과 카메라 모두 보간된 자리를 쓴다', OV.count('pbPos(') >= 3)
_pos = _nocomment(OV[OV.find('function pbPos('):OV.find('function pbTarget(')])
chk('보간은 물리를 안 건드린다', 'SetTransform' not in _pos and 'SetLinearVelocity' not in _pos)
# ⚠️ 그림자 번짐은 확대를 그대로 타서 3배면 48px — 비싸고 번들거린다.
chk('그림자 번짐이 확대에 안 따라간다', '(16 + hit * 26) / Z' in OV)

# 🎯 카메라 — 비슷한 자리의 구슬 둘이 매 프레임 순위를 주고받으면 카메라도 오간다.
chk('주인공을 뚌 들여 바꾼다', 'function pbTarget(' in OV and 'PB_TGT_HOLD' in OV)
chk('주인공이 골인하면 바로 바꾼다', 'pbTgt.pbDone || act.indexOf(pbTgt) < 0' in OV)
chk('카메라·슬로모션·표시가 같은 주인공을 본다',
    'const t = pbTarget();' in OV and 'const t = pbTgt;' in OV and 'const tgt = pbTgt;' in OV)
# ⚠️ pbLoop 과 검사 도구가 같은 걸음 함수를 써야 한다. 도구가 루프를 베껴 쓰다 한 줄을
#    빠뜨려 "고쳐도 안 고쳐진다"고 잘못 읽은 적이 있다.
chk('물리 한 걸음이 함수 하나다', 'function pbStepOnce(' in OV and 'pbStepOnce();' in OV
    and 'pbWorld.Step(' not in _nocomment(OV[OV.find('function pbLoop('):OV.find('function pbCamera(')]))

print()
print('=' * 74)
print('⑭ 물리 엔진을 우리 서버에서 내보내는가')
print('=' * 74)
# ⚠️ 외부 CDN 을 부르면 방송 중 그쪽이 막히는 순간 게임이 통째로 안 뜬다.
#    컨페티를 vendor 에 둔 것과 같은 이유다.
chk('vendor 에서 부른다', '/vendor/box2d/Box2D.js' in OV and "return '/vendor/box2d/' + f;" in OV)
chk('바깥 주소를 안 부른다', 'cdnjs' not in OV.split('<style>')[0] and 'unpkg' not in OV)
_bj = os.path.join(ROOT, 'vendor', 'box2d', 'Box2D.js')
_bw = os.path.join(ROOT, 'vendor', 'box2d', 'Box2D.wasm')
chk('파일이 실제로 있다', os.path.exists(_bj) and os.path.exists(_bw),
    ('%dKB + %dKB' % (os.path.getsize(_bj) // 1024, os.path.getsize(_bw) // 1024))
    if os.path.exists(_bj) and os.path.exists(_bw) else '없음')
_lz = os.path.join(ROOT, 'vendor', 'box2d', 'LICENSE.zlib.txt')
chk('라이선스(Zlib) 표기를 같이 둔다', os.path.exists(_lz)
    and 'zlib' in io.open(_lz, encoding='utf-8', errors='replace').read().lower())
# ⚠️ .wasm 은 방송판(OBS)이 로그인 없이 받아야 하고, 종류(application/wasm)가 맞아야 한다.
#    안 그러면 핀볼만 조용히 안 뜬다.
chk('.wasm 을 로그인 없이 내보낸다', SRV.count("'.wasm'") >= 2 and "'application/wasm'" in SRV)
chk('없어도 방송은 계속된다', 'function pbHasEngine(' in OV and '!pbHasEngine()' in OV)

print()
print('=' * 74)
print('⑮ 없는 함수를 부르지 않는가')
print('=' * 74)
# ⚠️ 실제로 당했다 — pbShowWinner 가 escText 를 불렀는데 방송판엔 그 함수가 없다.
#    우승 딱지를 띄우려는 순간마다 ReferenceError 로 터져서 딱지가 영영 안 떴다.
#    문법 검사로는 안 잡힌다(부를 때가 돼야 터지므로). 방송판은 첫 화면이라
#    여기서 터지면 대표님이 방송 중에 알게 된다.
#    내가 만든 시험 페이지가 escText 를 자체 정의해 두어 더 오래 가려져 있었다.
_pbblk = _nocomment(OV[OV.find('const PB_W = 980'):OV.find('let dgLastG = null;')])
_calls = set(re.findall(r'(?<![.\w])([A-Za-z_$][\w$]*)\s*\(', _pbblk))
_BUILTIN = set([
    'if', 'for', 'while', 'switch', 'catch', 'function', 'return', 'typeof', 'new',
    'delete', 'void', 'in', 'instanceof', 'parseInt', 'parseFloat', 'isFinite', 'isNaN',
    'encodeURIComponent', 'decodeURIComponent', 'setTimeout', 'clearTimeout',
    'setInterval', 'clearInterval', 'requestAnimationFrame', 'cancelAnimationFrame',
    'fetch', 'alert',
    'rgba',            # CSS 글자 안의 rgba( — 함수가 아니다
])
# vendor 가 실어오는 전역 — 없을 때 대비가 있어야 통과시킨다
_VENDOR = {'confetti': "typeof confetti !== 'function'", 'Box2D': "typeof Box2D === 'function'"}
_missing = []
for _c in sorted(_calls):
    if _c in _BUILTIN or _c.startswith('pb'):
        continue
    if _c in _VENDOR:
        if _VENDOR[_c] not in OV:
            _missing.append(_c + '(없을 때 대비 없음)')
        continue
    if _c[:1].isupper():          # Matter·Math·JSON 같은 객체 — 위에서 걸렀다
        continue
    if (re.search(r'function\s+' + re.escape(_c) + r'\s*\(', OV)
            or re.search(r'(?:const|let|var)\s+' + re.escape(_c) + r'\s*=', OV)):
        continue
    _missing.append(_c)
chk('핀볼이 부르는 함수가 모두 있다', not _missing,
    ('없는 함수: ' + ', '.join(_missing)) if _missing else ('%d개 확인' % len(_calls)))
# ⚠️ 방송판의 이스케이프 함수는 escapeSlotText 다. escText 는 어디에도 없다(조종실은 escapeHTML).
chk('이름을 방송판의 함수로 안전하게 넣는다',
    'escapeSlotText(n)' in OV and 'escText(' not in OV)   # 주석에 남긴 기록은 통과시킨다

print()
print('=' * 74)
print('🚫 뺀 맵을 못 고르게 막는가')
print('=' * 74)
# ⚠️ Pot of greed(2번) 는 항아리에 구슬이 갇혀 25판 중 16판이 중간에 멎었다.
#    속도 상한·되돌림을 달리 해도 그대로여서 조율로는 못 고친다. 대표님이 빼라고 했다(2026-09-16).
chk('막을 맵 목록이 있다', 'PINBALL_BLOCKED = (2,)' in SRV)
# ⚠️ 조종실 목록에서 빼는 것만으로는 옛 저장본·손으로 보낸 요청을 못 막는다.
chk('서버가 거절한다', 'if v in PINBALL_BLOCKED:' in SRV)
chk('옛 저장본도 스스로 고쳐진다', "g['map'] = _pinball_map(g.get('map'))" in SRV)
# ⚠️ CTL 전체에서 value="2" 를 찾으면 주사위 개수 칸에 걸린다. 핀볼 목록만 본다.
_mapsel = re.search(r'<select id="pb-map".*?</select>', CTL, re.S)
chk('조종실 목록에 없다', bool(_mapsel) and 'value="2"' not in _mapsel.group(0)
    and 'Pot of greed' not in _mapsel.group(0),
    ('고를 수 있는 판 %d개' % _mapsel.group(0).count('<option')) if _mapsel else '목록 없음')
# ⚠️ 맵 데이터는 지우지 않는다 — 배열에서 빼면 뒤 맵 번호가 밀려(3 Yoru → 2)
#    저장된 3 이 어느 날 딴 맵을 가리킨다. 번호는 고정하고 '못 고르게'만 막는다.
chk('맵 개수는 그대로다 (번호 안 밀린다)', 'PINBALL_MAPS = 4' in SRV)
chk('조종실 이름표도 번호를 지킨다', "'BubblePop', null, 'Yoru ni Kakeru'" in CTL)

print()
print('=' * 74)
print('⓷ 구슬 200개까지 받는가')
print('=' * 74)
# 🎱 대표님: "최대 200개로 늘려줘" (2026-09-16).
#    ⚠️ 숫자만 올리면 **우리 코스가 안 끝난다.** 아래 셋이 같이 지켜져야 한다.
_mx = re.search(r'^PINBALL_MAX = (\d+)', SRV, re.M)
chk('서버 상한이 200이다', bool(_mx) and int(_mx.group(1)) == 200,
    ('PINBALL_MAX = %s' % (_mx.group(1) if _mx else '?')))
# ⚠️ 한 사람 상한을 낮게 두면 '양양*50' 같은 정당한 쓰임까지 막힌다.
chk('한 사람 상한도 전체와 같다', 'PINBALL_COUNT_MAX = PINBALL_MAX' in SRV)
# ⚠️ 방송판이 이 숫자로 출발 줄 수와 뚜껑 높이를 정한다. 어긋나면 윗줄 구슬이
#    뚜껑 위에서 시작해 영영 못 내려온다 — 실측으로 '끝까지 남기' 6판 전부 못 끝냈다.
_bx = re.search(r'const PB_BALL_MAX = (\d+);', OV)
chk('방송판 상한이 서버와 같다',
    bool(_bx) and bool(_mx) and int(_bx.group(1)) == int(_mx.group(1)),
    ('방송판 %s · 서버 %s' % (_bx.group(1) if _bx else '?', _mx.group(1) if _mx else '?')))

# 🚿 출발 자리 — 한 줄에 몇 개가 들어가는지부터 센다.
#    ⚠️ 예전엔 '몇 개든 한 줄에 다 뿌리고 8개마다 줄 바꾸기' 였다. 200개면 옆 칸이
#       3px 라 구슬이 통째로 겹쳐 서로를 밀어내며 튀었다.
chk('한 줄에 들어갈 개수를 센다', 'const PB_SPAWN_PER = Math.max(1, Math.floor(' in OV)
chk('구슬 지름보다 넓게 벌린다', 'const PB_SPAWN_GAP = PB_R * 2 + 6;' in OV)
chk('넘치면 줄을 쌓는다', 'Math.floor(slot / per) * PB_SPAWN_ROWH' in OV)
chk('한 줄에 다 들어가면 예전 자리 그대로', 'const per = Math.min(n, PB_SPAWN_PER);' in OV)
# 🧢 뚜껑 — 이게 이번 고침의 핵심이다.
chk('뚜껑을 제일 윗줄 위로 올렸다', 'const PB_CEIL = PB_SPAWN_Y0' in OV)
chk('뚜껑이 y=-7 에 붙어 있지 않다',
    'box(PB_W / 2, PB_CEIL - PB_WALL / 2' in OV
    and 'box(PB_W / 2, -PB_WALL / 2' not in OV)

# 🧮 실제로 계산해 본다 — 상수를 고쳤을 때 조용히 어긋나지 않게.
_num = lambda k: int(re.search(r'const %s = (\d+)' % k, OV).group(1))
try:
    _W = _num('PB_W'); _R = _num('PB_R'); _MAXB = _num('PB_BALL_MAX')
    _band = _W - 320; _gap = _R * 2 + 6; _rowh = _R * 2 + 16
    _per = max(1, _band // _gap)
    _rows = -(-_MAXB // _per)                       # 올림
    _ceil = 40 - (_rows - 1) * _rowh - 60
    _top = 40 - (_rows - 1) * _rowh                 # 제일 윗줄
    chk('제일 윗줄이 뚜껑보다 아래에 있다', _ceil < _top - _R,
        '윗줄 y=%d · 뚜껑 y=%d · 한 줄 %d개 · %d줄' % (_top, _ceil, _per, _rows))
    # ⚠️ 옆벽은 y = -PB_WORLD/2 까지만 내려온다. 뚜껑이 그보다 위면 구슬이 옆으로 샌다.
    _world = 140 + 620 * 3 + 200
    chk('쌓은 구슬이 옆벽 안에 있다', _ceil > -_world / 2,
        '뚜껑 y=%d · 옆벽 위끝 y=%d' % (_ceil, -_world // 2))
except Exception as _e:
    chk('출발 자리 셈이 맞는가', False, str(_e))

# 🏷️ 이름 — 200개면 글자가 겹쳐 더미가 된다. 접고, 주인공만 남긴다.
chk('많으면 구슬 밑 이름을 접는다',
    'const PB_NAME_MAX = 40;' in OV
    and 'pbBalls.length > PB_NAME_MAX && b !== tgt' in OV)
# 🏆 많이 뽑으면 딱지가 화면을 넘친다.
chk('딱지에 쓰는 이름 수를 막았다',
    'const PB_BANNER_MAX = 8;' in OV and 'list.slice(0, PB_BANNER_MAX)' in OV)
chk('나머지는 수로 알린다', "' \uc678 ' + rest + '\uba85'" in OV)
# ⚠️ 줄이기만으로는 모자랐다 — 20명 뽑기 실측에서 딱지가 **판 밖으로** 삐져나왔다
#    (캔버스는 980px 인데 nowrap 에 폭 제한이 없어 화면 끝까지 늘어났다).
_win = re.search(r'\.pb-winner \{.*?\}', OV, re.S)
chk('딱지 폭을 판 안으로 가둔다',
    bool(_win) and 'max-width:' in _win.group(0) and 'white-space: nowrap' not in _win.group(0))
chk('이름 가운데서 안 끊는다', bool(_win) and 'word-break: keep-all' in _win.group(0))
chk('여럿일 때 글자를 줄인다',
    '.pb-winner.many {' in OV and "el.classList.toggle('many', list.length > 1)" in OV)
# 🎛️ 조종실
chk('뽑는 수를 199까지 받는다', 'id="pb-picks" type="number" min="1" max="199"' in CTL)
chk('조종실이 200개라고 알려준다', '200\uac1c</b>\uae4c\uc9c0' in CTL)
chk('이름이 안 붙는다는 것도 알려준다', '40\uac1c\ub97c \ub118\uc73c\uba74' in CTL)

print()
print('=' * 74)
print('\u24f8 끝까지 남기 — 진짜 1등을 고르는가')
print('=' * 74)
# ⚠️ result 는 **도착 순서**다(먼저 떨어진 사람이 앞). '끝까지 남기' 면 거기서
#    제일 뒤가 1등이다. 예전에는 서버 기록도 조종실도 규칙을 안 보고 result[0] 을
#    1등이라 적었다 — 정확히 **반대 사람**이 나갔다. 방송판만 제대로 세고 있었다.
chk('서버가 규칙대로 당첨자를 고른다', 'def _pinball_winners(' in SRV)
chk('저장할 때 한 군데에서 센다',
    "g['winners'] = _pinball_winners(g.get('result')" in SRV)
chk('기록에 result[0] 을 안 쓴다',
    '"\U0001F3B1 핀볼 1등: %s" % _top' in SRV and '% order[0]' not in SRV)
chk('조종실이 서버가 고른 당첨자를 읽는다', 'g.winners && g.winners.length' in CTL)
# ⚠️ 옷 저장본에는 winners 칸이 없다. 올리고 나서 판을 한 번 굴리기 전까지
#    조종실이 옷 방식으로 보여준다 — 그 한 판 동안 거짓말을 한다. 읽을 때 채운다.
chk('옷 저장본은 읽을 때 보정한다',
    '_pb0["winners"] = _pinball_winners(' in SRV)
# ⚠️ 모금함·진행봇과 같은 이유 — 칸이 아예 없으면 기본값 **객체를 그대로** 물어
#    거기에 명단을 적으면 다음 방송이 남의 명단을 물고 시작한다.
chk('기본값 객체를 그대로 안 물게 한다',
    '_pb0 is DEFAULT_STATE["pinball"]' in SRV)

# 🧪 서버 셈을 **진짜 굴려** 본다 (server.py 를 통째로 들여오지 않고 그 함수만 떼어 쓴다)
_fn = re.search(r'^def _pinball_winners\(.*?(?=\n\ndef )', SRV, re.S | re.M)
_ns = {}
if _fn:
    exec(_fn.group(0), _ns)
_w = _ns.get('_pinball_winners')
_ORD = ['가', '나', '다', '라', '마']
if _w:
    chk('먼저 골인 1명 → 맨 앞', _w(_ORD, 'first', 1) == ['가'], _w(_ORD, 'first', 1))
    chk('먼저 골인 3명 → 앞 셋', _w(_ORD, 'first', 3) == ['가', '나', '다'], _w(_ORD, 'first', 3))
    chk('끝까지 남기 1명 → 맨 뒤', _w(_ORD, 'last', 1) == ['마'], _w(_ORD, 'last', 1))
    chk('끝까지 남기 3명 → 뒤에서 셋, 늦은 순', _w(_ORD, 'last', 3) == ['마', '라', '다'],
        _w(_ORD, 'last', 3))
    chk('사람보다 많이 뽑아도 안 터진다', _w(_ORD, 'last', 99) == ['마', '라', '다', '나', '가'])
    chk('빈 결과는 빈 목록', _w([], 'last', 3) == [] and _w(None, 'first', 1) == [])
else:
    chk('서버 당첨자 셈을 떼어 쓸 수 있다', False, '함수를 못 찾음')

# 🔁 방송판(pbWinnersOf)과 **같은 답**이 나오는가 — 한쪽만 고치면 화면과 기록이 달라진다
_js = re.search(r'function pbWinnersOf\(order\) \{.*?\n        \}', OV, re.S)
if _js and _w:
    _prog = ('let pbPicks = 1, pbRule = "first";\n' + _js.group(0) + '\n'
             + 'const O = ' + json.dumps(_ORD, ensure_ascii=False) + ';\n'
             + 'const out = [];\n'
             + 'for (const r of ["first", "last"]) for (const k of [1, 2, 3, 99]) {\n'
             + '  pbRule = r; pbPicks = k; out.push(pbWinnersOf(O.slice()));\n'
             + '}\n'
             + 'console.log(JSON.stringify(out));')
    _tmp = os.path.join(tempfile.gettempdir(), 'pbwin_check.js')
    io.open(_tmp, 'w', encoding='utf-8').write(_prog)
    try:
        _r = subprocess.run(['node', _tmp], capture_output=True, timeout=30)
        _got = json.loads(_r.stdout.decode('utf-8').strip() or '[]')
        _want = [_w(_ORD, r, k) for r in ('first', 'last') for k in (1, 2, 3, 99)]
        chk('방송판과 서버가 같은 사람을 뽑는다', _got == _want,
            ('방송판 %s / 서버 %s' % (_got, _want)) if _got != _want else ('%d가지 확인' % len(_want)))
    except Exception as _e:
        chk('방송판과 서버가 같은 사람을 뽑는다', False, str(_e))
    finally:
        try:
            os.remove(_tmp)
        except OSError:
            pass
else:
    chk('방송판 당첨자 셈을 찾는다', False)

print()
print('=' * 74)
print('🎱 굴리기 전 대기 화면')
print('=' * 74)
# 대표님이 고른 것(2026-09-18): 굴리기 전엔 빈 검은 상자만 떠 있었다.
chk('굴리기 전엔 코스와 구슬을 한 장 그린다', 'pbStart(list, Number(g.seed) || 1, map, true);' in OV)
# ⚠️ 미리보기에서 물리를 돌리면 구슬이 먼저 떨어져 버린다 — 한 장만 그리고 끝낸다
chk('미리보기는 물리를 안 민다', 'if (previewOnly) { pbDraw(); return; }' in OV)
# ⚠️ SSE 가 올 때마다 판을 다시 지으면 방송 컴퓨터가 쉬지 못한다 — 명단·판이 바뀔 때만
chk('같은 명단이면 다시 안 짓는다', 'key !== pbPreviewKey' in OV and 'pbPreviewKey = key;' in OV)
chk('굴리기 시작하면 대기 딱지를 내린다', 'pbPreviewKey = null;\n                    pbShowWinner(null);\n                    pbShowReady(0);' in OV)
chk('대기 딱지가 있다', 'id="pb-ready"' in OV and 'function pbShowReady(' in OV)
# ⚠️ 결과가 있으면(판이 끝났으면) 대기 화면을 안 그린다 — 1등 딱지를 덮는다
chk('끝난 판에는 대기 화면을 안 그린다', 'if (!res.length) {' in OV)

print()
print('=' * 74)
print('통과 %d · 실패 %d' % (ok, bad))
print('=' * 74)
sys.exit(1 if bad else 0)
