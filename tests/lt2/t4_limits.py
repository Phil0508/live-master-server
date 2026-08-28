# -*- coding: utf-8 -*-
"""4단계 - 상한과 방어선. 큐 / 영상 업로드 / AI 한도 / 잘못된 입력."""
import io, json, os, sys, time, uuid
import requests
sys.stdout.reconfigure(encoding='utf-8')

BASE = "http://127.0.0.1:5177"
TOK = "lt-sandbox-secret-0123456789"
H = {"Authorization": "Bearer " + TOK, "Content-Type": "application/json"}
HB = {"Authorization": "Bearer " + TOK}
OK, BAD = [], []


def chk(name, cond, detail=""):
    (OK if cond else BAD).append(name)
    print(("  [OK] " if cond else "  [!!] ") + name + (("  -- " + str(detail)[:140]) if detail else ""))


print("\n" + "=" * 72)
print("(1) 리액션 큐 상한 - 오버레이가 꺼져 있어도 무한히 안 쌓이는가")
print("=" * 72)
os.environ.setdefault('HEADLESS', '1')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import server as SV

st = {'reaction_queue': []}
for i in range(60):
    SV.enqueue_signature(st, {'id': i, 'title': 'sig%d' % i, 'audio_url': 'a', 'image_url': 'b'},
                         10000, '후원자%d' % i, 'ㅎㅇ', count_tally=False)
q = st['reaction_queue']
chk("큐가 상한 %d 에서 멈춘다" % SV.REACTION_QUEUE_MAX, len(q) == SV.REACTION_QUEUE_MAX, len(q))
chk("가장 오래된 것부터 버린다(최신 20건 유지)", q[0]['title'] == 'sig20', q[0]['title'])
chk("가장 최근 것이 남아 있다", q[-1]['title'] == 'sig59', q[-1]['title'])
chk("큐가 차도 reaction_mode 는 켜져 있다", st.get('reaction_mode') is True, st.get('reaction_mode'))
size_kb = len(json.dumps(st, ensure_ascii=False).encode()) / 1024
chk("큐 40건 상태 크기가 200KB 미만", size_kb < 200, "%.1fKB" % size_kb)

print("\n" + "=" * 72)
print("(2) AI 분당 한도 - 초과분이 곱게 죽는가")
print("=" * 72)
SV._nim_calls.clear()
passed = sum(1 for _ in range(45) if SV._nim_allowed())
chk("45번 중 %d번만 통과" % SV.NIM_RATE_LIMIT, passed == SV.NIM_RATE_LIMIT, passed)
chk("초과 뒤에도 예외 없이 False", SV._nim_allowed() is False)
SV._nim_calls.clear()

print("  (키가 없는 샌드박스에서는 AI 호출이 즉시 skipped 로 떨어진다 - 그 경로를 확인)")
r = requests.post(BASE + "/api/audit/suggest", headers=H, timeout=20,
                  json={'name': '아무개', 'amount': 1000, 'message': '알수없는말',
                        'players': ['가', '나']}).json()
chk("AI 를 못 써도 200 으로 곱게 답한다", r.get('status') == 'success', r)
chk("AI 를 못 쓰면 모름으로 떨어진다", r.get('tier') == 'unknown', r.get('tier'))

print("  AI 판단이 실패해도 후원이 대기함에 남는가")
requests.post(BASE + "/api/restore", headers=H, timeout=20, json={
    'broadcast_active': True, 'bjs': [{'name': n, 'score': 0, 'contribution': 0} for n in ['가', '나']],
    'pending_donations': [], 'logs': []})
for i in range(5):
    requests.post(BASE + "/api/donation", timeout=20,
                  json={'tx_id': 'toon_' + uuid.uuid4().hex, 'name': 'AI실패%d' % i,
                        'amount': 5000, 'message': '???', 'time': '21:00'})
time.sleep(0.6)
stt = requests.get(BASE + "/api/data", headers=H, timeout=20).json()
n = len([d for d in stt['pending_donations'] if str(d.get('name', '')).startswith('AI실패')])
chk("AI 가 못 풀어도 후원 5건이 대기함에 그대로", n == 5, "%d건" % n)

print("\n" + "=" * 72)
print("(3) 영상 업로드 - 확장자 / 용량 / 본문 상한")
print("=" * 72)
r = requests.post(BASE + "/api/account/video/upload", headers=HB, timeout=30,
                  files={'file': ('나쁜.exe', b'MZ' + b'\0' * 100, 'application/octet-stream')})
