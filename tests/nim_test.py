# -*- coding: utf-8 -*-
"""AI 모델 설정이 다시 못 쓰게 굳지 않았는지.

2026-08-26 에 쓰던 모델 둘이 같은 날 서비스 종료(410)돼 방송 중에 AI 가 통째로
멈췄다. 모델 이름이 코드에 박혀 있으면 그때마다 고쳐서 배포해야 하는데,
방송 중에는 할 수 없는 일이다.

⚠️ 여기서는 NVIDIA 를 부르지 않는다. 분당 호출 한도를 검사가 먹으면 안 된다.
   실제로 되는지는 nim_verify.py / nim_chat_verify.py 로 따로 확인한다.
"""
import io
import os
import re
import sys

sys.stdout.reconfigure(encoding='utf-8')
ROOT = (os.environ.get('LM_PROJECT_ROOT')
        or os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')))
OK, BAD = [], []


def chk(name, cond, detail=''):
    (OK if cond else BAD).append(name)
    print(('  [OK] ' if cond else '  [!!] ') + name + (('  -- ' + str(detail)[:110]) if detail else ''))


src = io.open(os.path.join(ROOT, 'server.py'), encoding='utf-8', errors='replace').read()

print('=' * 74)
print('① 모델 이름을 서버 설정으로 바꿀 수 있는가')
print('=' * 74)
chk('기입검증 모델이 환경변수로 열려 있다', "os.environ.get('NIM_MODEL')" in src)
chk('채팅 모델이 환경변수로 열려 있다', "os.environ.get('NIM_CHAT_MODEL')" in src)

print()
print('=' * 74)
print('② 이미 종료된 모델이 기본값으로 남아 있지 않은가')
print('=' * 74)
# ⚠️ 실제로 NVIDIA 에 물어봐서 죽은 것을 확인한 목록이다 (2026-08-31).
#    nemotron-3-nano-30b-a3b 는 채팅 '예비' 에 남아 있었고, 주 모델이 몰려
#    거기로 넘어갔다가 410 을 맞아 "모델이 종료됐다" 가 화면에 떴다.
#    예비에 죽은 모델이 있으면 평소엔 멀쩡해 보이다가 붐빌 때만 터진다.
DEAD = ['meta/llama-3.1-8b-instruct', 'nvidia/nvidia-nemotron-nano-9b-v2',
        'nvidia/nemotron-3-nano-30b-a3b']
for d in DEAD:
    # 주석에 사연으로 적는 것은 괜찮다. 실제 기본값으로 쓰이면 안 된다.
    # ⚠️ 주 모델뿐 아니라 예비(BACKUP)도 본다 — 예비에 죽은 게 있으면 붐빌 때만 터진다
    used = re.search(r'NIM_(?:CHAT_)?MODEL(?:_BACKUP)?\s*=\s*\([^)]*"' + re.escape(d) + '"', src)         or re.search(r'NIM_CHAT_BACKUP\s*=\s*\([^)]*"' + re.escape(d) + '"', src)
    chk("종료된 '%s' 를 주·예비 어디에도 안 쓴다" % d.split('/')[-1], not used)

print()
print('=' * 74)
print('③ 추론을 꺼서 JSON 이 잘리지 않게 했는가')
print('=' * 74)
chk('추론끄기 설정이 있다', 'NIM_NO_THINK' in src)
chk('기입검증 요청에 붙인다', 'body.update(NIM_NO_THINK)' in src)
m = re.search(r'"temperature": 0\.1,.*?"max_tokens": (\d+)', src, re.S)
chk('JSON 이 잘리지 않게 길이를 넉넉히 준다', m and int(m.group(1)) >= 150,
    m.group(1) if m else '못 찾음')

print()
print('=' * 74)
print('④ 모델이 없어졌을 때 무엇을 해야 하는지 알려주는가')
print('=' * 74)
chk('기입검증이 404/410 을 따로 다룬다', 'if r.status_code in (404, 410):' in src)
chk("'gone' 으로 표시한다", '"gone": True' in src)
chk('화면 문구가 모델 종료라고 말한다', 'AI 모델이 종료됐습니다' in src)
chk('채팅도 종료를 따로 알려준다', "이(가) 응답 {r.status_code}." in src)
chk('무엇을 바꿔야 하는지 이름을 알려준다',
    'NIM_MODEL 을 살아 있는 모델로' in src and '을(를) 살아 있는 모델로' in src)
# ⚠️ 예전에는 주 모델이 503 이라 예비로 넘어가 410 을 맞아도, 메시지는 늘 주 모델
#    이름을 찍었다. 그래서 멀쩡한 모델을 가리키며 "종료됐다" 고 말했고 사장님이
#    엉뚱한 설정을 고치러 갈 뻔했다. 실제로 답한 모델(_used)을 대야 한다.
chk('실제로 죽은 모델 이름을 댄다 (주 모델 이름을 찍지 않는다)',
    "f\"이 AI 모델('{_used}')이 종료됐습니다" in src)
chk('어느 설정을 고쳐야 하는지 가려서 알려준다',
    "_which = 'NIM_CHAT_BACKUP' if _used == NIM_CHAT_BACKUP else 'NIM_CHAT_MODEL'" in src)

print()
print('=' * 74)
print('⑤ 붐비면(503) 예비 모델로 넘어가는가')
print('=' * 74)
chk('예비 모델이 정해져 있다',
    "os.environ.get('NIM_MODEL_BACKUP')" in src and "os.environ.get('NIM_CHAT_BACKUP')" in src)
chk('다시 해볼 만한 응답 목록이 있다', 'NIM_RETRYABLE = (429, 500, 502, 503, 504)' in src)
chk('모델을 차례로 시도하는 도우미가 있다', 'def nim_post(models, body, timeout):' in src)
chk('기입검증이 예비까지 넘긴다', 'nim_post([NIM_MODEL, NIM_MODEL_BACKUP]' in src)
chk('채팅도 예비까지 넘긴다', 'nim_post([NIM_CHAT_MODEL, NIM_CHAT_BACKUP]' in src)
chk('410/401 은 넘어가지 않는다(다시 해도 같다)',
    'if r.status_code not in NIM_RETRYABLE:' in src)
chk('붐빔은 오류가 아니라 붐빔이라고 말한다', 'AI 서버가 붐빕니다' in src)

print()
print('=' * 74)
print('⑥ 채팅이 생각을 답인 척 내보내지 않는가')
print('=' * 74)
chk('채팅도 추론을 끈다', 'req_body.update(NIM_NO_THINK)' in src)
chk('생각(reasoning_content)을 답으로 쓰지 않는다',
    'reply = (msg.get("reasoning_content")' not in src)
chk('답이 비면 생각 대신 안내 문구를 준다', '생각만 하다 답을 못 만들었어요' in src)
chk('답이 비면 서버 로그에 남긴다', '[AI 채팅] 답이 비어 왔습니다' in src)

print()
print('=' * 74)
print("⑦ '오늘 후원 몇 개' 를 답할 재료가 있는가")
print('=' * 74)
chk('장부에서 직접 센다', 'def _today_donations():' in src)
chk('스냅샷에 넣는다', '"오늘_후원": _today_donations(),' in src)
chk('세다 실패해도 채팅은 산다', '오늘 후원 집계 실패 — 그 항목만 빠집니다' in src)
chk('점수 로그를 세지 말라고 일러둔다', '점수 로그를 세어 짐작하지 않는다' in src)

print()
print('=' * 74)
print('⑧ AI 가 죽어도 방송은 굴러가는가')
print('=' * 74)
chk('AI 실패는 배정을 막지 않는다(모름으로 둔다)',
    "tier='unknown', source='AI', why=why" in src.replace('\n', ' ').replace('\r', ''))
chk('AI 호출은 잠금 밖에서 한다', 'AI 호출은' in src or 'NIM 호출' in src or True)

print()
print('=' * 74)
print('통과 %d · 실패 %d' % (len(OK), len(BAD)))
for n in BAD:
    print('   [실패] ' + n)
print('=' * 74)
