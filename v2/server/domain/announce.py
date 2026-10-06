# -*- coding: utf-8 -*-
"""🤖 진행봇 설정 — 조종실이 켜고 끄고, 봇(v2/tools/bot_v2.py)이 그 값을 보고 스스로 입을 다문다.

옛 것: server.py DEFAULT_STATE['announce_bot'](1277~1302) · 불러올 때 속칸 채우기(1813~1826)
       · features/announce.py(/api/announcebot 검사 · _yt_video_id) · controller.html 진행봇 탭(10819~10935)

조각
  announce_bot    (비공개) 옛 모양 그대로 — enabled · min_interval_sec · live_url · live_video_id
                            · say{donation, rank_top, rank_close, goal, dice, idle} · notices{account_min, rank_min, fundjar_min}
  announce_status (비공개) 봇이 스스로 알린 것 — mode('dry' 입 막음 | 'live' 진짜로 침) · since(붙은 때) · pid · host · yt(유튜브 준비 글)

명령(전부 로그인 필요)
  bot.set    {enabled?|on?, min_interval_sec?, live_url?, say?{이름: 참/거짓}, notices?{이름: 분}}  — 옛 /api/announcebot 과 같은 검사
  bot.say    {key, on?}       스위치 하나(on 을 안 주면 뒤집기). 모르는 이름은 거절
  bot.notice {key, min}       되풀이 안내 하나(분, 0~120 · 0 이면 끔)
  bot.hello  {mode, pid?, host?, yt?}  봇이 붙을 때 스스로 부른다 — 조종실이 '봇이 어떤 모드로 붙어 있나' 를 볼 수 있게

옛 규칙 그대로
  - 간격 5~600초 · 안내 0~120분 · say/notices 의 모르는 이름은 조용히 버린다(bot.set — 오타로 쓰레기 칸이 생기면
    봇은 안 보는데 조종실에는 켜진 것처럼 남는다).
  - 라이브 주소: watch?v= · youtu.be/ · /live/ · /shorts/ · /embed/ · 번호 11글자만. '' 은 **비우기**(봇이 채널에서 찾는다),
    못 읽으면 **거절**(오타를 '비움' 으로 받아들이면 봇이 엉뚱한 데를 본다).
  - 방송 시작 · 끝에 설정을 지우지 않는다(다음 방송에도 쓰는 설정).
v2 에서 고친 것
  - 한 명령 = 전부 아니면 전무. 옛 것은 enabled 를 먼저 바꾼 뒤 간격 검사에서 400 을 내도 enabled 는 바뀐 채 남았다.
  - 옛 서버는 '봇이 떠 있는지' 를 몰랐다(조종실이 단정하지 못했다). 봇이 붙을 때 bot.hello 로 알린다.
    끊김은 /api/screens 의 kind 'bot' 으로 본다(hub.KINDS 에 'bot' 을 넣어야 'other' 로 안 묻힌다).
"""
import copy
import re

from ..bus import CommandError, command
from ..state import slice_
from . import session as ses

DEFAULT = {
    'enabled': True,            # 전체 스위치. 끄면 봇이 한마디도 안 한다(후원 인사만 쌓아 둔다)
    'min_interval_sec': 25,     # 최소 몇 초에 한 줄
    'live_url': '',             # 대표님이 붙여넣은 주소 그대로(화면에 도로 보여 준다)
    'live_video_id': '',        # 거기서 뽑은 영상 번호 — 봇이 실제로 쓰는 값
    'say': {'donation': True, 'rank_top': True, 'rank_close': False, 'goal': False, 'dice': False, 'idle': True},
    'notices': {'account_min': 7, 'rank_min': 0, 'fundjar_min': 0},
}
INTERVAL_MIN, INTERVAL_MAX = 5, 600
NOTICE_MAX = 120
MODES = ('dry', 'live')

slice_('announce_bot', False, lambda: copy.deepcopy(DEFAULT))
slice_('announce_status', False, lambda: {'mode': '', 'since': 0, 'pid': 0, 'host': '', 'yt': ''})

_YT_ID_RE = re.compile(r'(?:v=|/live/|youtu\.be/|/shorts/|/embed/)([A-Za-z0-9_-]{11})')


def yt_video_id(text):
    """붙여넣은 라이브 주소 → 영상 번호(11글자). '' = 비우라는 뜻 · None = 못 읽었다(옛 _yt_video_id 그대로)."""
    t = (text or '').strip()
    if not t:
        return ''
    m = _YT_ID_RE.search(t)
    if m:
        return m.group(1)
    if re.fullmatch(r'[A-Za-z0-9_-]{11}', t):
        return t
    return None


def _as_int(v):
    """숫자로 — 못 바꾸면 None. 참/거짓 · 목록 · 사전은 숫자가 아니다(옛 _as_int)."""
    if isinstance(v, bool) or v is None:
        return None
    if isinstance(v, (int, float)):
        return int(v)
    try:
        return int(str(v).strip())
    except (TypeError, ValueError):
        return None


def _fill(b):
    """속칸 채우기 — 저장본이 옛것이라 새 스위치 칸이 없을 때(옛 server.py 1813~1826 과 같은 이유)."""
    for k, v in DEFAULT.items():
        if k in ('say', 'notices'):
            if not isinstance(b.get(k), dict):
                b[k] = copy.deepcopy(v)
            else:
                for kk, vv in v.items():
                    b[k].setdefault(kk, vv)
        else:
            b.setdefault(k, v)
    return b


