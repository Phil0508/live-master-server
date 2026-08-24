# -*- coding: utf-8 -*-
"""
투네이션 후원을 '크롬 없이' 서버가 직접 받아 방송 서버로 넘긴다.

  알림창 페이지에서 소켓 토큰을 꺼내 → wss://ws.toon.at 에 붙어 →
  후원(code 101)이 오면 → 방송 서버 /api/donation 으로 전달한다.

이걸 systemd 로 상주시키면 크롬·템퍼몽키·OBS 브라우저 소스가 전부 필요 없어진다.

환경변수:
  ALERTBOX_URL   투네이션 알림창 주소 (필수)
  DONATION_URL   방송 서버 접수 주소 (기본 http://127.0.0.1:8080/api/donation)
  INCLUDE_TEST   '1' 이면 '후원 테스트'도 서버로 전달(기본은 전달 안 함, 로그만)

실행:
  ALERTBOX_URL=https://toon.at/widget/alertbox/<키> python toon_listener.py
  옵션: --dry  (서버로 실제 전송하지 않고, 보낼 내용만 출력 = 안전한 리허설)

⚠️ 투네이션의 비공개 규격이라 그쪽이 바꾸면 끊길 수 있다(공식 API 아님).
   기존 템퍼몽키+OBS 방식을 폴백으로 남겨두는 것을 권장.
"""
import os, sys, re, json, time, asyncio, hashlib, threading, urllib.request

try:
    import websockets
except ImportError:
    print("먼저: pip install websockets"); sys.exit(1)

ALERTBOX_URL = os.environ.get("ALERTBOX_URL", "")
DONATION_URL = os.environ.get("DONATION_URL", "http://127.0.0.1:8080/api/donation")
INCLUDE_TEST = os.environ.get("INCLUDE_TEST", "").strip() in ("1", "on", "true", "yes")
# 💵 소액 후원 걸러내기. 10,000원 미만은 서버로 보내지 않는다.
#    10,000원당 1점이라 그 아래는 어차피 0점이고, 시그니처 최저가도 10,300원이라 걸리는 게 없다.
#    0원은 통과시킨다 — '시그니처 신청'이 0원으로 들어오기 때문이다.
#    MIN_AMOUNT=0 으로 두면 전부 통과한다.
try:
    MIN_AMOUNT = int(os.environ.get("MIN_AMOUNT", "10000"))
except ValueError:
    MIN_AMOUNT = 10000
DRY = "--dry" in sys.argv

# 📮 보내지 못한 후원을 적어두는 파일. 서버가 잠깐 죽어 있어도 후원이 사라지지 않게 한다.
#    (자동 배포가 커밋마다 서버를 재시작하므로, 이 창은 드물지 않게 열린다)
SPOOL_FILE = os.environ.get("SPOOL_FILE") or os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "donation_spool.jsonl")
# 전송 재시도 간격(초).
# ⚠️ 여기서 오래 붙잡고 있으면 그동안 웹소켓을 못 읽는다. websockets 는 20초마다 ping 을
#    주고받는데 그게 밀리면 연결이 통째로 끊긴다 — 후원을 지키려다 소켓을 잃는 셈이다.
#    그래서 한 번만 짧게 다시 보고, 안 되면 곧바로 대기줄에 넣는다.
#    (대기줄은 아래 spool_watcher 가 10초마다 비워주므로 늦어야 10초다)
RETRY_DELAYS = (0.6,)

DONATION_CODE = 101  # 투네이션 후원 이벤트 코드 (실측 확인)

def log(*a):
    print(time.strftime("%H:%M:%S"), *a, flush=True)

def fetch_token(alert_url):
    req = urllib.request.Request(alert_url, headers={"User-Agent": "Mozilla/5.0"})
    html = urllib.request.urlopen(req, timeout=15).read().decode("utf-8", "replace")
    m = re.search(r'window\.payload\s*=\s*JSON\.parse\(\s*"(.*?)"\s*\)', html, re.S)
    if not m:
        raise RuntimeError("window.payload 를 못 찾음 - ALERTBOX_URL 확인")
    obj = json.loads(json.loads('"' + m.group(1) + '"'))
    tok = obj.get("payload")
    if not tok:
        raise RuntimeError("소켓 토큰이 비어있음")
    return tok

# 소켓 재전송(재연결 시 밀린 알림 재수신)만 걸러내기 위한 최근 수신 기록.
# {후원신원: 마지막 수신시각}. 오래된 것은 자동 정리한다.
_recent = {}
REPLAY_TTL = 90  # 초. 이 안에 똑같은 후원이 또 오면 '소켓 재전송'으로 보고 버린다.

