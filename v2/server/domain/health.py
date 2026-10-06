# -*- coding: utf-8 -*-
"""🩺 서버 상태판 — 폰으로 슬쩍 보는 무인증 페이지(옛 /health 그대로).

GET /health      브라우저면 페이지(web/health/index.html), 아니면 JSON
GET /api/health  JSON
담는 것   가동시간 · 메모리 · 장부(SQLite) SELECT 1 실측 · 화면 수 · 개수(선수 · 대기함 · 시그 대기줄 · 기록) ·
          지금 무대 · 방송 중인지 · 마지막 후원 몇 초 전 · 리스너 상태
⚠️ 담지 않는 것: 후원자 이름 · 금액 · 메시지 · 비밀번호 · 키 · 파일 경로. 무인증이라 남이 봐도 되는 것만.
"""
import time

from .preflight import listener, spool

def _rss_mb():
    """메모리(RSS) — 리눅스는 /proc, 그 밖엔 모름(None)."""
    try:
        with open('/proc/self/status', encoding='utf-8') as f:
            for ln in f:
                if ln.startswith('VmRSS:'):
                    return round(int(ln.split()[1]) / 1024, 1)
    except Exception:
        pass
    return None


def _db_ms(store):
    t = time.perf_counter()
    try:
        store.db.execute('SELECT 1').fetchone()
    except Exception:
        return None
    return round((time.perf_counter() - t) * 1000, 2)


def view(bus, boot):
    st = bus.state
    sess = st.get('session')
    show = st.get('show')
    lis = listener()
    last = None
    try:
        r = bus.store.db.execute('SELECT MAX(at) AS t FROM donations').fetchone()
        last = int(time.time() - float(r['t'])) if r and r['t'] else None
    except Exception:
        pass
    kinds = {}
    for c in list(bus.hub.clients):
        k = 'monitor' if c.monitor else c.kind
        kinds[k] = kinds.get(k, 0) + 1
    from .legacy import trial_on
    return {'ok': True, 'trial': trial_on(), 'uptime_sec': int(time.time() - boot), 'rss_mb': _rss_mb(),
            'db': {'kind': 'sqlite', 'ping_ms': _db_ms(bus.store)},
            'seq': st.seq, 'live': bool(sess.get('live')),
            'live_sec': int(time.time() - sess['started_at']) if sess.get('live') and sess.get('started_at') else None,
            'stage': show.get('stage'),
            'screens': dict(kinds, total=len(bus.hub.clients)), 'dropped': bus.hub.dropped,
            'counts': {'players': len(st.get('players').get('list') or []), 'pending': len(st.get('pending') or []),
                       'sig_queue': len(st.get('queue').get('items') or []), 'logs': len(st.get('logs') or [])},
            'last_donation_sec': last,
            'listener': {k: lis.get(k) for k in ('level', 'age_sec', 'state', 'connected_sec', 'last_donation_sec')},
            'spool': spool()}
