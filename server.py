import sys
# ✂️ `python server.py` 로 띄우면 이 파일의 이름은 server 가 아니라 __main__ 이다.
#    features/ 의 파일들이 `from server import …` 로 공용 도구를 빌려 가는데, 그때 이 파일을
#    **한 번 더** 읽어 들이면 app·잠금·상태가 두 벌이 되어 조용히 망가진다. 같은 것을 가리키게 묶어 둔다.
sys.modules.setdefault('server', sys.modules[__name__])
import os
import io

# GUI 모드(console=False)에서 발생하는 모든 에러를 파일로 로깅하여 크래시 분석
if getattr(sys, 'frozen', False):
    try:
        exe_dir = os.path.dirname(sys.executable)
        log_file = open(os.path.join(exe_dir, 'server_error.log'), 'w', encoding='utf-8', buffering=1)
        sys.stderr = log_file
        sys.stdout = log_file
    except Exception:
        pass
else:
    # 윈도우 콘솔 UTF-8 출력 강제 (cp949 이모지 에러 방지)
    try:
        if sys.stdout is not None and hasattr(sys.stdout, 'buffer'):
            sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
        if sys.stderr is not None and hasattr(sys.stderr, 'buffer'):
            sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')
    except Exception:
        pass

import json
import copy
import mimetypes
# 🎱 .wasm 을 제 종류(application/wasm)로 내보낸다 — 윈도우 · 일부 리눅스는 이 이름을 모른다.
#    모르면 브라우저가 빠른 길(스트리밍 컴파일)을 못 쓰고 경고를 띄운다(그래도 돌아가긴 한다).
mimetypes.add_type('application/wasm', '.wasm')
import re       # 후원 메시지에서 별명 후보 토막내기
import random   # 시그게임 카드 배치·섞기, 슬롯 당첨 뽑기
import math     # 시그게임 판을 정사각형에 가깝게 잡을 때
import select
import socket
import threading
import uuid
import logging
import secrets

import time
import datetime   # 월별 후원 순위 — 수요일 방송 창(수 17시~목 3시)을 셈한다
import csv
import queue
import shutil
import subprocess   # 버전 전환 때 git·systemctl 을 부른다
import sqlite3
from contextlib import contextmanager
import urllib.request
import urllib.parse

try:
    import requests
except ImportError:
    requests = None

# Try importing psycopg2 for PostgreSQL support
try:
    import psycopg2
except ImportError:
    psycopg2 = None

DATABASE_URL = os.environ.get('DATABASE_URL')
IS_POSTGRES = bool(DATABASE_URL)

# 서버가 언제 켜졌는지. /api/health 가 가동시간을 계산하는 데 쓴다.
# 이 값이 자꾸 0 근처면 서버가 계속 재시작되고 있다는 뜻이라 그 자체가 신호다.
SERVER_BOOT_TS = time.time()

def db_query(query):
    if IS_POSTGRES:
        return query.replace('?', '%s')
    return query

# ⚡ [연결 재사용] 예전에는 DB 작업마다 새 연결을 열고 닫았다.
# Render(오레곤)에서 Supabase(서울)까지는 TLS 핸드셰이크만 왕복 여러 번이라
# 연결 생성 하나가 쿼리 10개보다 비쌌고, 점수 저장이 2초를 넘겼다.
# 스레드마다 연결을 하나씩 살려두고 재사용한다. (Flask가 스레드로 요청을 처리하므로
# 연결을 공유하면 안 되고, 스레드 로컬이어야 안전하다)
_db_local = threading.local()

def _new_db_connection():
    if IS_POSTGRES:
        if psycopg2 is None:
            raise ImportError("psycopg2 is not installed but DATABASE_URL is set.")
        db_url = DATABASE_URL
        if 'sslmode=' not in db_url.lower():
            sep = '&' if '?' in db_url else '?'
            db_url += f"{sep}sslmode=require"
        return psycopg2.connect(db_url, connect_timeout=15)
    return sqlite3.connect(DB_FILE)

def _get_live_connection():
    """스레드에 살아있는 연결을 돌려준다. 끊겼으면 새로 연다.

    ⚠️ 여기서 'SELECT 1' 같은 확인 쿼리를 보내면 안 된다.
    매 작업마다 왕복이 하나 더 붙어서 연결 재사용으로 아낀 시간을 도로 까먹는다.
    서버가 유휴 연결을 끊은 경우는 실제 쿼리에서 예외로 드러나므로,
    호출부(save_data_sync 등)에서 한 번 재시도해 자가복구한다.
    """
    conn = getattr(_db_local, 'conn', None)
    if conn is not None and IS_POSTGRES and conn.closed:
        conn = None
    if conn is None:
        conn = _new_db_connection()
        _db_local.conn = conn
    return conn

@contextmanager
def get_db_connection():
    conn = _get_live_connection()
    try:
        yield conn
        conn.commit()
    except Exception:
        # 실패한 연결은 상태가 오염됐을 수 있으므로 버리고 다음에 새로 연다
        try: conn.rollback()
        except Exception: pass
        try: conn.close()
        except Exception: pass
        _db_local.conn = None
        raise
from flask import Flask, jsonify, request, send_from_directory, redirect, url_for, session
# 📺 방송 화면(무대·고정 자리·알림·순서표) 규칙은 show.py 한 곳에 있다 — server.py 를 쪼개는 첫 조각
import show as showmod
from werkzeug.exceptions import HTTPException
try:
    import tkinter as tk
    from tkinter import messagebox
except ImportError:
    tk = None
    messagebox = None
import webbrowser

if getattr(sys, 'frozen', False):
    BASE_DIR = os.path.dirname(sys.executable)
    BUNDLE_DIR = getattr(sys, '_MEIPASS', BASE_DIR)
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    BUNDLE_DIR = BASE_DIR

DB_FILE = os.path.join(BASE_DIR, 'live_master.db')
LAYOUT_FILE = os.path.join(BASE_DIR, 'layout.json')
AUTH_CONFIG_FILE = os.path.join(BASE_DIR, 'auth_config.json')

# ⚠️ 이 값은 '기본값'이라 저장소·백업·유저스크립트에 흔적이 남아 있어 사실상 공개된 문자열이다.
#    그런데 session_secret 은 Bearer 토큰으로도 쓰여서, 이 값이 그대로 쓰이는 동안에는
#    주소만 아는 사람이 점수 조작·전광판·방송 리셋까지 전부 통과할 수 있다.
#    Render 환경변수 SESSION_SECRET 을 넣으면 덮어써진다. 넣기 전까지는 아래에서 시끄럽게 경고한다.
#    (여기서 임의값을 자동 생성하지는 않는다 — Render 파일시스템은 재시작마다 초기화되므로
#     매 배포마다 값이 바뀌어 로그인 세션이 계속 끊긴다)
WEAK_DEFAULT_SECRET = 'isacbin_master_key_0508'
SECRET_IS_WEAK = False          # /api/server/status 로 노출해서 눈에 보이게 한다
AUTH_POSTURE_WARNED = False     # 로그인 잠금 상태 경고는 시작할 때 한 번만 찍는다

