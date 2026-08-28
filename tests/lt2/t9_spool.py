# -*- coding: utf-8 -*-
"""9단계 - 서버가 죽어 있는 동안 들어온 후원이 살아 돌아오는가.

리스너(toon_listener.py)의 대기줄을 그대로 쓴다. 서버를 내린 채 후원을 흘리고,
서버를 다시 올린 뒤 한 건도 빠짐없이 도착하는지 센다.
포트는 소크와 겹치지 않게 5188 을 쓴다.
"""
import json, os, shutil, subprocess, sys, time, uuid
import requests
sys.stdout.reconfigure(encoding='utf-8')

SRC = os.path.dirname(os.path.abspath(__file__))
HERE = os.path.join(SRC, 'spoolbox')
PORT = 5188
BASE = "http://127.0.0.1:%d" % PORT
TOK = "lt-sandbox-secret-0123456789"
H = {"Authorization": "Bearer " + TOK, "Content-Type": "application/json"}
PROJ = r"C:\Users\Administrator\Desktop\새로다시시작"

if os.path.isdir(HERE):
    shutil.rmtree(HERE, ignore_errors=True)
os.makedirs(HERE, exist_ok=True)
shutil.copy2(os.path.join(SRC, 'server.py'), os.path.join(HERE, 'server.py'))
shutil.copy2(os.path.join(PROJ, 'toon_listener.py'), os.path.join(HERE, 'toon_listener.py'))

ENV = dict(os.environ)
ENV.update({'HEADLESS': '1', 'PORT': str(PORT), 'ADMIN_PASSWORD': 'lt-sandbox-pw',
            'SESSION_SECRET': TOK, 'SELF_PING': 'off',
            'PYTHONIOENCODING': 'utf-8', 'PYTHONUNBUFFERED': '1'})

sys.path.insert(0, HERE)
LIS = None


def start_server():
    log = open(os.path.join(HERE, 'srv.log'), 'a', encoding='utf-8', errors='replace')
    p = subprocess.Popen([sys.executable, 'server.py'], cwd=HERE, env=ENV,
                         stdout=log, stderr=subprocess.STDOUT)
    for _ in range(80):
        time.sleep(0.4)
        try:
            if requests.get(BASE + "/api/ping", timeout=3).ok:
                return p
        except Exception:
            pass
    return p


def stop(p):
    subprocess.run(['taskkill', '/PID', str(p.pid), '/F', '/T'],
                   capture_output=True)
    time.sleep(1.5)


OK, BAD = [], []


def chk(name, cond, detail=""):
    (OK if cond else BAD).append(name)
    print(("  [OK] " if cond else "  [!!] ") + name + (("  -- " + str(detail)[:120]) if detail else ""))


print("=" * 72)
print("9단계 - 서버가 죽은 동안 들어온 후원")
print("=" * 72)

srv = start_server()
requests.post(BASE + "/api/restore", headers=H, timeout=20, json={
    'broadcast_active': True,
    'bjs': [{'name': n, 'score': 0, 'contribution': 0} for n in ['가', '나']],
    'pending_donations': [], 'logs': []})
print("  서버 기동 완료")

# 리스너 모듈을 불러 대기줄만 쓴다 (웹소켓은 안 붙는다)
os.chdir(HERE)
os.environ['DONATION_URL'] = BASE + '/api/donation'
os.environ['SPOOL_FILE'] = os.path.join(HERE, 'donation_spool.jsonl')
import importlib
tl = importlib.import_module('toon_listener')
tl.DONATION_URL = BASE + '/api/donation'
tl.SPOOL_FILE = os.environ['SPOOL_FILE']
print('  리스너 접수 주소:', tl.DONATION_URL)

print("\n  [1] 서버가 살아 있을 때 5건")
alive_ids = []
for i in range(5):
    pl = {"name": "살아있음%d" % i, "amount": 10000, "message": "ㅎㅇ",
          "tx_id": "toon_" + uuid.uuid4().hex}
    alive_ids.append(pl['name'])
    tl.deliver(pl)
time.sleep(1.0)
st = requests.get(BASE + "/api/data", headers=H, timeout=20).json()
got = [d['name'] for d in st['pending_donations']]
chk("살아 있을 때 5건 모두 도착", all(n in got for n in alive_ids),
    "%d/5" % sum(1 for n in alive_ids if n in got))

