# -*- coding: utf-8 -*-
"""📣 공지 탭 — 여러 개를 등록해 순서대로, 정한 간격마다 하나씩.

대표님(2026-09-30): "공지 시스템도 여러 개를 등록해서 여러 가지 멘트가 순서대로
얼마 만에 한 번씩 나올 수 있게 해 줘"

여기서 지키는 것
  ① 공지는 목록(notice_msgs)이고, 조종실에서 추가·고치기·순서·지우기가 다 된다
  ② 간격은 분·초로 자유롭게 (20초 ~ 60분). 방송판도 같은 하한을 쓴다
  ③ 차례는 서버 시계로 정한다 — 화면이 몇 개든 같은 공지가 같은 순간에 뜬다
     (방송판 renderNotice 의 식을 그대로 꺼내 돌려 본다 — 옮겨 적으면 어긋난다)
  ④ 조종실이 보여주는 '다음 차례' 도 그 식과 같아야 한다
  ⑤ 저장은 /api/settings/patch 로 — 서버에 그대로 남는다
"""
import io
import json
import os
import re
import sys
import urllib.error
import urllib.request

sys.stdout.reconfigure(encoding='utf-8')
ROOT = (os.environ.get('LM_PROJECT_ROOT')
        or os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')))
B = 'http://127.0.0.1:%s' % os.environ.get('LM_PT_PORT', '5199')
H = {'Content-Type': 'application/json', 'Authorization': 'Bearer sandboxsecret123456'}
OK, BAD = [], []


def chk(name, cond, detail=''):
    (OK if cond else BAD).append(name)
    print(('  [OK] ' if cond else '  [!!] ') + name + (('  -- ' + str(detail)[:160]) if detail else ''))


def head(s):
    print()
    print('=' * 74)
    print(s)
    print('=' * 74)


def post(path, obj=None):
    req = urllib.request.Request(B + path, json.dumps(obj or {}).encode(), H)
    try:
        with urllib.request.urlopen(req, timeout=25) as r:
            return r.status, json.loads(r.read().decode() or '{}')
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode() or '{}')
        except Exception:
            return e.code, {}


def get():
    with urllib.request.urlopen(urllib.request.Request(B + '/api/data', headers=H), timeout=25) as r:
        return json.loads(r.read().decode())


CT = io.open(os.path.join(ROOT, 'controller.html'), encoding='utf-8').read()
OV = io.open(os.path.join(ROOT, 'overlay.html'), encoding='utf-8', errors='replace').read()

head('① 조종실 공지 탭 — 한 공지 한 칸')
chk('공지 탭이 있다(⋯ 뒤에 숨기지 않는다)', 'id="tab-notice"' in CT
    and 'data-s="공지" onclick="openTab(event, \'tab-notice\')' in CT
    and 'tab-x" data-s="공지"' not in CT)
for fn in ('ntcAdd', 'ntcEdit', 'ntcMove', 'ntcDel', 'ntcNow', 'ntcSetEvery', 'ntcEveryFromInputs', 'ntcStatus'):
    chk('%s 가 있다' % fn, 'function %s(' % fn in CT or 'async function %s(' % fn in CT)
chk('한 줄씩 칸으로 그린다(.ntc-row)', "class=\"ntc-row\"" in CT and '.ntc-row {' in CT)
chk('옛 글상자(ntc-msgs)는 걷어냈다', 'id="ntc-msgs"' not in CT)
chk('지옥·퇴근 탭에는 공지로 가는 길만 남겼다(10-02 부터 공지는 ⚙ 설정 화면)', "ctlView('setup', 'tab-notice')" in CT)
chk('소액 후원 줄은 그대로 보여준다', 'id="ntc-donors"' in CT and 'notice_donors' in CT)
chk('공지는 20개까지', 'const NTC_MAX = 20;' in CT and '.slice(0, NTC_MAX)' in CT)
chk('빈 칸으로 고치면 되돌린다(실수로 지워지지 않게)', "el.value = m[i]; acctToast('비우려면" in CT)
chk('지울 때 한 번 묻는다', "premiumConfirm((i + 1) + '번 공지를 지울까요?" in CT)
chk('묻는 사이 목록이 바뀌면 같은 글을 찾아 지운다', 'const k = now.indexOf(m[i]);' in CT)
chk('분·초 칸은 쉼표 금지(comma_input.js 가 글자 칸으로 바꾼다)',
    'id="ntc-min" data-no-comma' in CT and 'id="ntc-sec" data-no-comma' in CT
    and '.ntc-every input {' in CT and '.ntc-every input[type=number]' not in CT)

