# -*- coding: utf-8 -*-
"""10단계 - 리스너가 웹소켓을 굶기는가.

서버가 '죽지는 않았는데 응답이 없는' 상태(가장 흔한 장애 모양)를 만들고,
후원 한 건을 넘기는 동안 이벤트 루프가 얼마나 멈춰 있는지 잰다.
그 시간이 웹소켓 ping 간격(20초)을 넘으면 연결이 끊긴다 —
후원이 쏟아지는 바로 그 순간에.
"""
import asyncio, os, shutil, socket, sys, threading, time
sys.stdout.reconfigure(encoding='utf-8')

SRC = os.path.dirname(os.path.abspath(__file__))
HERE = os.path.join(SRC, 'starvebox')
if os.path.isdir(HERE):
    shutil.rmtree(HERE, ignore_errors=True)
os.makedirs(HERE, exist_ok=True)
shutil.copy2(os.path.join((os.environ.get('LM_PROJECT_ROOT')
        or os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))), 'toon_listener.py'),
             os.path.join(HERE, 'toon_listener.py'))
sys.path.insert(0, HERE)
os.chdir(HERE)

# 받기만 하고 영영 답하지 않는 가짜 서버
srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
srv.bind(('127.0.0.1', 0))
PORT = srv.getsockname()[1]
srv.listen(20)
held = []


def accept_forever():
    while True:
        try:
            c, _ = srv.accept()
            held.append(c)          # 붙잡아만 두고 답하지 않는다
        except Exception:
            return


threading.Thread(target=accept_forever, daemon=True).start()

os.environ['DONATION_URL'] = 'http://127.0.0.1:%d/api/donation' % PORT
os.environ['SPOOL_FILE'] = os.path.join(HERE, 'spool.jsonl')
import toon_listener as tl
tl.DONATION_URL = os.environ['DONATION_URL']
tl.SPOOL_FILE = os.environ['SPOOL_FILE']
tl.log = lambda *a: None            # 로그는 끈다

print("=" * 74)
print("응답 없는 서버(포트 %d)에 후원을 넘길 때 — 이벤트 루프가 멈추는 시간" % PORT)
print("=" * 74)
print("  타임아웃 %ds · 재시도 %s" % (10, tl.RETRY_DELAYS))


async def heartbeat(stop_ev, gaps):
    """웹소켓 ping 을 흉내낸다. 0.2초마다 깨어나야 정상."""
    last = time.time()
    while not stop_ev.is_set():
        await asyncio.sleep(0.2)
        now = time.time()
        gaps.append(now - last)
        last = now


async def run(blocking):
    gaps = []
    stop_ev = asyncio.Event()
    hb = asyncio.create_task(heartbeat(stop_ev, gaps))
    await asyncio.sleep(0.5)
    payload = {"name": "굶김시험", "amount": 10000, "message": "z", "tx_id": "toon_starve1"}
    t0 = time.time()
    if blocking:
        tl.deliver(payload)                      # 옛 방식 (async 안에서 그냥 호출)
    else:
        await asyncio.to_thread(tl.deliver, payload)   # 고친 코드가 실제로 하는 방식
    el = time.time() - t0
    await asyncio.sleep(0.5)
    stop_ev.set()
    await hb
    return el, (max(gaps) if gaps else 0)


for label, blocking in (("옛 방식 (그냥 호출)", True), ("고친 코드 (to_thread)", False)):
    if os.path.exists(tl.SPOOL_FILE):
        os.remove(tl.SPOOL_FILE)
    el, worst = asyncio.run(run(blocking))
    verdict = "웹소켓 끊김 (ping 20초 초과)" if worst >= 20 else (
        "위험 (ping 간격의 절반 넘음)" if worst >= 10 else "안전")
    print("  %-22s 후원 1건에 %5.1fs · 루프가 한 번에 멈춘 최대 %5.1fs  -> %s"
          % (label, el, worst, verdict))

print("\n  후원이 여러 건 몰릴 때 (지금 코드, 3건 연속)")
if os.path.exists(tl.SPOOL_FILE):
    os.remove(tl.SPOOL_FILE)


async def burst():
    gaps = []
    stop_ev = asyncio.Event()
    hb = asyncio.create_task(heartbeat(stop_ev, gaps))
    await asyncio.sleep(0.3)
    t0 = time.time()
    for i in range(3):
        await asyncio.to_thread(tl.deliver, {"name": "몰림%d" % i, "amount": 1000,
                                             "message": "z", "tx_id": "toon_burst%d" % i})
    el = time.time() - t0
    await asyncio.sleep(0.3)
    stop_ev.set()
    await hb
    return el, max(gaps)


el, worst = asyncio.run(burst())
print("  후원 3건에 %5.1fs · 루프가 한 번에 멈춘 최대 %5.1fs -> %s"
      % (el, worst, "웹소켓 끊김" if worst >= 20 else ("위험" if worst >= 10 else "안전")))
print("=" * 74)
