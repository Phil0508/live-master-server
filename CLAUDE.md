# 📊 엑셀 방송(라이브 마스터) — 이 폴더 안내 (Claude Code 용)

⚠️ 이 저장소는 GitHub 에 **공개**다. 이 파일에도 비밀번호 · 열쇠 · 알림 주제 이름 같은 건 적지 않는다.

담당 셋(엑셀 방송 · 크루 사이트 · 엔젤 스튜디오) · 서로 이어진 곳 · 대표님과 일하는 법은 위 폴더 `AngelCompany/CLAUDE.md` 에 있다(이 PC 에서는 같이 읽힌다).
그 파일이 없는 곳(다른 컴퓨터에서 이 저장소만 받았을 때)에서도 꼭 지킬 것:
- 대표님은 개발자가 아니다 → 쉬운 말 · 결론 먼저.
- **main 에 push = 운영 배포** → 대표님이 "올려" 할 때만, 방송 중(수 17:00 ~ 목 03:00)엔 절대 안 한다.
- 크루 사이트 시그리스트가 `/api/signatures/board` 를, 엔젤오락실 랭킹이 `/api/oraksil/donors` 를 읽는다 — 칸 이름을 바꾸면 사이트가 깨진다.


## 무엇

엔젤오락실 수요일 엑셀 방송을 돌리는 프로그램. 후원(투네이션 · 계좌)을 받아 선수 점수 · 시그니처 연출 · 게임판(주사위 · 룰렛 · 슬롯 · 시그뒤집기 · 핀볼 · 퀴즈 …)을 방송판에 띄우고, 대표님은 조종실에서 부린다.

## 운영
- 서버: Vultr 서울 · `ssh live` · 경로 `/opt/livemaster` · 유닛 `livemaster`. 주소 https://엔젤컴퍼니.메인.한국 — 퓨니코드는 손으로 짓지 말고 `'엔젤컴퍼니.메인.한국'.encode('idna').decode()`.
- **main 에 push = 배포**: 서버의 auto-deploy 가 2분마다 origin/main 을 받아 재시작한다. push 전에 `git log origin/main..HEAD` 로 올라갈 커밋을 본다.
- 되돌리기: 조종실 → 시스템 → 버전(최근 20개).
- 상태 보기(읽기만, 방송 중에도 됨): `GET /api/health` · `/health` 페이지. 방송 전 점검표 `/api/preflight`(로그인).
- 후원 길: `toon_listener.py` → `/api/donation`. 못 보내면 `donation_spool.jsonl` 에 적었다가 10초마다 다시 보낸다(이 파일이 계속 남으면 서버가 안 뜬 것).
- 시그니처: Supabase(signatures 표 · Storage). 이 PC 열쇠는 `SUPABASE_CREDENTIALS.txt`(git 밖).
- 새로 짜는 판 **v2**: 설계 · 진행표는 `v2/ARCHITECTURE.md` 가 원본. 시험판 `:8443/controller/`. auto-deploy 는 v2 를 재시작하지 않는다.

## 구조
- `server.py`(공용 · 상태 · 로그인) + `features/`(기능별, 지도는 `features/__init__.py`) — 새 기능은 features/ 새 파일 + server.py 맨 아래 묶음에 한 줄.
- 화면: `controller.html`(조종실) · `overlay.html`(방송판, OBS) · `admin.html`(편집기) · `manual_send.html`(후원 콘솔) · `mobile.html`(폰) · `streamdeck.html`
- 기능별 설계 노트: `docs/`. ⚠️ `PROJECT_OVERVIEW.md` · `PROJECT_STATUS.md` 는 Render 시절 옛 문서 — 믿지 말 것.

## 검사
- `python tests/runall.py` — 전부(15분쯤). 끝에 **'문제 있는 항목: 0개'** 여야 올린다.
- 이 PC 에서 띄우기: `.claude/launch.json` 의 `livemaster`(:5000, HEADLESS=1).

## 조심
- `overlay.html` 에 널 문자 2개 → `grep -a`. 줄바꿈이 섞여 있다(server.py · controller.html CRLF, overlay.html LF) — `.gitattributes` 에 `* text=auto` 금지. 맥에서는 클론 전에 `git config --global core.autocrlf input`.
- 방송판 `</div>` 하나 때문에 게임판들이 후원 팝업 위로 올라온 사고(10-06) → `tests/overlay_structure_test.py`.
- 끊긴 실시간 연결이 쌓이면 점수가 안 들어간다(09-30) — 서버 8080 의 CLOSE-WAIT · 스레드 수부터 본다.
- 방송 중 재시작은 끊긴 연결 사고를 부를 수 있다 — 허락을 받았어도 위험을 먼저 말하고 방송 뒤로 미루자고 한다.