# 🔓 조종실 로그인은 비밀번호 하나다 — OTP 는 걷어냈다(대표님 2026-09-30 "너무 불편해").
#    운영 서버는 원래 OTP 를 강제하지 않아(빈칸이면 통과) 칸만 남아 헷갈렸다.
#    ⚠️ auth_config.json 에 남은 totp_secret 은 지우지 않는다 — '버전 되돌리기' 로 옛 버전에 가면 쓴다.
def load_auth_config():
    config = {
        'admin_password': '0508',
        'session_secret': WEAK_DEFAULT_SECRET,
    }
    if os.path.exists(AUTH_CONFIG_FILE):
        try:
            with open(AUTH_CONFIG_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                if 'admin_password' in data:
                    config['admin_password'] = data['admin_password']
                if 'session_secret' in data:
                    config['session_secret'] = data['session_secret']
        except Exception as e:
            print(f"Error reading auth config: {e}")
            
    env_password = os.environ.get('ADMIN_PASSWORD')
    if env_password:
        config['admin_password'] = env_password.strip()
        
    env_session_secret = os.environ.get('SESSION_SECRET')
    if env_session_secret:
        config['session_secret'] = env_session_secret.strip()
        
    global AUTH_POSTURE_WARNED
    if not AUTH_POSTURE_WARNED:
        AUTH_POSTURE_WARNED = True
        gripes = []
        if config['admin_password'] == '0508':
            gripes.append("조종실 비밀번호가 공개된 기본값 '0508' 입니다. ADMIN_PASSWORD 를 넣어주세요.")
        if gripes:
            print("=" * 70, flush=True)
            for g in gripes:
                print(f"⚠️  {g}", flush=True)
            print("=" * 70, flush=True)

    global SECRET_IS_WEAK
    weak = (config['session_secret'] == WEAK_DEFAULT_SECRET)
    if weak and not SECRET_IS_WEAK:
        # 한 번만 크게 알린다(이 함수는 요청마다 불린다)
        print("=" * 70, flush=True)
        print("⚠️  관리자 키가 '공개된 기본값'입니다. 주소만 알면 점수·전광판·리셋이 통과됩니다.", flush=True)
        print("    Render 환경변수 SESSION_SECRET 에 새 값을 넣어주세요.", flush=True)
        print("=" * 70, flush=True)
    SECRET_IS_WEAK = weak

    return config

# ⚠️ auth_config.json 에는 아무것도 쓰지 않는다. 예전에는 OTP 키(totp_secret)를 적었고, 그보다 전에는
#    config 를 통째로 써서 환경변수로 넣은 운영 비밀번호(ADMIN_PASSWORD) · 관리자 키(SESSION_SECRET)가
#    평문으로 적혔다(저장소에 추적되는 파일이다). 비밀은 환경변수로만 둔다.

# ==========================================
# 🟢 Supabase 시그니처 연동 (Storage + PostgREST)
#    - 시그니처 데이터/미디어는 Supabase 에 있고, 서버는 secret 키로 대신 조회한다.
#    - 브라우저(오버레이/컨트롤러)는 같은 서버의 /api/signatures 만 호출 → 키 노출/CORS/Mixed-Content 없음
# ==========================================
def load_supabase_config():
    cfg = {
        'url': (os.environ.get('SUPABASE_URL') or '').strip().rstrip('/'),
        'key': (os.environ.get('SUPABASE_SECRET_KEY') or '').strip(),
    }
    # 로컬 개발 편의: 환경변수가 없으면 SUPABASE_CREDENTIALS.txt 에서 읽는다 (git 제외 파일)
    if not cfg['url'] or not cfg['key']:
        cred_path = os.path.join(BASE_DIR, 'SUPABASE_CREDENTIALS.txt')
        if os.path.exists(cred_path):
            try:
                with open(cred_path, 'r', encoding='utf-8') as f:
                    for line in f:
                        line = line.strip()
                        if line.startswith('#') or '=' not in line:
                            continue
                        k, v = line.split('=', 1)
                        k = k.strip(); v = v.split('#')[0].strip()
                        if k == 'SUPABASE_URL' and not cfg['url']:
                            cfg['url'] = v.rstrip('/')
                        elif k == 'SUPABASE_SECRET_KEY' and not cfg['key']:
                            cfg['key'] = v
            except Exception as e:
                print(f"[Supabase 설정 읽기 오류] {e}")
    return cfg

SUPABASE = load_supabase_config()

def _supabase_ready():
    return bool(SUPABASE['url'] and SUPABASE['key'] and requests)

def _supabase_headers():
    return {'apikey': SUPABASE['key'], 'Authorization': f"Bearer {SUPABASE['key']}"}

def supabase_list_signatures():
    """전체 시그니처 목록 (금액 오름차순). 실패/미설정 시 빈 리스트."""
    if not _supabase_ready():
        return []
    url = (f"{SUPABASE['url']}/rest/v1/signatures"
           f"?select=id,amount,title,image_url,sound_url,duration&order=amount.asc")
    r = requests.get(url, headers=_supabase_headers(), timeout=10)
    r.raise_for_status()
    return r.json()

SIG_FIELDS = 'id,amount,title,image_url,sound_url,duration'

def _supabase_query(params, retries=1):
    """PostgREST GET 헬퍼. 결과 리스트 반환.
       후원 매칭은 방송 중 필수 경로라 일시적 네트워크 오류 시 1회 재시도한다."""
    last_err = None
    for attempt in range(retries + 1):
        try:
            # 방송 중 후원 경로에서 쓰이므로 오래 기다리지 않는다.
            # 12초씩 두 번 기다리면 시그니처가 나올 때쯤엔 이미 방송 흐름이 지나가 있다.
            r = requests.get(f"{SUPABASE['url']}/rest/v1/signatures?{params}",
                             headers=_supabase_headers(), timeout=4)
            r.raise_for_status()
            return r.json()
        except Exception as e:
            last_err = e
            if attempt < retries:
                print(f"⚠️ [Supabase 조회 재시도] {e}")
                time.sleep(0.5)
    raise last_err

_SIG_CHEAPEST = {'amount': None, 'at': 0.0}
# 💛 시그니처 최저선의 **상한**. 자료에서 끌어온 최저가가 이보다 비싸도 이 금액이면 튼다.
#    제일 싼 시그니처가 10,300원이라 제일 흔한 후원 금액인 '만원'이 통째로 빠졌다.
SIG_ROUND_FLOOR = 10000


def _sig_min_amount():
    """시그니처가 재생되는 최저 후원 금액.

    기본은 **전체에서 제일 싼 시그니처 값** 이다 — 숫자를 손으로 정하지 않으려고 자료에서 끌어온다.
    ⚠️ '후원금 이상 중 제일 싼 것'(gte 결과) 을 쓰면 안 된다. 15,000원 후원에 15,100원짜리가
       걸리는데 그걸 최저선으로 삼으면 정상 후원이 통째로 막힌다.
    ⚠️ 값이 자주 바뀌지 않으므로 10분 기억한다(서울까지 왕복이 비싸다).
    ⚠️ SIG_MIN_AMOUNT 환경변수로 덮어쓸 수 있다. 0 이면 최저선 없음(예전 동작).
    """
    env = os.environ.get('SIG_MIN_AMOUNT')
    if env is not None:
        try:
            return max(0, int(env))
        except (TypeError, ValueError):
            pass
    now = time.time()
    if _SIG_CHEAPEST['amount'] is not None and now - _SIG_CHEAPEST['at'] < 600:
        return _SIG_CHEAPEST['amount']
    val = 0
    try:
        # ⚠️ _supabase_query 를 직접 부르면 안 된다. 검사 샌드박스는 supabase_list_signatures
        #    쪽을 갈아끼우므로, 직접 부르면 검사에서 최저선이 통째로 안 걸린다(실제로 그랬다).
        #    이 목록은 금액 오름차순이라 첫 줄이 제일 싼 것이다.
        rows = supabase_list_signatures() or []
        amounts = [int(r.get('amount') or 0) for r in rows if r.get('amount') is not None]
        if amounts:
            val = max(0, min(amounts))
    except Exception as e:
        # ⚠️ 실패도 1분 기억한다 — 안 그러면 Supabase 가 죽어 있는 동안 후원이 올 때마다 10초씩 기다린다(10-06 점검).
        #    전에 알아 둔 값이 있으면 그걸 쓴다(낡은 값이 '최저선 없음' 보다 낫다). 처음부터 모르면 예전처럼 0(최저선 없음).
        old = _SIG_CHEAPEST['amount']
        val = old if old is not None else 0
        _SIG_CHEAPEST.update({'amount': val, 'at': now - 540})     # 600 - 540 = 60초 뒤에 다시 물어본다
        print(f'⚠️ [시그니처 최저가 조회 실패 — {"전에 알던 " + format(val, ",") + "원으로" if val else "최저선 없이"} 진행 · 1분 뒤 다시] {e}', flush=True)
        return val
    # 💛 '만원'은 특수 취급한다(사장님: "10000원 같은 경우엔 특수경우로 최저 리액션으로").
    #    제일 싼 시그니처가 10,300원이면 만원을 낸 사람은 아무것도 못 받고 전광판으로만 갔다.
    #    최저선을 SIG_ROUND_FLOOR 위로 못 올라가게 눌러서 10,000~10,299원 구간을 연다.
    #    그 금액이면 supabase_match_signature 가 '이상 중 제일 싼 것' = 최저 시그를 고른다.
    # ⚠️ SIG_MIN_AMOUNT 로 직접 정한 값은 위에서 이미 돌려줬다 — 여기 안 걸린다(일부러).
    if val:
        val = min(val, SIG_ROUND_FLOOR)
    _SIG_CHEAPEST.update({'amount': val, 'at': now})
    return val


def supabase_match_signature(amount):
    """금액 매칭: ① 정확히 일치하거나, 없으면 올림(이상 중 가장 가까운)
       → ② 그래도 없으면(최고가 초과 후원) 가장 비싼 시그니처.

    ⚠️ 예전에는 '정확히 일치' 쿼리를 따로 먼저 보냈는데,
    아래 gte + 오름차순 + limit 1 이 정확히 일치하는 값을 이미 첫 번째로 돌려주므로
    같은 결과를 얻으려고 왕복을 한 번 더 쓴 셈이었다. (서울까지 왕복이라 비싸다)
    """
    if not _supabase_ready():
        return None
    amount = int(amount)
    rows = _supabase_query(f"amount=gte.{amount}&order=amount.asc&limit=1&select={SIG_FIELDS}")
    if rows:
        return rows[0]
    rows = _supabase_query(f"order=amount.desc&limit=1&select={SIG_FIELDS}")
    return rows[0] if rows else None

def supabase_get_signature(sig_id):
    """id로 시그니처 1개 조회."""
    if not _supabase_ready():
        return None
    rows = _supabase_query(f"id=eq.{int(sig_id)}&limit=1&select={SIG_FIELDS}")
    return rows[0] if rows else None

def supabase_insert_signature(fields):
    """시그니처 행 삽입 후 생성된 행(id 포함) 반환."""
    r = requests.post(f"{SUPABASE['url']}/rest/v1/signatures",
                      headers={**_supabase_headers(),
                               'Content-Type': 'application/json',
                               'Prefer': 'return=representation'},
                      json=fields, timeout=15)
    r.raise_for_status()
    rows = r.json()
    return rows[0] if rows else None

def supabase_update_signature(sig_id, fields):
    r = requests.patch(f"{SUPABASE['url']}/rest/v1/signatures?id=eq.{int(sig_id)}",
                       headers={**_supabase_headers(),
                                'Content-Type': 'application/json',
                                'Prefer': 'return=representation'},
                       json=fields, timeout=15)
    r.raise_for_status()
    rows = r.json()
    return rows[0] if rows else None

def supabase_delete_signature(sig_id):
    r = requests.delete(f"{SUPABASE['url']}/rest/v1/signatures?id=eq.{int(sig_id)}",
                        headers=_supabase_headers(), timeout=15)
    r.raise_for_status()
    return True

# ------- Supabase Storage (media 버킷) -------
STORAGE_BUCKET = 'media'

# 미디어 캐시 기간: 1년.
# Supabase 기본값은 1시간이라, 오버레이를 새로고침할 때마다 99개(약 70MB)를 다시 받아
# 무료 전송량 5GB를 금방 소진한다. 파일을 교체하면 URL 뒤에 ?v=타임스탬프가 새로 붙으므로
# 길게 캐시해도 변경은 즉시 반영된다.
MEDIA_CACHE_CONTROL = 'public, max-age=31536000, immutable'

def storage_upload(path, data, content_type):
    """Storage 업로드 후 공개 URL 반환."""
    r = requests.post(f"{SUPABASE['url']}/storage/v1/object/{STORAGE_BUCKET}/{path}",
                      data=data,
                      headers={**_supabase_headers(),
                               'Content-Type': content_type,
                               'Cache-Control': MEDIA_CACHE_CONTROL,
                               'x-upsert': 'true'},
                      timeout=120)
    if r.status_code not in (200, 201):
        raise RuntimeError(f"Storage 업로드 실패 {r.status_code}: {r.text[:200]}")
    return f"{SUPABASE['url']}/storage/v1/object/public/{STORAGE_BUCKET}/{path}"

def storage_delete_by_url(url):
    """공개 URL로부터 Storage 경로를 역산해 삭제 (실패는 무시)."""
    if not url:
        return
    marker = f"/storage/v1/object/public/{STORAGE_BUCKET}/"
    if marker not in url:
        return
    path = url.split(marker, 1)[1].split('?')[0]
    try:
        requests.delete(f"{SUPABASE['url']}/storage/v1/object/{STORAGE_BUCKET}/{path}",
                        headers=_supabase_headers(), timeout=30)
    except Exception as e:
        print(f"[Storage 삭제 무시] {e}")

def compress_image_to_webp(file_storage, max_dim=1280, quality=82):
    """업로드된 이미지를 WebP로 축소·압축. Pillow 없으면 원본 바이트 그대로."""
    raw = file_storage.read()
    try:
        from PIL import Image
        im = Image.open(io.BytesIO(raw))
        if im.mode in ('P', 'LA'):
            im = im.convert('RGBA')
        elif im.mode == 'CMYK':
            im = im.convert('RGB')
        w, h = im.size
        scale = min(1.0, max_dim / max(w, h))
        if scale < 1.0:
            im = im.resize((int(w * scale), int(h * scale)), Image.LANCZOS)
        buf = io.BytesIO()
        im.save(buf, format='WEBP', quality=quality, method=6)
        return buf.getvalue(), 'webp', 'image/webp'
    except Exception as e:
        print(f"[이미지 압축 실패 - 원본 사용] {e}")
        ext = (file_storage.filename or 'img.png').rsplit('.', 1)[-1].lower()
        return raw, ext, (file_storage.content_type or 'application/octet-stream')

# 오버레이가 안 돌고 있을 때 리액션 큐가 무한정 쌓이는 것을 막는 상한.
# 전체 큐가 매 update 마다 모든 클라이언트로 나가므로 메모리·트래픽에 직접 영향을 준다.
REACTION_QUEUE_MAX = 40
# 💛 전광판에 올릴 소액 후원자 수. 넘으면 오래된 것부터 흘려보낸다.
#    ⚠️ 무한히 쌓으면 전광판 한 줄이 끝없이 길어져 다음 회차를 밀어낸다.
NOTICE_DONORS_MAX = 20
# 💛 전광판에 적을 이름 길이. 바깥에서 오는 값이라 상한이 필요하다.
NOTICE_DONOR_NAME_MAX = 16

# 점수 로그 보관 개수. 위와 같은 이유로 상한이 필요하다.
LOG_MAX = 200

# 대기함이 이만큼 쌓이면 경고한다. 버리지는 않는다 — 대기함 한 건은 아직 배정 안 된 '돈'이라
# 조용히 버리면 그 후원은 누구에게도 못 들어간다. 리액션 큐(연출)와 성격이 다르다.
PENDING_WARN_AT = 200


def _as_int(v, default=None):
    """숫자로 바꿔본다. 못 바꾸면 default(기본 None).

       ⚠️ 밖에서 들어오는 값은 글자·None·목록·사전 무엇이든 올 수 있다.
          int() 를 그냥 부르면 그 자리에서 예외가 나고, 바깥 except 가 그걸
          500 + 파이썬 오류 문구로 돌려준다(내부 구조가 그대로 샌다).
    """
    if isinstance(v, bool) or v is None:
        return default
    if isinstance(v, (int, float)):
        return int(v)
    try:
        return int(str(v).strip())
    except (TypeError, ValueError):
        return default


def man_won(amount):
    """금액 → 점수(만원 단위). 5,000원대는 내리고 6,000원부터 올린다 — 사장님이 정한 규칙.

    ⚠️ round() 를 쓰면 안 된다. 파이썬 round 는 짝수 쪽으로 가서 15,000 → 2, 25,000 → 2 가
       되고, 조종실의 Math.round 는 5,000 을 올린다 — 서로도 달랐다. 한 식으로 통일한다.
       조종실·폰의 manWon() 과 같은 식이어야 한다.
    """
    try:
        return (int(amount) + 4000) // 10000
    except (TypeError, ValueError):
        return 0


def enqueue_signature(state, sig, amount, donator, message, skip_popup=False, count_tally=True,
                      play_after_ms=0, extra=None):
    """시그니처를 리액션 큐에 추가 (모든 재생 경로가 이 함수를 공유).

    큐를 태우면 reaction_mode가 켜지고, 재생이 끝나 큐가 비면 자동으로 꺼진다.
    skip_popup: 슬롯 당첨처럼 이미 자체 연출을 보여준 경우 후원 팝업을 건너뛴다.
    count_tally: 시그니처 순위 집계에 셀지 여부. 실제 후원(자동/장부기록)만 True,
                 슬롯 당첨·재생전용 수동 송출은 False(집계 부풀림 방지).
    extra: 큐 항목에 더 실을 것(예: 주사위 {'source': 'dice', 'banner': '밍밍 · 시그 칸 도착'}).
    """
    reaction_uuid = f"rq_{uuid.uuid4().hex}"
    # ⚠️ 큐는 '오버레이가 재생해야만' 줄어든다. OBS 장면을 바꿔놨거나 오버레이를 닫아둔 채
    #    후원이 계속 들어오면 끝없이 쌓이고, 그 전체가 매 update 마다 모든 클라이언트에게 전송된다.
    #    게다가 오버레이가 다시 붙는 순간 밀린 것을 전부 연달아 재생해버린다.
    #    상한을 두고 가장 오래된 것부터 버린다(버린 사실은 로그로 남긴다).
    _queue = state.setdefault('reaction_queue', [])
    # 🔁 같은 사람 · 같은 시그니처가 줄 끝에 이미 있으면 새로 줄 세우지 않고 묶는다(대표님 2026-09-29 C안).
    #    2만 원을 7번 보내면 2만 원 시그니처를 한 번 틀고 ×7. 금액을 합쳐 다른 시그니처로 바꾸지 않는다.
    #    조종실 대기줄의 [N번 다 틀기](play_all)를 누르면 방송판이 같은 시그니처를 N번 다 튼다.
    #    ⚠️ 줄 '끝'과만 묶는다 — 사이에 다른 후원이 끼면 순서를 지키려고 새로 줄 선다.
    #    ⚠️ 지금 틀고 있는 것(줄 머리)과도 묶인다 — 방송판이 틀면서 ×N 을 바로 올린다.
    #    ⚠️ 슬롯 당첨 · 재생전용 수동 송출(count_tally=False) · 주사위 대기(play_after)는 묶지 않는다.
    #    정산 · 시그 순위 · 점수는 후원마다 그대로 센다(아래 집계는 묶여도 1씩 올린다).
    _last = _queue[-1] if _queue else None
    if (count_tally and not skip_popup and not play_after_ms and _last is not None
            and not _last.get('skip_popup') and not _last.get('play_after')
            and str(_last.get('item_id')) == str(sig.get('id'))
            and _norm_donor(_last.get('donator')) == _norm_donor(donator)):
        _last['count'] = int(_last.get('count') or 1) + 1
        reaction_uuid = _last['id']
        state['reaction_mode'] = True
        print(f"  🔁 [시그 묶음] {donator} '{sig.get('title')}' ×{_last['count']}", flush=True)
        _merged = True
    else:
        _merged = False
    if not _merged and len(_queue) >= REACTION_QUEUE_MAX:
        dropped = len(_queue) - REACTION_QUEUE_MAX + 1
        del _queue[:dropped]
        print(f"⚠️ [리액션 큐 상한] 밀린 시그니처 {dropped}건을 버렸습니다 (상한 {REACTION_QUEUE_MAX}건). "
              f"오버레이가 꺼져 있거나 재생이 멈춰 있는지 확인하세요.")
    if not _merged:
      _queue.append({
        "id": reaction_uuid,
        "item_id": sig.get('id'),
        "title": sig.get('title'),
        # ⚠️ 아래 amount 는 '후원 금액'이다. 어떤 시그니처가 걸렸는지는 그걸로 알 수 없다
        #    (26만원을 쏴도 25만원짜리가 걸릴 수 있다). 화면이 시그니처별 연출을
        #    고르려면 시그니처 자신의 값이 필요해서 따로 싣는다.
        "sig_amount": sig.get('amount'),
        "audio_url": sig.get('sound_url') or "",
        "image_url": sig.get('image_url') or "",
        "duration": sig.get('duration') or 10,
        "amount": amount,
        "donator": donator,
        "message": message,
        "skip_popup": bool(skip_popup),
        # ⏳ 이 시각(밀리초) 전에는 화면이 재생을 시작하지 않고 리액션 모드로도
        #    안 넘어간다. 주사위가 말을 다 옮길 때까지 기다리게 하려고 쓴다.
        #    0 이면 곧바로 재생 — 보통 후원은 전부 0 이다.
        "play_after": (int(time.time() * 1000) + play_after_ms) if play_after_ms > 0 else 0,
        # 🔁 묶음 — count: 같은 사람이 같은 시그니처를 몇 번 보냈나, play_all: 조종실 [N번 다 틀기]
        "count": 1,
        "play_all": False,
      })
      if isinstance(extra, dict):
          _queue[-1].update({k: v for k, v in extra.items() if k not in _queue[-1]})
    state['reaction_mode'] = True

    # ✂️ 쇼츠 클립 목록 — 기준 금액 이상이면 '이런 순간이 곧 나온다' 고 적어 둔다.
    #    실제 저장은 방송판이 재생을 시작한 뒤 건다(대기열이 밀리면 재생은 한참 뒤다).
    #    묶인 후원은 이미 적힌 한 줄로 충분하다.
    try:
        _c = _clip_state(state)
        if not _merged and _c.get('auto') and _c.get('auto_min') and int(amount or 0) >= int(_c['auto_min']):
            _clip_log(state, 'auto', '%s %s원 %s' % (donator or '익명', format(int(amount or 0), ','), sig.get('title') or ''),
                      ref=reaction_uuid)
    except Exception as e:
        print(f"⚠️ [클립 목록 실패] {e}")

    # 📊 시그니처별 신청 집계 (실제 후원만 센다 — 슬롯/재생전용 수동은 count_tally=False)
    if count_tally:
        try:
            key = str(sig.get('id'))
            tally = state.setdefault('sig_tally', {})
            row = tally.get(key) or {
                'title': sig.get('title'), 'image_url': sig.get('image_url') or '',
                'amount': sig.get('amount') or 0, 'count': 0
            }
            row['count'] = int(row.get('count') or 0) + 1
            row['title'] = sig.get('title') or row.get('title')
            row['image_url'] = sig.get('image_url') or row.get('image_url') or ''
            row['amount'] = sig.get('amount') or row.get('amount') or 0
            # 누가 몇 개 쐈는지도 같이 센다 ("3만원짜리 누가 몇 개 쐈어?" 에 답하려면 필요)
            # setdefault 인 이유: 이 기능 이전에 저장된 상태에는 donors 키가 없다.
            donors = row.setdefault('donors', {})
            who = _norm_donor(donator)
            donors[who] = int(donors.get(who) or 0) + 1
            tally[key] = row
        except Exception as e:
            print(f"⚠️ [시그니처 집계 실패] {e}")

    return reaction_uuid

# 🛡️ 내용 기반 후원 중복 방지 (tx_id 없는 재전송 대비)
# 투네이션이 같은 후원을 tx_id 없이 두 번 POST하면 시그니처가 두 번 재생되던 문제를 막는다.
# 이름+금액+메시지가 완전히 동일한 후원이 아주 짧은 시간(윈도우) 안에 또 오면 중복으로 간주한다.
# 서로 다른 사람이 같은 금액/메시지를 2.5초 안에 보낼 확률은 사실상 0이라 안전하다.
_recent_don_lock = threading.Lock()
_recent_don = {}
# ⚠️ 재시도 간격(3초/5초)보다 넉넉히 길어야 한다.
#    2.5초였을 때는 서버 응답이 느려 스크립트가 3초 뒤 재시도하면 창이 이미 닫혀 중복이 통과했다.
DONATION_DEDUPE_WINDOW = 12.0

def is_duplicate_donation(key):
    now = time.time()
    with _recent_don_lock:
        for k in list(_recent_don.keys()):
            if now - _recent_don[k] > DONATION_DEDUPE_WINDOW:
                del _recent_don[k]
        if key in _recent_don:
            return True
        _recent_don[key] = now
        return False

# 슬롯 릴 정지 + 당첨 배너(약 3.3초) 뒤 결과 처리까지의 대기 시간
SLOT_RESULT_DELAY_SEC = 4.0

# 🎮 게임판 이름 — 옛 세이브 슬롯(board)을 읽을 때만 쓴다.
#    ⚠️ '무대에는 하나만' 규칙은 이제 show.py(showmod.set_stage)가 맡는다. 예전 _solo_board 는 걷었다.
BOARD_NAMES = ('dicegame', 'siggame', 'roulette', 'slot', 'pinball')


def _stage_log(prev, now):
    if prev != now:
        print('  📺 [무대] %s → %s' % (showmod.STAGE_LABEL.get(prev, '없음'), showmod.STAGE_LABEL.get(now, '없음')), flush=True)


def _slot_finish(winner):
    """슬롯 당첨 확정 처리: 슬롯 위젯을 끄고 당첨 시그니처를 리액션 큐에 넣는다.

       🎯 기여도도 같이 올린다 — 주사위와 같은 셈으로 한 판 값을 뺀 만큼.
    """
    try:
        title = winner.get('title') or '시그니처'
        with file_lock:
            state = load_data()
            showmod.end_temp(state, 'slot')      # 📺 잠깐 올라온 슬롯이 내려가고 원래 무대로 돌아간다
            enqueue_signature(state, winner, winner.get('amount') or 0,
                              '🎰 슬롯머신', f'[슬롯 당첨] {title}', skip_popup=True, count_tally=False)
            # 🎯 기여도만 — 점수(그날 일당)는 안 건드린다.
            #    ⚠️ 당첨 값에서 한 판 값을 뺀다. 슬롯 한 판은 2만원 후원으로 사는데,
            #       그 후원이 들어올 때 이미 2점이 올라갔다. 통째로 또 주면 두 번 셈된다.
            #    ⚠️ 주사위와 달리 '굴린 사람' 이 없다. 차례가 없으니 서버가 누구 것인지
            #       알 길이 없어, 조종실이 고르도록 대기함에 카드로 올린다.
            #       아무에게나 자동으로 넣으면 그건 틀린 사람에게 주는 것이다.
            try:
                _amt = int(winner.get('amount') or 0)
                _price = max(0, _as_int(state.get('slot_price'), 20000) or 0)
                _c = max(0, man_won(_amt - _price))
                if _c:
                    _contrib_alert(
                        state, '🎰 슬롯 당첨', _c,
                        '%s (%s원 − 한 판 %s원)' % (title[:40], format(_amt, ','), format(_price, ',')))
                    print(f"  🎯 [슬롯] 기여도 {_c} 알림을 대기함에 올렸습니다 "
                          f"({_amt:,}원 − 한 판 {_price:,}원)")
                else:
                    print(f"  🎯 [슬롯] '{title}' 는 한 판 값({_price:,}원) 이하라 더 줄 기여도가 없습니다")
            except Exception as e:
                print(f'⚠️ [슬롯] 기여도 알림 실패 — 당첨 재생은 계속됩니다: {e}')
            save_data(state)
            broadcast_event('update', state)
        print(f"  🎰 [슬롯 당첨 처리] '{title}' → 슬롯 위젯 OFF, 리액션 큐 투입")
    except Exception as e:
        print(f"❌ [슬롯 당첨 처리 실패] {e}")

# ==========================================
# 🤫 서버 로그 제어
# ==========================================
log = logging.getLogger('werkzeug')
log.setLevel(logging.ERROR)
log.disabled = True 

app = Flask(__name__)
app.secret_key = load_auth_config()['session_secret']
# 📦 업로드 크기 상한. 이걸 안 두면 아무나(로그인은 필요하지만) 몇 GB 를 밀어넣어
#    1GB 짜리 서버의 디스크를 채울 수 있다. 넘으면 Flask 가 413 을 돌려준다.
app.config['MAX_CONTENT_LENGTH'] = 80 * 1024 * 1024
# ⚠️ CORS 를 열지 않는다. 오버레이·조종실·후원 콘솔은 전부 같은 출처에서 돌고,
#    투네이션 리스너는 서버 안에서(127.0.0.1), 템퍼몽키는 GM_xmlhttpRequest 로 부른다
#    — 셋 다 CORS 를 타지 않는다. 열어두면 아무 웹페이지나 Bearer 토큰으로 이 API 를 부를 수 있다.
file_lock = threading.Lock()

# 🚫 [강력 차단] 웹 브라우저 및 OBS CEF 캐싱 방지 헤더 이식
@app.after_request
def add_header(r):
    # ⚠️ 예전에는 모든 응답에 걸었다. 그러면 .js·.css·글꼴·그림까지 캐시가 금지돼
    #    OBS 오버레이를 새로고침할 때마다 정적 파일을 통째로 다시 받는다.
    #    상하면 안 되는 것은 상태(API)뿐이라 거기에만 건다.
    if request.path.startswith('/api/') or request.path == '/login':
        r.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        r.headers["Pragma"] = "no-cache"
        r.headers["Expires"] = "0"
    return r

# 🔒 [보안 통제] 웹 제어실 및 중요 API 접근 제한 미들웨어
# 로그인 없이 나가는 정적 자원 확장자.
# 파일 서빙 허용목록(SERVABLE_EXTS)과 따로 놓면 한쪽에만 추가하고 빠뜨려
# '허용된 것이 로그인으로 튐기는' 사고가 난다. 그림·글꼴·스크립트만 여기 넣는다.
STATIC_FREE_EXTS = {
    '.css', '.js', '.mjs', '.map', '.wasm',   # 🎱 .wasm — 핀볼 물리 엔진(box2d). 방송판(OBS)은 로그인이 없다
    '.png', '.jpg', '.jpeg', '.gif', '.webp', '.svg', '.ico', '.avif',
    '.woff', '.woff2', '.ttf', '.otf', '.eot',
}


@app.before_request
def require_login():
    path = request.path

    # 🛰️ 대기 모드: 화면은 보여주되 상태를 바꾸는 요청은 받지 않는다.
    #    저장(save_data)도 이미 막혀 있지만, 여기서 먼저 끊어야 메모리 상태까지
    #    운영과 어긋나지 않는다(어긋난 채로 승격되면 그 값이 그대로 DB 로 간다).
    if STANDBY and request.method not in ('GET', 'HEAD', 'OPTIONS') and path not in STANDBY_ALLOWED:
        return jsonify({"status": "error",
                        "message": "이 서버는 대기 모드입니다. 운영 서버로 보내주세요."}), 503

    
    # 정적 자원 파일 프리패스
    # ⚠️ 오버레이는 로그인 세션이 없다. 여기에 빠진 확장자는 로그인 페이지로 302 된다 —
    #    그러면 방송 화면에서 그 그림만 조용히 안 나온다. 실제로 .webp 가 빠져 있었다.
    #    소리·영상(.mp3 등)은 일부러 넣지 않는다 — 효과음은 /sfx/ 전용 길로 나간다.
    if os.path.splitext(path)[1].lower() in STATIC_FREE_EXTS:
        return
        
    # 세션 검증 예외 경로 리스트
    exempt_routes = [
        '/login',
        '/logout',
        '/',
        '/overlay',
        '/overlay.html',
        '/alertbox',
        '/alertbox.html',
        # 🎰📺 슬롯·시그니처 표시 화면도 알림창과 같은 성격이다 — OBS 브라우저 소스로 띄우는
        #    '보여주기만 하는' 페이지라 로그인 세션이 있을 수 없다. 여기에 없으면 OBS 가
        #    로그인 화면을 띄워 아무것도 안 나오고, 억지로 쓰려면 주소에 관리자 키를 박아야 한다
        #    (그 키가 화면에 잡히면 그대로 유출이다).
        #    두 화면이 받는 것은 SSE 로 나가는 공개 상태뿐이라 새로 새는 것은 없다.
        '/slot',
        '/slot.html',
        '/signature-display',
        '/signature-display.html',
        '/signature_display.html',   # 파일 이름 그대로 친 주소도 열어준다(밑줄)
        '/api/stream',
        '/api/ping',
        # 🩺 상태 확인은 로그인 없이 열어둔다. 폰으로 '서버 괜찮나' 보는 용도라
        #    로그인을 요구하면 쓸모가 없다. 담기는 내용은 api_health() 참고 —
        #    이름·금액·토큰은 없고, 보안 항목은 로그인했을 때만 붙는다.
        '/health',
        '/privacy',      # 📄 구글 OAuth 게시에 필요 — 로그인 없이 열려야 한다
        '/terms',
        '/api/health',
        '/api/donation',
        # ⚠️ /api/streamdeck/* 는 여기에 두면 안 된다. 무인증 GET 만으로 reaction_mode 를
        #    켤 수 있어서, 주소만 아는 사람이 랭킹판·게이지를 숨겨버릴 수 있었다.
        #    큐가 비어 있으면 그걸 끄는 코드가 없어 운영자가 손으로 끌 때까지 돌아오지 않는다.
        #    streamdeck.html 자체가 이미 로그인 뒤에 있어서, 같은 출처 fetch 에 세션이 실린다.
        '/api/roulette/winner',
        # 🎱 핀볼 결과도 **방송판이 보낸다** — 오버레이는 세션이 없다(룰렛과 같은 이유).
        #    ⚠️ 여기서 열어도 아무나 결과를 못 심는다: 굴러가는 중(running)일 때만 받고,
        #       판 번호(round_id)가 맞아야 하며, 받는 즉시 문을 닫는다(먼저 온 하나만 이긴다).
        '/api/pinball/result',
        # ✂️ 쇼츠 클립 — 방송판(OBS)이 '저장 담당' 상태만 알린다. 메모리 표시용(상태·DB 안 바뀜)
        '/api/clip/hello',
        '/api/match/timeup',
        '/api/signatures',
        '/api/reaction/next',
        '/sfx/list',        # 🔊 어떤 효과음이 있나 — 오버레이는 세션이 없다
        '/toonation_tampermonkey.user.js',
    ]
    
    # 메서드까지 봐야 하는 예외: 조회는 오버레이가 써야 해서 공개, 변경은 로그인 필요.
    # (경로만으로 예외를 주면 POST/DELETE까지 무인증으로 열려버린다)
    method_exempt = {
        '/api/vips': ('GET',),
        # 오버레이·알림창은 로그인 세션이 없으므로 조회는 열어둬야 한다.
        # 반면 POST 는 상태를 통째로 덮어쓰는 요청이라 반드시 인증이 필요하다.
        # (예전에는 경로만으로 예외를 줘서, URL 만 알면 누구나 점수를 지우거나
        #  전광판에 아무 문구나 띄울 수 있었다. 오버레이가 쓰던 유일한 POST 용도인
        #  '대결 타이머 종료'는 /api/match/timeup 이라는 좁은 전용 엔드포인트로 옮겼다)
        '/api/data': ('GET',),
    }
    if path in method_exempt and request.method in method_exempt[path]:
        return

    # 시그니처 등록(/upload, /노래등록)은 관리 기능이므로 로그인 필요로 변경했다.
    # (등록 API가 /api/signatures/add 로 바뀌면서 인증이 필요해졌기 때문)
    if (path in exempt_routes or
        path.startswith('/videos/') or   # 🎬 고액후원 영상 — 오버레이는 로그인 세션이 없다
        path.startswith('/sfx/')):      # 🔊 효과음 — 오버레이는 로그인 세션이 없다
        return
         
    # HTTP Authorization Bearer 토큰 및 ?token= 파라미터 검증 지원
    auth_header = request.headers.get('Authorization')
    token = None
    if auth_header and auth_header.startswith('Bearer '):
        token = auth_header.split(' ')[1]
    else:
        token = request.args.get('token')
        
    is_token_valid = (token and token == load_auth_config()['session_secret'])
        
    # 비인증 사용자 제약
    if not session.get('authenticated') and not is_token_valid:
        if path.startswith('/api/'):
            return jsonify({'status': 'error', 'message': 'Unauthorized'}), 401
        if request.query_string:
            return redirect(url_for('serve_login') + '?' + request.query_string.decode('utf-8'))
        return redirect(url_for('serve_login'))

# ==========================================
# 🛰️ 대기 모드 (STANDBY)
# ==========================================
# 폴백 서버를 켜둔 채 운영 서버와 같은 DB 를 보게 하면, 두 서버가 서로의 데이터를 지운다.
#
# load_data() 는 한 번 읽은 상태를 메모리에 들고 계속 재사용하고(DB 를 다시 안 본다),
# save_data() 는 그 기억을 통째로 DB 에 쓴다. 그래서 뒤처진 서버가 저장하는 순간
# 상대가 받은 후원과 점수가 되돌려진다. 실제로 방송 중에 두 서버의 마지막 후원이
# 서로 달랐고, 폴백이 재시작할 때마다 옛 큐를 읽어 같은 시그니처를 다시 재생했다.
#
# STANDBY=1 로 켜면 그 서버는 '구경만' 한다:
#   - DB 에 쓰지 않는다        → 운영 데이터를 건드릴 수 없다
#   - 상태를 바꾸는 요청을 거절한다 → 시그니처를 재생시키거나 큐를 넘기지 못한다
# 운영 서버가 죽어 실제로 넘겨받을 때는 이 값을 끄고 재시작하면 된다
# (그때 DB 에서 최신 상태를 새로 읽는다).
STANDBY = (os.environ.get('STANDBY') or '').strip().lower() in ('1', 'on', 'true', 'yes')

# 상태를 바꾸지 않아 대기 모드에서도 허용하는 경로
STANDBY_ALLOWED = ('/login', '/logout', '/api/ping', '/api/health', '/api/stream')


# ==========================================
# 🔒 무인증 경로 보호
# ==========================================
# 오버레이·알림창은 로그인 세션이 없어서 몇몇 경로를 열어둘 수밖에 없다.
# 그런데 그 경로들이 '주소만 알면 누구나' 쓸 수 있다는 뜻이기도 하다.
# 방송 화면에 주소가 나오고 저장소도 공개라, 사실상 아무나 안다고 봐야 한다.
# 아래 도구들로 '열어두되 함부로 못 쓰게' 만든다.


def request_is_authed():
    """로그인 세션이 있거나 관리자 키를 들고 왔는가."""
    if session.get('authenticated'):
        return True
    auth = request.headers.get('Authorization') or ''
    token = auth.split(' ', 1)[1].strip() if auth.startswith('Bearer ') else request.args.get('token')
    return bool(token) and secrets.compare_digest(token, load_auth_config()['session_secret'])


def request_is_from_this_server():
    """이 서버 안에서 들어온 요청인가(예: 같은 기계에서 도는 투네이션 리스너).

    ⚠️ remote_addr 만 보면 안 된다. 앞단의 Caddy 가 127.0.0.1 로 넘겨주므로
       바깥에서 온 요청도 전부 로컬로 보인다. 프록시를 거친 요청에는
       X-Forwarded-For 가 붙으므로, 그게 '없을 때'만 진짜 로컬이다.
    """
    if request.headers.get('X-Forwarded-For') or request.headers.get('X-Real-IP'):
        return False
    return request.remote_addr in ('127.0.0.1', '::1', 'localhost')


# 무인증 응답에서 빼는 항목. 오버레이·알림창은 이 중 무엇도 쓰지 않는다(확인함).
# 대기 후원에는 아직 화면에 안 뜬 후원자의 이름·금액·메시지가 들어 있어 특히 민감하다.
PRIVATE_STATE_FIELDS = ('pending_donations', 'logs', 'match_logs',
                        'bank_ledger', 'donation_history', 'snapshots')


def strip_private_state(state):
    """무인증 상대에게 보낼 상태에서 민감한 항목을 뺀다(원본은 건드리지 않는다)."""
    if not isinstance(state, dict):
        return state
    out = dict(state)
    for k in PRIVATE_STATE_FIELDS:
        out.pop(k, None)
    # 🎲 황금열쇠 덱은 뽑기 전까지 비밀이다. 오버레이는 덱이 필요 없다 —
    #    뽑힌 카드는 서버가 action 에 실어 보낸다. 장수만 남겨 화면 표시에 쓴다.
    g = out.get('dicegame')
    if isinstance(g, dict) and g.get('keys'):
        g = dict(g)
        g['keys_count'] = len(g.get('keys') or [])
        g['keys'] = []
        out['dicegame'] = g
    # 🧩 퀴즈 정답 · 분류 · 내 문제는 조종실에만 — 방송판은 네모칸(tiles)만 받는다
    q = out.get('quiz')
    if isinstance(q, dict):
        out['quiz'] = {'tiles': q.get('tiles') or [], 'revealed': bool(q.get('revealed'))}
    return out


# 📡 실시간 SSE 클라이언트 관리 시스템
sse_clients = []
sse_lock = threading.Lock()
# 클라이언트 1대가 밀렸을 때 쌓아둘 최대 메시지 수.
# state 전체가 실리므로(수십 KB) 이 값이 곧 '밀린 클라 1대당 최대 메모리'다.
SSE_QUEUE_MAX = 120

# 🧹 죽은 연결 치우기 (2026-09-30 방송 중 실제 사고 — 끊긴 연결 161개 · 실 가닥 235개)
#    붙은 연결을 지우는 곳이 finally 뿐이라, 조용히 사라진 브라우저는 영영 안 치워졌다.
#    ⚠️ 셋 다 넉넉하게 잡는다. 방송 중 멀쩡한 화면을 실수로 끊는 쪽이 훨씬 나쁘다.
SSE_MAX_CLIENTS = int(os.environ.get('SSE_MAX_CLIENTS', '60'))   # 이보다 많으면 가장 오래된 것부터
SSE_STALE_SEC = int(os.environ.get('SSE_STALE_SEC', '120'))      # 이 동안 한 줄도 안 받아 가면 죽은 것
SSE_SOCKET_TIMEOUT = int(os.environ.get('SSE_SOCKET_TIMEOUT', '90'))   # 소켓이 이만큼 막히면 끊는다
_sse_evicted = 0          # 지금까지 내보낸 죽은 연결 수(상태 페이지에 보여준다)


def _sse_drop(q, why):
    """죽은 연결 하나를 목록에서 빼고, 기다리는 제너레이터를 깨워 빠져나가게 한다.
       ⚠️ sse_lock 을 쥔 채로 부른다."""
    global _sse_evicted
    if q in sse_clients:
        sse_clients.remove(q)
        _sse_evicted += 1
    q._evict = why
    try:
        q.put_nowait(None)          # None = '이제 그만' 표시. 제너레이터가 이걸 보고 끝낸다
    except Exception:
        pass
    # ⚠️ 소켓도 닫아 준다. 안 닫으면 CLOSE-WAIT 로 그대로 남아(오늘 161개가 그랬다)
    #    실 가닥이 안 풀린다. 닫으면 그 실이 쓰기에서 깨어나 finally 까지 간다.
    sk = getattr(q, '_sock', None)
    if sk is not None:
        try:
            sk.shutdown(socket.SHUT_RDWR)
        except Exception:
            pass
        try:
            sk.close()
        except Exception:
            pass


def _peer_gone(sock):
    """상대가 연결을 끊었는가 — 소켓에서 직접 본다.
       브라우저가 탭을 닫으면 FIN 이 와서 '읽을 게 있는데 읽으면 0바이트' 가 된다.
       (이게 CLOSE-WAIT 로 쌓이던 그 상태다. 글자를 써 넣는 것만으로는 절대 알 수 없다 —
        상대가 사라져도 운영체제 버퍼에는 잘 들어가기 때문이다.)
       ⚠️ 엿보기(MSG_PEEK)라 읽어도 없어지지 않는다. 확실할 때만 True — 애매하면 살려 둔다."""
    if sock is None:
        return False
    try:
        r, _, _ = select.select([sock], [], [], 0)
        if not r:
            return False                      # 읽을 게 없다 = 잘 붙어 있다
        return sock.recv(1, socket.MSG_PEEK) == b''    # 0바이트 = 저쪽이 끊었다
    except (BlockingIOError, InterruptedError):
        return False
    except OSError:
        return True                           # 소켓이 이미 망가졌다
    except Exception:
        return False


# 🏷️ 붙은 화면 이름표 (2026-10-02) — 대표님 "오버레이 하나랑 컨트롤러 하나만 띄워놨는데" 6개로 나왔다.
#    숫자만 있어서 뭐가 뭔지 몰랐다(알고 보니 폰 화면 안에 방송판 미리보기가 숨어 있어 폰 하나가 2개).
#    화면마다 /api/stream?kind=… 로 자기가 뭔지 알려 준다. 모르는 것(옛 화면 · 바깥 접속)은 'unknown'.
SSE_KINDS = ('controller', 'overlay', 'mobile', 'manual', 'admin', 'alertbox', 'sigdisp', 'slot')
# 상한에 걸렸을 때 내보내는 순서 — 작을수록 먼저. ⚠️ 방송에 나가는 화면(방송판 · 알림창 · 전광판)은 맨 나중.
#    예전엔 '가장 오래된 것' 부터였는데, 가장 오래된 건 보통 방송 시작 때 켠 OBS 방송판이었다.
_SSE_KEEP_RANK = {'unknown': 0, 'controller': 1, 'mobile': 1, 'manual': 1, 'admin': 1, 'slot': 1,
                  'alertbox': 2, 'sigdisp': 2, 'overlay': 2}
_SSE_SHOW_ORDER = ('overlay', 'alertbox', 'sigdisp', 'controller', 'mobile', 'manual', 'admin', 'slot', 'unknown')


def _sse_device(ua, obs_hint=False):
    """어떤 기기인지 대충만 — 이름표용이라 정확할 필요는 없다. 주소·IP 는 안 남긴다."""
    ua = ua or ''
    if obs_hint or 'OBS/' in ua:
        return 'obs'
    if 'iPhone' in ua:
        return 'iphone'
    if 'iPad' in ua:
        return 'ipad'
    if 'Android' in ua:
        return 'android'
    if 'Windows' in ua:
        return 'windows'
    if 'Macintosh' in ua or 'Mac OS X' in ua:
        return 'mac'
    return 'other'


def _sse_keep_rank(q):
    k = getattr(q, '_kind', 'unknown')
    r = _SSE_KEEP_RANK.get(k, 0)
    if k == 'overlay' and getattr(q, '_monitor', False):
        r = 1          # 미리보기(폰 · 편집기 안의 방송판)는 방송에 안 나간다
    return r


def _sse_trim_over(keep=None):
    """상한을 넘으면 '덜 중요한 것 · 오래된 것' 부터 내보낸다. ⚠️ sse_lock 을 쥔 채로 부른다.
       keep — 방금 붙은 화면. 이건 내보내지 않는다(10-06 점검: 이름표 없는 화면이 붙자마자 자기를 내보내고,
       다시 붙고, 또 내보내는 고리가 될 수 있었다)."""
    while len(sse_clients) > SSE_MAX_CLIENTS:
        pool = [x for x in sse_clients if x is not keep] or list(sse_clients)
        victim = min(pool, key=lambda x: (_sse_keep_rank(x), getattr(x, '_born', 0)))
        _sse_drop(victim, 'over')


def sse_screens():
    """지금 붙은 화면 목록 — 조종실 시스템 칸에 보인다(로그인한 쪽에만). 주소 · IP 는 싣지 않는다."""
    now = time.time()
    with sse_lock:
        rows = [{'kind': getattr(q, '_kind', 'unknown'),
                 'device': getattr(q, '_dev', 'other'),
                 'monitor': bool(getattr(q, '_monitor', False)),
                 'authed': bool(getattr(q, '_authed', False)),
                 'since_sec': max(0, int(now - getattr(q, '_born', now))),
                 'idle_sec': max(0, int(now - getattr(q, '_drained', now)))} for q in sse_clients]
    order = {k: i for i, k in enumerate(_SSE_SHOW_ORDER)}
    rows.sort(key=lambda r: (order.get(r['kind'], 99), r['monitor'], -r['since_sec']))
    return rows


def _sse_janitor():
    """30초마다 죽은 연결을 치운다.
       ① 상대가 끊은 것(제일 흔하다 — 탭 닫기 · 새로고침 연타)
       ② 오래 아무것도 못 받아 간 것(소켓이 막힌 경우)
       ③ 그래도 넘치면 오래된 것부터"""
    while True:
        time.sleep(30)
        try:
            now = time.time()
            with sse_lock:
                for q in list(sse_clients):
                    if _peer_gone(getattr(q, '_sock', None)):
                        _sse_drop(q, 'closed')
                for q in [x for x in sse_clients
                          if now - getattr(x, '_drained', now) > SSE_STALE_SEC]:
                    _sse_drop(q, 'stale')
                # 상한을 넘으면 덜 중요한 것부터 (새 화면이 못 붙는 일을 막는다 · 방송판은 맨 나중)
                _sse_trim_over()
        except Exception as e:
            print(f'⚠️ [실시간 연결 청소] 한 번 걸렀습니다: {e}', flush=True)


threading.Thread(target=_sse_janitor, daemon=True, name='sse-janitor').start()

# '나머지 까보기' 를 열어두는 시간. 오버레이의 SG_PEEK_MS 와 같아야 한다.
#  ⚠️ mask_siggame 이 이 값을 쓰므로 그 함수보다 위에 있어야 한다.
SIGGAME_PEEK_MS = 6000


def mask_siggame(data):
    """밖으로 나가는 상태에서 '아직 안 뒤집힌 카드'의 속을 지운다.

    ⚠️ 이게 없으면 재미가 통째로 사라진다. /api/stream 과 /api/data 는 무인증으로 열려 있어서
       개발자도구만 열면 덮인 카드가 무슨 시그니처인지 그대로 보인다.
       뒤집힌 카드만 사진·이름을 싣고, 덮인 카드는 번호와 '덮임'만 내보낸다.
    ⚠️ 원본 상태를 건드리면 안 된다(서버가 정답을 잃어버린다).
       그래서 '새 dict 를 만들어 돌려주는' 형태다. 반드시 반환값을 받아 써야 한다:
           data = mask_siggame(data)
    """
    if not isinstance(data, dict):
        return data
    g = data.get('siggame')
    if not isinstance(g, dict) or not isinstance(g.get('cards'), list):
        return data
    data = dict(data)
    # 🔍 '나머지 까보기' 중에는 덮인 카드의 정체도 내보낸다.
    #    이게 없으면 화면이 알 방법이 없다 — 마스킹이 사진·이름을 아예 지우기 때문이다.
    #    창이 몇 초로 짧고 진행자가 직접 연 것이라, 그동안만 열어주는 게 맞다.
    _peek = False
    try:
        _act = g.get('action') or {}
        if _act.get('type') == 'PEEK':
            _peek = (time.time() * 1000 - (_act.get('ts') or 0)) < SIGGAME_PEEK_MS
    except Exception:
        _peek = False
    safe = []
    for c in g['cards']:
        if not isinstance(c, dict):
            continue
        if c.get('state') == 'REVEALED' or _peek:
            # ⚠️ state 는 원래 값을 그대로 보낸다. 까보기 중이라고 HIDDEN 을 REVEALED 로
            #    바꿔 보내면, 까보기가 끝난 뒤 화면이 그 카드를 계속 열린 것으로 여긴다.
            safe.append({"id": c.get('id'), "state": c.get('state'),
                         "image": c.get('image'), "title": c.get('title') or '',
                         "amount": c.get('amount'),
                         "flippedAt": c.get('flippedAt'), "doneAt": c.get('doneAt')})
        else:
            safe.append({"id": c.get('id'), "state": "HIDDEN"})
    g2 = dict(g)
    g2['cards'] = safe
    # picks(이번 판에 쓸 시그니처 후보)는 카드와 달리 감춰지지 않고 그대로 나가고 있었다.
    # 사진 주소·이름·금액이 전부 실려서, 갱신이 있을 때마다 접속한 오버레이 수만큼
    # 같은 목록이 다시 나간다. 조종실은 sig_id 만 있으면 선택을 되살릴 수 있으므로
    # 번호만 남긴다. (목록 자체를 완전히 감추려면 /api/signatures 도 잠가야 하는데,
    #  그건 알림창이 쓰고 있어 여기서 건드리지 않는다)
    g2['picks'] = [{"sig_id": p.get('sig_id')}
                   for p in (g.get('picks') or []) if isinstance(p, dict)]
    data['siggame'] = g2
    return data


def state_for_client(state, authed):
    """밖으로 내보낼 상태 한 벌을 만든다.

    ⚠️ state 를 응답이나 SSE 에 실을 때는 반드시 이 함수를 거친다.
       같은 정리를 경로마다 손으로 되풀이하다 세 번 빠뜨렸다:
         ① SSE 첫 전송(init)에서 덮인 카드의 정체가 그대로 나갔다
         ② 그 자리에 server_time 도 빠져, 갓 붙은 오버레이는 시계를 못 맞췄다
         ③ /api/reaction/next 는 시그게임 마스킹을 아예 안 했다 —
            시그니처가 재생될 때마다(방송 중 가장 잦은 일이다) 16장 전부의
            이름·사진·금액·번호가 무인증으로 나갔다
       경로가 하나 더 생겨도 여기만 거치면 같은 실수가 안 난다.
    """
    out = mask_siggame(state)            # 🃏 덮인 카드의 정체 — 로그인 여부와 무관하게 지운다
    if not authed:
        out = strip_private_state(out)   # 🔒 대기 후원·장부·로그는 오버레이가 쓰지 않는다
    out = dict(out)                      # 원본을 건드리면 서버가 정답을 잃는다
    out.pop('api_token', None)           # 🔐 상태에 섞여 들어갔더라도 절대 내보내지 않는다
    # 📺 방송 화면 — 저장본 + 계산한 덮기(cover) + 한 줄 요약. 방송판·조종실이 이것 하나만 본다
    try:
        out['show'] = showmod.view(out)
    except Exception as _e:
        print(f'⚠️ [방송 화면] 내보내기 실패: {_e}', flush=True)
    out['server_time'] = int(time.time() * 1000)   # ⏱️ 화면이 서버 시계에 맞출 수 있게
    # 🎲 전용 점수판이 아직 없는 옛 저장본이면 여기서 채워 내보낸다.
    #    ⚠️ 원본은 안 건드린다(얕은 복사본에만 얹는다) — 읽는 길에서 상태를 고치면 안 된다.
    #       조종실이 주사위를 한 번 건드리기 전까지 방송판 판이 비어 보이던 것을 막는다.
    try:
        _dg = out.get('dicegame')
        if isinstance(_dg, dict) and not isinstance(_dg.get('board'), list):
            _dg = dict(_dg)
            _dg['board'] = [{'name': p.get('name'), 'pts': 0}
                            for p in (_dg.get('pieces') or []) if isinstance(p, dict) and p.get('name')]
            out['dicegame'] = _dg
    except Exception as _e:
        print(f'⚠️ [주사위 판] 내보내기 보정 실패: {_e}', flush=True)
    # 👑 이번 방송 순위 등급 — 후원 순위(donor_tally)처럼 공개다. 팝업·순위판·조종실이 같이 본다.
    try:
        out['vip_live'] = _vip_live(out)
    except Exception as _e:
        print(f'⚠️ [VIP 순위 계산 실패] {_e}', flush=True)
        out['vip_live'] = {}
    # 🎬 끝 화면이 떠 있고 방송 중이면 '오늘의 기록' 을 지금 상태로 만들어 싣는다
    #    (방송을 끝낸 뒤에는 stage_screen.last_snap 을 쓴다 — 종료가 기록을 지운다)
    try:
        _ss = out.get('stage_screen')
        if isinstance(_ss, dict) and _ss.get('mode') == 'end' and out.get('broadcast_active'):
            out['stage_live'] = _stage_snapshot(out)
    except Exception as _e:
        print(f'⚠️ [끝 화면 기록 계산 실패] {_e}', flush=True)
    return out


def broadcast_event(event_name, data):
    # 로그인한 쪽(조종실·후원 콘솔)과 아닌 쪽(오버레이)에 다른 내용을 보낸다.
    if isinstance(data, dict):
        data = state_for_client(data, True)
        public_data = strip_private_state(data)
    else:
        public_data = data
    with sse_lock:
        message = f"event: {event_name}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"
        public_message = (f"event: {event_name}\ndata: {json.dumps(public_data, ensure_ascii=False)}\n\n"
                          if public_data is not data else message)
        for client_q in sse_clients:
            msg = message if getattr(client_q, '_authed', False) else public_message
            try:
                client_q.put_nowait(msg)
            except queue.Full:
                # 밀린 클라이언트(느린 네트워크·멈춘 OBS): 가장 오래된 것을 버리고 최신을 넣는다.
                # update 는 state 전체를 싣고 다니므로 중간 것을 버려도 최신 상태는 그대로 도착한다.
                # 버리지 않고 쌓아두면 그 클라이언트 큐가 서버 메모리를 계속 먹는다.
                try:
                    client_q.get_nowait()
                    client_q.put_nowait(msg)
                except Exception:
                    pass

# 🔒 공개된 기본 비밀번호로는 인터넷에서 로그인할 수 없게 막는다.
#
# '0508' 은 이 파일에 적혀 있고 저장소는 공개(public)라, 사실상 누구나 아는 값이다.
# 조종실 자물쇠는 비밀번호 하나라(OTP 없음), 이 상태에서는 주소만 알면 조종실에 들어와
# 점수·전광판·방송 리셋을 전부 만질 수 있었다.
#
# 그래서 '서버로 돌고 있을 때'(HEADLESS 또는 DATABASE_URL) 는 기본값을 거부한다.
# 집에서 GUI 로 띄우는 경우는 인터넷에 열려 있지 않으므로 그대로 둔다.
#
# ⚠️ 막힌 사람이 무엇을 해야 하는지 화면에 그대로 알려준다. '비밀번호가 틀렸습니다'
#    로 끝내면 방송 직전에 원인을 못 찾고 시간을 버린다.
DEFAULT_ADMIN_PASSWORD = '0508'


def admin_password_is_unset():
    if not (os.environ.get('HEADLESS') or os.environ.get('DATABASE_URL')):
        return False        # 로컬 GUI 실행 — 밖에서 접근할 수 없으므로 막지 않는다
    return load_auth_config()['admin_password'] == DEFAULT_ADMIN_PASSWORD


ADMIN_PASSWORD_UNSET_MSG = (
    '서버에 관리자 비밀번호가 설정되지 않았습니다. '
    '공개된 기본값은 보안상 사용할 수 없습니다. '
    '환경변수 ADMIN_PASSWORD 에 새 비밀번호를 넣고 서버를 다시 시작해주세요.'
)


# 🐢 로그인 시도를 늦춘다.
#    /login 은 비밀번호 한 개로 통과하는데 시도 횟수에 제한이 없었다.
#    기본 비밀번호가 네 자리(0508)라, 자동 도구면 몇 초 만에 다 넣어본다.
#    OTP 를 걷어낸 뒤로는(2026-09-30) 이것이 찍어보기를 막는 유일한 장치다 — 빼지 말 것.
#
# ⚠️ '몇 번 틀리면 잠금' 은 일부러 쓰지 않는다. 남이 아무 비밀번호나 계속 넣어
#    방송 직전에 사장님을 못 들어오게 만들 수 있다(그게 더 큰 사고다).
#    대신 틀릴수록 응답을 늦춘다. 사람은 한두 번 틀려도 못 느끼고,
#    자동 도구는 시도 속도가 사실상 0 이 된다.
_LOGIN_FAILS = {}                     # {누구: (실패횟수, 마지막 실패시각)}
_LOGIN_FAIL_LOCK = threading.Lock()
LOGIN_FAIL_RESET_SEC = 900            # 15분 조용하면 없던 일로 한다
LOGIN_MAX_DELAY_SEC = 8.0


def _login_key():
    """시도한 쪽을 구분하는 값. 앞단 Caddy 때문에 remote_addr 은 전부 127.0.0.1 이라,
       프록시가 붙여주는 실제 주소를 먼저 본다."""
    xff = (request.headers.get('X-Forwarded-For') or '').split(',')
    tail = xff[-1].strip() if xff and xff[-1].strip() else ''
    return tail or (request.headers.get('X-Real-IP') or '').strip() or (request.remote_addr or '?')


def _login_fail_count(key, now):
    n, ts = _LOGIN_FAILS.get(key, (0, 0.0))
    return 0 if (now - ts) > LOGIN_FAIL_RESET_SEC else n


def login_throttle():
    """직전 실패 횟수만큼 기다렸다가 돌아온다. 2번까지는 지연이 없다."""
    now = time.time()
    with _LOGIN_FAIL_LOCK:
        n = _login_fail_count(_login_key(), now)
    if n >= 2:
        time.sleep(min(LOGIN_MAX_DELAY_SEC, 0.5 * (2 ** (n - 2))))


def login_failed(what):
    key = _login_key()
    now = time.time()
    with _LOGIN_FAIL_LOCK:
        n = _login_fail_count(key, now) + 1
        _LOGIN_FAILS[key] = (n, now)
        if len(_LOGIN_FAILS) > 500:   # 방치하면 메모리를 계속 먹는다
            for k in [k for k, (_, t) in _LOGIN_FAILS.items()
                      if (now - t) > LOGIN_FAIL_RESET_SEC]:
                _LOGIN_FAILS.pop(k, None)
    if n in (5, 20, 100) or n % 500 == 0:
        print(f"🚨 {what} 실패 {n}회 (ip={key}) — 누가 비밀번호를 찍어보고 있습니다", flush=True)


def login_ok():
    with _LOGIN_FAIL_LOCK:
        _LOGIN_FAILS.pop(_login_key(), None)


def password_matches(given):
    """비밀번호 비교. 한 글자씩 비교하다 멈추면 응답 시간으로 앞자리를 알아낼 수 있다."""
    return secrets.compare_digest(str(given or ''), str(load_auth_config()['admin_password'] or ''))


def serve_html_file(filename):
    local_path = os.path.join(BASE_DIR, filename)
    if os.path.exists(local_path):
        return send_from_directory(BASE_DIR, filename)
    return send_from_directory(BUNDLE_DIR, filename)

DEFAULT_STATE = {
    "bjs": [],
    "bottom_fixed": {"name": "운영비", "score": 0},
    # 🏺 모금함 — 운영비와 같은 통 하나. 다른 점은 **종잣돈(seed)** 이 있다는 것뿐이다.
    #    화면에 뜨는 금액 = seed + score. seed 는 회사가 깔아준 상금, score 는 시청자 후원분.
    #    ⚠️ 목표 게이지 셈에는 **안 넣는다**. 상금으로 나갈 돈이라 방송 매출이 아니다.
    "fundjar": {"name": "모금함", "enabled": False, "seed": 200000, "score": 0},
    # 🤖 진행봇 설정 — 봇(bot/announce.py)은 **다른 프로그램**이라 서버가 켜고 끄지는 못한다.
    #    대신 봇이 SSE 로 이 값을 받아 스스로 입을 다물거나 연다. 조종실에서 방송 중에 바꾼다.
    #    ⚠️ 봇이 안 떠 있으면 여기서 뭘 눌러도 아무 일도 안 일어난다 — 조종실이 그렇게 안내한다.
    "announce_bot": {
        "enabled": True,            # 전체 스위치. 끄면 봇이 한마디도 안 한다
        "min_interval_sec": 25,     # 최소 몇 초에 한 줄
        # 🔗 어느 방송 채팅에 칠 것인가 — 조종실에서 라이브 주소를 붙여넣는다.
        #    비워두면 봇이 제 계정의 라이브를 찾는다(방송을 다른 계정으로 하면 못 찾는다).
        "live_url": "",             # 사장님이 붙여넣은 주소 그대로 (화면에 도로 보여준다)
        "live_video_id": "",        # 거기서 뽑아낸 영상 번호 — 봇이 실제로 쓰는 값
        "say": {                    # 무엇을 말할지
            "donation": True,       # 💝 후원 감사 (리액션이 화면에 나올 때)
            "rank_top": True,       # 👑 1위 바뀜
            "rank_close": False,    # 🔥 접전 — 1·2위 점수차
            "goal": False,          # 🎯 목표 진행·달성
            "dice": False,          # 🎲 주사위 전부
            "idle": True,           # 💬 조용할 때 던지는 질문
        },
        "notices": {                # 📣 되풀이 안내. **분** 단위, 0 이면 끔
            "account_min": 7,       # 💛 후원 계좌
            "rank_min": 0,          # 📊 순위 요약
            "fundjar_min": 0,       # 🏺 모금함
        },
    },
    "target_goal": 50000,
    "goal_offset": 0,          # 💰 게이지 보정(원). 막대의 현재 금액에만 ± 로 얹는다. 방송 끝나면 0
    "theme": "default",
    "theme_fx_enabled": True,   # ✨ 테마를 입었을 때 후원 알림에 테마 모양 입자(하트·리본·보석·금가루)를 뿌릴지
    "reaction_mode": False,
    "reaction_queue": [],
    "reaction_volume": 0.5,
    # 🎬 시그니처 리액션 위젯 크기/위치/축소타이밍 (admin 에디터에서 조절, DEFAULT_STATE에 없으면 재시작 시 소실)
    "reaction_big_scale": 1.0,     # 처음 크게 보일 때 배율
    "reaction_small_scale": 0.6,   # 줄어든 뒤 배율
    "reaction_min_x": 180,         # 줄어든 뒤 위치 X(뷰포트 px, 중심 기준)
    "reaction_min_y": 600,         # 줄어든 뒤 위치 Y(뷰포트 px, 중심 기준)
    "reaction_shrink_delay": 2500, # 크게 보였다가 줄어들기까지(ms)
    # 🔥 시그니처 이름 대형 네온 배너 (화면 정중앙)
    "reaction_title_enabled": True,
    "reaction_title_size": 150,     # 글자 크기(px)
    "reaction_title_duration": 3500,# 노출 시간(ms)
    "reaction_title_suffix": "업",  # 후원자 이름 뒤에 붙는 말 ("홍길동" → "홍길동업")
    # 📊 시그니처 신청 집계 패널 (이번 방송에 어떤 시그니처가 몇 번 신청됐는지)
    "sig_tally_enabled": False,     # 기본 꺼짐 — 켜야 방송 화면에 뜬다
    "sig_tally_limit": 6,           # 화면에 표시할 개수
    "sig_tally": {},                # {item_id: {title, image_url, amount, count}} — 방송마다 초기화

    # 🏅 후원 순위 위젯 — 누가 이번 방송에 얼마를 넣었나
    #    이름·순위는 항상 보이고, 금액과 익명 포함 여부는 켜고 끌 수 있다.
    "donor_rank_enabled": False,    # 기본 꺼짐 — 켜야 방송 화면에 뜬다
    "best_enabled": False,          # 💥 한 방 최고 후원 위젯 — 켜야 방송 화면에 뜬다
    # 💥 이번 방송 '한 방' 최고 후원. 후원이 들어올 때 서버가 적고, 조종실에서 배정하면 받은 멤버가 붙는다.
    #    ⚠️ 방송 1회분이다(reset_session_keys). 밖에서 못 덮게 SERVER_OWNED · PATCH_DENY 에 넣었다.
    #    ⚠️ 고칠 때는 사전을 **새로 만들어** 넣는다 — 이 기본값 객체를 그대로 고치면 다음 방송이 물고 시작한다.
    "best_single": {"name": "", "amount": 0, "at": 0, "id": None, "member": ""},
    # 🎬 방송 시작·끝 화면 — mode: off · start · end. last_snap 은 방송 종료 직전에 떠 둔 오늘의 기록
    "stage_screen": {"mode": "off", "title": "", "start_at": 0, "names": [], "shown_at": 0, "last_snap": None},
    "donor_rank_limit": 5,          # 화면에 표시할 인원
    "donor_rank_amount": True,      # 금액도 보여줄지 (끄면 이름·순위만)
    "donor_rank_anon": False,       # 익명 후원을 순위에 넣을지
    "donor_tally": {},              # {이름: {total, count}} — 방송마다 초기화
    "popup_enabled": True,
    "takeover_enabled": True,
    # 📣 안내 전광판 — 방송 중간중간 저절로 뜨는 안내 문구.
    #    화면이 서버 시계로 "지금 몇 번째 문구를 띄울 차례인가" 를 계산한다
    #    (서버가 주기마다 밀어주면 상태 전체가 접속 대수만큼 나간다).
    "notice_enabled": False,
    "notice_msgs": [
        "계좌로 보내주실 때 닉네임+플레이어 를 적어주시면 자동으로 올라갑니다",
    ],
    "notice_period": 300,      # 몇 초마다 한 번 (기본 5분)
    "notice_speed": 130,       # 초당 몇 픽셀로 흐르는가 (뜨는 시간은 글자 길이가 정한다)
    "notice_now": {},          # 진행자가 지금 띄운 것 {ts, idx}
    # 💛 소액 후원(제일 싼 시그니처보다 적은 것)은 시그니처를 안 튼다. 대신 여기 모아
    #    전광판 순환에 한 줄로 끼운다 — 화면에 이름이 뜨니 무시당한 느낌이 없다.
    #    ⚠️ 한 줄로 묶는다. 사람마다 문구를 만들면 원래 안내가 통째로 밀려난다.
    "notice_donors": [],       # [{name, amount, ts}] — 방송마다 초기화

    "ticker_enabled": True,
    "ticker_speed": 70,
    "ticker_text": "📢 환영합니다! 후원은 방송에 큰 힘이 됩니다!",
    # ⚔️ 대결. players 는 대결자(또는 팀)다.
    #    team_mode 를 켜면 players[i].members 에 넣은 점수판 사람들에게 들어온 후원이
    #    그 팀의 점수로도 함께 올라간다. 꺼두면 예전처럼 손으로만 넣는다.
    #    link 는 조종실이 고른 방식 — 'team'(팀원 여럿) · 'solo'(개인전: 대결자마다 점수판 한 명).
    #    ⚠️ 개인전도 같은 길(members 한 명)을 탄다. 연동 여부는 여전히 team_mode 가 정한다.
    #    [{name, score, members: ["제이양", "밍밍"]}]
    "match_data": {"active": False, "players": [], "time_left_ms": 180000,
                   "is_running": False, "team_mode": False},
    # ⚠️ 실제 계좌를 기본값으로 적지 않는다 — 이 저장소는 공개라 코드와 커밋 이력에 그대로 남는다.
    #    조종실 편집기에서 한 번 입력하면 DB 에 저장돼 계속 유지된다.
    "account": {"bank": "", "acc_num": "", "name": ""},
    "pending_donations": [],
    "latest_donation": {"name": "", "amount": 0, "message": "", "time": 0},
    "extra_game_active": False,
    "extra_bjs": [],
    "roulette_enabled": False,
    # 🎤 노래방 모드: 붙여넣은 유튜브(inst) 영상을 오버레이 화면에 띄운다
    "karaoke_enabled": False,
    "karaoke_video": "",     # 유튜브 영상 ID
    "karaoke_volume": 70,    # 영상 음량 0~100 (유튜브 척도). 노래를 부르는 사람 목소리와 균형을 잡는 값
    # 🏦 계좌 고액후원 영상: 조종실에서 [계좌] 를 누르면 금액대에 맞는 유튜브 영상을 재생한다.
    #    구간은 조종실의 버튼 순서 그대로다(자동 금액 판정은 하지 않는다).
    #    video 는 유튜브 영상 ID(설정 UI가 URL 을 넣어도 ID만 뽑아 저장한다). 비어 있으면 그 구간은 재생 안 함.
    # 🃏 시그 뒤집기 게임. 시그니처를 덮어 깔고 몇 장을 뒤집어, 그 시그니처를
    #    제한 시간 안에 후원으로 받아내는 게임. 사진은 등록된 시그니처를 그대로 쓴다.
    #    ⚠️ 상태는 서버가 정본이다. 원본 프로그램은 localStorage 로 창끼리 맞췄는데,
    #       OBS 브라우저 소스는 조종실 크롬과 저장소를 공유하지 않아 아예 동기화가 안 됐다.
    # 🎲 주사위게임 (부루마블식) — 테두리를 도는 고리 보드, 공용 말 1개.
    #    주사위·황금열쇠 뽑기는 전부 서버가 정한다(화면은 연출만).
    "dicegame": {
        "enabled": False,
        "cols": 7,          # 테두리 고리 — 칸 수는 2*(cols+rows)-4 (기본 20칸)
        "rows": 5,
        "dice": 1,          # 주사위 개수 (1 또는 2). 한 개로 굴린다 — 사장님이 정함
        # 💰 한 판 값. 주사위 한 판은 이 금액의 후원으로 산다.
        #    그 후원이 들어올 때 이미 점수·기여도가 (금액/10000)만큼 올라간다.
        #    그래서 시그니처가 걸렸을 때 시그니처 값에서 이만큼을 빼고 준다
        #    (10만원짜리 시그 = 10점, 한 판 2만원 = 2점 → 기여도 8점).
        "roll_price": 20000,
        # 🏁 한 바퀴 돌 때마다 주는 기여도 (출발 칸을 **지나치면** 준다 — 밟지 않아도 된다)
        "lap_contrib": 10,
        # 🙋 마지막으로 굴린 사람. 다음 굴림에 아무도 안 고르면 이 사람에게 간다.
        #    ⚠️ 차례가 넘어갔는데 안 바꾸면 앞사람에게 들어간다 — 그래서 굴림 응답에
        #       '누구에게 갔는지' 를 반드시 실어 보낸다.
        "last_player": "",
        # 🧩 말 = 선수. 엑셀판에 있는 사람이 그대로 말이 된다.
        #    말이 선 칸의 점수는 그 말의 주인에게 간다.
        #    이름을 여기 박아두면 방송마다 코드를 고쳐야 해서, 명단을 따라가게 했다.
        # 비워 둔다 — 지금 쓰는 점수판 명단에서 저절로 채워진다.
        "pieces": [],
        # 🏆 주사위게임 **전용** 점수판. [{name, pts}]
        #    엑셀판(진짜 기여도)과 완전히 따로 논다 — 여기 점수는 조종실에서
        #    [엑셀판으로 옮기기] 를 눌러야 기여도가 된다. 전원 0점에서 시작하고
        #    마이너스도 된다(사장님이 정함).
        "board": [],
        # 🅿️ 명단에서 잠깐 빠진 이름의 기록 {이름: {pos, laps, shield, choose, pts}}.
        #    같은 이름이 돌아오면 되살린다(오타 고쳤다 되돌리기 · 번외 게임). 방송마다 비운다.
        "parked": {},
        # 🙋 다음에 굴릴 말 번호. 조종실이 안 고르면 이 말이 움직인다.
        "turn": 0,
        # ⬇️ 아래 둘은 옛 저장본 호환용. 마지막으로 움직인 말을 그대로 비춰 둔다.
        "pos": 0,           # 말 위치 (0 = 출발 칸)
        "laps": 0,          # 몇 바퀴 돌았나
        # 칸 목록. [{id, type, label, points, sig}]
        #   type : start(출발) | blank(빈칸) | mission(미션 글) | sig(시그니처)
        #          | score(점수 지급/차감) | key(황금열쇠)
        #   sig  : type=sig 일 때 재생할 시그니처 전체(id·image_url·sound_url·duration…).
        #          ⚠️ 칸을 편집할 때 미리 받아 둔다 — 굴리는 순간 Supabase 에 물으러 가면
        #             잠금 안에서 네트워크를 기다리게 된다(그동안 후원 접수가 멈춘다).
        "tiles": [],
        "keys": [],         # 황금열쇠 덱(글 목록) — 무인증에는 장수만 나간다(뽑기 전까지 비밀)
        "action": {},       # {type: PLACE|ROLL|MOVE, ts, dice, path, from, to, lap, tile, key}
    },

    # 🎱 구슬 핀볼 — 구슬이 못·레일에 튕기며 떨어져, 먼저 바닥에 닿는 순서로 순위가 난다.
    #    ⚠️ 물리는 **방송판이 굴린다**(서버는 심판만 본다). 화면이 여럿이면 각자 굴려
    #       결과가 갈릴 수 있으므로, 판마다 씨앗(seed)을 서버가 줘서 같은 경기를 보게 하고
    #       결과는 **먼저 온 보고 하나만** 받는다 (룰렛 /api/roulette/winner 과 같은 방식).
    "pinball": {
        "enabled": False,       # 화면에 띄울지
        "names": [],            # 참가자 ["밍밍", "양양", ...] — 조종실이 넣는다
        "running": False,       # 굴러가는 중인가. 이게 켜져 있을 때만 결과를 받는다
        "round_id": 0,          # 판 번호. 늦게 온 보고를 가려내는 표식
        "seed": 0,              # 이 판의 씨앗 — 모든 화면이 같은 경기를 본다
        "result": [],           # 도착 순서 ["양양", "밍밍", ...]
        # 🏆 실제 당첨자 — 규칙(rule)·뽑는 수(picks)로 도착 순서에서 골라낸 것.
        #    ⚠️ result[0] 이 1등이 **아니다.** '끝까지 남기' 면 뒤에서부터가 우승자다.
        #       조종실·기록이 예전에 result[0] 을 1등이라 적어 정확히 반대로 나갔다.
        #    저장할 때마다 _pinball_save 가 다시 센다(한 군데에서만 센다).
        "winners": [],
        # 🗺️ 어느 판에서 굴릴까. -1 = 우리가 만든 코스, 0~3 = 가져온 맵.
        #    ⚠️ 씨앗으로 정하지 않고 **사람이 고른다.** 맵마다 걸리는 시간이 크게 달라서
        #       (실측 3~48초) 방송 흐름에 맞는 것을 운영자가 골라야 한다.
        "map": -1,
        # 🏆 누가 이기는가.
        #    "first" = 먼저 골인한 사람 / "last" = 끝까지 안 떨어지고 남은 사람
        #    ⚠️ 이 값이 도착 순서의 **어느 쪽 끝**을 우승자로 읽을지를 정한다.
        #       방송판은 이 값으로 카메라가 따라갈 구슬까지 바꾼다(원본과 같은 방식).
        "rule": "first",
        # 🏅 몇 명을 뽑을까. 1이면 한 명, 3이면 세 명.
        #    "first" 면 먼저 들어온 3명, "last" 면 끝까지 남은 3명이 우승이다.
        "picks": 1,
        # 💢 밀어내기 스킬을 쓸까. 구슬이 가끔 주변을 확 밀어내 순위가 뒤집힌다.
        #    ⚠️ 재미용이다. 상금이 걸린 진지한 추첨이면 꺼 두는 게 낫다.
        "skills": True,
        # 🎱 실제로 굴러갈 구슬 이름들. names 를 펼친 것이다 (양양*3 → 양양 3개).
        #    ⚠️ 손으로 채우지 말 것 — _pinball_save 가 저장할 때마다 다시 센다.
        #       두 군데서 세면 반드시 어긋난다.
        "balls": [],
        "started_at": 0,        # 시작 시각(ms) — 몇 초 걸렸는지 재려고
    },

    # 🧩 퀴즈판(초성 · 사자성어, 2026-10-06) — features/quiz.py 가 모양을 맞춘다(_quiz_state).
    #    방송판에는 네모칸(tiles)만. 정답(cur)은 조종실에만 — strip_private_state 가 뺀다.
    "quiz": {
        "kind": "chosung",      # 'chosung' 초성 · 'idiom' 사자성어
        "cur": None,            # {'kind', 'answer', 'note'} — 지금 문제(정답 · 분류/뜻)
        "tiles": [],            # 방송판 네모칸 [{'c': 글자, 's': 'q'|'g'|'b'|'h'|'o'}]
        "revealed": False,
        "used": {"chosung": [], "idiom": []},     # 이번 방송에 나온 정답 — 방송 시작 · 종료 때 비운다
        "custom": {"chosung": [], "idiom": []},   # 내 문제 [[정답, 분류/뜻], …] — 방송이 바뀌어도 남는다
        "order": {"chosung": [], "idiom": []},    # 그날 낼 순서(남은 것) — 조종실에서 고친다. 방송 시작 · 종료 때 새로 섞는다
    },

    "siggame": {
        "enabled": False,
        "cols": 4,
        "rows": 4,
        "opacity": 1.0,
        "target": 5,       # 뒤집을 장수. 이만큼 뒤집으면 그게 이번 판의 목표가 된다.
        # 목표만 한 줄로 올려둔 상태인가. 진행자가 조종실 버튼으로 켜고 끈다.
        # (예전에는 목표를 다 뒤집는 순간 화면이 저 혼자 올렸다)
        "compact": False,
        # 조종실이 고른 시그니처들: [{sig_id, title, image}]
        "picks": [],
        # 판에 깔린 카드. id 는 화면에 보이는 번호(1..N)다.
        # [{id, sig_id, image, title, amount, state, flippedAt, doneAt}]
        #   state    : HIDDEN(덮임) | REVEALED(공개됨)
        #   flippedAt: 목표로 뒤집은 시각. 이게 있어야 '목표'다.
        #              (게임이 끝나고 전부 공개한 카드는 REVEALED 이지만 목표가 아니다)
        #   doneAt   : 받아냈다고 표시한 시각. 진행자가 직접 누른다.
        "cards": [],
        "timer": {"status": "STOPPED", "timeLeft": 600, "expiresAt": None},
        # 오버레이가 재생할 연출 신호.
        # {type: PLACE|SHUFFLE|FLIP|DONE|ALLCLEAR|REVEAL, ts, ...}
        "action": None,
    },
    # ⏸️ 알림(시그니처) 일시정지. 중요한 순간에 말이 끊기지 않게 잠깐 멈추는 스위치.
    #    큐는 그대로 쌓이고, 풀면 순서대로 이어서 나간다. '전체 비우기'와 전혀 다르다.
    "reaction_paused": False,
    "account_video_tiers": [
        {"min": 200000,  "label": "20만",    "video": ""},
        {"min": 300000,  "label": "30만",    "video": ""},
        {"min": 400000,  "label": "40만",    "video": ""},
        {"min": 500000,  "label": "50만",    "video": ""},
        {"min": 600000,  "label": "60~70만", "video": ""},
        {"min": 800000,  "label": "80~90만", "video": ""},
        {"min": 1000000, "label": "100만",   "video": ""},
        {"min": 2000000, "label": "200만",   "video": ""},
        {"min": 3000000, "label": "300만",   "video": ""},
        {"min": 5000000, "label": "500만",   "video": ""},
    ],
    # 💸 서버 깨워두기. 켜면 Render 무료 인스턴스 시간을 하루 24시간씩 먹는다(월 720h / 한도 750h).
    #    방송 중에는 SSE 연결이 붙어 있어 저절로 깨어 있으므로 기본은 꺼둔다.
    #    방송 준비하며 자리를 비울 때만 조종실에서 켜는 용도.
    "self_ping_enabled": False,
    # 🎰 슬롯머신
    # load_data()는 DEFAULT_STATE에 있는 키만 복원하므로, 여기 없으면 재시작 때 조용히 사라진다.
    #    ⚠️ 기본값은 꺼 둔다. 켜져 있으면 오버레이가 슬롯판을 그리고,
    #    그러면 body.game-on 이 붙어 후원 게이지 옆 금액이 가려진다.
    "slot_enabled": False,
    # 🔊 효과음(주사위·후원·목표·1등탈환). 방송 중에 거슬리면 바로 꺼야 하므로 스위치를 둔다.
    #    ⚠️ 기본은 켜짐 — 없으면 왜 소리가 안 나는지 찾느라 방송 중에 헤맨다.
    "sfx_enabled": True,
    "slot_pool": [],   # 이번 방송에 쓸 시그니처 id 목록. 비어 있으면 전체를 후보로 사용.
    # 💰 슬롯 한 판 값. 이 금액의 후원으로 한 판을 산다.
    #    그 후원이 들어올 때 이미 점수·기여도가 (금액/10000)만큼 올라갔으므로,
    #    당첨 시그니처 값에서 이만큼을 빼고 기여도를 준다 (주사위와 같은 셈).
    "slot_price": 20000,
    # 🎯 목표 100% 달성 연출 (달성하면 pending, 운영자가 승인해야 송출)
    "goal_event_pending": False,
    "goal_event_approved": False,
    # 🏃 퇴근전쟁(퇴근빵): 켜면 랭킹판 자리에 개인별 목표 진행바가 뜬다
    "home_race_enabled": False,
    "home_goals": {},         # {플레이어 이름: 퇴근 목표 점수}
    "home_race_notified": [], # 이미 퇴근 카드를 띄운 사람 (송출 후 다시 생기는 것 방지)
    # 🔥 지옥탈출 (2026-09-21 추석 방송): 퇴근빵 대신 마지막에 한다.
    #    '시작' 을 누르는 순간의 등수로 목표가 정해지고(1등 50·2등 40·3등 30·4등 20, 단위 점=만원),
    #    **그 뒤에 받은 점수만** 센다(base = 시작 순간 점수). 채우면 그 사람은 탈출 — 끝.
    #    퇴근빵(home_goals)과 따로 둔다 — 대표님이 방송 전에 넣어 둔 퇴근빵 목표를 덮지 않게.
    #    서버만 바꾼다(/api/hell/*) — SERVER_OWNED·PATCH_DENY 에 들어 있다.
    #    ⚠️ 못 채웠다고 벌칙이 생기지 않는다(대표님 2026-09-22: "퇴근빵처럼 채우면 끝, 벌칙 룰렛은 따로").
    "hell": {"on": False, "started_at": 0, "base": {}, "goals": {}, "escaped": []},
    # 💾 세이브 슬롯 (대표님 2026-09-22: "말 그대로 세이브 파일") — 누르면 저장해 둔 그대로 바뀐다.
    #    한 칸 = {id, name, layout(위젯 자리·크기), switches(위젯 켜기/끄기), board(떠 있던 게임판), saved_at}
    #    ⚠️ 게임 속 내용(룰렛 칸·핀볼 명단·점수)은 안 담는다 — 누르는 순간의 내용을 그대로 쓴다.
    #    ⚠️ 진행 기록이 있는 지옥탈출·퇴근빵·대결은 불러와도 켜지도 꺼지지도 않는다.
    #    방송이 바뀌어도 남는다(reset_session_keys 에 안 넣는다). 서버만 바꾼다(/api/presets/*).
    "layout_presets": [],
    "layout_rev": 0,          # 슬롯을 불러올 때마다 +1 — 열려 있는 편집기가 보고 자리를 다시 읽는다
    "logs": [],               # 점수/기여도 지급 로그 [{time, name, val}] — DEFAULT_STATE에 있어야 재로드 시 유지된다
    "match_logs": [],         # 대결(임시게임) 전용 지급 로그. logs 와 같은 이유로 여기 있어야 살아남는다
    "neon_speed": 1.5,        # 조명 속도 슬라이더(초). 방송 종료 시 보존 대상 목록에도 들어 있는 '설정값'이다
    "effect_trigger": None,   # 조명 상태 {time, color, infinite}. 일회성 연출이 아니라 '켜 둔 상태'라 유지해야 한다
    "broadcast_active": False,
    "broadcast_started_at": 0,   # 📊 이번 방송을 시작한 시각(ms) — 조종실 클릭 기록을 방송별로 나눈다
    "saved_colors": ['#ff0055', '#00e5ff', '#ff9100', '#d500f9', '#00ff00', '#ffff00', '#ff0000', '#0000ff', '#ffffff'],
    "version": 1,
    "roulette": {
        "command": None,
        "command_time": 0,
        "weight_type": "equal",
        "select_name": "",
        "select_index": -1,
        "winner_name": None,
        "is_spinning": False,
        "item_source": "bj",
        "custom_items": ["벌칙 1", "벌칙 2", "벌칙 3", "벌칙 4", "벌칙 5"]
    }
}

MEMORY_STATE = None

# ==========================================
# 🗄️ 데이터베이스 핵심 로직
# ==========================================
def init_db():
    if not IS_POSTGRES:
        if not os.path.exists(DB_FILE) and os.path.exists(DB_FILE + '.bak'):
            try:
                shutil.copy2(DB_FILE + '.bak', DB_FILE)
                print("[DB 자동 복구] 백업 본으로 DB 복구 성공!")
            except Exception as e:
                print(f"[DB 자동 복구 실패] {e}")

    with get_db_connection() as conn:
        cursor = conn.cursor()
        if not IS_POSTGRES:
            try:
                cursor.execute("PRAGMA journal_mode=WAL;")
            except Exception:
                pass
        
        cursor.execute("CREATE TABLE IF NOT EXISTS kv_store (key TEXT PRIMARY KEY, value TEXT)")
        cursor.execute("CREATE TABLE IF NOT EXISTS players (name TEXT PRIMARY KEY, score INTEGER, contribution INTEGER)")
        
        if IS_POSTGRES:
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS donation_history (
                    id SERIAL PRIMARY KEY,
                    timestamp TEXT,
                    name TEXT,
                    amount INTEGER,
                    current_total INTEGER, 
                    message TEXT,
                    source TEXT,
                    tx_id TEXT
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS snapshots (
                    id SERIAL PRIMARY KEY,
                    timestamp TEXT,
                    state_json TEXT,
                    summary TEXT
                )
            """)
        else:
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS donation_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT,
                    name TEXT,
                    amount INTEGER,
                    current_total INTEGER, 
                    message TEXT,
                    source TEXT,
                    tx_id TEXT
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS snapshots (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT,
                    state_json TEXT,
                    summary TEXT
                )
            """)
        
        # 아래 신규 테이블들이 공통으로 쓰는 자동증가 기본키 표현
        pk = "SERIAL PRIMARY KEY" if IS_POSTGRES else "INTEGER PRIMARY KEY AUTOINCREMENT"

        # 🏦 [은행 원장] 점수/기여도 변동을 통장처럼 한 줄씩 남긴다.
        # 절대값을 덮어쓰는 대신 "변동분 + 거래 후 잔액"을 쌓아두므로,
        # 잔액이 어긋나면 원장을 다시 합산해 복구할 수 있다. (append-only)
        cursor.execute(f"""
            CREATE TABLE IF NOT EXISTS bank_ledger (
                id {pk},
                timestamp TEXT NOT NULL,
                player_name TEXT NOT NULL,
                tx_type TEXT NOT NULL,
                score_change INTEGER NOT NULL,
                score_balance INTEGER NOT NULL,
                contrib_change INTEGER NOT NULL,
                contrib_balance INTEGER NOT NULL,
                description TEXT
            )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_bank_ledger_player ON bank_ledger(player_name)")

        # 🧠 [후원자 기억] "이 후원자의 돈이 누구에게 갔나" 를 남긴다.
        #
        # ⚠️ 지금까지 이 연결이 어디에도 없었다. donation_history 는 후원자를,
        #    bank_ledger 는 받은 사람을 갖고 있는데 둘을 잇는 것이 없었다.
        #    그래서 "ㄱㅇㅈ" 같은 메시지는 영영 풀 수 없었다 — 글자만 봐서는 모르지만
        #    "이 사람은 지난 세 번 다 밍밍에게 갔다" 는 것을 알면 풀린다.
        # ⚠️ 방송이 끝나도 지우지 않는다. 방송을 거듭할수록 정확해지는 것이 요점이다.
        #    (end_broadcast 는 players·donation_history·snapshots 와 kv_store 일부만 지운다)
        cursor.execute(f"""
            CREATE TABLE IF NOT EXISTS donor_memory (
                id {pk},
                timestamp TEXT NOT NULL,
                donor TEXT NOT NULL,
                player TEXT NOT NULL,
                amount INTEGER,
                message TEXT
            )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_donor_memory_donor ON donor_memory(donor)")

        # 🏷️ [별명 기억] 메시지에 있던 말이 어느 플레이어에게 이어졌는지 센다.
        #    시청자는 본명 대신 별명·줄임말을 쓴다("ㅁㅁ", "밍밍이", "1번").
        #    배정할 때마다 조용히 쌓아두면, 다음부터는 AI 를 부르지 않고도 맞힌다.
        cursor.execute(f"""
            CREATE TABLE IF NOT EXISTS alias_memory (
                id {pk},
                token TEXT NOT NULL,
                player TEXT NOT NULL,
                hits INTEGER NOT NULL DEFAULT 1,
                updated TEXT
            )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_alias_memory_token ON alias_memory(token)")

        # 👑 [특별 후원자(VIP)] 직접 준 등급(예외용). 진짜 등급은 이번 방송 순위(_vip_live)다.
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS vip_donators (
                name TEXT PRIMARY KEY,
                grade TEXT NOT NULL,
                custom_color TEXT DEFAULT '#ffd700',
                badge TEXT DEFAULT '👑'
            )
        """)
        # 2026-09-09 등급이 '이번 방송 순위' 로 바뀌었다 — 옛 평생누적 등급은 한 번 비운다
        try:
            _vip_wipe_legacy_once(cursor)
        except Exception as _e:
            print(f'⚠️ [VIP] 옛 등급 비우기 실패(계속합니다): {_e}', flush=True)

        # 🚫 [순위에서 뺄 이름] 익명·테스트처럼 명단에 넣으면 안 되는 이름.
        # ⚠️ 후원 기록 자체는 절대 지우지 않는다(바로 아래 영구 보관 장부 참고).
        #    여기 적힌 이름은 순위·후보에서만 안 보이고, 돈은 장부에 그대로 남는다.
        #    이름은 _norm_donor 로 다듬어 넣는다 — '홍길동님' 과 '홍길동' 이 갈리면 안 된다.
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS donor_excluded (
                name TEXT PRIMARY KEY,
                memo TEXT DEFAULT '',
                added_at TEXT
            )
        """)

        # 📚 [영구 보관 장부] 방송 종료 시 donation_history는 초기화되지만,
        # 여기로 먼저 복사해 두므로 지난 방송 기록이 영구히 남는다. (append-only, 절대 삭제하지 않음)
        # 📊 조종실 클릭 기록 — 방송(session)마다 '무엇을 몇 번' 만. 누가·언제·무슨 값은 안 적는다.
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS ui_clicks (
                session TEXT NOT NULL,
                key TEXT NOT NULL,
                label TEXT,
                tab TEXT,
                n INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (session, key)
            )
        """)
        cursor.execute(f"""
            CREATE TABLE IF NOT EXISTS donation_archive (
                id {pk},
                archived_at TEXT,
                session_label TEXT,
                timestamp TEXT,
                name TEXT,
                amount INTEGER,
                current_total INTEGER,
                message TEXT,
                source TEXT,
                tx_id TEXT
            )
        """)

    # 💡 [스키마 마이그레이션 패치] 기존 테이블에 컬럼 동적 추가
    # ⚠️ Postgres는 트랜잭션 안에서 한 문장이 실패하면 그 트랜잭션 전체가 취소된다.
    # 예전처럼 위 CREATE TABLE들과 같은 트랜잭션에서 ALTER를 시도하면,
    # "컬럼이 이미 존재" 오류 하나 때문에 앞서 만든 테이블이 전부 롤백되어
    # 빈 DB에서는 테이블이 하나도 생기지 않는다. (SQLite에서는 발생하지 않아 발견이 늦었다)
    # 따라서 ALTER는 각각 별도 연결(트랜잭션)에서 실행한다.
    for stmt in ("ALTER TABLE snapshots ADD COLUMN summary TEXT",
                 "ALTER TABLE donation_history ADD COLUMN tx_id TEXT"):
        try:
            with get_db_connection() as conn2:
                conn2.cursor().execute(stmt)
        except Exception:
            pass  # 이미 존재하면 정상적으로 무시

def load_data():
    global MEMORY_STATE, LAST_PERSISTED
    if MEMORY_STATE is not None:
        return MEMORY_STATE
    init_db()

    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(db_query("SELECT key, value FROM kv_store"))
            kv_data = {row[0]: json.loads(row[1]) for row in cursor.fetchall()}
            cursor.execute(db_query("SELECT name, score, contribution FROM players ORDER BY contribution DESC"))
            bjs = [{"name": row[0], "score": row[1], "contribution": row[2]} for row in cursor.fetchall()]
    except Exception as e:
        print(f"⚠️ [DB 로드 오류] {e}")
        # DB 로드 실패 시 데이터를 덮어써서 날려버리는 것을 막기 위해 예외를 상위로 전파합니다.
        raise e

    if not kv_data and not bjs:
        # ⚠️ 반드시 깊은 복사. 얕은 복사면 중첩 객체(bjs/account/pending_donations 등)가
        # DEFAULT_STATE와 공유되어, 이후 append/수정이 기본값 자체를 오염시킨다.
        MEMORY_STATE = copy.deepcopy(DEFAULT_STATE)
        save_data(MEMORY_STATE, is_initial=True, sync=True)
        return MEMORY_STATE

    state = {}
    for key, default_val in DEFAULT_STATE.items():
        if key == "bjs": 
            state["bjs"] = bjs
        elif key in kv_data: 
            state[key] = kv_data[key]
        else: 
            # ⚠️ 기본값 **객체를 그대로** 넣으면 안 된다(복사본을 넣는다) — 저장본에 없던 키(새로 생긴 퀴즈 등)를
            #    고치면 DEFAULT_STATE 자체가 바뀌어, 복원 · 초기화가 방금 내용을 물고 오고 저장 비교도 틀린다(10-06 점검)
            state[key] = copy.deepcopy(default_val)
            
    # 🏺 모금함 보정 — 옛 저장본에는 이 키가 없다.
    # ⚠️ 위 반복문은 없는 키에 기본값 **객체를 그대로** 넣는다. 그 뒤 score 를 더하면
    #    DEFAULT_STATE 안의 사전이 같이 바뀌어, 다음 방송이 남의 금액을 물고 시작한다.
    _fj = state.get("fundjar")
    if not isinstance(_fj, dict) or _fj is DEFAULT_STATE["fundjar"]:
        state["fundjar"] = copy.deepcopy(DEFAULT_STATE["fundjar"])

    # 🤖 진행봇 설정 보정 — 위와 같은 이유(기본값 객체를 그대로 물면 안 된다) + 속칸도 채운다.
    #    ⚠️ 나중에 스위치를 하나 더 늘려도 옛 저장본이 그 칸 없이 돌아오면 안 된다.
    _ab = state.get("announce_bot")
    if not isinstance(_ab, dict) or _ab is DEFAULT_STATE["announce_bot"]:
        _ab = copy.deepcopy(DEFAULT_STATE["announce_bot"])
        state["announce_bot"] = _ab
    # ⚠️ 속칸(say·notices)만 채우면 위 칸이 빠진다. 옛 저장본에는 주소 칸이 없다.
    for _k in ("live_url", "live_video_id"):
        _ab.setdefault(_k, DEFAULT_STATE["announce_bot"][_k])
    for _sub in ("say", "notices"):
        if not isinstance(_ab.get(_sub), dict):
            _ab[_sub] = copy.deepcopy(DEFAULT_STATE["announce_bot"][_sub])
        else:
            for _k, _v in DEFAULT_STATE["announce_bot"][_sub].items():
                _ab[_sub].setdefault(_k, _v)

    # 🎱 핀볼 보정 — 위 둘과 같은 이유(기본값 객체를 그대로 물면 안 된다) + 당첨자 칸.
    #    ⚠️ 옛 저장본에는 winners 칸이 없다. 조종실이 그걸 못 읽으면 '끝까지 남기' 의
    #       1등을 도착 순서 **맨 앞**(= 실제로는 꼴찌)으로 보여준다 — 고친 버그로 되돌아간다.
    #       판을 한 번 굴리면 저절로 채워지지만, 그 한 판 동안 거짓말을 하게 된다.
    _pb0 = state.get("pinball")
    if not isinstance(_pb0, dict) or _pb0 is DEFAULT_STATE["pinball"]:
        _pb0 = copy.deepcopy(DEFAULT_STATE["pinball"])
        state["pinball"] = _pb0
    for _k, _v in DEFAULT_STATE["pinball"].items():
        _pb0.setdefault(_k, copy.deepcopy(_v))
    if not _pb0.get("winners"):
        _pb0["winners"] = _pinball_winners(_pb0.get("result"), _pb0.get("rule"), _pb0.get("picks"))

    # saved_colors 보정 (6개 -> 9개로 확장 및 하위 호환 마이그레이션)
    default_colors = ['#ff0055', '#00e5ff', '#ff9100', '#d500f9', '#00ff00', '#ffff00', '#ff0000', '#0000ff', '#ffffff']
    if 'saved_colors' in state:
        if not isinstance(state['saved_colors'], list):
            state['saved_colors'] = default_colors
        elif len(state['saved_colors']) < 9:
            for i in range(len(state['saved_colors']), 9):
                state['saved_colors'].append(default_colors[i])
    else:
        state['saved_colors'] = default_colors

    # 🏦 계좌 고액후원 영상 구간 마이그레이션.
    #    구간 목록(금액·이름)은 코드가 정본이고, DB 에는 '어느 구간에 어떤 영상을 넣었는지'만 남는다.
    #    위 for 문이 DB 값을 그대로 쓰기 때문에, 예전에는 코드에서 구간을 바꿔도
    #    조종실에는 옛날 구간이 계속 보였다(DB 가 이김). 그래서 여기서 새 목록으로 갈아끼운다.
    #    금액(min)이 같은 구간에 넣어둔 영상은 그대로 옮겨주고, 사라진 구간의 영상은 로그로 알린다.
    default_tiers = DEFAULT_STATE['account_video_tiers']
    saved_tiers = state.get('account_video_tiers')
    kept = {}
    if isinstance(saved_tiers, list):
        for t in saved_tiers:
            if not isinstance(t, dict):
                continue
            vid = str(t.get('video') or '').strip()
            if not vid:
                continue
            try:
                kept[int(t.get('min'))] = vid
            except (TypeError, ValueError):
                pass
    # 금액이 딱 맞는 구간에 먼저 넣고, 없어진 구간의 영상은 '그 금액을 담는 새 구간'으로 내려보낸다.
    # (예: 없어진 70만 구간의 영상 → 새 60~70만 구간). 그렇게도 갈 곳이 없을 때만 버린다.
    merged = [{"min": t['min'], "label": t['label'], "video": kept.get(t['min'], "")}
              for t in default_tiers]
    by_min = {t['min']: t for t in merged}
    for old_min in sorted(kept):
        if old_min in by_min:
            continue
        fits = [t for t in merged if t['min'] <= old_min]
        target = max(fits, key=lambda t: t['min']) if fits else None
        if target and not target['video']:
            target['video'] = kept[old_min]
            print(f"ℹ️ [계좌영상] 없어진 {old_min:,}원 구간의 영상을 '{target['label']}' 로 옮겼습니다", flush=True)
        else:
            print(f"⚠️ [계좌영상] {old_min:,}원 구간의 영상은 갈 곳이 없어 버립니다: {kept[old_min]}", flush=True)
    state['account_video_tiers'] = merged

    
    MEMORY_STATE = state
    # DB에서 막 읽어온 값이 곧 "DB에 저장된 내용"이므로 비교 기준을 여기에 맞춘다.
    # (초기화하지 않으면 첫 저장 때 모든 점수가 '수동 점수 조작'으로 장부에 잘못 기록된다)
    LAST_PERSISTED = copy.deepcopy(state)
    return MEMORY_STATE

db_write_queue = queue.Queue()

# 마지막 DB 저장 실패 정보 (조용한 실패 방지 — /api/server/status 로 노출)
LAST_DB_ERROR = {"message": None, "time": None}

# 마지막으로 DB에 성공적으로 기록한 상태의 깊은 복사본.
# 변경분만 저장하기 위한 비교 기준이며, MEMORY_STATE와 별개여야 한다.
LAST_PERSISTED = None

def db_worker():
    while True:
        done = None
        try:
            new_data, is_initial, done = db_write_queue.get()
            if new_data is not None:          # None 은 '여기까지 처리됐다'를 알리는 표식(drain_db_writes)
                try:
                    save_data_sync(new_data, is_initial)
                except Exception as _se:
                    # 💾 동기 저장을 기다리는 쪽이 '실패했다'는 걸 알 수 있게 이벤트에 붙여 둔다.
                    #    ⚠️ 예전에는 done 만 깨워서, 방송 시작·종료가 저장에 실패해도 '성공' 이라고 답했다
                    #       (그 사이 kv_store 는 이미 지워져 있어, 재시작하면 설정이 통째로 사라진다).
                    if done is not None:
                        done.error = _se
                    raise
            db_write_queue.task_done()
        except Exception as e:
            print(f"❌ [비동기 DB 저장 백그라운드 오류] {e}")
            time.sleep(1)
        finally:
            # 동기 저장을 기다리는 쪽이 영원히 멈추지 않도록 실패해도 반드시 깨운다
            if done is not None:
                done.set()

threading.Thread(target=db_worker, daemon=True).start()

def save_data_sync(new_data, is_initial=False, _retry=True):
    global LAST_PERSISTED
    # ⚠️ 반드시 "마지막으로 DB에 쓴 내용"과 비교해야 한다.
    # 예전에는 MEMORY_STATE와 비교했는데, 호출부가 load_data()가 돌려준 객체를
    # 그 자리에서 수정하므로 MEMORY_STATE와 new_data가 같은 객체가 되어
    # "변경된 키 없음"으로 판정 → kv_store에 아무것도 저장되지 않았다.
    # (플레이어 테이블은 매번 통째로 다시 쓰기 때문에 이 문제가 드러나지 않았다)
    old_data = LAST_PERSISTED if LAST_PERSISTED is not None else DEFAULT_STATE

    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            # 1. 점수/기여도 변동을 장부 + 은행 원장에 기록 (영수증 발급)
            if not is_initial:
                old_scores = {p["name"]: p.get("score", 0) for p in old_data.get("bjs", [])}
                old_contribs = {p["name"]: p.get("contribution", 0) for p in old_data.get("bjs", [])}
                now_str = time.strftime('%Y-%m-%d %H:%M:%S')
                ledger_rows = []
                for new_p in new_data.get("bjs", []):
                    p_name = new_p["name"]
                    p_score = int(new_p.get("score") or 0)
                    p_contrib = int(new_p.get("contribution") or 0)
                    score_diff = p_score - old_scores.get(p_name, 0)
                    contrib_diff = p_contrib - old_contribs.get(p_name, 0)

                    # ⚠️ 예전에는 여기서 donation_history 에도 한 줄을 넣었다.
                    #    그런데 그 표의 amount 는 '후원 금액(원)' 칸이다. 점수(점)를 거기 넣으니
                    #    한 열에 30,000(원)과 1(점)이 섞여, 합계도 평균도 의미가 없어졌다.
                    #    (실제로 -1 같은 값이 '후원 -1원'처럼 보였다)
                    #    점수 변동은 바로 아래 bank_ledger 에 score_change/score_balance 로
                    #    이미 온전히 남고 조종실의 '점수 통장 내역'에서 볼 수 있으므로,
                    #    돈 장부에는 넣지 않는다. 장부는 원, 통장은 점 — 단위를 섞지 않는다.
                    # 🏦 은행 원장: 변동분과 거래 후 잔액을 남겨 나중에 재정산할 수 있게 한다
                    if score_diff != 0 or contrib_diff != 0:
                        ledger_rows.append((now_str, p_name, "MANUAL_CHANGE", score_diff, p_score,
                                            contrib_diff, p_contrib,
                                            f"점수 {score_diff:+} / 기여도 {contrib_diff:+}"))

                # N분할처럼 여러 명이 한꺼번에 바뀔 때 왕복이 인원수만큼 늘지 않도록 묶어서 넣는다
                if ledger_rows:
                    ph = ', '.join([('(%s, %s, %s, %s, %s, %s, %s, %s)' if IS_POSTGRES else '(?, ?, ?, ?, ?, ?, ?, ?)')] * len(ledger_rows))
                    cursor.execute(
                        f"""INSERT INTO bank_ledger
                            (timestamp, player_name, tx_type, score_change, score_balance,
                             contrib_change, contrib_balance, description) VALUES {ph}""",
                        [v for r in ledger_rows for v in r]
                    )

            # 2. 플레이어 테이블 갱신
            # ⚠️ 예전에는 DELETE 전체 후 재INSERT였다. 이제는 사라진 플레이어만 지우고
            #    나머지는 UPSERT한다 (원장과 잔액을 함께 다루므로 통째로 지우면 위험하다)
            new_bjs = new_data.get("bjs", [])
            valid_names = [bj["name"] for bj in new_bjs if bj.get("name")]
            if valid_names:
                if IS_POSTGRES:
                    cursor.execute("DELETE FROM players WHERE NOT (name = ANY(%s))", (valid_names,))
                else:
                    placeholders = ', '.join(['?'] * len(valid_names))
                    cursor.execute(f"DELETE FROM players WHERE name NOT IN ({placeholders})", valid_names)
            else:
                cursor.execute(db_query("DELETE FROM players"))

            # ⚡ 플레이어를 한 명씩 저장하면 인원수만큼 왕복이 생긴다.
            #    한 문장에 여러 행을 담아 왕복을 1회로 줄인다.
            if new_bjs:
                rows = [(bj["name"], bj.get("score", 0), bj.get("contribution", 0)) for bj in new_bjs]
                if IS_POSTGRES:
                    ph = ', '.join(['(%s, %s, %s)'] * len(rows))
                    cursor.execute(
                        f"INSERT INTO players (name, score, contribution) VALUES {ph} "
                        "ON CONFLICT (name) DO UPDATE SET score = EXCLUDED.score, contribution = EXCLUDED.contribution",
                        [v for r in rows for v in r]
                    )
                else:
                    ph = ', '.join(['(?, ?, ?)'] * len(rows))
                    cursor.execute(
                        f"INSERT INTO players (name, score, contribution) VALUES {ph} "
                        "ON CONFLICT(name) DO UPDATE SET score = excluded.score, contribution = excluded.contribution",
                        [v for r in rows for v in r]
                    )

            # 3. 설정 상태 키-값 저장 (변경된 값만) — 이것도 한 문장으로 묶어 왕복을 줄인다
            kv_rows = []
            for key, value in new_data.items():
                if key == "bjs":
                    continue
                new_val_str = json.dumps(value, ensure_ascii=False)
                old_val = old_data.get(key)
                old_val_str = json.dumps(old_val, ensure_ascii=False) if old_val is not None else None
                if is_initial or old_val_str != new_val_str:
                    kv_rows.append((key, new_val_str))

            if kv_rows:
                if IS_POSTGRES:
                    ph = ', '.join(['(%s, %s)'] * len(kv_rows))
                    cursor.execute(
                        f"INSERT INTO kv_store (key, value) VALUES {ph} "
                        "ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value",
                        [v for r in kv_rows for v in r]
                    )
                else:
                    ph = ', '.join(['(?, ?)'] * len(kv_rows))
                    cursor.execute(
                        f"INSERT OR REPLACE INTO kv_store (key, value) VALUES {ph}",
                        [v for r in kv_rows for v in r]
                    )
                            
        # 커밋 성공 후에만 비교 기준을 갱신한다 (실패 시 다음 저장에서 다시 시도되도록)
        LAST_PERSISTED = new_data
        LAST_DB_ERROR["message"] = None
    except Exception as e:
        # 재사용하던 연결을 서버가 끊어둔 경우일 수 있다.
        # get_db_connection이 이미 죽은 연결을 버렸으므로, 한 번만 새 연결로 다시 시도한다.
        if _retry:
            print(f"⚠️ [DB 저장 재시도] {e}")
            return save_data_sync(new_data, is_initial, _retry=False)
        # 조용히 넘어가면 저장된 줄 알고 방송을 계속하게 된다. 상태에 남겨 컨트롤러가 경고할 수 있게 한다.
        LAST_DB_ERROR["message"] = str(e)
        LAST_DB_ERROR["time"] = time.strftime('%Y-%m-%d %H:%M:%S')
        print(f"❌ [DB 저장 실패] {e}")
        raise

def reset_session_keys(state):
    """방송 1회분에만 유효한 상태를 초기화한다.

    ⚠️ 새 기능을 넣을 때 여기에 등록하지 않으면, 서버를 끄지 않고 방송을 두 번 할 때
    지난 방송의 흔적이 남아 오작동한다. (예: goal_event_approved 가 남아 2회차에는
    목표 달성 배너가 영영 안 뜨고, home_race_notified 에 남은 이름은 퇴근 카드를 못 받는다)
    """
    state['goal_event_pending'] = False
    state['goal_event_approved'] = False
    state['home_race_notified'] = []   # '누가 이미 퇴근 카드를 받았나'는 지난 방송의 기록이라 비운다
    state['sig_tally'] = {}            # 시그니처 신청 집계도 방송 1회분 기록이라 비운다
    state['donor_tally'] = {}          # 후원 순위도 이번 방송분만 센다
    state['notice_donors'] = []        # 전광판 소액 후원자도 이번 방송분만
    state['best_single'] = {"name": "", "amount": 0, "at": 0, "id": None, "member": ""}   # 💥 한 방 최고 후원도 이번 방송분만
    # 🔥 지옥탈출도 이번 방송분이다 — 시작 순간 점수(base)는 지난 방송 점수라 남으면 '받은 돈' 이 틀어진다
    state['hell'] = copy.deepcopy(DEFAULT_STATE['hell'])
    # 💰 게이지 보정도 이번 방송 것이다.
    #    ⚠️ 방송 종료 쪽에서만 0 으로 돌리고 있었다. 그런데 load_data() 는 메모리 상태를
    #       그대로 돌려주므로, 종료를 안 거치고 다음 방송을 시작하면 지난주 보정값이
    #       그대로 남아 게이지가 처음부터 그만큼 올라간 채로 시작한다.
    state['goal_offset'] = 0
    # 🎲🃏 게임판 진행 상태도 방송 1회분이다. 종료 뒤 오버레이에 CLEAR 카드판과 주사위 말이
    #    그대로 남아 있었다. 칸 배치(tiles)와 고른 시그니처(picks)는 다음 주에도 쓰는 설정이라 남기고,
    #    보이기·말 위치·바퀴·카드·타이머만 걷는다.
    _dg = state.get('dicegame')
    if isinstance(_dg, dict):
        _dg.update({'enabled': False, 'pos': 0, 'laps': 0, 'action': {}})
        for _p in (_dg.get('pieces') or []):
            if isinstance(_p, dict):
                _p['pos'] = 0; _p['laps'] = 0
                _p['shield'] = False; _p['choose'] = False   # 실드 · '원하는 곳으로' 도 이번 방송 것
        _dg['turn'] = 0
        # 🏆 주사위 전용 점수판 · 맡아 둔 기록도 방송 1회분이다.
        #    ⚠️ 예전엔 말 자리만 비우고 점수판은 남겼다 — [엑셀판으로 옮기기] 를 깜빡하면
        #       지난주 점수가 이번 주 기여도에 섞였다. 끝낼 때 남아 있으면 조종실이 먼저 묻는다.
        for _r in (_dg.get('board') or []):
            if isinstance(_r, dict):
                _r['pts'] = 0
        _dg['parked'] = {}
        _dg['last_player'] = ''
    # 🎱 핀볼도 방송 1회분이다. 참가자 명단(names)은 다음에도 쓰므로 남기고,
    #    보이기·굴러가는 중·결과만 걷는다.
    # 🧩 퀴즈도 방송 1회분 — 지금 문제 · 그날 나온 문제를 비운다(내 문제는 남긴다). 본문은 features/quiz.py
    from features.quiz import quiz_reset_session
    quiz_reset_session(state)
    _pb = state.get('pinball')
    if isinstance(_pb, dict):
        _pb.update({'enabled': False, 'running': False, 'result': [], 'started_at': 0})
    _sg = state.get('siggame')
    if isinstance(_sg, dict):
        _sg.update({'enabled': False, 'cards': [], 'action': None, 'compact': False,
                    'timer': {'status': 'STOPPED', 'timeLeft': 600, 'expiresAt': None}})
    # 📺 무대도 방송 1회분 — 비운다. 고정 자리·알림은 설정이라 남긴다(예전 스위치도 안 지웠다)
    showmod.reset_session(state)
    # ⚠️ home_goals(퇴근빵 개인별 목표)는 여기서 지우면 안 된다.
    #    이건 '지난 방송의 흔적'이 아니라 운영자가 방송 전에 세팅해두는 '설정'이다.
    #    그런데 이 함수는 방송 종료뿐 아니라 '방송 시작'에서도 불린다.
    #    그래서 목표를 다 입력하고 시작 버튼을 누르는 순간 전부 지워졌고,
    #    퇴근빵 게이지는 목표 0 → 진행률 0% → 바가 안 차고 '남은 금액'도 0으로 보였다.
    #    (같은 이유로 방송 목표금액 target_goal 도 보존 대상 목록에 들어가 있다)
    return state

def create_snapshot(state, label):
    """복구 지점 저장 (append-only). 실패해도 방송은 계속되어야 하므로 예외를 삼킨다."""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                db_query("INSERT INTO snapshots (timestamp, state_json, summary) VALUES (?, ?, ?)"),
                (time.strftime('%Y-%m-%d %H:%M:%S'), json.dumps(state, ensure_ascii=False), label)
            )
        print(f"  💾 [스냅샷 저장] {label}")
        return True
    except Exception as e:
        print(f"⚠️ [스냅샷 저장 실패] {e}")
        return False

