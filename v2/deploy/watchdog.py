# -*- coding: utf-8 -*-
"""🩹 감시 장치(watchdog) — 방송 서버 안에서 1분마다 돌며 **죽은 것만** 다시 켠다. 대표님 결정(10-07): 방송 중에도.

왜 필요한가
  systemd 의 Restart=always 는 프로그램이 **꺼졌을 때**만 다시 켠다. 켜져는 있는데 답을 안 하는 것(멈춤)은 못 본다.
  — 9/30 끊긴 연결이 쌓여 점수가 안 들어간 날, 서버는 '켜져' 있었다.
보는 것(1분마다)
  ① 옛 방송 서버  127.0.0.1:8080/api/health  — 3번 연속(3분) 답이 없으면 livemaster 다시 켜기(리스너 · 진행봇도 따라 켜진다)
  ② v2 서버       127.0.0.1:5300/api/health  — 켜 둔 경우만 · 3번 연속이면 livemaster-v2 다시 켜기
  ③ 투네이션 리스너 toon_listener_status.json — 3분 넘게 소식이 없거나(멈춤) 10분 넘게 '연결 안 됨'이면 toon-listener 다시 켜기
     (못 보낸 후원은 리스너가 파일에 적어 뒀다 다시 보낸다 — 다시 켜도 후원은 안 사라진다)
  ④ 알림만: 디스크 1GB 미만 · 8080 의 반쯤 끊긴 연결(CLOSE-WAIT) 100개 넘음
  ⑤ 요약 알림(한국 시각): 수요일 16시 '방송 전 점검' · 목요일 4시 '방송 끝 정리'(밤사이 다시 켠 일 · 지금 상태)
안전 장치
  - 한 서비스를 1시간에 3번 넘게 다시 켜지 않는다 — 넘으면 멈추고 '사람이 봐야 해요' 만 알린다(다시 켜기를 무한히 돌지 않게).
  - 코드를 바꾸거나 올리지 않는다. 설정도 안 바꾼다. 하는 일은 `systemctl restart <서비스>` 뿐.
기록 · 알림
  - /var/lib/livemaster-watchdog/events.jsonl(최근 200줄) — v2 /health 상태판이 마지막 몇 줄을 보여 준다(이름 · 금액 같은 건 없다).
  - NOTIFY_URL(/etc/livemaster.env)이 있으면 그 주소로 한 줄 보낸다(ntfy 같은 폰 알림 — 없으면 기록만).
"""
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.request

STATE_DIR = os.environ.get('WATCHDOG_DIR', '/var/lib/livemaster-watchdog')
APP_DIR = os.environ.get('APP_DIR', '/opt/livemaster')
STATUS_FILE = os.environ.get('TOON_STATUS_FILE') or os.path.join(APP_DIR, 'toon_listener_status.json')
OLD_URL = os.environ.get('WATCHDOG_OLD_URL', 'http://127.0.0.1:8080/api/health')
V2_URL = os.environ.get('WATCHDOG_V2_URL', 'http://127.0.0.1:5300/api/health')
FAILS_BEFORE_RESTART = 3          # 1분마다 → 3분 연속 답이 없으면
RESTARTS_PER_HOUR = 3
LISTENER_STALE_SEC = 180          # 리스너는 10초마다 상태를 적는다 — 3분 넘게 안 적었으면 멈춘 것
LISTENER_DOWN_SEC = 600           # 10분 넘게 '연결 안 됨'이면 리스너 혼자 못 붙는 것으로 본다
DISK_MIN_GB = 1.0
CLOSE_WAIT_WARN = 100
EVENTS_MAX = 200


# ── 바깥과 닿는 곳(검사가 가짜로 바꿔 끼운다) ──
def http_ok(url, timeout=5):
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return r.status == 200
    except Exception:
        return False


def run(cmd, timeout=60):
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return r.returncode, (r.stdout or '') + (r.stderr or '')
    except Exception as e:
        return 1, str(e)


def unit_enabled(unit):
    return run(['systemctl', 'is-enabled', '--quiet', unit])[0] == 0


def restart(unit):
    return run(['systemctl', 'restart', unit], timeout=90)


