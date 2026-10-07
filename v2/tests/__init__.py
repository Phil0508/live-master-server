# -*- coding: utf-8 -*-
# 🤖 무인 방송(autopilot) — 검사는 '끔' 으로 시작한다(운영 기본은 그림자). 켜서 보는 검사는 test_autopilot 이 auto.set 으로 켠다.
#    ⚠️ 켜 둔 채로 두면 후원마다 서버가 스스로 판단 · AI 를 불러, 다른 검사(AI 부른 횟수 · 기억 등)가 들쭉날쭉해진다.
import os

os.environ['LM2_AUTOPILOT'] = 'off'
# 🤖 Claude — 이 PC 에 ANTHROPIC_API_KEY 가 있어도 검사는 절대 진짜 Claude 를 부르지 않는다(Claude 를 쓰는 검사는 claude_key 를 가짜로 바꾼다)
os.environ.pop('ANTHROPIC_API_KEY', None)