def drain_db_writes(timeout=30):
    """큐에 밀려 있는 DB 쓰기가 전부 끝날 때까지 기다린다.

    ⚠️ 복구·재정산처럼 'DB를 진실로 삼아 메모리를 다시 읽는' 작업 직전에 반드시 호출해야 한다.
       안 그러면 복구가 끝난 뒤에 워커가 '복구 전에 큐잉된 낡은 스냅샷'을 뒤늦게 써버려
       복구를 통째로 되돌린다. 게다가 LAST_PERSISTED 까지 낡은 값이 되어, 다음 저장이
       그 낡은 값과의 차이를 '수동 변경'으로 오해하고 엉뚱한 장부 줄을 남긴다.
       (task_done 기반 join() 은 쓰기가 한 번이라도 실패하면 영영 안 끝나므로 쓰지 않는다)
    """
    ev = threading.Event()
    db_write_queue.put((None, False, ev))
    if not ev.wait(timeout=timeout):
        print("⚠️ [DB 쓰기 큐 비우기 시간 초과] 낡은 저장이 뒤늦게 반영될 수 있습니다.")


_STANDBY_SAVE_WARNED = False


def save_data(new_data, is_initial=False, sync=False, wait=True):
    # 🛰️ 대기 모드에서는 절대 DB 에 쓰지 않는다. 여기서 막지 않으면 이 서버의
    #    (뒤처졌을 수 있는) 기억이 운영 서버의 후원·점수를 덮어쓴다.
    if STANDBY:
        global _STANDBY_SAVE_WARNED
        if not _STANDBY_SAVE_WARNED:
            _STANDBY_SAVE_WARNED = True
            print("🛰️ [대기 모드] 이 서버는 DB 에 쓰지 않습니다. 저장 요청을 무시합니다.", flush=True)
        return None
    return _save_data_real(new_data, is_initial=is_initial, sync=sync, wait=wait)


