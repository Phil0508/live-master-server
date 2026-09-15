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
chk('참가자가 둘은 돼야 굴린다', '참가자가 둘 이상이어야 합니다' in SRV)

print()
print('=' * 74)
print('④ 굴러가다 멈추지 않는가')
print('=' * 74)
chk('끼임 풀기가 있다', 'function pbUnstick(' in OV)
# ⚠️ '얼마나 내려갔나(dy)'로 보면 안 된다. 덫에 걸린 구슬은 제자리에서 떨리는데
#    그 떨림이 셈을 0으로 되돌려 영영 안 걸린다(실측: 20초를 굴려도 0~5 를 오갔다).
chk('속도로 본다 (내려간 거리로 보면 안 걸린다)', 'PB_STUCK_V' in OV and 'b.velocity' in OV)
chk('갈수록 세게 민다', 'pbKicks' in OV)
chk('고리에서 주기적으로 살핀다', 'pbUnstick()' in OV and 'pbTick' in OV)
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
chk('출발 자리를 섞는다', 'slots' in _mk and 'slots[i] = slots[j]' in _mk)
chk('섞을 때도 씨앗 난수를 쓴다', 'rng()' in _mk and 'Math.random' not in _mk)

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
    'function pbStart(names, seed, mapIdx)' in OV and 'mapIdx >= 0' in OV)
# ⚠️ 맵 파일을 못 읽었거나 -1 이면 우리 코스로 굴러야 한다. 방송이 빈 화면이 되면 안 된다.
chk('판을 못 쓰면 우리 코스로 굴린다', 'if (!bodies) { PB_WORLD = PB_WORLD_OWN' in OV)
chk('조종실에 고르는 칸이 있다', 'id="pb-map"' in CTL and 'pbcSetMap' in CTL)
# ⚠️ 목록에 걸리는 시간을 적어 둔다. 모르고 고르면 방송 흐름이 끊긴다.
chk('걸리는 시간을 적어 뒀다', '29~44초' in CTL and '21~48초' in CTL)
chk('가끔 안 끝나는 판을 숨기지 않는다', '가끔 안 끝남' in CTL)

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
# 🔴 구슬이 맵 배율을 따라야 한다 — 15px 고정이면 좁은 맵에서 못 사이에 낀다
#    (실측: 틈 24px 에 지름 30px 이라 여섯 개가 모두 y≈2850 에서 멈췄다).
chk('구슬 크기가 판 배율을 따른다', 'pbR = Math.max(' in OV and 'SC * 0.17' in OV)

print()
print('=' * 74)
print('⑧ 물리 엔진을 우리 서버에서 내보내는가')
print('=' * 74)
# ⚠️ 외부 CDN 을 부르면 방송 중 그쪽이 막히는 순간 게임이 통째로 안 뜬다.
#    컨페티를 vendor 에 둔 것과 같은 이유다.
chk('vendor 에서 부른다', '/vendor/matter.min.js' in OV)
chk('바깥 주소를 안 부른다', 'cdnjs' not in OV.split('<style>')[0] and 'unpkg' not in OV)
_mj = os.path.join(ROOT, 'vendor', 'matter.min.js')
chk('파일이 실제로 있다', os.path.exists(_mj),
    ('%dKB' % (os.path.getsize(_mj) // 1024)) if os.path.exists(_mj) else '없음')
if os.path.exists(_mj):
    _head = io.open(_mj, encoding='utf-8', errors='replace').read(400)
    chk('MIT 표기를 지운 적 없다', 'MIT' in _head and 'matter-js' in _head)
chk('없어도 방송은 계속된다', 'function pbHasEngine(' in OV and '!pbHasEngine()' in OV)

print()
print('=' * 74)
print('통과 %d · 실패 %d' % (ok, bad))
print('=' * 74)
sys.exit(1 if bad else 0)
