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
import os, sys, re, json, time, asyncio, hashlib, urllib.request

try:
    import websockets
except ImportError:
    print("먼저: pip install websockets"); sys.exit(1)

ALERTBOX_URL = os.environ.get("ALERTBOX_URL", "")
DONATION_URL = os.environ.get("DONATION_URL", "http://127.0.0.1:8080/api/donation")
INCLUDE_TEST = os.environ.get("INCLUDE_TEST", "").strip() in ("1", "on", "true", "yes")
DRY = "--dry" in sys.argv

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
    # 고유 id 가 없을 때만, 짧은 시간 내 동일 후원 재수신을 소켓 재전송으로 보고 버린다
    if stable is None and ident in _recent and now - _recent[ident] < REPLAY_TTL:
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

async def listen(token):
    url = "wss://ws.toon.at/" + token
    async with websockets.connect(url, open_timeout=15, ping_interval=20) as ws:
        log("✅ 연결됨 →", DONATION_URL, "(dry-run)" if DRY else "")
        async for raw in ws:
            try:
                msg = json.loads(raw)
            except Exception:
                continue
            payload, is_test, skip = to_donation(msg)
            if payload is None:
                if skip == "replay":
                    log("· 소켓 재전송으로 보이는 중복 후원 무시")
                continue
            tag = "[테스트] " if is_test else ""
            log("💰 후원 감지:", tag + payload["name"], payload["amount"], "캐시",
                repr(payload["message"][:30]))
            if is_test and not INCLUDE_TEST:
                log("   → 테스트라 서버 전송 생략 (INCLUDE_TEST=1 로 켤 수 있음). 파이프라인은 정상.")
                continue
            if DRY:
                log("   → [dry] 보낼 내용:", json.dumps(payload, ensure_ascii=False))
                continue
            try:
                st, body = post_donation(payload)
                log("   → 서버 응답", st, body)
            except Exception as e:
                log("   ❌ 전송 실패:", type(e).__name__, e)

async def main():
    if not ALERTBOX_URL:
        print("ALERTBOX_URL 환경변수가 필요합니다."); return
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
