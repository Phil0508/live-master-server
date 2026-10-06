# -*- coding: utf-8 -*-
"""🔄 v2 조각(slices) → 옛 상태 모양 — 옛 진행봇(bot/announce.py)의 판단 코드를 **고치지 않고** 쓰려고.

순수 함수 하나(to_old). 서버도, 네트워크도, 옛 봇도 안 부른다 → 검사하기 쉽다(v2/tests/test_oldshape.py).

옛 봇이 읽는 칸(bot/announce.py 의 st.get / cur.get / prev.get 전부)과 v2 에서 가져오는 곳:
  broadcast_active  ← session.live
  bjs               ← players.list[{name, score, contribution}]        (순위 · 1위 바뀜 · 접전 · 순위 안내)
  extra_bjs         ← players.extra                                      (봇은 안 본다 — 옛 모양을 맞춰 둔 것)
  bottom_fixed      ← players.bottom{name, score}                        (목표 게이지 셈)
  target_goal       ← goal.target · goal_offset ← goal.offset
  latest_donation   ← popup.donation{id, name, amount, message, at(ms)} → {name, amount, message, time(초), id, display_only?}
                      ⚠️ 옛 봇은 time 이 바뀌면 '새 후원' 으로 본다. at(ms) 을 초로 바꿔 옮긴다. 비어 있으면 time 0(= 없음).
  reaction_queue    ← queue.items(맨 앞 = 방송판에서 재생 중 — 옛 것과 같다). id · donator · amount 로 후원과 짝을 짓는다
  reaction_paused   ← queue.paused
  dicegame          ← dicegame(action 은 옛 모양 그대로) + enabled = (show.stage == 'dicegame')  — v2 엔 enabled 스위치가 없다
  account           ← account{bank, acc_num, name}
  fundjar           ← fundjar{name, enabled, seed, score}
  donor_tally       ← tallies.donors{정규화이름: {name, total, count}} → {이름: {total, count}}
  announce_bot      ← announce_bot(조종실 설정, 비공개 조각 — 로그인해야 온다)
                      ⚠️ 조각이 아예 없으면(서버에 announce 모듈을 안 붙였거나 로그인 안 됨) {'enabled': False} 로 둔다.
                         조종실이 끌 수 없는 봇이 문구표대로 떠들게 두지 않는다.
"""

MISSING_BOT = {'enabled': False, '_missing': True}


def _d(sl, name):
    v = sl.get(name)
    return v if isinstance(v, dict) else {}


def _int(v):
    if isinstance(v, bool):
        return int(v)
    try:
        return int(v or 0)
    except (TypeError, ValueError):
        try:
            return int(float(v))
        except (TypeError, ValueError):
            return 0


def _rows(rows):
    out = []
    for r in rows if isinstance(rows, list) else []:
        if isinstance(r, dict) and r.get('name'):
            out.append({'name': str(r['name']), 'score': _int(r.get('score')), 'contribution': _int(r.get('contribution'))})
    return out


def latest_donation(popup):
    d = (popup or {}).get('donation')
    if not isinstance(d, dict):
        return {'name': '', 'amount': 0, 'message': '', 'time': 0}
    out = {'name': str(d.get('name') or ''), 'amount': _int(d.get('amount')), 'message': str(d.get('message') or ''),
           'time': _int(d.get('at')) / 1000.0, 'id': str(d.get('id') or '')}
    if d.get('display_only'):
        out['display_only'] = True
    return out


def to_old(sl):
    """v2 조각 사전 → 옛 상태 사전. 매번 새 사전을 만든다(옛 봇이 prev/cur 로 들고 있어도 서로 안 엉킨다)."""
    sl = sl if isinstance(sl, dict) else {}
    players, goal, queue, show = _d(sl, 'players'), _d(sl, 'goal'), _d(sl, 'queue'), _d(sl, 'show')
    bottom = players.get('bottom') if isinstance(players.get('bottom'), dict) else {}
    dice = dict(_d(sl, 'dicegame'))
    dice['enabled'] = show.get('stage') == 'dicegame'
    acc, jar = _d(sl, 'account'), _d(sl, 'fundjar')
    donors = _d(sl, 'tallies').get('donors')
    bot = sl.get('announce_bot')
    return {
        'broadcast_active': bool(_d(sl, 'session').get('live')),
        'bjs': _rows(players.get('list')),
        'extra_bjs': _rows(players.get('extra')),
        'extra_active': bool(players.get('extra_active')),
        'bottom_fixed': {'name': str(bottom.get('name') or '운영비'), 'score': _int(bottom.get('score'))},
        'target_goal': _int(goal.get('target')),
        'goal_offset': _int(goal.get('offset')),
        'latest_donation': latest_donation(_d(sl, 'popup')),
        'reaction_queue': [dict(x) for x in (queue.get('items') or []) if isinstance(x, dict)],
        'reaction_paused': bool(queue.get('paused')),
        'dicegame': dice,
        'account': {'bank': str(acc.get('bank') or ''), 'acc_num': str(acc.get('acc_num') or ''),
                    'name': str(acc.get('name') or '')},
        'fundjar': {'name': str(jar.get('name') or '모금함'), 'enabled': bool(jar.get('enabled')),
                    'seed': _int(jar.get('seed')), 'score': _int(jar.get('score'))},
        'donor_tally': {str(v.get('name') or k): {'total': _int(v.get('total')), 'count': _int(v.get('count'))}
                        for k, v in (donors.items() if isinstance(donors, dict) else []) if isinstance(v, dict)},
        'announce_bot': _copy_bot(bot) if isinstance(bot, dict) else dict(MISSING_BOT),
    }


def _copy_bot(b):
    out = dict(b)
    for k in ('say', 'notices'):
        if isinstance(out.get(k), dict):
            out[k] = dict(out[k])
    return out