def close_wait_8080():
    code, out = run(['ss', '-tan', 'state', 'close-wait', '( sport = :8080 )'])
    return max(0, len([l for l in out.splitlines() if l.strip()]) - 1) if code == 0 else 0


def disk_free_gb(path='/'):
    try:
        return shutil.disk_usage(path).free / 1024 ** 3
    except Exception:
        return 99.0


PRIORITY = {'gaveup': '5', 'restart_failed': '5', 'restart': '4', 'warn': '4', 'recovered': '3', 'summary': '3'}


def notify(text, kind=''):
    """폰 알림(ntfy 모양 — 본문 한 줄 · Title · Priority). NOTIFY_URL 이 없으면 아무것도 안 한다."""
    url = (os.environ.get('NOTIFY_URL') or '').strip()
    if not url:
        return
    try:
        req = urllib.request.Request(url, data=text.encode('utf-8'), method='POST',
                                     headers={'Title': 'Live Master', 'Priority': PRIORITY.get(kind, '3'),
                                              'Content-Type': 'text/plain; charset=utf-8'})
        urllib.request.urlopen(req, timeout=10).read()
    except Exception as e:
        print('[알림 실패] %s' % type(e).__name__, flush=True)


# ── 기억(연속 실패 수 · 다시 켠 때 · 알림 보낸 때) ──
def load_state():
    try:
        with open(os.path.join(STATE_DIR, 'state.json'), encoding='utf-8') as f:
            s = json.load(f)
        return s if isinstance(s, dict) else {}
    except Exception:
        return {}


def save_state(s):
    os.makedirs(STATE_DIR, exist_ok=True)
    p = os.path.join(STATE_DIR, 'state.json')
    tmp = p + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(s, f, ensure_ascii=False)
    os.replace(tmp, p)


def event(kind, text, now):
    """기록 한 줄 + journal + (있으면) 폰 알림. 이름 · 금액 같은 개인 정보는 안 쓴다."""
    os.makedirs(STATE_DIR, exist_ok=True)
    p = os.path.join(STATE_DIR, 'events.jsonl')
    rows = []
    try:
        with open(p, encoding='utf-8') as f:
            rows = [l for l in f if l.strip()][-(EVENTS_MAX - 1):]
    except FileNotFoundError:
        pass
    rows.append(json.dumps({'at': int(now), 'kind': kind, 'text': text}, ensure_ascii=False) + '\n')
    tmp = p + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        f.writelines(rows)
    os.replace(tmp, p)
    print('[%s] %s' % (kind, text), flush=True)
    notify(text, kind)


def due(s, key, every, now):
    """같은 알림을 every 초에 한 번만 — 처음이면 바로."""
    last = s.get(key)
    if last is None or now - last > every:
        s[key] = now
        return True
    return False


def may_restart(s, unit, now):
    hist = [t for t in s.setdefault('restarts', {}).get(unit, []) if now - t < 3600]
    s['restarts'][unit] = hist
    return len(hist) < RESTARTS_PER_HOUR


def do_restart(s, unit, why, now):
    if not may_restart(s, unit, now):
        if due(s, 'gaveup_' + unit, 3600, now):
            event('gaveup', '🆘 %s 를 1시간에 %d번 다시 켜도 안 살아나요 — 사람이 봐야 해요 (%s)' % (unit, RESTARTS_PER_HOUR, why), now)
        return False
    code, out = restart(unit)
    s['restarts'][unit].append(now)
    if code == 0:
        event('restart', '🩹 %s 를 다시 켰어요 — %s' % (unit, why), now)
    else:
        event('restart_failed', '⚠️ %s 다시 켜기 실패 — %s · %s' % (unit, why, out.strip()[:120]), now)
    return code == 0


def check_http(s, name, url, unit, now):
    fails = s.setdefault('fails', {})
    if http_ok(url):
        if fails.get(name, 0) >= FAILS_BEFORE_RESTART:
            event('recovered', '✅ %s 가 다시 답해요' % unit, now)
        fails[name] = 0
        return
    fails[name] = fails.get(name, 0) + 1
    if fails[name] >= FAILS_BEFORE_RESTART:
        if do_restart(s, unit, '%d분째 답이 없어서' % fails[name], now):
            fails[name] = 0


