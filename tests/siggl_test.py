# -*- coding: utf-8 -*-
"""🎆 빛·입자 레이어 (WebGL).

왜 만들었나
  연출 조각을 DOM 으로 그리면 1,400개쯤에서 9fps 로 무너진다. 같은 것을 WebGL 로
  그리면 20만 개를 한 프레임 0.8ms 에 그린다 (2026-08-31 RTX 3070 Ti 실측,
  60fps 예산 16.7ms 의 5%).

여기서 지키는 것 — 전부 실제로 났던 사고에서 나온 것이다
  · 스스로 멈추는가        루프가 방송 내내 도는 사고가 룰렛에서 있었다
  · 화면에서 떨어진 걸 아는가  parentNode 로 보면 레이어를 떼도 참으로 남는다
  · 연출이 끝나면 떼는가     안 떼면 캔버스는 사라져도 루프가 남는다
  · 못 쓰는 자리에서 살아남는가 하드웨어 가속 꺼진 OBS 에서도 방송은 나가야 한다
  · 지우기가 공짜인가        16만 개를 다시 올리면 연출마다 멈칫한다
  · 방송 위에 얹히는가       미리 곱해진 알파라야 가리지 않고 빛만 더해진다
"""
import io
import os
import re
import sys

sys.stdout.reconfigure(encoding='utf-8')
ROOT = r'C:\Users\Administrator\Desktop\새로다시시작'
OK, BAD = [], []


def chk(name, cond, detail=''):
    (OK if cond else BAD).append(name)
    print(('  [OK] ' if cond else '  [!!] ') + name + (('  -- ' + str(detail)[:110]) if detail else ''))


gl = io.open(os.path.join(ROOT, 'sig-fx-gl.js'), encoding='utf-8', errors='replace').read()
fx = io.open(os.path.join(ROOT, 'sig-fx.js'), encoding='utf-8', errors='replace').read()
ov = io.open(os.path.join(ROOT, 'overlay.html'), encoding='utf-8', errors='replace').read()

print('=' * 74)
print('① 엔진이 제자리에 있는가')
print('=' * 74)
chk('sig-fx-gl.js 가 SigGL 을 내보낸다', 'global.SigGL = SigGL' in gl)
chk('오버레이가 읽는다', '/sig-fx-gl.js' in ov)
i, j = ov.find('/sig-fx-gl.js'), ov.find('/sig-fx.js')
chk('sig-fx.js 보다 먼저 읽는다 (연출이 엔진을 찾을 수 있어야 한다)',
    0 < i < j, '%d < %d' % (i, j))
for f in ('attach', 'detach', 'burst', 'clear'):
    chk('%s() 가 있다' % f, re.search(r'\b' + f + r'\s*\(', gl) is not None)

print()
print('=' * 74)
print('② 스스로 멈추는가 — 방송 내내 도는 루프를 만들지 않는다')
print('=' * 74)
chk('마지막 입자가 죽는 시각을 들고 있다', '_until' in gl)
chk('그 시각이 지나면 루프를 끊는다',
    re.search(r'if \(t > SigGL\._until[^)]*\) return;', gl) is not None)
chk('쏠 때만 깨운다 (_wake)', '_wake()' in gl and 'if (this._raf || !this.on) return;' in gl)
chk('떼면 예약된 프레임을 취소한다', 'cancelAnimationFrame(this._raf)' in gl)
# ⚠️ parentNode 로 보면 안 된다. 연출 레이어를 통째로 떼도 캔버스의 부모는
#    여전히 그 레이어라 참으로 남는다. 실제로 그것 때문에 화면에 붙어 있지도
#    않은 캔버스에 계속 그리는 루프가 돌았다.
chk('화면에서 떨어진 것을 document.contains 로 본다', 'document.contains(SigGL.cv)' in gl)
chk('parentNode 로 살아있음을 판단하지 않는다',
    not re.search(r'if\s*\(\s*!?\w*\.parentNode\s*\)\s*(return|\{)', gl))

print()
print('=' * 74)
print('③ 연출이 끝나면 떼는가')
print('=' * 74)
chk('play() 가 붙인다', 'SigGL.attach(fx, this.W, this.H)' in fx)
chk('_cleanup() 이 뗀다', 'this.gl.detach()' in fx)
chk('떼고 나서 null 로 둔다 (다음 연출이 헌 것을 안 쓰게)',
    re.search(r'this\.gl\.detach\(\);? \} catch \(e\) \{\} this\.gl = null;', fx) is not None)
chk('다음 발 예약 타이머도 치운다 (다음 연출에 한 발이 끼어들지 않게)',
    'clearTimeout(this._glTimer)' in fx)
chk('불꽃이 레이어가 떨어진 것을 알아챈다',
    '!this.gl || !this.gl.on' in fx)

