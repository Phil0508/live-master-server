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

@contextmanager
def get_db_connection():
    if IS_POSTGRES:
        if psycopg2 is None:
            raise ImportError("psycopg2 is not installed but DATABASE_URL is set.")
        conn = psycopg2.connect(DATABASE_URL)
    else:
        conn = sqlite3.connect(DB_FILE)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
from flask import Flask, jsonify, request, send_from_directory, redirect, url_for, session
from flask_cors import CORS
try:
    import tkinter as tk
    from tkinter import messagebox
except ImportError:
    tk = None
    messagebox = None
import webbrowser

# ==========================================
# 🤫 서버 로그 제어
# ==========================================
log = logging.getLogger('werkzeug')
log.setLevel(logging.ERROR)
log.disabled = True 

app = Flask(__name__)
app.secret_key = "isacbin_master_key_0508"
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
        '/api/stream',
        '/api/donation',
        '/api/streamdeck/neon',
        '/api/streamdeck/save',
        '/setup'
    ]
    
    if path in exempt_routes:
        return
        
    # 비인증 사용자 제약
    if not session.get('authenticated'):
        if path.startswith('/api/'):
            return jsonify({'status': 'error', 'message': 'Unauthorized'}), 401
        return redirect(url_for('serve_login'))

# 📡 실시간 SSE 클라이언트 관리 시스템
sse_clients = []
sse_lock = threading.Lock()

def broadcast_event(event_name, data):
    with sse_lock:
        message = f"event: {event_name}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"
        for client_q in sse_clients:
            try:
                client_q.put_nowait(message)
            except queue.Full:
                pass

if getattr(sys, 'frozen', False):
    BASE_DIR = os.path.dirname(sys.executable)
    BUNDLE_DIR = getattr(sys, '_MEIPASS', BASE_DIR)
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    BUNDLE_DIR = BASE_DIR

# 📂 JSON 대신 튼튼한 DB 파일 사용
DB_FILE = os.path.join(BASE_DIR, 'live_master.db')
LAYOUT_FILE = os.path.join(BASE_DIR, 'layout.json')
AUTH_CONFIG_FILE = os.path.join(BASE_DIR, 'auth_config.json')

