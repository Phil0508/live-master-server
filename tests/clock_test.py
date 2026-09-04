# -*- coding: utf-8 -*-
"""🕘 화면에 뜨는 시각은 한국 시각이어야 한다.

사장님 말
  "로그탭에서 [16:07:26] 예지랑님 +9점 이렇게 뜨는데 시간이 안 맞아"

무엇이 문제였나
  운영 서버(Vultr)는 시간대 설정이 없어 UTC 로 돈다. time.strftime 은 서버 지역시를
  주므로, 밤 1시에 준 점수가 로그창에 16:07 로 찍혔다. 언제 준 것인지 알 수 없다.

여기서 지키는 것
  ① 로그·대기함에 적는 시각은 now_hms() 를 쓴다 (BROADCAST_TZ_SHIFT 만큼 옮긴다)
  ② DB 의 timestamp 는 **안 옮긴다** — 그쪽은 읽을 때 _bc_window 가 옮기므로
     쓸 때도 옮기면 두 번 밀려 월별 순위가 통째로 어긋난다
  ③ 타임머신에 치는 시각도 한국 시각으로 친다 (DB 는 서버시라 되돌려 물어봐야 한다)

⚠️ 이 검사는 서버를 안 띄운다. 시간대는 '어느 함수를 쓰느냐' 의 문제라 코드를 읽어서 본다
   (서버를 UTC 로 돌려놓고 재는 것은 윈도우에서 재현이 안 된다).
"""
import io
import os
import re
import sys

sys.stdout.reconfigure(encoding='utf-8')

PROJ = (os.environ.get('LM_PROJECT_ROOT')
        or os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')))
SV = io.open(os.path.join(PROJ, 'server.py'), encoding='utf-8', errors='replace').read()

OK, BAD = [], []


def chk(n, c, d=''):
    (OK if c else BAD).append(n)
    print(('  [OK] ' if c else '  [!!] ') + n + (('  -- ' + str(d)[:110]) if d else ''))


def body_of(name):
    """함수 하나의 본문만 잘라낸다."""
    seg = SV.split('def %s(' % name)
    if len(seg) < 2:
        return ''
    return re.split(r'\n(?:def |@app\.route)', seg[1])[0]


print('=' * 74)
print('① 시각을 한국 시각으로 주는 함수가 있다')
print('=' * 74)
chk('now_hms 가 있다', 'def now_hms():' in SV)
nh = body_of('now_hms')
chk('BROADCAST_TZ_SHIFT 만큼 옮긴다', '_bc_shift_hours()' in nh and '3600' in nh, nh.strip()[-90:])
# 정의가 쓰이는 곳보다 앞에 있어야 한다 — 뒤에 있으면 첫 호출에서 NameError 로 터진다
chk('정의가 첫 사용보다 앞에 있다',
    SV.index('def now_hms():') < SV.index('now_hms()', SV.index('def now_hms():') + 20))

print()
print('=' * 74)
print('② 로그·대기함에 서버 지역시가 남아 있지 않다')
print('=' * 74)
# 로그창과 대기함에 찍히는 것은 '시:분:초' 형태다. 이건 전부 now_hms 여야 한다.
left = [ln.strip() for ln in SV.split('\n') if "strftime('%H:%M:%S')" in ln]
chk('시:분:초를 서버 지역시로 찍는 곳이 없다', not left, left[:3])
chk('로그가 now_hms 를 쓴다', SV.count('now_hms()') >= 6, SV.count('now_hms()'))

print()
print('=' * 74)
print('③ DB 의 timestamp 는 그대로 둔다 — 옮기면 두 번 밀린다')
print('=' * 74)
don = body_of('receive_donation')
chk('후원 장부는 서버 지역시 그대로',
    "time.strftime('%Y-%m-%d %H:%M:%S')" in don and 'now_hms' not in don.split('INSERT INTO donation_history')[0][-400:],
    '장부 INSERT 앞에 now_hms 가 끼어들면 안 된다')
bw = body_of('_bc_window')
chk('읽을 때 옮기는 쪽은 그대로', 'timedelta(hours=shift)' in bw)

print()
print('=' * 74)
print('③-b 지난 방송 장부도 한국 시각으로 보여준다')
print('=' * 74)
chk('ts_kst 가 있다', 'def ts_kst(' in SV)
tk = body_of('ts_kst')
chk('보정이 0 이면 그대로 둔다', 'not shift' in tk)
chk('모양이 다르면 안 건드린다', 'except (TypeError, ValueError):' in tk and 'return ts_text' in tk)
for fn, what in (('api_archive_sessions', '회차 목록'),
                 ('api_archive_rows', '회차별 내역'),
                 ('api_archive_csv', '엑셀 내려받기')):
    b = body_of(fn)
    chk('%s 가 한국 시각으로 준다' % what, 'ts_kst(' in b, b[:0])
# 회차 이름(session_label)은 고르는 열쇠라 옮기면 안 된다
_rows = body_of('api_archive_rows')
chk('회차 이름은 안 옮긴다', 'ts_kst(label)' not in _rows and "ts_kst(r[0])" in _rows)
b = body_of('get_manual_logs') or body_of('api_manual_logs')
chk('이번 방송 장부 표도 한국 시각', "'timestamp': ts_kst(" in b, b[:0])
_csv = body_of('api_archive_csv')
chk('엑셀은 시각 칸만 옮긴다', '_r[1] = ts_kst(_r[1])' in _csv and 'ts_kst(_r[0])' not in _csv)

print()
print('=' * 74)
print('④ 타임머신 — 사장님이 치는 시각은 한국 시각이다')
print('=' * 74)
tm = body_of('restore_by_time')
chk('시간대 보정을 쓴다', '_bc_shift_hours()' in tm)
chk('KST 로 받아 서버시로 되돌려 묻는다', 'timedelta(hours=_shift)' in tm)
chk('오늘 날짜도 한국 기준으로 잡는다', 'today_kst' in tm and '_shift * 3600' in tm)
chk('안 맞는 시각은 곱게 거절한다', 'ValueError' in tm and '시간 형식' in tm)
chk('사람에게는 한국 시각으로 보여준다', 'shown_ts' in tm)
# 옛 코드가 남아 있으면 안 된다
chk('서버 날짜를 그대로 쓰던 줄이 없다', "today_str = time.strftime('%Y-%m-%d')" not in tm)

print()
print('=' * 74)
print('통과 %d · 실패 %d' % (len(OK), len(BAD)))
print('=' * 74)
sys.exit(1 if BAD else 0)