print()
print('=' * 74)
print('④ 못 쓰는 자리에서 살아남는가')
print('=' * 74)
chk('attach 가 못 쓰면 false 를 준다', 'return false;' in gl and 'catch (e) {' in gl)
chk('왜 못 쓰는지 남긴다 (this.why)', 'this.why' in gl)
chk('연출이 그걸 보고 null 로 둔다',
    re.search(r'this\.gl = null;[\s\S]{0,200}SigGL\.attach', fx) is not None)
chk('불꽃이 예전 캔버스2D 길을 그대로 갖고 있다',
    'if (this.gl) return this._fireworksGL(totalMs);' in fx and "getContext('2d')" in fx)
chk('붙이기가 터져도 연출은 계속 간다 (try/catch)',
    re.search(r'try \{[\s\S]{0,160}SigGL\.attach[\s\S]{0,120}catch', fx) is not None)

print()
print('=' * 74)
print('⑤ 지우기가 공짜인가')
print('=' * 74)
# 16만 개 × 64바이트 = 10MB 를 다시 올리면 연출이 시작·끝날 때마다 멈칫한다
chk('세대 번호로 지운다 (다시 올리지 않는다)', 'u_gen' in gl and 'this._gen = this._now()' in gl)
chk('셰이더가 지난 세대를 거른다', 'a_meta.x < u_gen' in gl)
mc = re.search(r'\n  clear\(\) \{[\s\S]*?\n  \}\n', gl)      # 본문 길이 제한에 안 걸리게
chk('clear() 안에서 대량 업로드를 하지 않는다',
    mc is not None and '_upload' not in mc.group(0),
    '_upload 발견' if (mc and '_upload' in mc.group(0)) else '')
chk('쏠 때는 쓴 자리만 올린다', 'bufferSubData' in gl and 'const first = cap - from' in gl)
chk('시계를 attach 마다 되감지 않는다 (되감으면 올라간 입자가 미래가 된다)',
    re.search(r'this\.t0 = \(global\.performance \|\| Date\)\.now\(\);', gl) is not None
    and gl.count('this.t0 =') == 1)

print()
print('=' * 74)
print('⑥ 방송 화면 위에 제대로 얹히는가')
print('=' * 74)
chk('미리 곱해진 알파로 만든다', 'premultipliedAlpha: true' in gl)
chk('입자도 미리 곱해서 낸다', 'o = vec4(c * a, a);' in gl)
chk('겹칠수록 밝아진다 (가산 혼합)', 'gl.blendFunc(gl.ONE, gl.ONE)' in gl)
chk('번진 빛도 알파를 올린다 (안 그러면 영상 위로 안 보인다)',
    re.search(r'float a = clamp\(sc\.a \+', gl) is not None)
chk('캔버스가 조작을 안 가로챈다', 'pointer-events:none' in gl)

print()
print('=' * 74)
print('⑦ 한계를 정해뒀는가')
print('=' * 74)
mcap = re.search(r'const CAP = (\d+);', gl)
chk('담아둘 수 있는 입자 수에 상한이 있다', mcap is not None, mcap.group(1) if mcap else '못 찾음')
if mcap:
    cap = int(mcap.group(1))
    chk('상한이 실측 범위 안이다 (20만까지 0.8ms 로 확인)', 20000 <= cap <= 200000, cap)
chk('한 번에 상한을 넘겨 쏠 수 없다', 'Math.min(opt.n || 3000, this.cap)' in gl)
# ⚠️ 'smoke' 가 두 뜻이다 — 화면을 채우는 연기 구름(SigGL.smoke)과
#    입자 종류로서의 먼지. 입자 쪽은 dust 로 부르고 smoke 는 옛 이름으로 남겼다.
chk('입자 종류가 여럿이다 (불티·반짝임·먼지)',
    "{ ember: 0, glint: 1, dust: 2, smoke: 2 }" in gl)

print()
print('=' * 74)
print('⑨ 매질 — PPT 느낌을 없애는 핵심')
print('=' * 74)
'''조각이 빈 화면 위에 홀로 뜨면 그게 PPT 다. 경계 없는 것이 흐르면 잠긴다.'''
for f in ('smoke', 'glow', 'shock'):
    chk('%s() 가 있다' % f, ('  ' + f + '(x, y, opt)') in gl)
chk('연기가 옥타브를 겹친다 (한 크기만 있으면 가짜로 보인다)', 'float fbm(' in gl)
chk('좌표 자체를 밀어 뭉게뭉게하게 한다 (도메인 왜곡)',
    'q += swirl * (vec2(fbm(q + 3.1), fbm(q + 7.7)) - 0.5)' in gl)
chk('매질을 1/4 크기로 그린다 (전체 크기면 이것만으로 예산을 다 쓴다)',
    'FIELD_DIV = 4' in gl and 'FIELD_DIV' in gl)
