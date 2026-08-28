# -*- coding: utf-8 -*-
"""3단계 - 부하. 후원이 화면에 뜨기까지 얼마나 걸리는가, 몇 대까지 버티는가."""
import json, statistics, sys, threading, time, uuid
import requests
sys.stdout.reconfigure(encoding='utf-8')

BASE = "http://127.0.0.1:5177"
TOK = "lt-sandbox-secret-0123456789"
H = {"Authorization": "Bearer " + TOK, "Content-Type": "application/json"}
PLAYERS = ['가', '나', '다', '라']


def reset():
    requests.post(BASE + "/api/restore", headers=H, timeout=30, json={
        'broadcast_active': True,
        'bjs': [{'name': n, 'score': 0, 'contribution': 0} for n in PLAYERS],
        'pending_donations': [], 'logs': [], 'reaction_queue': []})
    time.sleep(0.5)


class Watcher(threading.Thread):
    """오버레이 흉내 - SSE 로 상태를 받으며 '언제 이 후원이 보였는지' 를 기록한다."""
    daemon = True

    def __init__(self, authed=True):
        super().__init__()
        self.seen = {}
        self.ready = threading.Event()
        self.stop_flag = False
        self.authed = authed
        self.bytes = 0
        self.events = 0
        self.err = None

    def run(self):
        url = BASE + "/api/stream" + ("?token=" + TOK if self.authed else "")
        try:
            r = requests.get(url, stream=True, timeout=(10, 900))
            ev = None
            for raw in r.iter_lines(decode_unicode=True):
                if self.stop_flag:
                    break
                if raw is None:
                    continue
                if raw.startswith("event:"):
                    ev = raw[6:].strip()
                elif raw.startswith("data:") and ev in ("init", "update"):
                    now = time.time()
                    self.bytes += len(raw)
                    self.events += 1
                    try:
                        st = json.loads(raw[5:].strip())
                    except Exception:
                        continue
                    for d in (st.get('pending_donations') or []):
                        k = d.get('name')
                        if k and k not in self.seen:
                            self.seen[k] = now
                    self.ready.set()
            r.close()
        except Exception as e:
            self.err = str(e)[:60]


def phase(n_clients, n_don, gap, label):
    reset()
    ws = [Watcher() for _ in range(n_clients)]
    for w in ws:
        w.start()
    t_end = time.time() + 20
    while time.time() < t_end and not all(w.ready.is_set() for w in ws):
        time.sleep(0.2)
    live = sum(1 for w in ws if w.ready.is_set())

    sent = {}
    post_ms = []
    fails = 0
    for i in range(n_don):
        nm = "부하%s_%03d" % (label, i)
        t0 = time.time()
        try:
            r = requests.post(BASE + "/api/donation", timeout=30,
                              json={'tx_id': 'toon_' + uuid.uuid4().hex, 'name': nm,
                                    'amount': 10000 + i, 'message': 'ㅎㅇ %d' % i,
                                    'time': '21:00'})
            if not r.ok:
                fails += 1
        except Exception:
            fails += 1
        post_ms.append((time.time() - t0) * 1000)
        sent[nm] = t0
        if gap:
            time.sleep(gap)

    time.sleep(3.0)
    lat = []
    missing = 0
    for nm, t0 in sent.items():
        ts = [w.seen.get(nm) for w in ws if w.ready.is_set()]
        ts = [t for t in ts if t]
        if not ts:
            missing += 1
            continue
        lat.append((max(ts) - t0) * 1000)

    st = requests.get(BASE + "/api/data", headers=H, timeout=30).json()
    landed = len([d for d in (st.get('pending_donations') or [])
                  if str(d.get('name', '')).startswith("부하%s_" % label)])
    for w in ws:
        w.stop_flag = True

    def pct(v, p):
        if not v:
            return 0
        v = sorted(v)
        return v[min(len(v) - 1, int(len(v) * p / 100))]

    print("  %-22s 접속%2d/%2d  후원%3d  대기함도달%3d  누락%2d  실패%d"
          % (label, live, n_clients, n_don, landed, missing, fails))
    print("      POST   p50 %6.1fms  p95 %6.1fms  최대 %7.1fms"
          % (pct(post_ms, 50), pct(post_ms, 95), max(post_ms) if post_ms else 0))
    print("      화면반영 p50 %6.1fms  p95 %6.1fms  최대 %7.1fms   (마지막 화면 기준)"
          % (pct(lat, 50), pct(lat, 95), max(lat) if lat else 0))
    return {'label': label, 'clients': live, 'landed': landed, 'missing': missing,
            'fails': fails, 'post_p95': pct(post_ms, 95), 'see_p95': pct(lat, 95)}


print("\n" + "=" * 78)
print("3단계 - 부하 (후원 -> 화면 반영)")
print("=" * 78)
out = []
out.append(phase(3, 30, 0.20, "3대/여유"))
out.append(phase(12, 40, 0.10, "12대/평소"))
out.append(phase(24, 40, 0.05, "24대/빡셈"))
out.append(phase(40, 60, 0.0, "40대/동시폭주"))

print("\n" + "=" * 78)
print("판정")
print("=" * 78)
for o in out:
    ok = (o['missing'] == 0 and o['fails'] == 0 and o['see_p95'] < 500)
    print("  %-14s %s  누락%d 실패%d  화면반영p95 %.0fms"
          % (o['label'], "통과" if ok else "확인필요", o['missing'], o['fails'], o['see_p95']))
print("=" * 78)