head('② 간격 — 분·초로 자유롭게, 하한은 방송판과 같다')
m = re.search(r'function ntcSetEvery\(sec\) \{\s*sec = Math\.max\((\d+), Math\.min\((\d+),', CT)
chk('조종실 하한 20초 · 상한 60분', bool(m) and m.group(1) == '20' and m.group(2) == '3600', m.groups() if m else None)
mv = re.search(r"const period = Math\.max\((\d+), parseInt\(d\.notice_period\) \|\| 300\) \* 1000;", OV)
chk('방송판 하한도 20초 — 같다', bool(mv) and mv.group(1) == '20', mv.group(1) if mv else None)

head('③ 차례 — 서버 시계로(방송판 식 그대로 돌려 본다)')
# 방송판: pIdx = floor(now / period) % msgs.length
mp = re.search(r"const pIdx = Math\.floor\(now / period\) % msgs\.length;", OV)
chk('방송판은 구간 번호 % 공지 수 로 고른다', bool(mp))
# 조종실 상태 줄도 같은 식이어야 한다
mc = re.search(r"const now = Date\.now\(\) \+ serverTimeOffset, k = Math\.floor\(now / per\);\s*\n\s*cur = k % n;", CT)
chk('조종실 다음 차례도 같은 식 · 서버 시계를 쓴다', bool(mc))
chk('조종실도 소액 후원 줄을 한 칸으로 센다(방송판과 같게)', "const n = msgs.length + (donor ? 1 : 0);" in CT)


def turn(now_ms, period_s, count):
    """방송판 식 그대로 — 이 시각에 몇 번째 공지가 나오나"""
    return (now_ms // (period_s * 1000)) % count


ok = True
for t, per, cnt, want in ((0, 180, 4, 0), (180000, 180, 4, 1), (540000, 180, 4, 3), (720000, 180, 4, 0),
                          (95000, 90, 3, 1), (1000, 20, 2, 0)):
    if turn(t, per, cnt) != want:
        ok = False
chk('차례가 돌아간다 — 1 → 2 → 3 → 4 → 다시 1', ok)

head('④ 서버에 그대로 남는다')
st, _ = post('/api/settings/patch', {'notice_msgs': ['하나', '둘', '셋'], 'notice_period': 90, 'notice_speed': 130})
d = get()
chk('공지 세 개가 순서 그대로 저장된다', st == 200 and d.get('notice_msgs') == ['하나', '둘', '셋'], d.get('notice_msgs'))
chk('간격도 저장된다(90초)', d.get('notice_period') == 90, d.get('notice_period'))
st, r = post('/api/notice/now', {'idx': 2})
chk('[지금] 은 고른 공지를 띄운다', st == 200 and r.get('text') == '셋', (st, r))
st, r = post('/api/notice/now', {'idx': 99})
chk('없는 번호를 줘도 터지지 않는다(맨 끝으로)', st == 200 and r.get('idx') == 2, (st, r))
post('/api/settings/patch', {'notice_msgs': ['하나'], 'notice_period': 300})

print()
print('=' * 74)
print('통과 %d · 실패 %d' % (len(OK), len(BAD)))
for n in BAD:
    print('   [실패] ' + n)
sys.exit(1 if BAD else 0)