# ⚠️ [후원이 사라지던 문제] 예전에는 이 재전송 방어를 '항상' 걸었다. 그런데 투네이션은
#    후원마다 고유번호를 주지 않아서(실측 확인) 이름+금액+메시지로만 판단할 수밖에 없다.
#    그래서 같은 사람이 같은 금액을 같은 메시지(빈 메시지 포함)로 90초 안에 또 쏘면
#    두 번째가 통째로 버려졌다 — 실제 방송에서 후원이 사라졌다.
#
#    재전송은 '소켓이 끊겼다 다시 붙었을 때'만 생긴다. 그리고 우리는 언제 다시 붙었는지 안다.
#    그러니 평소에는 방어를 아예 걸지 않고, 재연결 직후 이 시간 동안만 건다.
#    (0 으로 두면 방어를 완전히 끈다)
try:
    REPLAY_GUARD_AFTER_RECONNECT = int(os.environ.get("REPLAY_GUARD_SEC", "60"))
except ValueError:
    REPLAY_GUARD_AFTER_RECONNECT = 60

# 마지막으로 소켓에 붙은 시각. 0 이면 아직 한 번도 안 붙은 것.
_connected_at = 0.0

def _replay_guard_active(now):
    """지금 재전송 방어를 걸어야 하는 구간인가."""
    if REPLAY_GUARD_AFTER_RECONNECT <= 0 or not _connected_at:
        return False
    return (now - _connected_at) < REPLAY_GUARD_AFTER_RECONNECT

def to_donation(msg):
    """투네이션 packet → (방송 서버 후원 형식, 테스트여부, 건너뛸사유).
       후원이 아니면 payload=None. 소켓 재전송이면 skip='replay'."""
    if msg.get("code") != DONATION_CODE:
        return None, False, "not_donation"
    c = msg.get("content") or {}
    is_test = bool(msg.get("test")) or bool(c.get("test_noti"))
    name = (c.get("name") or "익명").strip()
    try:
        amount = int(c.get("amount") or 0)
    except (TypeError, ValueError):
        amount = 0
    message = (c.get("message") or "").strip()

    # tx_id 는 서버의 '영구 중복 차단'에 쓰인다. 그래서 매번 고유해야 한다.
    # 같은 사람이 같은 금액·메시지로 시간차를 두고 또 후원할 수 있기 때문이다.
    # 단, packet 에 진짜 고유 id 가 있으면 그걸 쓴다(가장 정확).
    stable = None
    for k in ("idx", "pay_key", "seq", "id", "donation_id", "key"):
        v = c.get(k) or msg.get(k)
        if v:
            stable = str(v); break

    ident = "{}|{}|{}".format(name, amount, message)
    now = time.time()
    for kk in [k for k, t in _recent.items() if now - t > REPLAY_TTL]:
        _recent.pop(kk, None)
    # 고유 id 가 없고, '재연결 직후 구간'일 때만 동일 후원 재수신을 재전송으로 보고 버린다.
    # 평소(연결이 계속 유지된 상태)에는 같은 내용이 또 와도 진짜 후원이므로 그냥 통과시킨다.
    if (stable is None and _replay_guard_active(now)
            and ident in _recent and now - _recent[ident] < REPLAY_TTL):
        return None, is_test, "replay"
    _recent[ident] = now

    tx = stable or hashlib.md5("{}|{}".format(ident, now).encode("utf-8")).hexdigest()[:16]
    payload = {"name": name, "amount": amount, "message": message, "tx_id": "toon_" + tx}
    return payload, is_test, None

def post_donation(payload):
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(DONATION_URL, data=data,
                                 headers={"Content-Type": "application/json"})
    r = urllib.request.urlopen(req, timeout=10)
    return r.status, r.read().decode("utf-8", "replace")[:200]


# ══ 후원을 잃지 않기 위한 장치 ══
#
# ⚠️ 예전에는 전송이 실패하면 로그 한 줄만 남기고 그 후원을 버렸다. 재시도도, 저장해
#    뒀다 나중에 보내는 것도 없었다. 그런데 배포 스크립트가 새 커밋마다
#    `systemctl restart livemaster` 를 하므로, 재시작하는 몇 초 사이에 들어온 후원은
#    영구히 사라졌다. 방송 중에 코드를 올리면 정확히 그 창이 열린다.
#
#    이제 ① 몇 번 다시 보내보고 ② 그래도 안 되면 파일에 적어둔 뒤
#    ③ 서버가 살아나면 밀린 것부터 흘려보낸다. tx_id 가 그대로라 서버가 중복을 걸러주므로
#    같은 후원이 두 번 들어갈 걱정은 없다.