_LAST_REACTION_MODE = None   # 지난 저장 때의 리액션 모드 — 켜지고 꺼지는 순간을 알아챈다


def _match_follow_reaction(state):
    """⏱️ 리액션 모드가 켜지면 대결 타이머를 얼리고, 꺼지면 이어서 돌린다 — **누가 켰든** 같다.

    대표님(2026-09-30): "후원으로 리액션모드로 진입하면 타이머가 자동으로 안 멈추는데,
    손으로 직접 리액션모드 누르면 멈춰 — 이상하지?"
    ⚠️ 예전엔 멈추는 코드가 조종실 화면(enterContentMode · triggerNeon)에만 있었다. 후원 시그니처는
       서버(enqueue_signature)가 리액션 모드를 켜서 그 코드를 안 탔다 — 시그가 도는 동안 대결 시간이 흘렀다.
       서버가 리액션 모드를 켜고 끄는 곳이 여덟 군데라, 한 곳씩 고치면 또 빠진다. 저장하는 이 한 곳에서 본다.
    ⚠️ 조종실이 이미 얼려 보냈으면(was_running_before_reaction) 여기선 할 일이 없다 — 두 번 얼리지 않는다.
       이어 돌리기도 '리액션 때문에 멈춘 것'(그 표시)일 때만 한다. 손으로 멈춘 타이머는 안 건드린다.
    ⚠️ 시각은 서버 시계(ms)다. 조종실도 서버 시계(serverTimeOffset)로 맞춘 값을 보낸다.
    """
    global _LAST_REACTION_MODE
    if not isinstance(state, dict):
        return
    now_rx = bool(state.get('reaction_mode'))
    was_rx = _LAST_REACTION_MODE
    _LAST_REACTION_MODE = now_rx
    if was_rx is None or was_rx == now_rx:
        return
    md = state.get('match_data')
    if not isinstance(md, dict):
        return
    now_ms = int(time.time() * 1000)
    if now_rx and md.get('is_running'):
        left = max(0, int(md.get('end_time_ms') or 0) - now_ms)
        md['time_left_ms'] = left
        md['is_running'] = False
        md['was_running_before_reaction'] = True
        md['paused_time_left'] = left or md.get('paused_time_left') or 180000
        print(f'  ⏸️ [대결 타이머] 리액션 모드 — {left // 1000}초 남기고 멈춤', flush=True)
    elif not now_rx and md.get('was_running_before_reaction'):
        left = int(md.get('time_left_ms') or 0)
        if left <= 0:
            left = int(md.get('paused_time_left') or 180000)
        md['time_left_ms'] = left
        md['end_time_ms'] = now_ms + left
        md['is_running'] = True
        md['was_running_before_reaction'] = False
        print(f'  ▶️ [대결 타이머] 리액션 끝 — {left // 1000}초부터 이어서', flush=True)


