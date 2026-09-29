# -*- coding: utf-8 -*-
"""📺 방송 화면 개편 (2026-09-29) — 화면을 한 곳에서 정하는가.

왜 만들었나
  대표님: "위젯 개념으로 껐다 켰다 하잖아, 다른 방식으로 싹 다 드러내서 고치자".
  예전엔 스위치 25개 · 바꾸는 서버 길 12군데 · 몰래 가리는 규칙 5개가 흩어져 있었다.
  이제 화면은 show 하나(무대 · 고정 자리 · 알림 · 순서표 + 계산한 덮기)로 정한다.

여기서 지키는 것
  ① show.py 규칙 — 무대는 하나, 잠깐(슬롯·룰렛)은 끝나면 원래 무대로, 대결은 내려도 안 끝난다
  ② 옛 저장본(show 없음)은 옛 스위치에서 한 번 옮겨 담는다
  ③ /api/show — 무대 · 고정 자리 · 알림을 바꾸고, 옛 스위치가 따라 계산된다
  ④ 옛 스위치는 밖에서 못 바꾼다(통째 저장·설정 패치)
  ⑤ 폰처럼 옛 방식으로 대결을 켜고 끄면 무대가 따라간다
  ⑥ 순서표 — 다음 · 이전 · 고르기, 끝이면 알려준다
  ⑦ 방송 시작·끝은 무대를 비운다(고정 자리는 설정이라 남는다)
  ⑧ 덮기는 저장하지 않고 계산한다(시작·끝 화면 > 노래방 > 시그 리액션)

⚠️ pausetest 서버(5199)가 필요하다 — runall 이 띄운다.
"""
import copy
import json
import os
import sys
import time
import urllib.error
import urllib.request

sys.stdout.reconfigure(encoding='utf-8')
B = 'http://127.0.0.1:5199'
H = {'Content-Type': 'application/json', 'Authorization': 'Bearer sandboxsecret123456'}
PROJ = (os.environ.get('LM_PROJECT_ROOT')
        or os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')))
sys.path.insert(0, PROJ)
import show as S  # noqa: E402

OK, BAD = [], []


def chk(name, cond, detail=''):
    (OK if cond else BAD).append(name)
    print(('  [OK] ' if cond else '  [!!] ') + name + (('  -- ' + str(detail)[:140]) if detail else ''))


def req(path, obj=None, method=None, auth=True):
    data = json.dumps(obj).encode() if obj is not None else None
    r = urllib.request.Request(B + path, data, H if auth else {'Content-Type': 'application/json'},
                               method=method or ('POST' if data is not None else 'GET'))
    try:
        with urllib.request.urlopen(r, timeout=25) as res:
            return res.status, json.loads(res.read().decode() or '{}')
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode() or '{}')
        except Exception:
            return e.code, {}


def st():
    return req('/api/data')[1]


def base_state():
    return {'dicegame': {'enabled': False}, 'siggame': {'enabled': False}, 'pinball': {'enabled': False, 'running': False},
            'fundjar': {'enabled': False}, 'match_data': {'active': False}, 'hell': {'on': False},
            'roulette_enabled': False, 'slot_enabled': False, 'home_race_enabled': False}


