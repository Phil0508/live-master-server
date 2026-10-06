# -*- coding: utf-8 -*-
"""🎬 방송 한 회(session) — 시작 · 끝.

session 조각: live(방송 중인가) · id(이번 방송 번호) · started_at · ended_at
⚠️ live 는 배포 잠금(/api/deploy/ok)의 근거다 — 방송 중엔 자동 배포가 기다린다.
"""
import time
import uuid

from ..bus import CommandError, command
from ..state import slice_

slice_('session', True, lambda: {'live': False, 'id': '', 'started_at': 0, 'ended_at': 0})
slice_('session_log', False, lambda: [])     # 지난 방송들 [{id, started_at, ended_at}] — 최근 200회


def session_id(ctx):
    return ctx.read('session').get('id') or ''


@command('session.start')
def start(ctx, data):
    s = ctx.edit('session')
    if s['live']:
        raise CommandError('이미 방송 중입니다', 409)
    s.update({'live': True, 'id': time.strftime('%Y%m%d-%H%M', time.localtime(ctx.now)) + '-' + uuid.uuid4().hex[:4],
              'started_at': ctx.now, 'ended_at': 0})
    log = ctx.edit('session_log')
    log.append({'id': s['id'], 'started_at': ctx.now, 'ended_at': 0})
    del log[:-200]
    for fn in ON_START:
        fn(ctx, data)


@command('session.end')
def end(ctx, data):
    s = ctx.edit('session')
    if not s['live']:
        raise CommandError('방송 중이 아닙니다', 409)
    for fn in ON_END:
        fn(ctx, data)
    s.update({'live': False, 'ended_at': ctx.now})
    for row in reversed(ctx.edit('session_log')):
        if row['id'] == s['id']:
            row['ended_at'] = ctx.now
            break


# 다른 조각들이 방송 시작 · 끝에 할 일을 여기 건다(예: 대기함 비우기)
ON_START, ON_END = [], []