chk("exe 는 거부", r.status_code == 400, "%s %s" % (r.status_code, r.text[:80]))

r = requests.post(BASE + "/api/account/video/upload", headers=HB, timeout=30,
                  files={'file': ('영상.mp4.exe', b'MZ' + b'\0' * 100, 'video/mp4')})
chk("확장자 위장(mp4.exe) 거부", r.status_code == 400, "%s %s" % (r.status_code, r.text[:80]))

big = b'\0' * (int(SV.ACCT_VIDEO_MAX_MB * 1024 * 1024) + 2 * 1024 * 1024)
try:
    r = requests.post(BASE + "/api/account/video/upload", headers=HB, timeout=120,
                      files={'file': ('큰영상.mp4', big, 'video/mp4')})
    chk("%dMB 초과 거부" % SV.ACCT_VIDEO_MAX_MB, r.status_code in (400, 413),
        "%s %s" % (r.status_code, r.text[:80]))
except Exception as e:
    chk("%dMB 초과 거부" % SV.ACCT_VIDEO_MAX_MB, True, "연결 차단: " + str(e)[:50])

huge = b'\0' * (90 * 1024 * 1024)
try:
    r = requests.post(BASE + "/api/account/video/upload", headers=HB, timeout=180,
                      files={'file': ('초대형.mp4', huge, 'video/mp4')})
    chk("본문 상한 80MB 가 먼저 끊는다", r.status_code in (400, 413),
        "%s" % r.status_code)
except Exception as e:
    chk("본문 상한 80MB 가 먼저 끊는다", True, "연결 차단: " + str(e)[:50])

r = requests.get(BASE + "/api/server/status", headers=H, timeout=20)
chk("초대형 업로드 뒤에도 서버가 살아 있다", r.ok, r.status_code)

print("\n" + "=" * 72)
print("(4) 잘못된 입력 - 서버가 죽지 않는가")
print("=" * 72)
cases = [
    ("음수 후원", "/api/donation", {'amount': -5000, 'name': 'x', 'message': 'y'}, None),
    ("천문학적 금액", "/api/donation", {'amount': 10 ** 15, 'name': 'x', 'message': 'y'}, None),
    ("금액이 글자", "/api/donation", {'amount': 'abc', 'name': 'x'}, None),
    ("이름이 없음", "/api/score/add", {'scope': 'rank', 'delta': 1}, H),
    ("delta 가 글자", "/api/score/add", {'scope': 'rank', 'name': '가', 'delta': 'x'}, H),
    ("없는 사람에게 점수", "/api/score/add", {'scope': 'rank', 'name': '없는사람', 'delta': 1}, H),
    ("players 가 빈 배열", "/api/audit/suggest", {'name': 'a', 'amount': 1, 'message': 'b', 'players': []}, H),
    ("players 가 문자열", "/api/audit/suggest", {'name': 'a', 'amount': 1, 'message': 'b', 'players': 'x'}, H),
    ("아주 긴 메시지", "/api/audit/suggest",
     {'name': 'a', 'amount': 1, 'message': '가' * 50000, 'players': ['가']}, H),
    ("아주 긴 이름 후원", "/api/donation", {'amount': 1000, 'name': '나' * 5000, 'message': 'z'}, None),
]
for label, path, body, hdr in cases:
    try:
        r = requests.post(BASE + path, headers=(hdr or {"Content-Type": "application/json"}),
                          json=body, timeout=30)
        chk("%s -> 500 이 아니다" % label, r.status_code != 500, "%s %s" % (r.status_code, r.text[:60]))
    except Exception as e:
        chk("%s -> 500 이 아니다" % label, False, str(e)[:60])

r = requests.post(BASE + "/api/data", headers=HB, timeout=20,
                  data=b'{"broken": ', )
chk("깨진 JSON -> 500 이 아니다", r.status_code != 500, r.status_code)

r = requests.get(BASE + "/api/server/status", headers=H, timeout=20)
chk("잘못된 입력 폭격 뒤에도 서버가 살아 있다", r.ok, r.status_code)

print("\n" + "=" * 72)
print("통과 %d · 실패 %d" % (len(OK), len(BAD)))
if BAD:
    for b in BAD:
        print("   - " + b)
print("=" * 72)
