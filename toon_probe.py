# -*- coding: utf-8 -*-
"""
투네이션 후원을 '크롬 없이' 서버가 직접 받는 방식의 탐침(probe).

  1) 알림창 페이지를 HTTP GET 해서 소켓 토큰을 꺼내고
  2) wss://ws.toon.at/<토큰> 에 붙어
  3) 후원 packet 이 올 때만 골라서 찍는다.

목적: 후원 packet 이 '정확히 어떻게 생겼는지' 한 번 보는 것.
      투네이션 대시보드 > 통합알림창 > 후원 테스트 를 누르면 여기 찍힌다.

사용:
  pip install websockets
  python toon_probe.py https://toon.at/widget/alertbox/<내알림창키>

⚠️ 연결 직후 오는 'type 0' 설정 메시지에는 구글 OAuth 토큰·이메일이 들어 있다.
   이 스크립트는 그걸 자동으로 가려서 안 보여준다. 그래도 출력을 남에게 주지 말 것.
⚠️ 투네이션의 비공개 규격이라 그쪽이 바꾸면 끊길 수 있다(공식 API 아님).
"""
import sys, re, json, asyncio, urllib.request

try:
    import websockets
except ImportError:
    print("먼저: pip install websockets"); sys.exit(1)

ALERT_URL = sys.argv[1] if len(sys.argv) > 1 else ""

SENSITIVE = ("token", "value", "extern_key", "account", "access_token", "payload")
def redact(o):
    """혹시 모를 토큰·계정 값을 재귀적으로 가린다."""
    if isinstance(o, dict):
        return {k: ("***가림***" if k in SENSITIVE and isinstance(v, (str,)) and len(v) > 12
                    else redact(v)) for k, v in o.items()}
    if isinstance(o, list):
        return [redact(x) for x in o]
    return o

def fetch_token(alert_url):
    req = urllib.request.Request(alert_url, headers={"User-Agent": "Mozilla/5.0"})
    html = urllib.request.urlopen(req, timeout=15).read().decode("utf-8", "replace")
    m = re.search(r'window\.payload\s*=\s*JSON\.parse\(\s*"(.*?)"\s*\)', html, re.S)
    if not m:
        raise RuntimeError("window.payload 를 못 찾음 - 알림창 주소 확인")
    obj = json.loads(json.loads('"' + m.group(1) + '"'))
    tok = obj.get("payload")
    if not tok:
        raise RuntimeError("소켓 토큰이 비어있음")
    return tok, obj

async def listen(token):
    url = "wss://ws.toon.at/" + token
    print("연결 시도: wss://ws.toon.at/<토큰 %d자>" % len(token))
    async with websockets.connect(url, open_timeout=15, ping_interval=20) as ws:
        print("✅ 연결됨. 대시보드 > 통합알림창 > '후원 테스트' 를 눌러보세요.")
        print("   (연결 직후 오는 설정값은 건너뜁니다. 후원만 아래에 찍힙니다.)\n")
        async for raw in ws:
            try:
                msg = json.loads(raw)
            except Exception:
                print("(파싱불가 원본)", str(raw)[:300]); continue

            t = msg.get("type")
            # type 0 = 접속 시 설정 뭉치(민감정보 포함). 요약만.
            if t == 0:
                print("· 설정 수신(type 0) — 후원 아님, 건너뜀\n"); continue

            print("═" * 60)
            print("★ 후원 packet 도착 (type = %s)" % t)
            print("─" * 60)
            print(json.dumps(redact(msg), ensure_ascii=False, indent=2)[:4000])
            print("═" * 60 + "\n")

async def main():
    if not ALERT_URL:
        print("사용법: python toon_probe.py https://toon.at/widget/alertbox/<키>"); return
    token, obj = fetch_token(ALERT_URL)
    print("uid:", obj.get("uid", "")[:10], "... / 토큰 %d자 확보" % len(token))
    while True:
        try:
            await listen(token)
        except Exception as e:
            print("연결 끊김:", type(e).__name__, "- 3초 후 재연결")
            await asyncio.sleep(3)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n종료")