def _save_data_real(new_data, is_initial=False, sync=False, wait=True):
    """상태 저장.

    sync=True: 후원 접수·점수 변경·방송 시작/종료처럼 잃으면 안 되는 기록은
               응답을 돌려주기 전에 DB에 직접 쓴다.
               (비동기 큐에만 넣으면 프로세스가 죽을 때 마지막 쓰기가 사라진다)
    sync=False: 슬라이더·전광판 문구 같은 잦은 UI 갱신은 기존대로 백그라운드 처리.
    """
    global MEMORY_STATE
    try:
        _match_follow_reaction(new_data)
    except Exception as _e:
        print(f'⚠️ [대결 타이머 · 리액션] 맞추기 실패 — 저장은 계속합니다: {_e}', flush=True)
    # 메모리 캐시는 즉시 최신화하여 조종실과 오버레이에 0ms로 반영
    MEMORY_STATE = new_data
    # ⚠️ 큐에 넣는 것은 스냅샷(깊은 복사)이어야 한다.
    # 같은 객체를 넘기면 워커가 순회하는 동안 요청 스레드가 계속 수정해 저장 내용이 섞인다.
    snapshot = copy.deepcopy(new_data)

    # ⚠️ 동기 저장도 반드시 같은 큐를 통과해야 한다.
    # 예전에는 sync=True가 큐를 건너뛰고 바로 썼는데, 그러면 먼저 대기 중이던
    # 오래된 비동기 스냅샷이 나중에 처리되면서 방금 저장한 최신 값(예: 후원 기록)을
    # 도로 덮어썼다. 큐를 거치면 순서가 보장되고, LAST_PERSISTED도 워커 스레드
    # 한 곳에서만 갱신되어 경합이 사라진다.
    done = threading.Event() if sync else None
    db_write_queue.put((snapshot, is_initial, done))
    if done is not None and wait:
        # 워커가 밀려 있어도 방송이 멈추지 않도록 상한을 둔다 (실패는 LAST_DB_ERROR에 남음)
        if not done.wait(timeout=30):
            print("⚠️ [동기 저장 시간 초과] 백그라운드에서 계속 진행됩니다.")
    # wait=False 로 부른 쪽은 이 이벤트를 받아 '락을 놓은 뒤' 기다릴 수 있다.
    return done