def send_once(payload):
    """한 번 보낸다. 성공하면 True."""
    try:
        st, body = post_donation(payload)
        log("   → 서버 응답", st, body)
        return True
    except Exception as e:
        log("   ⚠️ 전송 실패:", type(e).__name__, e)
        return False


# ⚠️ 대기줄 파일을 만지는 곳이 두 군데다 — 후원을 넘기는 쪽과 10초마다 도는 감시자.
#    아래에서 이 둘을 각각 딴 갈래(스레드)로 돌리므로, 자물쇠 없이 두면
#    한쪽이 파일을 다시 쓰는 사이 다른 쪽이 적은 줄이 통째로 날아갈 수 있다(= 후원 유실).
_spool_lock = threading.Lock()


def spool_add(payload):
    """보내지 못한 후원을 파일 끝에 적어둔다."""
    try:
        with _spool_lock:
            with open(SPOOL_FILE, "a", encoding="utf-8") as f:
                f.write(json.dumps(payload, ensure_ascii=False) + "\n")
        log("   📮 대기줄에 넣었습니다 —", os.path.basename(SPOOL_FILE),
            "(서버가 살아나면 자동으로 다시 보냅니다)")
    except Exception as e:
        # 여기까지 실패하면 정말로 방법이 없다. 최소한 화면에는 남긴다.
        log("   ❌❌ 대기줄 기록마저 실패 —", type(e).__name__, e)
        log("   ❌❌ 사라진 후원:", json.dumps(payload, ensure_ascii=False))


def spool_drain():
    """밀린 후원을 순서대로 다시 보낸다. 못 보낸 것만 파일에 남긴다.

    ⚠️ 통신이 들어 있어 오래 걸린다. 절대 async 루프 안에서 그냥 부르지 말 것
       (아래 to_thread 주석 참고). 그리고 자물쇠 덕에 두 갈래가 겹쳐 돌지 않는다 —
       겹치면 같은 줄을 두 번 보내거나, 더 나쁘게는 적힌 줄이 사라진다.
    """
    if DRY or not os.path.exists(SPOOL_FILE):
        return
    if not _spool_lock.acquire(blocking=False):
        return              # 이미 다른 갈래가 흘리는 중이다
    try:
        _spool_drain_locked()
    finally:
        _spool_lock.release()


def _spool_drain_locked():
    if not os.path.exists(SPOOL_FILE):
        return
    try:
        with open(SPOOL_FILE, "r", encoding="utf-8") as f:
            rows = [ln.strip() for ln in f if ln.strip()]
    except Exception as e:
        log("⚠️ 대기줄을 읽지 못했습니다:", e)
        return
    if not rows:
        return
    log("📮 밀린 후원 %d건을 다시 보냅니다." % len(rows))
    left = []
    for i, ln in enumerate(rows):
        try:
            payload = json.loads(ln)
        except Exception:
            continue   # 깨진 줄은 버린다(되살릴 방법이 없다)
        if send_once(payload):
            log("   ✅ 재전송 성공:", payload.get("name"), payload.get("amount"))
        else:
            left.extend(rows[i:])   # 하나라도 실패하면 순서를 지키려고 나머지는 그대로 둔다
            break
    try:
        if left:
            with open(SPOOL_FILE, "w", encoding="utf-8") as f:
                f.write("\n".join(left) + "\n")
            log("📮 아직 %d건이 대기줄에 남아 있습니다." % len(left))
        else:
            os.remove(SPOOL_FILE)
            log("📮 대기줄을 모두 비웠습니다.")
    except Exception as e:
        log("⚠️ 대기줄 정리 실패:", e)


def deliver(payload):
    """후원 한 건을 책임지고 넘긴다. 끝까지 안 되면 파일에 적어둔다."""
    if send_once(payload):
        spool_drain()   # 서버가 살아 있는 것을 확인했으니 밀린 것도 같이 보낸다
        return True
    for d in RETRY_DELAYS:
        time.sleep(d)
        log("   ↻ 다시 보냅니다 (%.1f초 뒤)" % d)
        if send_once(payload):
            spool_drain()
            return True
    spool_add(payload)
    return False

