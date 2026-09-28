# -*- coding: utf-8 -*-
"""server.py 에서 떼어 낸 기능들.

각 파일은 server 의 공용 도구(app · file_lock · load_data · save_data · broadcast_event …)를
`from server import …` 로 빌려 쓴다. 그래서 **server.py 맨 아래에서만** 불러야 한다
(그 전에는 빌려 올 이름이 아직 없다). 여기 파일끼리는 서로 직접 부르지 않고 server 를 거친다.
"""
