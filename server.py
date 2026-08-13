import sys
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
import threading
import logging
import pyotp
import secrets

import time
import csv
import queue
import shutil
import socket
import sqlite3
from contextlib import contextmanager
import ssl
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
from flask_cors import CORS
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

def load_auth_config():
    config = {
        'admin_password': '0508',
        'session_secret': 'isacbin_master_key_0508',
        'totp_secret': ''
    }
    if os.path.exists(AUTH_CONFIG_FILE):
        try:
            with open(AUTH_CONFIG_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                if 'admin_password' in data:
                    config['admin_password'] = data['admin_password']
                if 'session_secret' in data:
                    config['session_secret'] = data['session_secret']
                if 'totp_secret' in data:
                    config['totp_secret'] = data['totp_secret']
        except Exception as e:
            print(f"Error reading auth config: {e}")
            
    env_password = os.environ.get('ADMIN_PASSWORD')
    if env_password:
        config['admin_password'] = env_password.strip()
        
    env_session_secret = os.environ.get('SESSION_SECRET')
    if env_session_secret:
        config['session_secret'] = env_session_secret.strip()
        
    env_totp_secret = os.environ.get('TOTP_SECRET')
    if env_totp_secret:
        config['totp_secret'] = env_totp_secret.strip()
        
    if not config['totp_secret']:
        config['totp_secret'] = pyotp.random_base32()
        save_auth_config(config)
        
    return config

def save_auth_config(config):
    try:
        with open(AUTH_CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=4)
    except Exception as e:
        print(f"Error writing auth config: {e}")

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

def enqueue_signature(state, sig, amount, donator, message, skip_popup=False):
    """시그니처를 리액션 큐에 추가 (모든 재생 경로가 이 함수를 공유).

    큐를 태우면 reaction_mode가 켜지고, 재생이 끝나 큐가 비면 자동으로 꺼진다.
    skip_popup: 슬롯 당첨처럼 이미 자체 연출을 보여준 경우 후원 팝업을 건너뛴다.
    """
    reaction_uuid = f"rq_{uuid.uuid4().hex}"
    state.setdefault('reaction_queue', []).append({
        "id": reaction_uuid,
        "item_id": sig.get('id'),
        "title": sig.get('title'),
        "audio_url": sig.get('sound_url') or "",
        "image_url": sig.get('image_url') or "",
        "duration": sig.get('duration') or 10,
        "amount": amount,
        "donator": donator,
        "message": message,
        "skip_popup": bool(skip_popup)
    })
    state['reaction_mode'] = True
    return reaction_uuid

# 🛡️ 내용 기반 후원 중복 방지 (tx_id 없는 재전송 대비)
# 투네이션이 같은 후원을 tx_id 없이 두 번 POST하면 시그니처가 두 번 재생되던 문제를 막는다.
# 이름+금액+메시지가 완전히 동일한 후원이 아주 짧은 시간(윈도우) 안에 또 오면 중복으로 간주한다.
# 서로 다른 사람이 같은 금액/메시지를 2.5초 안에 보낼 확률은 사실상 0이라 안전하다.
_recent_don_lock = threading.Lock()
_recent_don = {}
DONATION_DEDUPE_WINDOW = 2.5

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

def _slot_finish(winner):
    """슬롯 당첨 확정 처리: 슬롯 위젯을 끄고 당첨 시그니처를 리액션 큐에 넣는다."""
    try:
        title = winner.get('title') or '시그니처'
        with file_lock:
            state = load_data()
            state['slot_enabled'] = False
            enqueue_signature(state, winner, winner.get('amount') or 0,
                              '🎰 슬롯머신', f'[슬롯 당첨] {title}', skip_popup=True)
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
CORS(app)
file_lock = threading.Lock()

# 🚫 [강력 차단] 웹 브라우저 및 OBS CEF 캐싱 방지 헤더 이식
@app.after_request
def add_header(r):
    r.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    r.headers["Pragma"] = "no-cache"
    r.headers["Expires"] = "0"
    return r

# 🔒 [보안 통제] 웹 제어실 및 중요 API 접근 제한 미들웨어
@app.before_request
def require_login():
    path = request.path
    
    # 정적 자원 파일 프리패스
    if (path.endswith('.css') or path.endswith('.js') or path.endswith('.png') or 
        path.endswith('.jpg') or path.endswith('.ico') or path.endswith('.woff') or 
        path.endswith('.woff2') or path.endswith('.ttf') or path.endswith('.svg')):
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
        '/api/stream',
        '/api/ping',
        '/api/donation',
        '/api/streamdeck/neon',
        '/api/streamdeck/save',
        '/api/roulette/winner',
        '/api/data',
        '/api/signatures',
        '/api/reaction/next',
        '/api/reaction/list',
        '/toonation_tampermonkey.user.js',
        '/setup'
    ]
    
    # 메서드까지 봐야 하는 예외: 조회는 오버레이가 써야 해서 공개, 변경은 로그인 필요.
    # (경로만으로 예외를 주면 POST/DELETE까지 무인증으로 열려버린다)
    method_exempt = {
        '/api/vips': ('GET',),
    }
    if path in method_exempt and request.method in method_exempt[path]:
        return

    # 시그니처 등록(/upload, /노래등록)은 관리 기능이므로 로그인 필요로 변경했다.
    # (등록 API가 /api/signatures/add 로 바뀌면서 인증이 필요해졌기 때문)
    if (path in exempt_routes or
        path.startswith('/uploads/')):
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

# 📡 실시간 SSE 클라이언트 관리 시스템
sse_clients = []
sse_lock = threading.Lock()

def broadcast_event(event_name, data):
    if isinstance(data, dict):
        data = data.copy()
        data['server_time'] = int(time.time() * 1000)
    with sse_lock:
        message = f"event: {event_name}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"
        for client_q in sse_clients:
            try:
                client_q.put_nowait(message)
            except queue.Full:
                pass

def get_or_create_totp_secret():
    return load_auth_config()['totp_secret']

def serve_html_file(filename):
    local_path = os.path.join(BASE_DIR, filename)
    if os.path.exists(local_path):
        return send_from_directory(BASE_DIR, filename)
    return send_from_directory(BUNDLE_DIR, filename)

