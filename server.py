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
import re       # 후원 메시지에서 별명 후보 토막내기
import random   # 시그게임 카드 배치·섞기, 슬롯 당첨 뽑기
import math     # 시그게임 판을 정사각형에 가깝게 잡을 때
import threading
import uuid
import logging
import pyotp
import secrets

import time
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

# OTP 를 반드시 입력하게 할지. 기본은 꺼짐(=빈칸이면 통과) — 지금까지의 동작이다.
# ⚠️ 켜기 전에 반드시 OTP 앱이나 마스터 코드로 로그인이 되는지 먼저 확인할 것.
#    확인 없이 켜면 방송 직전에 조종실에 못 들어가는 사고가 난다.
# ⚠️ load_auth_config() 가 이 값을 읽고, 그 함수는 모듈이 로딩되는 도중에도 불린다
#    (app.secret_key 설정). 그래서 정의는 반드시 load_auth_config 보다 위에 있어야 한다.
REQUIRE_OTP = (os.environ.get('REQUIRE_OTP') or '').strip().lower() in ('1', 'on', 'true', 'yes')


def load_auth_config():
    config = {
        'admin_password': '0508',
        'session_secret': WEAK_DEFAULT_SECRET,
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
        save_auth_config(config)   # ⚠️ totp_secret 만 저장된다(save_auth_config 참고)

    global AUTH_POSTURE_WARNED
    if not AUTH_POSTURE_WARNED:
        AUTH_POSTURE_WARNED = True
        gripes = []
        if config['admin_password'] == '0508':
            gripes.append("조종실 비밀번호가 공개된 기본값 '0508' 입니다. ADMIN_PASSWORD 를 넣어주세요.")
        master = (os.environ.get('OTP_MASTER_CODE') or '').strip()
        if master and len(master) < 8:
            gripes.append(f"OTP 마스터 코드가 {len(master)}자로 짧습니다. 두 번째 자물쇠가 사실상 없는 것과 같습니다.")
        if not REQUIRE_OTP:
            gripes.append("OTP 를 비워두면 통과합니다. 잠그려면 REQUIRE_OTP=1 을 넣으세요.")
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

# 저장하는 것은 totp_secret 하나뿐이다.
# ⚠️ 예전에는 config 를 통째로 썼다. 그러면 환경변수로 넣은 실제 운영
#    비밀번호(ADMIN_PASSWORD)와 관리자 키(SESSION_SECRET)가 auth_config.json 에
#    평문으로 적힌다. 그 파일은 저장소에 추적되고 있어서, 무심코 커밋하면
#    공개 저장소에 그대로 올라간다. 환경변수는 환경변수로만 두고 파일에 옮기지 않는다.
_AUTH_PERSIST_KEYS = ('totp_secret',)


def save_auth_config(config):
    try:
        keep = {k: config[k] for k in _AUTH_PERSIST_KEYS if config.get(k)}
        with open(AUTH_CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(keep, f, indent=4)
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

# ==========================================
# 🤖 NVIDIA NIM (AI 기입 검증 도우미)
#   후원 메시지를 읽고 "누구를 지목한 후원인지" 추정해, 운영자의 배정 실수를 잡아준다.
#   ⚠️ 절대 자동으로 점수를 바꾸지 않는다. 추천/경고만 제공하는 서포트 전용 기능이다.
# ==========================================
def load_nvidia_key():
    key = (os.environ.get('NVIDIA_API_KEY') or '').strip()
    if not key:
        cred_path = os.path.join(BASE_DIR, 'NVIDIA_CREDENTIALS.txt')  # git 제외 파일
        if os.path.exists(cred_path):
            try:
                with open(cred_path, 'r', encoding='utf-8') as f:
                    for line in f:
                        line = line.strip()
                        if line.startswith('#') or '=' not in line:
                            continue
                        k, v = line.split('=', 1)
                        if k.strip() == 'NVIDIA_API_KEY':
                            key = v.split('#')[0].strip()
                            break
            except Exception as e:
                print(f"[NVIDIA 키 읽기 오류] {e}")
    return key

NVIDIA_API_KEY = load_nvidia_key()
NIM_URL = "https://integrate.api.nvidia.com/v1/chat/completions"

# ⚠️ 모델 이름은 환경변수로 바꿀 수 있게 둔다.
#    2026-08-26 에 쓰던 모델 둘이 같은 날 서비스 종료(410)돼 AI 기능이 방송 중에 통째로
#    멈췄다. 코드에 박혀 있으면 그때마다 고쳐서 배포해야 한다 — 방송 중에는 못 할 일이다.
#    서버 설정(NIM_MODEL / NIM_CHAT_MODEL)만 바꾸고 재시작하면 넘어갈 수 있게 한다.
NIM_MODEL = (os.environ.get('NIM_MODEL') or "nvidia/nemotron-3-nano-30b-a3b").strip()
NIM_CHAT_MODEL = (os.environ.get('NIM_CHAT_MODEL') or "nvidia/nemotron-3-super-120b-a12b").strip()

# nemotron 3 계열은 생각을 먼저 늘어놓고 답한다. 기입검증은 JSON 한 줄만 필요하고
# 후원이 들어온 순간 바로 답해야 하므로 추론을 끈다.
#   실측(정답 4/4 · JSON 4/4): 추론 켠 채 1.10초 → 끄면 0.26초.
#   (예전 모델은 0.7초였으니 더 빨라졌다)
NIM_NO_THINK = {"chat_template_kwargs": {"thinking": False}}
NIM_CHAT_PREFIX = ""  # 채팅은 추론을 켜 둔다 — 설명이 필요한 자리라 그게 낫다.

# 🔁 붐빌 때 넘어갈 예비 모델.
#    503 은 고장이 아니라 "그 모델이 지금 몰렸다" 는 뜻이다. 몇 분 뒤면 풀리지만
#    방송 중에 몇 분은 길다. 한쪽이 막히면 다른 쪽으로 넘어가 AI 가 통째로 멈추지 않게 한다.
#    (실측: 같은 모델이 어떤 때는 6/6 되고 어떤 때는 overloaded 를 뱉는다. 큰 모델일수록 잦다)
NIM_MODEL_BACKUP = (os.environ.get('NIM_MODEL_BACKUP')
                    or "nvidia/nemotron-3-super-120b-a12b").strip()
NIM_CHAT_BACKUP = (os.environ.get('NIM_CHAT_BACKUP')
                   or "nvidia/nemotron-3-nano-30b-a3b").strip()

# 다시 해보면 될 만한 응답. 410(모델이 없어짐)·401(키)은 다시 해도 같으므로 넣지 않는다.
NIM_RETRYABLE = (429, 500, 502, 503, 504)


def nim_post(models, body, timeout):
    """모델을 차례로 시도한다. 붐비면(503 등) 다음 모델로 넘어간다.

       돌려주는 값: (응답 or None, 마지막 상태코드, 실제로 답한 모델)
    """
    last = 0
    tried = [m for m in models if m]
    for i, m in enumerate(tried):
        one = dict(body)
        one["model"] = m
        try:
            r = requests.post(NIM_URL, headers={"Authorization": f"Bearer {NVIDIA_API_KEY}"},
                              json=one, timeout=timeout)
        except Exception:
            last = 0
            continue
        if r.status_code == 200:
            if i > 0:
                print("🔁 [AI 예비 모델] %s 이(가) 막혀 %s 로 넘어갔습니다."
                      % (tried[0], m), flush=True)
            return r, 200, m
        last = r.status_code
        if r.status_code not in NIM_RETRYABLE:
            return r, r.status_code, m      # 다시 해도 같은 오류 — 그대로 알린다
        more = " — 예비 모델로 넘어갑니다" if i + 1 < len(tried) else ""
        print("⚠️ [AI 붐빔] %s 응답 %s%s" % (m, r.status_code, more), flush=True)
    return None, last, (tried[-1] if tried else "")

# 분당 호출 한도. 넘으면 검증을 조용히 건너뛴다.
# 35 로 뒀을 때 부하 테스트에서 45건을 밀어넣으니 우리 리미터는 11건만 막았고
# 1건은 NVIDIA 쪽에서 그대로 429 를 맞았다. 즉 35 는 실제 허용치에 붙어 있었다.
NIM_RATE_LIMIT = 30
_nim_calls = []                 # 최근 호출 시각(초) 슬라이딩 윈도우
_nim_lock = threading.Lock()

def _nim_allowed():
    """분당 한도 안이면 True(그리고 이번 호출을 기록). 초과면 False."""
    now = time.time()
    with _nim_lock:
        while _nim_calls and now - _nim_calls[0] > 60:
            _nim_calls.pop(0)
        if len(_nim_calls) >= NIM_RATE_LIMIT:
            return False
        _nim_calls.append(now)
        return True

def nim_suggest_target(name, amount, message, players, history=None, context=None):
    """후원 메시지가 지목하는 플레이어를 추정한다.
       반환: {"target": 이름 또는 None, "confidence": 0.0~1.0}
       키 없음/한도 초과/오류/타임아웃 시에는 target=None 으로 조용히 실패한다(예외를 던지지 않는다)."""
    names = [(p.get('name') if isinstance(p, dict) else str(p)) for p in (players or [])]
    names = [n for n in names if n]
    if not NVIDIA_API_KEY or not requests or not (message or '').strip() or not names:
        return {"target": None, "confidence": 0.0, "skipped": True}
    if not _nim_allowed():
        return {"target": None, "confidence": 0.0, "skipped": True, "reason": "rate"}
    # ⚠️ 메시지 글자만 주면 'ㄱㅇㅈ' 같은 건 영영 못 푼다.
    #    이 후원자가 예전에 누구에게 갔는지, 지금 화면에서 뭐가 벌어지는지를 같이 준다.
    extra = ""
    if history:
        extra += ("\n이 후원자의 과거 배정: "
                  + ", ".join(f"{p} {c}번" for p, c in history[:4]))
    if context:
        extra += "\n지금 방송 상황: " + " / ".join(context)
    sys_prompt = (
        "너는 라이브 후원 방송의 기입 검증 도우미다. 후원 메시지를 읽고 "
        "그 후원이 아래 플레이어 중 누구를 지목/응원하는지 판단한다.\n"
        "플레이어: " + ", ".join(names) + extra + "\n"
        "규칙: 이름/별명/맥락으로 특정 플레이어를 지목하면 그 이름을, "
        "지목이 전혀 없으면 target 을 null 로 둔다. 반드시 목록에 있는 정확한 이름만 사용한다.\n"
        "과거 배정은 참고만 한다 — 메시지가 다른 사람을 가리키면 메시지를 따른다.\n"
        'JSON만 출력: {"target": "이름 또는 null", "confidence": 0.0~1.0}'
    )
    body = {
        "model": NIM_MODEL,
        "messages": [
            {"role": "system", "content": sys_prompt},
            {"role": "user", "content": f"닉:{name}/금액:{amount}/메시지:{message}"},
        ],
        "temperature": 0.1,
        # ⚠️ 추론을 켜 두면 생각을 먼저 쓰다가 길이 제한에 잘려 JSON 이 아예 안 나온다.
        #    (실제로 그래서 답을 못 읽었다) 넉넉히 주되 추론은 끈다.
        "max_tokens": 200,
    }
    body.update(NIM_NO_THINK)
    try:
        # 붐비면 예비 모델로 넘어간다. 후원이 들어온 순간이라 기다릴 수 없다.
        r, _code, _used = nim_post([NIM_MODEL, NIM_MODEL_BACKUP], body, 8)
        if r is None:
            return {"target": None, "confidence": 0.0, "error": _code or "no-response"}
        if r.status_code != 200:
            # ⚠️ 410/404 는 서버 고장이 아니라 "그 모델이 없어졌다" 는 뜻이다.
            #    NVIDIA 는 모델을 예고 후 내린다. 운영자가 무엇을 해야 하는지 알 수 있게
            #    다른 오류와 구분해서 알려준다.
            if r.status_code in (404, 410):
                print(f"❌ [AI 모델 없음] '{NIM_MODEL}' 이(가) 응답 {r.status_code}. "
                      f"NVIDIA 에서 내려간 모델일 수 있습니다. "
                      f"서버 설정 NIM_MODEL 을 살아 있는 모델로 바꿔주세요.", flush=True)
                return {"target": None, "confidence": 0.0, "error": r.status_code, "gone": True}
            return {"target": None, "confidence": 0.0, "error": r.status_code}
        content = r.json()["choices"][0]["message"]["content"].strip()
        i, j = content.find('{'), content.rfind('}')   # JSON 블록만 추출
        if i == -1 or j == -1:
            return {"target": None, "confidence": 0.0}
        parsed = json.loads(content[i:j + 1])
        target = parsed.get("target")
        if isinstance(target, str):
            target = target.strip()
            if target.lower() in ('null', 'none', ''):
                target = None
        if target not in names:      # 환각 방지: 실제 플레이어 이름과 일치할 때만 인정
            target = None
        try:
            conf = float(parsed.get("confidence", 0))
        except Exception:
            conf = 0.0
        return {"target": target, "confidence": conf}
    except Exception as e:
        return {"target": None, "confidence": 0.0, "error": str(e)[:80]}

# ---- AI 서포트 채팅: 현재 방송 상태 스냅샷 + 시스템 프롬프트 ----
AI_SYSTEM_PROMPT = (
    "너는 '엔젤컴퍼니' 라이브 방송 운영 시스템의 AI 서포트 어시스턴트다.\n\n"
    "[이 프로그램이 무엇인가]\n"
    "- 시청자 후원(투네이션)을 받아 방송 화면(오버레이)에 리액션·연출을 띄우고, "
    "플레이어(출연자)들의 점수·기여도 랭킹을 관리하는 라이브 방송 운영 도구다.\n"
    "- 운영자(사람)가 '컨트롤러' 화면에서 조작한다. 너는 그 운영자를 돕는다.\n\n"
    "[핵심 흐름]\n"
    "- 후원이 들어오면 '승인 대기함'에 쌓인다. 운영자가 각 후원을 특정 플레이어에게 배정하면 "
    "그 플레이어의 점수·기여도가 오른다(대개 금액/10000 만큼).\n"
    "- 후원 금액대에 맞는 '시그니처'(효과음+이미지 연출)가 자동으로 화면에 재생된다.\n"
    "- 위젯: 플레이어 랭킹판, 후원 게이지, 계좌, 대결(match) 위젯, 퇴근빵(개인별 목표 레이스), "
    "슬롯머신/룰렛 게임 등.\n\n"
    "[너의 역할 = 서포트만]\n"
    "- 현재 상황을 파악해 질문에 답한다. 예: '지금 1등 누구야?', '대결 몇 점 차이야?', "
    "'대기함에 밀린 후원 있어?', '누가 역전당했어?'.\n"
    "- 상황 요약, 실수 방지 조언, 우선순위 제안을 한다.\n"
    "- ⚠️ 너는 직접 점수를 바꾸거나 조작을 실행하지 않는다. 정보 제공과 조언만 한다. "
    "실제 실행은 운영자가 버튼으로 직접 한다.\n\n"
    "[답변 규칙]\n"
    "- 제공된 '현재 방송 상태(JSON)'를 근거로 답한다. 직접 안 적혀 있어도 데이터로 계산·추론할 수 있으면 "
    "끝까지 계산해서 답한다. 예: 점수 차이는 두 점수를 빼서, 역전 여부·급상승은 최근 점수 로그와 현재 순위를 "
    "비교해서 알아낸다. 성급하게 '모른다'고 하지 말 것.\n"
    "- 한두 줄로 끝내지 말고, 운영자가 상황을 판단하는 데 도움이 되게 충분히 설명한다. 관련 숫자(점수·차이·순위·"
    "대기 건수·남은 시간 등)를 구체적으로 제시하고, 도움이 되면 다음에 뭘 하면 좋을지 짧은 제안도 덧붙인다.\n"
    "- 그래도 데이터에 정말 없는 항목이면, 없다고 말한 뒤 어디서 확인하면 되는지(어떤 위젯·기능을 켜거나 봐야 하는지)"
    " 알려준다. 숫자를 지어내지는 않는다.\n"
    "- 후원 건수·합계를 물으면 '오늘_후원' 을 그대로 쓴다. 점수 로그를 세어 짐작하지 않는다 — "
    "그건 배정 기록이라 후원 건수와 다르다(하나를 나눠주면 여러 줄이 된다).\n"
    "- 한국어로. 핵심을 먼저, 세부는 뒤에. 방송 중이라 읽기 쉽게 정리한다."
)

def _top_donors(d, n=8):
    """시그니처 1건의 신청자별 횟수 중 상위 n명. 스냅샷 토큰을 아끼려고 자른다.
       잘린 경우 '…그 외'를 남겨서, AI가 일부만 보고 전체인 양 답하지 않게 한다."""
    if not isinstance(d, dict) or not d:
        return None
    items = sorted(d.items(), key=lambda kv: kv[1], reverse=True)
    out = {k: v for k, v in items[:n]}
    if len(items) > n:
        out["…그 외"] = f"{len(items) - n}명"
    return out


def _goal_waiting(state):
    """목표를 넘었는데 아직 연출을 송출하지 않았는가."""
    tgt = int(state.get('target_goal') or 0)
    if tgt <= 0 or state.get('goal_event_approved'):
        return False
    total = sum(int(b.get('contribution') or 0) for b in (state.get('bjs') or []))
    return total >= tgt


def _today_donations():
    """이번 방송에 들어온 후원 건수·합계·상위 후원자.

       ⚠️ AI 에게 세라고 시키면 틀린다. 점수 로그는 20건만 넘기는 데다 배정 기록이라
          후원 건수와 다르다(반반으로 나누면 한 후원이 여러 줄이 된다).
          장부에서 서버가 직접 센다.
       ⚠️ donation_history 는 방송 시작/종료 때 비워지므로 자연히 '이번 방송' 이 된다.
    """
    try:
        with get_db_connection() as conn:
            cur = conn.cursor()
            cur.execute(db_query("SELECT COUNT(*), SUM(amount) FROM donation_history"))
            row = cur.fetchone() or (0, 0)
            cnt, total = int(row[0] or 0), int(row[1] or 0)
            cur.execute(db_query(
                "SELECT name, COUNT(*), SUM(amount) FROM donation_history"
                " GROUP BY name ORDER BY SUM(amount) DESC LIMIT 5"))
            top = [{"이름": r[0], "횟수": int(r[1] or 0), "금액합": int(r[2] or 0)}
                   for r in cur.fetchall()]
        return {"건수": cnt, "합계금액": total, "많이_쏜_사람": top}
    except Exception as e:
        print(f"⚠️ [AI 스냅샷] 오늘 후원 집계 실패 — 그 항목만 빠집니다: {e}", flush=True)
        return None


def build_ai_snapshot(state):
    """AI 서포트가 상황을 파악할 수 있게 현재 상태의 핵심만 추려 컴팩트한 dict로 만든다.
       (레이아웃·에디터·미디어 데이터 등 방송 판단과 무관한 큰 값은 제외해 토큰을 아낀다.)"""
    extra = bool(state.get("extra_game_active"))
    src = "extra_bjs" if extra else "bjs"
    ranking = sorted(
        [{"이름": b.get("name"), "점수": b.get("score", 0), "기여도": b.get("contribution", 0)}
         for b in state.get(src, [])],
        key=lambda x: x["기여도"], reverse=True,
    )
    pend = [{"이름": d.get("name"), "금액": d.get("amount"), "메시지": d.get("message")}
            for d in state.get("pending_donations", []) if d.get("type") != "off_work"]
    recent_logs = [{"시각": l.get("time"), "대상": l.get("name"), "점수변화": l.get("val")}
                   for l in (state.get("logs") or [])[:20]]   # 최신순 상위 20건
    tally = state.get("sig_tally") or {}
    sig_tally_list = sorted(
        [{"제목": v.get("title"), "신청수": v.get("count"), "금액": v.get("amount"),
          "신청자": _top_donors(v.get("donors"))} for v in tally.values()],
        key=lambda x: (x["신청수"] or 0), reverse=True)
    # 시그니처를 많이 쏜 사람 순위. 8b 모델은 여러 항목을 가로질러 합산하는 걸 자주 틀리므로
    # "오늘 시그 제일 많이 쏜 사람?" 에 바로 답할 수 있게 서버에서 미리 합쳐준다.
    donor_total = {}
    for v in tally.values():
        amt = v.get("amount") or 0
        for nm, cnt in (v.get("donors") or {}).items():
            row = donor_total.setdefault(nm, {"횟수": 0, "금액합": 0})
            row["횟수"] += int(cnt or 0)
            row["금액합"] += int(cnt or 0) * amt
    sig_donor_rank = sorted(
        [{"이름": k, "횟수": v["횟수"], "금액합": v["금액합"]} for k, v in donor_total.items()],
        key=lambda x: x["금액합"], reverse=True)[:10]
    roul = state.get("roulette") or {}
    return {
        "방송중": bool(state.get("broadcast_active")),
        "임시게임_진행중": extra,
        "플레이어_랭킹": ranking,
        "승인_대기_후원": pend,
        "승인_대기_건수": len(pend),
        "리액션_대기열_수": len(state.get("reaction_queue", [])),
        "최근_점수_로그": recent_logs,
        # ⚠️ 점수 로그는 '배정' 기록이라 후원 건수와 다르다. 후원 건수를 물으면 여기를 봐야 한다.
        "오늘_후원": _today_donations(),
        "최근_후원": state.get("latest_donation"),
        "방송_목표금액": state.get("target_goal"),
        "대결": state.get("match_data"),
        "퇴근빵_켜짐": bool(state.get("home_race_enabled")),
        "퇴근빵_목표": state.get("home_goals"),
        "계좌": state.get("account"),
        "운영비": state.get("bottom_fixed"),
        "시그니처_신청집계": sig_tally_list,
        "시그니처_후원자_순위": sig_donor_rank,
        # ⚠️ goal_event_pending 은 true 가 되는 코드가 없어서 늘 거짓이었다.
        #    조종실이 승인 버튼을 띄우는 기준(기여도 합계가 목표를 넘었는가)과 같게 맞춘다.
        "목표연출_승인대기": bool(_goal_waiting(state)),
        "슬롯": {"켜짐": bool(state.get("slot_enabled")), "후보수": len(state.get("slot_pool") or [])},
        "룰렛": {"켜짐": bool(state.get("roulette_enabled")), "당첨자": roul.get("winner_name"), "돌리는중": bool(roul.get("is_spinning"))},
        "티커_문구": state.get("ticker_text"),
    }

def _ai_vip_list():
    """AI 스냅샷용 VIP(특별 후원자) 목록. 실패해도 빈 리스트."""
    try:
        with get_db_connection() as conn:
            cur = conn.cursor()
            cur.execute(db_query("SELECT name, grade, badge FROM vip_donators ORDER BY name ASC"))
            return [{"이름": r[0], "등급": r[1], "뱃지": r[2]} for r in cur.fetchall()]
    except Exception:
        return []

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

# 오버레이가 안 돌고 있을 때 리액션 큐가 무한정 쌓이는 것을 막는 상한.
# 전체 큐가 매 update 마다 모든 클라이언트로 나가므로 메모리·트래픽에 직접 영향을 준다.
REACTION_QUEUE_MAX = 40

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


def _norm_donor(name):
    """후원자 표기 정규화. 같은 사람이 '홍길동' / '홍길동님' / ' 홍길동 ' 으로 갈라져
       집계가 쪼개지는 것을 막는다."""
    n = ' '.join(str(name or '').split())
    if n.endswith('님'):
        n = n[:-1].strip()
    return n or '익명'


# ══ 🧠 후원자 기억 ══

# 메시지에서 '이름 후보'가 될 만한 토막을 뽑는다.
# ⚠️ 너무 많이 뽑으면 아무 말이나 별명이 되어 오답을 만든다. 짧고 흔한 말은 버린다.
_ALIAS_STOP = {'화이팅', '파이팅', '감사', '감사합니다', '고생', '고생하셨어요', '수고',
               '수고하셨습니다', '응원', '응원합니다', '축하', '사랑해요', '가즈아', '대박',
               '오늘', '방송', '재밌어요', '잘보고있어요', '님', '언니', '누나', '형', '오빠'}


def alias_tokens(message):
    """메시지에서 별명 후보를 뽑는다."""
    txt = str(message or '')
    out = []
    for w in re.split(r'[\s,./!?~\-()\[\]"\'·:;]+', txt):
        w = w.strip().strip('님아야이가는은를을에게한테')
        if not (2 <= len(w) <= 8):
            continue
        if w in _ALIAS_STOP:
            continue
        if w.isdigit():          # 순수 숫자는 금액·시각일 때가 많다
            continue
        out.append(w)
    return out[:6]


def remember_assignment(donor, player, amount, message):
    """후원 한 건이 누구에게 갔는지 기억한다. 실패해도 배정은 이미 끝났으니 조용히 넘어간다."""
    d = _norm_donor(donor)
    p = str(player or '').strip()
    if not p or d == '익명':      # 익명은 사람을 특정할 수 없어 기억해도 쓸모가 없다
        return
    try:
        now = time.strftime('%Y-%m-%d %H:%M:%S')
        with get_db_connection() as conn:
            cur = conn.cursor()
            cur.execute(db_query("INSERT INTO donor_memory (timestamp, donor, player, amount, message)"
                                 " VALUES (?, ?, ?, ?, ?)"),
                        (now, d, p, int(amount or 0), str(message or '')[:300]))
            for tok in alias_tokens(message):
                cur.execute(db_query("SELECT id, hits FROM alias_memory WHERE token = ? AND player = ?"),
                            (tok, p))
                row = cur.fetchone()
                if row:
                    cur.execute(db_query("UPDATE alias_memory SET hits = hits + 1, updated = ? WHERE id = ?"),
                                (now, row[0]))
                else:
                    cur.execute(db_query("INSERT INTO alias_memory (token, player, hits, updated)"
                                         " VALUES (?, ?, 1, ?)"), (tok, p, now))
    except Exception as e:
        print(f"⚠️ [후원자 기억 실패] {e}")


def donor_history(donor, limit=5):
    """이 후원자가 최근 누구에게 갔는지. [(플레이어, 횟수)] 를 많은 순으로."""
    d = _norm_donor(donor)
    if not d or d == '익명':
        return []
    try:
        with get_db_connection() as conn:
            cur = conn.cursor()
            cur.execute(db_query("SELECT player, COUNT(*) c FROM donor_memory WHERE donor = ?"
                                 " GROUP BY player ORDER BY c DESC LIMIT ?"), (d, limit))
            return [(r[0], int(r[1])) for r in cur.fetchall()]
    except Exception:
        return []


def alias_lookup(message, players):
    """메시지 안의 말이 특정 플레이어로만 이어져 왔는지 본다.
       반환: (플레이어, 적중수, 그 말) 또는 None."""
    toks = alias_tokens(message)
    if not toks:
        return None
    names = {str(p).strip() for p in (players or []) if str(p or '').strip()}
    try:
        with get_db_connection() as conn:
            cur = conn.cursor()
            ph = ', '.join(['?'] * len(toks))
            cur.execute(db_query(f"SELECT token, player, hits FROM alias_memory WHERE token IN ({ph})"),
                        tuple(toks))
            rows = [r for r in cur.fetchall() if r[1] in names]
    except Exception:
        return None
    if not rows:
        return None
    # 한 말이 여러 사람에게 이어져 왔으면 믿을 수 없다 — 아예 쓰지 않는다.
    by_tok = {}
    for tok, player, hits in rows:
        by_tok.setdefault(tok, []).append((player, int(hits)))
    best = None
    for tok, lst in by_tok.items():
        if len(lst) != 1:
            continue          # 그 말이 두 사람 이상을 가리킨 적이 있다 → 버린다
        player, hits = lst[0]
        if not best or hits > best[1]:
            best = (player, hits, tok)
    return best


def enqueue_signature(state, sig, amount, donator, message, skip_popup=False, count_tally=True):
    """시그니처를 리액션 큐에 추가 (모든 재생 경로가 이 함수를 공유).

    큐를 태우면 reaction_mode가 켜지고, 재생이 끝나 큐가 비면 자동으로 꺼진다.
    skip_popup: 슬롯 당첨처럼 이미 자체 연출을 보여준 경우 후원 팝업을 건너뛴다.
    count_tally: 시그니처 순위 집계에 셀지 여부. 실제 후원(자동/장부기록)만 True,
                 슬롯 당첨·재생전용 수동 송출은 False(집계 부풀림 방지).
    """
    reaction_uuid = f"rq_{uuid.uuid4().hex}"
    # ⚠️ 큐는 '오버레이가 재생해야만' 줄어든다. OBS 장면을 바꿔놨거나 오버레이를 닫아둔 채
    #    후원이 계속 들어오면 끝없이 쌓이고, 그 전체가 매 update 마다 모든 클라이언트에게 전송된다.
    #    게다가 오버레이가 다시 붙는 순간 밀린 것을 전부 연달아 재생해버린다.
    #    상한을 두고 가장 오래된 것부터 버린다(버린 사실은 로그로 남긴다).
    _queue = state.setdefault('reaction_queue', [])
    if len(_queue) >= REACTION_QUEUE_MAX:
        dropped = len(_queue) - REACTION_QUEUE_MAX + 1
        del _queue[:dropped]
        print(f"⚠️ [리액션 큐 상한] 밀린 시그니처 {dropped}건을 버렸습니다 (상한 {REACTION_QUEUE_MAX}건). "
              f"오버레이가 꺼져 있거나 재생이 멈춰 있는지 확인하세요.")
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
        "skip_popup": bool(skip_popup)
    })
    state['reaction_mode'] = True

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

