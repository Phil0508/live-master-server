# -*- coding: utf-8 -*-
"""🏷️ 리스너 — 투네이션 신호에서 칭호 · 레벨 · VIP · 번호표를 꺼내고, 다시 보기 · 테스트에 표시를 붙인다(2026-10-08).

 ① 칭호 {name, color, type, icon} — 색은 #RRGGBB 만, 그림은 크리에이터 칭호(type 301~)만 투네이션 칭호 그림 주소로
 ② 번호표 — 계정(이메일형)을 HMAC 16자로. 같은 계정(대소문자 · 띄어쓰기 달라도)은 같고 다른 계정은 다르다.
    ⭐ 이메일 원문은 보내는 내용 어디에도 없다. 열쇠가 없으면 번호표를 안 만든다(열쇠 없는 해시는 이메일을 맞혀 볼 수 있다)
 ③ replay==1 → replay 표시, 후원 테스트 → test 표시
※ 신호 모양은 2026-10-08 실제 투네이션 신호(테스트 1 · 다시 보기 2)의 칸 구조 그대로다(값은 지어낸 것).
"""
import importlib.util
import json
import os
import sys

sys.stdout.reconfigure(encoding='utf-8')
ROOT = (os.environ.get('LM_PROJECT_ROOT')
        or os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')))
OK, BAD = [], []


def chk(name, cond, detail=''):
    (OK if cond else BAD).append(name)
    print(('  [OK] ' if cond else '  [!!] ') + name + (('  -- ' + str(detail)[:110]) if detail else ''))


def load(secret):
    for k in ('DONOR_KEY_SECRET', 'SESSION_SECRET'):
        os.environ.pop(k, None)
    if secret:
        os.environ['SESSION_SECRET'] = secret
    spec = importlib.util.spec_from_file_location('toon_listener_t', os.path.join(ROOT, 'toon_listener.py'))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def real_like(**over):
    c = {'account': 'Somebody@Example.com', 'acctype': 2, 'level': 44, 'message': '서아 화이팅', 'name': '별빛',
         'amount': 30000, 'image': None, 'hideinfo': 0,
         'title_info': {'type': 301, 'name': '밍밍', 'color': '#ff8282', 'hash': 'AbCdEf0123-_='},
         'donator_vip_tier': {'tierCode': 'vip', 'tierName': 'VIP', 'sortOrder': 1},
         'vip_effect': None}
    c.update(over)
    return {'code': 101, 'content': c}


tl = load('unit-test-secret')
print('=' * 74)
print('① 칭호 · 레벨 · VIP')
print('=' * 74)
p, is_test, skip = tl.to_donation(real_like())
chk('기본 칸(이름 · 금액 · 메시지 · tx_id)은 그대로', p['name'] == '별빛' and p['amount'] == 30000 and p['tx_id'].startswith('toon_'))
chk('칭호 이름 · 색(대문자) · 종류', p.get('title', {}).get('name') == '밍밍' and p['title'].get('color') == '#FF8282'
    and p['title'].get('type') == 301, p.get('title'))
chk('크리에이터 칭호(301~)는 투네이션 칭호 그림 주소', p['title'].get('icon') ==
    'https://cache.cdn.toona.xyz/prod/uploaded/__special_title_img__/AbCdEf0123-_=.img', p['title'].get('icon'))
chk('레벨 · VIP', p.get('level') == 44 and p.get('vip') == 'VIP', (p.get('level'), p.get('vip')))
p2, _, _ = tl.to_donation(real_like(title_info={'type': 120, 'name': '그린 다이아', 'color': '', 'hash': 'zzzzzzzzzz'}))
chk('다이아 · 노블레스(101~300)는 그림 주소를 안 만든다(내장 그림이라 주소가 다르다)', 'icon' not in p2['title'] and 'color' not in p2['title'], p2['title'])
p3, _, _ = tl.to_donation(real_like(title_info={'type': 301, 'name': '나쁜', 'color': 'red;background:url(x)', 'hash': '../../x y'}))
chk('이상한 색 · 그림 값은 버린다', 'color' not in p3['title'] and 'icon' not in p3['title'], p3['title'])
p4, _, _ = tl.to_donation(real_like(title_info=None, level=None, donator_vip_tier=None))
chk('칭호 · 레벨 · VIP 가 없으면 칸도 없다', not ({'title', 'level', 'vip'} & set(p4)), sorted(p4))

print('=' * 74)
print('② 번호표')
print('=' * 74)
k1 = p.get('donor_key')
chk('번호표 16자(16진수)', isinstance(k1, str) and len(k1) == 16 and all(ch in '0123456789abcdef' for ch in k1), k1)
chk('⭐ 이메일 원문은 보내는 내용 어디에도 없다', 'example.com' not in json.dumps(p, ensure_ascii=False).lower()
    and 'somebody' not in json.dumps(p, ensure_ascii=False).lower())
q, _, _ = tl.to_donation(real_like(account='  somebody@example.COM '))
chk('같은 계정(대소문자 · 띄어쓰기 달라도) → 같은 번호표', q.get('donor_key') == k1)
r, _, _ = tl.to_donation(real_like(account='other@example.com'))
chk('다른 계정 → 다른 번호표', r.get('donor_key') and r['donor_key'] != k1)
e, _, _ = tl.to_donation(real_like(account=''))
chk('계정이 비면 번호표 없음', 'donor_key' not in e)
tl_nokey = load('')
n, _, _ = tl_nokey.to_donation(real_like())
chk('열쇠가 없으면 번호표를 안 만든다', 'donor_key' not in n and n.get('title', {}).get('name') == '밍밍')
tl_other = load('another-secret')
o, _, _ = tl_other.to_donation(real_like())
chk('열쇠가 다르면 번호표도 다르다(열쇠 없이 이메일로 맞혀 볼 수 없다)', o.get('donor_key') != k1)

print('=' * 74)
print('③ 다시 보기 · 테스트')
print('=' * 74)
tl = load('unit-test-secret')
rp = real_like()
rp.update({'replay': 1, 'intercept': 0, 'code_ex': 1400})
x, is_test, skip = tl.to_donation(rp)
chk('replay==1 → replay 표시(서버가 화면에만 띄운다)', x.get('replay') is True and not is_test and skip is None)
y, _, _ = tl.to_donation(real_like())
chk('보통 후원엔 replay 표시가 없다', 'replay' not in y and 'test' not in y)
ts = real_like(test_noti=1)
ts['test'] = 1
z, is_test, _ = tl.to_donation(ts)
chk('후원 테스트 → test 표시', z.get('test') is True and is_test)
rz = real_like()
rz['replay'] = 0
w, _, _ = tl.to_donation(rz)
chk('replay==0 은 보통 후원', 'replay' not in w)

print('\n' + '=' * 74)
print('결과: 통과 %d · 실패 %d' % (len(OK), len(BAD)))
for b in BAD:
    print('  ✗', b)
sys.exit(1 if BAD else 0)