print('=' * 74); print('① show.py 규칙 (서버 없이)'); print('=' * 74)
s = base_state()
S.set_stage(s, 'pinball')
chk('무대에 올리면 옛 스위치가 따라온다', s['pinball']['enabled'] is True and s['show']['stage'] == 'pinball')
S.set_stage(s, 'dicegame')
chk('무대는 하나 — 주사위를 올리면 핀볼이 내려간다', s['dicegame']['enabled'] and not s['pinball']['enabled'])
s['pinball']['running'] = True
S.set_stage(s, 'slot', temp=True)
chk('슬롯은 잠깐 — 돌아갈 곳을 기억한다', s['show']['stage'] == 'slot' and s['show']['ret'] == 'dicegame' and s['slot_enabled'])
chk('핀볼이 무대에 없으면 굴러가던 것도 멈춘다', s['pinball']['running'] is False)
S.set_stage(s, 'roulette', temp=True)
chk('잠깐 위에 잠깐 — 처음 자리를 지킨다', s['show']['stage'] == 'roulette' and s['show']['ret'] == 'dicegame')
S.end_temp(s, 'roulette')
chk('끝나면 원래 무대로 (슬롯이 아니라 주사위)', s['show']['stage'] == 'dicegame' and s['dicegame']['enabled'] and not s['roulette_enabled'])
chk('다른 것이 끝났다고 알려도 무대는 그대로', S.end_temp(s, 'slot') is None and s['show']['stage'] == 'dicegame')
S.set_stage(s, 'match')
chk('대결을 무대에 올리면 대결이 시작된다', s['match_data']['active'] is True)
S.set_stage(s, 'slot', temp=True); S.end_temp(s, 'slot')
chk('슬롯을 돌리고 와도 대결이 무대로 돌아오고 끝나지 않는다', s['show']['stage'] == 'match' and s['match_data']['active'])
S.set_stage(s, None)
chk('무대를 비워도 대결 기록은 그대로', s['match_data']['active'] is True and s['show']['stage'] is None)
chk('상시 슬롯(잠깐이 아님)은 돌아갈 곳이 없다', (S.set_stage(s, 'slot'), s['show']['ret'])[1] is None)
S.clear_stage(s, 'slot')
S.set_hud(s, 'best', True); S.set_hud(s, 'fundjar', True); S.set_alert(s, 'popup', False)
chk('고정 자리 · 알림이 옛 스위치로', s['best_enabled'] is True and s['fundjar']['enabled'] is True and s['popup_enabled'] is False)
chk('없는 칸은 거절', S.set_hud(s, 'nope', True) is False and S.set_alert(s, 'nope', True) is False)
rv = s['show']['rev']; S.set_hud(s, 'best', False)
chk('바뀔 때마다 번호가 오른다', s['show']['rev'] == rv + 1)

print(); print('=' * 74); print('② 옛 저장본 옮겨 담기'); print('=' * 74)
old = base_state(); old['siggame']['enabled'] = True; old['sig_tally_enabled'] = True; old['takeover_enabled'] = False
S.ensure(old)
chk('옛 스위치에서 무대를 읽는다', old['show']['stage'] == 'siggame')
chk('옛 스위치에서 고정 자리 · 알림을 읽는다', old['show']['hud']['sig_tally'] is True and old['show']['alerts']['takeover'] is False)
old2 = base_state(); old2['hell']['on'] = True
chk('지옥탈출이 떠 있었으면 그것이 무대', (S.ensure(old2), old2['show']['stage'])[1] == 'hell')
bad = {'show': {'stage': 'zzz', 'ret': 'slot', 'hud': {'best': 1, 'x': 1}, 'alerts': 'nope', 'cue_at': 'x'}}
S.ensure(bad)
chk('망가진 저장본도 온전한 모양으로', bad['show']['stage'] is None and bad['show']['ret'] is None
    and bad['show']['hud']['best'] is True and 'x' not in bad['show']['hud'] and bad['show']['cue_at'] == -1)

print(); print('=' * 74); print('③ /api/show'); print('=' * 74)
req('/api/server/start_broadcast', {'names': ['가', '나', '다']})
c, r = req('/api/show', {'stage': 'pinball'})
d = st()
chk('무대에 올린다', c == 200 and d['show']['stage'] == 'pinball' and d['pinball']['enabled'] is True, (c, d['show']['stage']))
chk('밖으로 나갈 때 한 줄 요약이 붙는다', '무대: 핀볼' in (d['show'].get('summary') or ''), d['show'].get('summary'))
c, r = req('/api/show', {'stage': 'nope'})
chk('없는 무대는 400', c == 400, c)
c, r = req('/api/show', {'stage': 'hell'})
chk('지옥탈출은 시작 전엔 무대에 못 올린다', c == 409, (c, r.get('message')))
c, r = req('/api/show', {'hud': {'donor_rank': True, 'notice': True}, 'alerts': {'takeover': False}})
d = st()
chk('고정 자리 · 알림', c == 200 and d.get('donor_rank_enabled') is True and d.get('notice_enabled') is True
    and d.get('takeover_enabled') is False, (c, d.get('donor_rank_enabled'), d.get('takeover_enabled')))
c, r = req('/api/show', {'hud': {'zzz': True}})
chk('없는 고정 자리는 400', c == 400, c)
c, r = req('/api/show', {'stage': None}, auth=False)
chk('로그인 없이는 못 바꾼다', c in (401, 403, 302), c)
c, r = req('/api/show')
chk('GET 도 된다(순서표까지)', c == 200 and 'cues' in r and r['show']['stage'] == 'pinball', c)
req('/api/show', {'alerts': {'takeover': True}})