# ⚠️ 실제로 났던 사고: 매질의 y 가 입자와 반대라 착탄점 빛이 화면 아래에 가 있었다
chk('매질 y 를 입자와 같은 방향으로 뒤집는다',
    'vec2 px = vec2(uv.x, 1.0 - uv.y) * u_res;' in gl)
chk('충격파도 같은 좌표계를 쓴다',
    'vec2  d = vec2(uv.x, 1.0 - uv.y) * u_res - u_k0[i].xy;' in gl)
chk('충격파가 방송 화면은 못 건드린다고 적어뒀다', '방송 화면은 못 건드린다' in gl)
chk('자리가 꽉 차면 오래된 것을 밀어낸다', 'this.smokes.shift()' in gl)
chk('매질·빛·충격파도 루프 멈춤 계산에 들어간다', gl.count('this._mark(') >= 4)

print()
print('=' * 74)
print('⑩ 연출 문법 — 17개가 부르는 말')
print('=' * 74)
for f in ('gAmbient', 'gImpact', 'gPlume', 'gGlow', 'gSparkle', 'gStream'):
    chk('%s() 가 있다' % f, ('  ' + f + '(') in fx)
chk('레이어가 없으면 조용히 아무것도 안 한다 (예전 모습으로 그대로 간다)',
    fx.count('if (!this.gl) return;') >= 6)
chk('설계 좌표를 안에서 옮긴다 (연출이 좌표계를 신경 안 쓰게)',
    'this._x(x)' in fx and 'this._y(y)' in fx and 'this._r(' in fx)
# ⚠️ 착탄은 순서가 생명이다. 동시에 터뜨리면 그냥 '펑' 이고, 어긋나야 '맞았다' 가 된다
chk('착탄이 빛→충격파→불티→연기 순으로 어긋난다',
    "delay: 0.02" in fx and "delay: 0.03" in fx and "delay: 0.09" in fx)
import re as _re
cnt = len(_re.findall(r'this\.gAmbient\(', fx))
chk('연출 17개가 전부 화면을 채우고 시작한다 (빈 화면이 PPT 느낌의 큰 몫)',
    cnt >= 17, '%d개' % cnt)
chk('빛 번짐을 끌 수 있다', 'this.bloom > 0' in gl)
# ⚠️ 번짐이 많다고 좋은 게 아니다. 1.15 로 뒀더니 연기까지 통째로 번져 화면이 뿌옜다.
chk('빛 번짐이 기본으로 꺼져 있다', re.search(r'this\.bloom = 0;', gl) is not None)
chk('뜨거운 심지만 뽑는다 (문턱이 높다)',
    re.search(r'smoothstep\(0\.6[0-9], 1\.0, b\)', gl) is not None)
# ⚠️ 예전에는 번짐을 끄면 합치는 단계를 통째로 건너뛰어 그레인·색수차·충격파까지 꺼졌다
chk('번짐을 꺼도 렌즈는 돈다 (그레인·색수차·충격파는 번짐과 무관하다)',
    'const target = rt.scene;' in gl and 'if (useBloom) {' in gl
    and 'if (!useBloom) { gl.disable(gl.BLEND); return; }' not in gl)

print()
print('=' * 74)
print('⑪ 요소 — 주인공도 GL 안으로')
print('=' * 74)
"""매질만 깔아서는 'PPT 같다' 가 안 없어진다. 주인공인 글자·형상이 CSS div 로
   화면 위에 따로 떠 있으면 아무리 분위기를 깔아도 '위에 얹힌 종이' 로 보인다."""
chk('스프라이트를 GL 에 올릴 수 있다', 'sprite(src, o)' in gl and 'SPR_VS' in gl and 'SPR_FS' in gl)
chk('입자 위·빛 번짐 앞에서 그린다 (같은 빛·그레인·왜곡을 먹게)',
    '_drawSprites(t, target)' in gl)
# ⚠️ 'half' 는 GLSL 예약어다. 이걸로 셰이더가 안 만들어져 레이어가 통째로 꺼진 적이 있다
chk("GLSL 예약어를 변수로 쓰지 않는다 ('half' 로 레이어가 꺼진 적이 있다)",
    'vec2 half' not in gl)
chk('타들어오며 나타난다 (켜졌다/꺼졌다가 아니라)', 'u_dis' in gl and '문턱' in gl)
chk('타는 경계에 뜨거운 테가 생긴다 (없으면 그냥 지워지는 것처럼 보인다)', 'u_burn' in gl)
chk('테두리가 빛난다 (장면 안에서 빛을 받는다)', 'u_rim' in gl)
chk('금속 결이 흐른다 (광택 쓸기)', 'u_sheen' in gl)
chk('열에 일렁인다', 'u_warp' in gl)
chk('부서져 가루가 된다', 'shatter(src, x, y, w, h, o)' in gl)
chk('부술 때 픽셀을 건너뛰며 훑는다 (촘촘히 보면 CPU 가 죽는다)',
    "step = Math.max(2, o.step || 4)" in gl)
