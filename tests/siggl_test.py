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
chk('입자 종류가 여럿이다 (불티·반짝임·연기)',
    "{ ember: 0, glint: 1, smoke: 2 }" in gl)
chk('빛 번짐을 끌 수 있다', 'this.bloom > 0' in gl)

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