print(); print('=' * 74); print('④ 옛 스위치는 밖에서 못 바꾼다'); print('=' * 74)
d = st(); body = {k: v for k, v in d.items() if k not in ('api_token', 'server_time')}
body.update({'slot_enabled': True, 'best_enabled': True, 'show': {'stage': 'slot'}})
req('/api/data', body)
d = st()
chk('통째 저장으로 보낸 옛 스위치 · show 는 무시', d['show']['stage'] == 'pinball' and d.get('slot_enabled') is False
    and d.get('best_enabled') is False, (d['show']['stage'], d.get('slot_enabled'), d.get('best_enabled')))
for k in ('show', 'slot_enabled', 'popup_enabled', 'ticker_enabled', 'home_race_enabled'):
    c, _ = req('/api/settings/patch', {k: True})
    chk('설정 패치로 %s 못 바꿈' % k, c == 400, c)

print(); print('=' * 74); print('⑤ 폰처럼 옛 방식 — 대결 켜기/끄기 · 룰렛 돌리기'); print('=' * 74)
md = copy.deepcopy(st()['match_data']); md['active'] = True; md['players'] = [{'name': '가', 'score': 0}]
c, _ = req('/api/settings/patch', {'match_data': md})
d = st()
chk('대결을 켜면 무대가 대결로', c == 200 and d['show']['stage'] == 'match' and d['pinball']['enabled'] is False, (c, d['show']['stage']))
r0 = copy.deepcopy(st().get('roulette') or {}); r0.update({'command': 'spin', 'command_time': int(time.time() * 1000)})
req('/api/settings/patch', {'roulette': r0})
d = st()
chk('룰렛을 돌리면 잠깐 무대에, 끝나면 대결로', d['show']['stage'] == 'roulette' and d['show']['ret'] == 'match', d['show'])
req('/api/roulette/winner', {'name': '가'})
d = st()
chk('룰렛 결과 뒤 대결로 돌아온다', d['show']['stage'] == 'match' and d['match_data']['active'], d['show']['stage'])
md = copy.deepcopy(d['match_data']); md['active'] = False
req('/api/settings/patch', {'match_data': md})
d = st()
chk('대결을 끄면 무대에서도 내려간다', d['show']['stage'] is None, d['show']['stage'])

print(); print('=' * 74); print('⑥ 순서표 (세이브 슬롯이 단계)'); print('=' * 74)
for p in (req('/api/presets')[1].get('presets') or []):
    req('/api/presets/delete', {'id': p['id']})
c, r = req('/api/show', {'cue': 'next'})
chk('비어 있으면 알려준다', c == 409 and '비어' in (r.get('message') or ''), (c, r.get('message')))
req('/api/show', {'stage': 'match', 'hud': {'best': False}})
req('/api/presets/save', {'name': '1차 대결'})
req('/api/show', {'stage': 'pinball', 'hud': {'best': True}})
req('/api/presets/save', {'name': '핀볼'})
req('/api/show', {'stage': None, 'hud': {'best': False}})
req('/api/presets/save', {'name': '휴식'})
ps = req('/api/presets')[1]['presets']
chk('단계 셋이 저장된다(무대 · 고정 자리 새 모양)', [p.get('stage') for p in ps] == ['match', 'pinball', None]
    and ps[1].get('hud', {}).get('best') is True, [(p.get('name'), p.get('stage')) for p in ps])
c, r = req('/api/show', {'cue': 'go', 'id': ps[0]['id']})
chk('고르면 그 단계로', c == 200 and r['show']['stage'] == 'match' and r['show']['cue_at'] == 0, (c, r.get('show', {}).get('stage')))
c, r = req('/api/show', {'cue': 'next'})
d = st()
chk('다음 ▶ — 핀볼 · 최고 후원 켜짐', c == 200 and d['show']['stage'] == 'pinball' and d.get('best_enabled') is True
    and d['show']['cue_at'] == 1, (c, d['show']['stage'], d.get('best_enabled')))