def _slot_finish(winner):
    """슬롯 당첨 확정 처리: 슬롯 위젯을 끄고 당첨 시그니처를 리액션 큐에 넣는다."""
    try:
        title = winner.get('title') or '시그니처'
        with file_lock:
            state = load_data()
            state['slot_enabled'] = False
            enqueue_signature(state, winner, winner.get('amount') or 0,
                              '🎰 슬롯머신', f'[슬롯 당첨] {title}', skip_popup=True, count_tally=False)
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
    if request.path.startswith('/api/') or request.path in ('/login', '/setup'):
        r.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        r.headers["Pragma"] = "no-cache"
        r.headers["Expires"] = "0"
    return r

# 🔒 [보안 통제] 웹 제어실 및 중요 API 접근 제한 미들웨어
# 로그인 없이 나가는 정적 자원 확장자.
# 파일 서빙 허용목록(SERVABLE_EXTS)과 따로 놓면 한쪽에만 추가하고 빠뜨려
# '허용된 것이 로그인으로 튐기는' 사고가 난다. 그림·글꼴·스크립트만 여기 넣는다.
STATIC_FREE_EXTS = {
    '.css', '.js', '.mjs', '.map',
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
        '/api/health',
        '/api/donation',
        # ⚠️ /api/streamdeck/* 는 여기에 두면 안 된다. 무인증 GET 만으로 reaction_mode 를
        #    켤 수 있어서, 주소만 아는 사람이 랭킹판·게이지를 숨겨버릴 수 있었다.
        #    큐가 비어 있으면 그걸 끄는 코드가 없어 운영자가 손으로 끌 때까지 돌아오지 않는다.
        #    streamdeck.html 자체가 이미 로그인 뒤에 있어서, 같은 출처 fetch 에 세션이 실린다.
        '/api/roulette/winner',
        '/api/match/timeup',
        '/api/signatures',
        '/api/reaction/next',
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
    return out


# 📡 실시간 SSE 클라이언트 관리 시스템
sse_clients = []
sse_lock = threading.Lock()
# 클라이언트 1대가 밀렸을 때 쌓아둘 최대 메시지 수.
# state 전체가 실리므로(수십 KB) 이 값이 곧 '밀린 클라 1대당 최대 메모리'다.
SSE_QUEUE_MAX = 120

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
    out['server_time'] = int(time.time() * 1000)   # ⏱️ 화면이 서버 시계에 맞출 수 있게
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

def get_or_create_totp_secret():
    return load_auth_config()['totp_secret']


# 🔒 공개된 기본 비밀번호로는 인터넷에서 로그인할 수 없게 막는다.
#
# '0508' 은 이 파일에 적혀 있고 저장소는 공개(public)라, 사실상 누구나 아는 값이다.
# 게다가 OTP 는 빈칸이면 통과하므로, 이 상태에서는 주소만 알면 조종실에 들어와
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


# 🔑 OTP 마스터 코드 — OTP 앱 없이 들어가기 위한 예비 열쇠.
#
# ⚠️ 값을 코드에 적지 않는다. 이 저장소는 공개(public)라, 여기 적는 순간
#    누구나 읽을 수 있는 열쇠가 된다. 반드시 환경변수로만 넣는다.
#      /etc/livemaster.env  →  OTP_MASTER_CODE=...
#    설정하지 않으면 이 기능은 아예 꺼진 상태다(아무 코드도 통과시키지 않는다).
#
# ⚠️ 이 코드는 '두 번째 자물쇠'를 통째로 대신한다. 짧고 뻔한 값(생일·0508 등)을
#    넣으면 2단계 인증이 사실상 없는 것과 같아진다. 그래도 쓰겠다면 최소한
#    조종실 비밀번호(ADMIN_PASSWORD)만은 길고 어렵게 두어야 한다.
# 🐢 로그인 시도를 늦춘다.
#    /login 과 /setup 은 비밀번호 한 개로 통과하는데 시도 횟수에 제한이 없었다.
#    기본 비밀번호가 네 자리(0508)라, 자동 도구면 몇 초 만에 다 넣어본다.
#    /setup 은 통과하면 OTP 비밀키를 그대로 보여주므로 두 번째 자물쇠까지 같이 열린다.
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


def otp_master_matches(code):
    master = (os.environ.get('OTP_MASTER_CODE') or '').strip()
    if not master:
        return False
    # 글자를 하나씩 비교하다 처음 틀린 데서 멈추면, 응답 시간 차이로
    # 코드를 앞에서부터 알아낼 수 있다. 길이와 무관하게 같은 시간이 걸리게 비교한다.
    return secrets.compare_digest(code.strip(), master)

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

    "ticker_enabled": True,
    "ticker_speed": 70,
    "ticker_text": "📢 환영합니다! 후원은 방송에 큰 힘이 됩니다!",
    # ⚔️ 대결. players 는 대결자(또는 팀)다.
    #    team_mode 를 켜면 players[i].members 에 넣은 점수판 사람들에게 들어온 후원이
    #    그 팀의 점수로도 함께 올라간다. 꺼두면 예전처럼 손으로만 넣는다.
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
        "dice": 2,          # 주사위 개수 (1 또는 2)
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
    "slot_enabled": True,
    "slot_pool": [],   # 이번 방송에 쓸 시그니처 id 목록. 비어 있으면 전체를 후보로 사용.
    # 🎯 목표 100% 달성 연출 (달성하면 pending, 운영자가 승인해야 송출)
    "goal_event_pending": False,
    "goal_event_approved": False,
    # 🏃 퇴근전쟁(퇴근빵): 켜면 랭킹판 자리에 개인별 목표 진행바가 뜬다
    "home_race_enabled": False,
    "home_goals": {},         # {플레이어 이름: 퇴근 목표 점수}
    "home_race_notified": [], # 이미 퇴근 카드를 띄운 사람 (송출 후 다시 생기는 것 방지)
    "logs": [],               # 점수/기여도 지급 로그 [{time, name, val}] — DEFAULT_STATE에 있어야 재로드 시 유지된다
    "match_logs": [],         # 대결(임시게임) 전용 지급 로그. logs 와 같은 이유로 여기 있어야 살아남는다
    "neon_speed": 1.5,        # 조명 속도 슬라이더(초). 방송 종료 시 보존 대상 목록에도 들어 있는 '설정값'이다
    "effect_trigger": None,   # 조명 상태 {time, color, infinite}. 일회성 연출이 아니라 '켜 둔 상태'라 유지해야 한다
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


def _save_data_real(new_data, is_initial=False, sync=False, wait=True):
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
    if done is not None and wait:
        # 워커가 밀려 있어도 방송이 멈추지 않도록 상한을 둔다 (실패는 LAST_DB_ERROR에 남음)
        if not done.wait(timeout=30):
            print("⚠️ [동기 저장 시간 초과] 백그라운드에서 계속 진행됩니다.")
    # wait=False 로 부른 쪽은 이 이벤트를 받아 '락을 놓은 뒤' 기다릴 수 있다.
    return done

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
    with sse_lock:
        sse_clients.append(q)

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
                yield msg
        finally:
            # ⚠️ 반드시 finally 여야 한다.
            #    예전에는 while 을 정상적으로 빠져나올 때만 정리했는데, ping 은 `except queue.Empty:`
            #    블록 '안에서' yield 하고 있어서 하필 그 순간 클라이언트가 끊기면
            #    GeneratorExit 가 except 를 지나쳐 밖으로 튀고 정리가 통째로 건너뛰어졌다.
            #    그러면 죽은 큐가 sse_clients 에 남아 이후 모든 broadcast 를 계속 받아 쌓았다.
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

    # 여기부터는 로그인한 사람에게만. 남이 보면 공격 힌트가 되는 것들이다.
    if session.get('authenticated'):
        out['private'] = {
            'weak_admin_secret': SECRET_IS_WEAK,
            'self_ping_enabled': bool(load_data().get('self_ping_enabled')),
            'self_ping_blocked': (os.environ.get('SELF_PING') or '').strip().lower() in ('0', 'off', 'false', 'no'),
            'bind_host': (os.environ.get('BIND_HOST') or '0.0.0.0').strip(),
            'ai_key_present': bool((os.environ.get('NVIDIA_API_KEY') or '').strip()),
            'default_admin_password': load_auth_config()['admin_password'] == '0508',
            'require_otp': REQUIRE_OTP,
            # 코드 자체가 아니라 '설정됐는지/길이가 되는지'만. 값은 절대 내보내지 않는다.
            'otp_master_set': bool((os.environ.get('OTP_MASTER_CODE') or '').strip()),
            'otp_master_short': 0 < len((os.environ.get('OTP_MASTER_CODE') or '').strip()) < 8,
        }

    return jsonify(out)


@app.route('/health')
def serve_health():
    return serve_html_file('health.html')

# 🟢 시그니처 목록 (Supabase 대리 조회) — 오버레이/컨트롤러/슬롯이 공통으로 사용
# 로그인 없이 볼 수 있는 항목. 오버레이가 사진·음원을 미리 받아두는 데 필요한 것뿐이다.
# ⚠️ title 과 amount 를 빼는 이유: 시그게임에서 어느 시그니처가 판에 깔렸는지가
#    번호(sig_id)로 나가는데, 여기서 번호→이름·금액을 그대로 조회할 수 있으면
#    카드를 감춘 의미가 절반은 사라진다. 오버레이는 이 두 값을 쓰지 않는다.
_PUBLIC_SIG_FIELDS = ('id', 'image_url', 'sound_url', 'duration')


@app.route('/api/signatures')
def api_signatures():
    try:
        sigs = supabase_list_signatures()
        if not request_is_authed():
            sigs = [{k: s.get(k) for k in _PUBLIC_SIG_FIELDS if k in s}
                    for s in sigs if isinstance(s, dict)]
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
# 📚 지난 방송 후원내역 (donation_archive) — 로그인 필요
#   방송 종료 때마다 그 회차 장부가 여기로 옮겨진다(지우지 않는다).
#   넣기만 하고 읽는 길이 없어서 그동안 꺼내 볼 수가 없었다.
# ==========================================
ARCHIVE_ROWS_MAX = 5000      # 한 회차가 이보다 많으면 잘라 보낸다(화면이 감당 못 한다)


def _csv_cell(v):
    """엑셀에서 열 때 안전한 한 칸으로 만든다.

       ⚠️ = + - @ 로 시작하는 값은 엑셀이 '수식'으로 읽는다. 후원 메시지는
          후원자가 적는 글이라 그런 글자로 시작할 수 있고, 그대로 두면 정산 파일을
          여는 순간 엑셀이 계산을 시도한다(수식 주입). 앞에 따옴표를 붙여 글로 못박는다.
    """
    t = '' if v is None else str(v)
    if t[:1] in ('=', '+', '-', '@'):
        t = "'" + t
    return '"' + t.replace('"', '""') + '"'


@app.route('/api/archive/sessions')
def api_archive_sessions():
    """회차 목록. 언제 방송분이 몇 건이고 얼마인지."""
    try:
        out = []
        with get_db_connection() as conn:
            cur = conn.cursor()
            cur.execute(db_query("""
                SELECT session_label, COUNT(*), SUM(amount), MIN(timestamp), MAX(timestamp)
                FROM donation_archive
                GROUP BY session_label
                ORDER BY MAX(archived_at) DESC, session_label DESC
            """))
            for r in cur.fetchall():
                out.append({'label': r[0] or '(이름 없음)', 'count': int(r[1] or 0),
                            'total': int(r[2] or 0), 'first': r[3], 'last': r[4]})
        return jsonify({'status': 'success', 'sessions': out, 'count': len(out)})
    except Exception as e:
        print(f'[지난 방송 목록 조회 오류] {e}')
        return jsonify({'status': 'error', 'message': str(e), 'sessions': []}), 500


@app.route('/api/archive/rows')
def api_archive_rows():
    """한 회차의 후원내역. ?label=... 로 회차를 고른다."""
    label = (request.args.get('label') or '').strip()
    if not label:
        return jsonify({'status': 'error', 'message': '회차를 골라주세요'}), 400
    try:
        rows = []
        with get_db_connection() as conn:
            cur = conn.cursor()
            cur.execute(db_query("""
                SELECT timestamp, name, amount, message, source
                FROM donation_archive WHERE session_label = ?
                ORDER BY id ASC
            """), (label,))
            for r in cur.fetchall():
                rows.append({'time': r[0], 'name': r[1], 'amount': int(r[2] or 0),
                             'message': r[3] or '', 'source': r[4] or ''})
        total = sum(r['amount'] for r in rows)
        cut = len(rows) > ARCHIVE_ROWS_MAX
        if cut:
            rows = rows[:ARCHIVE_ROWS_MAX]
        # ⚠️ 잘랐으면 반드시 알려준다. 말없이 자르면 '이게 전부' 로 읽혀 정산이 틀어진다.
        return jsonify({'status': 'success', 'label': label, 'rows': rows,
                        'total': total, 'truncated': cut, 'max': ARCHIVE_ROWS_MAX})
    except Exception as e:
        print(f'[지난 방송 내역 조회 오류] {e}')
        return jsonify({'status': 'error', 'message': str(e), 'rows': []}), 500


@app.route('/api/archive/csv')
def api_archive_csv():
    """엑셀로 내려받기. ?label=... 없으면 전체."""
    from flask import Response
    label = (request.args.get('label') or '').strip()
    try:
        with get_db_connection() as conn:
            cur = conn.cursor()
            if label:
                cur.execute(db_query("""
                    SELECT session_label, timestamp, name, amount, message, source
                    FROM donation_archive WHERE session_label = ? ORDER BY id ASC
                """), (label,))
            else:
                cur.execute(db_query("""
                    SELECT session_label, timestamp, name, amount, message, source
                    FROM donation_archive ORDER BY id ASC
                """))
            data = cur.fetchall()
        lines = ['회차,시각,후원자,금액,메시지,경로']
        for r in data:
            lines.append(','.join(_csv_cell(x) for x in r))
        # ⚠️ 앞에 BOM 을 붙인다. 없으면 엑셀이 UTF-8 을 못 알아채고 한글이 전부 깨진다.
        body = '\ufeff' + '\r\n'.join(lines) + '\r\n'
        stamp = time.strftime('%Y%m%d_%H%M%S')
        fname = f'donations_{stamp}.csv'
        # ⚠️ mimetype 에 charset 을 적으면 Flask 가 뒤에 또 붙여 두 번 들어간다.
        #    content_type 으로 통째로 지정한다.
        return Response(body.encode('utf-8'), content_type='text/csv; charset=utf-8',
                        headers={'Content-Disposition': f'attachment; filename="{fname}"'})
    except Exception as e:
        print(f'[지난 방송 내려받기 오류] {e}')
        return jsonify({'status': 'error', 'message': str(e)}), 500

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

            # DB에서 다시 읽어 메모리 상태를 맞춘다.
            # ⚠️ 먼저 큐를 비운다. 재정산 직전에 눌린 점수 버튼의 낡은 스냅샷이 뒤늦게 쓰이면
            #    방금 원장 기준으로 맞춘 점수가 도로 돌아가고, 그 차이가 '수동 변경'으로
            #    장부에 기록되어 재정산이 신뢰하는 원장 자체를 오염시킨다.
            drain_db_writes()
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
        amount = _as_int(data.get('amount') or 0)
        if amount is None:
            return jsonify({'status': 'error', 'message': '금액이 숫자가 아닙니다'}), 400
        donator = str(data.get('name') or '수동송출').strip() or '수동송출'
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
            # 재생 전용 수동 송출은 실제 후원이 아니므로 시그니처 순위 집계에서 제외한다.
            enqueue_signature(state, sig, amount, donator, message, count_tally=False)
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
        req = request.get_json(silent=True) or {}
        names = req.get('names', [])
        if not isinstance(names, list):
            return jsonify({'status': 'error', 'message': '이름 목록이 필요합니다.'}), 400
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
@app.route('/setup')
def serve_setup():
    """OTP 페어링 화면. 통과하면 2단계 인증의 비밀키를 그대로 보여준다.

    ⚠️ 예전에는 비밀번호 한 겹만 넘으면 열렸다 — 그러면 자물쇠 두 개가 사실상 한 개다.
       (비밀번호를 알아낸 사람이 여기서 OTP 키까지 가져가면 2단계가 무의미해진다)
       이제 조종실 로그인을 먼저 통과해야 한다. 무인증 예외 목록에서도 뺐으므로
       로그인하지 않으면 before_request 가 로그인 화면으로 돌려보낸다.
    """

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
    <script src="/vendor/qrious.min.js"></script>
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
            if admin_password_is_unset():
                return jsonify({'status': 'error', 'message': ADMIN_PASSWORD_UNSET_MSG}), 403

            login_throttle()   # 앞서 틀린 만큼 늦춘다(찍어보기 방지)

            if password_matches(p):
                totp_secret = get_or_create_totp_secret()
                totp = pyotp.TOTP(totp_secret)

                # 통과 사유를 남긴다. '왜 들어왔는지'를 로그로 볼 수 있어야
                # 마스터 코드가 남에게 쓰였을 때 알아챌 수 있다.
                how = None
                if otp_code and otp_master_matches(otp_code):
                    how = 'master'
                elif otp_code and totp.verify(otp_code, valid_window=1):
                    how = 'otp'
                elif not otp_code and not REQUIRE_OTP:
                    how = 'skipped'

                if how:
                    login_ok()
                    session['authenticated'] = True
                    if how == 'master':
                        print(f"🔑 조종실 로그인: 마스터 코드 사용 (ip={_login_key()})", flush=True)
                    return jsonify({'status': 'success'})
                else:
                    # OTP 가 틀린 것도 실패로 센다. 비밀번호를 알아낸 뒤
                    # OTP 여섯 자리를 찍어보는 것도 같은 방식으로 막아야 한다.
                    login_failed('조종실 OTP')
                    return jsonify({'status': 'error', 'message': '보안 OTP 번호가 일치하지 않습니다.'}), 400
            else:
                login_failed('조종실 로그인')
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
@app.route('/signature_display.html')
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

# 📱↔💻 기기를 보고 알아서 갈라준다.
#    폰으로 /controller 를 열면 폰 조종실로, PC 로 /mobile 을 열면 PC 조종실로 보낸다.
#    즐겨찾기가 어느 쪽이든 그 기기에 맞는 화면이 뜬다 — 주소를 두 개 외울 필요가 없다.
#    ?view=pc / ?view=mobile 을 붙이면 강제로 그 화면을 연다(태블릿에서 PC 판을 쓰고 싶을 때).
#    ⚠️ 되돌릴 때 쿼리스트링(토큰!)을 반드시 그대로 실어야 한다 — 떨어뜨리면 로그인으로 튕긴다.
def _wants_mobile():
    forced = (request.args.get('view') or '').strip().lower()
    if forced in ('pc', 'desktop'):
        return False
    if forced in ('mobile', 'phone'):
        return True
    # 'Mobi' 는 아이폰 사파리·안드로이드 크롬이 다 갖고 있는 표준 표식이다.
    # 아이패드(데스크톱 UA)는 화면이 넓으니 PC 판을 준다 — 의도된 동작.
    return 'Mobi' in (request.headers.get('User-Agent') or '')


def _redirect_keep_query(path):
    qs = request.query_string.decode('utf-8')
    return redirect(path + ('?' + qs if qs else ''))


@app.route('/controller')
def serve_controller():
    if _wants_mobile():
        return _redirect_keep_query('/mobile')
    return serve_html_file('controller.html')

@app.route('/mobile')
def serve_mobile():
    # 📱 아이폰 방식 폰 조종실 (앱 12개 + 상단 알림 배너)
    if not _wants_mobile():
        return _redirect_keep_query('/controller')
    return serve_html_file('mobile.html')

@app.route('/admin')
@app.route('/admin.html')
def serve_admin():
    return serve_html_file('admin.html')

@app.route('/upload')
@app.route('/노래등록')
def serve_upload():
    return serve_html_file('upload.html')

# 이 폴더에는 화면 파일만 있는 게 아니다. server.py, live_master.db,
# SUPABASE_CREDENTIALS.txt, auth_config.json, .env, 로그가 전부 같이 있다.
# 아래 catch-all 이 '있으면 준다' 였던 탓에, 주소만 대면 그것들이 그대로 내려왔다
# (관리자 키가 공개 기본값이면 로그인 없이도 통했다).
# 그래서 화면이 실제로 부르는 확장자만 통과시킨다. 목록에 없는 것은
# 로그인한 사람에게도 주지 않는다 — 조종실도 이 파일들을 주소로 꺼내 쓰지 않는다.
SERVABLE_EXTS = {
    '.html', '.htm', '.css', '.js', '.mjs', '.map',
    '.png', '.jpg', '.jpeg', '.gif', '.webp', '.svg', '.ico', '.avif',
    '.woff', '.woff2', '.ttf', '.otf', '.eot',
    '.mp3', '.m4a', '.aac', '.ogg', '.wav', '.webm', '.mp4',
}


# 🔊 효과음. 오버레이에는 로그인 세션이 없으므로 이 폴더만 따로 열어준다.
#    ⚠️ sounds/ 안의 소리 파일만 나간다. 폴더를 벗어나거나 다른 확장자면 404 다.
#       (아래 catch-all 은 .mp3 를 로그인 없이 주지 않는다 — 그래서 전용 길이 필요하다)
SFX_DIR = os.path.join(BASE_DIR, 'sounds')
SFX_EXTS = {'.mp3', '.m4a', '.ogg', '.wav', '.webm'}


@app.route('/sfx/<path:filename>')
def serve_sfx(filename):
    if os.path.splitext(filename)[1].lower() not in SFX_EXTS:
        return jsonify({"error": "File not found"}), 404
    full = os.path.normpath(os.path.join(SFX_DIR, filename))
    if not full.startswith(os.path.normpath(SFX_DIR) + os.sep) or not os.path.exists(full):
        return jsonify({"error": "File not found"}), 404
    return send_from_directory(SFX_DIR, filename)


# 🎬 고액후원 영상. 효과음(/sfx/)과 같은 이유로 전용 길을 낸다 —
#    오버레이에는 로그인 세션이 없어서, 일반 경로로 두면 영상이 로그인 화면으로 튕긴다.
#    (지금은 Supabase 에 두므로 이 길이 없어도 되지만, 서버에 직접 두고 싶어질 때를 위해
#     열어둔다. 그러면 조종실에 저장된 주소 한 줄만 바꾸면 되고 코드는 안 건드린다)
#    ⚠️ videos/ 폴더 안의 영상만 나간다. 폴더를 벗어나거나 다른 확장자면 404 다.
VIDEO_DIR = os.path.join(BASE_DIR, 'videos')
VIDEO_EXTS = {'.mp4', '.webm', '.mov', '.m4v'}


@app.route('/videos/<path:filename>')
def serve_video(filename):
    if os.path.splitext(filename)[1].lower() not in VIDEO_EXTS:
        return jsonify({"error": "File not found"}), 404
    full = os.path.normpath(os.path.join(VIDEO_DIR, filename))
    if not full.startswith(os.path.normpath(VIDEO_DIR) + os.sep) or not os.path.exists(full):
        return jsonify({"error": "File not found"}), 404
    # 영상은 커서 탐색(range 요청)이 되어야 한다. conditional=True 가 그걸 처리한다.
    return send_from_directory(VIDEO_DIR, filename, conditional=True)


@app.route('/<path:filename>')
def serve_dynamic_file(filename):
    if filename.startswith('api/'):
        return jsonify({"status": "error", "message": "API endpoint not found"}), 404
    if os.path.splitext(filename)[1].lower() not in SERVABLE_EXTS:
        return jsonify({"error": "File not found"}), 404
    for root in [BASE_DIR, BUNDLE_DIR]:
        # 상위 폴더로 빠져나가는 경로를 두 겹으로 막는다
        # (send_from_directory 도 막지만, 여기서 os.path.exists 로 존재 여부를
        #  먼저 알려주는 것 자체가 힌트가 된다)
        full = os.path.normpath(os.path.join(root, filename))
        if not full.startswith(os.path.normpath(root) + os.sep):
            continue
        if os.path.exists(full):
            return send_from_directory(root, filename)
    return jsonify({"error": "File not found"}), 404

# ==========================================
# 🛡️ 투네이션 후원 안전 접수 및 파서
# ==========================================

# 메시지 앞에 붙은 "닉네임: 내용" 을 대리 후원 표기로 볼지 판정한다.
#
# ⚠️ 예전에는 '콜론이 있고 앞이 15자 이하'면 무조건 이름으로 갈아끼웠다. 그래서
#    "수고하셨습니다 :)" 는 후원자가 '수고하셨습니다' 가 되고, "10:30에 봐요" 는 '10',
#    "목표: 100만" 은 '목표' 가 됐다. 이모티콘과 시각 표기가 흔해 자주 터졌고,
#    바뀐 이름이 그대로 대기함·장부·순위에 박혀 되돌릴 방법도 없었다.
#    아래 조건은 전부 '그건 이름일 리 없다'가 확실한 경우만 걸러낸다.
_EMOTICON_AFTER_COLON = set(')(dDpPoO3/\\|<>^_-*;')


# 플랫폼이 이름을 제대로 안 준 경우들. 이때만 메시지에서 이름을 가져온다.
_ANONYMOUS_NAMES = {'', '-', '익명', '익명의 후원자', '익명후원자', '무명', '후원자',
                    'anonymous', 'anon', 'unknown'}


def name_is_missing(name):
    """플랫폼이 준 이름이 '사실상 없는' 것인가."""
    return str(name or '').strip().lower() in _ANONYMOUS_NAMES


def looks_like_proxy_name(prefix, rest):
    """prefix 가 '대리 후원 닉네임'으로 보이는가."""
    if not prefix or len(prefix) > 12:
        return False            # 너무 길면 이름이 아니라 문장이다
    if not rest:
        return False            # 콜론 뒤가 비었으면 이름이 아니다
    if rest[0] in _EMOTICON_AFTER_COLON:
        return False            # :) :D :3 :/ ... 이모티콘
    if prefix.isdigit():
        return False            # 10:30 같은 시각·숫자
    if any(ch in prefix for ch in '.,!?~…'):
        return False            # 문장 부호가 섞였으면 이름이 아니다
    if not any(ch.isalnum() for ch in prefix):
        return False            # 글자가 하나도 없으면 이름이 아니다
    return True
def donation_source_allowed():
    """후원 접수를 받아줄 상대인가.

    ⚠️ 이 경로는 예전에 완전히 열려 있었다. 크롬 유저스크립트가 바깥에서 쏴야 했기 때문인데,
       그 대가로 '주소만 알면 누구나 100만원 후원을 만들어낼 수 있는' 상태였다.
       가짜 후원은 대기함에 쌓이고, 금액에 맞는 시그니처가 방송에 재생되고, 장부에도 남는다.
    ⚠️ 이제 투네이션 리스너가 같은 서버 안에서(127.0.0.1) 부르므로 바깥을 막을 수 있다.
       유저스크립트를 다시 쓰려면 DONATION_KEY 를 정하고 스크립트에 같은 값을
       X-Donation-Key 헤더로 넣으면 된다.
    """
    if request_is_from_this_server():
        return True                      # 서버 안의 리스너
    if request_is_authed():
        return True                      # 조종실에서 수동 송출
    key = (os.environ.get('DONATION_KEY') or '').strip()
    if key:
        sent = (request.headers.get('X-Donation-Key') or '').strip()
        if sent and secrets.compare_digest(sent, key):
            return True
    return False


@app.route('/api/donation', methods=['POST'])
def receive_donation():
    if not donation_source_allowed():
        print(f"⛔ [후원 접수 거부] 허용되지 않은 곳에서 왔습니다 (ip={request.remote_addr}, "
              f"xff={request.headers.get('X-Forwarded-For')})", flush=True)
        return jsonify({"status": "error",
                        "message": "이 서버에서만 후원을 접수합니다. 바깥에서 보내려면 "
                                   "DONATION_KEY 를 정하고 X-Donation-Key 헤더에 같은 값을 넣으세요."}), 401
    try:
        new_don = request.get_json(silent=True)
        if not isinstance(new_don, dict):
            return jsonify({"status": "error",
                            "message": "후원 내용(JSON)이 필요합니다"}), 400
        # ⚠️ 금액은 바깥(리스너·템퍼몽키)에서 온다. 숫자가 아니면 그 자리에서 예외가 나
        #    500 이 되고, 보내는 쪽은 '서버가 고장났다'로 보고 계속 재시도한다.
        #    무엇이 잘못됐는지 알려주고 곱게 거절한다.
        amount = _as_int(new_don.get('amount', 0))
        if amount is None:
            return jsonify({"status": "error",
                            "message": "금액(amount)이 숫자가 아닙니다"}), 400
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

        # 2-b. 재전송 대비: 이름+금액+메시지가 동일한 후원이 아주 짧은 시간 안에
        #      다시 오면 중복으로 간주해 무시한다(시그니처 이중 재생 방지).
        # ⚠️ 예전에는 `if not tx_id:` 였다. 그런데 템퍼몽키 스크립트는 재시도할 때마다
        #    tx_id 를 '새로 만들어' 보낸다. 그래서 응답이 늦어 재시도가 걸리면
        #    tx_id 검사는 통과해버리고(값이 다르니까) 이 검사는 아예 건너뛰어서,
        #    같은 후원이 두 번 들어와 시그니처가 두 번 재생되고 장부에도 두 줄이 남았다.
        #    tx_id 유무와 무관하게 항상 내용 기반으로도 걸러야 한다.
        #    ⚠️ 단, 웹소켓 리스너(tx_id 가 'toon_' 로 시작)가 보낸 것은 예외로 둔다.
        #       리스너는 실패해도 재시도하지 않고, 소켓 재전송은 리스너가 스스로 걸러낸다.
        #       그래서 여기까지 온 리스너 후원은 '진짜로 두 번 쏜 것'이며, 버리면 돈이 사라진다.
        #       (실제 방송에서 같은 사람이 같은 금액·같은 메시지로 연달아 쏘자 두 번째가 날아갔다)
        #       이 예외는 템퍼몽키를 끄고 리스너만 쓸 때를 전제로 한다. 둘을 같이 켜면
        #       알림창 애니메이션이 긴 후원에서 중복이 통과할 수 있으니 한쪽만 쓸 것.
        from_listener = str(tx_id or '').startswith('toon_')
        dup_key = f"{(new_don.get('name') or '').strip()}|{amount}|{(new_don.get('message') or '').strip()}"
        if not from_listener and is_duplicate_donation(dup_key):
            print("⚠️ [내용 기반 중복 후원 무시] 동일 후원이 짧은 시간에 재수신됨")
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
            # ⚠️ 예전에는 don_<밀리초> 였다. 같은 밀리초에 두 건이 들어오면 번호가 겹쳐,
            #    한 건을 대기함에서 지울 때 두 건이 같이 사라진다. 리액션 큐는 이미 uuid 를 쓴다.
            don_id = f"don_{int(time.time() * 1000)}_{uuid.uuid4().hex[:6]}"
            name = new_don.get('name', '익명')
            msg = new_don.get('message', '')
            
            orig_name = name.strip()          # 투네이션이 준 진짜 닉네임. 무슨 일이 있어도 보존한다.
            parsed_name = orig_name
            cleaned_msg = msg.strip()

            # 💡 "닉네임: 내용" 형태로 보낸 이름을 가져온다(시그니처 신청 태그는 제외).
            #
            # ⚠️ 플랫폼이 이름을 제대로 준 경우에는 절대 건드리지 않는다.
            #    이 기능은 '익명'처럼 이름이 안 들어올 때 메시지로 알려주라고 있는 것인데,
            #    예전에는 이름이 멀쩡해도 메시지에 콜론만 있으면 갈아끼웠다.
            #    그래서 "목표: 100만 가자" 같은 평범한 문장에도 후원자가 '목표'가 됐다.
            #    "목표: …" 와 "철수: …" 는 글자 모양이 같아 내용만으로는 구분할 수 없다.
            #    그래서 '이름이 없을 때만' 이라는, 헷갈릴 여지가 없는 기준을 쓴다.
            cleaned_msg_for_split = cleaned_msg.replace('：', ':')
            if (name_is_missing(orig_name)
                    and cleaned_msg_for_split and ':' in cleaned_msg_for_split
                    and not cleaned_msg.startswith("[시그니처 신청:")):
                split_char = ':' if ':' in cleaned_msg else '：'
                parts = cleaned_msg.split(split_char, 1)
                potential_name = parts[0].strip()
                rest = parts[1].strip() if len(parts) > 1 else ''
                if looks_like_proxy_name(potential_name, rest):
                    parsed_name = potential_name
                    cleaned_msg = rest
                    print(f"  ↪️ [이름 보정] 이름이 '{orig_name}' 으로 들어와, 메시지에서 '{parsed_name}' 을 가져왔습니다")

            # ⚠️ '님' 떼기는 화면 글자를 긁어오던 시절의 보정이다("홍길동님이 후원하셨습니다").
            #    웹소켓 리스너(tx_id 가 toon_)는 닉네임을 그대로 주므로 떼면 안 된다 —
            #    '하늘님' 같은 닉네임이 '하늘' 로 바뀌어 순위가 두 사람으로 쪼개진다.
            if not str(tx_id or '').startswith('toon_'):
                if parsed_name.endswith('님') and len(parsed_name) > 1:
                    parsed_name = parsed_name[:-1]

            parsed_don_entry = {
                'id': don_id,
                'name': parsed_name,
                # 실제로 돈을 보낸 사람. parsed_name 이 대리 후원 표기로 바뀌어도 여기는 그대로다.
                # (예전에는 원본이 어디에도 안 남아, 잘못 바뀌면 되돌릴 방법이 없었다)
                'orig_name': orig_name,
                'amount': amount,
                'message': cleaned_msg,
                'time': time.strftime('%H:%M:%S')
            }
            state['pending_donations'].append(parsed_don_entry)
            # 대기함이 커지면 state 전체가 그만큼 무거워지고, 그게 접속 대수만큼 곱해져 나간다.
            # (부하 테스트: 802건 → state 120KB → 12대에 1.4MB/회)
            if len(state['pending_donations']) == PENDING_WARN_AT:
                print(f"⚠️ [대기함 {PENDING_WARN_AT}건] 배정이 밀려 있습니다. 화면 갱신이 무거워집니다 "
                      f"— 조종실에서 처리하거나 오토파일럿을 켜주세요.")
            state['latest_donation'] = {
                'name': parsed_name,
                'amount': amount,
                'message': cleaned_msg,
                'time': time.time()
            }
            # ⚠️ 여기서 reaction_mode 를 무조건 켜면 안 된다.
            #    시그니처가 매칭되지 않는 후원(금액 미등록, 0원 후원, Supabase 일시 오류)에서도
            #    켜져버리는데, 켜는 건 여기뿐이고 끄는 건 '오버레이가 큐를 다 소화했을 때'뿐이라
            #    큐가 비어 있으면 아무도 못 끈다. 그러면 오버레이가 랭킹판·게이지를 숨긴 채
            #    (컨트롤러 표기: '위젯 숨김') 방송이 계속되고, 운영자가 수동으로 끌 때까지 돌아오지 않는다.
            #    실제로 큐에 넣는 enqueue_signature 가 이미 켜주므로 여기서는 손대지 않는다.

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
            # 🏅 후원 순위 집계 — 이번 방송에 누가 얼마를 넣었나.
            #    ⚠️ 여기서 적어두면 SSE 를 타고 방송 화면까지 저절로 간다.
            #       DB 를 매번 뒤져 순위를 내면 화면이 몇 초마다 물어봐야 하고 반영도 늦다.
            #    ⚠️ 익명도 일단 세어 둔다. 순위에 넣을지 말지는 보여줄 때 정한다 —
            #       그래야 방송 중에 '익명 포함' 을 껐다 켜도 숫자가 안 틀어진다.
            #    ⚠️ 묶는 이름과 보여줄 이름을 나눈다. _norm_donor 는 '홍길동님' 을 '홍길동' 으로
            #       합치려고 끝의 '님' 을 떼는데, 닉네임이 '새손님' 인 사람은 '새손' 이 되어
            #       방송 화면에 틀린 이름이 나간다. 합산은 정규화된 이름으로, 표시는 원래 이름으로.
            try:
                _who = _norm_donor(parsed_name)
                _dt = state.setdefault('donor_tally', {})
                _row = _dt.get(_who) or {'total': 0, 'count': 0}
                _row['total'] = int(_row.get('total') or 0) + max(0, amount)
                _row['count'] = int(_row.get('count') or 0) + 1
                _shown = ' '.join(str(parsed_name or '').split())
                _row['name'] = _shown or _who
                _dt[_who] = _row
            except Exception as _e:
                print(f"⚠️ [후원 순위 집계 실패] {_e}")

            # ⚠️ 한 번 실패하면 그 후원은 정산 장부에서 통째로 사라진다(운영자는 대기함에서 보고
            #    점수를 주지만 장부엔 없다). Supabase 는 유휴 커넥션을 끊기 때문에 조용한 구간 뒤
            #    첫 후원에서 이게 실제로 발생한다. 다른 곳(save_data_sync)은 이미 1회 재시도로
            #    대응하고 있는데 여기만 빠져 있었다. 실패는 상태창에도 남겨 운영자가 알 수 있게 한다.
            for _attempt in range(2):
                try:
                    with get_db_connection() as conn:
                        cursor = conn.cursor()
                        cursor.execute(
                            db_query("INSERT INTO donation_history (timestamp, name, amount, current_total, message, source, tx_id) VALUES (?, ?, ?, ?, ?, ?, ?)"),
                            (time.strftime('%Y-%m-%d %H:%M:%S'), parsed_name, amount, current_total, cleaned_msg, "toonation", tx_id)
                        )
                    break
                except Exception as dbe:
                    if _attempt == 0:
                        print(f"[장부 기록 실패 — 재시도] {dbe}")   # 끊긴 커넥션은 이미 폐기됐다
                        continue
                    print(f"[장부 기록 오류] {dbe}")
                    LAST_DB_ERROR["message"] = f"후원 장부 기록 실패({parsed_name} {amount}원): {dbe}"
                    LAST_DB_ERROR["time"] = time.strftime('%Y-%m-%d %H:%M:%S')
                
            # 🎵 자동 시그니처 리액션 연동 (매칭은 위에서 락 밖에 끝냈고, 여기서는 큐에만 넣는다)
            if matched_sig:
                enqueue_signature(state, matched_sig, amount, parsed_name, cleaned_msg)
                print(f"  🎵 [자동 시그니처] 후원 {amount}원 → '{matched_sig.get('title')}' (#{matched_sig.get('id')}, {matched_sig.get('amount')}원) 큐 추가 완료")


            # ⚠️ 저장 '대기'를 락 안에서 하면 안 된다.
            #    save_data(sync=True) 는 DB 쓰기 큐가 빌 때까지 최대 30초를 기다린다.
            #    점수 버튼을 몇 번 누른 직후라면 그 큐에 앞선 쓰기가 쌓여 있어(Render→Supabase 왕복)
            #    후원 한 건이 file_lock 을 수 초에서 수십 초까지 쥐고 있었다. 그동안
            #    점수 지급·큐 넘김(/api/reaction/next)·대기함 삭제가 전부 얼어붙어,
            #    화면에서는 시그니처가 멈추고 컨트롤러가 먹통이 됐다.
            #    큐에 넣는 것까지만 락 안에서 하고, 기다리는 건 락을 놓은 뒤에 한다.
            pending_write = save_data(state, sync=True, wait=False)
            broadcast_event('update', state)

            print("  🎯 [최종 처리 결과]")
            print(f"    ▶ 최종 분류된 이름  : {parsed_name}")
            print(f"    ▶ 최종 분류된 메시지: {cleaned_msg}")
            print("    ▶ 자동 승인 처리 여부: 🟡 클래식 수동 정산 모드 작동 (승인 대기함 적립)")
            print("======================================================================\n")

        # 락을 놓은 뒤에 기다린다 — 후원이 실제로 저장된 뒤에 응답한다는 보장은 그대로 유지된다.
        if pending_write is not None and not pending_write.wait(timeout=30):
            print("⚠️ [후원 동기 저장 시간 초과] 백그라운드에서 계속 진행됩니다.")
        return jsonify({'status': 'success', 'id': don_id})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

# ══ 🎯 배정 대상 판단 ══
#
# 예전에는 AI 에게 메시지 글자만 던지고 끝이었다. 그래서 'ㄱㅇㅈ' 처럼 글자만으로는
# 풀 수 없는 것이 전부 '모름' 으로 떨어졌고, 자리를 비운 사이 대기함만 쌓였다.
#
# 이제 네 가지를 순서대로 본다. 앞의 것이 확실하면 AI 를 아예 부르지 않는다
# (분당 한도를 아끼고, 무엇보다 즉시 답이 나온다).
#   ① 메시지에 플레이어 이름이 그대로 있는가
#   ② 그 말이 늘 특정 플레이어로 이어져 왔는가 (별명 기억)
#   ③ 이 후원자가 늘 같은 사람에게 갔는가 (후원자 이력)
#   ④ 그래도 애매하면 AI 에게 — 위 세 가지를 근거로 함께 넘긴다
#
# ⚠️ 확신은 하나의 문턱이 아니라 세 단계다. 예전에는 0.85 하나로 잘라서,
#    0.84 는 아무 표시 없이 조용히 묻혔다. 이제 자동/추천/모름 으로 나눠
#    '모름' 도 눈에 보이게 한다 — 사람이 봐야 할 것을 숨기지 않는 게 핵심이다.
CONF_AUTO = 0.90      # 이 위는 오토파일럿이 스스로 배정한다
CONF_SUGGEST = 0.60   # 이 위는 추천만 한다(사람이 누른다)


def _tier(conf):
    if conf >= CONF_AUTO:
        return 'auto'
    if conf >= CONF_SUGGEST:
        return 'suggest'
    return 'unknown'


def game_context(state):
    """지금 화면에서 벌어지는 일. AI 가 금액·이름을 문맥으로 읽게 해준다."""
    out = []
    try:
        g = state.get('siggame') or {}
        goals = [c for c in (g.get('cards') or []) if c.get('flippedAt') and not c.get('doneAt')]
        if g.get('enabled') and goals:
            out.append('시그뒤집기 진행 중 — 아직 못 받은 목표 금액: '
                       + ', '.join(f"{int(c.get('amount') or 0):,}원" for c in goals))
        md = state.get('match_data') or {}
        if md.get('active'):
            teams = []
            for p in (md.get('players') or []):
                mem = [str(m).strip() for m in (p.get('members') or []) if str(m or '').strip()]
                teams.append(f"{p.get('name')}({'·'.join(mem)})" if mem else str(p.get('name')))
            if teams:
                out.append('대결 진행 중 — ' + ' vs '.join(teams))
        if state.get('home_race_enabled'):
            out.append('퇴근전쟁 진행 중')
    except Exception:
        pass
    return out


# 이름 뒤에 흔히 붙는 조사·호칭. '철수형' → '철수' 로 되돌리려고 쓴다.
_NAME_TAILS = ('에게', '한테', '이랑', '님께', '님', '씨', '형', '누나', '오빠', '언니',
               '쨩', '찡', '아', '야', '이', '가', '은', '는', '을', '를', '와', '과',
               '랑', '도', '만', '께')


def _name_forms(word):
    """낱말 하나에서 '이름일 수 있는 모양'들을 만든다(조사·호칭을 두 번까지 뗀다)."""
    out = {word}
    cur = word
    for _ in range(2):
        for t in _NAME_TAILS:
            if len(cur) > len(t) and cur.endswith(t):
                cur = cur[:-len(t)]
                out.add(cur)
                break
        else:
            break
    return out


def names_in_message(msg, names):
    """메시지가 지목하는 이름을 두 갈래로 나눠 돌려준다.

       exact — 낱말이 딱 떨어진다('철수', '철수형', '철수에게'). 믿을 만하다.
       loose — 글자만 겹친다('철수했다가', '밍밍화이팅'). 참고는 되지만 확실하지 않다.

       ⚠️ 예전에는 이 둘을 구분하지 않고 '글자가 들어 있으면' 전부 확실한 것으로 봤다.
          그래서 '철수했다가 다시 왔어요' 가 철수에게 자동 배정됐다.
       """
    txt = str(msg or '')
    exact, loose = set(), set()
    if not txt:
        return exact, loose
    for w in re.split(r'[\s,./!?~\-()\[\]"\'·:;]+', txt):
        w = w.strip()
        if not w:
            continue
        forms = _name_forms(w)
        # 여러 이름이 걸리면 가장 긴 것을 쓴다('수아' 와 '수' 가 같이 있을 때)
        best = None
        for n in names:
            if n in forms and (best is None or len(n) > len(best)):
                best = n
        if best:
            exact.add(best)
    for n in names:
        if n and n not in exact and n in txt:
            loose.add(n)
    return exact, loose


def _hold_if_message_points_elsewhere(res, loose):
    """메시지가 다른 이름을 가리키고 있으면 자동 배정을 막는다.

       ⚠️ 이력·별명은 '이 사람은 늘 밍밍에게 줬다' 는 통계일 뿐이다.
          그런데 그 후원의 메시지에 '철수' 글자가 들어 있다면, 통계보다 지금 쓴 말이
          우선이어야 한다. 낱말이 딱 떨어지면 ① 에서 이미 잡히고, 여기 걸리는 것은
          '철수화이팅' 처럼 붙여 쓴 애매한 경우다 — 애매하면 사람이 봐야 한다.
    """
    tgt = res.get('target')
    if not tgt or not loose or tgt in loose:
        return res
    if res.get('tier') != 'auto':
        return res
    other = ', '.join(sorted(loose))
    return dict(res, tier='suggest', confidence=min(res.get('confidence') or 0, 0.85),
                why=(res.get('why') or '') + f" — 다만 메시지에 '{other}' 글자가 있어 확인 필요")


def suggest_target(donor, amount, message, players, state=None):
    """이 후원이 누구를 지목하는지 판단한다.
       반환: {target, confidence, tier, source, why, history}"""
    names = [str(p.get('name') if isinstance(p, dict) else p or '').strip() for p in (players or [])]
    names = [n for n in names if n]
    msg = str(message or '')
    hist = donor_history(donor)
    base = {'target': None, 'confidence': 0.0, 'tier': 'unknown',
            'source': None, 'why': None,
            'history': [{'name': p, 'count': c} for p, c in hist]}
    if not names:
        return base

    # ① 메시지에 이름이 그대로 — 가장 확실하다.
    #    단 '낱말이 딱 떨어질 때'만이다. 글자만 겹치는 것은 아래에서 추천으로 낮춘다.
    exact, loose = names_in_message(msg, names)
    if len(exact) == 1:
        one = next(iter(exact))
        return dict(base, target=one, confidence=0.97, tier='auto',
                    source='이름', why=f'메시지에 \'{one}\' 이 있음')
    if len(exact) > 1:
        # 두 사람 이상을 부른 후원은 반반일 수 있다. 사람이 봐야 한다.
        return dict(base, target=None, confidence=0.0, tier='unknown',
                    source='이름', why='여러 사람을 부름: ' + ', '.join(sorted(exact)))

    # ② 별명 기억
    # ⚠️ 한 번만 본 말은 쓰지 않는다. '오늘도' 같은 흔한 말이 우연히 한 번
    #    특정 플레이어로 이어진 것까지 추천으로 올리면 잡음만 된다.
    #    두 번 이상 같은 사람으로 이어졌을 때부터가 '별명'이라 부를 만하다.
    al = alias_lookup(msg, names)
    if al and al[1] >= 2:
        player, hits, tok = al
        conf = min(0.95, 0.62 + 0.09 * hits)
        return _hold_if_message_points_elsewhere(
            dict(base, target=player, confidence=round(conf, 2), tier=_tier(conf),
                 source='별명', why=f'\'{tok}\' 은 지금까지 {hits}번 모두 {player} 였음'), loose)

    # ③ 후원자 이력 — 늘 같은 사람에게 갔는가
    known = [(p, c) for p, c in hist if p in names]
    if known:
        top_p, top_c = known[0]
        others = sum(c for p, c in known[1:])
        if others == 0 and top_c >= 2:
            conf = min(0.93, 0.66 + 0.07 * top_c)
            return _hold_if_message_points_elsewhere(
                dict(base, target=top_p, confidence=round(conf, 2), tier=_tier(conf),
                     source='이력', why=f'이 후원자는 지금까지 {top_c}번 모두 {top_p} 였음'), loose)
        if top_c >= 3 * max(1, others):
            conf = 0.7
            return _hold_if_message_points_elsewhere(
                dict(base, target=top_p, confidence=conf, tier=_tier(conf),
                     source='이력', why=f'{top_c}번 {top_p} / 그 외 {others}번'), loose)

    # ③-b 글자만 겹치는 이름 — 버리지 않고 '추천'으로만 올린다.
    #    '밍밍화이팅' 처럼 붙여 쓴 진짜 지목을 놓치지 않으면서,
    #    '철수했다가' 같은 우연한 겹침으로 돈이 자동으로 가지는 않게 한다.
    if len(loose) == 1:
        one = next(iter(loose))
        return dict(base, target=one, confidence=0.75, tier=_tier(0.75),
                    source='이름', why=f'메시지에 \'{one}\' 글자가 있음 (낱말이 딱 떨어지진 않음)')
    if len(loose) > 1:
        return dict(base, target=None, confidence=0.0, tier='unknown',
                    source='이름', why='여러 이름 글자가 섞임: ' + ', '.join(sorted(loose)))

    # ④ 여기까지 못 풀면 AI 에게. 위에서 모은 것을 근거로 같이 넘긴다.
    ctx = game_context(state) if state else []
    ai = nim_suggest_target(donor, amount, msg, names,
                            history=known, context=ctx)
    conf = float(ai.get('confidence') or 0)
    if not ai.get('target'):
        # ⚠️ 왜 모르는지를 사람 말로 돌려준다. 'rate' 같은 낱말은 화면에 그대로 뜨면
        #    운영자가 무슨 뜻인지 알 수 없고, 그러면 그 표시를 아예 안 믿게 된다.
        if ai.get('reason') == 'rate':
            why = 'AI 호출이 잠시 몰려 못 물어봄 (조금 뒤 다시 봄)'
        elif ai.get('skipped'):
            why = 'AI 가 꺼져 있음 — 이름·별명·이력으로는 못 찾음'
        elif ai.get('error') in NIM_RETRYABLE:
            # 붐빈 것뿐이라 저절로 풀린다. '오류' 라고 하면 고칠 게 있는 줄 알고
            # 방송 중에 서버를 건드리게 된다.
            why = 'AI 서버가 붐빕니다 — 잠시 뒤 저절로 됩니다'
        elif ai.get('gone'):
            why = 'AI 모델이 종료됐습니다 — 서버 설정에서 모델을 바꿔주세요'
        elif ai.get('error'):
            why = 'AI 오류로 못 물어봄'
        elif hist:
            why = '메시지로도 이력으로도 특정이 안 됨'
        else:
            why = '처음 보는 후원자이고 메시지에 단서가 없음'
        return dict(base, target=None, confidence=0.0, tier='unknown', source='AI', why=why)
    # AI 는 이력·별명만큼 믿지 않는다. 위쪽 단계에서 걸리지 않은 건은 애매한 것이다.
    conf = min(conf, 0.88)
    return _hold_if_message_points_elsewhere(
        dict(base, target=ai['target'], confidence=round(conf, 2), tier=_tier(conf),
             source='AI', why='메시지 내용으로 추정'), loose)


@app.route('/api/audit/suggest', methods=['POST'])
def api_audit_suggest():
    """[AI 기입 검증] 후원 메시지가 지목하는 플레이어를 추정해 돌려준다.
       컨트롤러가 대기함 후원 1건당 1회 호출해 '추천 배지 / 오배정 경고'에만 쓴다.
       실패해도 항상 200 + target=None 으로 응답해 컨트롤러가 멈추지 않게 한다."""
    try:
        body = request.get_json(silent=True) or {}
        name = str(body.get('name', ''))
        amount = body.get('amount', 0)
        message = str(body.get('message', ''))
        players = body.get('players')
        if not players:   # 클라이언트가 안 보냈으면 서버 상태에서 현재 플레이어를 읽는다
            with file_lock:
                state = load_data()
                src = 'extra_bjs' if state.get('extra_game_active') else 'bjs'
                players = [b.get('name') for b in state.get(src, [])]
        with file_lock:
            st = load_data()
        result = suggest_target(name, amount, message, players, st)
        return jsonify({"status": "success", **result})
    except Exception as e:
        return jsonify({"status": "success", "target": None, "confidence": 0.0, "error": str(e)[:80]})

@app.route('/api/ai/chat', methods=['POST'])
def api_ai_chat():
    """[AI 서포트 채팅] 운영자가 현재 상황을 물어보면, 실시간 상태 스냅샷을 근거로 답한다.
       조작은 하지 않고 정보/조언만. 실패해도 항상 200 + 안내 문구로 응답한다."""
    try:
        body = request.get_json(silent=True) or {}
        question = str(body.get('question', '')).strip()
        history = body.get('messages') or []
        if not question:
            return jsonify({"status": "success", "reply": "무엇을 도와드릴까요?"})
        if not NVIDIA_API_KEY or not requests:
            return jsonify({"status": "success",
                            "reply": "AI 키가 설정되지 않았어요. (Render 환경변수 NVIDIA_API_KEY 확인)"})
        if not _nim_allowed():
            return jsonify({"status": "success",
                            "reply": "지금 AI 호출이 몰려서 잠시 후 다시 물어봐 주세요."})
        with file_lock:
            state = load_data()
            snap = build_ai_snapshot(state)
        snap["VIP_후원자"] = _ai_vip_list()   # 상태 밖(DB)이라 여기서 붙인다
        sys_full = NIM_CHAT_PREFIX + AI_SYSTEM_PROMPT + "\n\n[현재 방송 상태(JSON)]\n" + json.dumps(snap, ensure_ascii=False)
        msgs = [{"role": "system", "content": sys_full}]
        for m in history[-6:]:   # 직전 대화 몇 개만(토큰 절약)
            role = m.get('role'); content = str(m.get('content', ''))
            if role in ('user', 'assistant') and content:
                msgs.append({"role": role, "content": content})
        msgs.append({"role": "user", "content": question})
        # ⚠️ 채팅도 추론을 끈다. 켜 뒀더니 700 토큰을 생각에 다 쓰고 답을 쓰기 전에
        #    잘려서, 화면에 생각하는 과정이 그대로 나갔다
        #    ("Okay, let's see. The user is asking… Let me count the entries…").
        req_body = {"messages": msgs, "temperature": 0.3, "max_tokens": 700}
        req_body.update(NIM_NO_THINK)
        # 붐비면 예비 모델로 넘어간다 — 한쪽이 막혔다고 채팅이 통째로 죽지 않게.
        r, _code, _used = nim_post([NIM_CHAT_MODEL, NIM_CHAT_BACKUP], req_body, 30)
        if r is None:
            return jsonify({"status": "success",
                            "reply": "지금 AI 서버가 붐벼서 답을 못 받았어요. "
                                     "잠시 뒤 다시 물어봐 주세요. (후원·점수에는 영향 없습니다)"})
        if r.status_code != 200:
            if r.status_code in (404, 410):
                print(f"❌ [AI 모델 없음] '{NIM_CHAT_MODEL}' 이(가) 응답 {r.status_code}.", flush=True)
                return jsonify({"status": "success",
                                "reply": f"이 AI 모델('{NIM_CHAT_MODEL}')이 종료됐습니다.\n"
                                         "서버 설정의 NIM_CHAT_MODEL 을 살아 있는 모델로 "
                                         "바꾸고 재시작해주세요. (후원·점수에는 영향 없습니다)"})
            return jsonify({"status": "success", "reply": f"(AI 오류 {r.status_code}) 잠시 후 다시 시도해주세요."})
        msg = r.json()["choices"][0]["message"]
        reply = (msg.get("content") or "").strip()
        # ⚠️ reasoning_content 는 답이 아니라 '생각' 이다. 예전에는 답이 비면 그걸 대신
        #    보여줬는데, 지금 모델은 거기에 혼잣말을 담는다. 그대로 내보내면 조종실에
        #    "Okay, let's see. The user is asking…" 같은 게 뜬다. 답으로 쓰지 않는다.
        if not reply:
            think = (msg.get("reasoning_content") or "").strip()
            if think:
                print(f"⚠️ [AI 채팅] 답이 비어 왔습니다(생각만 {len(think)}자). "
                      f"모델: {_used}", flush=True)
            reply = "생각만 하다 답을 못 만들었어요. 조금 더 짧게 물어봐 주세요."
        return jsonify({"status": "success", "reply": reply})
    except Exception as e:
        return jsonify({"status": "success", "reply": f"(오류) {str(e)[:100]}"})

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
            SERVER_OWNED = ('reaction_queue', 'latest_donation', 'pending_donations',
                            'reaction_paused', 'siggame', 'dicegame', 'sig_tally', 'donor_tally')

            # 🔐 [보안] 응답 전용 필드는 절대 상태로 들어오면 안 된다.
            #   GET /api/data 는 로그인 세션이 있으면 응답에 api_token(= 관리자 비밀키)을 얹어준다.
            #   그런데 에디터는 받은 응답 객체를 통째로 globalData 에 넣고(admin.html) 그대로 다시 POST 한다.
            #   여기서 걸러내지 않으면 그 키가 state 에 눌러앉아 DB 에 평문으로 저장되고,
            #   무인증으로 열려 있는 /api/stream 을 통해 모든 오버레이·알림창에 방송된다.
            #   그 값은 보호된 API 를 전부 통과하는 Bearer 토큰이자 세션 서명키다.
            for _k in ('api_token', 'server_time'):
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

            state = dict(current_state)
            state.update(incoming)                      # 클라이언트 편집 필드는 그대로 반영(설정·승인 등 기존 동작 유지)
            state.pop('api_token', None)                # 과거에 이미 오염됐다면 여기서 씻어낸다
            for k in SERVER_OWNED:
                if k in current_state:
                    state[k] = current_state[k]          # 서버 소유 필드는 서버의 최신 값을 유지
            # ⚠️ 이름 앞뒤 공백을 저장 단계에서 떼어낸다.
            #    이름 칸에 공백을 하나만 더 눌러도 그 사람이 점수를 못 받는 사고가 있었다.
            #    찾을 때도 공백을 무시하도록 고쳤지만(_find_score_target), 저장되는 값 자체가
            #    깨끗해야 장부와 순위에 '밍밍' 과 '밍밍 ' 이 따로 쌓이는 일이 없다.
            for _k in ('bjs', 'extra_bjs'):
                for _p in (state.get(_k) or []):
                    if isinstance(_p, dict) and isinstance(_p.get('name'), str):
                        _p['name'] = _p['name'].strip()
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

@app.route('/api/offwork/pending', methods=['POST'])
def api_offwork_pending():
    """퇴근전쟁 목표를 넘긴 플레이어의 '퇴근 성공' 카드를 서버에 만든다.

    ⚠️ 예전에는 컨트롤러가 자기 pending_donations 에 카드를 직접 넣고 /api/data 로 밀어넣었다.
       그런데 pending_donations 는 SERVER_OWNED 라 그 POST 에서 통째로 버려진다.
       카드는 다음 update 가 오는 순간 화면에서 사라지는데, '이미 알렸다'는 표시
       (home_race_notified)는 서버 소유가 아니라 그대로 저장됐다.
       결과적으로 그 플레이어는 두 번 다시 퇴근 카드를 받지 못했다 = 퇴근 연출을 영영 못 보냄.
       카드 생성과 '알림 표시'를 서버 한 곳에서 같이 처리해 어긋날 수 없게 한다.
    """
    name = ((request.get_json(silent=True) or {}).get('name') or '').strip()
    if not name:
        return jsonify({"status": "error", "message": "name required"}), 400
    with file_lock:
        state = load_data()
        pend = state.setdefault('pending_donations', [])
        notified = state.setdefault('home_race_notified', [])
        if name in notified or any(d.get('type') == 'off_work' and d.get('name') == name for d in pend):
            return jsonify({"status": "success", "message": "already"})
        notified.append(name)
        pend.insert(0, {
            'id': f"off_{int(time.time() * 1000)}_{uuid.uuid4().hex[:4]}",
            'type': 'off_work',
            'name': name,
            'amount': 0,
            'message': '퇴근전쟁 목표 달성!',
            'time': time.strftime('%H:%M:%S'),
        })
        save_data(state)
        broadcast_event('update', state)
    print(f"  🏃 [퇴근전쟁] '{name}' 퇴근 성공 카드 생성")
    return jsonify({"status": "success"})


@app.route('/api/match/timeup', methods=['POST'])
def api_match_timeup():
    """대결 타이머가 0이 됐을 때 오버레이가 알린다.

    ⚠️ 예전에는 오버레이가 이 목적으로 /api/data 에 '자기가 들고 있는 상태 전체'를 POST 했다.
       두 가지가 나빴다.
       1) 그것 때문에 /api/data POST 를 무인증으로 열어둘 수밖에 없었다(누구나 점수를 지울 수 있었다).
       2) 오버레이의 상태가 조금이라도 낡아 있으면 그 낡은 점수가 서버를 덮어썼다.
       그래서 '타이머를 멈춘다'는 사실만 전달하는 좁은 엔드포인트로 분리했다.
    """
    with file_lock:
        state = load_data()
        md = state.get('match_data') or {}
        if not md.get('active'):
            return jsonify({"status": "ignored"})   # 이미 끝난 대결이면 아무것도 하지 않는다

        # ⚠️ 이 경로도 무인증이라, 진행 중인 대결을 밖에서 아무 때나 끝낼 수 있었다.
        #    '정말 시간이 다 됐는지'를 서버가 직접 확인한다. 3초는 시계 차이·전송 지연 몫이다.
        end_ms = md.get('end_time_ms')
        if md.get('is_running') and end_ms and not request_is_authed():
            now_ms = int(time.time() * 1000)
            if now_ms < int(end_ms) - 3000:
                left = (int(end_ms) - now_ms) / 1000
                print(f"⛔ [대결 종료 거부] 아직 {left:.1f}초 남았습니다 (ip={request.remote_addr})", flush=True)
                return jsonify({"status": "error", "message": "아직 시간이 남았습니다"}), 409

        md['is_running'] = False
        md['time_left_ms'] = 0
        state['match_data'] = md
        save_data(state)
        broadcast_event('update', state)
    return jsonify({"status": "success"})


@app.route('/api/account/play', methods=['POST'])
def api_account_play_video():
    """후원 콘솔에서 금액대 버튼을 눌렀을 때 그 구간의 유튜브 영상을 오버레이에 재생한다.

    ⚠️ 예전에는 후원 금액을 받아 '알아서' 구간을 골라 자동 재생했다. 그런데 계좌 버튼이
       점수 배정 자리(대기함 카드)에 붙어 있어서, 배정·시그니처 재생과 순서가 뒤엉켰다.
       지금은 운영자가 '어느 영상을' 트는지 직접 고른다. 자동 매칭은 없앴다.

    body: {"tier": 구간 번호(0부터)}

    상태를 바꾸지 않고 이벤트만 쏘므로 file_lock 을 잡지 않는다(후원 처리를 막지 않는다).
    """
    data = request.get_json(silent=True) or {}
    tiers = load_data().get('account_video_tiers') or []

    try:
        idx = int(data.get('tier'))
    except (TypeError, ValueError):
        return jsonify({"status": "error", "message": "tier 번호가 필요합니다"}), 400
    if not (0 <= idx < len(tiers)):
        return jsonify({"status": "error", "message": "없는 구간입니다"}), 400

    t = tiers[idx]
    video = (t.get('video') or '').strip()
    label = t.get('label') or ''
    if not video:
        return jsonify({"status": "ok", "played": False, "reason": "no_video", "label": label})

    broadcast_event('account_video', {"videoId": video, "label": label})
    return jsonify({"status": "ok", "played": True, "label": label})


@app.route('/api/effect/fire', methods=['POST'])
def api_effect_fire():
    """후원 콘솔의 '이펙트' 탭에서 조종실(사장님) 후원 연출을 쏜다.

    body: {"kinds": ["banner","flash","ticker"], "name": 후원자, "amount": 금액, "message": 문구}

    ⚠️ 기존 시그니처·목표달성 연출과 섞지 않는다. 그쪽은 큐·게이지 상태에 묶여 있어서
       끼어들면 서로를 끊는다(실제로 그런 사고가 있었다). 전용 이벤트로 따로 보낸다.
    상태를 바꾸지 않고 이벤트만 쏘므로 file_lock 을 잡지 않는다.
    """
    data = request.get_json(silent=True) or {}
    kinds = data.get('kinds') or []
    if isinstance(kinds, str):
        kinds = [kinds]
    # 오버레이가 실제로 그릴 줄 아는 연출만 받는다(오타로 아무 일도 안 일어나는 것을 막는다)
    allowed = {'banner', 'flash', 'ticker', 'card', 'shock', 'glitch', 'warn'}
    kinds = [k for k in kinds if k in allowed]
    if not kinds:
        return jsonify({"status": "error", "message": "연출을 하나 이상 골라주세요"}), 400

    name = (data.get('name') or '').strip()
    message = (data.get('message') or '').strip()
    try:
        amount = int(data.get('amount') or 0)
    except (TypeError, ValueError):
        amount = 0

    broadcast_event('operator_effect', {
        "kinds": kinds, "name": name, "amount": amount, "message": message,
        "time": int(time.time() * 1000),
    })
    return jsonify({"status": "ok", "fired": kinds})


@app.route('/api/effect/clear', methods=['POST'])
def api_effect_clear():
    """연출을 즉시 걷는다(잘못 눌렀을 때)."""
    broadcast_event('operator_effect_clear', {})
    return jsonify({"status": "ok"})


# ==========================================
# 🕹️ 버전 되돌리기 / 올리기
# ==========================================
#
# 방송 중에 뭔가 이상하면 조종실에서 바로 이전 버전으로 되돌릴 수 있게 한다.
#
# ⚠️ 자동배포와 싸우지 않게 하는 것이 핵심이다. auto-deploy 는 2분마다
#    `git reset --hard origin/main` 을 하므로, 그냥 옛 커밋으로 옮겨두면
#    2분 안에 최신으로 도로 끌려 올라간다. 그래서 '지금은 이 버전에 고정'
#    이라는 표시(DEPLOY_PIN 파일)를 남기고, auto-deploy 가 그걸 먼저 읽게 했다.
#
# ⚠️ 고를 수 있는 것은 '저장소에 이미 올라간 최근 커밋'뿐이다. 아무 번호나 받으면
#    남의 갈래(fork)에 있는 코드를 서버에서 돌리게 만들 수 있다.

DEPLOY_PIN_FILE = os.path.join(BASE_DIR, 'DEPLOY_PIN')
VERSION_LIST_MAX = 20      # 조종실에 보여주고 고를 수 있는 개수


def _git(*args, timeout=25):
    """저장소 폴더에서 git 을 부른다. (stdout, 성공여부)"""
    try:
        # ⚠️ encoding 을 못박아야 한다. 안 그러면 파이썬이 '이 컴퓨터의 기본 인코딩'으로
        #    해독하는데, 커밋 메시지가 한글(UTF-8)이라 윈도우에서 통째로 깨져 빈 값이 된다
        #    (예외가 읽기 갈래 안에서 조용히 삼켜져서, 오류 없이 목록만 비어 보였다).
        r = subprocess.run(('git',) + args, cwd=BASE_DIR, capture_output=True,
                           text=True, encoding='utf-8', errors='replace', timeout=timeout)
        return (r.stdout or '').strip(), r.returncode == 0
    except Exception as e:
        print(f'⚠️ [git 실패] {" ".join(args)} → {e}')
        return '', False


def _pinned_sha():
    """지금 고정해둔 버전. 없으면 None(= 최신을 따라간다)."""
    try:
        with open(DEPLOY_PIN_FILE, 'r', encoding='utf-8') as f:
            v = f.read().strip()
        return v or None
    except Exception:
        return None


def _write_pin(sha):
    """고정 표시를 남긴다(sha 가 None 이면 지운다). 이 파일 하나로 자동배포와 약속한다."""
    try:
        if sha:
            with open(DEPLOY_PIN_FILE, 'w', encoding='utf-8') as f:
                f.write(sha)
        elif os.path.exists(DEPLOY_PIN_FILE):
            os.remove(DEPLOY_PIN_FILE)
        return True
    except Exception as e:
        print(f'⚠️ [고정 표시 기록 실패] {e}')
        return False


def _recent_commits(limit=VERSION_LIST_MAX):
    """origin/main 의 최근 커밋 목록. [{sha, short, date, subject}]"""
    out, ok = _git('log', f'-{int(limit)}', '--date=format:%Y-%m-%d %H:%M',
                   '--pretty=%H\x1f%h\x1f%ad\x1f%s', 'origin/main')
    if not ok:
        # origin/main 을 모르는 환경(로컬 개발 등)에서는 현재 갈래로 대신 본다
        out, ok = _git('log', f'-{int(limit)}', '--date=format:%Y-%m-%d %H:%M',
                       '--pretty=%H\x1f%h\x1f%ad\x1f%s')
    rows = []
    for line in (out or '').splitlines():
        parts = line.split('\x1f')
        if len(parts) == 4:
            rows.append({'sha': parts[0], 'short': parts[1],
                         'date': parts[2], 'subject': parts[3]})
    shas = [r['sha'] for r in rows]
    ui = _commits_with_version_ui(shas)
    nums = _version_nums(shas)
    for r in rows:
        r['num'] = nums.get(r['sha'], 0)
        r['label'] = ('V%d' % r['num']) if r['num'] else r['short']
        r['has_ui'] = (r['sha'] in ui) if ui is not None else None
    return rows


def _version_nums(shas):
    """여러 버전의 번호를 한꺼번에. {sha: 번호}

       ⚠️ 커밋마다 세면 20번을 부른다. 맨 위와 맨 아래만 세보고 차이가 딱 맞으면
          (= 그 구간이 한 줄로 이어져 있으면) 사이는 빼기로 채운다. 2번이면 끝난다.
          갈라졌다 합쳐진 구간이면 딱 안 맞으므로, 그때만 하나씩 센다.
    """
    if not shas:
        return {}
    top = _version_num(shas[0])
    bot = _version_num(shas[-1])
    if top and bot and (top - bot) == (len(shas) - 1):
        return {sha: top - i for i, sha in enumerate(shas)}
    return {sha: _version_num(sha) for sha in shas}


def _version_num(sha):
    """그 커밋까지 쌓인 커밋 수 = V번호. 자동으로 매겨지고 다시 안 바뀐다."""
    out, ok = _git('rev-list', '--count', sha, timeout=15)
    try:
        return int(out) if ok else 0
    except ValueError:
        return 0


def _commits_with_version_ui(shas):
    """준 버전들 중 이 '버전' 화면이 들어 있는 것들. 모르면 None.

       ⚠️ 없는 버전으로 되돌리면 조종실에서 돌아올 방법이 사라진다
          (서버에 직접 들어가 고정 파일을 지워야 한다). 미리 알려주려고 본다.

       ⚠️ 찾을 글자는 반드시 쪼개서 만든다. 통째로 적으면 '이 함수 자신'이 걸려서
          어떤 버전이든 '있음'으로 나온다(실제로 그렇게 틀렸다).

       ⚠️ '처음 들어온 커밋 뒤는 전부 있다'로 보면 안 된다 — 뺐다가 다시 넣은
          이력이 있으면 틀린다. git grep 은 여러 버전을 한 번에 받으므로
          한 번 불러서 정확하게 가른다.
    """
    if not shas:
        return set()
    marker = '/api/' + 'version/switch'
    out, ok = _git('grep', '-l', marker, *shas, '--', 'server.py', timeout=40)
    if not ok and not out:
        return None          # 못 봤으면 표시하지 않는다(틀린 표시보다 낫다)
    got = set()
    for line in (out or '').splitlines():
        # 'e288b1e...:server.py' 모양으로 온다
        head = line.split(':', 1)[0].strip()
        if head:
            got.add(head)
    return got


def _restart_services():
    """서비스를 재시작한다. 권한이 없으면 조용히 실패하고 자동배포에 맡긴다.

       ⚠️ 이 명령이 지금 이 프로세스를 죽인다. 그래서 응답을 먼저 보낸 뒤
          딴 갈래에서 잠깐 있다가 부른다.
    """
    for unit in ('livemaster', 'toon-listener'):
        try:
            r = subprocess.run(['sudo', '-n', 'systemctl', 'restart', unit],
                               capture_output=True, text=True, encoding='utf-8',
                               errors='replace', timeout=30)
            if r.returncode == 0:
                print(f'🔄 [버전 전환] {unit} 재시작', flush=True)
            else:
                print(f'⚠️ [버전 전환] {unit} 재시작 권한 없음 — 자동배포가 2분 안에 처리합니다',
                      flush=True)
        except Exception as e:
            print(f'⚠️ [버전 전환] {unit} 재시작 실패: {e} — 자동배포에 맡깁니다', flush=True)


# 이 프로세스가 켜질 때 어떤 버전이었는지. 파일은 바뀌었는데 재시작이 안 됐으면
# 이 값과 현재 HEAD 가 달라진다 — 그때 화면에 '아직 안 바뀌었다'고 알려야 한다.
RUNNING_SHA = _git('rev-parse', 'HEAD')[0] or ''


@app.route('/api/version/list', methods=['GET'])
def api_version_list():
    """고를 수 있는 버전 목록과 지금 돌고 있는 버전."""
    head, ok = _git('rev-parse', 'HEAD')
    if not ok:
        return jsonify({'status': 'error',
                        'message': '이 서버는 git 으로 배포된 것이 아니라 버전을 바꿀 수 없습니다'}), 400
    _git('fetch', '--quiet', 'origin', 'main', timeout=20)
    subj, _ = _git('log', '-1', '--pretty=%s')
    date, _ = _git('log', '-1', '--date=format:%Y-%m-%d %H:%M', '--pretty=%ad')
    num = _version_num(head)
    run_num = _version_num(RUNNING_SHA) if RUNNING_SHA else 0
    # ⚠️ '파일이 이 버전' 과 '지금 돌고 있는 코드가 이 버전' 은 다르다.
    #    재시작이 안 됐으면 파일만 바뀌고 옛 코드가 계속 돈다.
    return jsonify({'status': 'success',
                    'current': {'sha': head, 'short': head[:8], 'subject': subj, 'date': date,
                                'num': num, 'label': ('V%d' % num) if num else head[:8]},
                    'running_sha': RUNNING_SHA,
                    'running_label': ('V%d' % run_num) if run_num else RUNNING_SHA[:8],
                    'needs_restart': bool(RUNNING_SHA and head and RUNNING_SHA != head),
                    'pinned': _pinned_sha(),
                    'commits': _recent_commits()})


@app.route('/api/version/switch', methods=['POST'])
def api_version_switch():
    """고른 버전으로 옮기고 재시작한다."""
    body = request.get_json(silent=True) or {}
    want = str(body.get('sha') or '').strip()
    if not want:
        return jsonify({'status': 'error', 'message': '버전을 골라주세요'}), 400

    _git('fetch', '--quiet', 'origin', 'main', timeout=25)
    # ⚠️ 목록에 있는 것만 허용한다. 아무 번호나 받으면 남의 갈래 코드를 돌릴 수 있다.
    allowed = {c['sha'] for c in _recent_commits()}
    if want not in allowed:
        return jsonify({'status': 'error',
                        'message': '목록에 없는 버전입니다 (최근 %d개 중에서만 고를 수 있습니다)'
                                   % VERSION_LIST_MAX}), 400

    head, _ = _git('rev-parse', 'HEAD')
    if head == want:
        _write_pin(want)
        return jsonify({'status': 'success', 'message': '이미 그 버전으로 돌고 있습니다',
                        'restarting': False})

    # 옮기기는 여기서 바로 한다(빠르고, 실패하면 재시작도 하지 않는다)
    _write_pin(want)
    # ⚠️ --force 가 필요하다. 서버에서 파일이 하나라도 손대져 있으면 그냥 checkout 은
    #    거부한다. 어차피 자동배포도 매번 reset --hard 로 밀어버리므로(= 서버의 손댄 내용은
    #    보존되지 않는 것이 이 서버의 규칙이다) 같은 규칙으로 맞춘다.
    out, ok = _git('checkout', '--quiet', '--force', '--detach', want, timeout=40)
    if not ok:
        _write_pin(None)
        return jsonify({'status': 'error',
                        'message': '버전을 옮기지 못했습니다. 서버 상태를 확인해주세요'}), 500

    subj, _ = _git('log', '-1', '--pretty=%s')
    print(f'🕹️ [버전 전환] {head[:8]} → {want[:8]} · {subj}', flush=True)

    # 응답을 먼저 보내고 재시작한다 — 재시작이 지금 이 프로세스를 죽이기 때문이다.
    threading.Timer(1.0, _restart_services).start()
    lbl = 'V%d' % _version_num(want) if _version_num(want) else want[:8]
    return jsonify({'status': 'success', 'restarting': True,
                    'sha': want, 'short': want[:8], 'subject': subj, 'label': lbl,
                    'message': f'{lbl} 로 옮겼습니다. 곧 다시 시작합니다'})


@app.route('/api/version/latest', methods=['POST'])
def api_version_latest():
    """고정을 풀고 최신(main)으로 돌아간다."""
    _git('fetch', '--quiet', 'origin', 'main', timeout=25)
    remote, ok = _git('rev-parse', 'origin/main')
    if not ok:
        # ⚠️ 500 이 아니라 400 이다. 서버가 고장난 게 아니라 '여기서는 이 기능을 쓸 수
        #    없다'는 상황이다(git 으로 배포된 서버가 아님). 500 을 주면 조종실이
        #    '서버 이상'으로 보고 재시도한다.
        return jsonify({'status': 'error',
                        'message': '이 서버는 git 으로 배포된 것이 아니라 버전을 바꿀 수 없습니다'}), 400
    _write_pin(None)
    head, _ = _git('rev-parse', 'HEAD')
    if head == remote:
        return jsonify({'status': 'success', 'message': '이미 최신입니다', 'restarting': False})
    out, ok = _git('checkout', '--quiet', '--force', '-B', 'main', 'origin/main', timeout=40)
    if not ok:
        return jsonify({'status': 'error',
                        'message': '최신으로 되돌리지 못했습니다. 서버 상태를 확인해주세요'}), 500
    print(f'🕹️ [버전 전환] 최신으로 복귀 → {remote[:8]}', flush=True)
    threading.Timer(1.0, _restart_services).start()
    return jsonify({'status': 'success', 'restarting': True,
                    'sha': remote, 'short': remote[:8],
                    'message': '최신으로 되돌렸습니다. 곧 다시 시작합니다'})


@app.route('/api/patchnotes', methods=['GET'])
def api_patchnotes():
    """저장소의 PATCHNOTES.md 를 읽어 조종실 시스템 탭에 보여준다.

    파일을 그대로 읽으므로 배포하면 곧바로 최신 내용이 뜬다(따로 DB에 넣지 않는다).
    파싱은 '## 날짜' 아래 '- [분류] 내용' 만 본다.
    """
    path = os.path.join(BASE_DIR, 'PATCHNOTES.md')
    if not os.path.exists(path):
        path = os.path.join(BUNDLE_DIR, 'PATCHNOTES.md')
    try:
        with open(path, 'r', encoding='utf-8') as f:
            text = f.read()
    except Exception as e:
        return jsonify({"status": "error", "message": f"패치노트를 읽지 못했습니다: {e}"}), 500

    releases, cur = [], None
    for line in text.splitlines():
        line = line.rstrip()
        if line.startswith('## '):
            cur = {"date": line[3:].strip(), "items": []}
            releases.append(cur)
        elif line.startswith('- ') and cur is not None:
            body = line[2:].strip()
            kind = ''
            if body.startswith('['):
                end = body.find(']')
                if end > 0:
                    kind = body[1:end].strip()
                    body = body[end + 1:].strip()
            cur['items'].append({"kind": kind, "text": body})
    return jsonify({"status": "success", "releases": releases})


# 🎬 고액후원 영상 — 유튜브 대신 mp4 파일을 쓸 수 있게 한다.
#
# ⚠️ 유튜브 임베드는 방송에 쓰기엔 약점이 있다: 재생 전 광고가 붙을 수 있고, 끝나면
#    추천 영상 썸네일이 뜨고, 로고와 제목이 화면에 남는다. 고액 후원 연출 끝에 남의
#    영상 썸네일이 뜨는 셈이다. 게다가 '끝났다'를 postMessage 로 물어보는 구조라
#    놓치면 20분 안전장치가 돌 때까지 화면을 점유한다.
#    파일은 <video> 의 onended 로 확실히 끝나고, 광고도 로고도 없다.
#
# ⚠️ 파일은 Supabase Storage 에 둔다. 서버 디스크에 두면 서버를 다시 세팅할 때
#    통째로 사라지는데, 시그니처는 이미 Supabase 라 영상만 취약해진다.
#    저장 위치가 바뀌어도 화면은 손댈 필요가 없다 — 오버레이는 '주소'만 보고
#    유튜브인지 파일인지 알아서 판단한다.
ACCT_VIDEO_TYPES = {'mp4': 'video/mp4', 'webm': 'video/webm',
                    'mov': 'video/quicktime', 'm4v': 'video/x-m4v'}
ACCT_VIDEO_MAX_MB = 60


@app.route('/api/account/video/upload', methods=['POST'])
def api_account_video_upload():
    """금액대 한 칸에 영상 파일을 올린다. form: tier(번호), file"""
    try:
        # ⚠️ 파일 검사를 먼저 한다. exe 를 거부하는 일이 저장소 설정 여부에 달려 있으면,
        #    저장소가 잠깐 어긋난 사이에는 무엇을 올려도 같은 오류만 돌아와
        #    무엇이 잘못됐는지 알 수 없다. 저장소는 실제로 올리기 직전에 확인한다.
        try:
            idx = int(request.form.get('tier'))
        except (TypeError, ValueError):
            return jsonify({'status': 'error', 'message': '구간 번호가 필요합니다'}), 400
        f = request.files.get('file')
        if not f or not f.filename:
            return jsonify({'status': 'error', 'message': '영상 파일을 골라주세요'}), 400
        ext = (f.filename.rsplit('.', 1)[-1] or '').lower()
        if ext not in ACCT_VIDEO_TYPES:
            return jsonify({'status': 'error',
                            'message': f"{ext or '?'} 형식은 쓸 수 없습니다 (mp4 · webm · mov · m4v)"}), 400

        data = f.read()
        mb = len(data) / 1024 / 1024
        if mb > ACCT_VIDEO_MAX_MB:
            return jsonify({'status': 'error',
                            'message': f'파일이 {mb:.0f}MB 입니다. {ACCT_VIDEO_MAX_MB}MB 이하로 줄여주세요'}), 400
        if not data:
            return jsonify({'status': 'error', 'message': '빈 파일입니다'}), 400

        with file_lock:
            state = load_data()
            tiers = state.get('account_video_tiers') or []
            if not (0 <= idx < len(tiers)):
                return jsonify({'status': 'error', 'message': '없는 구간입니다'}), 400
            tier = tiers[idx]
            old = (tier.get('video') or '').strip()

        if not _supabase_ready():
            return jsonify({'status': 'error',
                            'message': '영상 보관소(Supabase)가 설정되지 않아 올릴 수 없습니다'}), 503

        # ⚠️ 올리기는 락 밖에서 한다. 60MB 를 서울까지 보내는 동안 락을 쥐고 있으면
        #    그동안 후원 접수·점수 지급이 통째로 멈춘다.
        ver = int(time.time())
        path = f"videos/acct_{tier.get('min')}.{ext}"
        url = storage_upload(path, data, ACCT_VIDEO_TYPES[ext]) + f'?v={ver}'

        with file_lock:
            state = load_data()
            tiers = state.get('account_video_tiers') or []
            if 0 <= idx < len(tiers):
                tiers[idx]['video'] = url
                state['account_video_tiers'] = tiers
                save_data(state, sync=True)
                broadcast_event('update', state)

        # 확장자가 바뀌면 옛 파일이 남는다(acct_200000.mov 를 mp4 로 갈아끼운 경우).
        # 실패해도 새 영상은 이미 걸렸으므로 조용히 넘어간다.
        if old.startswith('http') and '/storage/v1/object/public/' in old and old.split('?')[0] != url.split('?')[0]:
            storage_delete_by_url(old)

        print(f"  🎬 [고액후원 영상] {tier.get('label')} 구간에 {ext} {mb:.1f}MB 올림")
        return jsonify({'status': 'success', 'url': url, 'label': tier.get('label'),
                        'size_mb': round(mb, 1)})
    except HTTPException:
        # ⚠️ 본문이 상한(80MB)을 넘으면 파일을 읽는 순간 Flask 가 413 을 던진다.
        #    아래 except 가 그걸 삼키면 운영자에게 "서버 오류" 로 보여서,
        #    파일을 줄이면 된다는 걸 알 방법이 없다. 그대로 올려보낸다.
        raise
    except Exception as e:
        print(f'[고액후원 영상 업로드 오류] {e}')
        return jsonify({'status': 'error', 'message': str(e)}), 500


@app.route('/api/account/stop', methods=['POST'])
def api_account_stop_video():
    """재생 중인 영상을 즉시 끈다. 잘못 눌렀거나 길 때 손으로 멈출 수 있어야 한다."""
    broadcast_event('account_video_stop', {})
    return jsonify({"status": "ok"})


# ⚠️ 아래 둘은 오버레이가 부르므로 로그인을 요구할 수 없다. 대신 '지금 그럴 상황인가'를
#    상태로 확인해, 아무 때나 밖에서 불러 방송을 흔드는 것을 막는다.
@app.route('/api/roulette/winner', methods=['POST'])
def api_roulette_winner():
    try:
        req_data = request.get_json(silent=True) or {}
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
            # ⚠️ 돌고 있지 않은데 결과가 들어오면 밖에서 부른 것이다.
            #    (오버레이는 자기가 돌린 룰렛이 멈출 때만 부른다)
            #    로그인한 요청은 그대로 통과시킨다 — 조종실 조작이나 시험용이다.
            if not state['roulette'].get('is_spinning') and not request_is_authed():
                print(f"⛔ [룰렛 결과 거부] 돌고 있지 않은데 결과가 들어왔습니다 "
                      f"(ip={request.remote_addr}, 이름={winner_name})", flush=True)
                return jsonify({"status": "error", "message": "지금은 룰렛이 돌고 있지 않습니다"}), 409

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
        # ⚠️ 여기 담기는 것은 '방송 화면의 모든 위젯 위치'다. 잘못 쓰면 오버레이가
        #    통째로 흐트러지고, 되돌릴 방법이 없다.
        #    ① 본문이 깨졌거나 사전이 아니면 아예 손대지 않는다
        #      (예전에는 request.json 이 그 자리에서 터져 500 이 났고, null 을 보내면
        #       파일에 'null' 이 적혀 배치가 날아갔다)
        data = request.get_json(silent=True)
        if not isinstance(data, dict):
            return jsonify({"status": "error",
                            "message": "레이아웃 내용(JSON 사전)이 필요합니다"}), 400
        # ② 임시 파일에 다 쓴 뒤 갈아끼운다. 쓰는 도중에 서버가 죽어도
        #    예전 배치가 그대로 남는다(반쯤 쓰인 파일은 읽을 수 없다).
        tmp = LAYOUT_FILE + '.tmp'
        with open(tmp, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, LAYOUT_FILE)
        broadcast_event('layout', data)
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
            state = json.loads(state_json)
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
        req = request.get_json(silent=True) or {}
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
        req_data = request.get_json(silent=True) or {}
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

@app.route('/api/reaction/next', methods=['POST'])
def next_reaction():
    try:
        data = request.get_json(silent=True) or {}
        pop_id = data.get('id')
        
        with file_lock:
            state = load_data()
            queue = state.get('reaction_queue', [])
            
            # ⚠️ 이 경로는 무인증으로 열려 있다(오버레이가 재생을 끝내고 스스로 넘겨야 하므로).
            #    그래서 '번호 없이 무조건 pop' 은 허용하면 안 된다 — 주소만 알면 누구나
            #    빈 POST 를 반복해 대기 중인 시그니처를 하나씩 지울 수 있다.
            #    돈을 낸 후원의 시그니처가 재생도 없이 사라지는데 흔적도 안 남는다.
            #    번호를 대면(오버레이가 하는 일) 큐 머리와 일치할 때만 지운다.
            #    번호 없이 넘기는 건 조종실·후원 콘솔의 '건너뛰기' 뿐이라 로그인을 요구한다.
            if not pop_id and not request_is_authed():
                return jsonify({"status": "error",
                                "message": "넘길 항목의 번호(id)가 필요합니다"}), 400

            if queue:
                if not pop_id or queue[0].get('id') == pop_id:
                    queue.pop(0)
                
            if not queue:
                state['reaction_mode'] = False
                
            save_data(state)
            broadcast_event('update', state)
        # 오버레이가 이 응답의 state 를 그대로 써서 다음 시그니처를 즉시 재생한다
        # (예전엔 pop 후 /api/data 를 한 번 더 불러 왕복이 2회였고, 그 사이 SSE 와 겹쳐
        #  대기열이 깊을 때 재생이 불안정했다. 이제 왕복 1회로 줄여 겹침/지연을 낮춘다.)
        # ⚠️ 여기도 반드시 state_for_client 를 거쳐야 한다.
        #    예전에는 strip_private_state 만 불러서 시그게임 마스킹이 빠져 있었고,
        #    시그니처가 재생될 때마다 덮인 카드 16장의 정체가 통째로 나갔다.
        out_state = state_for_client(state, request_is_authed())
        return jsonify({"status": "success", "message": "Popped reaction", "state": out_state})
    except Exception as e:
        print(f"Error in next_reaction: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

# ==========================================
# 🃏 시그 뒤집기 게임
# ==========================================
# 규칙: 시그니처를 덮어 깔고, 그중 몇 장(기본 5장)을 뒤집는다.
#       뒤집힌 것이 이번 판의 '목표'이고, 제한 시간 안에 그 시그니처를 후원으로 받아내면 달성이다.
#
# ⚠️ 달성 표시는 전부 사람이 누른다. 후원이 들어올 때 자동으로 찍지 않는다 —
#    후원은 즉시 접수되지만 시그니처는 대기열에 쌓였다가 나중에 재생되기 때문에,
#    자동으로 찍으면 아직 화면에 나오지도 않은 시그니처가 이미 달성된 것처럼 보인다.
#    타이밍은 진행자가 잡아야 연출이 산다.
#
# 상태는 전부 서버가 들고 SSE 로 뿌린다. 원본 프로그램은 창끼리 localStorage 로 맞췄는데,
# OBS 브라우저 소스는 조종실 크롬과 저장소를 공유하지 않아 애초에 동기화가 되지 않았다.
SIGGAME_MAX_CARDS = 36   # 6x6. 이보다 크면 상태가 무거워지고 OBS 가 버벅인다.


def _siggame_state(state):
    """항상 온전한 모양의 게임 상태를 돌려준다(예전 저장본에 없던 키 보정)."""
    g = state.get('siggame')
    if not isinstance(g, dict):
        g = copy.deepcopy(DEFAULT_STATE['siggame'])
        state['siggame'] = g
    for k, v in DEFAULT_STATE['siggame'].items():
        g.setdefault(k, copy.deepcopy(v))
    if not isinstance(g.get('timer'), dict):
        g['timer'] = copy.deepcopy(DEFAULT_STATE['siggame']['timer'])
    for k in ('cards', 'picks'):
        if not isinstance(g.get(k), list):
            g[k] = []
    return g


def _siggame_save(state, g):
    state['siggame'] = g
    save_data(state)
    broadcast_event('update', state)


@app.route('/api/siggame/picks', methods=['POST'])
def api_siggame_picks():
    """이번 판에 깔 시그니처를 고른다.

    body: {"picks": [12345, 12346, ...]}   (시그니처 id 목록)
    ⚠️ 여기에는 감출 것이 없다. 어느 카드가 무엇인지는 '깔고 나서' 감춰진다(mask_siggame).
    """
    data = request.get_json(silent=True) or {}
    ids = data.get('picks')
    if not isinstance(ids, list) or not ids:
        return jsonify({"status": "error", "message": "시그니처를 하나 이상 골라주세요"}), 400
    if len(ids) > SIGGAME_MAX_CARDS:
        return jsonify({"status": "error",
                        "message": "카드는 최대 %d장까지입니다 (지금 %d장)"
                                   % (SIGGAME_MAX_CARDS, len(ids))}), 400

    by_id = {int(s['id']): s for s in (supabase_list_signatures() or []) if s.get('id') is not None}
    picks, missing = [], []
    for raw_id in ids:
        try:
            sid = int(raw_id)
        except (TypeError, ValueError):
            continue
        s = by_id.get(sid)
        if not s:
            missing.append(sid)
            continue
        picks.append({"sig_id": sid, "title": s.get('title') or '',
                      "image": s.get('image_url') or '', "amount": s.get('amount')})
    if not picks:
        return jsonify({"status": "error", "message": "고른 시그니처를 찾을 수 없습니다"}), 400

    with file_lock:
        state = load_data()
        g = _siggame_state(state)
        g['picks'] = picks
        _siggame_save(state, g)
    if missing:
        print("⚠️ [시그게임] 고른 시그니처 %d장을 찾을 수 없어 뺐습니다: %s" % (len(missing), missing), flush=True)
    print("🃏 [시그게임] 시그니처 %d장 선택" % len(picks), flush=True)
    return jsonify({"status": "success", "count": len(picks), "missing": missing,
                    "requested": len(ids)})


@app.route('/api/siggame/deal', methods=['POST'])
def api_siggame_deal():
    """고른 시그니처를 무작위 자리에 깔고 전부 덮는다."""
    data = request.get_json(silent=True) or {}
    try:
        minutes = max(0, min(180, int(data.get('minutes', 10))))
    except (TypeError, ValueError):
        minutes = 10

    with file_lock:
        state = load_data()
        g = _siggame_state(state)
        picks = list(g.get('picks') or [])
        if not picks:
            return jsonify({"status": "error",
                            "message": "먼저 시그니처를 골라주세요 (아래 목록에서 선택)"}), 400
        try:
            target = int(data.get('target', g.get('target') or 5))
        except (TypeError, ValueError):
            target = 5
        target = max(1, min(len(picks), target))

        random.shuffle(picks)   # 자리를 섞는다 — 번호만 보고는 무엇인지 알 수 없어야 한다
        n = len(picks)
        cols = int(math.ceil(math.sqrt(n)))
        rows = int(math.ceil(n / cols))
        g['cards'] = [{"id": i + 1, "sig_id": p.get('sig_id'), "image": p.get('image'),
                       "title": p.get('title'), "amount": p.get('amount'),
                       "state": "HIDDEN", "doneAt": None, "flippedAt": None}
                      for i, p in enumerate(picks)]
        g.update({"cols": cols, "rows": rows, "enabled": True, "target": target,
                  "compact": False,     # 새 판이면 올린 상태를 푼다
                  "timer": {"status": "STOPPED", "timeLeft": minutes * 60, "expiresAt": None},
                  "action": {"type": "PLACE", "ts": int(time.time() * 1000)}})
        _siggame_save(state, g)
    print("🃏 [시그게임] %d장 배치 (%dx%d, 목표 %d장, %d분)" % (n, cols, rows, target, minutes), flush=True)
    return jsonify({"status": "success", "count": n, "target": target, "cols": cols, "rows": rows})


@app.route('/api/siggame/shuffle', methods=['POST'])
def api_siggame_shuffle():
    """자리를 다시 섞고 전부 덮는다(달성 기록도 초기화된다 — 새 판이나 마찬가지다)."""
    with file_lock:
        state = load_data()
        g = _siggame_state(state)
        cards = g.get('cards') or []
        if not cards:
            return jsonify({"status": "error", "message": "먼저 카드를 깔아주세요"}), 400
        faces = [{"sig_id": c.get('sig_id'), "image": c.get('image'),
                  "title": c.get('title'), "amount": c.get('amount')} for c in cards]
        random.shuffle(faces)
        g['cards'] = [{"id": c["id"], "sig_id": f["sig_id"], "image": f["image"],
                       "title": f["title"], "amount": f["amount"],
                       "state": "HIDDEN", "doneAt": None, "flippedAt": None}
                      for c, f in zip(cards, faces)]
        g['compact'] = False        # 섞으면 목표가 사라지므로 올린 상태도 푼다
        g['action'] = {"type": "SHUFFLE", "ts": int(time.time() * 1000),
                       "animIndex": random.randint(1, 4)}
        n = len(cards)
        _siggame_save(state, g)
    print("🃏 [시그게임] 카드 %d장 다시 섞음" % n, flush=True)
    return jsonify({"status": "success"})


@app.route('/api/siggame/flip', methods=['POST'])
def api_siggame_flip():
    """카드 한 장을 뒤집는다. 뒤집힌 카드가 이번 판의 '목표'가 된다.

    ⚠️ 목표 장수(target)를 넘겨 뒤집지 못하게 막는다. 실수로 하나 더 뒤집으면
       참가자가 받아야 할 금액이 늘어난다 — 돈이 걸린 문제라 되돌리기보다 막는 쪽이 낫다.
    ⚠️ '크게 보이는 2초'는 서버 상태로 두지 않는다. 요청이 실패하거나 조종실이 닫혔을 때
       카드가 확대된 채 방송에 박히기 때문이다. 뒤집은 시각만 남기고 연출은 화면이 판단한다.
    """
    data = request.get_json(silent=True) or {}
    try:
        cid = int(data.get('id'))
    except (TypeError, ValueError):
        return jsonify({"status": "error", "message": "카드 번호가 필요합니다"}), 400
    now_ms = int(time.time() * 1000)
    with file_lock:
        state = load_data()
        g = _siggame_state(state)
        cards = g.get('cards') or []
        found = next((c for c in cards if c.get('id') == cid), None)
        if not found:
            return jsonify({"status": "error", "message": "%d번 카드가 없습니다" % cid}), 404
        if found.get('state') == 'REVEALED':
            return jsonify({"status": "success", "id": cid, "already": True,
                            "title": found.get('title') or ''})
        opened = sum(1 for c in cards if c.get('state') == 'REVEALED')
        target = int(g.get('target') or 5)
        if opened >= target:
            return jsonify({"status": "error",
                            "message": "이미 %d장을 뒤집었습니다 (목표 %d장)" % (opened, target)}), 400
        found['state'] = 'REVEALED'
        found['flippedAt'] = now_ms
        g['action'] = {"type": "FLIP", "ts": now_ms, "id": cid}
        title = found.get('title') or ''
        amount = found.get('amount')
        left = target - (opened + 1)
        _siggame_save(state, g)
    # ⚠️ 여기서 예외가 나면 이미 저장·전파가 끝난 뒤라, 카드는 뒤집혔는데 조종실엔 500 이 뜬다.
    #    금액이 숫자가 아니어도 로그 한 줄 때문에 요청이 실패하면 안 된다.
    try:
        amount_txt = format(int(amount or 0), ',')
    except (TypeError, ValueError):
        amount_txt = str(amount)
    print("🃏 [시그게임] %d번 뒤집음 → '%s' (%s원) / 더 뒤집을 수 있는 카드 %d장"
          % (cid, title, amount_txt, left), flush=True)
    return jsonify({"status": "success", "id": cid, "title": title,
                    "amount": amount, "remaining_flips": left})


@app.route('/api/siggame/done', methods=['POST'])
def api_siggame_done():
    """목표 카드를 손으로 달성/취소 처리한다.

    ⚠️ 달성은 전부 이 경로로만 찍힌다. 후원이 들어올 때 자동으로 찍지 않는다 —
       후원은 즉시 접수되지만 시그니처는 대기열에 쌓였다가 나중에 재생되므로,
       자동으로 찍으면 아직 화면에 안 나온 시그니처가 이미 달성된 것처럼 보인다.
    """
    data = request.get_json(silent=True) or {}
    try:
        cid = int(data.get('id'))
    except (TypeError, ValueError):
        return jsonify({"status": "error", "message": "카드 번호가 필요합니다"}), 400
    want = data.get('done')
    now_ms = int(time.time() * 1000)
    with file_lock:
        state = load_data()
        g = _siggame_state(state)
        found = next((c for c in (g.get('cards') or []) if c.get('id') == cid), None)
        if not found:
            return jsonify({"status": "error", "message": "%d번 카드가 없습니다" % cid}), 404
        if found.get('state') != 'REVEALED':
            return jsonify({"status": "error", "message": "아직 뒤집지 않은 카드입니다"}), 400
        done = (not found.get('doneAt')) if want is None else bool(want)
        found['doneAt'] = now_ms if done else None
        g['action'] = {"type": "DONE", "ts": now_ms, "id": cid} if done else None
        _siggame_save(state, g)
    return jsonify({"status": "success", "id": cid, "done": done})


@app.route('/api/siggame/allclear', methods=['POST'])
def api_siggame_allclear():
    """남은 목표를 전부 달성 처리하고 올클리어 연출을 터뜨린다 — '한 방' 버튼.

    ⚠️ 다 채웠다고 자동으로 터지지는 않는다. 언제 터뜨릴지는 진행자가 정한다.
       그리고 하나씩 채우다 누르는 게 아니라, '한 번에 몰아서 쏜' 후원이 들어왔을 때
       목표를 일일이 찍을 겨를이 없으니 버튼 하나로 남은 것까지 전부 채우면서 터뜨린다.
       (예전에는 다 채워야만 눌렸는데, 정작 이 연출이 필요한 순간은 한 방에 다 채운
        순간이라 진행자가 5장을 급하게 하나씩 찍고 있어야 했다)
    """
    with file_lock:
        state = load_data()
        g = _siggame_state(state)
        goals = [c for c in (g.get('cards') or []) if c.get('flippedAt')]
        if not goals:
            return jsonify({"status": "error", "message": "뒤집은 카드가 없습니다"}), 400
        now_ms = int(time.time() * 1000)
        left = [c for c in goals if not c.get('doneAt')]
        for c in left:
            c['doneAt'] = now_ms
        g['action'] = {"type": "ALLCLEAR", "ts": now_ms, "count": len(goals)}
        n, filled = len(goals), len(left)
        _siggame_save(state, g)
    print("🎉 [시그게임] 올클리어! (%d장, 이번에 채운 %d장)" % (n, filled), flush=True)
    return jsonify({"status": "success", "count": n, "filled": filled})


# 한 줄에 나란히 세워도 카드가 알아볼 만한 최대 장수.
# 6칸부터는 폭이 6등분이라 그림도 금액도 작아져서 올리는 의미가 없다.
SIGGAME_LIFT_MAX = 5



@app.route('/api/siggame/lift', methods=['POST'])
def api_siggame_lift():
    """목표만 한 줄로 올리거나(on) 판 전체로 되돌린다(off).

       ⚠️ 예전에는 목표를 다 뒤집는 순간 화면이 저 혼자 올렸다. 진행자가
          멘트를 칠 새도 없이 판이 바뀌고, 되돌릴 방법도 없었다.
          이제 언제 올릴지는 진행자가 정한다.
    """
    data = request.get_json(silent=True) or {}
    want = data.get('on')
    with file_lock:
        state = load_data()
        g = _siggame_state(state)
        goals = [c for c in (g.get('cards') or []) if c.get('flippedAt')]
        on = (not g.get('compact')) if want is None else bool(want)
        if on:
            if not goals:
                return jsonify({'status': 'error', 'message': '뒤집은 목표가 없습니다'}), 400
            if len(goals) > SIGGAME_LIFT_MAX:
                return jsonify({'status': 'error',
                                'message': '목표가 %d장이라 올리지 않습니다. 한 줄에 %d장까지만 알아볼 만합니다'
                                           % (len(goals), SIGGAME_LIFT_MAX)}), 400
        g['compact'] = on
        g['action'] = {'type': 'LIFT', 'ts': int(time.time() * 1000), 'on': on}
        _siggame_save(state, g)
    print('🃏 [시그게임] 목표만 올리기 %s (목표 %d장)' % ('켬' if on else '끔', len(goals)), flush=True)
    return jsonify({'status': 'success', 'compact': on, 'goals': len(goals)})


@app.route('/api/siggame/peek', methods=['POST'])
def api_siggame_peek():
    """안 뽑힌 카드가 뭐였는지 잠깐 까본다(목표만 올려둔 상태에서도).

       ⚠️ reveal 과 다르다. reveal 은 판을 영영 열어두는 '게임 끝' 동작이고,
          이건 '나머지 궁금하죠?' 하고 잠깐 보여주는 것이다. 목표 달성 판정과
          무관하도록 flippedAt 은 건드리지 않는다.
    """
    now_ms = int(time.time() * 1000)
    with file_lock:
        state = load_data()
        g = _siggame_state(state)
        cards = g.get('cards') or []
        if not cards:
            return jsonify({'status': 'error', 'message': '깔린 카드가 없습니다'}), 400
        rest = [c for c in cards if not c.get('flippedAt')]
        if not rest:
            return jsonify({'status': 'error', 'message': '안 뽑힌 카드가 없습니다'}), 400
        g['action'] = {'type': 'PEEK', 'ts': now_ms, 'count': len(rest)}
        _siggame_save(state, g)
    print('🃏 [시그게임] 나머지 %d장 까보기' % len(rest), flush=True)
    return jsonify({'status': 'success', 'count': len(rest)})


@app.route('/api/siggame/reveal', methods=['POST'])
def api_siggame_reveal():
    """남은 카드를 전부 공개한다(게임이 끝난 뒤 무엇이 있었는지 보여줄 때).

    ⚠️ 이건 '목표 추가'가 아니다. 공개만 하고 달성 판정에는 넣지 않기 위해
       flippedAt 을 남기지 않는다.
    """
    now_ms = int(time.time() * 1000)
    with file_lock:
        state = load_data()
        g = _siggame_state(state)
        if not (g.get('cards') or []):
            return jsonify({"status": "error", "message": "깔린 카드가 없습니다"}), 400
        for c in g['cards']:
            if c.get('state') != 'REVEALED':
                c['state'] = 'REVEALED'
                c['flippedAt'] = None   # 목표가 아니라 '구경용 공개'
        g['action'] = {"type": "REVEAL", "ts": now_ms}
        _siggame_save(state, g)
    print("🃏 [시그게임] 남은 카드 전체 공개", flush=True)
    return jsonify({"status": "success"})


@app.route('/api/siggame/timer', methods=['POST'])
def api_siggame_timer():
    """타이머 시작·일시정지·초기화.

    ⚠️ 남은 시간을 서버가 1초씩 세지 않는다. '끝나는 시각'만 두고 화면이 계산한다.
       그래야 오버레이를 새로 띄우거나 늦게 붙어도 시간이 어긋나지 않는다.
    """
    data = request.get_json(silent=True) or {}
    action = str(data.get('action') or '').upper()
    if action not in ('START', 'PAUSE', 'STOP'):
        return jsonify({"status": "error", "message": "action 은 START/PAUSE/STOP"}), 400
    now_ms = int(time.time() * 1000)
    with file_lock:
        state = load_data()
        g = _siggame_state(state)
        t = g['timer']
        if action == 'START' and t.get('status') != 'PLAYING':
            left = max(0, int(t.get('timeLeft') or 0))
            if left <= 0:
                return jsonify({"status": "error", "message": "남은 시간이 없습니다"}), 400
            t.update({"status": "PLAYING", "expiresAt": now_ms + left * 1000})
        elif action == 'PAUSE' and t.get('status') == 'PLAYING':
            left = max(0, int(((t.get('expiresAt') or now_ms) - now_ms) / 1000))
            t.update({"status": "PAUSED", "timeLeft": left, "expiresAt": None})
        elif action == 'STOP':
            try:
                minutes = int(data.get('minutes'))
            except (TypeError, ValueError):
                minutes = None
            left = minutes * 60 if minutes is not None else int(t.get('timeLeft') or 0)
            t.update({"status": "STOPPED", "timeLeft": max(0, left), "expiresAt": None})
        timer_out = dict(t)
        _siggame_save(state, g)
    return jsonify({"status": "success", "timer": timer_out})


@app.route('/api/siggame/set', methods=['POST'])
def api_siggame_set():
    """켜기/끄기, 투명도, 목표 장수 같은 설정."""
    data = request.get_json(silent=True) or {}
    with file_lock:
        state = load_data()
        g = _siggame_state(state)
        if 'enabled' in data:
            g['enabled'] = bool(data['enabled'])
        if 'opacity' in data:
            try:
                g['opacity'] = max(0.1, min(1.0, float(data['opacity'])))
            except (TypeError, ValueError):
                pass
        if 'target' in data:
            try:
                # 깔린 카드보다 많이 뒤집을 수는 없다. 넘겨두면 '③ 카드를 뒤집으세요 (5/10)'
                # 에서 영원히 멈추고, 오버레이도 목표만 남기는 화면으로 넘어가지 않는다.
                cap = len(g.get('cards') or []) or SIGGAME_MAX_CARDS
                g['target'] = max(1, min(cap, int(data['target'])))
            except (TypeError, ValueError):
                pass
        out = {"enabled": g['enabled'], "opacity": g['opacity'], "target": g['target']}
        _siggame_save(state, g)
    return jsonify({"status": "success", **out})


@app.route('/api/siggame/clear', methods=['POST'])
def api_siggame_clear():
    """판을 치운다. 고른 시그니처 목록은 남겨 다음 판에 그대로 다시 쓴다."""
    with file_lock:
        state = load_data()
        g = _siggame_state(state)
        g.update({"cards": [], "enabled": False, "action": None,
                  "timer": copy.deepcopy(DEFAULT_STATE['siggame']['timer'])})
        _siggame_save(state, g)
    print("🃏 [시그게임] 판을 치웠습니다 (고른 시그니처는 유지)", flush=True)
    return jsonify({"status": "success"})


@app.route('/api/reaction/pause', methods=['POST'])
def api_reaction_pause():
    """알림(시그니처) 재생을 잠시 멈추거나 다시 내보낸다.

    ⚠️ 큐는 건드리지 않는다. 멈춘 동안 들어온 후원은 그대로 쌓였다가 풀면 순서대로 나간다.
       큐를 지우는 '전체 비우기'(/api/reaction/stop)와 혼동하면 안 된다.
    ⚠️ 재생 중인 시그니처는 끊지 않는다. 오버레이가 '다음 것을 시작하지 않는' 방식으로 멈추므로,
       지금 나가고 있는 것은 끝까지 나가고 그 다음부터 멈춘다.
       (중간에 끊으면 돈 낸 후원자의 시그니처가 잘려나간다)

    body 에 paused 가 있으면 그 값으로, 없으면 현재값을 뒤집는다(버튼 한 개로 토글).
    """
    # ⚠️ request.json 은 Content-Type 이 application/json 이 아니면 415 를 던진다.
    #    이 엔드포인트는 '본문 없이 눌러서 토글'하는 쓰임이 정상이므로 그걸로 실패하면 안 된다.
    #    (실제로 콘솔 버튼이 헤더 없이 보내 415 로 막혔다)
    data = request.get_json(silent=True) or {}
    with file_lock:
        state = load_data()
        paused = bool(data['paused']) if 'paused' in data else not bool(state.get('reaction_paused'))
        state['reaction_paused'] = paused
        queued = len(state.get('reaction_queue') or [])
        save_data(state)
        broadcast_event('update', state)
    print(f"{'⏸️ 알림 일시정지' if paused else '▶️ 알림 재개'} (대기 {queued}건)", flush=True)
    return jsonify({"status": "success", "paused": paused, "queued": queued})

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
        data = request.get_json(silent=True) or {}
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

@app.route('/api/pending/remove/<don_id>', methods=['POST'])
def remove_pending_donation(don_id):
    """승인 대기함에서 특정 후원 한 건을 제거한다(전용 read-modify-write).
       pending_donations 는 /api/data 에서 서버 소유로 보호되므로, 승인/무시 시 이 엔드포인트로만 제거해야
       후원이 막 들어온 순간 조종실이 점수를 눌러도 새 후원이 안 사라진다."""
    try:
        with file_lock:
            state = load_data()
            pend = state.get('pending_donations', []) or []
            state['pending_donations'] = [d for d in pend if d.get('id') != don_id]
            save_data(state)
            broadcast_event('update', state)
        return jsonify({"status": "success", "message": "Removed from pending"})
    except Exception as e:
        print(f"Error in remove_pending_donation: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500


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
))


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
            state.update(body)
            state['version'] = (state.get('version') or 1) + 1
            save_data(state)
            broadcast_event('update', state)
        return jsonify({"status": "success", "patched": sorted(body.keys())})
    except Exception as e:
        print(f"Error in api_settings_patch: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500


def _match_team_of(state, member_name):
    """그 사람이 속한 대결 팀을 돌려준다. 팀전이 꺼져 있거나 소속이 없으면 None.

    ⚠️ 이름 비교는 양쪽 모두 공백을 떼고 한다. 팀원 이름은 점수판에서 골라 넣지만,
       나중에 점수판에서 이름을 고치면 팀원 목록에는 옛 이름이 남는다.
       그때는 조용히 합산이 멈춘다 — 조종실이 그 사실을 보여준다(팀원 칸에 회색 표시).
    """
    md = state.get('match_data') or {}
    if not md.get('active') or not md.get('team_mode'):
        return None
    want = str(member_name or '').strip()
    if not want:
        return None
    for team in (md.get('players') or []):
        for m in (team.get('members') or []):
            if str(m or '').strip() == want:
                return team
    return None


def _find_score_target(state, scope, name):
    """점수를 더할 대상 하나를 찾는다. 언제나 '이름'으로 찾는다 —
       랭킹은 기여도순으로 계속 재정렬되므로 위치 인덱스로 찾으면 엉뚱한 사람에게 돈이 들어간다.

    ⚠️ 이름을 비교할 때 양쪽 모두 앞뒤 공백을 뗀다.
       들어온 이름은 위에서 이미 strip 되는데 저장된 이름은 안 됐다. 그래서 이름 칸에
       공백을 하나만 더 눌러도('밍밍 ') 그 사람은 그때부터 점수를 받을 수 없었다.
       화면에는 '밍밍' 으로 멀쩡히 보이니 원인을 찾을 수도 없다.
       대결·점수판 양쪽 모두에서 재현된다.
    """
    want = str(name or '').strip()

    def same(v):
        return str(v or '').strip() == want

    if scope == 'bot':
        return state.get('bottom_fixed')
    if scope == 'match':
        md = state.get('match_data') or {}
        return next((p for p in (md.get('players') or []) if same(p.get('name'))), None)
    src = 'extra_bjs' if state.get('extra_game_active') else 'bjs'
    return next((b for b in (state.get(src) or []) if same(b.get('name'))), None)


@app.route('/api/score/add', methods=['POST'])
def api_score_add():
    """점수는 '더할 값'만 받아서 서버가 읽고-더하고-쓴다.

    ⚠️ 이 엔드포인트가 생긴 이유:
       폰(mobile.html)과 조종실은 둘 다 '상태 전체'를 POST 했고, /api/data 는 필드를 통째로
       교체한다(state.update). 그래서 같은 스냅샷을 들고 각자 점수를 더해 보내면 나중에 도착한
       쪽이 앞선 점수를 덮어썼다. 부하 테스트에서 동시 배정 12건 중 6건이 사라졌다.
       위험 구간은 SSE 전파 지연만큼인데 Render 실측이 약 0.5초라 사람이 충분히 부딪힌다.
       (자리 비운 사이 폰으로 배정하는데 PC 에서 오토파일럿이 돌고 있으면 정확히 그 조건이다)
       여기서는 스냅샷을 주고받지 않으므로 두 조작이 겹쳐도 둘 다 남는다.

    pending_id 를 함께 주면 '점수 지급'과 '대기함에서 제거'가 같은 잠금 안에서 끝난다.
    예전에는 왕복 두 번이라 그 사이에 실패하면 후원이 어디에도 없는 상태가 될 수 있었다.
    그 후원이 대기함에 이미 없으면 누군가 먼저 처리한 것이므로 점수를 더하지 않고
    already=True 로 답한다 — 폰과 PC 에서 같은 후원을 동시에 눌러도 두 번 들어가지 않는다.

    items 로 여러 명을 한 번에 줄 수 있다(반반·N분할). 한 명이라도 못 찾으면 아무것도 반영하지 않는다.
    """
    try:
        body = request.get_json(silent=True) or {}
        # scope 가 숫자로 오면 .strip() 에서 터진다 — 무엇이 와도 글자로 본다
        scope = str(body.get('scope') or 'rank').strip()
        if scope not in ('rank', 'bot', 'match'):
            return jsonify({"status": "error", "message": f"알 수 없는 scope: {scope}"}), 400

        raw = body.get('items') or [{"name": body.get('name'), "delta": body.get('delta'),
                                     "contribution": body.get('contribution')}]
        # 값 검증을 먼저 다 끝낸다 — 절반만 반영되는 일이 없게
        wanted = []
        for it in raw:
            name = str(it.get('name') or '').strip()
            if not name and scope != 'bot':
                return jsonify({"status": "error", "message": "name 이 비어 있다"}), 400
            try:
                delta = int(it.get('delta') or 0)
                contrib = delta if it.get('contribution') is None else int(it.get('contribution'))
            except (TypeError, ValueError):
                return jsonify({"status": "error", "message": "delta/contribution 이 숫자가 아니다"}), 400
            wanted.append((name, delta, contrib))

        # 🧠 이 후원이 누구에게 갔는지 기억해 둔다(다음 판단의 재료).
        #    조종실·폰이 배정할 때 donor 를 같이 보낸다. 없으면 그냥 기억하지 않는다.
        donor_name = (body.get('donor') or '').strip()
        donor_msg = (body.get('donor_message') or '').strip()
        want_log = bool(body.get('log', True))
        want_popup = bool(body.get('popup', False))
        want_takeover = bool(body.get('takeover', False))
        pending_id = body.get('pending_id')
        undo_log = body.get('undo_log')

        with file_lock:
            state = load_data()
            # 🛡️ 같은 후원을 두 곳에서 동시에 배정하면 점수가 두 번 들어간다.
            #    조종실도 '이미 처리됐나' 를 보지만 그건 각자 화면의 사본이라, 폰과 PC 가
            #    서로를 못 본다. 대기함에 그 후원이 남아 있는지는 서버만 확실히 안다.
            #    이미 없으면 '누군가 먼저 처리했다' 는 뜻이므로 점수를 더하지 않는다.
            if pending_id:
                _pend = state.get('pending_donations') or []
                if not any(d.get('id') == pending_id for d in _pend):
                    print(f'  ↩️ [이중 배정 방지] 이미 처리된 후원입니다 ({pending_id})', flush=True)
                    return jsonify({'status': 'success', 'already': True,
                                    'message': '이미 다른 기기에서 처리된 후원입니다'})
            src = 'extra_bjs' if state.get('extra_game_active') else 'bjs'
            prev_first = None
            if scope == 'rank':
                lst = state.get(src) or []
                prev_first = (lst[0].get('name') if lst else None)

            # ⚠️ 대상을 '전부 찾은 뒤에' 더한다. load_data() 는 살아 있는 메모리 상태를 돌려주므로,
            #    더하다가 중간에 빠져나가면 저장을 건너뛰어도 앞사람 점수는 이미 올라가 있다.
            #    (반반 지급에서 두 번째 이름이 오타일 때 첫 사람만 점수를 받는 사고가 난다)
            targets = []
            for name, delta, contrib in wanted:
                t = _find_score_target(state, scope, name)
                if t is None:
                    return jsonify({"status": "error",
                                    "message": f"'{name}' 을(를) 찾을 수 없습니다"}), 404
                targets.append((t, delta, contrib, t.get('name') or name))

            applied = []
            team_hits = []
            for t, delta, contrib, tname in targets:
                t['score'] = (t.get('score') or 0) + delta
                if scope == 'rank':
                    t['contribution'] = (t.get('contribution') or 0) + contrib
                    # ⚔️ 팀전: 이 사람이 어느 팀 소속이면 그 팀 점수도 같이 올린다.
                    #    대결판이 후원을 따라 실시간으로 움직여야 보는 재미가 있다.
                    team = _match_team_of(state, tname) if delta else None
                    if team is not None:
                        team['score'] = (team.get('score') or 0) + delta
                        team_hits.append((team.get('name'), tname, delta))
                applied.append({"name": tname, "delta": delta,
                                "score": t.get('score'), "contribution": t.get('contribution')})
            for tn, mn, dv in team_hits:
                print(f"  ⚔️ [팀전] {mn} 의 {dv:+d} 점이 '{tn}' 팀 점수에도 반영됐습니다", flush=True)

            time_str = time.strftime('%H:%M:%S')
            log_key = 'match_logs' if scope == 'match' else 'logs'
            logs = state.get(log_key)
            if not isinstance(logs, list):
                logs = []
            state[log_key] = logs
            if want_log:
                for a in applied:
                    logs.insert(0, {"time": time_str, "name": a['name'], "val": a['delta']})
            # 되돌리기: '-3점' 줄을 새로 남기는 대신 원래 줄을 지운다(장부가 깔끔하게 남는다).
            # 반반·N분할을 되돌릴 때는 지울 줄이 여러 개라 목록도 받는다.
            for u in ([undo_log] if isinstance(undo_log, dict) else (undo_log or [])):
                for i, l in enumerate(logs):
                    if (l.get('time') == u.get('time') and l.get('name') == u.get('name')
                            and l.get('val') == u.get('val')):
                        del logs[i]
                        break
            del logs[LOG_MAX:]

            if want_popup:
                top = max(applied, key=lambda a: a['delta'])
                if top['delta'] > 0:
                    state['latest_popup'] = {"time": int(time.time() * 1000),
                                             "name": top['name'], "diff": top['delta']}

            if scope == 'rank':
                lst = state.get(src) or []
                lst.sort(key=lambda b: -(b.get('contribution') or 0))
                state[src] = lst
                if want_takeover and prev_first and lst:
                    curr = lst[0].get('name')
                    gained = {a['name'] for a in applied if a['delta'] > 0}
                    if curr and curr != prev_first and curr in gained:
                        state['latest_takeover'] = {"time": int(time.time() * 1000), "name": curr}

            if pending_id:
                pend = state.get('pending_donations') or []
                state['pending_donations'] = [d for d in pend if d.get('id') != pending_id]

            save_data(state)
            broadcast_event('update', state)

        # ⚠️ 기억은 락 밖에서 적는다. DB 왕복이라 락 안에서 하면 그동안 후원 접수가 멈춘다.
        #    되돌리기(delta<0)는 기억하지 않는다 — 취소한 것을 배운 것으로 쌓으면 오히려 나빠진다.
        if donor_name and scope == 'rank':
            for a in applied:
                if (a.get('delta') or 0) > 0:
                    remember_assignment(donor_name, a['name'], a.get('delta'), donor_msg)
        return jsonify({"status": "success", "applied": applied, "time": time_str})
    except Exception as e:
        print(f"Error in api_score_add: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

# ==========================================
# 📣 안내 전광판 — 로그인 필요
#   평소에는 화면이 서버 시계로 알아서 띄운다. 여기는 "지금 띄워" 만 받는다.
# ==========================================
@app.route('/api/notice/now', methods=['POST'])
def api_notice_now():
    """진행자가 고른 문구를 지금 띄운다. body: {idx?: 몇 번째}"""
    body = request.get_json(silent=True) or {}
    idx = _as_int(body.get('idx'), 0) or 0
    with file_lock:
        state = load_data()
        msgs = state.get('notice_msgs') or []
        if not msgs:
            return jsonify({'status': 'error', 'message': '띄울 문구가 없습니다'}), 400
        idx = max(0, min(len(msgs) - 1, idx))
        state['notice_now'] = {'ts': int(time.time() * 1000), 'idx': idx}
        save_data(state)
        broadcast_event('update', state)
    print(f'📣 [안내 전광판] 지금 띄움 — "{msgs[idx][:30]}"', flush=True)
    return jsonify({'status': 'success', 'idx': idx, 'text': msgs[idx]})


# ==========================================
# 🎲 주사위게임 (부루마블식) — 로그인 필요 (exempt 목록에 없음)
#   시그뒤집기와 같은 원칙: 서버가 유일한 진실, 화면은 action 신호로 연출만.
# ==========================================
DICE_TILE_TYPES = ('start', 'blank', 'mission', 'sig', 'score', 'key')


def _dicegame_state(state):
    """항상 온전한 모양의 게임 상태를 돌려준다(예전 저장본에 없던 키 보정)."""
    g = state.get('dicegame')
    if not isinstance(g, dict):
        g = copy.deepcopy(DEFAULT_STATE['dicegame'])
        state['dicegame'] = g
    for k, v in DEFAULT_STATE['dicegame'].items():
        g.setdefault(k, copy.deepcopy(v))
    for k in ('tiles', 'keys'):
        if not isinstance(g.get(k), list):
            g[k] = []
    return g


def _dicegame_save(state, g):
    state['dicegame'] = g
    save_data(state)
    broadcast_event('update', state)


def _dicegame_apply_score(state, player, points):
    """점수 칸 자동 반영. 기존 점수 경로와 같은 규칙을 지킨다 —
       기여도 함께, 로그 남기고, 기여도순 재정렬, 대결 팀이면 팀 점수도.
       (규칙이 갈라지면 장부가 안 맞는다. api_score_add 가 하는 일의 축소판이다)"""
    t = _find_score_target(state, 'rank', player)
    if t is None:
        return None
    t['score'] = (t.get('score') or 0) + points
    t['contribution'] = (t.get('contribution') or 0) + points
    team = _match_team_of(state, t.get('name') or player)
    if team is not None:
        team['score'] = (team.get('score') or 0) + points
    logs = state.get('logs')
    if not isinstance(logs, list):
        logs = []
        state['logs'] = logs
    logs.insert(0, {"time": time.strftime('%H:%M:%S'), "name": t.get('name') or player,
                    "val": points})
    del logs[LOG_MAX:]
    src = 'extra_bjs' if state.get('extra_game_active') else 'bjs'
    lst = state.get(src) or []
    lst.sort(key=lambda b: -(b.get('contribution') or 0))
    state[src] = lst
    return t.get('name') or player


@app.route('/api/dicegame/setup', methods=['POST'])
def api_dicegame_setup():
    """판을 깐다. 같은 번호 칸의 내용은 남긴다 — 크기만 바꿔도 적어둔 게 안 날아가게."""
    body = request.get_json(silent=True) or {}
    # ⚠️ '안 보낸 것'(기본값으로 간다)과 '보냈는데 숫자가 아닌 것'(400)을 구분한다.
    #    _as_int 에 기본값을 주면 쓰레기도 조용히 기본값이 되어, 잘못 보낸 쪽이
    #    자기 실수를 영영 모른다.
    def _opt(key, default):
        return default if body.get(key) is None else _as_int(body.get(key))
    cols = _opt('cols', 7)
    rows = _opt('rows', 5)
    dice = _opt('dice', 2)
    if cols is None or rows is None or dice is None:
        return jsonify({'status': 'error', 'message': '숫자가 아닙니다'}), 400
    cols = max(4, min(10, cols))
    rows = max(3, min(8, rows))
    dice = max(1, min(2, dice))
    n = 2 * (cols + rows) - 4
    with file_lock:
        state = load_data()
        g = _dicegame_state(state)
        old = {t.get('id'): t for t in (g.get('tiles') or []) if isinstance(t, dict)}
        tiles = []
        for i in range(n):
            prev = old.get(i)
            if i == 0:
                tiles.append({'id': 0, 'type': 'start', 'label': '출발'})
            elif prev and prev.get('type') in DICE_TILE_TYPES and prev.get('type') != 'start':
                tiles.append(prev)
            else:
                tiles.append({'id': i, 'type': 'blank', 'label': ''})
        g.update({'cols': cols, 'rows': rows, 'dice': dice, 'tiles': tiles,
                  'pos': 0, 'laps': 0, 'enabled': True,
                  'action': {'type': 'PLACE', 'ts': int(time.time() * 1000)}})
        _dicegame_save(state, g)
    print(f"🎲 [주사위게임] 판 깔림 — {cols}×{rows} 테두리 {n}칸, 주사위 {dice}개")
    return jsonify({'status': 'success', 'tiles': n})


@app.route('/api/dicegame/tile', methods=['POST'])
def api_dicegame_tile():
    """칸 하나를 고친다. body: {id, type, label?, points?, sig_id?}"""
    body = request.get_json(silent=True) or {}
    tid = _as_int(body.get('id'))
    ttype = str(body.get('type') or '').strip()
    if tid is None:
        return jsonify({'status': 'error', 'message': '칸 번호가 없습니다'}), 400
    if ttype not in DICE_TILE_TYPES:
        return jsonify({'status': 'error', 'message': f'모르는 칸 종류: {ttype}'}), 400
    if tid == 0 or ttype == 'start':
        return jsonify({'status': 'error', 'message': '출발 칸은 바꿀 수 없습니다'}), 400
    label = str(body.get('label') or '').strip()[:60]
    points = _as_int(body.get('points'), 0) or 0
    points = max(-1000, min(1000, points))
    # ⚠️ 시그니처 정보는 잠금 밖(여기)에서 미리 받아 칸에 붙여 둔다.
    #    굴리는 순간 받으러 가면 잠금 안에서 네트워크를 기다린다.
    sig = None
    if ttype == 'sig':
        sig_id = _as_int(body.get('sig_id'))
        if sig_id is None:
            return jsonify({'status': 'error', 'message': '시그니처를 골라주세요'}), 400
        try:
            sig = supabase_get_signature(sig_id)
        except Exception as e:
            print(f'[주사위게임] 시그니처 조회 실패: {e}')
            sig = None
        if not sig:
            return jsonify({'status': 'error', 'message': '그 시그니처를 찾지 못했습니다'}), 404
    with file_lock:
        state = load_data()
        g = _dicegame_state(state)
        tiles = g.get('tiles') or []
        if not (0 <= tid < len(tiles)):
            return jsonify({'status': 'error', 'message': '없는 칸입니다'}), 400
        tile = {'id': tid, 'type': ttype, 'label': label}
        if ttype == 'score':
            tile['points'] = points
        if ttype == 'sig' and sig:
            tile['sig'] = sig
            if not label:
                tile['label'] = str(sig.get('title') or '')[:60]
        tiles[tid] = tile
        _dicegame_save(state, g)
    return jsonify({'status': 'success', 'tile': tile})


@app.route('/api/dicegame/keys', methods=['POST'])
def api_dicegame_keys():
    """황금열쇠 덱을 통째로 저장한다. body: {keys: [글, ...]}"""
    body = request.get_json(silent=True) or {}
    raw = body.get('keys')
    if not isinstance(raw, list):
        return jsonify({'status': 'error', 'message': '목록이 아닙니다'}), 400
    keys = [str(k).strip()[:200] for k in raw if str(k or '').strip()][:40]
    with file_lock:
        state = load_data()
        g = _dicegame_state(state)
        g['keys'] = keys
        _dicegame_save(state, g)
    return jsonify({'status': 'success', 'count': len(keys)})


@app.route('/api/dicegame/roll', methods=['POST'])
def api_dicegame_roll():
    """주사위를 굴린다. body: {player?: 이 굴림이 누구 것인지(점수 칸 자동 반영용)}

       ⚠️ 눈·경로·황금열쇠까지 전부 여기서 정해 action 에 싣는다.
          화면마다 따로 정하면 오버레이 두 개가 서로 다른 결과를 보여준다.
    """
    body = request.get_json(silent=True) or {}
    player = str(body.get('player') or '').strip()
    now_ms = int(time.time() * 1000)
    with file_lock:
        state = load_data()
        g = _dicegame_state(state)
        tiles = g.get('tiles') or []
        if not g.get('enabled') or not tiles:
            return jsonify({'status': 'error', 'message': '먼저 판을 깔아주세요'}), 400
        # 연타 방지 — 앞 연출이 끝나기 전의 굴림은 겹쳐 보인다.
        #   연출 길이 = 굴림 횟수 × 1.3초(주사위 하나가 이어 구른다) + 칸당 0.3초 + 착지 여유.
        prev = g.get('action') or {}
        if prev.get('type') == 'ROLL':
            hold = len(prev.get('path') or []) * 300 + 1300 * len(prev.get('dice') or [1]) + 2200
            if now_ms - (prev.get('ts') or 0) < hold:
                return jsonify({'status': 'error',
                                'message': '앞 연출이 아직 끝나지 않았습니다. 잠깐만요.'}), 429
        n = len(tiles)
        dice = [random.randint(1, 6) for _ in range(max(1, min(2, _as_int(g.get('dice'), 2) or 2)))]
        steps = sum(dice)
        frm = _as_int(g.get('pos'), 0) or 0
        frm = frm % n
        to = (frm + steps) % n
        lap = (frm + steps) >= n
        path = [(frm + i) % n for i in range(1, steps + 1)]
        tile = tiles[to] if isinstance(tiles[to], dict) else {'id': to, 'type': 'blank'}
        action = {'type': 'ROLL', 'ts': now_ms, 'dice': dice, 'from': frm, 'to': to,
                  'path': path, 'lap': bool(lap),
                  'tile': {k: tile.get(k) for k in ('id', 'type', 'label', 'points')}}
        if tile.get('type') == 'sig' and isinstance(tile.get('sig'), dict):
            action['tile']['image'] = tile['sig'].get('image_url')
        # 🔑 황금열쇠 — 뽑기도 서버가 한다. 화면마다 다른 카드가 나오면 안 된다.
        if tile.get('type') == 'key':
            keys = g.get('keys') or []
            action['key'] = random.choice(keys) if keys else '(황금열쇠 덱이 비어 있습니다)'
        # 💯 점수 칸 — 누구 차례인지 알려줬을 때만 자동 반영. 아니면 표시만.
        if tile.get('type') == 'score' and tile.get('points'):
            if player:
                applied_to = _dicegame_apply_score(state, player, int(tile['points']))
                if applied_to:
                    action['scored'] = {'name': applied_to, 'points': int(tile['points'])}
                else:
                    action['score_note'] = f"'{player}' 을(를) 명단에서 못 찾아 점수는 넣지 않았습니다"
            else:
                action['score_note'] = '누구 차례인지 고르지 않아 점수는 손으로 주세요'
        # 🎵 시그니처 칸 — 기존 재생 경로 그대로(재생 전용이라 집계에는 안 센다)
        if tile.get('type') == 'sig' and isinstance(tile.get('sig'), dict):
            try:
                enqueue_signature(state, tile['sig'], tile['sig'].get('amount') or 0,
                                  '주사위게임', '', count_tally=False)
            except Exception as e:
                print(f'⚠️ [주사위게임] 시그니처 재생 실패 — 게임은 계속됩니다: {e}')
        g['pos'] = to
        if lap:
            g['laps'] = (_as_int(g.get('laps'), 0) or 0) + 1
        g['action'] = action
        _dicegame_save(state, g)
    print(f"🎲 [주사위게임] {'+'.join(map(str, dice))} → {frm}→{to} 칸"
          f" ({tile.get('type')}{' 한바퀴!' if lap else ''})", flush=True)
    return jsonify({'status': 'success', 'dice': dice, 'to': to,
                    'tile': action['tile'], 'lap': bool(lap),
                    'scored': action.get('scored'), 'note': action.get('score_note'),
                    'key': action.get('key')})


@app.route('/api/dicegame/move', methods=['POST'])
def api_dicegame_move():
    """말 위치를 손으로 맞춘다(연출이 어긋났을 때의 비상 손잡이)."""
    body = request.get_json(silent=True) or {}
    pos = _as_int(body.get('pos'))
    if pos is None:
        return jsonify({'status': 'error', 'message': '칸 번호가 숫자가 아닙니다'}), 400
    with file_lock:
        state = load_data()
        g = _dicegame_state(state)
        n = len(g.get('tiles') or [])
        if not n:
            return jsonify({'status': 'error', 'message': '먼저 판을 깔아주세요'}), 400
        if not (0 <= pos < n):
            return jsonify({'status': 'error', 'message': f'칸 번호는 0~{n - 1} 입니다'}), 400
        g['pos'] = pos
        g['action'] = {'type': 'MOVE', 'ts': int(time.time() * 1000), 'to': pos}
        _dicegame_save(state, g)
    return jsonify({'status': 'success', 'pos': pos})


@app.route('/api/dicegame/enable', methods=['POST'])
def api_dicegame_enable():
    """방송 화면에 보일지만 켜고 끈다(판 내용은 그대로)."""
    body = request.get_json(silent=True) or {}
    on = bool(body.get('on'))
    with file_lock:
        state = load_data()
        g = _dicegame_state(state)
        g['enabled'] = on
        _dicegame_save(state, g)
    return jsonify({'status': 'success', 'enabled': on})


@app.route('/api/dicegame/reset', methods=['POST'])
def api_dicegame_reset():
    """말을 출발로 되돌린다. 칸 구성과 황금열쇠 덱은 남긴다 — 적는 데 든 손이 아깝다."""
    with file_lock:
        state = load_data()
        g = _dicegame_state(state)
        g.update({'pos': 0, 'laps': 0, 'enabled': False,
                  'action': {'type': 'PLACE', 'ts': int(time.time() * 1000)}})
        _dicegame_save(state, g)
    return jsonify({'status': 'success'})


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
