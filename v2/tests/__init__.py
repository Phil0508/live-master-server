# -*- coding: utf-8 -*-
# 🤖 무인 방송(autopilot) — 검사는 '끔' 으로 시작한다(운영 기본은 그림자). 켜서 보는 검사는 test_autopilot 이 auto.set 으로 켠다.
#    ⚠️ 켜 둔 채로 두면 후원마다 서버가 스스로 판단 · AI 를 불러, 다른 검사(AI 부른 횟수 · 기억 등)가 들쭉날쭉해진다.
import os

os.environ['LM2_AUTOPILOT'] = 'off'