req('/api/show', {'cue': 'next'})
c, r = req('/api/show', {'cue': 'next'})
chk('끝에서 다음이면 알려준다', c == 409 and '끝' in (r.get('message') or ''), (c, r.get('message')))
c, r = req('/api/show', {'cue': 'prev'})
chk('◀ 이전', c == 200 and r['show']['stage'] == 'pinball' and r['show']['cue_at'] == 1, (c, r.get('show', {}).get('stage')))
c, r = req('/api/presets/apply', {'id': ps[2]['id']})
chk('예전 [불러오기] 도 같은 길 — 순서표 위치가 맞춰진다', c == 200 and r['show']['cue_at'] == 2 and r['show']['stage'] is None,
    (c, r.get('show', {}).get('cue_at')))
# ✏️ 순서표 편집 — 이름 · 순서 · 지우기. 옮기거나 지워도 '지금 단계' 표시는 같은 단계를 가리킨다
c, r = req('/api/presets/rename', {'id': ps[1]['id'], 'name': '핀볼 2판'})
chk('이름 바꾸기', c == 200 and [p['name'] for p in r['presets']] == ['1차 대결', '핀볼 2판', '휴식'], (c, r.get('message')))
c, r = req('/api/presets/move', {'id': ps[2]['id'], 'dir': -1})
chk('지금 단계(휴식)를 앞으로 옮기면 표시도 따라간다', c == 200 and [p['name'] for p in r['presets']] == ['1차 대결', '휴식', '핀볼 2판']
    and r['show']['cue_at'] == 1, (c, r.get('show', {}).get('cue_at')))
c, r = req('/api/presets/move', {'id': ps[0]['id'], 'dir': 1})
chk('다른 단계를 옮겨도 표시는 휴식에', c == 200 and [p['name'] for p in r['presets']] == ['휴식', '1차 대결', '핀볼 2판']
    and r['show']['cue_at'] == 0, (c, r.get('show', {}).get('cue_at')))
c, r = req('/api/presets/delete', {'id': ps[2]['id']})
chk('지금 단계를 지우면 그 앞을 가리킨다', c == 200 and r['show']['cue_at'] == -1 and len(r['presets']) == 2, (c, r.get('show', {}).get('cue_at')))
c, r = req('/api/show', {'cue': 'next'})
chk('그래서 다음 ▶ 은 지운 단계 다음 것(1차 대결)', c == 200 and r['show']['stage'] == 'match' and r['show']['cue_at'] == 0,
    (c, r.get('show', {}).get('stage')))
c, r = req('/api/presets/delete', {'id': ps[1]['id']})
chk('뒤 단계를 지워도 표시는 그대로', c == 200 and r['show']['cue_at'] == 0, (c, r.get('show', {}).get('cue_at')))
c, r = req('/api/presets/rename', {'id': ps[0]['id'], 'name': '   '})
chk('빈 이름은 막는다', c == 400, c)
req('/api/show', {'stage': 'pinball', 'hud': {'best': True}})
c, r = req('/api/presets/save', {'id': ps[0]['id']})
chk('📸 지금 화면으로 바꾸기 — 이름 · 개수는 그대로, 무대 · 고정 자리만 새로', c == 200 and len(r['presets']) == 1
    and r['preset']['id'] == ps[0]['id'] and r['preset']['name'] == '1차 대결' and r['preset']['stage'] == 'pinball'
    and r['preset']['hud']['best'] is True, (c, r.get('preset', {}).get('stage')))
CTLSRC = open(os.path.join(PROJ, "controller.html"), encoding="utf-8").read()
chk('조종실에 순서표 [편집] 단추', 'onclick="psEditToggle()"' in CTLSRC and 'id="ps-edit"' in CTLSRC)
chk('편집 중엔 단계를 눌러도 방송판이 안 바뀐다(고르기만)', "const click = psEditing ? 'psEditPick' : 'psApply';" in CTLSRC)
chk('지우기는 두 번 눌러야', 'psDelArmed = setTimeout(' in CTLSRC and "psCall('delete'" in CTLSRC)
chk('이름 · 순서 바꾸기 길', "psCall('rename'" in CTLSRC and "psCall('move'" in CTLSRC)
chk('지금 화면으로 바꾸기도 두 번 눌러야(같은 단계 id 로 저장)', "psOverArmed = setTimeout(" in CTLSRC and "psCall('save', { id: psPick })" in CTLSRC)
for p in ps:
    req('/api/presets/delete', {'id': p['id']})

