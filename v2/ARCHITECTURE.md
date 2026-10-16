# 라이브 마스터 v2 — 처음부터 다시 만든 방송 프로그램

대표님 2026-10-07 "통째로 다시 만들어도 괜찮아 — 한번 다시 만들어봐".
**지금 방송은 옛 프로그램(저장소 루트의 server.py)으로 한다.** v2 는 이 폴더 안에서만 자라고,
기능이 다 옮겨지기 전까지 운영 서버에서 돌지 않는다(같은 저장소에 있지만 auto-deploy 는 v2 를 실행하지 않는다).

## 왜 다시 만드나 — 옛 구조에서 사고가 났던 자리

| 옛 방식 | 생긴 일 | v2 방식 |
|---|---|---|
| 상태 전체(큰 공책)를 저장하고, 바뀔 때마다 **통째로** 모든 화면에 보낸다 | 조종실이 통째 저장하며 서버 것을 덮어씀 → SERVER_OWNED · PATCH_DENY 같은 보호 목록이 계속 늘었다 | 조종실은 **명령(쪽지)** 만 보낸다("하율 +5"). 서버가 검사하고 **바뀐 조각(slice)만** 보낸다 |
| 연결 하나에 일꾼(스레드) 하나 — 개발용 서버 | 09-30 죽은 연결 161개 · 실 235개 → 점수가 안 들어감 | 비동기 서버(uvicorn) + WebSocket. 15초 숨쉬기 확인, 답 없으면 끊는다 |
| 전역 잠금(file_lock) 안에서 읽고 쓰기 | 잠금 안에서 느린 일을 하면 전부 멈춤 | 명령은 한 줄로 서서 하나씩(asyncio). 느린 일(시그니처 서버 조회)은 명령 밖에서 |
| 후원 기록이 공책 안에 섞여 있다 | 같은 후원 두 번 · 되살리기 판단이 어려움 | **장부 표**(donations, tx_id 유일) · 점수 기록 표(score_log) — 되돌리기가 기록에서 나온다 |
| 방송판 한 파일 1만 1천 줄 | 닫는 `</div>` 하나가 판 6개를 후원 팝업 위로 올림(10-06) | 위젯마다 파일 하나(web/overlay/widgets/*.js) · 층 순서는 **한 표**(layers.js) |
| "방송 중엔 올리지 말 것" 을 사람이 지킨다 | 방송 중 재배포 → 연결이 끊김 | 서버가 방송 중이면 `/api/deploy/ok` 가 409 — 자동 배포가 기다린다 |
| 운영 Postgres · 개발 SQLite 가 다르다 | 개발에선 되는데 운영에서 다름 | 어디서나 같은 SQLite(WAL) — 한 서버 · 한 프로세스라 충분하고 빠르다. 바깥 백업은 따로 |

## 그대로 가져가는 것
- 서버가 정하고 방송판은 그리기만 · 후원 받기는 따로(toon_listener.py, 대기줄) · 서울 서버
- **옛 주소 호환**: 리스너가 쓰는 `POST /api/donation` 은 같은 모양으로 받는다 → 리스너를 안 고쳐도 된다
- 방송판 모습(색 · 글꼴 · 테마)은 옛 것과 같게 — 대표님이 다듬어 온 디자인이다
- 글꼴 · 그림은 우리 서버에서(vendor/) — OBS 가 바깥에 기대지 않게

## 구조
```
v2/
  server/
    app.py        주소 · 로그인 · WebSocket · 배포 잠금 · 옛 주소 호환
    store.py      SQLite 장부(events · donations · score_log · kv) — 한 프로세스, 한 줄 쓰기
    state.py      상태 = 이름 붙은 조각(slice)들. 조각마다 공개/비공개
    commands.py   명령 → 검사 → 바뀐 조각. 순수 함수에 가깝게(검사하기 쉽게)
    hub.py        실시간 연결 — 구독 · 숨쉬기 · 공개 조각만 방송판으로
  web/
    shared/       client.js(연결 · 다시 붙기 · 번호 빠지면 통째 다시 받기)
    overlay/      index.html · layers.js(층 표) · widgets/*.js
    controller/   조종실
  tests/          python -m unittest discover v2/tests
```

### 조각(slice)
상태는 이름 붙은 조각들이다: `players` · `pending` · `queue` · `show` · `popup` · `goal` · `notice` · `account` · `settings` …
- 명령 하나가 조각 몇 개를 바꾸면 서버는 `{"t":"patch","seq":N,"slices":{"players":…}}` 로 **그 조각만** 보낸다.
- 화면은 seq 가 하나 건너뛰면(빠진 쪽지) 통째(`snapshot`)를 다시 달라고 한다.
- 조각마다 `public` 여부가 있다. 방송판(로그인 없음)은 공개 조각만 받는다 — 퀴즈 정답 같은 것은 비공개 조각에 둔다.

### 명령
`POST /api/cmd {"type":"score.add","player":"하율","delta":5}` 또는 WebSocket `{"t":"cmd",…}`.
명령은 한 줄로 서서 하나씩 처리한다 → 잠금 사고가 없다. 결과는 `{"ok":true,"seq":N}` 또는 `{"ok":false,"error":"…"}`.

## 단계 (진행 상황은 아래 표를 고친다)
| 단계 | 내용 | 상태 |
|---|---|---|
| 1 | 뼈대: 장부 · 조각 · 명령 · 실시간 연결 · 로그인 · 배포 잠금 · 검사 | ✅ 10-07 (test_core 7) |
| 2 | 핵심 흐름: 후원 받기(옛 주소 호환) → 대기함 → 선수에게 배정 → 점수판 · 되돌리기 · 방송 시작/끝 | ✅ 서버 10-07 (test_flow 16) |
| 3 | 방송판: 점수판 · 후원 팝업 · 공지 · 목표 게이지 · 계좌 (옛 모습 그대로) | ✅ 기본 · 테마 · 게임판(games_b: 주사위 · 시그뒤집기 · 대결 · 퇴근빵 · 지옥) / 진행: basics2(공지 · 계좌 · 시작/끝) · games_a(퀴즈 · 핀볼 · 룰렛 · 슬롯) |
| 4 | 조종실: 점수 · 대기함 · 되돌리기 · 방송 시작/끝 | ✅ 기본 · 도구(무대 · 공지 · 계좌 · 모금함 · 영상 · 후원 콘솔) · 기록(장부 · 후원자 · 점검/경보 · BGM) · 편집기 / 진행: 게임 탭 · 시그니처 관리 · 폰 |
| 5 | 시그니처: 매칭 · 재생 대기줄 · 방송판 재생 · 건너뛰기/멈춤 | ✅ 서버(reaction · 후원 콘솔) · 방송판 진행 |
| 6 | 게임 하나씩: 룰렛 · 슬롯 · 주사위 · 시그뒤집기 · 핀볼 · 퀴즈 · 대결 · 지옥/퇴근 | ✅ 서버: 퀴즈 · 핀볼 · 지옥/퇴근 / 진행: 대결 · 룰렛 · 슬롯 · 주사위 · 시그뒤집기 |
| 7 | 나머지: 테마 · 편집기 · 노래방 · 계좌 영상 · 진행봇 · 클립 · AI · 상태판 | ✅ 진행봇(서버 · 봇 · 조종실 탭) · AI 서버 · 버전 되돌리기 · 옛 설정 옮기기 탭 · 상태판 · 효과음 · 서버 시계 · 직접 준 VIP · 클립(머리줄 단추 포함) · 스트림덱 · 클릭 기록 · 월별 순위 · 시그니처 관리 · 폰 · 시스템 탭(투네이션 연결 · 최근 기록) · AI 조종실 화면(배정 제안 배지 · 오토파일럿 · 상황판 · 대화 · 알림) · 시그 집계 위젯 · 목표 달성 상자(goal.celebrate/dismiss · goal.done) / 진행: 시그니처 조명(네온 · 아우디 · 테마 입자) · 편집기 설정(시그 화면 · 표시 개수) · 순서표(세이브 슬롯) · 노래방 소리 · 효과음 스위치 |
| 8 | 옛 것과 나란히 시험 방송 → 갈아타기 | 준비물 ✅ v2/deploy/(서비스 · Caddy :8443 · 리스너 덧붙임 · 백업 타이머 · README) · v2/tools/import_old_db.py(옛 장부) · backup_db.py / 남음: 설치(허락) · 연습 방송 |

## 조각 · 명령 (2단계까지)
| 조각 | 공개 | 내용 |
|---|---|---|
| session | ✅ | live · id · started_at · ended_at |
| players | ✅ | list[{name, score, contribution}] · extra · extra_active · bottom{name, score} |
| goal | ✅ | target(점수, 0=없음) · offset — 게이지 = bottom.score + Σ list.score + offset |
| popup | ✅ | donation{id,name,amount,message,at(ms),display_only?} · score{name,diff,at} · takeover{name,at} |
| tallies | ✅ | donors{정규화이름:{name,total,count}} · best{name,amount,at,id,member} · notice_donors[{name,amount,ts}] · sigs{id:{title,image_url,amount,count,donors}} |
| queue | ✅ | items[{id,sig_id,title,sig_amount,audio_url,image_url,duration,amount,donator,message,count,play_all,skip_popup,play_after,replay?}] · paused · volume |
| show | ✅ | stage(무대 하나) · ret · hud{ranking,gauge,account,notice,donor_rank,sig_tally,best,fundjar} · alerts{popup,takeover,reaction_title,small} |
| notice | ✅ | msgs[] · period · speed · now{ts,idx,text?} |
| account | ✅ | bank · acc_num · name |
| look | ✅ | theme |
| pending | ❌ | [{id,name,orig_name,amount,message,at,kind?,contrib?,test?,returned?}] |
| logs | ❌ | [{at,name,val,before,after,cval,cbefore,cafter,ref,list,kind?,why?}] 최근 200 |

명령: session.start{names} · session.end · score.add{name,delta,contrib?,reason?,list?|target:'bottom'} · score.undo{ref?} ·
players.add/remove/rename/order · extra.start/end/cancel · goal.set{target?,offset?} ·
donation.add(옛 주소 /api/donation 이 부름) · pending.assign{id,name|names|items,list?} · pending.ignore{id} ·
reaction.done{id}(로그인 없이) · reaction.skip · reaction.stop · reaction.pause{paused?} · reaction.remove{id} · reaction.playall{id,on} · reaction.volume{volume} ·
signature.play(옛 주소 /api/signature/play) · show.stage{stage} · show.hud{key,on} · show.alert{key,on} · notice.add/edit/remove/move/every/now · account.set · look.theme

옛 주소: POST /api/donation(리스너) · POST /api/signature/play(후원 콘솔) · GET /api/signatures · GET /api/preflight[?deep=1]

실행: `.claude/launch.json` 의 **v2**(포트 5300, DB v2/data/dev.db). 검사: `python -m unittest discover -s v2/tests -t .`

## 3단계 이후 더한 조각 · 명령
| 조각 | 공개 | 내용 |
|---|---|---|
| quiz / quiz_ops | ✅ / ❌ | 네모칸 · revealed / 정답 · 순서 · 내 문제 |
| home / hell | ✅ | 퇴근빵 목표 · 알림 / 지옥탈출 목표 · 시작 점수 · 탈출 — 목표를 넘기면 **서버가** 대기함 카드 |
| fundjar | ✅ | name · enabled · seed(원) · score(원) |
| screen | ✅ | 시작 전 · 끝 화면(mode · title · start_at · names · snap) — 끝내는 순간 '오늘의 기록' 을 얼린다 |
| donor_rules | ❌ | 순위에서 뺀 이름 |
| acct_video / karaoke | ✅ | 금액대 영상 · 지금 트는 것 / 노래방 |
| pinball | ✅ | 명단 · 구슬 · 규칙 · 씨앗 · 판 번호 · 결과(방송판 첫 보고만) |
| sig_admin | ❌ | 시그니처 관리 변경 기록 ver · log(최근) — 지우기 전 줄 통째 · 고치기 전 값(되살리기 · 되돌리기 근거). ver 가 오르면 조종실이 시그 목록을 새로 받는다 |
| siggame_picks | ❌ | 시그뒤집기에 고른 시그 번호만(카드 속 · 자리는 숨김 조각 siggame_deck) |
| session_log | ❌ | 방송 시작 · 끝 기록(최근 200회) |
| clip / clip_log / clip_key | ✅ / ❌ / 숨김 | 클립 설정 · 지금 순간(ask) / 기록(60) · 파일 이름 규칙 / 회사 PC 도우미가 읽는 열쇠 |
| announce_bot / announce_status | ❌ | 진행봇 설정(옛 모양) / 봇이 붙으며 알린 모드(dry · live) |
| sigview | ✅ | 시그니처 카드 크기 · 줄어드는 시간 · 줄어든 자리 · 'OO업' 글자 크기 · 시간 · 붙는 말(옛 reaction_*) — `sigview.set` |
| presets | ❌ | 💾 세이브 슬롯 = 순서표 단계 list[{id, name, layout, hud, stage, saved_at}] — `preset.save/rename/move/delete/apply` · `show.cue{dir}` · 지금 몇 번째 = show.cue_at |
| autopilot | ❌ | 🤖 자동 진행(무인 방송) mode(off · shadow 기본 · on) · use_ai · games(금액 → 룰렛 · 슬롯 · 주사위) · stats{session, total} · log(60) — `auto.set` · `auto.games` · `auto.reset_stats`(서버가 스스로: auto.decide · auto.ai · auto.roulette(_stop) · auto.slot · auto.dice). 대기함 카드에 auto{…} 를 붙인다. 흐름 · 채점 규칙은 autopilot.py 맨 위 |
| lights | ✅ | 💡 조명 color('#rrggbb' · RAINBOW · OFF) · audi · speed(0.3~5초) · colors[9] · at — `lights.color{color}`(옛 단추 하나: AUDI 뒤집기 · OFF 둘 다) · `lights.set` · `lights.slot` · 스트림덱 /api/streamdeck/neon. 방송판은 방송 중 · 시그니처가 나오는 동안만 켠다(groups/fx.js · widgets/fx/) |
look 에 sig_tally_limit · donor_rank_limit(`look.limits`) · sfx(`look.sfx`, 없으면 켜짐)가, karaoke 에 volume(`karaoke.volume`, 기본 70)이 더해졌다(settings2.py).
look 에 fx(✨ 테마 연출 — `look.fx`, 없으면 켜짐 · 옛 theme_fx_enabled)가 더해졌다(lights.py).
tallies 에 vip(특별 후원자 등급) 이 더해졌다. popup 에 offwork · goal(축하) 신호가 더해졌다.
장부 보기: GET /api/ledger · /api/sessions · /api/scores — 방송을 끝내도 장부를 지우지 않는다(회차로 골라 본다).
session_log(비공개) 가 방송 시작 · 끝을 적는다 — 후원 · 점수가 하나도 없던 방송도 '지난 방송'에 나온다.
donor_rules.names 는 뺄 때 보이던 이름(키는 '님' 을 뗀 정규화 이름). score_log.list 는 list(본 명단) · extra · bottom · jar.
무인증 주소: /health(폰 상태판 — 이름 · 금액 · 메시지 없음) · /api/health · /api/time · /sfx/list · /sfx/<파일>(sounds/ 안의 소리만).
화면 이름표: WebSocket 이 User-Agent 로 기기를 적는다(obs · iphone …) — 점검표가 'OBS 에 붙은 방송판' 을 센다.

## 갈아타기 계획(8단계) — 대표님 허락을 받고 하나씩
> 명령 · 파일은 **v2/deploy/README.md** 가 원본(설치 · 주소 :8443 · 옛 장부 옮기기 · 연습 방송 · 갈아타는 날 · 되돌리기 · 백업 되살리기).
1. **나란히 띄우기**: 운영 서버에 v2 를 따로 띄운다(포트 5300, systemd `livemaster-v2`, 같은 /opt/livemaster 폴더 · 자기 DB `v2/data/lm2.db`).
   필요한 것: venv 에 `fastapi` · `uvicorn` 설치(**받기 허락 필요**). Caddy 에 v2 길(같은 주소의 다른 포트, 예: `:8443` → 127.0.0.1:5300) — DNS 를 안 건드린다.
2. **설정 옮기기**: 옛 조종실 [💾 백업] 파일 → v2 조종실 `admin.import_old`(공지 · 계좌 · 목표 · 테마 · 퇴근빵 목표 · 내 퀴즈 문제 · 고액 영상 · 모금함 · 룰렛 · 슬롯 · 주사위 판 · 스위치).
3. **연습 방송**: 방송 없는 날 v2 조종실 · 방송판(OBS 에 소스 하나 더)으로 한 바퀴. 후원은 v2 의 `/api/donation` 에 테스트로.
4. **리스너 두 갈래**(선택): 한동안 리스너가 옛 서버와 v2 둘 다에 보내게(DONATION_URL 둘) — 장부를 맞대 본다.
5. **갈아타기**: OBS 방송판 소스 주소 · 조종실 주소를 v2 로. 옛 것은 한동안 그대로 둔다(되돌리기용).
6. **배포 잠금**: auto-deploy 가 v2 `/api/deploy/ok` 를 보고 방송 중이면 기다린다(옛 서버에도 같은 걸 붙일 수 있다).

## 시그니처 관리(sigadmin) — 옛 /upload 화면
- 옛 주소 그대로: POST /api/signatures/add · /api/signatures/update/{id} · /api/signatures/delete/{id}(폼). 새 주소: GET /api/sigadmin/list · POST /api/sigadmin/restore {lid} · /api/sigadmin/revert {lid}.
- ⚠️ 지우기는 **줄만** 지운다(그림 · 소리 파일은 보관소에 남는다) — 지우기 전에 줄 통째를 sig_admin.log 에 적고, 못 적으면 안 지운다(10-07, 시그 id 105 를 통째로 잃은 일 때문).
- 고칠 때 새 파일은 새 이름(images/{id}_v{ms}.ext)으로 — 옛 파일을 덮지 않아 되돌릴 수 있다. 같은 금액은 409 dup → 한 번 묻고 allow_dup.
- 바뀌면 서버 매칭 목록(bus.sigs.refresh)과 조종실 목록(sig_admin.ver)을 바로 새로 받는다.
- 조종실 탭 💿 시그니처 관리 · 👀 방송 화면 보기, 방송 전에도 쓰는 단독 화면 /controller/sig.html(옛 /upload 는 여기로 넘긴다).

## 시험 서버 스위치
- `ANTHROPIC_API_KEY` — 있으면 AI 를 **Claude 먼저**(`CLAUDE_MODEL`, 기본 claude-haiku-4-5), 막히면 NVIDIA. 넣는 법은 deploy/README '🤖 AI 를 Claude 로'.
- `LM2_AI_OFF=1` — AI 열쇠(Claude · NVIDIA 둘 다)를 안 읽는다(서버 계산만). `LM2_NIM_URL` — 가짜 AI 주소. ⚠️ 저장소의 NVIDIA_CREDENTIALS.txt · SUPABASE_CREDENTIALS.txt 를
  저절로 읽으므로 그냥 띄운 시험 서버도 진짜 서비스를 부른다. `.claude/launch.json` 의 v2 는 LM2_AI_OFF=1 로 띄운다.
- Supabase 는 `SUPABASE_URL` · `SUPABASE_SECRET_KEY` 환경변수가 파일보다 먼저다(검사는 닫힌 포트로 돌려 막는다).
- `LM2_AUTOPILOT=off|shadow|on` — 🤖 자동 진행의 **처음** 모드(새 DB 일 때만, 기본 shadow). 검사 꾸러미(v2/tests/__init__.py)는 off 로 시작한다.
- 🧪 `python -m v2.tools.backtest_autopilot --db v2/data/lm2.db` — 지난 후원자 기억(donor_memory)을 시간 순으로 다시 돌려 '그때 기계였다면' 을 채점(읽기만 · AI 안 부름 · 이름 · 금액 안 찍음).

## 10-17 이사 1차 — sturdy
> 튼튼하게(재시작 · 중복 · 검사 울타리) · 실수 되살리기. 검사는 v2/tests/test_sturdy_*.py.

### ⏪ [방송 끝] 되살리기 (domain/endundo.py · controller/js/endundo.js)
- 옛 것: server.py end_broadcast 가 끝내기 직전 상태를 '방송 종료 자동 백업' 복구 지점으로 남기고 타임머신 [복구] 로 되돌렸다.
- `session.end` 가 바꾼 조각의 바로 전(pre) · 바로 뒤(post) 값을 장부 표 **restore_points** 에 같은 묶음으로 적는다(`bus.BEFORE_COMMIT` 훅, 최근 20개). popup · endundo 조각은 안 적는다.
- 명령 **`session.undo_end`**(로그인) — 마지막 지점으로 점수판 · 대기함 · 점수 기록 · 시그니처 대기줄 · 무대 · 게임판 · 집계를 되살린다.
  장부 표(donations · score_log)는 끝낼 때도 되살릴 때도 안 건드린다. 같은 회차 번호라 score.undo · 장부 보기가 이어진다.
- 끝낸 뒤 들어온 후원은 잃지 않는다(merge3 · merge_tallies — 대기함 · 대기줄 이어 붙이기, 순위 · 시그 집계는 늘어난 만큼 더하기, 한 방 최고는 큰 쪽, 등급 다시).
- 로그인 없는 화면(방송판 · HTTP · WS)은 401 — 검사 test_sturdy_endundo Review.
- 거절: 방송 중 409 · 끝낸 뒤 새 방송 시작 409 · 12시간(UNDO_MAX_SEC) 지나면 409 · 지점 없음/다 씀 404. 끝 화면은 내리고, 서는 중이던 룰렛/슬롯 · 까보기 · 판단 중 카드는 예약을 다시 건다.
- 조각 **endundo**(비공개) `{ready, at, until, sid, started_at, players, score_total, pending, queue, undone_at}` — 방송 전 화면 맨 위 [⏪ 방송 끝 되돌리기] 상자(확인 상자)가 본다.

### ⏰ 예약을 장부에 (bus.py · store.py)
- `ctx.later` 예약을 명령과 같은 묶음으로 장부 표 **timers**(id · due · type · data · made)에 적는다. 부른 명령과 같은 묶음에서 지운다(실패 · 넘어짐도 치운다).
- 서버가 켜질 때 app lifespan → `bus.arm_timers()` — 남은 시간대로 다시 걸고, 지난 것은 적힌 순서대로 바로 부른다.
- ⚠️ app.py 는 이제 `lifespan=_life` 를 쓴다 — FastAPI 는 lifespan 이 있으면 `@app.on_event('startup')` 을 **부르지 않는다**. 켜질 때 할 일을 더하려면 `_life` 안에 적을 것(검토 10-17).
- ⚠️ `ctx.later` 의 data 는 JSON 으로 적힐 수 있는 것만. `run_sync` 로 생긴 예약은 장부에만 적히고 다음에 켜질 때 걸린다.

### 🔁 명령 번호(cid) — 두 번 안 들어가게 (shared/client.js · bus.py)
- client.js 가 명령마다 번호(cid)를 붙인다(POST /api/cmd 의 `cid`, WS `{t:'cmd', cid}`). 답을 못 받은 명령을 1분 안에 **똑같이** 다시 누르면 같은 번호를 다시 쓴다.
- bus 는 같은 이름 · 같은 번호면 다시 하지 않고 첫 결과에 `dup: true` 를 붙여 돌려준다(메모리 2000개 + 장부 표 **cmd_ids** 하루치, 처리 중이면 기다렸다 같은 결과). 실패한 명령은 기억하지 않는다.
- 번호가 없으면(리스너 · 옛 화면 · 예약) 예전 그대로. 조종실은 dup 이면 '아까 누른 것이 이미 들어가 있었어요' 알림.

### 🧯 SQLite
- `busy_timeout` 5000ms(연결 timeout 도 같은 값) — 백업 · sqlite3 셸이 잠깐 잠금을 쥐어도 명령이 바로 실패하지 않는다.
- `synchronous=FULL`(전원 차단 대비, 명령마다 수 ms 더 듦). 환경변수 `LM2_SQLITE_SYNC=NORMAL` 로 되돌릴 수 있다 — store.py 주석.

### 🧪 검사 울타리 · 층 순서
- v2/tests/__init__.py 가 SUPABASE_URL · SUPABASE_SECRET_KEY · LM2_NIM_URL 을 닫힌 주소(127.0.0.1:9)로, NVIDIA_API_KEY 를 비운다 — 그냥 돌려도 바깥으로 안 나간다.
- test_ai NimPost.test_key_from_env_then_file 은 LM2_AI_OFF=1 에서도 통과한다(검사 안에서 끄기 스위치를 빼고 본다).
- test_sturdy_layers — 진짜 layers.js · groups/*.js 를 node 로 읽어 '후원 카드 · 시그니처 > 게임판' 등 층 규칙을 본다(10-06 사고 재발 방지). 새 칸 · 위젯을 넣으면 이 검사가 먼저 알려 준다.
## 10-17 이사 1차 — donate
> 옛 10-08 ~ 10-16 '후원 받기 · 장부 바로잡기' 를 v2 로 옮겼다(옛 동작이 정답). 검사: v2/tests/test_donate_mig.py(node 로 방송판 도구 · 층 표 포함).
- 🔁🧪 **다시 보기(replay) · 후원 테스트(test)는 화면에만**(옛 features/donation.py, 176db46): `/api/donation` 이 리스너 칸
  `title · level · vip · donor_key · replay · test` 를 버리지 않고 `donation.add` 로 넘긴다. 리스너(tx_id `toon_`)가 보낸 것만 믿는다.
  팝업 · 시그니처(시그 집계 안 셈 — count_tally False, 묶음에도 안 낌)만 내고 대기함 · 정산 장부 합계 · 후원 순위 · 한 방 최고 · 월별 순위 ·
  AI 기억 · 등급 · 자동 진행에는 안 넣는다. 장부엔 status `display`(합계 밖) 줄 하나 — source `toonation_replay` · `toonation_dashtest`.
  답은 옛 모양 `{status:'success', show_only:'replay'|'test'}`. ⚠️ 투네이션 신호엔 고유 번호가 없어 리스너가 tx_id 를 매번 새로 만든다 —
  tx_id 중복 거르기로는 못 막는다(검사가 실제 리스너 함수로 보여 준다).
- ⏸️ **VIP 등급 끔**: `domain/donors.py` 의 `VIP_ON = False` 한 줄(검사 서버만 `LM2_VIP_ON=1`). 꺼지면 tallies.vip 늘 빔 · `tallies.vip_on false`,
  모든 명령 뒤(bus.AFTER `_vip_guard`) 남은 등급도 비운다. `vip.set` 은 409. 방송판 등급 옷 · 1위 훈장 · 'OO 6위' 딱지, 조종실 등급(안내 문구), AI 사실표 VIP 모두 없음.
- 💬 **묶음(×N) 메시지**: queue 줄의 `msgs[]`(후원마다 차례대로, 빈 것도 자리, 30개까지). 방송판 시그니처 카드는 [N번 다 틀기]면 그 차례, 한 번이면 다 같이.
- 🏆 **빼기 · 다시 넣기로 다시 고른 한 방 최고**는 `best.at = 0`(갱신 아님 — 방송판 best.js 는 at 0 이면 '최고 기록 갱신!' 을 안 터뜨린다).
  다시 넣기는 그 사람 한 방이 지금 기록보다 클 때만 기록을 돌려준다.
- 🏷️ **칭호 · 레벨 · 투네이션 VIP · 번호표**: `domain/donor_extras.py`(clean → pub/priv). pub(`donor_title{name,color}` · `donor_level`)은
  대기함 · 팝업 · 시그니처 줄 · 소액 띠에, priv(`toon_vip` · `donor_key`)는 대기함(비공개)과 **표 `donor_keys`**(tx_id · donor_key · level · title · vip · at)에만.
  표는 이 모듈이 처음 쓸 때 만든다. `v2/tools/import_old_db.py` 가 옛 donor_keys 도 옮긴다(없으면 건너뜀).
  방송판 도구 `web/overlay/donate_kit.js` · `css/donate.css`(보석 알약 13단계 · Lv), 조종실 `js/donate_tags.js` · `css/donate.css`.
- 💙 **'투네' 딱지**: 리스너 후원 시그니처 줄에 `via:'toon'` → 시그니처 카드 사진 왼쪽 위(#519CFF, --r-s 8px).
- 🏺 **시그니처 중 모금함 숨김**: groups/basics2.js 층 fundjar 에 `hideInReaction`.
- 🔁 **끝난 묶음 이어 틀기**: 비공개 조각 `reaction_done_recent{items[]}`(다 틀었거나 건너뛴 ×N 줄 30개, 방송 시작 · 끝에 비움).
  `reaction.playall {id}` 가 이미 빠진 줄이면 남은 만큼을 지금 것 바로 다음에 세운다(`again_of · seq_base · seq_total · skip_popup`),
  답 `{again:true, count, seq_base, seq_total}`. 조종실 대기줄에 45초 동안 [남은 N번 이어 틀기].
## 10-17 이사 1차 — sigfx
> 방송판 시그니처 연출 · 따로 띄우는 화면. 옛 overlay.html · sig-fx.js · sig-fx-gl.js · alertbox.html · signature_display.html · slot.html 을 옮겼다(옛 동작이 정답).

**🎆 시그니처 전용 연출 18가지(옛 17선 + 09-23 진압해) · 🚨 25만 계엄령 경보**
- 연출 파일은 옛 것을 글자 하나 안 바꾸고 `web/overlay/sigfx/sig-fx.js` · `sig-fx-gl.js` 로(검사 test_sigfx 가 옛 파일과 같은지 본다 — 옛 것을 고치면 같이 고칠 것).
- 어떤 시그에 무엇: `widgets/sigfx/rules.js` — **시그니처 자신의 값(sig_amount)** 으로 고른다(후원 금액 아님). 10만 진압해 · 100,009 가즈아 · 13만 람바다 · 15만 부티호텔 · 16만 크레이지 러브 · 18만 바운스 · 20만 마티니 · 200,001 뽀카치포 · 30만 푸차 · 35만 EDM · 50만 출항 · 500,001 방패 · 600,001 참격 · 70만 누나누나 · 80만 클럽 · 100만 VIP · 200만 엔젤 VIP · 300만 MVP.
- 가운데 갈래(옛 순서): 계엄령(sig_amount 250000, 없으면 제목 '계엄령') → 붉은 경보 4초 '주의 계엄령 발동' · 전용 연출이 있으면 그 연출(‘OO업’ 없음) · 못 띄우면 'OO업'.
  연출이 카드 등장을 맡는 동안은 카드 축소를 연출이 끝난 뒤(+0.12초)로 미룬다(rules.shrinkWait). 시그니처를 끊으면 연출 · 경보도 걷는다(조종실 이펙트는 안 건드림).
- 🎲 주사위 시그 배너는 '누구 · 시그 칸 도착'(서버 banner, 금액 · '업' 없음 — 옛 reactionUpText).
- 층(groups/sigfx.js): 시그니처 50 < 전용 연출 `sigfx` 55 < 경보 `sigWarn` 58 < 경고 띠 `sigUnlock` 60. **56 · 57 은 비워 둠** — 옛 후원 콘솔 '이펙트'(번쩍 · 충격파 · 글리치 · 전체 카드)를 옮길 때.
- 무대 약속: `stage.provide('sigfx', {play(item,{card}) → ms, stop})` · `stage.provide('sigWarn', {fire({message}), clear})` · `stage.provide('autoplayWarn', {show, hide})`.
  점검: 콘솔 `__lmSigfx.test(300000)` · `__lmSigfx.test('mvp')` — 카드 없이 연출만.

**🔥 미리받기** — 방송판이 켜질 때 `GET /api/sigfx/sigs`(**로그인 없이** · id · image_url · sound_url · duration 만 — 이름 · 금액은 빼고 순서는 섞는다(옛 _PUBLIC_SIG_FIELDS · 시그 뒤집기 카드 가리기) · 못 읽으면 빈 목록 · no-store)로 사진(crossOrigin, 받는 김에 대표색) · 소리(하나씩, force-cache)를 받는다. 경광봉 사진(/vendor/sigfx/baton.webp)도. ?monitor=1 은 소리를 안 받는다(폰 데이터).
  조종실의 `/api/signatures` 는 그대로 로그인 전용.

**🔊 자동재생 차단** — 막히면 음소거로라도 끝까지(사진 · 길이 · 차례 그대로) · 방송판을 한 번 누르면(클릭 · 키 · 터치) 소리를 살린다(음소거 재생 중이면 그 자리부터, 그마저 막혀 멈췄으면 처음부터). AbortError 는 한 번만 다시.
  빨간 경고 띠는 **알림창 화면(?only=alert)에만** — 방송판에는 옛 것처럼 안 띄운다(대표님 08-13 요청, 커밋 e4303aa).

**📺 따로 띄우는 화면** — 같은 방송판에서 일부 칸만(`VIEWS` in groups/sigfx.js, layers.js 가 내보냄). `viewOnly` 칸은 그 화면에만(편집기 목록에도 없다).
| 주소 | 옛 주소(서버가 302 로 넘김, 뒤 ?… 그대로) | 칸 | 연결 이름표 |
|---|---|---|---|
| `/overlay/?only=alert` | /alertbox · /alertbox.html | 후원 카드 · 소액 띠 · 시그니처(소리 · done 포함, 클립은 안 맡음) · 전용 연출 · 경보 · 경고 띠 | alertbox |
| `/overlay/?only=sig` | /signature-display · /signature-display.html · /signature_display.html | 출연진 전광판 카드(sigdisp.js) — 소리 · done 없음 · 줄지 않음 · 창 크기 그대로(native) · 어두운 바탕(`&transparent=1` 투명) | sigdisp |
| `/overlay/?only=slot` | /slot · /slot.html | 슬롯머신만(방송판과 같은 자리 · 소리는 방송판 시그니처 대기줄이) | slot |

hub `KINDS` 에 alertbox · sigdisp · slot — 점검표(/api/preflight)는 이것들을 '방송판' 으로 세지 않는다(total 에만).

검사: `v2/tests/test_sigfx.py`(14) · `v2/tests/js/sigfx_check.mjs`(node — 규칙 · 표 · 층 순서 · VIEWS).
## 10-17 이사 1차 — games
옛 프로그램(10-08 ~ 10-16)에만 있던 게임 · 위젯 자리 · 조종 연출을 옮겼다. 옛 동작이 정답이다.
- 🎱 핀볼(domain/pinball.py · widgets/games/pinball.js) — 시간(3분) · 걸음 수로 판을 **자르지 않는다**(옛 992bf7c, 10-08 52판 사고).
  끝나는 길은 승부 갈림과 정체 감시(20초, 물리 걸음으로 센다) 둘뿐. pinball 조각에 `cut`('' | 'stall') — 정체로 끊으면 우승 딱지 아랫줄
  '⏱ 구슬이 껴서 지금 자리로 결정' · 조종실 핀볼 탭 한 줄. 새 판 · 명단 · 초기화 · 방송 시작/끝 때 지운다.
- 📐 옛 위젯 자리 옮기기(domain/oldlayout.py) — `layout.import_old {layout, sizes?}`. 옛 좌표(왼쪽 위 기준) → v2 기준점(layers.js anchor):
  tl 그대로 · tr x = 옛 x + 폭×배율 · tc x = 옛 x + 폭×배율÷2 · y 그대로(폭 표는 oldlayout.py 맨 위 — v2 방송판을 잰 값).
  옛 규칙 그대로: `__v` 2 미만 무시 · `__free` 가 아니면 안전지대 · 전광판 안 옮김. `admin.import_old` 도 상태에 배치가 있으면 같이 옮기고,
  옛 세이브 슬롯의 자리도 바꿔 담는다. 조종실 [옛 설정 옮기기] 가 layout.json 도 받는다 · 편집기 [📥 옛 배치 가져오기](계좌 폭을 재서 보낸다).
- 🏺 `fundjar.side {side:'left'|'right'}` — 옛 /api/fundjar/side 셈 그대로(왼쪽이면 점수판이 비킨다). 모금함 탭 [◀ 왼쪽][오른쪽 ▶](panels/ops/fjside.js).
- 💬 cast 조각(✅ 공개, domain/cast.py) — 방송판에 '한 번 쏘는' 신호. 칸마다 쏠 때마다 id 가 오른다.
  | 칸 | 명령 | 방송판(groups/cast.js · widgets/cast/) |
  |---|---|---|
  | say {id, text, at} | `cast.say {text}` 60자 | castSay z55 — 가운데 궁서 · 흰 글씨 · 검은 테두리 1초(옛 /api/say) |
  | up {id, text, at} | `cast.up {text}` 60자 | castUp z34 liveOnly — 위 40% 금색 110px 2초(옛 gd.up_trigger) |
  | fx {id, kinds, name, amount, message, at} | `cast.fx` | castFx z60 — banner · flash · ticker · card · shock · glitch · warn(옛 /api/effect/fire, opFxFire) |
  | fx_clear {id, at} | `cast.fx_clear` | 쏜 연출을 바로 걷는다(옛 /api/effect/clear) |
  방송판은 새로 쏜 것만 그린다(widgets/cast/fresh.js — 다시 붙은 창은 3초 넘은 신호를 안 터뜨린다). 흔들림은 무대 모드 `opfx-shake`,
  다른 위젯이 쓸 수 있게 무대에 `opfx` {fire, clear, clearWarn} 를 내놓는다. 점수 · 장부 · 시그니처 대기줄은 안 건드린다.
  조종실: 오른쪽 칸 맨 위 두 줄(js/castbox.js — 💬 Enter · ⬆ Enter/[발사]) · 운영 탭 ✨ 이펙트(panels/ops/opfx.js).
- 🎲 주사위 시그 칸 — 시그니처 'OO업' 자리에 서버가 실은 banner('밍밍 · 시그 칸 도착')를 띄운다(widgets/signature.js, 옛 reactionUpText).
- 검사: test_pinball_cut · test_oldlayout · test_cast · test_games_js_syntax(v2/web 모든 .js 를 .mjs 로 node --check — 조종실이 통째로 안 뜨는 문법 오류를 막는다) · import 이름 잇기 검사 — 없는 이름 · 없는 파일을 부르면 걸린다).
## 10-17 이사 1차 — bank
🏦 계좌 입금 추천(옛 features/bank_inbox.py · bank_memo.py · manual_send '계좌 입금 추천' 칸 · controller 계좌 띠 · 거울)을 옮겼다. 서버 v2/server/domain/bank.py · bank_memo.py.
⚠️ **자동 송출은 없다** — 카드 → 대표님 [채우기] → 고쳐서 [송출](지금과 같은 /api/donation). 배정도 대기함에서, 카드엔 '누구 ＋? 예상' 만.

| 조각 | 공개 | 내용 |
|---|---|---|
| bank | ❌ | {ver, new, hidden, newest} — 이름 · 금액 없음. ver 가 오르면 조종실이 /api/bank/inbox · /api/bank/ext 를 다시 읽는다. 방송판엔 안 간다 |

명령: bank.sync(내용 없음 — '바뀌었다' 만 기록. 입금 카드 · 실명은 events 에 안 남긴다).
표(같은 SQLite 장부 파일): bank_inbox(입금 카드 · 실명 holder · 메모 원문, 36시간 · 300건) · bank_meta(확장 · 폰 마지막 신호 상자 · 기다리는 명령).

주소 — **옛 것과 같은 주소 · 같은 모양 · 같은 답**(은행 확장 bank-watch · 폰 앱 bank-phone 은 안 고친다. 갈아타는 날 Caddy 가 /api/bank/* · /download/bankphone.apk 를 v2 로):
- POST /api/bank/deposit (로그인 없음 · X-Bank-Key) → {status, added, cmds} · 1분 60번 넘으면 429 · 빈 목록 = 살아 있음 신호
- GET /api/bank/inbox · POST /api/bank/inbox/{id}/{used|dismiss|restore} · GET /api/bank/key · POST /api/bank/key/reset (로그인)
- GET /api/bank/ext · POST /api/bank/ext/cmd {t: enable(on) · interval(sec 20/30/60) · rebase · press} (로그인)
- GET /download/bankphone.apk (로그인 없음) · GET /api/bank/app (로그인 — 판 번호 · 크기)

열쇠: 옛 서버와 **같은 파일** 저장소 루트 bank_key.json(git 제외 · 권한 600)을 같이 쓴다 → 확장 · 폰 다시 설정 없음.
`LM2_BANK_KEY` 가 있으면 그것이 먼저(그땐 새 열쇠 못 만듦) · `LM2_BANK_KEY_FILE` 로 자리 바꿈 · 시험판(LM2_TRIAL=1)은 새 열쇠 잠금. 응답 · 기록엔 끝 네 글자만.
메모 나누기: bank_memo.py(옛 것 그대로 — 예전 닉네임 · 첫 낱말 · 선수 이름 앞(player_cut) · 이름만 · 메모 없음), 애매하면 ai.ai_post, '＋?' 는 ai.suggest — 답을 보낸 뒤에.

조종실: 후원 콘솔 맨 위 '계좌 입금 추천'(panels/ops/bank.js — 채우기 · 숨기기 · 되살리기 · 열쇠 보기/복사/새 열쇠 · 탭 배지 `badge`),
채운 송출은 tx_id `manual_bank_<입금번호>` · 이름 비우면 '익명' · [채우기] 뒤 '장부에 넣기' 를 채우기 전으로(옛 50878d1).
머리줄 '계좌' 점 · 계좌 띠(끊김 빨강 / 새 입금 초록 25초, **소리 없음**) — bankext.js(alarm.js 점 묶음 옆). 시스템 탭 거울 · 폰 앱 QR — panels/ops/bankmirror.js.
계산은 bankcore.js(화면 안 만짐 → node 검사). tabs.js 에 탭 배지(`badge(slices) → 글자`)를 더했다. 검사: test_bank · test_bank_js.
백업: v2/tools/backup_db.py 는 백업본에서 bank_inbox · bank_meta 를 비운다(scrub_private · secure_delete + VACUUM) — 옛 프로그램은 실명 든 bank_inbox.json 을 36시간만 두고 백업하지 않았다. 되살린 뒤엔 확장 · 폰이 다음 신호부터 다시 채운다.
## 10-17 이사 2차 — w2frame
조종실을 시안 B(두 줄 머리 · 왼쪽 아이콘 줄 · 세 칸)의 **틀(묶음 A)** 로 바꿨다. 설계서 scratchpad/b_v2_spec.md · 칸 id 는 그 2-1 약속 그대로. 서버 · 명령 · 단추 id 는 안 바꿨다.
- 머리 두 줄(js/header.js) — 상태 줄 `.sb`(보기만: 연결 · [방송 화면] [후원 받기] [계좌] 점 · 자동 진행 · 경보 띠 `#sb-band` · 방송 중 N분 · 시계 · [방송 끝] `.end-btn`)
  + 조종 줄 `.cb`(누르기만: `#ctl-bgm` · `#ctl-sig`(`#ctl-rx`) · `#ctl-misc` 클립 · 에디터 새 창). 폰은 [더보기] → 아래 판 `#ctl-more`(BGM '이 기기에서 소리' · 클립 · 에디터 · 방송 끝 · 로그아웃, 노드를 옮긴다).
  💰 이번 방송 후원 알약은 뺐다(숫자 카드 ① 로 — [B]). 로그인 전엔 연결 점만.
- 경보 띠(js/alarm.js) — PC 는 상태 줄 **안** 한 줄(아래 화면이 안 밀린다 · 재 봄: #center top 114 → 114), 폰은 상태 점 밑 30px(탭 줄 88 → 118).
  여러 건이면 첫 건 + '외 N건' · [자세히] = 뜬 판. 다른 파일은 `bandAdd(key, {level:'bad'|'warn'|'ok', title, sub, ttl, act, close})` · `bandRemove(key)` 로 얹는다
  (🏦 bankext.js 의 끊김 빨강 · 새 입금 초록 25초가 여기로 — 따로 띠 없음). ⚠️ 소리 · 진동 · 알림 권한 0줄(test_controller_frame 이 지킨다).
- 세 칸 `#v-shell`(옛 이름 v-live 같이) = `#rail` 왼쪽 줄(class tabbar · data-old="tabs") · `#center` · `#side` · `#drawer`(폰 서랍 자리, [C]). 방송 전에도 세 칸이 보인다 —
  가운데 '랭킹' 자리에 `#v-setup`(방송 준비), 오른쪽에 점검표. 폭: ≥1280 76 · 1fr · clamp(380,28.5vw,460) / 900~1279 64 · 1fr · 340 / 폰 한 줄(탭 줄이 머리 밑에 붙음).
- 탭(js/tabs.js) — 탭 설명에 `rail`(왼쪽 줄) · `pre`(방송 전에도 열림, 아니면 흐리게 + '방송을 시작하면 열려요') · `short`(줄 글자) · `home`(첫 화면).
  줄 순서는 `RAIL_ORDER` 한 곳: 랭킹 · BGM · 대결 · 룰렛 · 슬롯 · 주사위 · 시그뒤집기 · 퀴즈 │ 지옥·퇴근 · 핀볼 · 로그 · 후원콘솔 · 전광판 … 설정 · 백업.
  줄에 없는 탭은 숨은 단추(.tab-off)로 남겨 `.tabbar .tab[data-tab=…]` 를 눌러 여는 옛 길이 그대로 돈다. 페이지를 열면 늘 첫 화면, `lm2_tab` 은 설정 '최근' 딱지에만.
- 틀 탭(panels/frame.js) — 랭킹(home) · 로그(section#logs 를 옮김) · 전광판(/overlay/?only=sig 열기 · 주소 복사 — 대표님 '씀') · 백업(endundo.js 방송 끝 되돌리기).
  ⚙ 설정(panels/settings_menu.js) — 줄에 없는 탭을 묶음 타일로(방송 화면 · 시그니처·연출(이펙트 포함) · 기록 · AI·자동 · 시스템(은행 확장 거울 포함)), 안 적은 새 탭은 '그 밖' 에 저절로.
  타일 = button.tab[data-tab] → 클릭 기록 key 가 `tab:<id>` 그대로. 맨 아래 [로그아웃] = 있는 POST /logout 만.
- 1차 기능 새 자리: 화면에 한마디 · UP = `#say-slot`(castbox.js) · 계좌 점 = 상태 줄 점 묶음 · 계좌 띠 = 경보 띠 · 은행 거울 = 설정 타일 · 방송 끝 되살리기 = 왼쪽 줄 백업(+[방송 끝] 확인 글).
  계좌·화면 탭 '시작 화면 출연자' 는 방송 전엔 방송 준비 칸 이름(없으면 lm2_last_names).
- 단추 이름표: 아이콘 단추에 글자(더보기 · 에디터 · 로그아웃 · 닫기), 빈 UP 칸의 [발사] · 빈 대기줄의 [멈춤] 은 흐리게.
- 다음 작업자 자리: main.js 의 `// [B]` `// [C]` `// [D]` 주석 줄(import · views · LIVE 목록 · safe 호출)을 자기 줄만 푼다. css/home.css([B]) · css/side.css([C]) 는 빈 파일로 걸어 뒀다.
- 확인(10-17): 헤드리스 크롬 1440×900 · 945×900 · 390×844 × (로그인 · 방송 전 · 방송 중) 가로 넘침 0 · 탭 36개 전부 열어 세 폭 넘침 0 · 콘솔 오류 0(favicon 404 빼고) ·
  로그인 화면에 ₩ 없음 · 방송 전 공지 · 시작 화면 · 진행봇 명령 들어감 · 대결은 잠김 · 클릭 기록 구역 tabbar / top. 검사 v2/tests/test_controller_frame.py.
- 검토(10-17): 단추를 헤드리스로 **진짜 눌러** 서버 조각이 바뀌는 것까지 봤다 — 로그인 [들어가기] · 방송 전 공지 [＋ 공지 추가] · 진행봇 [저장] · 시작 화면 [🎬 시작 전 화면](준비 칸 이름) · [방송 시작] ·
  💬 한마디 Enter · ⬆ [발사] · 상태 점 · [BGM 고르기] · [✂ 클립] · 로그 탭 · 띠 [자세히]/단추/닫기 · 설정 → 은행 확장 타일 · 전광판 주소 · [방송 끝] → 백업 [되돌리기] · 폰 [더보기] → [방송 끝](취소) · [로그아웃].
  같은 후원 카드는 세 폭 · 폭 오가기 뒤에도 한 장씩(머리 단추 노드도 하나씩). 고친 것: PC · 반 화면에서 '서버와 연결이 끊겼어요' 띠 첫 글자가 왼쪽 줄 밑에 가리던 것 → 띠가 왼쪽 줄 자리를 비켜 선다.
  ⚠️ 남은 것(묶음 C 몫): 대기함 위 '🤖 ○○님 · 금액 / ○○에게 N점 줄까요? [지급]' 줄과 아래 카드가 같은 후원을 두 번 보여 준다 — 설계서 2-4 대로 C 가 mountAsks 를 뺀다.
## 10-17 이사 2차 — w2center
조종실 시안 B **가운데 첫 화면(묶음 B)** — 랭킹 탭. 틀(칸 id)은 w2frame 그대로, 단추 class · 명령 이름은 안 바꿨다.
- 🎬 무대 줄(js/stagebar.js · #stagebar) — **탭을 바꿔도 남는다**(가운데 칸 맨 위, PC 붙어 있음 · 폰은 판이 진행 중일 때만 붙음).
  무대 이름(show.stage) · '덮기: 시그 리액션'(대기줄이 돌 때) · 진행 중인 판: 대결 ⚔ 시계 [▶ 시작/⏸ 멈춤](match.start · match.pause) [+1분](match.add_time {sec:60})
  (시계는 서버 시각 · 돌 때만 0.25초 setInterval) · 시그뒤집기 [올클리어] · 주사위 [🎲 굴리기](각 탭과 같은 확인 상자) ·
  순서표 지금 단계 · [◀][다음 · 이름](show.cue) · [+ 단계](preset.save {name:''}) · [편집](무대 탭).
- 🔢 숫자 카드 4장(js/kpis.js · #kpis) — **랭킹 탭에서만**(대표님 10-17). ① 이번 방송 후원 = /api/ai/board?today=1 의 today
  (+ 서버 `ai_facts.today_summary` 에 `가장_큰 {이름, 금액}|None` — 같은 금액이면 먼저 온 것) · ② 1등 = players.list[0] · 아랫줄 '2등 이름 N점'(차이를 빼지 않는다) ·
  ③ 대기함 후원 카드 건수 · 합 · 제일 먼저 · ④ 목표 − gaugeValue. 머리줄 💰 알약은 없어졌고 panels/ai/today.js 는 받기만(`startToday`).
- 💱 정산 차액(대표님 10-17 · 카드 밑 한 줄 `#settle`) — **서버가 센다** GET `/api/ledger/settle`(로그인 · ledger.py `settle()`):
  실제 받은 돈 = 이번 방송 장부 COUNTED(화면에만 · 🔁 다시 보기 · 🧪 대시보드 테스트는 이미 'display') − 🧪 투네이션 테스트(source toonation_test)
  · 점수로 들어간 돈 = 배정한 후원마다 man_won((금액+4000)//10000) × 1만 · 차액 = 실제 − 점수.
  [까닭] = cut(자투리 버림 +) · up(6천 원부터 올림 −) · pending(대기함 +) · ignored(무시 +) · test(테스트를 준 것 −) · archived(옛 장부 +) — **합 = 차액**(test_settle 이 지킨다).
  참고 `hand` = 점수 기록(score_log, 되돌린 것 빼고)이 만 원 규칙과 다른 배정(나눠 줄 때 손으로 바꾼 것) — 차액 셈엔 안 넣는다.
  조종실은 15초마다 + 대기함 · 점수가 바뀌면 1.2초 모아 다시 받는다. 화면 · 방송판 · /health 엔 안 나간다.
- 🏆 점수판(js/scores.js) B 격자 40 · 이름(+기여도 막대) · 84 · 84 · 210 · 44(반 화면 34·1fr·52·52·96·28 · 폰 24·1fr·36·36·84·28) ·
  **기여도 숫자 = 옛 [기여도] 단추**(class cfix-btn 그대로) · 줄 끝 🗑 → 확인 상자 → players.remove · 머리 [명단] [＋ 선수] · 번외 판 단추(xs).
  운영비 줄 · 🏺 모금함 줄(새): 스위치(setJar) · 깃발 [◀ 왼쪽][오른쪽 ▶](`#jar-side-slot` — fjside.js `mountFjSide(ctx, {compact:true})`) · 금액(종잣돈+후원) · [+ 금액](fundjar.add reason '점수판').
  줄 바탕을 카드 끝까지 칠할 때 바깥 여백(음수 margin)을 쓰면 가로 넘침이 된다 → 그림자(--bleed)로 칠한다.
- ⚙ 기본 설정(details#basic, 접힘) — 명단 고치기(scores.js 가 옮김) · 목표 · **게이지 보정 칸**(goal.set {offset}) · [무대 탭에서 켜고 끄기 →](스위치를 두 곳에 안 만든다).
  goal.js `openBasic(sel, openSel)` 를 카드 ④ [정하기] · 점수판 [명단] [＋ 선수] 가 같이 쓴다. 🏆 달성 상자는 `#goal-win-slot` 으로 옮겨 어느 탭에서든 보인다.
- 아이콘은 js/homeicons.js(`hicon` — 없는 이름은 icons.js 것). 같은 SHAPES 표를 여러 갈래가 고치면 합칠 때 부딪혀서 따로 뒀다.
- ⚠️ 전역 `.empty`(가운데 정렬 + 위아래 18px) 이름을 다른 뜻으로 쓰지 말 것 — 무대 줄이 70px 로 커졌었다(지금은 `.none`).
- 확인(10-17): 헤드리스 크롬 1440×900 · 945×900 · 390×844 × (로그인 · 방송 전 · 방송 중) 가로 넘침 0 · 탭 36개 세 폭 넘침 0 · 콘솔 오류 0(favicon 404 빼고) ·
  로그인 화면에 ₩ · 원 · 숫자 카드 없음. 카드 ①~④ · 정산 = 서버 값과 같음(선수 6 · 후원 4 · 목표 100). 진짜 눌러 봄: 대결 ▶(시계 03:00→02:58) · ⏸(running false) ·
  +1분(+60000ms) · 룰렛 탭에서도 무대 줄 · 시계 남음 · [+ 단계] 둘 · [다음] cue_at 0→1 · [편집] → 무대 탭 · 기여도 숫자 → 기여도만 5→9 · 🗑 → 확인 → 빠짐 ·
  커서 중 줄 순서 그대로 · 보정 5 → 카드 ④ 62→57 · 모금함 켜기(enabled · hud 둘 다) · +15,000 · 배정 2 · 무시 1 → 정산 까닭 +100,009 / +20,000 / −100 ·
  목표를 넘기면 슬롯 탭에서도 달성 상자. 검사 v2/tests/test_settle.py · test_controller_home.py · test_ai(가장_큰).
- 검토(10-17 · 같은 가지): ① 숫자 카드 ① '이번 방송 후원' 이 🧪 투네이션 테스트(toon_t2_)까지 세서 💱 '실제 받은 돈' 과 달랐다(테스트 50만 원이면 ① 만 50만 원 큼 · '가장 큰 후원' 도 테스트가 될 수 있었다)
  → `ai_facts.today_summary` 가 source 'toonation_test' 를 빼고 센다(AI 채팅 '이번 방송 후원' 도 같은 셈). test_settle 이 ① 합계 · 건수 = 정산 real · real_n 을 지킨다.
  ② 방송 시작 직후 show.cue_at 은 **null** 로 온다 — `Number(null)` = 0 이라 무대 줄 · 무대 탭 순서표가 '1. ○○' 를 지금 단계로 보이고 [다음] 이름이 2단계를 가리켰다(서버는 -1 로 셈해 1단계로 감)
  → stagebar.js · ops/cues.js 가 null 을 -1 로(서버 settings2.cue_at 과 같은 셈). 헤드리스로 '순서표 2단계 · 시작 전 / 다음 · 슬롯 1' 확인.
  다시 잰 것: 세 폭 × 로그인 · 방송 전 · 방송 중 가로 넘침 0 · 탭 36개 넘침 0 · 같은 tx 두 번 + 테스트 한 건 → 대기함 카드 후원마다 한 장(세 폭) · 단추 진짜 누름(대결 ▶ ⏸ +1분 · 다음 · 단계 · 편집 · 기여도 · 🗑 · 보정 · 모금함) 모두 서버 상태가 바뀜.