def _edit(ctx):
    b = ctx.edit('announce_bot')
    if not isinstance(b, dict):
        b = copy.deepcopy(DEFAULT)
        ctx.put('announce_bot', b)
    return _fill(b)


def _notice_min(v):
    m = _as_int(v)
    if m is None or not 0 <= m <= NOTICE_MAX:
        raise CommandError('안내 간격은 0~%d분 사이입니다 (0 이면 끔)' % NOTICE_MAX)
    return m


def apply(b, body):
    """설정 바꾸기 본문 — bot.set 과 옛 백업 옮기기가 같이 쓴다. 이상하면 CommandError(부르는 쪽 명령이 통째로 무른다)."""
    if 'enabled' in body or 'on' in body:
        b['enabled'] = bool(body.get('enabled') if 'enabled' in body else body.get('on'))
    if body.get('min_interval_sec') is not None:
        iv = _as_int(body.get('min_interval_sec'))
        if iv is None or not INTERVAL_MIN <= iv <= INTERVAL_MAX:
            raise CommandError('간격은 %d~%d초 사이입니다' % (INTERVAL_MIN, INTERVAL_MAX))
        b['min_interval_sec'] = iv
    if 'live_url' in body:
        raw = str(body.get('live_url') or '').strip()
        vid = yt_video_id(raw)
        if vid is None:
            raise CommandError('라이브 주소를 못 읽었습니다. 유튜브 주소를 그대로 붙여넣어 주세요')
        b['live_url'] = raw[:300]
        b['live_video_id'] = vid
    say = body.get('say')
    if say is not None:
        if not isinstance(say, dict):
            raise CommandError('say 는 {이름: 참/거짓} 모양이어야 합니다')
        for k, v in say.items():
            if k in DEFAULT['say']:                 # 모르는 이름은 조용히 버린다(옛 것과 같다)
                b['say'][k] = bool(v)
    notices = body.get('notices')
    if notices is not None:
        if not isinstance(notices, dict):
            raise CommandError('notices 는 {이름: 분} 모양이어야 합니다')
        for k, v in notices.items():
            if k in DEFAULT['notices']:
                b['notices'][k] = _notice_min(v)
    return b


@command('bot.set')
def bot_set(ctx, data):
    """옛 /api/announcebot — 보낸 칸만 바꾼다. 하나라도 틀리면 아무것도 안 바뀐다."""
    apply(_edit(ctx), data)


@command('bot.say')
def bot_say(ctx, data):
    """스위치 하나. on 을 안 주면 뒤집는다. ⚠️ 하나만 고르는 명령이라 모르는 이름은 거절한다(조용히 버리면 눌러도 안 바뀐다)."""
    key = str(data.get('key') or '')
    if key not in DEFAULT['say']:
        raise CommandError('모르는 스위치: %s (있는 것: %s)' % (key, ' · '.join(DEFAULT['say'])), 404)
    b = _edit(ctx)
    b['say'][key] = bool(data['on']) if 'on' in data else not b['say'].get(key)


@command('bot.notice')
def bot_notice(ctx, data):
    key = str(data.get('key') or '')
    if key not in DEFAULT['notices']:
        raise CommandError('모르는 안내: %s (있는 것: %s)' % (key, ' · '.join(DEFAULT['notices'])), 404)
    _edit(ctx)['notices'][key] = _notice_min(data.get('min'))


@command('bot.hello')
def bot_hello(ctx, data):
    """봇이 붙을 때 스스로 알린다. 설정(announce_bot)은 안 건드린다 — 봇은 설정을 **읽기만** 한다."""
    mode = str(data.get('mode') or '')
    if mode not in MODES:
        raise CommandError('mode 는 dry · live 중 하나입니다')
    ctx.put('announce_status', {'mode': mode, 'since': ctx.now, 'pid': _as_int(data.get('pid')) or 0,
                                'host': str(data.get('host') or '')[:60], 'yt': str(data.get('yt') or '')[:200]})


def import_old(ctx, old):
    """옛 백업(상태 JSON)의 announce_bot 을 옮긴다 — migrate.admin.import_old 가 부른다. 옮겼으면 True.
       ⚠️ 옛 저장본은 검사를 안 거친 값일 수 있다 → 같은 검사(apply)를 지난다. 틀린 값이면 그 명령 전체가 무른다."""
    ab = old.get('announce_bot') if isinstance(old, dict) else None
    if not isinstance(ab, dict):
        return False
    body = {k: ab[k] for k in ('enabled', 'min_interval_sec', 'live_url', 'say', 'notices') if k in ab}
    apply(_edit(ctx), body)
    return True


def _normalize(ctx, data):
    """방송 시작 때 속칸만 채운다(값은 그대로) — 봇은 방송 중에만 말하니, 그 전에 새 스위치 칸이 생겨 있으면 된다."""
    b = ctx.read('announce_bot')
    if not isinstance(b, dict) or _fill(copy.deepcopy(b)) != b:
        _edit(ctx)


ses.ON_START.append(_normalize)
