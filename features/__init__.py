# -*- coding: utf-8 -*-
"""server.py 에서 떼어 낸 기능들 (2026-09-29).

어디에 무엇이 있나
  게임     pinball · dicegame · siggame · hell · extra_game · offwork(퇴근빵)
  방송판   show_api(/api/show · 세이브 슬롯) · screens(시작·끝 화면) · notice(전광판) · reaction(리액션 대기줄 · 슬롯)
           effects(효과 · 룰렛 당첨 · 모금함 · 대결 시간 끝) · layout(위젯 자리)
  후원     donation(후원 접수) · score(점수 넣기) · donor_memory(후원자 기억) · vip · excluded(순위에서 뺄 이름)
           account_video(계좌 영상) · ranking(이번 방송 순위) · bjs(선수 일괄 등록)
  시그니처 signatures(등록 · 수정 · 삭제) · signature_play(목록 · 바로 틀기)
  기록     archive(지난 방송 · 월별 순위) · logs(수동 조작 이력) · uistats(클릭 기록)
  도구     ai(NIM 제안 · AI 채팅) · clip(쇼츠 클립) · announce(안내 봇) · streamdeck
  화면     pages(로그인 · 처음 설정 · 각 화면 파일 · 효과음 · 영상 · 정적 파일)
  운영     versions(버전 되돌리기) · legal(개인정보처리방침 · 약관 · /health)

server.py 에 남은 것: DB · 로그인 규칙 · SSE · 상태 저장/불러오기 · /api/data · 서버 상태(/api/health) ·
  방송 시작/종료 · 스냅샷/시간 여행 · 은행 원장 · 설정 바꾸기 · GUI — 서버의 기억(MEMORY_STATE)을
  통째로 바꾸는 코드는 server.py 에 둔다. 다른 파일로 옮기면 서로 다른 기억을 보게 된다.

규칙
- 각 파일은 공용 도구(app · file_lock · load_data · save_data · broadcast_event …)를
  `from server import …` 로 빌려 쓴다. 그래서 **server.py 맨 아래 한 곳에서만** 불러야 한다
  (그 전에는 빌려 올 이름이 아직 없다). 남의 것을 빌려 쓰는 파일이 뒤에 온다.
- 여기 파일끼리는 서로 직접 부르지 않고 server 를 거친다.
- 연습 서버가 가짜로 바꿔 끼우는 시그니처 조회(supabase_* · _supabase_ready)는 `server.X(...)` 로
  부를 때마다 찾는다. `from server import` 로 받아 두면 가짜로 바꿔도 여기는 진짜를 부른다.
- 새 기능은 여기 새 파일로 만들고 server.py 맨 아래 묶음에 한 줄 더한다.
"""