def save_data_checked(new_data, is_initial=False):
    """동기 저장을 하고, **실제로 DB 에 들어갔는지** 확인한다. 못 들어갔으면 예외를 던진다.

    ⚠️ save_data(sync=True) 는 실패해도 조용히 돌아온다(워커가 로그만 남긴다).
       방송 시작·종료처럼 DB 행을 먼저 지운 뒤 다시 쓰는 곳에서 그러면, 화면엔 '성공' 이
       뜨는데 재시작하는 순간 슬롯 한 판 값·퇴근빵 목표·세이브 슬롯이 기본값으로 돌아간다.
    ⚠️ 30초 안에 안 끝나도 실패로 본다 — '들어갔는지 모른다' 를 성공이라고 말하지 않는다.
    """
    done = save_data(new_data, is_initial=is_initial, sync=True)
    if done is None:
        return          # 🛰️ 대기 모드 — 원래 DB 에 안 쓴다
    if not done.is_set():
        raise RuntimeError('DB 저장이 30초 안에 끝나지 않았습니다')
    err = getattr(done, 'error', None)
    if err is not None:
        raise RuntimeError(f'DB 저장 실패: {err}')

def time_machine_recovery():
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(db_query("DELETE FROM players"))
            cursor.execute(db_query("""
                INSERT INTO players (name, score, contribution)
                SELECT name, current_total, current_total 
                FROM donation_history 
                WHERE id IN (
                    SELECT MAX(id) FROM donation_history GROUP BY name
                )
            """))
            
        global MEMORY_STATE
        drain_db_writes()   # 복구 직후 낡은 스냅샷이 덮어쓰지 않도록 먼저 큐를 비운다
        MEMORY_STATE = None
        load_data()
        return True
    except Exception as e:
        print(f"❌ [복구 실패] {e}")
        return False

# ==========================================
# 📡 실시간 SSE 라우트 및 제네레이터
# ==========================================
@app.route('/api/stream')
def sse_stream():
    # ⚠️ maxsize 를 반드시 준다. 무제한이면 끊기거나 멈춘 클라이언트의 큐에 update 가
    #    무한정 쌓여 서버 메모리를 계속 먹는다(부하 테스트: 60대 재접속만으로 +53MB).
    q = queue.Queue(maxsize=SSE_QUEUE_MAX)
    # ⚠️ 붙는 시점의 신분을 기억해 둔다. 나중에 broadcast 할 때 조종실에는 전부,
    #    오버레이(무인증)에는 민감 항목을 뺀 것을 보내기 위해서다.
    #    (제너레이터 안에서는 요청 컨텍스트가 없어 session 을 다시 볼 수 없다)
    q._authed = request_is_authed()
    q._evict = None
    q._drained = time.time()      # 마지막으로 이 화면이 한 줄 받아 간 때(청소부가 본다)
    # 🔌 이 연결의 소켓. 청소부가 '상대가 끊었나' 를 여기서 직접 본다.
    #    (werkzeug 개발 서버가 넣어 준다. 다른 서버로 바꾸면 없을 수 있어 없으면 그냥 넘어간다)
    q._sock = request.environ.get('werkzeug.socket')
    # 🏷️ 이 화면이 뭔지 — 조종실 시스템 칸에 '방송판 · OBS · 3시간째' 로 보인다
    _k = (request.args.get('kind') or '').strip().lower()
    q._kind = _k if _k in SSE_KINDS else 'unknown'
    q._monitor = request.args.get('monitor') == '1'
    q._dev = _sse_device(request.headers.get('User-Agent', ''), request.args.get('obs') == '1')
    q._born = time.time()
    with sse_lock:
        # 🧹 새 화면이 붙는 김에, 저쪽이 이미 끊고 간 연결을 바로 치운다.
        #    새로고침하면 옛 연결이 청소부(30초)를 기다리지 않고 이 자리에서 빠진다.
        #    ⚠️ _peer_gone 은 '확실히 끊긴 것' 만 True 다 — 살아 있는 화면은 건드리지 않는다.
        for _old in list(sse_clients):
            if _peer_gone(getattr(_old, '_sock', None)):
                _sse_drop(_old, 'closed')
        sse_clients.append(q)
        # 상한을 넘으면 덜 중요한 것부터 내보낸다 — 새 화면이 못 붙는 일이 없게(방송판은 맨 나중)
        _sse_trim_over(keep=q)

    def event_generator():
        try:
            # ⚠️ 이 첫 전송은 broadcast_event 를 거치지 않는다. 거기서 하는 정리를 여기서도 해야 한다.
            #    오버레이·조종실이 붙을 때 받는 바로 그 데이터라, 빠뜨리면 가장 크게 샌다.
            initial_state = state_for_client(load_data(), q._authed)
            yield f"event: init\ndata: {json.dumps(initial_state, ensure_ascii=False)}\n\n"

            if os.path.exists(LAYOUT_FILE):
                try:
                    with open(LAYOUT_FILE, 'r', encoding='utf-8') as f:
                        layout_data = json.load(f)
                    yield f"event: layout\ndata: {json.dumps(layout_data, ensure_ascii=False)}\n\n"
                except Exception:
                    pass

            while True:
                try:
                    msg = q.get(timeout=15.0)
                except queue.Empty:
                    msg = "event: ping\ndata: {}\n\n"   # 무음 15초마다 연결 유지 신호
                if msg is None or q._evict:      # 청소부가 '이제 그만' 이라고 했다
                    break
                yield msg
                # ⚠️ yield 가 돌아왔다 = 저쪽이 실제로 받아 갔다. 이 시각이 '살아 있음' 의 증거다.
                #    소켓이 막히면 여기서 멈춰 있다가 시간제한에 걸려 예외가 나고 finally 로 간다.
                q._drained = time.time()
        finally:
            # ⚠️ 반드시 finally 여야 한다.
            #    예전에는 while 을 정상적으로 빠져나올 때만 정리했는데, ping 은 `except queue.Empty:`
            #    블록 '안에서' yield 하고 있어서 하필 그 순간 클라이언트가 끊기면
            #    GeneratorExit 가 except 를 지나쳐 밖으로 튀고 정리가 통째로 건너뛰어졌다.
            #    그러면 죽은 큐가 sse_clients 에 남아 이후 모든 broadcast 를 계속 받아 쌓았다.
            with sse_lock:
                if q in sse_clients:
                    sse_clients.remove(q)
            if q._evict:
                print(f'🧹 [실시간 연결] 죽은 것 하나 치웠습니다 ({q._evict}) — 남은 {len(sse_clients)}개',
                      flush=True)
                
    response = app.response_class(event_generator(), mimetype='text/event-stream')
    response.headers['X-Accel-Buffering'] = 'no'
    response.headers['Cache-Control'] = 'no-cache'
    response.headers['Connection'] = 'keep-alive'
    return response

@app.route('/api/ping')
def api_ping():
    return jsonify({'status': 'pong'})


def _rss_mb():
    """이 프로세스가 쓰는 메모리(MB). 리눅스 밖에서는 None."""
    try:
        with open('/proc/self/status', 'r') as f:
            for ln in f:
                if ln.startswith('VmRSS:'):
                    return round(int(ln.split()[1]) / 1024, 1)
    except Exception:
        pass
    return None


# 🩺 서버가 살아있고 제대로 일하는지 한눈에 — 폰으로 여는 /health 페이지가 쓴다.
#
# ⚠️ 무인증으로 열어둔다. 로그인해야 볼 수 있으면 폰에서 '괜찮나?' 확인하는
#    용도로 못 쓰기 때문이다. 대신 후원자 이름·금액·메시지·토큰처럼 남이 보면
#    안 되는 것은 절대 담지 않는다. 담는 것은 '몇 건'까지다.
#    보안 상태(약한 키 등)는 남에게 공격 힌트가 되므로 로그인했을 때만 덧붙인다.
@app.route('/api/health')
def api_health():
    out = {
        'status': 'ok',
        # server.py 는 datetime 을 import 하지 않는다. 이미 있는 time 으로 만든다.
        'server_time': time.strftime('%Y-%m-%d %H:%M:%S'),
        'uptime_sec': int(time.time() - SERVER_BOOT_TS),
        'rss_mb': _rss_mb(),
    }

    # 저장소는 '설정돼 있다'가 아니라 '지금 실제로 응답하는가'를 본다.
    # 붙은 줄 알았는데 끊겨 있는 상황이 제일 위험하다.
    t0 = time.perf_counter()
    try:
        with get_db_connection() as conn:
            conn.cursor().execute('SELECT 1')
        out['storage'] = {
            'kind': 'postgres' if IS_POSTGRES else 'sqlite',
            'persistent': IS_POSTGRES,
            'ok': True,
            'latency_ms': round((time.perf_counter() - t0) * 1000, 1),
        }
    except Exception as e:
        out['status'] = 'degraded'
        out['storage'] = {
            'kind': 'postgres' if IS_POSTGRES else 'sqlite',
            'persistent': IS_POSTGRES,
            'ok': False,
            'error': type(e).__name__,
        }

    try:
        state = load_data()
        out['counts'] = {
            'players': len(state.get('bjs') or []),
            'pending': len(state.get('pending_donations') or []),
            'reaction_queue': len(state.get('reaction_queue') or []),
            'logs': len(state.get('logs') or []),
        }
        out['modes'] = {
            'reaction': bool(state.get('reaction_mode')),
            'match': bool((state.get('match_data') or {}).get('active')),
            'karaoke': bool(state.get('karaoke_enabled')),
            'home_race': bool(state.get('home_race_enabled')),
        }
        # 마지막 후원이 '언제'인지만. 누가 얼마인지는 담지 않는다.
        # ⚠️ 이 값은 server.py:2365 에서 time.time() 으로 넣는 '초'다(밀리초 아님).
        #    1000 으로 나눴다가 '56년 전'이 찍힌 적이 있다.
        lt = ((state.get('latest_donation') or {}).get('time')) or 0
        age = int(time.time() - lt) if lt else None
        # 시계가 틀어졌거나 값이 이상하면 숫자를 지어내지 말고 모른다고 한다.
        out['last_donation_age_sec'] = age if (age is not None and 0 <= age < 60 * 60 * 24 * 365) else None
    except Exception as e:
        out['status'] = 'degraded'
        out['counts_error'] = type(e).__name__

    out['standby'] = STANDBY   # 🛰️ 대기 모드면 이 서버는 DB 를 건드리지 않는다
    with sse_lock:
        out['sse_clients'] = len(sse_clients)
        out['sse_evicted'] = _sse_evicted      # 지금까지 치운 죽은 연결 수

    # 여기부터는 로그인한 사람에게만. 남이 보면 공격 힌트가 되는 것들이다.
    if session.get('authenticated'):
        out['private'] = {
            'weak_admin_secret': SECRET_IS_WEAK,
            'self_ping_enabled': bool(load_data().get('self_ping_enabled')),
            'self_ping_blocked': (os.environ.get('SELF_PING') or '').strip().lower() in ('0', 'off', 'false', 'no'),
            'bind_host': (os.environ.get('BIND_HOST') or '0.0.0.0').strip(),
            'ai_key_present': bool((os.environ.get('NVIDIA_API_KEY') or '').strip()),
            'default_admin_password': load_auth_config()['admin_password'] == '0508',
        }

    return jsonify(out)


# ==========================================
# 🗓️ 월별 후원 순위 — 수요일 방송 시간만
# ==========================================
# 방송은 수요일 17:00 에 시작해 목요일 03:00 에 끝난다. 그 창 안에 들어온 후원만
# 센다. 다른 날 들어온 것(계좌 이체 등)은 순위에 안 넣는다.
BC_START_H = 17      # 수요일 17:00 시작 (정각은 창 안)
BC_END_H = 3         # 목요일 03:00 끝  (정각은 창 밖 — 끝난 시각이다)


def _bc_shift_hours():
    """DB 에 적힌 시각을 KST 로 옮기는 데 필요한 시간.

    ⚠️ 후원 시각은 time.strftime 으로 **서버 지역시** 로 적힌다. 배포 설정에
       시간대 지정이 없어 우분투 기본대로면 UTC 이고, 그러면 KST 수요일 17시가
       DB 에는 08시로 적혀 있다. 그대로 걸러내면 한 건도 안 잡힌다.
       서버가 이미 KST 면 0, UTC 면 9 를 준다. 환경변수로 바꿀 수 있게 둔다.
    """
    try:
        return int(os.environ.get('BROADCAST_TZ_SHIFT', '0'))
    except (TypeError, ValueError):
        return 0


def now_hms():
    """로그·대기함에 적을 '지금 시각'. 한국 시각으로 적는다.

    ⚠️ time.strftime 은 **서버 지역시**를 준다. 운영 서버는 UTC 라 9시간 뒤처진
       시각이 찍혔다 — 밤 1시에 준 점수가 로그창에 16:07 로 떠서, 언제 준
       것인지 알 수 없었다(사장님: "시간이 안 맞아").
    ⚠️ DB 의 timestamp 는 여기서 손대지 않는다. 그쪽은 서버 지역시로 적힌 것을
       전제로 _bc_window 가 읽을 때 옮긴다 — 여기서도 옮기면 두 번 밀린다.
    """
    return time.strftime('%H:%M:%S', time.localtime(time.time() + _bc_shift_hours() * 3600))


def ts_kst(ts_text):
    """DB 에 적힌 시각을 사람에게 보여줄 한국 시각으로 옮긴다.

    ⚠️ 장부의 timestamp 는 서버 지역시(운영 서버는 UTC)로 적혀 있다. 지난 방송
       후원내역·엑셀에 그대로 내보내면 9시간 뒤처진 시각이 나온다.
    ⚠️ 옮기는 것은 **보여줄 때뿐**이다. DB 에 쓸 때 옮기면 _bc_window 가 한 번 더
       옮겨 월별 순위가 통째로 어긋난다.
    """
    shift = _bc_shift_hours()
    if not ts_text or not shift:
        return ts_text
    try:
        t = datetime.datetime.strptime(str(ts_text)[:19], '%Y-%m-%d %H:%M:%S')
    except (TypeError, ValueError):
        return ts_text            # 모양이 다르면 건드리지 않는다
    return (t + datetime.timedelta(hours=shift)).strftime('%Y-%m-%d %H:%M:%S')


def _bc_window(ts_text, shift):
    """이 후원이 수요일 방송 창 안인가. 창 안이면 그 방송이 시작한 날짜를 돌려준다.

    돌려주는 날짜는 **수요일** 이다 — 목요일 새벽 2시에 들어온 후원도 그 방송이
    시작한 수요일에 붙는다. 안 그러면 월말에 걸친 한 방송이 두 달로 쪼개진다.
    """
    if not ts_text:
        return None
    try:
        t = datetime.datetime.strptime(str(ts_text)[:19], '%Y-%m-%d %H:%M:%S')
    except (TypeError, ValueError):
        return None
    t = t + datetime.timedelta(hours=shift)
    wd = t.weekday()          # 월0 화1 수2 목3
    if wd == 2 and t.hour >= BC_START_H:
        return t.date()                                  # 수요일 저녁
    if wd == 3 and t.hour < BC_END_H:
        return (t - datetime.timedelta(days=1)).date()   # 목요일 새벽 → 어제(수)
    return None

# ==========================================
# 🏦 은행 원장 (플레이어별 통장 내역 / 잔액 재정산)
# ==========================================
@app.route('/api/bank/statement/<path:player_name>', methods=['GET'])
def get_bank_statement(player_name):
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                db_query("""SELECT timestamp, tx_type, score_change, score_balance,
                                   contrib_change, contrib_balance, description
                            FROM bank_ledger WHERE player_name = ? ORDER BY id DESC LIMIT 50"""),
                (player_name,)
            )
            statement = [{
                "timestamp": r[0], "tx_type": r[1],
                "score_change": r[2], "score_balance": r[3],
                "contrib_change": r[4], "contrib_balance": r[5],
                "description": r[6]
            } for r in cursor.fetchall()]

            cursor.execute(db_query("SELECT score, contribution FROM players WHERE name = ?"), (player_name,))
            row = cursor.fetchone()

        return jsonify({
            "status": "success",
            "player_name": player_name,
            "current_score_balance": row[0] if row else 0,
            "current_contrib_balance": row[1] if row else 0,
            "statement_history": statement
        })
    except Exception as e:
        print(f"[통장 내역 조회 오류] {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

def _ledger_mark_broadcast(cursor, label):
    """원장에 '여기서 방송이 바뀌었다' 는 경계 줄을 하나 넣는다(점수 변동 0 · 이름 빈칸).

    ⚠️ 방송 시작·종료의 DELETE 와 **같은 트랜잭션** 안에서 부른다. 따로 넣으면
       지우기는 됐는데 경계가 없거나, 경계만 있고 지우기는 안 된 원장이 생길 수 있다.
    """
    cursor.execute(db_query("""INSERT INTO bank_ledger
                                   (timestamp, player_name, tx_type, score_change, score_balance,
                                    contrib_change, contrib_balance, description)
                               VALUES (?, '', 'BROADCAST_RESET', 0, 0, 0, 0, ?)"""),
                   (time.strftime('%Y-%m-%d %H:%M:%S'), label))


def _ledger_session_start_id(cursor):
    """이번 방송 원장이 시작되는 자리(그 번호 **뒤** 줄부터 이번 방송) — 재정산이 쓴다.

    경계 줄이 있으면 그 번호. 없으면(이 수정 전에 시작한 방송) broadcast_started_at 시각보다
    먼저 적힌 마지막 줄 번호. 그것도 없으면 0(원장 전체 — 옛 동작).
    ⚠️ 시각 비교는 보조 수단이다. 원장 시각은 서버 지역시 · 초 단위라 경계 줄이 더 정확하다.
    """
    cursor.execute(db_query("SELECT MAX(id) FROM bank_ledger WHERE tx_type = 'BROADCAST_RESET'"))
    row = cursor.fetchone()
    if row and row[0]:
        return int(row[0])
    started_ms = int((MEMORY_STATE or {}).get('broadcast_started_at') or 0)
    if started_ms:
        ts = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(started_ms / 1000))
        cursor.execute(db_query("SELECT MAX(id) FROM bank_ledger WHERE timestamp < ?"), (ts,))
        row = cursor.fetchone()
        return int(row[0]) if row and row[0] else 0
    return 0