print("\n  [2] 서버를 내린다")
stop(srv)
try:
    requests.get(BASE + "/api/ping", timeout=3)
    chk("서버가 실제로 죽었다", False, "아직 응답함")
except Exception:
    chk("서버가 실제로 죽었다", True)

print("  [3] 죽어 있는 동안 후원 8건")
dead_ids = []
t0 = time.time()
for i in range(8):
    pl = {"name": "죽은동안%d" % i, "amount": 20000 + i, "message": "ㅁㅁ",
          "tx_id": "toon_" + uuid.uuid4().hex}
    dead_ids.append(pl['name'])
    tl.deliver(pl)
# 이 테스트는 deliver 를 곧바로(동기로) 부르므로 재시도 시간만큼 걸리는 게 정상이다.
# 실제 리스너는 이걸 딴 갈래(스레드)에서 부르므로 웹소켓이 멈추지 않는다 — t10 에서 잰다.
print("      (한 갈래에서 곧바로 부르면 %.1fs. 실제 리스너는 딴 갈래로 부른다 → t10 참고)"
      % (time.time() - t0))

spool = os.environ['SPOOL_FILE']
n_spool = len(open(spool, encoding='utf-8').read().strip().splitlines()) if os.path.exists(spool) else 0
chk("못 보낸 후원 8건이 대기줄 파일에 적혔다", n_spool == 8, "%d건" % n_spool)

print("\n  [4] 서버를 다시 올리고 대기줄을 흘린다")
srv = start_server()
requests.post(BASE + "/api/restore", headers=H, timeout=20, json={
    'broadcast_active': True,
    'bjs': [{'name': n, 'score': 0, 'contribution': 0} for n in ['가', '나']],
    'pending_donations': [], 'logs': []})
tl.spool_drain()
time.sleep(1.2)
st = requests.get(BASE + "/api/data", headers=H, timeout=20).json()
got = [d['name'] for d in st['pending_donations']]
hit = sum(1 for n in dead_ids if n in got)
chk("죽은 동안 들어온 8건이 전부 살아 돌아온다", hit == 8, "%d/8  받은것=%s" % (hit, got[:10]))

left = len(open(spool, encoding='utf-8').read().strip().splitlines()) if os.path.exists(spool) and open(spool, encoding='utf-8').read().strip() else 0
chk("보낸 뒤 대기줄이 비워진다", left == 0, "%d건 남음" % left)

print("\n  [5] 두 번 흘려도 중복되지 않는가")
tl.spool_drain()
time.sleep(0.8)
st = requests.get(BASE + "/api/data", headers=H, timeout=20).json()
got2 = [d['name'] for d in st['pending_donations']]
chk("다시 흘려도 후원이 늘어나지 않는다", len(got2) == len(got), "%d -> %d" % (len(got), len(got2)))

print("\n  [6] 같은 후원을 일부러 두 번 보내면 (tx_id 가 같을 때)")
pl = {"name": "중복시험", "amount": 33000, "message": "ㅋㅋ", "tx_id": "toon_" + uuid.uuid4().hex}
tl.deliver(pl)
time.sleep(0.4)
tl.deliver(dict(pl))
time.sleep(0.8)
st = requests.get(BASE + "/api/data", headers=H, timeout=20).json()
n = sum(1 for d in st['pending_donations'] if d.get('name') == '중복시험')
chk("같은 tx_id 는 한 번만 접수된다", n == 1, "%d건" % n)

print("\n  [7] 같은 사람이 진짜로 같은 금액을 연달아 쏘면 (tx_id 는 다름)")
for i in range(2):
    tl.deliver({"name": "진짜연속", "amount": 44000, "message": "ㅇㅇ",
                "tx_id": "toon_" + uuid.uuid4().hex})
    time.sleep(0.3)
time.sleep(0.8)
st = requests.get(BASE + "/api/data", headers=H, timeout=20).json()
n = sum(1 for d in st['pending_donations'] if d.get('name') == '진짜연속')
chk("진짜 두 번 쏜 것은 두 건 다 남는다(돈이 안 사라진다)", n == 2, "%d건" % n)

stop(srv)
print("\n" + "=" * 72)
print("통과 %d · 실패 %d" % (len(OK), len(BAD)))
for b in BAD:
    print("   - " + b)
print("=" * 72)
