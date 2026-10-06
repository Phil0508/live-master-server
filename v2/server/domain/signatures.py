# -*- coding: utf-8 -*-
"""🎵 시그니처 목록 — Supabase(옛 서버와 같은 표 · 같은 열쇠).

⚠️ 바깥 왕복이라 **명령 밖에서** 부른다(asyncio.to_thread). 명령 안에서 부르면 그동안 모든 버튼이 멈춘다.
- 목록은 10분 기억한다. 실패하면 전에 알던 목록을 쓰고 1분 뒤에 다시 묻는다(후원마다 10초씩 기다리지 않게).
- 매칭: 후원금 이상 중 제일 싼 것(올림) → 없으면(최고가보다 큰 후원) 제일 비싼 것.
- 최저선: 제일 싼 시그니처 값, 단 1만 원을 못 넘는다. SIG_MIN_AMOUNT 로 덮어쓸 수 있다(0 = 최저선 없음).
"""
import os
import threading
import time

from .rules import SIG_ROUND_FLOOR

FIELDS = 'id,amount,title,image_url,sound_url,duration'


def _supabase_config():
    url = (os.environ.get('SUPABASE_URL') or '').strip().rstrip('/')
    key = (os.environ.get('SUPABASE_SECRET_KEY') or '').strip()
    if not url or not key:
        here = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
        p = os.path.join(here, 'SUPABASE_CREDENTIALS.txt')
        if os.path.exists(p):
            for line in open(p, encoding='utf-8'):
                line = line.strip()
                if line.startswith('#') or '=' not in line:
                    continue
                k, v = line.split('=', 1)
                v = v.split('#')[0].strip()
                if k.strip() == 'SUPABASE_URL' and not url:
                    url = v.rstrip('/')
                elif k.strip() == 'SUPABASE_SECRET_KEY' and not key:
                    key = v
    return url, key


def supabase_fetch():
    import requests
    url, key = _supabase_config()
    if not url or not key:
        return []
    r = requests.get('%s/rest/v1/signatures?select=%s&order=amount.asc' % (url, FIELDS),
                     headers={'apikey': key, 'Authorization': 'Bearer ' + key}, timeout=6)
    r.raise_for_status()
    return r.json()


class Signatures:
    def __init__(self, fetch=None, ttl=600, retry=60):
        self._fetch = fetch or supabase_fetch
        self.ttl, self.retry = ttl, retry
        self._rows, self._at, self._lock = None, 0.0, threading.Lock()
        self.last_error = ''

    def rows(self):
        now = time.time()
        with self._lock:
            if self._rows is not None and now - self._at < self.ttl:
                return self._rows
            try:
                rows = [r for r in (self._fetch() or []) if r.get('amount') is not None]
                rows.sort(key=lambda r: int(r.get('amount') or 0))
                self._rows, self._at, self.last_error = rows, now, ''
            except Exception as e:
                self.last_error = type(e).__name__
                self._rows = self._rows or []
                self._at = now - self.ttl + self.retry          # 1분 뒤에 다시
            return self._rows

    def refresh(self):
        """지금 바로 다시 받기 — 시그니처를 등록 · 고치기 · 지운 뒤(sigadmin.py). 실패하면 전에 알던 목록 그대로."""
        with self._lock:
            self._at = 0.0
        return self.rows()

    def floor(self):
        env = os.environ.get('SIG_MIN_AMOUNT')
        if env is not None:
            try:
                return max(0, int(env))
            except ValueError:
                pass
        rows = self.rows()
        if not rows:
            return 0
        return min(int(rows[0]['amount']), SIG_ROUND_FLOOR)

    def match(self, amount):
        rows = self.rows()
        if not rows or int(amount) <= 0:
            return None
        for r in rows:
            if int(r['amount']) >= int(amount):
                return r
        return rows[-1]

    def by_id(self, sid):
        return next((r for r in self.rows() if str(r.get('id')) == str(sid)), None)