@app.route('/api/bank/recalculate', methods=['POST'])
def recalculate_bank_balances():
    """원장에 쌓인 변동분을 **이번 방송 시작부터** 다시 합산해 현재 잔액을 재구성한다.
       점수가 어긋났다고 의심될 때 쓰는 복구 수단.

    ⚠️ 예전에는 원장 전체(지난 방송 전부)를 합산했다. 원장은 방송이 끝나도 안 지우므로,
       누르는 순간 이번 주 점수에 지난주·지지난주 점수가 통째로 더해졌다. 게다가 명단에
       없는 이름까지 INSERT 해서, 몇 주 전에 나간 사람이 점수판에 되살아났다.
       → 마지막 방송 경계(BROADCAST_RESET 줄) 뒤의 줄만 더하고, 지금 명단에 있는 사람만 고친다.
    ⚠️ 이번 방송에 원장 줄이 하나도 없는 사람은 건드리지 않는다. 백업 복구(/api/restore)처럼
       원장을 안 거치고 점수가 들어온 경우가 있어, 0 으로 만들면 멀쩡한 점수를 지운다.
    """
    try:
        global MEMORY_STATE, LAST_PERSISTED
        with file_lock:
            # ⚠️ 먼저 큐를 비운다. 재정산 직전에 눌린 점수 버튼의 저장이 아직 큐에 있으면,
            #    그 변동이 원장에 안 들어간 채로 합산하게 되고, 뒤늦게 쓰인 낡은 스냅샷이
            #    방금 맞춘 점수를 도로 되돌린다.
            drain_db_writes()
            roster = [str(p.get('name') or '').strip() for p in (load_data().get('bjs') or [])
                      if isinstance(p, dict) and str(p.get('name') or '').strip()]
            with get_db_connection() as conn:
                cursor = conn.cursor()
                since_id = _ledger_session_start_id(cursor)
                cursor.execute(db_query("""
                    SELECT player_name, SUM(score_change), SUM(contrib_change)
                    FROM bank_ledger WHERE id > ? AND tx_type <> 'BROADCAST_RESET'
                    GROUP BY player_name
                """), (since_id,))
                totals = {r[0]: (r[1] or 0, r[2] or 0) for r in cursor.fetchall()}

                # ⚠️ UPDATE 만 한다(INSERT 없음) — 명단에 없는 이름을 되살리지 않는다
                fixed = []
                for name in roster:
                    if name not in totals:
                        continue
                    score_sum, contrib_sum = totals[name]
                    cursor.execute(db_query("UPDATE players SET score = ?, contribution = ? WHERE name = ?"),
                                   (score_sum, contrib_sum, name))
                    fixed.append(name)

            # DB에서 다시 읽어 메모리 상태를 맞춘다.
            MEMORY_STATE = None
            LAST_PERSISTED = None
            state = load_data()
            broadcast_event('update', state)

        skipped = len(roster) - len(fixed)
        print(f"  🏦 [원장 재정산] {len(fixed)}명 잔액 복구 (원장 {since_id}번 뒤부터"
              f"{f' · 이번 방송 기록 없는 {skipped}명은 그대로' if skipped else ''})")
        return jsonify({"status": "success",
                        "message": f"{len(fixed)}명의 잔액을 이번 방송 원장 기준으로 재정산했습니다."
                                   + (f" (이번 방송 기록이 없는 {skipped}명은 그대로 두었습니다)" if skipped else ""),
                        "updated": len(fixed)})
    except Exception as e:
        print(f"[원장 재정산 오류] {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

def _keep_match_scores(inc_md, cur_md):
    """⚔️ 밖에서 온 match_data 의 대결 점수를 서버 값으로 되돌린다(그 자리에서 고친다).

    ⚠️ 대결 점수는 /api/score/add 로만 오른다(직접 넣기 · 팀전·개인전 연동).
       그런데 조종실 pushAPI(/api/data)와 폰 타이머 버튼(/api/settings/patch)은
       match_data 를 **통째로** 보낸다. 거기 실린 점수는 브라우저가 들고 있던 낡은 사본이라,
       타이머를 한 번 누르거나 팀원을 한 명 고르는 사이 들어온 후원 점수가 도로 사라졌다.
       명단(bjs)을 지키는 것과 똑같은 방식으로, 이름이 같은 대결자는 서버 점수를 지킨다.
    ⚠️ 점수 말고는 전부 받는다 — 대결자 추가·삭제·이름·팀원·타이머·켜고 끄기·연동 방식.
    ⚠️ 새 이름은 보낸 값을 그대로 쓴다(조종실은 새 대결자를 0 으로 만든다 — bjs 와 같은 규칙).
       단, 한 명만 이름을 바꾼 것(자리·인원 그대로)은 개명으로 보고 옛 점수를 물려준다.
    ⚠️ 새 대결을 0 점에서 시작하려면 대결자를 지우고 다시 넣는다(방송 시작·종료도 비운다).
    """
    if not isinstance(inc_md, dict) or not isinstance(inc_md.get('players'), list):
        return
    cur = [p for p in ((cur_md or {}).get('players') or []) if isinstance(p, dict)] \
        if isinstance(cur_md, dict) else []
    # ⚠️ 같은 이름이 둘일 수 있다([대결자 추가]를 두 번 누르면 둘 다 'Player').
    #    이름마다 서버 줄을 **차례로 한 번씩만** 짝짓는다 — 예전 첫 판은 두 번째 'Player' 에게도
    #    첫 번째의 점수를 복사해 줘서 가짜 점수가 생겼다(최종 검증에서 잡았다).
    have = {}
    for p in cur:
        have.setdefault(str(p.get('name') or '').strip(), []).append(p)
    rows = [p for p in inc_md['players'] if isinstance(p, dict)]
    used, newbies = set(), []
    for i, p in enumerate(rows):
        nm = str(p.get('name') or '').strip()
        cands = have.get(nm) or []
        old = cands.pop(0) if cands else None
        if old is None:
            newbies.append((i, p))
            continue
        used.add(id(old))
        p['score'] = old.get('score', 0)
    gone = [p for p in cur if id(p) not in used]
    if len(newbies) == 1 and len(gone) == 1 and len(rows) == len(cur):
        i, p = newbies[0]
        if i < len(cur) and cur[i] is gone[0]:          # 자리까지 같을 때만
            p['score'] = gone[0].get('score', 0)


@app.route('/api/data', methods=['GET', 'POST'])
def api_data():
    if request.method == 'POST':
        with file_lock:
            incoming = request.get_json(silent=True) or {}
            current_state = load_data()

            # 🛡️ [동시성 수정] 예전에는 클라이언트가 보낸 전체 상태로 서버를 통째로 덮어썼다(Last-Write-Wins).
            #   그러면 후원이 막 들어와 서버가 큐에 시그니처를 넣은 순간, (후원 직전 상태를 들고 있던)
            #   조종실이 점수 버튼을 누르면 그 스테일 상태가 서버를 덮어써서 방금 들어온 시그니처가
            #   큐에서 사라졌다("시그니처가 씹힌다"). 그래서 '서버만 건드리는 필드'는 클라이언트가
            #   덮어쓰지 못하게 서버 값을 유지한다. (이 필드들은 후원 수신·큐 조작 엔드포인트에서만 바뀐다.
            #   조종실/모바일/에디터의 어떤 조작도 /api/data 로 이 필드를 직접 수정하지 않으므로 안전하다.)
            #   집계 두 개도 같은 이유로 지킨다. 후원이 들어올 때 서버가 적는 값인데,
            #   조종실이 스위치 하나를 누르면 상태 전체를 보내므로 그 사이 들어온 후원이
            #   낡은 사본에 덮여 순위에서 사라진다. (편집기의 '집계 지우기'는 설정 패치라
            #   이 경로를 안 타고 그대로 동작한다)
            #   🏺 모금함도 같이 지킨다. 금액은 /api/score/add 로만 들어오고 설정은
            #      /api/fundjar 로만 바꾼다 — 조종실이 상태를 통째로 보낼 때 낡은 금액이 덮어쓰면
            #      상금이 어긋난다(운영비 점수를 지키는 것과 똑같은 이유다).
            SERVER_OWNED = ('reaction_queue', 'latest_donation', 'pending_donations',
                            'reaction_paused', 'siggame', 'dicegame', 'sig_tally', 'donor_tally',
                            'fundjar', 'announce_bot', 'pinball', 'quiz', 'best_single', 'stage_screen', 'hell',
                            'broadcast_started_at', 'layout_presets', 'layout_rev', 'clip',
                            # 📺 방송 화면 — 무대·고정 자리·알림은 /api/show 로만. 옛 스위치는 show 가 계산한다
                            'show') + showmod.LEGACY_OWNED

            # 🔐 [보안] 응답 전용 필드는 절대 상태로 들어오면 안 된다.
            #   GET /api/data 는 로그인 세션이 있으면 응답에 api_token(= 관리자 비밀키)을 얹어준다.
            #   그런데 에디터는 받은 응답 객체를 통째로 globalData 에 넣고(admin.html) 그대로 다시 POST 한다.
            #   여기서 걸러내지 않으면 그 키가 state 에 눌러앉아 DB 에 평문으로 저장되고,
            #   무인증으로 열려 있는 /api/stream 을 통해 모든 오버레이·알림창에 방송된다.
            #   그 값은 보호된 API 를 전부 통과하는 Bearer 토큰이자 세션 서명키다.
            # 🎬 stage_live 도 응답에만 싣는 칸이다 — 받은 걸 그대로 되돌려 보내도 상태에 눌러앉지 않게
            for _k in ('api_token', 'server_time', 'stage_live'):
                incoming.pop(_k, None)

            # 🛡️ [점수 지키기] 명단(bjs·extra_bjs·bottom_fixed)이 통째로 들어오면,
            #    이름이 그대로인 사람의 점수·기여도는 '서버 값'을 지킨다.
            #
            # ⚠️ 이 길로 명단을 보내는 조작은 플레이어 추가·삭제·이름변경뿐이고,
            #    그 어느 것도 점수를 바꿀 뜻이 없다. 그런데 보내는 내용에는 브라우저가
            #    들고 있던 '그 순간의 점수'가 같이 실린다. 그래서 이름 한 글자를 고치는
            #    사이에 폰이나 오토파일럿이 준 점수가 통째로 되돌아갔다
            #    (부하 테스트: 동시에 배정 25건 중 17건 소실 = 68%).
            #    점수를 실제로 바꾸는 길은 /api/score/add 하나뿐이고, 그쪽은 '더할 값'만
            #    받아 서버가 읽고-더하고-쓰므로 겹쳐도 둘 다 남는다.
            #    새 이름(추가·개명)은 서버에 없으니 클라이언트 값을 그대로 쓴다.
            for _key in ('bjs', 'extra_bjs'):
                _inc = incoming.get(_key)
                if not isinstance(_inc, list):
                    continue
                _cur = [p for p in (current_state.get(_key) or []) if isinstance(p, dict)]
                _have = {str(p.get('name') or '').strip(): p for p in _cur
                         if isinstance(p.get('name'), str)}
                _rows = [p for p in _inc if isinstance(p, dict)]
                _matched, _newbies = set(), []
                for _i, _p in enumerate(_rows):
                    _nm = str(_p.get('name') or '').strip()
                    _old = _have.get(_nm)
                    if _old is None:
                        _newbies.append((_i, _p))    # 새 이름 — 아래에서 개명인지 본다
                        continue
                    _matched.add(_nm)
                    _p['score'] = _old.get('score', 0)
                    _p['contribution'] = _old.get('contribution', 0)
                # ⚠️ 개명 처리. 이름으로만 찾으면 이름을 바꾼 그 사람의 점수가
                #    브라우저가 들고 있던 (조금 낡은) 값으로 저장돼 몇 점 어긋난다.
                #    명단 조작은 점수를 바꿀 뜻이 없으므로, '사라진 이름'과 '새 이름'의
                #    수가 같고 자리도 그대로면 개명으로 보고 옛 점수를 물려준다.
                #    (한 번에 여럿을 고치거나 추가·삭제가 섞이면 확신할 수 없으니 손대지 않는다)
                _gone = [p for p in _cur if str(p.get('name') or '').strip() not in _matched]
                if len(_newbies) == 1 and len(_gone) == 1 and len(_rows) == len(_cur):
                    _i, _p = _newbies[0]
                    if _i < len(_cur) and _cur[_i] is _gone[0]:      # 자리까지 같을 때만
                        _p['score'] = _gone[0].get('score', 0)
                        _p['contribution'] = _gone[0].get('contribution', 0)
                        print(f"  ✏️ [이름 변경] {_gone[0].get('name')} → {_p.get('name')}"
                              f" (점수 {_p['score']} 그대로)", flush=True)
            # 운영비 칸도 같은 이유로 점수를 지킨다(이름만 고치는 길이 열려 있다).
            _bf, _bf_old = incoming.get('bottom_fixed'), current_state.get('bottom_fixed')
            if isinstance(_bf, dict) and isinstance(_bf_old, dict):
                _bf['score'] = _bf_old.get('score', 0)
            # ⚔️ 대결 점수도 같은 이유로 지킨다(_keep_match_scores 설명 참고)
            _keep_match_scores(incoming.get('match_data'), current_state.get('match_data'))

            state = dict(current_state)
            state.update(incoming)                      # 클라이언트 편집 필드는 그대로 반영(설정·승인 등 기존 동작 유지)
            state.pop('api_token', None)                # 과거에 이미 오염됐다면 여기서 씻어낸다
            for k in SERVER_OWNED:
                if k in current_state:
                    state[k] = current_state[k]          # 서버 소유 필드는 서버의 최신 값을 유지
            # 📺 옛 방식으로 온 것만 무대에 옮긴다 — 룰렛 돌리기(roulette.command=spin) · 대결 켜기/끄기.
            #    그리고 옛 스위치를 show 에서 다시 계산해 적는다(낡은 조종실이 보낸 값이 남지 않게).
            #    ⚠️ 반드시 SERVER_OWNED 복원 **뒤**에 한다(복원이 show 를 서버 값으로 되돌려 놓은 다음).
            # ⚠️ 서버에 아직 show 가 없으면(개편 전 저장본) 밖에서 온 show 를 믿지 않는다 — 옛 스위치에서 옮겨 담는다
            if 'show' not in current_state:
                state.pop('show', None)
            _prev_stage = showmod.ensure(state)['stage']
            showmod.ingest_roulette(state, current_state.get('roulette'))
            showmod.ingest_match(state, bool((current_state.get('match_data') or {}).get('active')))
            showmod.project(state)
            _stage_log(_prev_stage, state['show']['stage'])
            # ⚠️ 이름 앞뒤 공백을 저장 단계에서 떼어낸다.
            #    이름 칸에 공백을 하나만 더 눌러도 그 사람이 점수를 못 받는 사고가 있었다.
            #    찾을 때도 공백을 무시하도록 고쳤지만(_find_score_target), 저장되는 값 자체가
            #    깨끗해야 장부와 순위에 '밍밍' 과 '밍밍 ' 이 따로 쌓이는 일이 없다.
            for _k in ('bjs', 'extra_bjs'):
                for _p in (state.get(_k) or []):
                    if isinstance(_p, dict) and isinstance(_p.get('name'), str):
                        _p['name'] = _p['name'].strip()
            # 🎲 명단이 바뀌었으면 주사위 말도 그 자리에서 맞춘다. 안 그러면 새로 넣은
            #    사람이 다음 굴림 전까지 판에도 폰 목록에도 없다(dicegame 은 서버 소유라
            #    여기서 손봐도 조종실 사본에 덮이지 않는다).
            if ('bjs' in incoming or 'extra_bjs' in incoming) and isinstance(state.get('dicegame'), dict):
                try:
                    _dicegame_state(state)
                except Exception as _e:
                    print(f'⚠️ [주사위게임] 명단 변경 뒤 말 맞추기 실패 — 계속합니다: {_e}', flush=True)
            _md = state.get('match_data')
            if isinstance(_md, dict):
                for _p in (_md.get('players') or []):
                    if not isinstance(_p, dict):
                        continue
                    if isinstance(_p.get('name'), str):
                        _p['name'] = _p['name'].strip()
                    # ⚔️ 팀원 이름도 같은 이유로 다듬는다. 여기 공백이 하나 남으면
                    #    그 사람 후원이 팀 점수에 조용히 안 붙는다.
                    if isinstance(_p.get('members'), list):
                        _seen = []
                        for _m in _p['members']:
                            _m = str(_m or '').strip()
                            if _m and _m not in _seen:
                                _seen.append(_m)
                        # 🧍 개인전은 대결자마다 한 명이다 — 둘이 붙어 있으면 한 사람 후원이 두 번 셀 수 있다
                        if _md.get('link') == 'solo':
                            _seen = _seen[:1]
                        _p['members'] = _seen
            _bf = state.get('bottom_fixed')
            if isinstance(_bf, dict) and isinstance(_bf.get('name'), str):
                _bf['name'] = _bf['name'].strip()

            # 큐에 항목이 남아 있으면 리액션 모드는 항상 켜져 있어야 한다(스테일 클라이언트가 끄는 사고 방지)
            if state.get('reaction_queue'):
                state['reaction_mode'] = True

            # 🧹 로그 상한을 서버에서 지킨다.
            #   조종실은 삽입 지점마다 200건으로 잘랐지만 mobile.html 은 안 잘랐고, 서버도 룰렛 경로에서만
            #   잘랐다. 그래서 폰으로만 배정하면 상한이 없었다(소크에서 432건까지 쌓이는 걸 확인).
            #   state 전체가 매 update 마다 모든 클라이언트로 나가므로 여기서 한 번에 막는 게 맞다.
            for _lk in ('logs', 'match_logs'):
                if isinstance(state.get(_lk), list) and len(state[_lk]) > LOG_MAX:
                    del state[_lk][LOG_MAX:]

            # [버전] 409 경고 대신 마지막 전송 기준으로 버전만 올린다.
            state['version'] = max(incoming.get('version', 0), current_state.get('version', 1)) + 1

            # ⚠️ 여기서 동기 저장을 하면 안 된다.
            # 점수 버튼은 방송 중 연타하는 조작인데, Render(오레곤)→Supabase(서울) 왕복 때문에
            # 클릭 한 번에 2초 넘게 걸려 점수 반영이 눈에 띄게 밀렸다.
            # 저장은 백그라운드 큐에 맡기고(수 ms 내 반영), 화면에는 즉시 브로드캐스트한다.
            # 잃으면 안 되는 기록은 방송 시작/종료·리셋·복구 쪽에서 동기로 처리한다.
            save_data(state)
            broadcast_event('update', state)
        return jsonify({"status": "success"})
        
    state = load_data()
    if isinstance(state, dict):
        # ⚠️ 다른 곳은 전부 request_is_authed() 를 쓰는데 여기만 session 을 봤다.
        #    그래서 관리자 키(Bearer)로 부르는 쪽은 대기 후원·장부가 빠진 상태를 받았고,
        #    "보냈는데 안 들어갔다"로 보였다(실제로는 저장돼 있었다).
        state = state_for_client(state, request_is_authed())
        # 조종실 웹에 로그인 세션이 있을 때만 보안 API 토큰을 붙인다.
        # (state_for_client 가 방금 지운 것을, 여기서만 의도적으로 다시 넣는다)
        if session.get('authenticated'):
            state['api_token'] = load_auth_config()['session_secret']
    return jsonify(state)


@app.route('/api/restore', methods=['POST'])
def api_restore():
    """백업에서 상태를 통째로 되돌린다 (브라우저 자동 백업 · 내려받은 백업 파일).

    ⚠️ 예전에는 조종실이 백업을 /api/data 로 밀어넣었다. 그런데 그 경로는
       pending_donations · reaction_queue · siggame 를 서버 소유로 보호해서 받은 값을 버린다.
       그래서 점수와 설정은 돌아오는데 '아직 배정 안 한 후원' 은 조용히 사라졌다.
       화면에는 '복구 완료' 라고 떴으니 운영자는 돈이 사라진 걸 알 방법이 없었다.
       복구는 그 필드까지 되돌려야 뜻이 있으므로 전용 경로로 분리한다.

    ⚠️ 평소 조작은 절대 이 경로를 쓰면 안 된다. 상태를 통째로 갈아끼우므로,
       그 사이 들어온 후원이 있으면 같이 지워진다. 그래서 되돌리기 전에 스냅샷을 남긴다.
    """
    try:
        body = request.get_json(silent=True) or {}
        if not isinstance(body, dict) or 'bjs' not in body:
            return jsonify({"status": "error",
                            "message": "복구할 상태가 아닙니다(백업 파일이 맞는지 확인해주세요)"}), 400
        with file_lock:
            before = load_data()
            create_snapshot(before, '복구 직전 자동 백업')
            # 모르는 키는 받지 않는다 — 백업 파일에 뭐가 들어 있든 상태를 오염시키지 않게.
            state = copy.deepcopy(DEFAULT_STATE)
            for k in DEFAULT_STATE:
                if k in body:
                    state[k] = body[k]
            state.pop('api_token', None)
            state['version'] = (before.get('version') or 1) + 1
            # is_initial=True 로 전체 키를 다시 쓴다(변경분만 쓰면 복구가 절반만 반영된다)
            save_data(state, is_initial=True, sync=True)
            broadcast_event('update', state)
        players = len(state.get('bjs') or [])
        pending = len(state.get('pending_donations') or [])
        print(f"  ♻️ [상태 복구] 플레이어 {players}명 · 대기함 {pending}건 · 큐 "
              f"{len(state.get('reaction_queue') or [])}건")
        return jsonify({"status": "success", "players": players, "pending": pending})
    except Exception as e:
        print(f"[상태 복구 오류] {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

# ==========================================
# 💾 타임머신 스냅샷 API
# ==========================================
@app.route('/api/snapshots', methods=['GET'])
def get_snapshots():
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(db_query("SELECT id, timestamp, summary FROM snapshots ORDER BY id DESC"))
            rows = cursor.fetchall()
            snapshots = [{"id": r[0], "timestamp": r[1], "summary": r[2]} for r in rows]
        return jsonify({"status": "success", "snapshots": snapshots})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/snapshots/manual', methods=['POST'])
def create_manual_snapshot():
    try:
        req_data = request.get_json(silent=True) or {}
        label = req_data.get("label", "수동 백업")
        state = load_data()
        timestamp = time.strftime('%Y-%m-%d %H:%M:%S')
        
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                db_query("INSERT INTO snapshots (timestamp, state_json, summary) VALUES (?, ?, ?)"),
                (timestamp, json.dumps(state, ensure_ascii=False), label)
            )
        return jsonify({"status": "success"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/snapshots/restore', methods=['POST'])
def restore_snapshot():
    try:
        req_data = request.get_json(silent=True) or {}
        # 목록·사전이 그대로 DB 로 내려가면 '파라미터를 못 묶는다'는 내부 오류가 샌다
        snap_id = _as_int(req_data.get("id"))
        if snap_id is None:
            return jsonify({"status": "error", "message": "스냅샷 번호가 필요합니다"}), 400

        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(db_query("SELECT state_json FROM snapshots WHERE id = ?"), (snap_id,))
            row = cursor.fetchone()
            if not row:
                return jsonify({"status": "error", "message": "스냅샷을 찾을 수 없습니다."}), 404
            state_json = row[0]
            
        with file_lock:
            # ⚠️ 기본 상태 위에 스냅샷을 얹는다(/api/restore 와 같은 방식).
            #    옛 스냅샷에는 그 뒤에 생긴 칸(show · hell · clip …)이 없다. 그대로 갈아끼우면
            #    그 칸을 읽는 곳마다 KeyError 로 죽었다. 모르는 칸은 받지 않는다.
            snap = json.loads(state_json)
            if not isinstance(snap, dict):
                return jsonify({"status": "error", "message": "스냅샷 내용이 올바르지 않습니다."}), 400
            state = copy.deepcopy(DEFAULT_STATE)
            for k in DEFAULT_STATE:
                if k in snap:
                    state[k] = snap[k]
            state.pop('api_token', None)
            save_data(state, sync=True)
            broadcast_event('update', state)
            
        return jsonify({"status": "success"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/snapshots/delete', methods=['POST'])
def delete_snapshot():
    try:
        req_data = request.get_json(silent=True) or {}
        snap_id = _as_int(req_data.get("id"))
        if snap_id is None:
            return jsonify({"status": "error", "message": "스냅샷 번호가 필요합니다"}), 400

        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(db_query("DELETE FROM snapshots WHERE id = ?"), (snap_id,))
        return jsonify({"status": "success"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/server/status', methods=['GET'])
def get_server_status():
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            # Get player count
            cursor.execute(db_query("SELECT COUNT(*) FROM players"))
            player_count = cursor.fetchone()[0]
            
            # Get donation history count
            cursor.execute(db_query("SELECT COUNT(*) FROM donation_history"))
            history_count = cursor.fetchone()[0]
            
            # Get snapshot count
            cursor.execute(db_query("SELECT COUNT(*) FROM snapshots"))
            snapshot_count = cursor.fetchone()[0]

            # 영구 보관 장부 누적 건수 (방송 종료/시작으로도 지워지지 않음)
            try:
                cursor.execute(db_query("SELECT COUNT(*) FROM donation_archive"))
                archive_count = cursor.fetchone()[0]
            except Exception:
                archive_count = 0
            
            # Get last 30 logs from donation_history
            cursor.execute(db_query("SELECT id, timestamp, name, amount, current_total, message, source FROM donation_history ORDER BY id DESC LIMIT 30"))
            history_rows = cursor.fetchall()
            history_list = []
            for r in history_rows:
                history_list.append({
                    'id': r[0],
                    'timestamp': r[1],
                    'name': r[2],
                    'amount': r[3],
                    'current_total': r[4],
                    'message': r[5],
                    'source': r[6]
                })
                
        return jsonify({
            'status': 'success',
            'is_postgres': IS_POSTGRES,
            # 영구 저장 여부. False면 임시 디스크 SQLite라 재시작 시 데이터가 사라진다.
            'persistent_storage': IS_POSTGRES,
            'last_db_error': LAST_DB_ERROR.get('message'),
            'last_db_error_time': LAST_DB_ERROR.get('time'),
            # 관리자 키가 아직 '공개된 기본값'인지. True 면 주소만 아는 사람이 조작할 수 있다.
            'weak_admin_secret': SECRET_IS_WEAK,
            # 깨우기가 지금 켜져 있는지(조종실 스위치). 켜두면 무료 인스턴스 시간을 하루 24시간 쓴다.
            'self_ping': bool(load_data().get('self_ping_enabled')),
            # 이 서비스에서 깨우기를 아예 못 쓰게 막아뒀는지(환경변수 하드 스위치)
            'self_ping_blocked': (os.environ.get('SELF_PING') or '').strip().lower() in ('0', 'off', 'false', 'no'),
            'player_count': player_count,
            'history_count': history_count,
            'snapshot_count': snapshot_count,
            'archive_count': archive_count,
            # 🏷️ 붙은 화면 목록(2026-10-02) — 로그인한 조종실에만. 공개 /api/health 엔 숫자만 나간다
            'screens': sse_screens(),
            'sse_evicted': _sse_evicted,
            'logs': history_list
        })
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/api/server/reset', methods=['POST'])
def reset_server_database():
    try:
        global MEMORY_STATE
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(db_query("DELETE FROM players"))
            cursor.execute(db_query("DELETE FROM kv_store"))
            cursor.execute(db_query("DELETE FROM donation_history"))
            cursor.execute(db_query("DELETE FROM snapshots"))
            
        # 얕은 복사면 중첩 객체가 DEFAULT_STATE와 공유되어 기본값 자체가 오염된다
        MEMORY_STATE = copy.deepcopy(DEFAULT_STATE)
        save_data(MEMORY_STATE, is_initial=True, sync=True)
        broadcast_event('update', MEMORY_STATE)
        return jsonify({"status": "success", "message": "데이터베이스가 성공적으로 완전히 리셋되었습니다."})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


# 방송을 시작·종료해도 DB 에서 안 지우는 설정 칸.
# ⚠️ 물음표 개수를 손으로 세지 않는다 — 칸을 하나 더하고 물음표를 안 늘려서
#    방송 시작·종료가 통째로 500 으로 죽을 뻔했다(2026-09-18, 테마 연출 칸).
BROADCAST_KEEP_KEYS = ('theme', 'theme_fx_enabled', 'neon_speed', 'saved_colors', 'target_goal', 'account',
                       'effect_rules', 'screen_effect', 'ticker_enabled', 'ticker_speed', 'ticker_text',
                       'totp_secret')


def _archive_and_clear_broadcast(session_label, what):
    """방송 시작·종료의 '장부 보관 + DB 비우기' 를 **한 트랜잭션** 으로 한다.

    ⚠️ 예전에는 보관(INSERT)과 지우기(DELETE)가 따로 커밋됐다. 보관은 됐는데 지우기가
       실패한 뒤 다시 누르면 같은 후원이 두 번 보관돼, 월별 후원 순위가 그만큼 두 배로 나왔다.
       이제는 둘 다 되거나 둘 다 안 된다. 게다가 '보관한 번호까지만' 지운다 —
       보관과 지우기 사이에 들어온 후원이 보관 없이 지워지는 틈도 막는다.
    ⚠️ 먼저 저장 큐를 비운다. 큐에 남은 낡은 저장이 지운 **뒤에** 쓰이면 지운 선수·설정이 되살아난다.
    ⚠️ 지운 뒤에는 LAST_PERSISTED(변경분 비교 기준)를 비운다. 옛 기준이 남아 있으면, 뒤이은
       전체 저장이 실패했을 때 다음 평소 저장이 '바뀐 게 없다' 며 지워진 설정 칸을 영영 안 쓴다.
    실패하면 예외를 그대로 던진다(롤백돼서 아무것도 안 지워진 상태다).
    """
    global LAST_PERSISTED
    drain_db_writes()
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(db_query("SELECT MAX(id) FROM donation_history"))
        _row = cursor.fetchone()
        max_id = int(_row[0]) if _row and _row[0] is not None else 0
        cursor.execute(db_query("""
            INSERT INTO donation_archive
                (archived_at, session_label, timestamp, name, amount, current_total, message, source, tx_id)
            SELECT ?, ?, timestamp, name, amount, current_total, message, source, tx_id
            FROM donation_history WHERE id <= ?
        """), (time.strftime('%Y-%m-%d %H:%M:%S'), session_label, max_id))
        cursor.execute(db_query("SELECT COUNT(*) FROM donation_archive"))
        print(f"  📚 [장부 영구 보관] 누적 {cursor.fetchone()[0]}건")

        cursor.execute(db_query("DELETE FROM players"))
        cursor.execute(db_query("DELETE FROM donation_history WHERE id <= ?"), (max_id,))
        cursor.execute(db_query("DELETE FROM snapshots"))
        # 설정 칸(BROADCAST_KEEP_KEYS)만 남기고 kv_store 를 비운다
        cursor.execute(
            db_query("DELETE FROM kv_store WHERE key NOT IN (%s)" % ', '.join('?' * len(BROADCAST_KEEP_KEYS))),
            BROADCAST_KEEP_KEYS
        )
        # 🏦 원장 경계 — 재정산이 여기서부터 이번 방송으로 센다
        _ledger_mark_broadcast(cursor, f'{what} ({session_label})')
    LAST_PERSISTED = None


@app.route('/api/server/end_broadcast', methods=['POST'])
def end_broadcast():
    try:
        global MEMORY_STATE
        with file_lock:
            # 0. ⚠️ 지우기 전에 반드시 보존한다.
            #    예전에는 방송 종료 시 장부(donation_history)를 그냥 삭제해서 기록이 영구히 사라졌다.
            session_label = time.strftime('%Y-%m-%d %H:%M:%S') + " 방송분"
            # ⚠️ 스냅샷은 아래 'DELETE FROM snapshots' 뒤에 넣는다.
            #    여기서 만들면 몇 줄 뒤 초기화가 방금 만든 백업까지 지워버려,
            #    실수로 방송을 종료했을 때 되돌릴 방법이 사라진다. 지금은 상태만 떠둔다.
            pre_state = copy.deepcopy(load_data())
            # 1. 장부 보관 + DB 비우기 — 한 트랜잭션. 보관에 실패하면 아무것도 안 지운다(기록 유실 방지)
            try:
                _archive_and_clear_broadcast(session_label, '방송 종료')
            except Exception as arch_e:
                print(f"❌ [장부 보관·초기화 실패 - 방송 종료 중단] {arch_e}")
                return jsonify({"status": "error",
                                "message": f"장부 백업·초기화에 실패해 방송 종료를 중단했습니다(아무것도 지우지 않았습니다): {arch_e}"}), 500

            # 초기화가 끝난 뒤에백업 스냅샷을 넣어야 살아남는다 (되돌리기 지점)
            create_snapshot(pre_state, f"방송 종료 자동 백업 ({session_label})")

            # 2. Get current state from database (which will have only configurations preserved)
            state = load_data()
            
            # Reset memory state and set broadcast_active to False
            state['broadcast_active'] = False
            state['bjs'] = []
            state['bottom_fixed']['score'] = 0
            # 🏺 모금함은 **후원분만** 턴다. 종잣돈(회사 상금)은 설정이라 남긴다 —
            #    매주 20만원을 손으로 다시 넣게 하면 언젠가 잊는다.
            state.setdefault('fundjar', {})['score'] = 0
            state['goal_offset'] = 0      # 💰 게이지 보정은 이번 방송 것 — 다음 주로 안 넘긴다
            state['reaction_mode'] = False
            # 🎬 리액션 대기줄도 방송 1회분이다. 안 비우면 지난주에 못 튼 시그니처가
            #    다음 방송을 시작하자마자 방송판에서 재생됐다(reaction_mode 는 큐가 있으면 다시 켜진다).
            state['reaction_queue'] = []
            state['match_data'] = {"active": False, "players": [], "time_left_ms": 180000,
                                   "is_running": False, "team_mode": False}
            state['pending_donations'] = []
            state['latest_donation'] = {"name": "", "amount": 0, "message": "", "time": 0}
            state['extra_game_active'] = False
            state['extra_bjs'] = []
            state['roulette_enabled'] = False
            if 'roulette' in state:
                state['roulette']['winner_name'] = None
                state['roulette']['is_spinning'] = False
                state['roulette']['select_name'] = ""
                state['roulette']['select_index'] = -1
            state['logs'] = []
            state['match_logs'] = []
            reset_session_keys(state)
            # 🎬 끝 화면에 띄울 '오늘의 기록' — 위에서 지우기 전에 떠 둔 pre_state 로 만든다.
            #    ⚠️ 방송을 끝낸 **뒤에** [끝 화면] 을 눌러도 오늘 기록이 나와야 한다.
            try:
                _stage_state(state)['last_snap'] = _stage_snapshot(pre_state)
            except Exception as _se:
                print(f'⚠️ [끝 화면 기록 보관 실패] {_se}', flush=True)

            # ⚠️ is_initial=True 로 전체 키를 다시 쓴다.
            #    위에서 kv_store 행을 지웠는데 메모리 값은 그대로라, 변경분만 쓰는 평소 방식으로는
            #    "바뀐 게 없다"고 판단해 아무것도 복구되지 않는다. 그 상태로 서버가 재시작되면
            #    볼륨·슬롯 후보 같은 설정이 기본값으로 돌아가 버린다.
            # ⚠️ 이 저장이 실패하면 '성공' 이라고 답하면 안 된다(save_data_checked 설명 참고).
            broadcast_event('update', state)
            try:
                save_data_checked(state, is_initial=True)
            except Exception as save_e:
                print(f"❌ [방송 종료 저장 실패] {save_e}", flush=True)
                return jsonify({"status": "error",
                                "message": f"방송은 종료했지만 저장에 실패했습니다 — 서버를 재시작하면 설정이 사라질 수 있어요. "
                                           f"DB 연결을 확인하고 [방송 종료] 를 한 번 더 눌러 주세요: {save_e}"}), 500

        return jsonify({"status": "success", "message": "방송이 종료되고 오늘의 데이터가 리셋되었습니다."})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/server/start_broadcast', methods=['POST'])
def start_broadcast():
    try:
        global MEMORY_STATE
        req = request.get_json(silent=True) or {}
        names = req.get('names', [])
        if not names:
            return jsonify({"status": "error", "message": "최소 한 명 이상의 플레이어를 등록해야 합니다."}), 400
        if len(names) > 10:
            return jsonify({"status": "error", "message": "플레이어는 최대 10명까지 등록할 수 있습니다."}), 400
            
        with file_lock:
            # 0. ⚠️ 방송 시작도 장부를 지우므로, 지우기 전에 지난 기록을 영구 보관한다.
            session_label = time.strftime('%Y-%m-%d %H:%M:%S') + " 방송 시작 전"
            # 1. 장부 보관 + DB 비우기 — 한 트랜잭션(_archive_and_clear_broadcast)
            try:
                _archive_and_clear_broadcast(session_label, '방송 시작')
            except Exception as arch_e:
                print(f"❌ [장부 보관·초기화 실패 - 방송 시작 중단] {arch_e}")
                return jsonify({"status": "error",
                                "message": f"장부 백업·초기화에 실패해 방송 시작을 중단했습니다(아무것도 지우지 않았습니다): {arch_e}"}), 500

            # 2. Get current statefrom database (which will have only configurations preserved)
            state = load_data()
            
            # 3. Set broadcast_active to True and initialize players
            state['broadcast_active'] = True
            state['broadcast_started_at'] = int(time.time() * 1000)
            state['bjs'] = [{"name": name.strip(), "score": 0, "contribution": 0} for name in names if name.strip()]
            state['bottom_fixed']['score'] = 0
            state.setdefault('fundjar', {})['score'] = 0     # 🏺 종잣돈은 그대로, 후원분만 0
            state['reaction_mode'] = False
            # 🎬 리액션 대기줄도 방송 1회분이다. 안 비우면 지난주에 못 튼 시그니처가
            #    다음 방송을 시작하자마자 방송판에서 재생됐다(reaction_mode 는 큐가 있으면 다시 켜진다).
            state['reaction_queue'] = []
            state['match_data'] = {"active": False, "players": [], "time_left_ms": 180000,
                                   "is_running": False, "team_mode": False}
            state['pending_donations'] = []
            state['latest_donation'] = {"name": "", "amount": 0, "message": "", "time": 0}
            state['extra_game_active'] = False
            state['extra_bjs'] = []
            state['roulette_enabled'] = False
            if 'roulette' in state:
                state['roulette']['winner_name'] = None
                state['roulette']['is_spinning'] = False
                state['roulette']['select_name'] = ""
                state['roulette']['select_index'] = -1
            state['logs'] = []
            state['match_logs'] = []
            reset_session_keys(state)
            # 🎬 지난 방송의 끝 화면이 새 방송 위에 남으면 안 된다.
            #    ⚠️ 시작 전 화면은 **그대로 둔다** — 선수를 먼저 등록해 두고 기다리는 흐름이 있다
            #       (등록하면 대기 화면에 멤버 이름이 뜬다). 방송에 들어갈 때 [끄기] 로 내린다.
            _ss = _stage_state(state)
            if _ss.get('mode') == 'end':
                _ss['mode'] = 'off'

            # kv_store 행을 위에서 지웠으므로 전체 키를 다시 기록해야 설정이 살아남는다
            # ⚠️ 이 저장이 실패하면 '성공' 이라고 답하면 안 된다(save_data_checked 설명 참고).
            broadcast_event('update', state)
            try:
                save_data_checked(state, is_initial=True)
            except Exception as save_e:
                print(f"❌ [방송 시작 저장 실패] {save_e}", flush=True)
                return jsonify({"status": "error",
                                "message": f"방송은 시작했지만 저장에 실패했습니다 — 서버를 재시작하면 설정이 사라질 수 있어요. "
                                           f"DB 연결을 확인하고 [방송 시작] 을 한 번 더 눌러 주세요: {save_e}"}), 500

        return jsonify({"status": "success", "message": "방송이 활성화되었습니다."})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

# ==========================================
# ⏪ 시간 여행 복원 API (오늘 지정 시간 기준)
# ==========================================
@app.route('/api/time_machine/restore_by_time', methods=['POST'])
def restore_by_time():
    """⏪ [막아 둠] 시각으로 되돌리기 — 410 으로 답하고 아무것도 바꾸지 않는다.

    ⚠️ 이 기능은 명단을 **후원 장부(donation_history)** 로 다시 만들었다. 그런데 그 표의
       name 은 '후원한 사람'이고 current_total 은 '후원 금액' 이다. 누르는 순간 점수판이
       선수 대신 후원자 이름들로 바뀌고, 점수 칸엔 원 단위 금액이 들어갔다(감사에서 재현).
       게다가 00~03시에는 '오늘' 날짜로 찾아서 방송이 시작한 어제 저녁을 못 찾았고,
       file_lock 없이 상태를 통째로 갈아끼워 그 사이 들어온 후원·점수를 덮었다.
    ⚠️ 제대로 하려면 선수별 점수 원장(bank_ledger)의 score_balance 로 다시 짜야 하는데,
       이름 바꾸기·백업 복구처럼 원장을 안 거치는 길이 있어 그것도 믿을 수 없다.
       → 되돌리기는 **스냅샷 되돌리기**(타임머신 목록)만 쓴다. 그쪽은 그 순간 상태를 통째로 떠 둔 것이다.
    """
    print("⛔ [시간여행 복원] 막아 둔 기능이 호출됐습니다 — 스냅샷 되돌리기를 안내합니다", flush=True)
    return jsonify({'status': 'error',
                    'message': '시각으로 되돌리기는 점수판을 후원자 이름으로 바꿔 버리는 문제가 있어 꺼 두었습니다. '
                               '같은 창의 [스냅샷 되돌리기] 목록에서 원하는 시점을 골라 주세요.'}), 410


# 설정 패치로는 건드릴 수 없는 필드.
# 점수·로그는 /api/score/add 로만, 큐·대기함은 후원 수신과 전용 엔드포인트로만 바뀌어야 한다.
# (여기에 구멍을 두면 patch 가 또 하나의 덮어쓰기 경로가 된다)
PATCH_DENY = frozenset((
    'bjs', 'extra_bjs', 'bottom_fixed', 'logs', 'match_logs',
    'reaction_queue', 'latest_donation', 'pending_donations',
    'api_token', 'server_time', 'version',
    # 🏅 후원 순위 집계는 서버가 후원을 받을 때만 적는다. 밖에서 통째로 덮어쓰면
    #    방금 들어온 후원이 사라진다(설정 3개는 자유롭게 바꿀 수 있다).
    'donor_tally',
    # 🎲 주사위게임도 서버만 굴린다(전용 엔드포인트로만 바뀐다)
    'dicegame',
    # 🎱 핀볼도 같다. 특히 round_id·running 이 밖에서 바뀌면 늦게 온 결과를 못 가려낸다.
    'pinball',
    # 🧩 퀴즈도 /api/quiz/* 로만 — 낡은 조종실이 통째로 보내면 방금 낸 문제 · 내 문제가 덮인다
    'quiz',
    # 💥 한 방 최고 후원도 후원 접수·배정 때만 서버가 적는다
    'best_single',
    # 🎬 시작·끝 화면도 /api/screen 으로만 (끝 화면 기록 last_snap 은 방송 종료만 적는다)
    'stage_screen', 'stage_live',
    # 🔥 지옥탈출 — 시작 순간 점수(base)가 밖에서 바뀌면 '받은 돈' 이 통째로 틀어진다
    'hell', 'broadcast_started_at',
    # 💾 세이브 슬롯도 /api/presets/* 로만 — 낡은 조종실이 통째로 보내면 방금 저장한 칸이 사라진다
    'layout_presets', 'layout_rev',
    # ✂️ 클립 목록도 /api/clip* 으로만
    'clip',
    # 📺 방송 화면과 옛 스위치 — /api/show 로만(옛 스위치는 show 가 계산해 적는다)
    'show',
)) | frozenset(showmod.LEGACY_OWNED)


@app.route('/api/settings/patch', methods=['POST'])
def api_settings_patch():
    """바뀐 필드만 받아서 합친다.

    ⚠️ 이 엔드포인트가 생긴 이유:
       편집기(admin.html)는 SSE 를 안 쓰고 1초마다 상태 전체를 받아 들고 있다가,
       편집할 때 그 스냅샷을 통째로 POST 했다. 그래서 슬라이더를 한 번 움직이면
       그 1초 사이에 들어온 점수가 통째로 사라졌다.
       (측정: 슬라이더 한 번에 5점 소실. 드래그 중에는 10점 중 9점 소실)
       바뀐 필드만 보내면 남이 바꾼 것을 건드릴 이유가 없다.
    """
    try:
        body = request.get_json(silent=True) or {}
        if not isinstance(body, dict) or not body:
            return jsonify({"status": "error", "message": "바꿀 필드가 없다"}), 400
        bad = [k for k in body if k in PATCH_DENY]
        if bad:
            return jsonify({"status": "error",
                            "message": f"이 필드는 설정 패치로 바꿀 수 없습니다: {', '.join(bad)}"}), 400

        with file_lock:
            state = load_data()
            _was_match = bool((state.get('match_data') or {}).get('active'))
            _was_roulette = copy.deepcopy(state.get('roulette'))
            # ⚔️ 폰 타이머 버튼이 match_data 를 통째로 보낸다 — 대결자 명단(이름 · 팀원 · 점수)은
            #    **서버 값을 통째로** 지킨다. 이 길로 대결자를 고치는 화면은 없다(폰은 켜기 · 타이머뿐).
            #    ⚠️ 점수만 지켰더니, 조종실에서 철수를 B팀으로 옮긴 뒤 폰이 옛 사본으로 타이머를 누르면
            #       팀원이 옛 구성으로 돌아가 철수 점수가 다시 A팀으로 들어갔다(2026-09-30 재현).
            _pm = body.get('match_data')
            _cm = state.get('match_data')
            if isinstance(_pm, dict) and isinstance(_cm, dict) and isinstance(_cm.get('players'), list):
                _pm['players'] = copy.deepcopy(_cm['players'])
            else:
                _keep_match_scores(_pm, _cm)
            state.update(body)
            # 📺 폰은 대결 켜기/끄기·룰렛 돌리기를 이 길로 보낸다 — 무대가 따라가게
            _prev_stage = showmod.ensure(state)['stage']
            showmod.ingest_roulette(state, _was_roulette)
            showmod.ingest_match(state, _was_match)
            showmod.project(state)
            _stage_log(_prev_stage, state['show']['stage'])
            state['version'] = (state.get('version') or 1) + 1
            save_data(state)
            broadcast_event('update', state)
        return jsonify({"status": "success", "patched": sorted(body.keys())})
    except Exception as e:
        print(f"Error in api_settings_patch: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500


# ==========================================
# 🖥️ GUI 관리자 및 로그인 창
# ==========================================
SELF_PING_INTERVAL = 600      # 10분마다 (Render 무료 비활성화 임계치 15분보다 짧게)
SELF_PING_POLL = 20           # 조종실에서 켠 걸 이만큼 안에 알아챈다


def start_self_ping():
    """Render 무료 인스턴스가 잠들지 않게 주기적으로 자기를 부른다.

    💸 이 루프가 도는 동안 서비스는 24시간 깨어 있고, 그게 무료 인스턴스 시간을 월 720시간 먹는다.
       무료 한도가 월 750시간이라 켜둔 서비스 하나가 한도를 거의 다 쓴다(2026-08 실측으로 확인).
       그런데 방송 중에는 오버레이·조종실의 SSE 연결이 계속 붙어 있어 저절로 깨어 있다.
       즉 이 루프가 실제로 지키는 건 '방송이 없는 동안의 깨어 있음'이다.
       그래서 기본은 꺼두고, 필요할 때만 조종실에서 켠다(state['self_ping_enabled']).

    SELF_PING=off 환경변수는 '조종실에서도 못 켜게' 하는 하드 스위치다(개발·예비 서비스용).
    """
    url = os.environ.get('RENDER_EXTERNAL_URL')
    if not url:
        return          # 로컬 실행 — 잠들 일이 없다

    if (os.environ.get('SELF_PING') or '').strip().lower() in ('0', 'off', 'false', 'no'):
        print("⏰ [Self-Ping] SELF_PING=off — 이 서비스에서는 깨우기를 쓰지 않습니다", flush=True)
        return

    def ping_loop():
        print(f"⏰ [Self-Ping] 준비됨 (조종실에서 켜면 시작): {url}", flush=True)
        time.sleep(30)
        last_ping = 0.0
        was_on = None
        while True:
            # 상태 한 칸만 읽으므로 file_lock 없이 본다(잠금을 오래 쥐면 후원 처리가 밀린다).
            try:
                on = bool(load_data().get('self_ping_enabled'))
            except Exception:
                on = False

            if on != was_on:
                print("⏰ [Self-Ping] " + ("켜짐 — 10분마다 깨웁니다 (무료 시간 소모)"
                                          if on else "꺼짐 — 요청이 없으면 15분 뒤 잠듭니다"), flush=True)
                was_on = on

            if on and (time.time() - last_ping) >= SELF_PING_INTERVAL:
                last_ping = time.time()
                try:
                    req = urllib.request.Request(url, headers={'User-Agent': 'LiveMaster-KeepAwake/1.0'})
                    with urllib.request.urlopen(req, timeout=15) as response:
                        print(f"⏰ [Self-Ping] 깨움 {response.getcode()}", flush=True)
                except Exception as e:
                    print(f"⚠️ [Self-Ping] 실패: {e}", flush=True)

            # ⚠️ 짧게 돌면서 상태를 살피지만, 이 자체로는 인스턴스가 깨어 있지 않는다.
            #    Render 의 잠들기 판정은 '들어온 HTTP 요청'이 기준이라 내부 스레드는 세지 않는다.
            time.sleep(SELF_PING_POLL)

    threading.Thread(target=ping_loop, daemon=True).start()

def run_flask():
    port = int(os.environ.get('PORT', 5000))
    start_self_ping()
    # ⚠️ Render 는 컨테이너 밖에서 들어오므로 0.0.0.0 이어야 한다(기본값 유지).
    #    반대로 직접 빌린 서버(VPS)에서는 앞단에 Caddy 가 HTTPS 를 받아 넘겨주므로,
    #    0.0.0.0 이면 이 포트가 인터넷에 그대로 열려 암호화 없는 우회로가 생긴다.
    #    (실제로 Vultr 서울 서버에서 8080 이 밖에서 응답하는 것을 확인했다)
    #    그런 곳에서는 BIND_HOST=127.0.0.1 을 넣어 Caddy 를 거치게 강제한다.
    host = (os.environ.get('BIND_HOST') or '0.0.0.0').strip()
    # ⚠️ 소켓에 시간제한을 건다. 이게 없으면 사라진 브라우저에 쓰다가 그 자리에서 영영 멈춰
    #    실 가닥이 하나씩 쌓인다(2026-09-30 방송 중 235개까지 갔다).
    #    SSE 는 15초마다 신호를 보내므로 90초 제한에 멀쩡한 화면이 걸릴 일은 없다.
    try:
        from werkzeug.serving import WSGIRequestHandler
        WSGIRequestHandler.timeout = SSE_SOCKET_TIMEOUT
    except Exception as e:
        print(f'⚠️ [소켓 시간제한] 못 걸었습니다 — 그대로 켭니다: {e}', flush=True)
    app.run(host=host, port=port, debug=False, use_reloader=False)

def has_gui_support():
    if os.environ.get('HEADLESS') or os.environ.get('DATABASE_URL'):
        return False
    if tk is None:
        return False
    try:
        temp_root = tk.Tk()
        temp_root.destroy()
        return True
    except Exception:
        return False

def run_login_gui():
    login_success = [False]
    
    def check_login():
        p = entry_pass.get().strip()
        # ⚠️ 예전에는 '0508' 을 그대로 비교했다. 공개 저장소에 적힌 비밀번호였고,
        #    ADMIN_PASSWORD 를 넣어도 이 창만은 옛 값으로 열렸다.
        if password_matches(p):
            login_success[0] = True
            login_win.destroy()
        else:
            messagebox.showerror('보안 인증 실패', '비밀번호가 올바르지 않습니다!')
            entry_pass.delete(0, tk.END)
            entry_pass.focus()
            
    def on_login_closing():
        login_win.destroy()
        sys.exit(0)
        
    login_win = tk.Tk()
    login_win.title('🔒 라이브 마스터 서버 기동 인증')
    login_win.geometry('380x220')
    login_win.configure(bg='#111113')
    login_win.resizable(False, False)
    
    ws = login_win.winfo_screenwidth()
    hs = login_win.winfo_screenheight()
    x = (ws / 2) - 190.0
    y = (hs / 2) - 110.0
    login_win.geometry(f'380x220+{int(x)}+{int(y)}')
    
    try:
        login_win.attributes('-alpha', 0.96)
    except:
        pass
        
    title = tk.Label(login_win, text='🔒 SERVER BOOT AUTH', fg='#00ffcc', bg='#111113', font=('Consolas', 15, 'bold'))
    title.pack(pady=20)
    
    frame_pass = tk.Frame(login_win, bg='#111113')
    frame_pass.pack(pady=10)
    
    lbl_pass = tk.Label(frame_pass, text='인증 PW : ', fg='#ffffff', bg='#111113', font=('Malgun Gothic', 10, 'bold'), width=8, anchor='e')
    lbl_pass.pack(side=tk.LEFT)
    
    entry_pass = tk.Entry(frame_pass, show='*', fg='white', bg='#222225', insertbackground='white', font=('Malgun Gothic', 10), width=18, relief='flat')
    entry_pass.pack(side=tk.LEFT)
    entry_pass.focus()
    
    entry_pass.bind('<Return>', lambda e: check_login())
    
    btn_login = tk.Button(login_win, text='🔓 서버 엔진 기동', command=check_login, fg='#000000', bg='#00ffcc', activebackground='#00cca3', font=('Malgun Gothic', 10, 'bold'), width=20, height=2, relief='flat')
    btn_login.pack(pady=15)
    
    login_win.protocol('WM_DELETE_WINDOW', on_login_closing)
    login_win.mainloop()
    
    return login_success[0]

def open_link(url):
    webbrowser.open(url)

def on_closing():
    if messagebox.askokcancel('서버 종료', '방송 서버를 완전히 종료하시겠습니까?\n(정산 기능 및 오버레이 송출이 중단됩니다)'):
        root.destroy()
        sys.exit(0)


# ── ✂️ 떼어 낸 기능들 (features/) ──
# ⚠️ 여기서 불러야 한다. 떼어 낸 파일들이 위에서 만든 공용 도구(app · load_data …)를 빌려 가므로
#    그보다 먼저 부르면 이름이 없어 죽는다. 순서도 중요하다 — 남의 것을 빌려 쓰는 파일이 뒤에 온다.
import features.account_video  # noqa: E402,F401  (주소만 등록)
from features.donor_memory import (  # noqa: E402
    _norm_donor, alias_lookup, donor_history, remember_assignment,
)
from features.excluded import (  # noqa: E402
    excluded_names, is_excluded,
)
from features.vip import (  # noqa: E402
    _vip_live, _vip_wipe_legacy_once,
)
import features.ai  # noqa: E402,F401  (주소만 등록)
import features.announce  # noqa: E402,F401  (주소만 등록)
import features.archive  # noqa: E402,F401  (주소만 등록)
import features.bjs  # noqa: E402,F401  (주소만 등록)
from features.clip import (  # noqa: E402
    _clip_log, _clip_state,
)
from features.score import (  # noqa: E402
    _find_score_target,
)
from features.dicegame import (  # noqa: E402
    _contrib_alert, _dicegame_state,
)
import features.donation  # noqa: E402,F401  (주소만 등록)
import features.effects  # noqa: E402,F401  (주소만 등록)
import features.extra_game  # noqa: E402,F401  (주소만 등록)
from features.hell import (  # noqa: E402
    _hell_state,
)
from features.layout import (  # noqa: E402
    _layout_read, _layout_write,
)
import features.legal  # noqa: E402,F401  (주소만 등록)
import features.logs  # noqa: E402,F401  (주소만 등록)
import features.notice  # noqa: E402,F401  (주소만 등록)
import features.offwork  # noqa: E402,F401  (주소만 등록)
import features.pages  # noqa: E402,F401  (주소만 등록)
import features.quiz  # noqa: E402,F401  (주소만 등록)
from features.pinball import (  # noqa: E402
    _pinball_winners,
)
import features.ranking  # noqa: E402,F401  (주소만 등록)
import features.reaction  # noqa: E402,F401  (주소만 등록)
from features.screens import (  # noqa: E402
    _stage_snapshot, _stage_state,
)
import features.show_api  # noqa: E402,F401  (주소만 등록)
import features.siggame  # noqa: E402,F401  (주소만 등록)
import features.signature_play  # noqa: E402,F401  (주소만 등록)
import features.signatures  # noqa: E402,F401  (주소만 등록)
import features.streamdeck  # noqa: E402,F401  (주소만 등록)
import features.uistats  # noqa: E402,F401  (주소만 등록)
import features.versions  # noqa: E402,F401  (주소만 등록)
import features.toon_accounts  # noqa: E402,F401  (주소만 등록)
import features.preflight  # noqa: E402,F401  (주소만 등록 · 🛫 방송 전 점검 · 방송 중 경보)
# ── ✂️ 끝 ──

if __name__ == '__main__':
    init_db()
    if not has_gui_support():
        print("🖥️ [헤드리스 모드] GUI 모드를 사용할 수 없는 환경이거나 클라우드 배포 상태입니다. 백엔드 Flask 서버만 무중단 구동합니다.")
        run_flask()
    else:
        if run_login_gui():
            flask_thread = threading.Thread(target=run_flask, daemon=True)
            flask_thread.start()
            
            root = tk.Tk()
            root.title('💎 라이브 마스터 순정 방송서버')
            root.geometry('460x340')
            root.configure(bg='#111113')
            root.resizable(False, False)
            
            try:
                root.attributes('-alpha', 0.96)
            except:
                pass
                
            ws = root.winfo_screenwidth()
            hs = root.winfo_screenheight()
            x = (ws / 2) - 230.0
            y = (hs / 2) - 170.0
            root.geometry(f'460x420+{int(x)}+{int(y)}')
            
            # UI 구성
            lbl_logo = tk.Label(root, text='💎 LIVE MASTER SERVER', fg='#00ffcc', bg='#111113', font=('Consolas', 18, 'bold'))
            lbl_logo.pack(pady=15)
            
            port = int(os.environ.get('PORT', 5000))
            lbl_status = tk.Label(root, text=f'🟢 실시간 방송 정산 엔진 구동 중 (Port: {port})', fg='#ffffff', bg='#111113', font=('Malgun Gothic', 11, 'bold'))
            lbl_status.pack(pady=5)
            
            lbl_info = tk.Label(root, text='투네이션의 모든 수동 후원이 대기함으로 입하되며,\n조종실 및 방송 오버레이가 한치의 오차 없이 구동됩니다.', fg='#8e8e93', bg='#111113', font=('Malgun Gothic', 9), justify='center')
            lbl_info.pack(pady=5)
            
            frame_btns = tk.Frame(root, bg='#111113')
            frame_btns.pack(pady=20)
            
            btn_ctrl = tk.Button(frame_btns, text='💻 제어 센터 (조종실)', command=lambda: open_link(f'http://localhost:{port}/controller'), fg='#000000', bg='#00ffcc', activebackground='#00cca3', font=('Malgun Gothic', 10, 'bold'), width=18, height=2, relief='flat')
            btn_ctrl.pack(side=tk.LEFT, padx=10)
            
            btn_ovr = tk.Button(frame_btns, text='🎬 송출용 오버레이', command=lambda: open_link(f'http://localhost:{port}/overlay'), fg='#ffffff', bg='#333336', activebackground='#444448', font=('Malgun Gothic', 10, 'bold'), width=18, height=2, relief='flat')
            btn_ovr.pack(side=tk.LEFT, padx=10)
            
            root.protocol('WM_DELETE_WINDOW', on_closing)
            root.mainloop()