def check_listener(s, now):
    if not unit_enabled('toon-listener'):
        return
    try:
        with open(STATUS_FILE, encoding='utf-8') as f:
            st = json.load(f)
    except FileNotFoundError:
        return                                   # 이 서버엔 리스너 상태 파일이 없다(안 쓰는 서버)
    except Exception:
        st = {}
    age = now - float(st.get('updated') or 0)
    main = ((st.get('accounts') or {}).get('main') or {}) if isinstance(st, dict) else {}
    if age > LISTENER_STALE_SEC:
        if do_restart(s, 'toon-listener', '%d분째 상태를 안 적어서(멈춤)' % (age // 60), now):
            s.pop('listener_down_since', None)
        return
    if main.get('state') == 'connected':
        if s.pop('listener_down_since', None):
            event('recovered', '✅ 투네이션 연결이 돌아왔어요', now)
        return
    since = s.setdefault('listener_down_since', now)
    if now - since > LISTENER_DOWN_SEC:
        if do_restart(s, 'toon-listener', '투네이션 연결이 %d분째 안 돼서' % ((now - since) // 60), now):
            s['listener_down_since'] = now


def check_warnings(s, now):
    gb = disk_free_gb()
    if gb < DISK_MIN_GB and due(s, 'warn_disk', 86400, now):
        event('warn', '💾 서버 디스크가 %.1fGB 밖에 안 남았어요' % gb, now)
    cw = close_wait_8080()
    if cw > CLOSE_WAIT_WARN and due(s, 'warn_cw', 1800, now):
        event('warn', '🔌 방송 서버에 반쯤 끊긴 연결이 %d개 쌓였어요(9/30 같은 일 조심)' % cw, now)


def _restarts_since(s, since):
    return {u: len([t for t in ts if t >= since]) for u, ts in (s.get('restarts') or {}).items() if any(t >= since for t in ts)}


def _status_line(s, now):
    old = http_ok(OLD_URL)
    parts = ['방송 서버 ' + ('✅' if old else '❌ 답 없음')]
    if unit_enabled('livemaster-v2'):
        parts.append('v2 ' + ('✅' if http_ok(V2_URL) else '❌ 답 없음'))
    if unit_enabled('toon-listener'):
        parts.append('투네이션 ' + ('❌ 연결 안 됨 (%d분째)' % ((now - s['listener_down_since']) // 60) if s.get('listener_down_since') else '✅ 연결됨'))
    parts.append('디스크 %.0fGB' % disk_free_gb())
    return ' · '.join(parts)


def check_summaries(s, now):
    """수요일 16시 방송 전 점검 · 목요일 4시 방송 끝 정리(한국 시각, 하루에 한 번씩)."""
    t = time.gmtime(now + 9 * 3600)
    day = time.strftime('%Y-%m-%d', t)
    if t.tm_wday == 2 and t.tm_hour == 16 and s.get('sum_pre') != day:
        s['sum_pre'] = day
        r = _restarts_since(s, now - 86400)
        event('summary', '📋 방송 전 점검 — ' + _status_line(s, now)
              + (' · 하루 사이 다시 켠 일: ' + ', '.join('%s %d번' % kv for kv in r.items()) if r else ' · 하루 사이 다시 켠 일 없음'), now)
    if t.tm_wday == 3 and t.tm_hour == 4 and s.get('sum_post') != day:
        s['sum_post'] = day
        r = _restarts_since(s, now - 12 * 3600)
        event('summary', '🌙 방송 끝 정리 — ' + ('밤사이 다시 켠 일: ' + ', '.join('%s %d번' % kv for kv in r.items()) if r else '밤사이 다시 켠 일 없음')
              + ' · 지금 ' + _status_line(s, now), now)


def main(now=None):
    now = time.time() if now is None else now
    s = load_state()
    check_http(s, 'old', OLD_URL, 'livemaster', now)
    if unit_enabled('livemaster-v2'):
        check_http(s, 'v2', V2_URL, 'livemaster-v2', now)
    check_listener(s, now)
    check_warnings(s, now)
    check_summaries(s, now)
    s['last_run'] = int(now)
    save_state(s)
    return 0


if __name__ == '__main__':
    sys.exit(main())
