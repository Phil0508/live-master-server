# -*- coding: utf-8 -*-
# 🤖 무인 방송(autopilot) — 검사는 '끔' 으로 시작한다(운영 기본은 그림자). 켜서 보는 검사는 test_autopilot 이 auto.set 으로 켠다.
#    ⚠️ 켜 둔 채로 두면 후원마다 서버가 스스로 판단 · AI 를 불러, 다른 검사(AI 부른 횟수 · 기억 등)가 들쭉날쭉해진다.
import os

os.environ['LM2_AUTOPILOT'] = 'off'
# 🤖 Claude — 이 PC 에 ANTHROPIC_API_KEY 가 있어도 검사는 절대 진짜 Claude 를 부르지 않는다(Claude 를 쓰는 검사는 claude_key 를 가짜로 바꾼다)
os.environ.pop('ANTHROPIC_API_KEY', None)

# 🧱 검사 울타리(sturdy 10-17) — 그냥 `python -m unittest discover -s v2/tests -t .` 만 돌려도 바깥으로 안 나가게.
#    ⚠️ 서버는 SUPABASE_CREDENTIALS.txt · NVIDIA_CREDENTIALS.txt 를 저절로 읽는다(환경변수가 먼저). 그래서 전에는
#       가짜 시그니처 목록 없이 서버를 만드는 검사(후원 받기 · 옛 장부 옮기기 · 진짜 서버 띄우기)가 진짜 Supabase 에 물으러 나갔다.
#    여기서 Supabase · NVIDIA 주소를 아무도 안 받는 닫힌 포트로 돌리고, NVIDIA 열쇠를 비운다. 진짜 서버를 띄우는 검사(test_live)도
#    이 환경을 물려받는다. 이 값이 필요한 검사는 mock.patch.dict 로 잠깐 바꿔 쓴다.
#    ⚠️ 이 줄들은 서버 부품(ai.py 의 NIM_URL 등)을 불러오기 **전에** 돌아야 한다 — 검사 꾸러미가 처음 불릴 때 여기가 먼저 돈다.
CLOSED = 'http://127.0.0.1:9'          # 9번(discard) — 아무도 안 받는다. 붙으려 하면 바로 '연결 거부'
os.environ['SUPABASE_URL'] = CLOSED
os.environ['SUPABASE_SECRET_KEY'] = 'x'
os.environ['LM2_NIM_URL'] = CLOSED
os.environ['NVIDIA_API_KEY'] = ''
