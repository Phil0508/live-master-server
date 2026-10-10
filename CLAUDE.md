# 엔젤컴퍼니 — 이 폴더 안내 (Claude Code 용)

⚠️ 이 저장소는 GitHub 에 **공개**다. 이 파일에도 비밀번호 · 열쇠 · 알림 주제 이름 같은 건 적지 않는다.

## 담당 셋 — 한 창은 한 담당만

| 담당 | 창을 여는 폴더 | 무엇 | 어디서 돌아가나 |
|---|---|---|---|
| 📊 **엑셀 방송**(라이브 마스터) | `새로다시시작` (여기) | 엔젤오락실 수요일 엑셀 방송 — 방송 서버 · 조종실 · 방송판(OBS) · 투네이션 리스너 | Vultr 서울 · https://엔젤컴퍼니.메인.한국 |
| 🌐 **크루 사이트** | `새로다시시작/crew` | crew.angelcompany.me — 멤버 · 시그리스트 · 커뮤니티 · 멤버 모집 · 관리자 | Azure `studio` 서버 |
| 🎥 **엔젤 스튜디오** | `새로다시시작/crew/studio` | 멤버용 윈도우 방송 프로그램(OBS 대신) | 멤버 PC · 새 판은 크루 사이트로 나간다 |

- 담당 창은 **그 폴더에서 연다** — 그래야 그 폴더 안내(CLAUDE.md)가 맨 앞에 온다. 위 폴더 안내도 같이 읽힌다.
- 다른 담당 일이 들어오면 "그건 ○○ 창에서 하는 게 좋아요" 하고 알려 준다. 아주 작은 것만 말하고 여기서 한다.

## 서로 이어진 곳 — 한쪽을 고치면 다른 쪽도 본다

- **크루 사이트 시그리스트 ← 방송 서버** `GET /api/signatures/board`(금액 · 이름 · 그림 · 소리, 번호 없음). 칸 이름을 바꾸면 사이트 시그리스트가 깨진다(사이트는 2분 기억 · 못 받으면 지난 목록).
- 방송 서버 공개 `GET /api/signatures`(번호 · 그림 · 소리, 순서 섞음) — 방송판 미리 받기 · 시그게임이 쓴다.
- **엔젤 스튜디오 → 크루 사이트**: 켤 때 로그인(`/api/app/*`) · 새 판(`/api/app/latest` · downloads) · 후원 알림 · 순위 · 게이지(방송 화면 주소 `/o/…`).
- 구글 클라우드 프로젝트 **angel-crew** 하나에 사이트 구글 로그인 · 유튜브 API 키 · 스튜디오 유튜브 연결(데스크톱 클라이언트)이 같이 있다.

## 대표님과 일하는 법(세 담당 공통)

- 대표님은 개발자가 아니다 → **쉬운 말 · 결론 먼저 · 빗대어**. 영어 함수 · 파일 이름은 꼭 필요할 때만.
- 대표님은 **폰으로** 본다 → 화면 시안은 Artifact 링크로, 결이 다른 2~3벌 + '지금 모습' 비교.
- **운영에 올리기(push · 배포 · 새 판)는 대표님이 "올려" 할 때만.** 검사를 통과해도 알아서 올리지 않는다.
- **방송 중**(엔젤오락실: 수 17:00 ~ 목 03:00, 그 밖에도 대표님이 방송 중이라 하면)에는 방송 서버에 push · 설정 바꾸기 · 상태 바꾸는 요청 금지. 같은 PC 에서 무거운 시험도 돌리지 않는다(방송 프로그램이 이 PC 일 수 있다).
- 보안 강화는 대표님이 앞에 두지 않는다(혼자 쓰는 도구) — 다만 **로그인 없이 상태를 바꿀 수 있는 새 길**이 생기면 꼭 알린다.
- 돈 · 사용량이 드는 것(구독 · 크레딧 · AI 그림)은 쓰기 전에 묻는다.
- 윈도우에서 파일 고칠 때: 먼저 `encode('utf-8')` 해 보고 임시 파일 → `os.replace`. 원본을 `'w'` 로 먼저 열지 않는다(0바이트 사고). 실행은 `PYTHONIOENCODING=utf-8`.

---

# 📊 엑셀 방송(라이브 마스터) — 이 폴더

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
