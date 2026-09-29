# -*- coding: utf-8 -*-
"""🧪 투네이션 연결 — 테스트용 두 번째 계정 주소 넣기 · 끄고 켜기 · 리스너 연결 상태 (2026-09-29).

주소는 서버 폴더의 toon_accounts.json 에 적는다(저장소에 안 올라간다 · .gitignore).
리스너(toon_listener.py)가 10초마다 이 파일을 읽어 붙거나 떼고, 수 · 목(방송하는 날)엔 저절로 쉰다.
리스너가 적는 toon_listener_status.json 을 읽어 조종실 시스템 탭에 연결 상태를 보여준다.

⚠️ 알림창 주소 끝의 키는 비밀번호 같은 접속 열쇠다. 화면에 그대로 돌려주지 않는다(끝 네 글자만).
"""
import json
import os
import re
import time
from flask import jsonify, request
from server import BASE_DIR, app

TOON_ACCOUNTS_FILE = os.path.join(BASE_DIR, 'toon_accounts.json')
TOON_STATUS_FILE = os.path.join(BASE_DIR, 'toon_listener_status.json')
TOON_REST_WEEKDAYS = (2, 3)          # 수 · 목 — 리스너(TEST_REST_WEEKDAYS)와 같게
_ALERTBOX_RE = re.compile(r'^https://toon\.at/widget/alertbox/([A-Za-z0-9_\-]{6,})/?$')


def _read_json(path):
    try:
        with open(path, 'r', encoding='utf-8') as f:
            v = json.load(f)
        return v if isinstance(v, dict) else {}
    except Exception:
        return {}


def _key_of(url):
    m = _ALERTBOX_RE.match(str(url or '').strip().split('?')[0].split('#')[0])
    return m.group(1) if m else ''


def _mask(url):
    k = _key_of(url)
    return ('toon.at/widget/alertbox/••••' + k[-4:]) if k else ''


def _view():
    cfg = _read_json(TOON_ACCOUNTS_FILE)
    st = _read_json(TOON_STATUS_FILE)
    url = str(cfg.get('test_url') or '')
    accs = st.get('accounts') if isinstance(st.get('accounts'), dict) else {}
    try:
        age = time.time() - float(st.get('updated') or 0)
    except (TypeError, ValueError):
        age = None
    return {
        'status': 'success',
        'test': {'set': bool(url), 'masked': _mask(url), 'enabled': cfg.get('enabled', True) is not False,
                 'resting_today': time.gmtime(time.time() + 9 * 3600).tm_wday in TOON_REST_WEEKDAYS},
        # 리스너는 10초마다 상태를 적는다 — 1분 넘게 소식이 없으면 멈췄거나 예전 리스너다
        'listener': {'alive': bool(st) and age is not None and age < 60,
                     'age_sec': int(age) if (st and age is not None) else None,
                     'main': accs.get('main'), 'test': accs.get('test')},
    }


@app.route('/api/toon/accounts', methods=['GET'])
def api_toon_accounts_get():
    return jsonify(_view())


@app.route('/api/toon/accounts', methods=['POST'])
def api_toon_accounts_set():
    body = request.get_json(silent=True) or {}
    cfg = _read_json(TOON_ACCOUNTS_FILE)
    if 'test_url' in body:
        raw = str(body.get('test_url') or '').strip()
        if raw:
            key = _key_of(raw)
            if not key:
                return jsonify({'status': 'error',
                                'message': '투네이션 알림창 주소(https://toon.at/widget/alertbox/…)를 그대로 붙여 주세요'}), 400
            # 본 계정과 같은 주소면 후원이 두 번씩 들어온다
            if key == _key_of(os.environ.get('ALERTBOX_URL', '')):
                return jsonify({'status': 'error', 'message': '본 계정과 같은 주소예요 — 두 번째 계정의 알림창 주소를 넣어 주세요'}), 400
            cfg['test_url'] = 'https://toon.at/widget/alertbox/' + key
            cfg['enabled'] = True
        else:
            cfg['test_url'] = ''
    if 'enabled' in body:
        cfg['enabled'] = bool(body.get('enabled'))
    cfg['updated'] = int(time.time())
    tmp = TOON_ACCOUNTS_FILE + '.tmp'
    try:
        with open(tmp, 'w', encoding='utf-8') as f:
            json.dump(cfg, f, ensure_ascii=False)
        try:
            os.chmod(tmp, 0o600)          # 열쇠가 든 파일 — 서버 사용자만 읽게
        except Exception:
            pass
        os.replace(tmp, TOON_ACCOUNTS_FILE)
    except Exception as e:
        return jsonify({'status': 'error', 'message': '설정을 저장하지 못했습니다: %s' % e}), 500
    return jsonify(_view())
