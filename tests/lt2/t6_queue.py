# -*- coding: utf-8 -*-
"""6단계 - 시그니처 큐를 오버레이가 실제로 하는 방식으로 돌려본다.
   (오버레이는 재생을 끝내고 그 항목의 id 를 대며 넘긴다)"""
import json, os, sys, time
sys.stdout.reconfigure(encoding='utf-8')
os.environ.setdefault('HEADLESS', '1')
os.environ.setdefault('ADMIN_PASSWORD', 'lt-sandbox-pw')
os.environ.setdefault('SESSION_SECRET', 'lt-sandbox-secret-0123456789')
HERE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'qbox')
os.makedirs(HERE, exist_ok=True)
import shutil
src = os.path.dirname(os.path.abspath(__file__))
for f in ('server.py',):
    shutil.copy2(os.path.join(src, f), os.path.join(HERE, f))
for f in ('live_master.db', 'live_master.db-wal', 'live_master.db-shm'):
    p = os.path.join(HERE, f)
    if os.path.exists(p):
        os.remove(p)
sys.path.insert(0, HERE)
os.chdir(HERE)
import server as SV

OK, BAD = [], []


def chk(name, cond, detail=""):
    (OK if cond else BAD).append(name)
    print(("  [OK] " if cond else "  [!!] ") + name + (("  -- " + str(detail)[:130]) if detail else ""))


FAKE = {'id': 1, 'title': '테스트시그', 'amount': 50000,
        'audio_url': 'https://x/a.mp3', 'image_url': 'https://x/i.png'}
SV.supabase_match_signature = lambda amt: (FAKE if amt >= 50000 else None)
SV._supabase_ready = lambda: True
app = SV.app
app.config['TESTING'] = True
C = app.test_client()
AUTH = {'Authorization': 'Bearer lt-sandbox-secret-0123456789'}

with SV.file_lock:
    st = SV.load_data()
    st.update({'reaction_queue': [], 'pending_donations': [], 'broadcast_active': True,
               'reaction_mode': False,
               'bjs': [{'name': n, 'score': 0, 'contribution': 0} for n in ['가', '나']]})
    SV.save_data(st)

print("\n" + "=" * 72)
print("(1) 오버레이가 꺼져 있는 동안 후원 60건")
print("=" * 72)
t0 = time.time()
for i in range(60):
    C.post('/api/donation', json={'tx_id': 'toon_q_%d' % i, 'name': '시그군%d' % i,
                                  'amount': 50000, 'message': 'ㅎㅇ', 'time': '21:00'})
el = time.time() - t0
with SV.file_lock:
    st = SV.load_data()
q = st.get('reaction_queue') or []
pend = [d for d in st['pending_donations'] if str(d.get('name', '')).startswith('시그군')]
chk("큐가 상한 %d 에서 멈춘다" % SV.REACTION_QUEUE_MAX, len(q) == SV.REACTION_QUEUE_MAX, len(q))
chk("버려진 것은 가장 오래된 20건", q[0]['donator'] == '시그군20', q[0].get('donator'))
chk("후원 60건은 대기함에 전부 남는다(돈은 안 사라진다)", len(pend) == 60, len(pend))
chk("reaction_mode 가 켜져 있다", st.get('reaction_mode') is True, st.get('reaction_mode'))
print("      후원 60건 처리 %.1fs (건당 %.0fms)" % (el, el / 60 * 1000))
size_kb = len(json.dumps(SV.state_for_client(st, False), ensure_ascii=False).encode()) / 1024
size_kb_a = len(json.dumps(SV.state_for_client(st, True), ensure_ascii=False).encode()) / 1024
chk("오버레이가 받는 상태 < 200KB", size_kb < 200, "%.1fKB (조종실용 %.1fKB)" % (size_kb, size_kb_a))

print("\n" + "=" * 72)
print("(2) 오버레이가 다시 붙어 큐를 넘긴다 (id 를 대는 정상 방식)")
print("=" * 72)
lat = []
drained = 0
for _ in range(SV.REACTION_QUEUE_MAX + 3):
    with SV.file_lock:
        st = SV.load_data()
    qq = st.get('reaction_queue') or []
    if not qq:
        break
    t0 = time.time()
    r = C.post('/api/reaction/next', json={'id': qq[0]['id']})
    lat.append((time.time() - t0) * 1000)
    if r.status_code == 200:
        drained += 1
with SV.file_lock:
    st = SV.load_data()
lat_s = sorted(lat)
p95 = lat_s[min(len(lat_s) - 1, int(len(lat_s) * .95))] if lat_s else 0
chk("큐를 전부 넘길 수 있다", len(st.get('reaction_queue') or []) == 0, "남은 %d" % len(st.get('reaction_queue') or []))
chk("넘긴 횟수가 상한과 같다", drained == SV.REACTION_QUEUE_MAX, drained)
chk("큐 전진 p95 < 300ms", p95 < 300, "p95 %.1fms (최대 %.1fms)" % (p95, max(lat) if lat else 0))
chk("큐가 비면 reaction_mode 가 꺼진다", st.get('reaction_mode') is False, st.get('reaction_mode'))

print("\n" + "=" * 72)
print("(3) 무인증으로 큐를 지울 수 있는가 (번호 없이 빈 POST)")
print("=" * 72)
for i in range(3):
    C.post('/api/donation', json={'tx_id': 'toon_q2_%d' % i, 'name': '지킴이%d' % i,
                                  'amount': 50000, 'message': 'ㅎㅇ', 'time': '21:00'})
with SV.file_lock:
    st = SV.load_data()
n0 = len(st.get('reaction_queue') or [])
blocked = 0
for _ in range(10):
    r = C.post('/api/reaction/next', json={})
    if r.status_code != 200:
        blocked += 1
with SV.file_lock:
    st = SV.load_data()
n1 = len(st.get('reaction_queue') or [])
chk("번호 없는 무인증 POST 는 전부 막힌다", blocked == 10, "%d/10" % blocked)
chk("큐가 그대로 남아 있다", n0 == n1 and n0 == 3, "%d -> %d" % (n0, n1))

r = C.post('/api/reaction/next', json={}, headers=AUTH)
with SV.file_lock:
    st = SV.load_data()
chk("로그인하면 번호 없이도 건너뛸 수 있다(조종실)",
    r.status_code == 200 and len(st.get('reaction_queue') or []) == 2,
    "%s 남은 %d" % (r.status_code, len(st.get('reaction_queue') or [])))

r = C.post('/api/reaction/next', json={'id': 'rq_없는번호'})
with SV.file_lock:
    st = SV.load_data()
chk("엉뚱한 번호로는 큐가 안 줄어든다", len(st.get('reaction_queue') or []) == 2,
    len(st.get('reaction_queue') or []))

print("\n" + "=" * 72)
print("통과 %d · 실패 %d" % (len(OK), len(BAD)))
if BAD:
    for b in BAD:
        print("   - " + b)
print("=" * 72)
