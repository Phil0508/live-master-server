# -*- coding: utf-8 -*-
"""서버 코드 글자 읽기 — server.py 와 거기서 떼어 낸 features/*.py 를 이어 붙여 돌려준다.

server.py 를 기능별 파일로 나누면서(2026-09-29), '서버 코드에 이 글자가 있나'를 보는 검사들이
server.py 한 파일만 읽으면 옮겨 간 코드를 못 찾는다. 검사는 이 함수로 서버 코드 전체를 읽는다.
"""
import glob
import io
import os


def server_src(root):
    parts = [os.path.join(root, 'server.py')] + sorted(glob.glob(os.path.join(root, 'features', '*.py')))
    return '\n\n'.join(io.open(p, encoding='utf-8', errors='replace').read() for p in parts if os.path.exists(p))