print(); print('=' * 74); print('⑦ 방송 시작 · 끝'); print('=' * 74)
req('/api/show', {'stage': 'dicegame', 'hud': {'donor_rank': True}})
req('/api/server/start_broadcast', {'names': ['가', '나']})
d = st()
chk('방송 시작은 무대를 비운다', d['show']['stage'] is None and not d['dicegame'].get('enabled'), d['show']['stage'])
chk('고정 자리는 설정이라 남는다', d['show']['hud']['donor_rank'] is True and d.get('donor_rank_enabled') is True)

print(); print('=' * 74); print('⑧ 덮기는 계산한다'); print('=' * 74)
x = base_state()
chk('아무것도 없으면 없음', S.cover_of(x) is None)
x['reaction_mode'] = True
chk('시그 리액션', S.cover_of(x) == 'reaction')
x['karaoke_enabled'] = True; x['karaoke_video'] = 'abc'
chk('노래방이 리액션보다 먼저', S.cover_of(x) == 'karaoke')
x['stage_screen'] = {'mode': 'end'}
chk('끝 화면이 가장 먼저', S.cover_of(x) == 'screen_end')
req('/api/screen', {'mode': 'start'})
chk('서버가 내보내는 show 에 덮기가 실린다', st()['show'].get('cover') == 'screen_start', st()['show'].get('cover'))
req('/api/screen', {'mode': 'off'})

print(); print('=' * 74); print('⑨ 💬 소액 후원 띠 (1천~9천 원 — 맨 위 검은 띠)'); print('=' * 74)
x = base_state(); x['show'] = {'stage': None, 'hud': {}, 'alerts': {'popup': True, 'takeover': True, 'reaction_title': True}}
chk('개편 직후 저장본(small 칸 없음)도 소액 알림은 켜진 채로 읽는다', S.ensure(x)['alerts'].get('small') is True)
c, r = req('/api/show', {'alerts': {'small': False}})
chk('조종실에서 끌 수 있다', c == 200 and r['show']['alerts']['small'] is False, (c, r.get('show', {}).get('alerts')))
req('/api/show', {'alerts': {'small': True}})
OVSRC = open(os.path.join(PROJ, 'overlay.html'), 'rb').read().replace(b'\x00', b'').decode('utf-8')
CTLSRC2 = open(os.path.join(PROJ, 'controller.html'), encoding='utf-8').read()
chk('방송판에 맨 위 띠 자리', 'id="small-don"' in OVSRC and '#small-don { position: absolute; left: 0; top: 0; width: 100%;' in OVSRC)
chk('색은 트위치 알림과 같게 — 이름 · 금액 청록 #32C3A6, 검은 테두리', '#small-don .sd-hl { color: #32C3A6; }' in OVSRC and '-webkit-text-stroke: 9px #000' in OVSRC)
chk('1만 원 미만 · 0원 초과 · 시그니처 신청 글은 카드로', 'const SMALL_DON_MAX = 10000;' in OVSRC and 'amt > 0 && amt < max' in OVSRC
    and "startsWith('[시그니처 신청:')" in OVSRC)
chk('[소액 후원]이 켜져 있으면 띠, 꺼져 있으면 예전 카드', "shAlert('small', d) && isSmallDon(d.latest_donation, d)" in OVSRC
    and "(_smallDon || shAlert('popup', d))" in OVSRC and 'showSmallDon(d.latest_donation);' in OVSRC)
chk('띠는 시그니처 대기줄을 붙잡지 않는다(카드처럼 2초 기다리지 않는다)', 'showSmallDon(d.latest_donation);\n                        checkReactionQueue();' in OVSRC)
chk('몰리면 줄 서되 밀린 만큼 짧게 — 아무도 건너뛰지 않는다', 'const hold = left >= 4 ? 2000 : (left >= 2 ? 3000 : 5000);' in OVSRC
    and 'smallDonQ.push(don);' in OVSRC and 'splice' not in OVSRC[OVSRC.find('function showSmallDon'):OVSRC.find('function smallDonNext')])
chk('조종실 알림 줄에 [소액 후원] 칩', "['small', '소액 후원']" in CTLSRC2)

print()
print('=' * 74)
print('통과 %d · 실패 %d' % (len(OK), len(BAD)))
print('=' * 74)
sys.exit(1 if BAD else 0)