chk('지나쳤다 돌아오는 결이 있다 (툭 놓였다가 아니라 내리꽂혔다)',
    "kind === 'back'" in gl)
chk('같은 그림을 두 번 올리지 않는다', '_texCache' in gl)

print()
print('=' * 74)
print('⑫ 글자가 재질인가')
print('=' * 74)
"""게임 연출에서 글자는 색이 아니라 재질이다. 한 색으로 칠하면 그건 종이다."""
chk('글자를 재질로 그리는 도구가 있다', 'gText(txt, o)' in fx)
chk('위에서 빛이 오는 결 (세로 그라데이션)', 'createLinearGradient(0, cy - size' in fx)
chk('가장자리에 테를 두 겹 두른다 (어떤 배경에서도 읽히게)', fx.count('strokeText(txt, cx, cy)') >= 2)
chk('안쪽에 그림자가 진다 (두께가 생긴다)', "globalCompositeOperation = 'source-atop'" in fx)
chk('설계 좌표로 GL 에 올린다', 'gSprite(cv, o)' in fx and 'this._x(o.x' in fx)
chk('부수는 말도 있다', 'gShatter(cv, o)' in fx)
# ⚠️ 레이어가 없으면 예전 CSS 글자로 그대로 가야 한다. 방송이 멈추면 안 된다.
chk('가즈아가 GL 글자를 쓴다', "this.gText('가즈아'" in fx)
chk('레이어가 없으면 예전 CSS 글자로 간다', "} else {" in fx and "this.txt(fx, '가즈아'" in fx)
chk('부서짐이 예약돼 있다', 'this.gShatter(GZ' in fx)

# ⚠️ 실제로 화면 어디에 서는가 — 여기서 한 번 크게 틀렸다.
#    from/to 의 x·y 를 '놓인 자리에서의 어긋남' 으로 쓰고 있는데 코드가 절대 좌표로
#    읽어서 to:{y:0} 이 '화면 꼭대기' 가 됐다. 글자가 맨 위에 붙어 버렸다.
chk('from/to 의 x·y 는 놓인 자리에서의 어긋남이다 (절대 좌표가 아니다)',
    'x = e.x + fx0' in gl and 'y = e.y + fy0' in gl)
chk('절대 좌표로 읽던 옛 코드가 남아 있지 않다',
    '(T.y != null ? T.y : e.y)' not in gl)
# 안전지대는 화면 6~50%. 글자는 그 안, 그리고 너무 위가 아니어야 한다.
_cy = re.search(r'const CY = (\d+);', fx)
chk('가즈아 글자 자리가 상수로 잡혀 있다', bool(_cy))
if _cy:
    _y = 115 + int(_cy.group(1)) * (1920 - 115 - 960) / 1080  # 설계 y → 화면 y
    _p = _y / 1920 * 100
    chk('글자가 안전지대 안이다 (6~50%%) — 지금 %.1f%%' % _p, 6 < _p < 50)
    chk('글자가 위로 쏠려 있지 않다 (25%% 아래) — 지금 %.1f%%' % _p, _p > 25)

print()
print('=' * 74)
print('⑧ 불꽃이 불꽃처럼 보이는가')
print('=' * 74)
# 속도를 넓게 흩뿌리면 가운데가 꽉 찬 원반 — '먼지 뭉치' 가 된다
mb = re.search(r"n: (\d+), kind: 'ember'[\s\S]{0,120}?speed: \[(\d+) \* this\.KX, (\d+) \* this\.KX\]", fx)
chk('껍질 모양으로 터진다 (속도 폭이 좁다)', mb is not None and int(mb.group(2)) / int(mb.group(3)) > 0.5,
    (mb.group(2) + '~' + mb.group(3)) if mb else '못 찾음')
chk('한 점·한 순간에 겹치지 않게 흩는다 (딱딱한 흰 원반 방지)',
    'jitter:' in fx and 'radius:' in fx)
chk('자국을 남긴다 (없으면 점이 멈춰 있는 것처럼 보인다)', 'this.gl.trail =' in fx)
chk('설계 좌표를 화면 좌표로 옮겨서 넘긴다', 'this._x(this.rnd(' in fx and 'this._y(this.rnd(' in fx)
chk('거리·힘도 배율을 탄다 (세로판에서 안 어긋나게)',
    '* this.KX' in fx and '* this.KY' in fx)
chk('시그니처 대표색을 따른다', 'this.C ? this.C[' in fx)

print()
print('=' * 74)
print('통과 %d · 실패 %d' % (len(OK), len(BAD)))
for n in BAD:
    print('   [실패] ' + n)
print('=' * 74)
