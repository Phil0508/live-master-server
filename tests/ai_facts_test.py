# -*- coding: utf-8 -*-
"""🤖 AI 도우미 개편 — 사실표 · 즉답 · 별명 힌트 · 조종실 단추 (2026-09-29).

왜 만들었나
  AI 채팅에 실제로 물어보니 계산을 틀렸다(3만 원 → +30점, 목표 1,000점을 1,000원으로 읽고 '초과 달성',
  퇴근빵 목표를 엉뚱한 사람에게). 답은 20줄씩 길었고 '누구에게 몰아주면 역전' 같은 조언까지 했다.
  배정 추천은 붐빔(503)으로 20번 중 4번 답을 못 받았고, 한 번 못 받으면 끝까지 '모름' 이었다.

여기서 지키는 것
  ① 사실표 — 순위 · 목표 · 대기함 · 대결 · 퇴근빵 · 최근 흐름 · 시그를 서버가 맞게 센다
  ② 즉답 — 여덟 가지 단추 답이 맞는 숫자를 말한다 · 빈 상태에서도 안 터진다
  ③ 질문 알아보기 · 별명 힌트 · 깨진 답 걸러내기 · AI 에게 주는 글자
  ④ 조종실 — 단추 여덟 개 · 이름표가 서버와 같다 · 붐비면 다시 묻는다 · '3분째 대기' 알림
  ⑤ 살아 있는 서버 — 단추가 AI 없이 답한다 · 키가 없어도 계산으로 답한다 · 별명만 겹치면 '확인 필요'

⚠️ NVIDIA 는 부르지 않는다(검사 서버에는 키가 없다). 실제 실력은 스크래치패드 ai_eval.py 로 잰다.
"""
import importlib.util
import io
import json
import os
import re
import sys
import urllib.error
import urllib.request