DEFAULT_STATE = {
    "bjs": [],
    "bottom_fixed": {"name": "운영비", "score": 0},
    "target_goal": 50000,
    "theme": "default",
    "reaction_mode": False,
    "reaction_queue": [],
    "reaction_volume": 0.5,
    "popup_enabled": True,
    "takeover_enabled": True,
    "ticker_enabled": True,
    "ticker_speed": 70,
    "ticker_text": "📢 환영합니다! 후원은 방송에 큰 힘이 됩니다!",
    "match_data": {"active": False, "players": [], "time_left_ms": 180000, "is_running": False},
    "account": {"bank": "기업은행", "acc_num": "464-068673-04-016", "name": "드래곤엔터"},
    "pending_donations": [],
    "latest_donation": {"name": "", "amount": 0, "message": "", "time": 0},
    "extra_game_active": False,
    "extra_bjs": [],
    "roulette_enabled": False,
    # 🎰 슬롯머신
    # load_data()는 DEFAULT_STATE에 있는 키만 복원하므로, 여기 없으면 재시작 때 조용히 사라진다.
    "slot_enabled": True,
    "slot_pool": [],   # 이번 방송에 쓸 시그니처 id 목록. 비어 있으면 전체를 후보로 사용.
    # 🎯 목표 100% 달성 연출 (달성하면 pending, 운영자가 승인해야 송출)
    "goal_event_pending": False,
    "goal_event_approved": False,
    # 🏃 퇴근전쟁(퇴근빵): 켜면 랭킹판 자리에 개인별 목표 진행바가 뜬다
    "home_race_enabled": False,
    "home_goals": {},         # {플레이어 이름: 퇴근 목표 점수}
    "home_race_notified": [], # 이미 퇴근 카드를 띄운 사람 (송출 후 다시 생기는 것 방지)
    "broadcast_active": False,
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
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS reaction_files (
                    id VARCHAR(64) PRIMARY KEY,
                    filename TEXT NOT NULL,
                    content_type VARCHAR(128) NOT NULL,
                    file_data BYTEA NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS reaction_items (
                    id SERIAL PRIMARY KEY,
                    title TEXT NOT NULL,
                    amount INTEGER DEFAULT 0,
                    audio_file_id VARCHAR(64),
                    image_file_id VARCHAR(64),
                    is_enabled BOOLEAN DEFAULT TRUE
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
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS reaction_files (
                    id TEXT PRIMARY KEY,
                    filename TEXT NOT NULL,
                    content_type TEXT NOT NULL,
                    file_data BLOB NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS reaction_items (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    amount INTEGER DEFAULT 0,
                    audio_file_id TEXT,
                    image_file_id TEXT,
                    is_enabled INTEGER DEFAULT 1
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

        # 👑 [특별 후원자(VIP)] 닉네임별 등급/색상/뱃지. 방송 데이터와 무관하게 계속 유지된다.
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS vip_donators (
                name TEXT PRIMARY KEY,
                grade TEXT NOT NULL,
                custom_color TEXT DEFAULT '#ffd700',
                badge TEXT DEFAULT '👑'
            )
        """)

        # 📚 [영구 보관 장부] 방송 종료 시 donation_history는 초기화되지만,
        # 여기로 먼저 복사해 두므로 지난 방송 기록이 영구히 남는다. (append-only, 절대 삭제하지 않음)
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
            state[key] = default_val
            
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
            save_data_sync(new_data, is_initial)
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
                hist_rows, ledger_rows = [], []
                for new_p in new_data.get("bjs", []):
                    p_name = new_p["name"]
                    p_score = int(new_p.get("score") or 0)
                    p_contrib = int(new_p.get("contribution") or 0)
                    score_diff = p_score - old_scores.get(p_name, 0)
                    contrib_diff = p_contrib - old_contribs.get(p_name, 0)

                    if score_diff != 0:
                        hist_rows.append((now_str, p_name, score_diff, p_score, "수동 점수 조작", "mobile"))
                    # 🏦 은행 원장: 변동분과 거래 후 잔액을 남겨 나중에 재정산할 수 있게 한다
                    if score_diff != 0 or contrib_diff != 0:
                        ledger_rows.append((now_str, p_name, "MANUAL_CHANGE", score_diff, p_score,
                                            contrib_diff, p_contrib,
                                            f"점수 {score_diff:+} / 기여도 {contrib_diff:+}"))

                # N분할처럼 여러 명이 한꺼번에 바뀔 때 왕복이 인원수만큼 늘지 않도록 묶어서 넣는다
                if hist_rows:
                    ph = ', '.join([('(%s, %s, %s, %s, %s, %s)' if IS_POSTGRES else '(?, ?, ?, ?, ?, ?)')] * len(hist_rows))
                    cursor.execute(
                        f"INSERT INTO donation_history (timestamp, name, amount, current_total, message, source) VALUES {ph}",
                        [v for r in hist_rows for v in r]
                    )
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
    state['home_race_notified'] = []
    state['home_goals'] = {}
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

def save_data(new_data, is_initial=False, sync=False):
    """상태 저장.

    sync=True: 후원 접수·점수 변경·방송 시작/종료처럼 잃으면 안 되는 기록은
               응답을 돌려주기 전에 DB에 직접 쓴다.
               (비동기 큐에만 넣으면 프로세스가 죽을 때 마지막 쓰기가 사라진다)
    sync=False: 슬라이더·전광판 문구 같은 잦은 UI 갱신은 기존대로 백그라운드 처리.
    """
    global MEMORY_STATE
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
    if done is not None:
        # 워커가 밀려 있어도 방송이 멈추지 않도록 상한을 둔다 (실패는 LAST_DB_ERROR에 남음)
        if not done.wait(timeout=30):
            print("⚠️ [동기 저장 시간 초과] 백그라운드에서 계속 진행됩니다.")

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
    q = queue.Queue()
    with sse_lock:
        sse_clients.append(q)
        
    def event_generator():
        initial_state = load_data()
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
                yield msg
            except queue.Empty:
                yield "event: ping\ndata: {}\n\n"
            except GeneratorExit:
                break
                
        with sse_lock:
            if q in sse_clients:
                sse_clients.remove(q)
                
    response = app.response_class(event_generator(), mimetype='text/event-stream')
    response.headers['X-Accel-Buffering'] = 'no'
    response.headers['Cache-Control'] = 'no-cache'
    response.headers['Connection'] = 'keep-alive'
    return response

@app.route('/api/ping')
def api_ping():
    return jsonify({'status': 'pong'})

# 🟢 시그니처 목록 (Supabase 대리 조회) — 오버레이/컨트롤러/슬롯이 공통으로 사용
@app.route('/api/signatures')
def api_signatures():
    try:
        sigs = supabase_list_signatures()
        return jsonify({'status': 'success', 'signatures': sigs, 'count': len(sigs)})
    except Exception as e:
        print(f"[시그니처 목록 조회 오류] {e}")
        return jsonify({'status': 'error', 'message': str(e), 'signatures': []}), 500

@app.route('/api/donation/ranking')
def api_donation_ranking():
    """현재 방송의 누적 후원 순위(이름별 합계·건수).
       donation_history는 방송 시작/종료 때 초기화되므로 자연히 '이번 방송' 집계가 된다."""
    try:
        rows = []
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT name, SUM(amount) AS total, COUNT(*) AS cnt, MAX(id) AS last_id
                FROM donation_history
                GROUP BY name
                ORDER BY total DESC, last_id DESC
            """)
            for r in cursor.fetchall():
                rows.append({'name': r[0], 'total': int(r[1] or 0), 'count': int(r[2] or 0)})
        return jsonify({'status': 'success', 'ranking': rows, 'count': len(rows)})
    except Exception as e:
        print(f"[후원 순위 조회 오류] {e}")
        return jsonify({'status': 'error', 'message': str(e), 'ranking': []}), 500

# ==========================================
# 🎵 시그니처 관리 (등록 / 수정 / 삭제) — 로그인 필요 (exempt 목록에 없음)
# ==========================================
def _save_signature_files(sig_id, image_file, sound_file):
    """업로드된 파일을 Storage에 올리고 {image_url, sound_url} 조각 반환.

    ⚠️ 파일 경로는 id 기준으로 고정이라 교체 시 URL이 같아진다.
    그러면 Supabase CDN 캐시 때문에 방송 화면에 '옛 사진/옛 음원'이 최대 1시간 계속 나온다.
    저장하는 URL 끝에 버전(?v=타임스탬프)을 붙여 교체 즉시 반영되게 한다.
    """
    ver = int(time.time())
    out = {}
    if image_file and image_file.filename:
        data, ext, ctype = compress_image_to_webp(image_file)
        out['image_url'] = storage_upload(f"images/{sig_id}.{ext}", data, ctype) + f"?v={ver}"
    if sound_file and sound_file.filename:
        ext = (sound_file.filename.rsplit('.', 1)[-1] or 'mp3').lower()
        # 클라이언트가 보낸 content_type은 신뢰하지 않고 확장자로 결정한다.
        # (octet-stream으로 올라가면 일부 브라우저에서 오디오 재생이 실패함)
        AUDIO_TYPES = {'mp3': 'audio/mpeg', 'm4a': 'audio/mp4', 'aac': 'audio/aac',
                       'ogg': 'audio/ogg', 'wav': 'audio/wav', 'webm': 'audio/webm',
                       'mp4': 'video/mp4'}
        ctype = AUDIO_TYPES.get(ext)
        if not ctype:
            ctype = sound_file.content_type or 'application/octet-stream'
        out['sound_url'] = storage_upload(f"sounds/{sig_id}.{ext}", sound_file.read(), ctype) + f"?v={ver}"
    return out

@app.route('/api/signatures/add', methods=['POST'])
def api_signature_add():
    try:
        if not _supabase_ready():
            return jsonify({'status': 'error', 'message': 'Supabase가 설정되지 않았습니다.'}), 500

        amount = int(request.form.get('amount') or 0)
        title = (request.form.get('title') or '').strip() or f"{amount:,}원 시그니처"
        duration = int(request.form.get('duration') or 10)
        if amount <= 0:
            return jsonify({'status': 'error', 'message': '후원 금액을 입력해주세요.'}), 400

        # 1) 행 먼저 삽입해서 id 확보 (파일 경로에 id를 쓰기 때문)
        row = supabase_insert_signature({'amount': amount, 'title': title, 'duration': duration})
        if not row:
            return jsonify({'status': 'error', 'message': '시그니처 생성에 실패했습니다.'}), 500
        sig_id = row['id']

        # 2) 파일 업로드 후 URL 반영
        urls = _save_signature_files(sig_id, request.files.get('image'), request.files.get('sound'))
        if urls:
            row = supabase_update_signature(sig_id, urls) or row

        print(f"  ✅ [시그니처 등록] #{sig_id} '{title}' {amount}원")
        return jsonify({'status': 'success', 'message': '시그니처가 등록되었습니다.', 'signature': row})
    except Exception as e:
        print(f"[시그니처 등록 오류] {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/api/signatures/update/<int:sig_id>', methods=['POST'])
def api_signature_update(sig_id):
    try:
        current = supabase_get_signature(sig_id)
        if not current:
            return jsonify({'status': 'error', 'message': '시그니처를 찾을 수 없습니다.'}), 404

        fields = {}
        if request.form.get('amount') is not None and request.form.get('amount') != '':
            fields['amount'] = int(request.form.get('amount'))
        if request.form.get('title') is not None and request.form.get('title').strip():
            fields['title'] = request.form.get('title').strip()
        if request.form.get('duration'):
            fields['duration'] = int(request.form.get('duration'))

        image_file = request.files.get('image')
        sound_file = request.files.get('sound')
        # 파일 교체 시 기존 Storage 파일 정리 (확장자가 바뀔 수 있으므로 URL 기준 삭제)
        if image_file and image_file.filename:
            storage_delete_by_url(current.get('image_url'))
        if sound_file and sound_file.filename:
            storage_delete_by_url(current.get('sound_url'))
        fields.update(_save_signature_files(sig_id, image_file, sound_file))

        if not fields:
            return jsonify({'status': 'success', 'message': '변경 사항이 없습니다.', 'signature': current})

        row = supabase_update_signature(sig_id, fields)
        print(f"  ✏️ [시그니처 수정] #{sig_id} {list(fields.keys())}")
        return jsonify({'status': 'success', 'message': '시그니처가 수정되었습니다.', 'signature': row})
    except Exception as e:
        print(f"[시그니처 수정 오류] {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/api/signatures/delete/<int:sig_id>', methods=['POST', 'DELETE'])
def api_signature_delete(sig_id):
    try:
        current = supabase_get_signature(sig_id)
        if not current:
            return jsonify({'status': 'error', 'message': '시그니처를 찾을 수 없습니다.'}), 404
        storage_delete_by_url(current.get('image_url'))
        storage_delete_by_url(current.get('sound_url'))
        supabase_delete_signature(sig_id)
        print(f"  🗑️ [시그니처 삭제] #{sig_id} '{current.get('title')}'")
        return jsonify({'status': 'success', 'message': '시그니처가 삭제되었습니다.'})
    except Exception as e:
        print(f"[시그니처 삭제 오류] {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500

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

@app.route('/api/bank/recalculate', methods=['POST'])
def recalculate_bank_balances():
    """원장에 쌓인 변동분을 처음부터 다시 합산해 현재 잔액을 재구성한다.
       점수가 어긋났다고 의심될 때 쓰는 복구 수단."""
    try:
        global MEMORY_STATE, LAST_PERSISTED
        with file_lock:
            with get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(db_query("""
                    SELECT player_name, SUM(score_change), SUM(contrib_change)
                    FROM bank_ledger GROUP BY player_name
                """))
                totals = {r[0]: (r[1] or 0, r[2] or 0) for r in cursor.fetchall()}

                for name, (score_sum, contrib_sum) in totals.items():
                    if IS_POSTGRES:
                        cursor.execute(
                            "INSERT INTO players (name, score, contribution) VALUES (%s, %s, %s) "
                            "ON CONFLICT (name) DO UPDATE SET score = EXCLUDED.score, contribution = EXCLUDED.contribution",
                            (name, score_sum, contrib_sum)
                        )
                    else:
                        cursor.execute(
                            "INSERT INTO players (name, score, contribution) VALUES (?, ?, ?) "
                            "ON CONFLICT(name) DO UPDATE SET score = excluded.score, contribution = excluded.contribution",
                            (name, score_sum, contrib_sum)
                        )

            # DB에서 다시 읽어 메모리 상태를 맞춘다
            MEMORY_STATE = None
            LAST_PERSISTED = None
            state = load_data()
            broadcast_event('update', state)

        print(f"  🏦 [원장 재정산] {len(totals)}명 잔액 복구")
        return jsonify({"status": "success",
                        "message": f"{len(totals)}명의 잔액을 원장 기준으로 재정산했습니다.",
                        "updated": len(totals)})
    except Exception as e:
        print(f"[원장 재정산 오류] {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

# ==========================================
# 👑 특별 후원자(VIP) 관리
#    조회는 오버레이가 써야 하므로 공개, 등록/삭제는 로그인 필요(exempt 목록에 없음)
# ==========================================
@app.route('/api/vips', methods=['GET'])
def get_vips():
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(db_query("SELECT name, grade, custom_color, badge FROM vip_donators ORDER BY name ASC"))
            vips = [{"name": r[0], "grade": r[1], "custom_color": r[2], "badge": r[3]}
                    for r in cursor.fetchall()]
        return jsonify({"status": "success", "vips": vips})
    except Exception as e:
        print(f"[VIP 목록 조회 오류] {e}")
        return jsonify({"status": "error", "message": str(e), "vips": []}), 500

@app.route('/api/vips', methods=['POST'])
def add_or_update_vip():
    try:
        data = request.get_json(silent=True) or {}
        name = (data.get('name') or '').strip()
        grade = (data.get('grade') or '').strip()
        custom_color = data.get('custom_color') or '#ffd700'
        badge = data.get('badge') or '👑'
        if not name or not grade:
            return jsonify({"status": "error", "message": "닉네임과 등급은 필수입니다."}), 400

        with get_db_connection() as conn:
            cursor = conn.cursor()
            if IS_POSTGRES:
                cursor.execute("""
                    INSERT INTO vip_donators (name, grade, custom_color, badge)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (name) DO UPDATE
                    SET grade = EXCLUDED.grade,
                        custom_color = EXCLUDED.custom_color,
                        badge = EXCLUDED.badge
                """, (name, grade, custom_color, badge))
            else:
                cursor.execute("""
                    INSERT OR REPLACE INTO vip_donators (name, grade, custom_color, badge)
                    VALUES (?, ?, ?, ?)
                """, (name, grade, custom_color, badge))

        broadcast_event('vips_updated', {})
        print(f"  👑 [VIP 저장] {name} ({grade})")
        return jsonify({"status": "success", "message": "특별 후원자 정보가 저장되었습니다."})
    except Exception as e:
        print(f"[VIP 저장 오류] {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/vips', methods=['DELETE'])
def delete_vip():
    try:
        name = request.args.get('name')
        if not name:
            return jsonify({"status": "error", "message": "닉네임이 누락되었습니다."}), 400
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(db_query("DELETE FROM vip_donators WHERE name = ?"), (name,))
        broadcast_event('vips_updated', {})
        print(f"  👑 [VIP 해제] {name}")
        return jsonify({"status": "success", "message": "특별 후원자 해제 완료!"})
    except Exception as e:
        print(f"[VIP 삭제 오류] {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/offwork/broadcast', methods=['POST'])
def broadcast_offwork():
    """🏃 퇴근 성공 연출 송출. 운영자가 승인대기함에서 [송출하기]를 누를 때 호출된다."""
    try:
        data = request.get_json(silent=True) or {}
        name = (data.get('name') or '선수').strip()
        broadcast_event('off_work_event', {'name': name})
        print(f"  🏃 [퇴근 송출] {name}")
        return jsonify({"status": "success", "message": f"{name}님 퇴근 이벤트를 송출했습니다."})
    except Exception as e:
        print(f"[퇴근 송출 오류] {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/goal/approve_event', methods=['POST'])
def approve_goal_event():
    """🎯 목표 100% 달성 연출 송출 승인. 운영자가 눌러야 오버레이에 연출이 나간다."""
    try:
        with file_lock:
            state = load_data()
            state['goal_event_pending'] = False
            state['goal_event_approved'] = True
            save_data(state)
            broadcast_event('goal_celebration', {
                'timestamp': time.time(),
                'target_goal': state.get('target_goal', 50000)
            })
            broadcast_event('update', state)
        print("  🎯 [목표 달성 연출 송출]")
        return jsonify({"status": "success", "message": "목표 달성 연출을 방송 화면에 송출했습니다!"})
    except Exception as e:
        print(f"[목표 연출 송출 오류] {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/signature/play', methods=['POST'])
def api_signature_play():
    """수동 송출 (정산 장부 기록 없음).
       sig_id 지정 시 해당 시그니처 그대로, 아니면 amount로 매칭."""
    try:
        data = request.get_json(silent=True) or {}
        sig_id = data.get('sig_id')
        amount = int(data.get('amount') or 0)
        donator = (data.get('name') or '수동송출').strip() or '수동송출'
        message = (data.get('message') or '').strip()

        if sig_id:
            sig = supabase_get_signature(sig_id)
            if sig and not amount:
                amount = sig.get('amount') or 0
        else:
            if amount <= 0:
                return jsonify({'status': 'error', 'message': '후원 금액을 입력해주세요.'}), 400
            sig = supabase_match_signature(amount)

        if not sig:
            return jsonify({'status': 'error', 'message': '재생할 시그니처를 찾지 못했습니다.'}), 404

        with file_lock:
            state = load_data()
            enqueue_signature(state, sig, amount, donator, message)
            save_data(state)
            broadcast_event('update', state)

        print(f"  ▶️ [수동 송출] {amount}원 → '{sig.get('title')}' (#{sig.get('id')})")
        return jsonify({'status': 'success', 'message': '송출했습니다.', 'signature': sig})
    except Exception as e:
        print(f"[수동 송출 오류] {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500

# ==========================================
# 👥 BJ 일괄 등록 API
# ==========================================
@app.route('/api/bjs/import', methods=['POST'])
def import_bjs():
    try:
        req = request.json
        names = req.get('names', [])
        if not names:
            return jsonify({'status': 'error', 'message': '등록할 이름이 없습니다.'}), 400
            
        with file_lock:
            state = load_data()
            overwrite = req.get('overwrite', False)
            new_bjs = []
            
            for name in names:
                name = name.strip()
                if not name:
                    continue
                new_bjs.append({"name": name, "score": 0, "contribution": 0})
                
            if overwrite:
                state['bjs'] = new_bjs
            else:
                existing_names = {bj['name'] for bj in state.get('bjs', [])}
                for new_bj in new_bjs:
                    if new_bj['name'] not in existing_names:
                        state['bjs'].append(new_bj)
                        
            save_data(state, sync=True)
            broadcast_event('update', state)
            
        return jsonify({'status': 'success', 'count': len(new_bjs)})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

# ==========================================
# 🌐 페이지 라우팅
# ==========================================
@app.route('/setup', methods=['GET', 'POST'])
def serve_setup():
    if request.method == 'POST':
        try:
            data = request.get_json() or {}
            p = data.get('password', '').strip()
            if p == load_auth_config()['admin_password']:
                session['setup_authorized'] = True
                return jsonify({'status': 'success'})
            else:
                return jsonify({'status': 'error', 'message': '비밀번호가 잘못되었습니다.'}), 400
        except Exception as e:
            return jsonify({'status': 'error', 'message': str(e)}), 500

    # GET request
    if not session.get('setup_authorized'):
        # Return a simple password protection UI for setup
        html = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>🔒 라이브 마스터 OTP 등록 게이트</title>
    <style>
        body {{
            background: #0d0d0f;
            color: #f5f5f7;
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            display: flex;
            align-items: center;
            justify-content: center;
            min-height: 100vh;
            margin: 0;
        }}
        .card {{
            background: #16161a;
            border: 1px solid rgba(255,255,255,0.08);
            border-radius: 20px;
            padding: 40px 30px;
            text-align: center;
            box-shadow: 0 10px 30px rgba(0,0,0,0.5);
            max-width: 400px;
            width: 90%;
            box-sizing: border-box;
        }}
        h2 {{ color: #00ffcc; margin-top: 0; font-size: 22px; }}
        input {{
            width: 100%;
            background: rgba(255,255,255,0.05);
            border: 1px solid rgba(255,255,255,0.1);
            padding: 12px;
            border-radius: 8px;
            color: #fff;
            font-size: 16px;
            text-align: center;
            box-sizing: border-box;
            outline: none;
            margin: 20px 0;
        }}
        input:focus {{ border-color: #00ffcc; }}
        .btn {{
            background: #00ffcc;
            color: #000;
            border: none;
            padding: 14px 28px;
            font-weight: bold;
            border-radius: 8px;
            cursor: pointer;
            width: 100%;
            font-size: 15px;
        }}
        .err {{ color: #ff453a; font-size: 13px; margin-top: 10px; display: none; }}
    </style>
</head>
<body>
    <div class="card">
        <h2>🔒 OTP 등록 페이지 인증</h2>
        <p style="font-size: 14px; color: #8e8e93;">보안을 위해 서버 비밀번호를 입력해 주세요.</p>
        <input type="password" id="pw" placeholder="비밀번호 입력" autofocus onkeydown="if(event.key==='Enter') verifyPw()">
        <button onclick="verifyPw()" class="btn">인증 및 등록 진행</button>
        <div id="err" class="err">비밀번호가 올바르지 않습니다.</div>
    </div>
    <script>
        async function verifyPw() {{
            const p = document.getElementById('pw').value.trim();
            const err = document.getElementById('err');
            err.style.display = 'none';
            try {{
                const res = await fetch('/setup', {{
                    method: 'POST',
                    headers: {{'Content-Type': 'application/json'}},
                    body: JSON.stringify({{password: p}})
                }});
                const data = await res.json();
                if (data.status === 'success') {{
                    window.location.reload();
                }} else {{
                    err.innerText = data.message;
                    err.style.display = 'block';
                }}
            }} catch(e) {{
                err.innerText = '인증 중 오류가 발생했습니다.';
                err.style.display = 'block';
            }}
        }}
    </script>
</body>
</html>
"""
        return html

    secret = get_or_create_totp_secret()
    # QR Code compatible URL (ASCII only for label/issuer)
    otp_uri = f"otpauth://totp/LiveMaster:admin?secret={secret}&issuer=LiveMaster"
    
    html = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>🔒 라이브 마스터 OTP 초기 페어링</title>
    <style>
        body {{
            background: #0d0d0f;
            color: #f5f5f7;
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            display: flex;
            align-items: center;
            justify-content: center;
            min-height: 100vh;
            margin: 0;
        }}
        .card {{
            background: #16161a;
            border: 1px solid rgba(255,255,255,0.08);
            border-radius: 20px;
            padding: 40px 30px;
            text-align: center;
            box-shadow: 0 10px 30px rgba(0,0,0,0.5);
            max-width: 420px;
            width: 90%;
            box-sizing: border-box;
        }}
        h2 {{ color: #00ffcc; margin-top: 0; font-size: 22px; }}
        p {{ font-size: 14px; color: #8e8e93; line-height: 1.6; }}
        canvas {{ background: #fff; padding: 10px; border-radius: 10px; margin: 20px 0; }}
        .secret-label {{ font-size: 12px; color: #8e8e93; margin-top: 15px; margin-bottom: 5px; }}
        .secret {{
            background: rgba(255,255,255,0.05);
            padding: 12px;
            border-radius: 8px;
            font-family: monospace;
            font-size: 18px;
            letter-spacing: 2px;
            color: #ff9f0a;
            user-select: all;
            word-break: break-all;
            font-weight: bold;
        }}
        .btn {{
            background: #00ffcc;
            color: #000;
            border: none;
            padding: 14px 28px;
            font-weight: bold;
            border-radius: 8px;
            cursor: pointer;
            margin-top: 25px;
            text-decoration: none;
            display: inline-block;
            transition: opacity 0.2s;
        }}
        .btn:hover {{ opacity: 0.9; }}
    </style>
    <script src="https://cdnjs.cloudflare.com/ajax/libs/qrious/4.0.2/qrious.min.js"></script>
</head>
<body>
    <div class="card">
        <h2>🔒 모바일 OTP 페어링 타워</h2>
        <p>스마트폰의 <b>구글 OTP (Google Authenticator)</b> 앱을 실행하고,<br>우측 하단의 '+' 버튼을 눌러 아래 QR 코드를 스캔해 주세요.</p>
        <canvas id="qr"></canvas>
        <div class="secret-label">수동 등록을 위한 보안 키 (앱에 직접 입력 가능)</div>
        <div class="secret">{secret}</div>
        <a href="/login" class="btn">인증 로그인 화면으로 이동</a>
    </div>
    <script>
        new QRious({{
            element: document.getElementById('qr'),
            value: '{otp_uri}',
            size: 200
        }});
    </script>
</body>
</html>
"""
    return html

@app.route('/login', methods=['GET', 'POST'])
def serve_login():
    if request.method == 'GET' and session.get('authenticated'):
        if request.query_string:
            return redirect(url_for('serve_controller') + '?' + request.query_string.decode('utf-8'))
        return redirect(url_for('serve_controller'))
        
    if request.method == 'POST':
        try:
            data = request.get_json(silent=True) or request.form or {}
            p = data.get('password', '').strip()
            otp_code = data.get('otp', '').strip()
            
            # PW 검증
            if p == load_auth_config()['admin_password']:
                totp_secret = get_or_create_totp_secret()
                totp = pyotp.TOTP(totp_secret)
                # OTP 번호가 비어있거나 입력된 OTP가 올바른 경우 로그인 승인
                if not otp_code or totp.verify(otp_code, valid_window=1):
                    session['authenticated'] = True
                    return jsonify({'status': 'success'})
                else:
                    return jsonify({'status': 'error', 'message': '보안 OTP 번호가 일치하지 않습니다.'}), 400
            else:
                return jsonify({'status': 'error', 'message': '비밀번호가 잘못되었습니다.'}), 400
        except Exception as e:
            return jsonify({'status': 'error', 'message': str(e)}), 500
            
    return serve_html_file('login.html')

@app.route('/logout')
def serve_logout():
    session.pop('authenticated', None)
    return redirect(url_for('serve_login'))

@app.route('/')
def serve_root():
    return serve_html_file('overlay.html')

@app.route('/overlay')
@app.route('/overlay.html')
def serve_overlay():
    return serve_html_file('overlay.html')

@app.route('/slot')
@app.route('/slot.html')
def serve_slot():
    return serve_html_file('slot.html')

@app.route('/signature-display')
@app.route('/signature-display.html')
def serve_signature_display():
    return serve_html_file('signature_display.html')

@app.route('/alertbox')
@app.route('/alertbox.html')
def serve_alertbox():
    return serve_html_file('alertbox.html')

@app.route('/manual')
@app.route('/manual_send')
@app.route('/manual_send.html')
def serve_manual_send():
    return serve_html_file('manual_send.html')

@app.route('/streamdeck')
@app.route('/streamdeck.html')
def serve_streamdeck():
    return serve_html_file('streamdeck.html')

@app.route('/controller')
def serve_controller():
    # 1. 쿼리 매개변수로 명시적 모드가 지정된 경우 우선 처리
    mode = request.args.get('mode', '').lower()
    if mode == 'mobile':
        return serve_html_file('mobile.html')
    elif mode == 'desktop':
        return serve_html_file('controller.html')
        
    # 2. 자동으로 User-Agent 판별
    ua = request.headers.get('User-Agent', '').lower()
    mobile_keywords = ['mobile', 'android', 'iphone', 'ipad', 'ipod', 'webos', 'blackberry', 'opera mini', 'opera mobi', 'windows phone']
    is_mobile = any(kw in ua for kw in mobile_keywords)
    if is_mobile:
        return serve_html_file('mobile.html')
    return serve_html_file('controller.html')

@app.route('/mobile')
def serve_mobile():
    return serve_html_file('mobile.html')

@app.route('/admin')
@app.route('/admin.html')
def serve_admin():
    return serve_html_file('admin.html')

@app.route('/upload')
@app.route('/노래등록')
def serve_upload():
    return serve_html_file('upload.html')

@app.route('/<path:filename>')
def serve_dynamic_file(filename):
    if filename.startswith('api/'):
        return jsonify({"status": "error", "message": "API endpoint not found"}), 404
    for root in [BASE_DIR, BUNDLE_DIR]:
        if os.path.exists(os.path.join(root, filename)):
            return send_from_directory(root, filename)
    return jsonify({"error": "File not found"}), 404

# ==========================================
# 🛡️ 투네이션 후원 안전 접수 및 파서
# ==========================================
@app.route('/api/donation', methods=['POST'])
def receive_donation():
    try:
        new_don = request.json or {}
        amount = int(new_don.get('amount', 0))
        tx_id = new_don.get('tx_id')
        
        # 1. 음수(0원 미만) 후원 금액 차단 (0원 시그니처 후원 등 허용)
        if amount < 0:
            return jsonify({"status": "error", "message": "Invalid amount"}), 400
            
        # 2. tx_id 중복 검사로 중복 처리 차단
        if tx_id:
            try:
                with get_db_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute(db_query("SELECT id FROM donation_history WHERE tx_id = ?"), (tx_id,))
                    if cursor.fetchone():
                        return jsonify({"status": "success", "message": "Duplicate donation ignored."})
            except Exception as dbe:
                print(f"⚠️ [tx_id 중복 확인 오류] {dbe}")

        # 2-b. tx_id가 없는 재전송 대비: 이름+금액+메시지가 동일한 후원이
        #      아주 짧은 시간 안에 다시 오면 중복으로 간주해 무시한다(시그니처 이중 재생 방지).
        if not tx_id:
            dup_key = f"{(new_don.get('name') or '').strip()}|{amount}|{(new_don.get('message') or '').strip()}"
            if is_duplicate_donation(dup_key):
                print("⚠️ [내용 기반 중복 후원 무시] tx_id 없는 동일 후원이 짧은 시간에 재수신됨")
                return jsonify({"status": "success", "message": "Duplicate donation ignored (content)."})

        # 🎵 시그니처 매칭은 file_lock 밖에서 미리 끝낸다.
        # ⚠️ 이 호출은 Supabase로 나가는 HTTP라 느려질 수 있는데, 예전에는 락을 쥔 채 실행했다.
        #    그러면 후원 한 건이 처리되는 동안 점수 버튼·슬롯·리액션 넘기기 등
        #    락을 쓰는 모든 조작이 통째로 멈춰 방송 중 컨트롤러가 얼어붙었다.
        #    매칭은 state를 읽지 않으므로 락이 필요 없다.
        matched_sig = None
        if amount > 0:
            try:
                matched_sig = supabase_match_signature(amount)
            except Exception as e:
                print(f"⚠️ [자동 시그니처 매칭 오류] {e}")

        with file_lock:
            state = load_data()
            don_id = f"don_{int(time.time() * 1000)}"
            name = new_don.get('name', '익명')
            msg = new_don.get('message', '')
            
            parsed_name = name.strip()
            cleaned_msg = msg.strip()
            
            # 💡 [핵심] 메시지 내 콜론(:)을 감지하여 이름과 메시지를 분리해주는 오토 파서 (시그니처 신청 태그는 제외)
            cleaned_msg_for_split = cleaned_msg.replace('：', ':')
            if cleaned_msg_for_split and ':' in cleaned_msg_for_split and not cleaned_msg.startswith("[시그니처 신청:"):
                split_char = ':' if ':' in cleaned_msg else '：'
                parts = cleaned_msg.split(split_char, 1)
                potential_name = parts[0].strip()
                if 0 < len(potential_name) <= 15:
                    parsed_name = potential_name
                    cleaned_msg = parts[1].strip()
                    
            if parsed_name.endswith('님') and len(parsed_name) > 1:
                parsed_name = parsed_name[:-1]
                
            parsed_don_entry = {
                'id': don_id,
                'name': parsed_name,
                'amount': amount,
                'message': cleaned_msg,
                'time': time.strftime('%H:%M:%S')
            }
            state['pending_donations'].append(parsed_don_entry)
            state['latest_donation'] = {
                'name': parsed_name,
                'amount': amount,
                'message': cleaned_msg,
                'time': time.time()
            }
            state['reaction_mode'] = True
            
            # BJ 점수판 업데이트
            current_total = amount
            target_list_key = 'extra_bjs' if state.get('extra_game_active', False) else 'bjs'
            
            if target_list_key == 'extra_bjs' and not state.get('extra_bjs'):
                state['extra_bjs'] = [{"name": bj['name'], "score": 0, "contribution": 0} for bj in state.get('bjs', [])]
                
            # [비활성화] 닉네임 직접 매칭 자동 점수 가산 기능 해제 (모든 후원이 승인 대기함으로 모이도록 설정)
            # for bj in state.get(target_list_key, []):
            #     if bj['name'] == parsed_name:
            #         add_point = int(amount / 10000 + 0.5)
            #         bj['score'] += add_point
            #         bj['contribution'] = bj.get('contribution', 0) + add_point
            #         current_total = bj['score']
            #         break
            try:
                with get_db_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute(
                        db_query("INSERT INTO donation_history (timestamp, name, amount, current_total, message, source, tx_id) VALUES (?, ?, ?, ?, ?, ?, ?)"),
                        (time.strftime('%Y-%m-%d %H:%M:%S'), parsed_name, amount, current_total, cleaned_msg, "toonation", tx_id)
                    )
            except Exception as dbe:
                print(f"[장부 기록 오류] {dbe}")
                
            # 🎵 자동 시그니처 리액션 연동 (매칭은 위에서 락 밖에 끝냈고, 여기서는 큐에만 넣는다)
            if matched_sig:
                enqueue_signature(state, matched_sig, amount, parsed_name, cleaned_msg)
                print(f"  🎵 [자동 시그니처] 후원 {amount}원 → '{matched_sig.get('title')}' (#{matched_sig.get('id')}, {matched_sig.get('amount')}원) 큐 추가 완료")


            save_data(state, sync=True)
            broadcast_event('update', state)
            
            print("  🎯 [최종 처리 결과]")
            print(f"    ▶ 최종 분류된 이름  : {parsed_name}")
            print(f"    ▶ 최종 분류된 메시지: {cleaned_msg}")
            print("    ▶ 자동 승인 처리 여부: 🟡 클래식 수동 정산 모드 작동 (승인 대기함 적립)")
            print("======================================================================\n")
            
        return jsonify({'status': 'success', 'id': don_id})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

# ==========================================
# 📺 CORS 우회 유튜브 검색 API (SSL 무시)
# ==========================================
@app.route('/api/yt/search')
def yt_search():
    query = request.args.get('q', '')
    if not query:
        return jsonify([])
        
    instances = ['https://yewtu.be', 'https://invidious.flokinet.to', 'https://iv.melmac.space']
    ssl_ctx = ssl._create_unverified_context()
    
    for base in instances:
        try:
            encoded_query = urllib.parse.quote(query)
            url = f"{base}/api/v1/search?q={encoded_query}"
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            
            with urllib.request.urlopen(req, context=ssl_ctx, timeout=3) as response:
                data = json.loads(response.read().decode('utf-8'))
                results = []
                for item in data:
                    if item.get('type') == 'video':
                         length = item.get('lengthSeconds', 0)
                         mins = length // 60
                         secs = length % 60
                         duration_str = f"{mins}:{secs:02d}"
                         
                         video_id = item.get('videoId', '')
                         results.append({
                             'title': item.get('title', ''),
                             'videoId': video_id,
                             'author': item.get('author', ''),
                             'duration': duration_str,
                             'thumbnail': f"https://img.youtube.com/vi/{video_id}/mqdefault.jpg"
                         })
                return jsonify(results)
        except Exception as e:
            print(f"[YT Search Exception on {base}] {e}")
            continue
            
    return jsonify([])

@app.route('/api/data', methods=['GET', 'POST'])
def api_data():
    if request.method == 'POST':
        with file_lock:
            state = request.json or {}
            current_state = load_data()
            
            # [수정] 409 conflict로 인한 경고창(Alert) 발생을 원천 차단하기 위해 409 검증을 제거하고,
            # 마지막으로 전송된 상태를 기준으로 버전을 갱신하여 저장합니다. (Last-Write-Wins)
            client_version = state.get('version', 0)
            server_version = current_state.get('version', 1)
            
            state['version'] = max(client_version, server_version) + 1

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
        state = state.copy()
        state['server_time'] = int(time.time() * 1000)
        # 조종실 웹에 로그인 세션이 있을 경우 보안 API 토큰을 제공
        if session.get('authenticated'):
            state['api_token'] = load_auth_config()['session_secret']
    return jsonify(state)

@app.route('/api/roulette/winner', methods=['POST'])
def api_roulette_winner():
    try:
        req_data = request.json
        winner_name = req_data.get('name', '익명')
        with file_lock:
            state = load_data()
            if 'roulette' not in state:
                state['roulette'] = {
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
            state['roulette']['winner_name'] = winner_name
            state['roulette']['command'] = 'ended'
            state['roulette']['is_spinning'] = False
            state['roulette']['command_time'] = int(time.time() * 1000)
            state['roulette_enabled'] = False
            
            # 랭킹 로그에 기록 추가
            time_str = time.strftime('%H:%M:%S')
            if 'logs' not in state:
                state['logs'] = []
            state['logs'].insert(0, {
                'time': time_str,
                'name': f"🎡 룰렛 결과: {winner_name}",
                'val': 0
            })
            if len(state['logs']) > 200:
                state['logs'] = state['logs'][:200]
                
            save_data(state)
            broadcast_event('update', state)
        return jsonify({"status": "success"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/layout', methods=['GET', 'POST'])
def api_layout():
    if request.method == 'POST':
        with open(LAYOUT_FILE, 'w', encoding='utf-8') as f:
            json.dump(request.json, f, ensure_ascii=False, indent=4)
        broadcast_event('layout', request.json)
        return jsonify({"status": "success"})
    if os.path.exists(LAYOUT_FILE):
        with open(LAYOUT_FILE, 'r', encoding='utf-8') as f:
            return jsonify(json.load(f))
    return jsonify({})

# ==========================================
# 🎮 번외 게임 모드 제어 API
# ==========================================
@app.route('/api/extra_game/start', methods=['POST'])
def extra_game_start():
    try:
        with file_lock:
            state = load_data()
            state["extra_game_active"] = True
            
            # Initialize extra_bjs with all players from bjs, reset scores to 0
            state["extra_bjs"] = []
            for bj in state.get("bjs", []):
                state["extra_bjs"].append({
                    "name": bj["name"],
                    "score": 0,
                    "contribution": 0
                })
                
            save_data(state)
            broadcast_event('update', state)
        return jsonify({"status": "success"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/extra_game/end', methods=['POST'])
def extra_game_end():
    try:
        with file_lock:
            state = load_data()
            if not state.get("extra_game_active", False) or "extra_bjs" not in state:
                return jsonify({"status": "error", "message": "진행 중인 번외 게임이 없습니다."}), 400
                
            extra_scores = {bj["name"]: bj for bj in state.get("extra_bjs", [])}
            
            for bj in state.get("bjs", []):
                bj_name = bj["name"]
                if bj_name in extra_scores:
                    bj["score"] += extra_scores[bj_name]["score"]
                    bj["contribution"] = bj.get("contribution", 0) + extra_scores[bj_name].get("contribution", 0)
                    
            state["extra_game_active"] = False
            state["extra_bjs"] = []
            
            save_data(state)
            broadcast_event('update', state)
        return jsonify({"status": "success"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/extra_game/cancel', methods=['POST'])
def extra_game_cancel():
    try:
        with file_lock:
            state = load_data()
            state["extra_game_active"] = False
            state["extra_bjs"] = []
            
            save_data(state)
            broadcast_event('update', state)
        return jsonify({"status": "success"})
    except Exception as e:
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
        req_data = request.json
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
        req_data = request.json
        snap_id = req_data.get("id")
        
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(db_query("SELECT state_json FROM snapshots WHERE id = ?"), (snap_id,))
            row = cursor.fetchone()
            if not row:
                return jsonify({"status": "error", "message": "스냅샷을 찾을 수 없습니다."}), 404
            state_json = row[0]
            
        with file_lock:
            state = json.loads(state_json)
            save_data(state, sync=True)
            broadcast_event('update', state)
            
        return jsonify({"status": "success"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/snapshots/delete', methods=['POST'])
def delete_snapshot():
    try:
        req_data = request.json
        snap_id = req_data.get("id")
        
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
            'player_count': player_count,
            'history_count': history_count,
            'snapshot_count': snapshot_count,
            'archive_count': archive_count,
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
            try:
                with get_db_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute(db_query("""
                        INSERT INTO donation_archive
                            (archived_at, session_label, timestamp, name, amount, current_total, message, source, tx_id)
                        SELECT ?, ?, timestamp, name, amount, current_total, message, source, tx_id
                        FROM donation_history
                    """), (time.strftime('%Y-%m-%d %H:%M:%S'), session_label))
                    cursor.execute(db_query("SELECT COUNT(*) FROM donation_archive"))
                    print(f"  📚 [장부 영구 보관] 누적 {cursor.fetchone()[0]}건")
            except Exception as arch_e:
                # 보관에 실패하면 삭제를 진행하지 않는다 (기록 유실 방지)
                print(f"❌ [장부 보관 실패 - 방송 종료 중단] {arch_e}")
                return jsonify({"status": "error",
                                "message": f"장부 백업에 실패해 방송 종료를 중단했습니다: {arch_e}"}), 500

            # 1. Clear database tables (donation history, snapshots, players)
            with get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(db_query("DELETE FROM players"))
                cursor.execute(db_query("DELETE FROM donation_history"))
                cursor.execute(db_query("DELETE FROM snapshots"))
                # Delete kv_store keys that are NOT persistent configurations
                cursor.execute(
                    db_query("DELETE FROM kv_store WHERE key NOT IN (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"), 
                    ('theme', 'neon_speed', 'saved_colors', 'target_goal', 'account', 'effect_rules', 'screen_effect', 'ticker_enabled', 'ticker_speed', 'ticker_text', 'totp_secret')
                )
            
            # 초기화가 끝난 뒤에 백업 스냅샷을 넣어야 살아남는다 (되돌리기 지점)
            create_snapshot(pre_state, f"방송 종료 자동 백업 ({session_label})")

            # 2. Get current state from database (which will have only configurations preserved)
            state = load_data()
            
            # Reset memory state and set broadcast_active to False
            state['broadcast_active'] = False
            state['bjs'] = []
            state['bottom_fixed']['score'] = 0
            state['reaction_mode'] = False
            state['match_data'] = {"active": False, "players": [], "time_left_ms": 180000, "is_running": False}
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

            # ⚠️ is_initial=True 로 전체 키를 다시 쓴다.
            #    위에서 kv_store 행을 지웠는데 메모리 값은 그대로라, 변경분만 쓰는 평소 방식으로는
            #    "바뀐 게 없다"고 판단해 아무것도 복구되지 않는다. 그 상태로 서버가 재시작되면
            #    볼륨·슬롯 후보 같은 설정이 기본값으로 돌아가 버린다.
            save_data(state, is_initial=True, sync=True)
            broadcast_event('update', state)

        return jsonify({"status": "success", "message": "방송이 종료되고 오늘의 데이터가 리셋되었습니다."})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/server/start_broadcast', methods=['POST'])
def start_broadcast():
    try:
        global MEMORY_STATE
        req = request.json or {}
        names = req.get('names', [])
        if not names:
            return jsonify({"status": "error", "message": "최소 한 명 이상의 플레이어를 등록해야 합니다."}), 400
        if len(names) > 10:
            return jsonify({"status": "error", "message": "플레이어는 최대 10명까지 등록할 수 있습니다."}), 400
            
        with file_lock:
            # 0. ⚠️ 방송 시작도 장부를 지우므로, 지우기 전에 지난 기록을 영구 보관한다.
            session_label = time.strftime('%Y-%m-%d %H:%M:%S') + " 방송 시작 전"
            try:
                with get_db_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute(db_query("""
                        INSERT INTO donation_archive
                            (archived_at, session_label, timestamp, name, amount, current_total, message, source, tx_id)
                        SELECT ?, ?, timestamp, name, amount, current_total, message, source, tx_id
                        FROM donation_history
                    """), (time.strftime('%Y-%m-%d %H:%M:%S'), session_label))
            except Exception as arch_e:
                print(f"❌ [장부 보관 실패 - 방송 시작 중단] {arch_e}")
                return jsonify({"status": "error",
                                "message": f"장부 백업에 실패해 방송 시작을 중단했습니다: {arch_e}"}), 500

            # 1. Clear database tables (donation history, snapshots, players)
            with get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(db_query("DELETE FROM players"))
                cursor.execute(db_query("DELETE FROM donation_history"))
                cursor.execute(db_query("DELETE FROM snapshots"))
                # Delete kv_store keys that are NOT persistent configurations
                cursor.execute(
                    db_query("DELETE FROM kv_store WHERE key NOT IN (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"), 
                    ('theme', 'neon_speed', 'saved_colors', 'target_goal', 'account', 'effect_rules', 'screen_effect', 'ticker_enabled', 'ticker_speed', 'ticker_text', 'totp_secret')
                )
            
            # 2. Get current state from database (which will have only configurations preserved)
            state = load_data()
            
            # 3. Set broadcast_active to True and initialize players
            state['broadcast_active'] = True
            state['bjs'] = [{"name": name.strip(), "score": 0, "contribution": 0} for name in names if name.strip()]
            state['bottom_fixed']['score'] = 0
            state['reaction_mode'] = False
            state['match_data'] = {"active": False, "players": [], "time_left_ms": 180000, "is_running": False}
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

            # kv_store 행을 위에서 지웠으므로 전체 키를 다시 기록해야 설정이 살아남는다
            
            save_data(state, is_initial=True, sync=True)
            broadcast_event('update', state)
            
        return jsonify({"status": "success", "message": "방송이 활성화되었습니다."})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


# ==========================================
# 📋 수동 조작 이력 조회 API
# ==========================================
@app.route('/api/manual_logs', methods=['GET'])
def get_manual_logs():
    try:
        source_filter = request.args.get('source', 'all')  # all, mobile, toonation
        name_filter = request.args.get('name', '').strip()
        page = max(1, int(request.args.get('page', 1)))
        per_page = min(200, max(10, int(request.args.get('per_page', 50))))
        export_csv = request.args.get('export', '') == 'csv'
        
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            # Build WHERE clause
            conditions = []
            params = []
            if source_filter == 'mobile':
                conditions.append("source = " + ("$1" if IS_POSTGRES else "?"))
                params.append("mobile")
            elif source_filter == 'toonation':
                conditions.append("source = " + ("$1" if IS_POSTGRES else "?"))
                params.append("toonation")
            
            if name_filter:
                param_idx = len(params) + 1
                if IS_POSTGRES:
                    conditions.append(f"name LIKE ${param_idx}")
                else:
                    conditions.append("name LIKE ?")
                params.append(f"%{name_filter}%")
            
            where_clause = (" WHERE " + " AND ".join(conditions)) if conditions else ""
            
            # Get total count
            count_q = f"SELECT COUNT(*) FROM donation_history{where_clause}"
            if IS_POSTGRES:
                # Replace $N placeholders for count query
                pg_count_q = count_q
                for i in range(len(params)):
                    pg_count_q = pg_count_q.replace(f"${i+1}", "%s", 1)
                cursor.execute(pg_count_q, params)
            else:
                cursor.execute(count_q, params)
            total_count = cursor.fetchone()[0]
            
            # CSV Export mode
            if export_csv:
                data_q = f"SELECT id, timestamp, name, amount, current_total, message, source FROM donation_history{where_clause} ORDER BY id DESC"
                if IS_POSTGRES:
                    pg_data_q = data_q
                    for i in range(len(params)):
                        pg_data_q = pg_data_q.replace(f"${i+1}", "%s", 1)
                    cursor.execute(pg_data_q, params)
                else:
                    cursor.execute(data_q, params)
                rows = cursor.fetchall()
                
                import io, csv
                output = io.StringIO()
                output.write('\ufeff')  # BOM for Excel
                writer = csv.writer(output)
                writer.writerow(['ID', '시간', '이름', '변동량', '누적점수', '메시지', '출처'])
                for r in rows:
                    writer.writerow([r[0], r[1], r[2], r[3], r[4], r[5], r[6]])
                
                from flask import Response
                return Response(
                    output.getvalue(),
                    mimetype='text/csv',
                    headers={'Content-Disposition': f'attachment; filename=score_log_{time.strftime("%Y%m%d_%H%M%S")}.csv'}
                )
            
            # Paginated fetch
            offset = (page - 1) * per_page
            if IS_POSTGRES:
                param_idx_limit = len(params) + 1
                param_idx_offset = len(params) + 2
                data_q = f"SELECT id, timestamp, name, amount, current_total, message, source FROM donation_history{where_clause} ORDER BY id DESC LIMIT ${param_idx_limit} OFFSET ${param_idx_offset}"
                pg_data_q = data_q
                all_params = params + [per_page, offset]
                for i in range(len(all_params)):
                    pg_data_q = pg_data_q.replace(f"${i+1}", "%s", 1)
                cursor.execute(pg_data_q, all_params)
            else:
                data_q = f"SELECT id, timestamp, name, amount, current_total, message, source FROM donation_history{where_clause} ORDER BY id DESC LIMIT ? OFFSET ?"
                cursor.execute(data_q, params + [per_page, offset])
            
            rows = cursor.fetchall()
            logs = []
            for r in rows:
                logs.append({
                    'id': r[0], 'timestamp': r[1], 'name': r[2],
                    'amount': r[3], 'current_total': r[4],
                    'message': r[5], 'source': r[6]
                })
        
        total_pages = max(1, (total_count + per_page - 1) // per_page)
        return jsonify({
            'status': 'success',
            'logs': logs,
            'page': page,
            'per_page': per_page,
            'total_count': total_count,
            'total_pages': total_pages
        })
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

# ==========================================
# ⏪ 시간 여행 복원 API (오늘 지정 시간 기준)
# ==========================================
@app.route('/api/time_machine/restore_by_time', methods=['POST'])
def restore_by_time():
    try:
        req_data = request.json
        time_str = req_data.get('time', '').strip()
        if not time_str:
            return jsonify({'status': 'error', 'message': '이동할 시간을 입력해주세요.'}), 400
            
        today_str = time.strftime('%Y-%m-%d')
        target_ts = f"{today_str} {time_str}"
        if len(time_str.split(':')) == 2:
            target_ts += ':00'
            
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(db_query("""
                SELECT name, current_total 
                FROM donation_history 
                WHERE id IN (
                    SELECT MAX(id) 
                    FROM donation_history 
                    WHERE timestamp <= ? 
                    GROUP BY name
                )
            """), (target_ts,))
            history_rows = cursor.fetchall()
            
            if not history_rows:
                return jsonify({'status': 'error', 'message': f'[{target_ts}] 시점 또는 그 이전에 기록된 장부가 없습니다.'}), 404
                
            cursor.execute(db_query("SELECT key, value FROM kv_store WHERE key = 'target_goal'"))
            goal_row = cursor.fetchone()
            target_goal = json.loads(goal_row[1]) if goal_row else 50000
            
        import copy
        current_state = load_data()
        restored_state = copy.deepcopy(current_state)
        restored_state['target_goal'] = target_goal
        restored_state['bjs'] = []
        
        for name, score in history_rows:
            restored_state['bjs'].append({
                'name': name,
                'score': score,
                'contribution': score
            })
            
        restored_state['bjs'].sort(key=lambda x: x['contribution'], reverse=True)
        
        global MEMORY_STATE
        MEMORY_STATE = restored_state
        save_data(restored_state, sync=True)
        broadcast_event('update', restored_state)
        
        return jsonify({
            'status': 'success',
            'message': f'⏳ [시간여행 성공]\n오늘 {time_str} 시점의 플레이어 상태로 안전하게 원복되었습니다!'
        })
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

# ==========================================
# 🎛️ 스트림덱 전용 원터치 제어 API (GET 방식)
# ==========================================
@app.route('/api/streamdeck/save', methods=['GET'])
def sd_save():
    try:
        state = load_data()
        timestamp = time.strftime('%Y-%m-%d %H:%M:%S')
        label = "스트림덱 수동 백업"
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                db_query("INSERT INTO snapshots (timestamp, state_json, summary) VALUES (?, ?, ?)"),
                (timestamp, json.dumps(state, ensure_ascii=False), label)
            )
        print("  💾 [스트림덱 명령] 수동 스냅샷 세이브포인트 저장 완료!")
        return jsonify({"status": "success", "message": "스냅샷 저장 완료"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/streamdeck/neon', methods=['GET'])
def sd_neon():
    try:
        color = request.args.get('color', 'RAINBOW').upper()
        # 6자리 16진수 색상 코드인 경우 #을 자동으로 붙여줌
        if len(color) == 6 and all(c in '0123456789ABCDEF' for c in color):
            color = '#' + color
            
        with file_lock:
            state = load_data()
            state['effect_trigger'] = {
                'time': int(time.time() * 1000),
                'color': color
            }
            if color != 'OFF':
                state['reaction_mode'] = True
            else:
                state['reaction_mode'] = False
                
            save_data(state)
            broadcast_event('update', state)
        print(f"  💡 [스트림덱 명령] 네온 이펙트 조명 전환: {color}")
        return jsonify({"status": "success", "color": color})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

# ==========================================
# 🎵 커스텀 리액션 플랫폼 API (영구 보존형)
# ==========================================
import uuid

@app.route('/uploads/<file_id>', methods=['GET'])
def get_reaction_file(file_id):
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(db_query("SELECT filename, content_type, file_data FROM reaction_files WHERE id = ?"), (file_id,))
            row = cursor.fetchone()
            if not row:
                return jsonify({"status": "error", "message": "File not found"}), 404
            
            filename, content_type, file_data = row
            data_bytes = bytes(file_data)
            
            import os
            from flask import send_file
            
            # Save file to a local cache directory to serve as a real static file.
            # This perfectly resolves HTML5 audio Range requests and buffering stream aborts.
            cache_dir = os.path.join(app.root_path, 'media_cache')
            os.makedirs(cache_dir, exist_ok=True)
            cache_path = os.path.join(cache_dir, file_id)
            
            if not os.path.exists(cache_path):
                with open(cache_path, 'wb') as f:
                    f.write(data_bytes)
            
            response = send_file(
                cache_path,
                mimetype=content_type,
                as_attachment=False,
                download_name=filename,
                conditional=True
            )
            response.headers.set('Cache-Control', 'public, max-age=31536000')
            return response
    except Exception as e:
        print(f"Error serving reaction file {file_id}: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/reaction/list', methods=['GET'])
def get_reactions_list():
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(db_query("SELECT id, title, amount, audio_file_id, image_file_id FROM reaction_items ORDER BY id ASC"))
            rows = cursor.fetchall()
            reactions = []
            for r in rows:
                reactions.append({
                    "id": r[0],
                    "title": r[1],
                    "amount": r[2],
                    "audio_url": f"/uploads/{r[3]}" if r[3] else "",
                    "image_url": f"/uploads/{r[4]}" if r[4] else ""
                })
            return jsonify(reactions)
    except Exception as e:
        print(f"Error listing reactions: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/reaction/add', methods=['POST'])
def add_reaction():
    try:
        title = request.form.get('title', '').strip()
        amount = int(request.form.get('amount', 0))
        
        if not title:
            return jsonify({"status": "error", "message": "제목을 입력해주세요."}), 400
            
        audio_file = request.files.get('audio')
        image_file = request.files.get('image')
        
        audio_file_id = None
        image_file_id = None
        
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            if audio_file and audio_file.filename:
                audio_file_id = f"aud_{uuid.uuid4().hex}"
                audio_data = audio_file.read()
                cursor.execute(
                    db_query("INSERT INTO reaction_files (id, filename, content_type, file_data) VALUES (?, ?, ?, ?)"),
                    (audio_file_id, audio_file.filename, audio_file.content_type, psycopg2.Binary(audio_data) if IS_POSTGRES else audio_data)
                )
                
            if image_file and image_file.filename:
                image_file_id = f"img_{uuid.uuid4().hex}"
                image_data = image_file.read()
                cursor.execute(
                    db_query("INSERT INTO reaction_files (id, filename, content_type, file_data) VALUES (?, ?, ?, ?)"),
                    (image_file_id, image_file.filename, image_file.content_type, psycopg2.Binary(image_data) if IS_POSTGRES else image_data)
                )
                
            cursor.execute(
                db_query("INSERT INTO reaction_items (title, amount, audio_file_id, image_file_id) VALUES (?, ?, ?, ?)"),
                (title, amount, audio_file_id, image_file_id)
            )
            conn.commit()
            
        return jsonify({"status": "success", "message": "리액션 곡 등록 완료!"})
    except Exception as e:
        print(f"Error adding reaction: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/reaction/delete/<int:item_id>', methods=['POST', 'DELETE'])
def delete_reaction(item_id):
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(db_query("SELECT audio_file_id, image_file_id FROM reaction_items WHERE id = ?"), (item_id,))
            row = cursor.fetchone()
            if not row:
                return jsonify({"status": "error", "message": "Reaction item not found"}), 404
                
            audio_file_id, image_file_id = row
            
            cursor.execute(db_query("DELETE FROM reaction_items WHERE id = ?"), (item_id,))
            
            if audio_file_id:
                cursor.execute(db_query("DELETE FROM reaction_files WHERE id = ?"), (audio_file_id,))
            if image_file_id:
                cursor.execute(db_query("DELETE FROM reaction_files WHERE id = ?"), (image_file_id,))
                
            conn.commit()
            
        return jsonify({"status": "success", "message": "리액션 곡 삭제 완료!"})
    except Exception as e:
        print(f"Error deleting reaction: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/reaction/play/<int:item_id>', methods=['POST'])
def play_reaction(item_id):
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(db_query("SELECT title, audio_file_id, image_file_id FROM reaction_items WHERE id = ?"), (item_id,))
            row = cursor.fetchone()
            if not row:
                return jsonify({"status": "error", "message": "Reaction item not found"}), 404
                
            title, audio_file_id, image_file_id = row
            audio_url = f"/uploads/{audio_file_id}" if audio_file_id else ""
            image_url = f"/uploads/{image_file_id}" if image_file_id else ""
            
            with file_lock:
                state = load_data()
                reaction_uuid = f"rq_{uuid.uuid4().hex}"
                state['reaction_queue'].append({
                    "id": reaction_uuid,
                    "item_id": item_id,
                    "title": title,
                    "audio_url": audio_url,
                    "image_url": image_url,
                    "donator": "수동송출",
                    "message": ""
                })
                state['reaction_mode'] = True
                save_data(state)
                broadcast_event('update', state)
                
        return jsonify({"status": "success", "message": "방송 송출 완료!"})
    except Exception as e:
        print(f"Error playing reaction: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/reaction/next', methods=['POST'])
def next_reaction():
    try:
        data = request.get_json(silent=True) or {}
        pop_id = data.get('id')
        
        with file_lock:
            state = load_data()
            queue = state.get('reaction_queue', [])
            
            if queue:
                # ID가 지정된 경우: 첫 번째 아이템의 ID가 일치할 때만 pop (이중 pop 방지)
                # ID가 없는 경우: 기존 방식대로 무조건 pop (하위 호환)
                if not pop_id or queue[0].get('id') == pop_id:
                    queue.pop(0)
                
            if not queue:
                state['reaction_mode'] = False
                
            save_data(state)
            broadcast_event('update', state)
        return jsonify({"status": "success", "message": "Popped reaction"})
    except Exception as e:
        print(f"Error in next_reaction: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/reaction/stop', methods=['POST'])
def stop_reaction():
    try:
        with file_lock:
            state = load_data()
            state['reaction_queue'] = []
            state['reaction_mode'] = False
            save_data(state)
            broadcast_event('update', state)
            broadcast_event('reaction_stop', {})
        return jsonify({"status": "success", "message": "All reactions stopped"})
    except Exception as e:
        print(f"Error in stop_reaction: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/slot/spin', methods=['POST'])
def api_slot_spin():
    try:
        data = request.json or {}
        winner = data.get('winner')
        candidates = data.get('candidates', [])

        if not winner:
            # winner 미지정 시: 서버가 무작위 선택.
            # 이번 방송용으로 고른 후보(slot_pool)가 있으면 그 안에서만 뽑는다.
            try:
                sigs = supabase_list_signatures()
            except Exception as e:
                return jsonify({"status": "error", "message": f"시그니처 조회 실패: {e}"}), 500
            if not sigs:
                return jsonify({"status": "error", "message": "등록된 시그니처가 없습니다."}), 400

            pool_ids = load_data().get('slot_pool') or []
            if pool_ids:
                pool_set = {int(i) for i in pool_ids}
                filtered = [s for s in sigs if s.get('id') in pool_set]
                if filtered:
                    sigs = filtered
                else:
                    print("⚠️ [슬롯] 선택된 후보가 목록에 없어 전체에서 뽑습니다.")

            import random
            winner = random.choice(sigs)
            candidates = sigs

        # 릴이 도는 동안 슬롯 위젯이 확실히 보이도록 켠다.
        # (오버레이는 매 업데이트마다 slot_enabled로 표시를 다시 칠하므로 상태로 켜야 한다)
        with file_lock:
            state = load_data()
            state['slot_enabled'] = True
            save_data(state)
            broadcast_event('update', state)

        broadcast_event('slot_spin', {
            "type": "slot_spin",
            "event": "slot_spin",
            "winner": winner,
            "candidates": candidates
        })

        # 당첨 발표(약 3.3초) 뒤에 슬롯을 끄고 시그니처를 리액션 큐에 넣는다.
        # 큐를 태우면 reaction_mode가 켜지고, 재생이 끝나면 큐가 비면서 자동으로 꺼진다.
        # 오버레이는 비인증이라 스스로 재생 API를 부를 수 없으므로 서버가 예약한다.
        threading.Timer(SLOT_RESULT_DELAY_SEC, _slot_finish, args=(winner,)).start()

        return jsonify({"status": "success", "winner": winner})
    except Exception as e:
        print(f"Error spinning slot: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/reaction/queue/remove/<string:rq_id>', methods=['POST'])
def remove_from_queue(rq_id):
    try:
        with file_lock:
            state = load_data()
            queue = state.get('reaction_queue', [])
            if queue:
                is_currently_playing = (queue[0]['id'] == rq_id)
                state['reaction_queue'] = [item for item in queue if item['id'] != rq_id]
                
                if is_currently_playing:
                    broadcast_event('reaction_stop', {'id': rq_id})
                    
                if not state['reaction_queue']:
                    state['reaction_mode'] = False
                    
                save_data(state)
                broadcast_event('update', state)
        return jsonify({"status": "success", "message": "Removed from queue"})
    except Exception as e:
        print(f"Error in remove_from_queue: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

# ==========================================
# 🖥️ GUI 관리자 및 로그인 창
# ==========================================
def start_self_ping():
    import urllib.request
    import threading
    import time
    
    url = os.environ.get('RENDER_EXTERNAL_URL')
    if not url:
        return
        
    def ping_loop():
        # 즉시 초기화 로그 출력
        print(f"⏰ [Self-Ping] Daemon initialized for: {url}", flush=True)
        # 서버 시작 후 첫 30초 대기
        time.sleep(30)
        print(f"⏰ [Self-Ping] Starting self-ping loop...", flush=True)
        while True:
            try:
                req = urllib.request.Request(
                    url,
                    headers={'User-Agent': 'LiveMaster-KeepAwake/1.0'}
                )
                with urllib.request.urlopen(req, timeout=15) as response:
                    print(f"⏰ [Self-Ping] Ping sent successfully, response code: {response.getcode()}", flush=True)
            except Exception as e:
                print(f"⚠️ [Self-Ping] Ping failed: {e}", flush=True)
            time.sleep(600)  # 10분마다 실행 (Render 무료 비활성화 임계치인 15분보다 짧음)
            
    ping_thread = threading.Thread(target=ping_loop, daemon=True)
    ping_thread.start()

def run_flask():
    port = int(os.environ.get('PORT', 5000))
    start_self_ping()
    app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)

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
        if p == '0508':
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
    
    login_win.protocol('WM_DELETE_WINDOW', on_closing_exit if 'on_closing_exit' in globals() else on_login_closing)
    login_win.mainloop()
    
    return login_success[0]

def open_link(url):
    webbrowser.open(url)

def on_closing():
    if messagebox.askokcancel('서버 종료', '방송 서버를 완전히 종료하시겠습니까?\n(정산 기능 및 오버레이 송출이 중단됩니다)'):
        root.destroy()
        sys.exit(0)

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
            
            # 🔑 OTP 보안 등록 정보 추가
            otp_sec = get_or_create_totp_secret()
            lbl_otp = tk.Label(root, text='🔑 모바일 OTP 보안키: ' + otp_sec, fg='#ff9f0a', bg='#111113', font=('Consolas', 11, 'bold'))
            lbl_otp.pack(pady=5)
            
            lbl_otp_info = tk.Label(root, text=f'* 최초 등록 방법: 스마트폰 구글 OTP 앱에서 위 키를 입력하거나,\n서버 PC 브라우저로 http://localhost:{port}/setup 에 접속해 QR 코드를 스캔하세요.', fg='#8e8e93', bg='#111113', font=('Malgun Gothic', 8), justify='center')
            lbl_otp_info.pack(pady=5)
            
            frame_btns = tk.Frame(root, bg='#111113')
            frame_btns.pack(pady=20)
            
            btn_ctrl = tk.Button(frame_btns, text='💻 제어 센터 (조종실)', command=lambda: open_link(f'http://localhost:{port}/controller'), fg='#000000', bg='#00ffcc', activebackground='#00cca3', font=('Malgun Gothic', 10, 'bold'), width=18, height=2, relief='flat')
            btn_ctrl.pack(side=tk.LEFT, padx=10)
            
            btn_ovr = tk.Button(frame_btns, text='🎬 송출용 오버레이', command=lambda: open_link(f'http://localhost:{port}/overlay'), fg='#ffffff', bg='#333336', activebackground='#444448', font=('Malgun Gothic', 10, 'bold'), width=18, height=2, relief='flat')
            btn_ovr.pack(side=tk.LEFT, padx=10)
            
            root.protocol('WM_DELETE_WINDOW', on_closing)
            root.mainloop()
