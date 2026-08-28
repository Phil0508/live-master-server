# -*- coding: utf-8 -*-
"""2b - 실제 클라이언트가 보내는 그대로 재현한 추돌 테스트.

조종실 pushAPI 는 PUSH_OWNED(bjs·extra_bjs·bottom_fixed·logs·match_logs)를
빼고 보낸다. 그러니 '설정 저장'이 점수를 지울 수는 없다.
다만 몇몇 조작은 일부러 bjs 를 실어 보낸다(기여도 직접 수정, 플레이어 추가·삭제·이름변경).
그 좁은 구간만 정확히 잰다.
"""
import copy, json, sys, threading, time
import requests
sys.stdout.reconfigure(encoding='utf-8')

BASE = "http://127.0.0.1:5177"
TOK = "lt-sandbox-secret-0123456789"
H = {"Authorization": "Bearer " + TOK, "Content-Type": "application/json"}
PLAYERS = ['가', '나', '다', '라']
PUSH_OWNED = ['bjs', 'extra_bjs', 'bottom_fixed', 'logs', 'match_logs']


def reset():
    requests.post(BASE + "/api/restore", headers=H, timeout=20, json={
        'broadcast_active': True,
        'bjs': [{'name': n, 'score': 0, 'contribution': 0} for n in PLAYERS],
        'pending_donations': [], 'logs': []})
    time.sleep(0.4)


def scores():
    st = requests.get(BASE + "/api/data", headers=H, timeout=20).json()
    return {b['name']: b.get('score', 0) for b in st['bjs']}, st


class Sse(threading.Thread):
    daemon = True

    def __init__(self):
        super().__init__()
        self.state = None
        self.ready = threading.Event()
        self.stop_flag = False

    def run(self):
        try:
            r = requests.get(BASE + "/api/stream?token=" + TOK, stream=True, timeout=(5, 600))
            ev = None
            for raw in r.iter_lines(decode_unicode=True):
                if self.stop_flag:
                    break
                if not raw:
                    continue
                if raw.startswith("event:"):
                    ev = raw[6:].strip()
                elif raw.startswith("data:") and ev in ("init", "update"):
                    try:
                        self.state = json.loads(raw[5:].strip())
                        self.ready.set()
                    except Exception:
                        pass
            r.close()
        except Exception:
            pass


def w_delta(cli, i):
    requests.post(BASE + "/api/score/add", headers=H, timeout=20,
                  json={'scope': 'rank', 'name': PLAYERS[i % 4], 'delta': 1})


def w_push_real(cli, i):
    """조종실 pushAPI() 그대로 - PUSH_OWNED 를 빼고 보낸다."""
    gd = copy.deepcopy(cli.state)
    if not gd:
        return
    gd['marquee_text'] = '공지 %d' % i
    for k in PUSH_OWNED:
        gd.pop(k, None)
    requests.post(BASE + "/api/data", headers=H, timeout=20, json=gd)


def w_push_with_bjs(cli, i):
    """pushAPI({include:['bjs','extra_bjs']}) 그대로 - 기여도 직접 수정 등."""
    gd = copy.deepcopy(cli.state)
    if not gd:
        return
    for k in PUSH_OWNED:
        if k not in ('bjs', 'extra_bjs'):
            gd.pop(k, None)
    tgt = gd.get('bjs') or []
    if tgt:
        tgt[0]['contribution'] = (tgt[0].get('contribution') or 0) + 1
    requests.post(BASE + "/api/data", headers=H, timeout=20, json=gd)


def w_patch(cli, i):
    """patchAPI - 필드 하나만."""
    requests.post(BASE + "/api/settings/patch", headers=H, timeout=20,
                  json={'marquee_text': '공지 %d' % i})


def run(title, fa, fb, gap, n=25, note=""):
    reset()
    a, b = Sse(), Sse()
    a.start(); b.start()
    if not (a.ready.wait(10) and b.ready.wait(10)):
        print("  SSE 실패")
        return
    errs = []

    def loop(cli, fn):
        for i in range(n):
            try:
                fn(cli, i)
            except Exception as e:
                errs.append(str(e)[:40])
            time.sleep(gap)

    ta = threading.Thread(target=loop, args=(a, fa))
    tb = threading.Thread(target=loop, args=(b, fb))
    ta.start(); tb.start(); ta.join(); tb.join()
    time.sleep(1.2)
    sc, st = scores()
    a.stop_flag = b.stop_flag = True
    total = sum(sc.values())
    lost = n - total
    flag = "OK " if lost == 0 else "!! "
    print("  %s%-28s %dms  배정 %2d점 → 남은 %2d점  손실 %2d (%5.1f%%)  오류 %d %s"
          % (flag, title, int(gap * 1000), n, total, lost, 100.0 * lost / n, len(errs), note))


print("\n" + "=" * 78)
print("실제 클라이언트 조합 - 배정(델타) 25건 + 상대편 조작 25건 동시")
print("=" * 78)
for gap in (0.10, 0.03, 0.0):
    run("배정 + 설정저장(조종실 그대로)", w_delta, w_push_real, gap)
print()
for gap in (0.10, 0.03, 0.0):
    run("배정 + 설정패치(patchAPI)", w_delta, w_patch, gap)
print()
for gap in (0.10, 0.03, 0.0):
    run("배정 + 기여도수정(bjs 포함)", w_delta, w_push_with_bjs, gap, note="<- 좁은 위험구간")
print()
for gap in (0.10, 0.03, 0.0):
    run("배정 + 배정 (폰+PC 동시)", w_delta, w_delta, gap)
print("=" * 78)