def get_or_create_totp_secret():
    if os.path.exists(AUTH_CONFIG_FILE):
        try:
            with open(AUTH_CONFIG_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                secret = data.get('totp_secret')
                if secret:
                    return secret
        except Exception as e:
            print(f"Error reading auth config: {e}")
            
    # Generate new secret
    secret = pyotp.random_base32()
    try:
        with open(AUTH_CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump({'totp_secret': secret}, f, indent=4)
    except Exception as e:
        print(f"Error writing auth config: {e}")
    return secret

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
                    source TEXT
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
                    source TEXT
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
        
        # 💡 [스키마 마이그레이션 패치] 기존 snapshots 테이블에 summary 컬럼이 없을 경우를 대비한 동적 추가
        try:
            cursor.execute("ALTER TABLE snapshots ADD COLUMN summary TEXT")
        except Exception:
            pass # 이미 컬럼이 존재하면 무시

def load_data():
    global MEMORY_STATE
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
        kv_data, bjs = {}, []

    if not kv_data and not bjs:
        MEMORY_STATE = DEFAULT_STATE.copy()
        save_data(MEMORY_STATE, is_initial=True)
        return MEMORY_STATE

    state = {}
    for key, default_val in DEFAULT_STATE.items():
        if key == "bjs": 
            state["bjs"] = bjs
        elif key in kv_data: 
            state[key] = kv_data[key]
        else: 
            state[key] = default_val
    
    MEMORY_STATE = state
    return MEMORY_STATE

def save_data(new_data, is_initial=False):
    global MEMORY_STATE
    old_data = MEMORY_STATE if MEMORY_STATE else DEFAULT_STATE
    
    if not is_initial:
        old_scores = {p["name"]: p["score"] for p in old_data.get("bjs", [])}
        try:
            with get_db_connection() as conn:
                cursor = conn.cursor()
                for new_p in new_data.get("bjs", []):
                    p_name = new_p["name"]
                    p_score = new_p["score"]
                    o_score = old_scores.get(p_name, 0)
                    diff = p_score - o_score
                    
                    if diff != 0:
                        cursor.execute(
                            db_query("INSERT INTO donation_history (timestamp, name, amount, current_total, message, source) VALUES (?, ?, ?, ?, ?, ?)"),
                            (time.strftime('%Y-%m-%d %H:%M:%S'), p_name, diff, p_score, "수동 점수 조작", "mobile")
                        )
        except Exception as e:
            print(f"⚠️ [수동조작 영수증 발급 오류] {e}")

    MEMORY_STATE = new_data

    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(db_query("DELETE FROM players"))
            for bj in new_data.get("bjs", []):
                cursor.execute(db_query("INSERT INTO players (name, score, contribution) VALUES (?, ?, ?)"), (bj["name"], bj["score"], bj.get("contribution", 0)))
            
            for key, value in new_data.items():
                if key != "bjs":
                    if IS_POSTGRES:
                        cursor.execute(
                            "INSERT INTO kv_store (key, value) VALUES (%s, %s) ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value",
                            (key, json.dumps(value, ensure_ascii=False))
                        )
                    else:
                        cursor.execute(
                            "INSERT OR REPLACE INTO kv_store (key, value) VALUES (?, ?)",
                            (key, json.dumps(value, ensure_ascii=False))
                        )
    except Exception as e:
        print(f"❌ [DB 전광판 저장 실패] {e}")

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
                
    return app.response_class(event_generator(), mimetype='text/event-stream')

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
                        
            save_data(state)
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
            if p == '0508':
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
    if request.method == 'POST':
        try:
            data = request.get_json()
            p = data.get('password', '').strip()
            otp_code = data.get('otp', '').strip()
            
            # PW 검증
            if p == '0508':
                # TOTP OTP 검증
                totp_secret = get_or_create_totp_secret()
                totp = pyotp.TOTP(totp_secret)
                if totp.verify(otp_code, valid_window=1): # Allow 30 seconds clock drift
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

@app.route('/streamdeck')
@app.route('/streamdeck.html')
def serve_streamdeck():
    return serve_html_file('streamdeck.html')

@app.route('/controller')
def serve_controller():
    return serve_html_file('controller.html')

@app.route('/mobile')
def serve_mobile():
    return serve_html_file('mobile.html')

@app.route('/admin')
@app.route('/admin.html')
def serve_admin():
    return serve_html_file('admin.html')



@app.route('/<path:filename>')
def serve_dynamic_file(filename):
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
        new_don = request.json
        with file_lock:
            state = load_data()
            don_id = f"don_{int(time.time() * 1000)}"
            amount = int(new_don.get('amount', 0))
            name = new_don.get('name', '익명')
            msg = new_don.get('message', '')
            
            parsed_name = name.strip()
            cleaned_msg = msg.strip()
            
            # 💡 [핵심] 메시지 내 콜론(:)을 감지하여 이름과 메시지를 분리해주는 오토 파서
            cleaned_msg_for_split = cleaned_msg.replace('：', ':')
            if cleaned_msg_for_split and ':' in cleaned_msg_for_split:
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
                
            for bj in state.get(target_list_key, []):
                if bj['name'] == parsed_name:
                    bj['score'] += amount
                    bj['contribution'] = bj.get('contribution', 0) + amount
                    current_total = bj['score']
                    break
                    
            try:
                with get_db_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute(
                        db_query("INSERT INTO donation_history (timestamp, name, amount, current_total, message, source) VALUES (?, ?, ?, ?, ?, ?)"),
                        (time.strftime('%Y-%m-%d %H:%M:%S'), parsed_name, amount, current_total, cleaned_msg, "toonation")
                    )
            except Exception as dbe:
                print(f"[장부 기록 오류] {dbe}")
                
            save_data(state)
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
            state = request.json
            save_data(state)
            broadcast_event('update', state)
        return jsonify({"status": "success"})
    return jsonify(load_data())

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
            save_data(state)
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
            'player_count': player_count,
            'history_count': history_count,
            'snapshot_count': snapshot_count,
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
            
        MEMORY_STATE = DEFAULT_STATE.copy()
        save_data(MEMORY_STATE, is_initial=True)
        broadcast_event('update', MEMORY_STATE)
        return jsonify({"status": "success", "message": "데이터베이스가 성공적으로 완전히 리셋되었습니다."})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

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
            
        restored_state = DEFAULT_STATE.copy()
        restored_state['target_goal'] = target_goal
        
        for name, score in history_rows:
            restored_state['bjs'].append({
                'name': name,
                'score': score,
                'contribution': score
            })
            
        restored_state['bjs'].sort(key=lambda x: x['contribution'], reverse=True)
        
        global MEMORY_STATE
        MEMORY_STATE = restored_state
        save_data(restored_state)
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
# 🖥️ GUI 관리자 및 로그인 창
# ==========================================
def run_flask():
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)

def has_gui_support():
    if os.environ.get('DATABASE_URL'):
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
