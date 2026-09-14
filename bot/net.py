# -*- coding: utf-8 -*-
"""🌐 IPv4 로만 나간다.

왜 이게 필요한가 (2026-09-14 에 실제로 겪은 것):
  방송 컴퓨터는 IPv6 주소를 **갖고는 있는데** 인터넷으로 나가는 IPv6 길이 없다.
      fdee:870:59eb:… ← 내부 전용(ULA). 바깥으로 못 나간다
      2620:9b::…      ← Hamachi 가 붙인 것. 역시 바깥 길이 아니다
  그런데 www.googleapis.com 은 AAAA(IPv6) 주소를 **여덟 개**나 준다. 그대로 두면
  여덟 개를 하나씩 다 기다린 뒤에야 IPv4 로 넘어간다.

  실측: 그냥 붙으면 48초 → 168초. IPv4 로만 붙으면 **0.1초**.

  이것 때문에 계정 연동이 두 번이나 '멈춘 것처럼' 보였다. 막힌 게 아니라 기어가고 있었다.

⚠️ 이 컴퓨터의 IPv6 설정을 고치는 게 더 근본적이지만, 그건 방송 컴퓨터 전체에 영향이
   가는 일이라 사장님이 정할 몫이다. 봇은 봇만 확실히 해 둔다.
⚠️ 이 프로그램 안에서만 바꾼다 — 다른 프로그램은 안 건드린다.
"""
import socket

_ORIGINAL = None


def force_ipv4():
    """이 프로그램이 여는 모든 연결을 IPv4 로 고정한다. 두 번 불러도 안전하다."""
    global _ORIGINAL
    if _ORIGINAL is not None:
        return
    _ORIGINAL = socket.getaddrinfo

    def _only_v4(host, port, family=0, *args, **kwargs):
        return _ORIGINAL(host, port, socket.AF_INET, *args, **kwargs)

    socket.getaddrinfo = _only_v4


def undo():
    """되돌린다 — 검사에서 쓴다."""
    global _ORIGINAL
    if _ORIGINAL is not None:
        socket.getaddrinfo = _ORIGINAL
        _ORIGINAL = None
