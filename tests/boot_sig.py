# -*- coding: utf-8 -*-
"""샌드박스 부팅 래퍼.

server.py 사본을 고치지 않고, Supabase 로 나가는 시그니처 조회만 가짜로 바꿔
시그게임 경로를 열어준다. (샌드박스에는 Supabase 자격증명이 없다 — 넣지도 않는다)
"""
import os
import sys

os.environ.setdefault('HEADLESS', '1')
os.environ.setdefault('PORT', '5199')
os.environ.setdefault('ADMIN_PASSWORD', 'sandboxpw')
os.environ.setdefault('SESSION_SECRET', 'sandboxsecret123456')
os.environ.setdefault('SELF_PING', 'off')

import server

FAKE = [
    {"id": 10000 + i, "amount": 10000 + i * 100, "title": "테스트시그%d" % i,
     "image_url": "https://example.invalid/img_%d.webp" % i,
     "sound_url": "https://example.invalid/snd_%d.mp3" % i, "duration": 10}
    for i in range(1, 41)
]

server.supabase_list_signatures = lambda: list(FAKE)


# 실제 서버와 같은 규칙: 후원 금액 이상 중 가장 싼 시그니처, 없으면 가장 비싼 것
def _match(amount):
    over = [x for x in FAKE if x["amount"] >= int(amount)]
    return min(over, key=lambda x: x["amount"]) if over else max(FAKE, key=lambda x: x["amount"])


server.supabase_match_signature = _match
# 주사위게임 칸 편집이 시그니처를 단건으로 조회한다
server.supabase_get_signature = lambda sid: next((x for x in FAKE if x['id'] == int(sid)), None)
server._supabase_ready = lambda: True

print("[래퍼] 가짜 시그니처 %d개로 기동합니다." % len(FAKE), flush=True)
server.app.run(host='127.0.0.1', port=int(os.environ['PORT']), debug=False, use_reloader=False)
