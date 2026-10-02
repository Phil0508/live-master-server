# -*- coding: utf-8 -*-
"""🔓 조종실 로그인 — 비밀번호 하나로 (2026-09-30).

왜 만들었나
  대표님: "OTP 인증은 없애자 앞으로 너무 불편해". 운영 서버는 원래 OTP 를 강제하지 않아(빈칸이면 통과)
  칸만 남아 헷갈렸고, 비밀번호를 틀리면 커서가 OTP 칸으로 갔다. 서버 · 화면 양쪽에서 걷어냈다.

여기서 지키는 것
  ① 비밀번호만으로 들어간다 · 옛 화면/진행봇이 otp 를 같이 보내도 들어간다 · 틀리면 막힌다
  ② OTP 등록 화면(/setup)이 없다
  ③ 코드 — OTP 검사가 없다 · 찍어보기 늦추기(login_throttle)는 그대로 있다 · 로그인 화면에 OTP 칸이 없다
  ④ 되돌리기 대비 — auth_config.json 의 totp_secret 은 안 지우고, requirements 의 pyotp 도 남긴다

⚠️ pausetest 서버(5199)가 필요하다 — runall 이 띄운다(ADMIN_PASSWORD=sandboxpw).
"""
import http.cookiejar
import io
import json
import os
import sys
import urllib.error
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _srvsrc import server_src  # server.py + features/*.py

sys.stdout.reconfigure(encoding='utf-8')
ROOT = (os.environ.get('LM_PROJECT_ROOT')
        or os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')))
B = 'http://127.0.0.1:5199'
OK, BAD = [], []


def chk(name, cond, detail=''):
    (OK if cond else BAD).append(name)
    print(('  [OK] ' if cond else '  [!!] ') + name + (('  -- ' + str(detail)[:160]) if detail else ''))


def head(s):
    print()
    print('=' * 74)
    print(s)
    print('=' * 74)


def login(body):
    """새 브라우저처럼(쿠키 없이) 로그인해 보고, 그 쿠키로 조종실이 열리는지까지 본다."""
    cj = http.cookiejar.CookieJar()
    op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
    r = urllib.request.Request(B + '/login', json.dumps(body).encode(), {'Content-Type': 'application/json'},
                               method='POST')
    try:
        with op.open(r, timeout=30) as res:
            code, d = res.status, json.loads(res.read().decode() or '{}')
    except urllib.error.HTTPError as e:
        code, d = e.code, json.loads(e.read().decode() or '{}')
    opened = False
    if code == 200:
        with op.open(urllib.request.Request(B + '/api/ai/board'), timeout=30) as res:
            opened = res.status == 200 and json.loads(res.read().decode() or '{}').get('status') == 'success'
    return code, d, opened


head('① 비밀번호만으로 들어간다')
c, d, opened = login({'password': 'sandboxpw'})
chk('비밀번호만 — 통과', c == 200 and d.get('status') == 'success', (c, d))
chk('그 쿠키로 로그인이 필요한 주소가 열린다', opened)
c, d, opened = login({'password': 'sandboxpw', 'otp': '123456'})
chk('옛 화면 · 진행봇처럼 otp 를 같이 보내도 통과(보지 않는다)', c == 200 and d.get('status') == 'success' and opened, (c, d))
c, d, opened = login({'password': 'sandboxpw', 'otp': ''})
chk('빈 otp 도 통과', c == 200 and opened, (c, d))
c, d, opened = login({'password': 'wrong-pass'})
chk('틀린 비밀번호는 막힌다', c == 400 and d.get('status') == 'error' and not opened, (c, d))
chk('틀리면 사람 말로', d.get('message') == '비밀번호가 달라요. 다시 넣어 주세요.', d.get('message'))

head('② OTP 등록 화면(/setup)이 없다')
try:
    with urllib.request.urlopen(urllib.request.Request(
            B + '/setup', headers={'Authorization': 'Bearer sandboxsecret123456'}), timeout=20) as res:
        body = res.read().decode('utf-8', 'replace')
        code = res.status
except urllib.error.HTTPError as e:
    code, body = e.code, ''
chk('/setup 에 OTP 키가 안 나온다', 'otpauth://' not in body and 'OTP' not in body, (code, body[:80]))

head('③ 코드')
SV = server_src(ROOT)
PG = io.open(os.path.join(ROOT, 'features', 'pages.py'), encoding='utf-8').read()
LG = io.open(os.path.join(ROOT, 'login.html'), encoding='utf-8').read()
CT = io.open(os.path.join(ROOT, 'controller.html'), encoding='utf-8').read()
chk('서버가 pyotp 를 안 부른다', 'import pyotp' not in SV and 'pyotp.' not in SV)
chk('OTP 강제 · 마스터 코드 설정이 없다', 'REQUIRE_OTP' not in SV and 'OTP_MASTER_CODE' not in SV and 'otp_master_matches' not in SV)
chk('/setup 주소가 없다', "@app.route('/setup')" not in SV)
lg = PG.split("def serve_login():")[1].split('\n@app.route')[0]
chk("로그인은 otp 를 읽지 않는다", "data.get('otp'" not in lg)
chk('찍어보기 늦추기는 그대로(OTP 가 없으니 유일한 장치)', 'login_throttle()' in lg and "login_failed('조종실 로그인')" in lg)
chk('기본 비밀번호(0508) 막기는 그대로', 'admin_password_is_unset()' in lg)
chk('로그인 화면에 OTP 칸이 없다', 'id="otp"' not in LG and 'otp:' not in LG)
chk('틀리면 비밀번호 칸으로 돌아간다', 'pw.focus(); pw.select();' in LG)
# 🎨 A안(2026-09-30) — 조종실과 같은 검정·금색, 폰은 한 줄 · PC 는 두 칸, 비밀번호 보기
# 🧥 2026-10-03: 조종실 금색 → 운영 화면 공통 옷(ops-theme.css)의 주황에 잇는다
chk('운영 화면 공통 옷을 입는다(예전 민트 네온이 아니다)', '/ops-theme.css' in LG and '--accent: var(--ops-accent);' in LG and '#00ffcc' not in LG)
chk('A안 — PC(900px 이상)는 왼쪽 소개 · 오른쪽 로그인 칸', '@media (min-width: 900px)' in LG
    and 'grid-template-columns: 1fr 520px;' in LG)
chk('비밀번호 보기 단추', 'function togglePw()' in LG and 'aria-label="비밀번호 보기"' in LG)
chk('보내는 동안 단추를 잠근다(두 번 눌림 방지)', 'btn.disabled = true;' in LG)
chk('아이폰이 칸을 누를 때 확대하지 않게 16px', 'font-size: 16px;' in LG)
chk("조종실에 'OTP 기기 등록' 링크가 없다", 'href="/setup"' not in CT)
chk('서버 창(GUI)에 OTP 키를 안 띄운다', 'OTP 보안키' not in SV)

head('④ 되돌리기 대비')
RQ = io.open(os.path.join(ROOT, 'requirements.txt'), encoding='utf-8').read()
chk("requirements 의 pyotp 는 남긴다(옛 버전은 import pyotp 가 있어야 뜬다)", 'pyotp' in RQ)
chk('방송 시작/종료 때 totp_secret 설정 칸은 안 지운다', "'totp_secret')" in SV)

print()
print('=' * 74)
print('통과 %d · 실패 %d' % (len(OK), len(BAD)))
for n in BAD:
    print('   [실패] ' + n)
print('=' * 74)