async def listen(token):
    url = "wss://ws.toon.at/" + token
    global _connected_at
    async with websockets.connect(url, open_timeout=15, ping_interval=20) as ws:
        _connected_at = time.time()
        # 끊겨 있던 동안 못 보낸 후원이 있으면 먼저 흘려보낸다
        spool_drain()
        log("✅ 연결됨 →", DONATION_URL, "(dry-run)" if DRY else "",
            "| 재전송 방어 {}초".format(REPLAY_GUARD_AFTER_RECONNECT)
            if REPLAY_GUARD_AFTER_RECONNECT > 0 else "| 재전송 방어 꺼짐")
        async for raw in ws:
            try:
                msg = json.loads(raw)
            except Exception:
                continue
            payload, is_test, skip = to_donation(msg)
            if payload is None:
                if skip == "replay":
                    # 조용히 버리면 방송이 끝난 뒤에야 알게 된다. 재연결 직후에만 나오는 로그다.
                    log("⚠️ 재연결 직후라 '재전송'으로 보고 버렸습니다 —",
                        "진짜 후원이었다면 후원 콘솔에서 수동 송출해 주세요.")
                continue
            tag = "[테스트] " if is_test else ""
            # ⚠️ 계좌/투네이션 구분용 힌트. 내일 진짜 계좌 후원이 들어오면 이 값으로 식별한다.
            c = msg.get("content") or {}
            hint = "acctype={} level={} code={}".format(
                c.get("acctype"), c.get("level"), msg.get("code"))
            log("💰 후원 감지:", tag + payload["name"], payload["amount"], "캐시",
                repr(payload["message"][:30]), "|", hint)
            # ⚠️ 서버(/api/donation)는 음수만 막고 소액은 안 거른다. 예전에는 템퍼몽키가
            #    소액을 걸러서 서버까지 오지도 않았다. 리스너로 갈아타면서 그 체가
            #    사라지면 100원짜리 후원까지 팝업·장부·대기함에 들어온다. 여기서 이어받는다.
            if MIN_AMOUNT > 0 and 0 < payload["amount"] < MIN_AMOUNT:
                log(f"   → {MIN_AMOUNT:,}원 미만이라 무시 (MIN_AMOUNT=0 으로 끌 수 있음)")
                continue
            if is_test and not INCLUDE_TEST:
                log("   → 테스트라 서버 전송 생략 (INCLUDE_TEST=1 로 켤 수 있음). 파이프라인은 정상.")
                continue
            if DRY:
                log("   → [dry] 보낼 내용:", json.dumps(payload, ensure_ascii=False))
                continue
            # ⚠️ 반드시 딴 갈래(스레드)에서 부른다.
            #    deliver 는 통신(최대 10초) + 재시도가 들어 있어 오래 걸리는데,
            #    여기서 그냥 부르면 그동안 이 async 루프가 통째로 멈춘다.
            #    그러면 웹소켓이 ping 에 답하지 못해 연결이 끊긴다 — 하필
            #    후원이 쏟아지는 바로 그 순간에.
            #    (실측: 응답 없는 서버에 후원 1건이면 루프가 20.8초, 3건이면 62초 정지.
            #     ping 간격이 20초라 첫 건에서 이미 끊긴다. to_thread 로는 0.2초)
            await asyncio.to_thread(deliver, payload)

async def spool_watcher():
    """후원이 한동안 없어도 밀린 것이 계속 묶여 있지 않게 주기적으로 다시 시도한다."""
    while True:
        await asyncio.sleep(10)
        try:
            # 여기도 같은 이유로 딴 갈래에서. 밀린 것이 많으면 한 건에 10초씩 걸린다.
            await asyncio.to_thread(spool_drain)
        except Exception as e:
            log("⚠️ 대기줄 재시도 중 오류:", e)


async def main():
    if not ALERTBOX_URL:
        print("ALERTBOX_URL 환경변수가 필요합니다."); return
    asyncio.create_task(spool_watcher())
    token = fetch_token(ALERTBOX_URL)
    log("토큰 %d자 확보. ws.toon.at 접속 시작." % len(token))
    while True:
        try:
            await listen(token)
        except Exception as e:
            log("연결 끊김:", type(e).__name__, "- 3초 후 재연결")
            await asyncio.sleep(3)
        # 토큰이 만료됐을 수 있으니 재연결 때 새로 받는다
        try:
            token = fetch_token(ALERTBOX_URL)
        except Exception as e:
            log("토큰 갱신 실패:", e)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n종료")