sys.stdout.reconfigure(encoding='utf-8')
ROOT = (os.environ.get('LM_PROJECT_ROOT')
        or os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')))
B = 'http://127.0.0.1:5199'
H = {'Content-Type': 'application/json', 'Authorization': 'Bearer sandboxsecret123456'}
OK, BAD = [], []


def chk(name, cond, detail=''):
    (OK if cond else BAD).append(name)
    print(('  [OK] ' if cond else '  [!!] ') + name + (('  -- ' + str(detail)[:160]) if detail else ''))


def head(s):
    print()
    print('=' * 74)
    print(s)
    print('=' * 74)


spec = importlib.util.spec_from_file_location('ai_facts', os.path.join(ROOT, 'features', 'ai_facts.py'))
F = importlib.util.module_from_spec(spec)
spec.loader.exec_module(F)

# 2026-09-29 11:26 (한국 시각) — 로그 시각과 맞춘다
NOW = 1790648760
MS = NOW * 1000
LOGS = [("11:24:10", "예지랑", 10), ("11:23:02", "예지랑", 5), ("11:21:40", "밍밍", 1), ("11:20:15", "예지랑", 3),
        ("11:18:30", "행복한걸", 1), ("11:17:05", "예지랑", 5), ("11:15:44", "앙나니", 1), ("11:14:20", "밍밍", 3),
        ("11:12:02", "행복한걸", 5), ("11:10:11", "밍밍", 1), ("11:08:40", "행복한걸", 3), ("11:06:15", "밍밍", 10)]
STATE = {
    "broadcast_active": True,
    "bjs": [{"name": "밍밍", "score": 134, "contribution": 387}, {"name": "행복한걸", "score": 148, "contribution": 478},
            {"name": "앙나니", "score": 61, "contribution": 65}, {"name": "예지랑", "score": 100, "contribution": 269}],
    "bottom_fixed": {"name": "운영비", "score": 0}, "target_goal": 1000, "goal_offset": 0,
    "pending_donations": [
        {"id": f"don_{MS - 4 * 60000}_a1b2c3", "name": "지수크루", "amount": 30000, "message": "밍밍이 노래 한곡"},
        {"id": f"don_{MS - 2 * 60000}_d4e5f6", "name": "재성", "amount": 10000, "message": ""},
        {"id": f"don_{MS - 60000}_0a0b0c", "name": "코코몽", "amount": 50000, "message": "행걸 화이팅"},
        {"id": "off_1", "type": "off_work", "name": "퇴근", "amount": 0},
        {"id": f"don_{MS}_c0ffee", "kind": "contrib", "name": "주사위", "amount": 0}],
    "logs": [{"time": t, "name": n, "val": v} for t, n, v in LOGS],
    "match_data": {"active": True, "is_running": True, "end_time_ms": MS + 95000, "time_left_ms": 0,
                   "players": [{"name": "밍밍", "score": 12}, {"name": "예지랑", "score": 19}]},
    "home_race_enabled": True,
    "home_goals": {"Player 1": 1080, "밍밍": 254, "복자": 88, "예지랑": 100, "행복한걸": 119, "앙나니": 72},
    "sig_tally": {
        "a": {"title": "응원봉", "count": 14, "amount": 10300, "donors": {"지수크루": 7, "영원": 2, "재성": 2, "앞뒤": 3}},
        "b": {"title": "하트뿅", "count": 6, "amount": 5000, "donors": {"재성": 3, "앞뒤": 3}},
        "c": {"title": "가즈아", "count": 1, "amount": 100009, "donors": {"재성": 1}}},
    "reaction_queue": [{"title": "응원봉", "count": 3}, {"title": "하트뿅"}],
}
TODAY = {"건수": 96, "합계금액": 4870000,
         "많이_쏜_사람": [{"이름": "지수크루", "횟수": 14, "금액합": 720000}, {"이름": "재성", "횟수": 9, "금액합": 610000}]}
SUG = {"지수크루": {"target": "밍밍", "tier": "auto"}, "코코몽": {"target": "행복한걸", "tier": "suggest"},
       "재성": {"target": None, "tier": "unknown"}}
f = F.build_facts(STATE, today=TODAY, suggest=lambda d: SUG.get(d.get('name')), now=NOW)

head('① 사실표 — 서버가 맞게 센다')
chk('점수 환산은 서버와 같은 식(4천 원부터 올림)',
    [F.man_won(x) for x in (5000, 6000, 30000, 15000, 16000, 0, None)] == [0, 1, 3, 1, 2, 0, 0])
r = f['순위']
chk('순위는 기여도 순', [x['이름'] for x in r] == ['행복한걸', '밍밍', '예지랑', '앙나니'])
chk('윗순위와 차이를 미리 뺀다', r[1]['윗순위와_기여도차'] == 91 and r[1]['윗순위와_점수차'] == 14)
g = f['목표']
chk('목표는 점수 단위 — 443 / 1000, 557 남음',
    g['현재점수'] == 443 and g['남은점수'] == 557 and g['달성률'] == '44%' and not g['달성'], g)
chk('목표가 없으면 없다고 둔다', F.build_facts(dict(STATE, target_goal=0), now=NOW)['목표'] == '목표 없음')
p = f['대기함']
chk('퇴근 요청은 대기함에서 뺀다', all(x['후원자'] != '퇴근' for x in p))
chk('기여도 알림은 후원이 아니라고 적는다', any(x.get('종류', '').startswith('기여도 알림') for x in p))
jk = next(x for x in p if x['후원자'] == '지수크루')
chk('대기 후원 점수 · 기다린 시간', jk['점수'] == 3 and jk['기다린_분'] == 4, jk)
chk('이미 해 둔 배정 판단을 붙인다', jk.get('추천', {}).get('target') == '밍밍')
chk('대기함 합계는 기여도 알림 금액까지 원 단위로 센다', f['대기함_합계']['점수'] == 9 and f['대기함_합계']['금액'] == 90000,
    f['대기함_합계'])
m = f['대결']
chk('대결 — 앞선 쪽 · 차이 · 남은 시간', m['앞선_쪽'] == '예지랑' and m['차이'] == 7 and '1:35' in m['상태'], m)
chk('멈춘 대결은 멈췄다고', '멈춤' in F.build_facts(dict(STATE, match_data=dict(
    STATE['match_data'], is_running=False, paused_time_left=60000)), now=NOW)['대결']['상태'])
chk('대결이 꺼져 있으면 안 한다고', F.build_facts(dict(STATE, match_data={'active': False}), now=NOW)['대결'] == '대결 안 함')
race = f['퇴근빵']
chk('퇴근빵 — 지금 선수만(옛 Player 1 · 복자 제외)', {x['이름'] for x in race['선수별']} == {'밍밍', '예지랑', '행복한걸', '앙나니'})
chk('퇴근빵 — 가장 가까운 미달성은 앙나니(11점)', race['가장_가까운_미달성'] == '앙나니'
    and next(x for x in race['선수별'] if x['이름'] == '앙나니')['남은점수'] == 11)
chk('퇴근빵 — 목표를 넘은 사람은 달성', next(x for x in race['선수별'] if x['이름'] == '행복한걸')['달성'])
hs = dict(STATE, home_race_enabled=False,
          hell={'on': True, 'base': {'밍밍': 130}, 'goals': {'밍밍': 10, '예지랑': 50}})
hf = F.build_facts(hs, now=NOW)['퇴근빵']
chk('지옥탈출은 시작 뒤 받은 점수로 센다', hf['이름'] == '지옥탈출'
    and next(x for x in hf['선수별'] if x['이름'] == '밍밍')['현재'] == 4, hf)
fl = f['최근_흐름']
chk('최근 15분 흐름 — 예지랑 +23 이 1등', fl['가장_많이_오른_사람'] == '예지랑' and fl['사람별_점수합']['예지랑'] == 23, fl)
old = F.build_facts(STATE, now=NOW + 3 * 3600)['최근_흐름']
chk('15분 안에 기록이 없으면 최근 20건으로', old['기간'].startswith('최근 12건'), old['기간'])
s = f['시그니처']
chk('시그 — 횟수 1등 지수크루 · 금액 1등 재성(135,609원)',
    s['횟수_순'][0]['이름'] == '지수크루' and s['금액_순'][0]['이름'] == '재성' and s['금액_순'][0]['금액합'] == 135609)
ex = F.build_facts(dict(STATE, extra_game_active=True, extra_bjs=[{"name": "임시", "score": 1, "contribution": 2}]), now=NOW)
chk('임시게임 중이면 임시 선수로 센다', [x['이름'] for x in ex['순위']] == ['임시'] and ex['판'].startswith('임시'))
chk('빈 상태에서도 안 터진다', isinstance(F.build_facts({}, now=NOW), dict))

head('② 즉답 — 여덟 단추가 맞는 숫자를 말한다')
QA = {k: F.quick_answer(k, f) for k in F.INTENTS}
chk('순위', QA['rank'].startswith('1등은 **행복한걸**') and '91 차' in QA['rank'], QA['rank'])
chk('대기함 — 오래 기다린 것부터 · 점수 · 추천', QA['pending'].split('\n')[1].startswith('- 지수크루 3만 원(3점)')
    and '→ 행복한걸(확인 필요)' in QA['pending'] and '누구 것인지 모름' in QA['pending'], QA['pending'])
chk('목표 — 557점(557만 원)', '557점' in QA['goal'] and '557만 원' in QA['goal'], QA['goal'])
chk('대결 — 받침 맞춘 조사', QA['match'].startswith('**예지랑**이 7점 앞서요'), QA['match'])
chk('퇴근빵 — 가장 가까운 사람', QA['race'].startswith('가장 가까운 사람은 **앙나니** — 11점 남음'), QA['race'])
chk('오늘 후원 — 487만 원', '96건' in QA['today'] and '487만 원' in QA['today'], QA['today'])
chk('시그 — 횟수 1등과 금액 1등을 따로', '**지수크루** 7번' in QA['sig'] and '금액으로는 재성' in QA['sig'], QA['sig'])
chk('최근 흐름', '**예지랑** +23점' in QA['flow'], QA['flow'])
E = F.build_facts({}, now=NOW)
EQ = {k: F.quick_answer(k, E) for k in F.INTENTS}
chk('빈 방송에서도 여덟 단추가 다 말을 한다', all(isinstance(v, str) and v for v in EQ.values()), EQ)
chk('모르는 단추는 None', F.quick_answer('nope', f) is None)
chk('돈 글자', [F.won(x) for x in (30000, 4870000, 12500, 0, 60000000000, 120000000)]
    == ['3만 원', '487만 원', '12,500원', '0원', '600억 원', '1억 2,000만 원'])

head('②-b 상황판 네 칸 (B안)')
BT = F.board_tiles(f)
T = {x['intent']: x for x in BT}
chk('네 칸 순서', [x['intent'] for x in BT] == ['pending', 'match', 'goal', 'race'])
chk('대기함 칸 — 후원만 센다(기여도 알림 빼고) · 4분째면 주황', T['pending']['v'] == '3건 · 9점' and T['pending']['hot']
    and '4분째' in T['pending']['k'] and '지수크루 3만 원' in T['pending']['s'], T['pending'])
chk('2분밖에 안 됐으면 주황 아님', not F.board_tiles(F.build_facts(STATE, now=NOW - 120))[0]['hot'])
chk('대결 칸', T['match']['v'] == '예지랑 +7' and T['match']['k'] == '⚔️ 대결 · 1:35'
    and T['match']['s'] == '예지랑 19 : 밍밍 12', T['match'])
chk('목표 칸 — 막대 44%', T['goal']['v'] == '443 / 1,000점' and T['goal']['pct'] == 44
    and T['goal']['s'] == '557점 남음', T['goal'])
chk('퇴근빵 칸', T['race']['v'] == '앙나니 11점 남음' and T['race']['s'] == '달성: 행복한걸 · 예지랑', T['race'])
ET = {x['intent']: x for x in F.board_tiles(F.build_facts({}, now=NOW))}
chk('빈 방송 — 비어 있음 · 안 함 · 목표 없음', ET['pending']['v'] == '비어 있음' and ET['match']['v'] == '안 함'
    and ET['goal']['v'] == '목표 없음' and ET['race']['v'] == '목표 없음', ET)
chk('받침 조사', [F.ga(x) for x in ('예지랑', '밍밍', '하루', 'Tom')] == ['이', '이', '가', '이(가)'])

head('③ 질문 알아보기 · 별명 힌트 · 깨진 답 · AI 에게 주는 글자')
IQ = [("지금 1등 누구야?", 'rank'), ("1등이랑 2등 몇 점 차이야?", 'rank'), ("대기함에 밀린 후원 있어?", 'pending'),
      ("오늘 후원 총 얼마 들어왔어?", 'today'), ("대결 누가 이기고 있어?", 'match'), ("목표까지 얼마 남았어?", 'goal'),
      ("시그 제일 많이 쏜 사람 누구야?", 'sig'), ("최근에 누가 치고 올라왔어?", 'flow'),
      ("코코몽님 후원 누구한테 줘야 돼?", 'pending'), ("퇴근빵 누가 제일 가까워?", 'race'), ("지금 뭐부터 처리하면 돼?", None)]
for q, want in IQ:
    chk(f"'{q}' → {want}", F.detect_intent(q) == want, F.detect_intent(q))
PL = ['행복한걸', '밍밍', '예지랑', '앙나니']
for msg, want in [('행걸 화이팅', '행복한걸'), ('행복이 예쁘다', '행복한걸'), ('ㅎㅂㅎㄱ 가즈아', '행복한걸'),
                  ('지랑이 텐션', '예지랑'), ('예지언니 노래', '예지랑'), ('나니 대박', '앙나니'), ('ㅇㄴㄴ 응원', '앙나니')]:
    h = F.nickname_hints(msg, PL)
    chk(f"별명 힌트 '{msg}' → {want}", list(h) == [want], h)
for msg in ('밍쨩 힘내', '방송 재밌어요', '1등 가자', '밍밍 화이팅'):
    chk(f"힌트 없음 '{msg}'", F.nickname_hints(msg, PL) == {}, F.nickname_hints(msg, PL))
chk('깨진 답을 알아본다', F.looks_broken('재시 가장의\n(\n:1{"\nTEXT\n[[[H0[[[0[[[0'))
chk('멀쩡한 답은 그대로', not F.looks_broken('1등은 **행복한걸** — 기여도 478 (점수 148)'))
chk('빈 답은 깨진 것', F.looks_broken(''))
chk('일본어 가나 · 한자 · 제목(#)을 걷어낸다', F.clean_reply('### 결과\n대결 残り 95초') == '결과\n대결 95초',
    F.clean_reply('### 결과\n대결 残り 95초'))
fa = F.facts_for_ai(f)
chk('AI 에게는 돈을 글자로 준다', fa['대기함'][0]['금액'] == '3만 원' and fa['오늘_후원']['합계'] == '487만 원', fa['대기함'][0])
chk('추천은 사람 말로', any(x.get('누구_것') == '행복한걸(확인 필요)' for x in fa['대기함']))
chk('원본 사실표는 그대로 둔다(즉답이 숫자를 쓴다)', f['대기함'][0]['금액'] == 30000)
sp = F.chat_system_prompt(f, '시그 제일 많이 쏜 사람 누구야?')
chk('질문 종류를 알아보면 계산한 답을 같이 준다', '[이 질문에 맞는 계산 결과' in sp and '**지수크루** 7번' in sp)
chk('모르는 질문엔 계산 답을 안 붙인다', '[이 질문에 맞는 계산 결과' not in F.chat_system_prompt(f, '뭐부터 해?'))
chk('프롬프트 — 짧게 · 한국어만 · 몰아주기 조언 금지',
    '5줄을 넘기지 않는다' in F.CHAT_PROMPT and '한국어 존댓말' in F.CHAT_PROMPT and '몰아주라거나' in F.CHAT_PROMPT)
chk('채팅 답 길이는 400 토큰', F.CHAT_MAX_TOKENS == 400)
ap = F.assign_system_prompt(PL, hints=F.nickname_hints('행걸 화이팅', PL), history=[('밍밍', 3)])
chk('배정 프롬프트에 힌트 · 이력 · JSON 한 줄', "'행걸' 는 '행복한걸' 의 줄임" in ap and '밍밍 3번' in ap and 'JSON 한 줄만' in ap)

head('④ 조종실 — 단추 · 이름표 · 다시 묻기 · 3분째 대기 알림')
CT = io.open(os.path.join(ROOT, 'controller.html'), encoding='utf-8').read()
btns = re.findall(r"onclick=\"aiAsk\('(\w+)'\)\">([^<]+)</button>", CT)
tiles = re.findall(r'id="ai-tile-(\w+)" onclick="aiAsk\(\'(\w+)\'\)"', CT)
chk('상황판 네 칸 — 대기함 · 대결 · 목표 · 퇴근빵', [a for a, _ in tiles] == ['pending', 'match', 'goal', 'race']
    and all(a == b for a, b in tiles), tiles)
chk('빠른 질문 단추 넷 — 상황판에 없는 것', [k for k, _ in btns] == ['rank', 'today', 'sig', 'flow'], btns)
chk('칸과 단추를 합치면 여덟 가지 다', sorted([k for k, _ in btns] + [a for a, _ in tiles]) == sorted(F.INTENTS))
chk('단추 이름표가 서버와 같다', all(F.INTENTS[k] == v for k, v in btns), btns)
chk('상황판은 패널이 열려 있을 때만 4초마다', 'function aiBoardRun(on)' in CT and 'aiBoardRun(open);' in CT
    and 'setInterval(aiBoardLoad, 4000)' in CT and "fetch('/api/ai/board')" in CT)
chk('머리에 AI 상태 점', 'id="ai-health"' in CT and "h.dataset.state = res.ai.state" in CT)
chk('패널 색은 조종실 토큰 — 파랑·보라 그라데이션이 없다', '#2563ff' not in CT and '#7c3aed' not in CT)
chk("AI 알림 '목표 넘었어요' 도 막대와 같은 셈(기여도 아님)", '(b2.contribution || 0)' not in CT
    and '+ (d.bjs || []).reduce((a2, b2) => a2 + (b2.score || 0), 0)' in CT)
chk('폰에서 패널을 열면 지급 창은 위로 · 백업 단추는 숨김', "document.body.classList.toggle('ai-open', open);" in CT
    and 'body.ai-open #ai-assign-toasts { top:12px; bottom:auto; }' in CT)
m = re.search(r'const AI_QUICK = \{(.*?)\};', CT, re.S)
jsq = dict(re.findall(r"(\w+): '([^']+)'", m.group(1))) if m else {}
chk('조종실 AI_QUICK 도 서버와 같다', jsq == F.INTENTS, jsq)
chk('단추는 intent 로 묻는다(AI 안 부름)', "JSON.stringify({ intent: intent })" in CT)
chk('답에 서버 계산 / AI 꼬리표', "const AI_SRC = { calc: '⚡ 서버 계산', ai: '🤖 AI' };" in CT)
chk('굵은 글씨 · 목록을 그린다(escape 먼저)', 'function aiFmt(text)' in CT and "escapeHTML(line).replace(/\\*\\*(.+?)\\*\\*/g" in CT)
chk('서버엔 말만 보낸다', 'aiChatLog.slice(-6).map(m => ({ role: m.role, content: m.content }))' in CT)
chk('붐빈 배정 추천은 다시 묻는다(세 번까지)', 'function auditAsk(don)' in CT and 'if (res.retry)' in CT
    and 'if (n <= 3)' in CT and '20000 * n' in CT)
chk('그새 처리된 후원은 다시 안 묻는다', "if (removedPendingIds.has(don.id) || !(gd.pending_donations || []).some(p => p && p.id === don.id)) return;" in CT)
chk("붐빔은 '모름' 과 따로 보인다", 'AI 가 붐벼요 — 곧 다시 물어봐요' in CT)
chk("'3분째 대기' 알림이 새 후원 번호를 읽는다", 'const mm = /^don_(\\d+)/.exec(p.id);' in CT and '/^don_(\\d+)$/.exec' not in CT)

head('⑤ 살아 있는 서버 — 단추 · 키 없이 계산 답 · 별명 추천')


def post(path, obj):
    r = urllib.request.Request(B + path, json.dumps(obj).encode(), H, method='POST')
    try:
        with urllib.request.urlopen(r, timeout=25) as res:
            return res.status, json.loads(res.read().decode() or '{}')
    except urllib.error.HTTPError as e:
        return e.code, {}
    except Exception as e:
        return 0, {'err': str(e)}


for k in F.INTENTS:
    c, d = post('/api/ai/chat', {'intent': k})
    chk(f'단추 {k} — 서버 계산으로 답한다', c == 200 and d.get('source') == 'calc' and d.get('reply'), (c, d))
c, d = post('/api/ai/chat', {'question': '지금 1등 누구야?'})
chk('AI 키가 없어도 알아본 질문은 계산으로 답한다', c == 200 and d.get('source') == 'calc'
    and '서버 계산으로 답했어요' in (d.get('reply') or ''), d)
c, d = post('/api/ai/chat', {'question': '오늘 분위기 어때?'})
chk('모르는 질문은 AI 가 없다고 말한다', c == 200 and d.get('source') == 'none' and 'NVIDIA_API_KEY' in (d.get('reply') or ''), d)
c, d = post('/api/audit/suggest', {'name': '별명시험', 'amount': 10000, 'message': '행걸 화이팅 ' + str(os.getpid()),
                                   'players': ['행복한걸', '밍밍']})
chk("AI 가 없을 때 별명만 겹치면 '확인 필요' 추천", c == 200 and d.get('target') == '행복한걸'
    and d.get('tier') == 'suggest' and d.get('confidence') == 0.72 and '글자로만' in (d.get('why') or ''), d)
chk('키가 없는 건 잠깐 막힌 게 아니다(다시 묻지 않는다)', not d.get('retry'), d)


def get(path, auth=True):
    r = urllib.request.Request(B + path, None, H if auth else {}, method='GET')
    try:
        with urllib.request.urlopen(r, timeout=25) as res:
            return res.status, json.loads(res.read().decode() or '{}')
    except urllib.error.HTTPError as e:
        return e.code, {}
    except Exception as e:
        return 0, {'err': str(e)}


c, d = get('/api/ai/board')
chk('상황판 주소 — 네 칸과 AI 상태', c == 200 and d.get('status') == 'success'
    and [x.get('intent') for x in d.get('tiles') or []] == ['pending', 'match', 'goal', 'race'], (c, d))
chk('검사 서버엔 키가 없다 → AI 꺼짐이라고', (d.get('ai') or {}).get('state') == 'off', d.get('ai'))
c, d = get('/api/ai/board', auth=False)
chk('상황판은 로그인해야 열린다(후원자 이름이 있다)', not (c == 200 and d.get('status') == 'success'), (c, d))

print()
print('=' * 74)
print('통과 %d · 실패 %d' % (len(OK), len(BAD)))
for n in BAD:
    print('   [실패] ' + n)
print('=' * 74)
