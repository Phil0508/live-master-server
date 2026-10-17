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
## 10-17 이사 1차 — ops
> 운영 서버에는 아무것도 안 했다 — 파일 · 글 · 검사만. 적용 순서는 **v2/deploy/README.md '5. 갈아타는 날'**(점검표 ⓪~⑨ · 되돌리는 길).
- **공개 주소(로그인 없음 · 조각/명령 없음 — 읽기만)** `domain/ops_public.py`: `GET /api/signatures/board`(크루 사이트 시그리스트 — 옛 3715894 · 3477d81 과 같은 칸,
  번호 없음, 시그 목록은 bus.sigs) · `GET /api/oraksil/donors`(엔젤오락실 순위 — 옛 6076216, monthly.bc_day · rules.norm_donor 재사용,
  익명 · 뺀 이름 · 테스트 계정 · 화면에만 제외) · `GET /privacy` · `GET /terms`(옛 legal.py 글 그대로). 1분 기억(bus.ops_public_cache). 검사 test_ops_public.
- **자동 배포** `deploy/auto-deploy.sh`(옛 서버 파일): livemaster-v2 가 enabled 일 때만 — 새 커밋 + `GET /api/deploy/ok` 409 면 기다림 ·
  v2/requirements.txt 바뀌면 pip · v2 · v2 진행봇 try-restart(돌 때만). 없으면 옛 동작 그대로(검사 test_ops_autodeploy 가 옛 판과 나란히).
- **리스너** `deploy/toon-listener.service`(v2 판, 통째로 바꿈): 옛 서버 Requires/After 없음 · v2 에 Wants= 만 · DONATION_URL 5300.
  덧붙임(.service.d)으로는 의존을 비울 수 없어 10-07 v2.conf 는 지웠다. 버전 되돌리기(versions.py)는 v2 자신을 맨 끝에 다시 켠다. 검사 test_ops_units.
- **Caddy 큰 주소 갈아타기** `deploy/Caddyfile.switch` · `Caddyfile.unswitch` · `caddy_switch.py status|apply|revert`: 큰 주소 덩어리 하나만 바꾼 새 파일을 쓴다
  (홈페이지 · crew · :8443 은 그대로 — 전후를 맞대 봄). 기계 주소(/api/bank/* · bankphone.apk · 시그리스트 · 오락실 · privacy · terms · /api/streamdeck/* · /api/donation)
  → 5300, 옛 운영자 화면 → :8443 같은 화면 302, OBS 소스 · 나머지 → 8080. 검사 test_ops_caddy.
- **장부 바깥 백업** `tools/backup_db.py --upload` / env `LM2_BACKUP_UPLOAD=1`(기본 0): 비공개 backups 버킷이 아니면 안 올린다. 검사 test_ops_backup_upload.
- **서버 처음 세우기** `deploy/setup.sh --with-v2`(또는 WITH_V2=1): v2 서비스 · 백업 · 감시 · 진행봇 v2(깔기만) · Caddy :8443 · 방화벽 8443 ·
  `/etc/sudoers.d/livemaster-v2-restart`(visudo 확인 뒤). 안 붙이면 옛 판과 같다(검사 test_ops_setup 이 나란히).
- 점검표 자체도 검사(test_ops_readme — 단계 순서 · 단계마다 명령 · root validate 금지 · 가리키는 파일이 있는지).
- 남은 것: 알림창 · 전광판 · 슬롯은 v2 에 같은 화면이 생기면 Caddyfile.switch 의 주석을 푼다. 은행 입구(/api/bank/*)는 은행 갈래가 v2 에 들어온 뒤에야 답한다.
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
## 10-17 이사 2차 — w2races
🏃 퇴근빵 · 🔥 지옥탈출을 **무대(show.stage)에서 뺐다** — 이제 늘 붙는 칸이다. 대표님 말 '다른 게임을 켜면 꺼진다'의 원인은 무대가 한 번에 하나라서였다
(대결 · 주사위 · 시그뒤집기 · 핀볼 · 퀴즈가 무대를 가져가면 끝나도 안 돌아왔다). 진행(기록 · 셈 · 카드)은 원래 이어졌고, 보이기만 무대에 묶여 있었다.

| 조각 | 칸 | 뜻 |
|---|---|---|
| home | on | 퇴근빵 진행 + 방송판에 보임. 무대를 안 건드린다. **방송 시작 · 끝에 꺼진다**(목표 goals 는 남김 — 옛 2fa794e) |
| hell | on · **shown** | on = 세는 중, shown = 방송판에 보임. `hell.start` 가 둘 다 켠다(무대 안 건드림) |

명령(새것): `hell.show {on}` 방송판에서 내리기 / 다시 띄우기(셈 · 카드는 계속) · `hell.resume` 끝낸 판을 같은 기준점으로 이어서.
`hell.off` 는 '끝내기'(on · shown 끔, 기록은 남김). 이름 그대로: home.on · home.goal · hell.start · hell.goal · offwork.send.

**옛 무대 이름 바꿔 받기**(show.py `RACE_STAGES` · `RACE_ON` — races.py 가 채운다):
- `show.stage {stage:'hell'}` → hell 보이기(끝낸 판이면 이어서 — 옛 /api/show 와 같다, 시작 전이면 409 '먼저 시작'). `'home_race'` → home.on. **무대는 그대로**(대결이 안 내려간다). 답에 `race`.
- `set_stage(ctx, 'hell' | 'home_race')` 를 누가 불러도 같은 바꿔 받기.
- 순서표 단계(settings2 `apply_cue`): 무대가 hell/home_race 면 그 판 스위치를 켜고(시작 전 지옥이면 실패 없이 넘어감) 무대는 비운다.
  `cue_stage` 는 옛 이름을 그대로 돌려준다(옛 슬롯 옮기기에서 잃지 않게). 어느 단계를 불러도 두 판은 안 꺼진다. '지금 화면 저장'(snap_now)은 두 판을 안 담는다.
- 저장본 옮겨 담기(races `_migrate_stage`, bus.AFTER — 다음 명령 때 한 번): 무대 · ret 에 남은 hell/home_race 를 비우고 스위치로.
  hell 에 shown 칸이 없는 10-17 전 저장본은 그때 무대에 있던 판만 보이게(옛 보이기 그대로 — 무대에 없던 '켜짐' 퇴근빵은 끈다).
- 스트림덱: v2 스트림덱 주소에는 무대 단추가 없다(clip · skip · pause · neon) — 옛 단추가 show.stage 를 부르면 위 규칙.

**다시 판정 `_recheck` 하나**(races.py) — 점수(AFTER_SCORE) · 되돌리기(ON_UNDO) · 번외 판 시작/끝/취소 · 선수 넣기/빼기/이름(ON_ROSTER) · hell.goal · home.goal · home.on · hell.start/resume:
① 목표 밑으로 내려간 사람(또는 목표 0)은 escaped/notified 에서 빼고 **아직 안 보낸** off_work 카드를 걷는다(꺼져 있어도 — 거짓 축하 방지)
② 목표(>0) 이상인데 없는 사람 → 카드(켜져 있을 때만). 목표 0 = 목표 없음. 명단에서 빠진 사람은 손대지 않는다.
- 이름 바꾸기(ON_RENAME): hell.base · goals · escaped · home.goals · notified · 대기함 카드 이름을 같이 옮긴다. 빠진 선수 이름으로 바꿔도 명단 · 카드는 한 번만 남는다(같은 사람 · 같은 판 카드 한 장).
- 번외 판 점수는 **옛 것과 같게 본판만** 센다 — 번외 판을 [끝]내 본판에 합쳐지면 그 자리에서 판정(옛 것은 다음 화면 갱신 때, v2 전엔 다음 점수 때).
- 등수 · 진행은 점수(score) 순(옛 것 그대로, 대표님 10-17). 목표 숫자는 0~10만, inf · NaN · 글자는 400.

방송판:
- `widgets/games/race_view.js` 한 곳(node 검사 가능)이 kind · shape 를 정한다 — 지옥(on 이고 shown, 값 없으면 보임) > 퇴근(on). **둘 다 켜지면 지옥 먼저**(대표님 10-17).
  | 무대 | 모양 |
  |---|---|
  | 없음 · 대결 · 룰렛 · 슬롯 · 퀴즈(8명까지) | 큰 판(그대로, 1038,167 tr) — 룰렛 · 슬롯은 몇 초 위에 덮인다 |
  | 시그뒤집기 · 핀볼 · 퀴즈 9명 이상 | 얇은 판 `.hr-wrap.thin` — 제목 + '탈출 n/m' + 5초마다 한 사람(167~290). 지옥 불은 끈다 |
  | 주사위 | 숨김(대표님 10-17 — 칩 아님) |
  시그니처가 나오는 동안은 지금처럼 숨는다(hideInReaction).
- 층 homeRace · hell **15 → 13**(후원 순위 12 < 판 13 < 룰렛 어둡게 14 < 게임판 15). 이제 게임판과 같이 뜨므로 게임판이 늘 위.
- 판이 보이면(큰 · 얇은) game-home/game-hell 모드 → 점수판 · **후원 순위 · 최고 후원**이 비킨다(modes.css). 모금함 깃발은 판과 실제로 겹칠 때만
  `race-jar-home/hell` 모드로 비킨다(위젯이 상자를 잰다 — 깃발을 오른쪽으로 옮겼으면 그대로).
- 계좌 · 안내 전광판: `account.js accountAway(lm)` = 무대(AWAY_STAGES 주사위 · 룰렛 · 슬롯 · 시그뒤집기) · 번외 판 · **race_view 가 판을 띄움** → 머리 줄(옛 75644ae, 계좌 띠 겹침 B3).
  `AWAY_SLICES`(show · players · hell · home)가 바뀌면 다시 본다. notice.js 도 같은 함수.

조종실(이 두 파일만): `panels/games/races.js` — [🔥 시작/처음부터 다시] · [화면에서 내리기 / 👁 다시 띄우기](hell.show) · [끝내기 / 이어서 하기](hell.off · hell.resume),
알약 '진행 중 · 방송판에 보임 / 숨김 · 끝남 · 기록 남음', 주사위 · 지옥 뒤 숨는 때 한 줄. `okToTake`(무대 뺏기 확인)는 뺐다 — 무대를 안 쓴다.
`panels/ops/stage.js` — 무대 단추에서 두 판을 빼고 '늘 붙는 판' 줄(data-race home/hell 칩 → home.on · hell.show). STAGE_NAME 에는 옛 이름표를 남겼다(순서표 칩 이름).
검사: `v2/tests/test_races.py`(22 — 조사 재현 사례 undo · goalraise · goalzero · extra · rename · stage · restart · neg + 옛 무대 이름 · 순서표 · 저장본 옮겨 담기)
· `v2/tests/js/races_check.mjs`(race_view · 계좌 비키기 · 층 순서 — node).
검토(10-17): 헤드리스로 조종실 단추를 실제로 눌러 봤다 — 시작(확인창) · 화면에서 내리기/다시 띄우기 · 끝내기(확인창)/이어서 하기 · 퇴근빵 띄우기 · 무대 탭 늘 붙는 판 칩 · 주사위/없음 무대 단추가 모두 해당 명령을 보내고, 대결 · 주사위를 켜도 두 판이 안 꺼진다. 콘솔 오류 0, 가로 넘침 0(1440 · 945 · 390). 검사 하나 더: 옛 저장본의 ret 에 남은 끈 판(B5 꼴)은 되살리지 않는다.
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
## 10-17 이사 2차 — w2side
조종실 시안 B **묶음 C(오른쪽 칸 · 대기함 한 장 · 폰 서랍)** 와 대표님 10-17 '이미 넣은 입금' 경고. 설계서 scratchpad/b_v2_spec.md 2-4 · 5장 C. 단추 id · class · 명령 이름은 그대로(새 명령 없음).
- 대기함 카드 한 장(js/pending.js) — q1 시각 · 칭호 · 후원자 · Lv · 금액 · 점수 · [🏺][나눠 주기][무시] / q2 “메시지”(한 줄) · ✦ AI 한 줄(누르면 까닭 · 지난 배정) / 태그(있을 때만) / q3 선수 단추 격자.
  **어두운 '🤖 지급할까요?' 줄(ai.mountAsks)은 없앴다** — 같은 후원이 두 번 보였다. AI 가 고른 사람은 그 카드 선수 단추 하나에 주황 테두리 + '추천' 딱지(`.pbtn.rec`) — 누르면 다른 단추와 **같은** assign → 오배정 경고 → pending.assign.
  추천은 판단이 sure('거의 확실') · maybe('아마도')이고 그 이름이 지금 판 선수일 때만. '❓ 누구 것인지 모름' · '⏳ AI 붐빔' 도 숨기지 않는다. 얼림(마우스 · 손가락 1.5초) 동안은 추천 자리도 그대로(assist.js sig · pick 이 얼린 답).
  판단 고르기는 panels/ai/assist.js `pick(it)` 한 곳(옛 배지 규칙 · 서버 자동 진행 판단은 autoBadge 말을 빌림 — 그림자 모드에서 고른 사람이 있으면 '밍밍 거의 확실', 켬 · 보류면 '🤖 몰라서 보류' 그대로).
  격자: PC 6칸(7명 넘으면 2줄) · 900~1279 minmax(56px) · 폰 6칸 **36px**. 건수 딱지는 뺐다(숫자 카드 ③). 제목 '후원 대기함 · 먼저 온 순서'.
- 되돌리기(js/undo.js) — 작은 가로 단추. PC 는 대기함 제목 줄 오른쪽(`.undo-slot`), 폰은 서랍 머리. section#undo · .undo-btn · .what · score.undo {ref} 길 그대로(전체 글은 title).
- 시그 조종(js/queue.js) — 머리 조종 줄 `#ctl-sig` 에 [소리 막대] · [중단](`.ctl-stop`) · [건너뛰기](`.skip-btn`). 폰은 소리 막대만 ⋯ 판(#ctl-more-sig).
  [중단] = reaction.stop — 대기줄 2개 이상이면 한 번 묻고, 1개(지금 도는 것)면 바로. 목록 · [멈춤] · [전부 지우기](늘 묻는다)는 오른쪽 칸 맨 아래 접힘 `#queue-fold`(0개면 접고, 생기면 편다 · 제목 옆 건수).
- 후원 콘솔 미니(panels/ops/console.js `mountConsole(el, ctx, {mini:true})`) — `#con-mini`. 72px 시그 사진 · 금액 · 후원자 · 메시지 · 장부에 넣기 스위치 · ×N · [송출] · [전체 열기].
  보내는 길(같은 번호 재시도 · 두 번 막기)은 후원 콘솔과 **같은 함수**. 계좌 입금 추천 칸 · 갤러리는 전체 탭에만. 클릭 기록 구역 `con-mini`. 로그인 전엔 시그 목록을 안 묻는다(401 없음).
- 폰 아래 서랍(js/drawer.js · css/side.css) — 900 아래에서 #pending · #con-mini · #say-slot 을 서랍으로 **옮긴다**(노드 이동 — 얼림 · 입력 중 글 · 클릭 기록 구역 그대로), 900 이상이면 오른쪽 칸 제자리로.
  머리 [대기함 N │ 시그 송출 │ 한마디] · [↩ 무엇] · [전체 ▴]. 접힘 = 맨 앞 후원 한 장(선수 단추 · 나눠 주기 · 무시 포함, 170px) · 펼침 = 화면 85%. 본문 아래 여백 = 접힌 서랍 높이(--drawer-h).
  다른 파일이 열 때: `document.dispatchEvent(new CustomEvent('lm:drawer', {detail: {pane:'pend', open:true}}))`(숫자 카드 ③ — [B]). 서랍이 있으면 phone.js 의 📥 새 후원 띠는 안 띄운다.
- 🏦 '이미 넣은 입금' 경고(대표님 10-17) — 서버 v2/server/domain/bank.py `dup_warns` · POST /api/bank/dupcheck {id, name, amount, ledger} → {warns}(로그인 · 읽기만 · 실명 안 실음).
  sent_id(이 입금을 이미 송출 — 장부 manual_bank_<번호>[_N] 또는 카드 '씀') · same_recent(30분 안 같은 이름 · 같은 금액 장부 줄 — 투네이션 · 손으로 · 계좌) ·
  same_card(같은 금액 · 같은 입금자의 다른 입금 카드를 30분 안 송출 — 폰 앱 · 은행 확장이 같은 입금을 따로 잡은 경우) · no_ledger_big('장부에 넣기' 끈 채 5만 원 이상).
  후원 콘솔은 계좌 입금에서 [채우기] 한 송출만 보내기 **전에** 묻고, 하나라도 있으면 '이미 넣은 것 같아요 — 그래도 보낼까요?'(장부만이면 "'장부에 넣기' 가 꺼져 있어요 — 그래도 보낼까요?") 한 번. [안 보내기] 면 칸은 그대로.
  막지는 않는다(묻는 길이 안 닿으면 그냥 보낸다) · 빠진 것만 다시 넣는 재시도는 묻지 않는다. 검사 v2/tests/test_bank_dupcheck.py.
- 확인(10-17, 사본 임시 DB · 5344 · 헤드리스): 1440 · 945 · 390 × (로그인 · 방송 전 · 방송 중) 가로 넘침 0 · 로그인 화면 ₩ 없음 · 같은 후원 id 마다 카드 1장 · `.ai-ask` 0 ·
  1440 에서 카드 4장 굴리지 않고 보임(마지막 카드 834 ≤ 오른쪽 칸 890) · '밍밍 화이팅' 카드 추천 1개=밍밍 → 누르면 대기함에서 빠지고 밍밍 12→17 · 다른 사람 단추 → '🤖 다른 사람 후원 같아요' ·
  마우스를 올린 채 순위가 바뀌고 새 후원이 와도 첫 카드 단추 자리 그대로(손 빼면 정리) · [↩] → 후원이 대기함으로 · 같은 ref 다시 = '이미 되돌렸거나 없는 기록' ·
  폰 서랍 접힘 1장(단추 36px) · [시그 송출] 콘솔 미니 · [전체] 4장 · 점수판 마지막 줄 안 가림 · 폭 오가도 카드 한 장씩 · [중단] 1개 바로 / 3개 묻기 · [건너뛰기] · 소리 0.3 ·
  계좌 입금 같은 입금(폰 · 웹) 두 번째 [송출] → '이미 넣은 것 같아요' 상자. 콘솔 오류 0(favicon 404 · 일부러 낸 404 빼고). 검사 v2/tests/test_controller_side.py.
- 합칠 때: test_controller_frame 의 main.js 자리 검사는 `import { mountDrawer }`(주석이든 아니든) 로 바꿨다 — [B] · [D] 도 자기 줄만 같은 식으로.
- 검토(10-17 w2side 검토자): 진짜 마우스 · 손가락 입력(CDP Input)으로 눌러 봄 — PC [추천 밍밍] → pending.assign(12→17) · [무시] → 확인 → 빠짐 · [나눠 주기] 2명 → 2점 · 1점 · 제목 줄 [↩] → 되돌아옴 ·
  콘솔 미니(장부에 넣기 켬) [송출] → 대기함에 들어옴 · 조종 줄 [건너뛰기] 3→2 · [중단] 확인 → 0. 폰 서랍 접힘 카드 이름 단추 · [무시] · 서랍 [↩] · [시그 송출] 탭도 손가락으로 명령이 닿음.
  세 폭 × (로그인 · 방송 전 · 방송 중) 가로 넘침 0 · 카드 = 후원 id 수 · `.ai-ask` 0. 고친 것: dupcheck 의 '자기 줄' 빼기가 startswith(번호)라 번호 앞부분만 같은 다른 입금 줄까지 빼던 것 → `번호` 또는 `번호_N` 만(검사 test_own_rows_only_exact_prefix).

## 10-17 이사 2차 — w2feat
조종실 시안 B **묶음 D(새 기능)**. 설계서 scratchpad/b_v2_spec.md 5장 D. 단추 id · 명령 이름은 그대로, 새 명령은 `lights.manual` 하나.
- 🎵 BGM 재생 목록(panels/records/bgm.js) — 옛 조종실 '유튜브 재생 목록'을 옮겼다. 목록은 이 브라우저 `lm2_bgm`(소리가 조종실 창에서 나므로 창을 따라간다), 최대 200곡.
  영상 주소 → 한 곡 · 재생목록 주소(list=) → 안 보이는 플레이어(`cuePlaylist` 대신 `listType: 'playlist'` + `getPlaylist()`)로 통째. 반복 🔁 전체 · 🔂 한 곡 · ➡️ 끔,
  ⚠️ **곡이 끝나면(ENDED) 다음 곡** — 예전 v2 는 '끝남' 에서 멈췄다. 셈은 `nextIndex(mode, i, n, manual)` 하나(검사가 node 로 부른다). 이전 · 다음 · ↑↓ · 빼기 · 비우기,
  나오는 곡을 빼면 끝까지 두고 그 자리 곡으로(옛 ytlGone), 못 트는 곡은 건너뛰고 다 막히면 멈춘다. 제목은 재생 때 `getVideoData()` 를 곡에 적어 기억 + 서버 `/api/yt/info`.
  조종 줄 `#ctl-bgm` = 제목 · 1:42 / 3:58 · ▶/⏸ · ⏭ 다음 곡 · 'BGM 소리'(반 화면은 막대를 탭으로, 폰은 [더보기] 판). 목록에 곡이 있으면 보인다 — 유튜브는 안 부르고 기억한 제목으로.
  조종 줄 ▶ 를 처음 누르면 `ctx.tabs.prepare('bgm')`(tabs.js 에 한 줄 더함) 으로 BGM 탭을 숨긴 채 그려 거기에 플레이어를 만든다 — 화면은 지금 탭 그대로.
  ⚠️ 바깥 불러오기는 여전히 IFrame API 하나(탭을 열 때 · ▶ · 주소 넣기 때만). 썸네일(i.ytimg.com)은 안 그린다.
- 📺 `GET /api/yt/info?id=`(server/domain/yt_info.py, 로그인) — 옛 features/yt_info.py 처럼 유튜브 공식 oEmbed 로 제목만. 6초까지만 기다리고, 받은 것만 기억. `LM2_YT_INFO_OFF=1` 이면 안 묻는다(시험 서버).
- 📥 장부 엑셀(panels/records/csv.js + ledger.js) — [⬇ 엑셀(CSV)]: 이번 방송 후원 · 이번 방송 점수 기록 · 전체 후원(모든 회차) / 지난 방송 회차마다 후원 · 점수.
  옛 /api/archive/csv 약속 그대로: BOM(한글) · 한국 시각(PC 시계와 상관없이) · `= + - @` 앞에 '(수식 막기 — 월별 순위 `csvCell` 을 그대로 부름) · 금액 · 점수는 숫자 칸.
  서버는 안 고쳤다(/api/ledger · /api/scores · /api/sessions 를 읽어 이 PC 에서 만든다). 한 회차 2,000건이 끝(넘으면 알림). '방송 밖' 회차는 따로 못 받는다(빈 회차 = 이번 방송으로 읽히는 주소라).
- ⌨️ Ctrl+K(⌘K) 빠른 명령(js/cmdk.js) — 입력칸에 커서가 있어도 열린다 · Esc 닫기 · 로그인 전엔 안 열림. '밍밍 5' · '룰렛 돌려' · '대결 시작' · '+1분' · '올클리어' · '클립' · '다음 단계' · 탭 이름 · 'BGM 다음 곡'.
  말 규칙은 panels/ai/commands.js `runCommand` **한 곳** — AI 대화창(chat.js)의 '바로 하는 말' 도 이것을 부른다(전에는 chat.js 안에 있었다). '+1분'(match.add_time) · '클립'(clip.now) · '다음 단계'(show.cue) 를 더했다.
- 🙈 리액션 모드 스위치(js/rxswitch.js, `#ctl-rx`) — 옛 '수동 리액션 모드'. `lights.manual {on}` → lights 조각 `manual`(공개). 방송판 signature.js 가
  `setMode('reaction', 시그 도는 중 || manual)` — 시그니처가 없어도 위젯 숨김 · 조명. 시그가 끝나도 손으로 켠 것은 남고, **방송 끝이면 서버가 끈다**. 스트림덱 조명 단추는 안 건드렸다.
- main.js 는 [D] 주석 줄 자리를 채웠다(주석 글자는 줄 끝에 남겨 test_controller_frame 이 그대로 통과 — 합칠 때 B · C 줄과 겹치지 않게).
- 확인(10-17): 검사 v2/tests/test_w2feat.py(+ js/w2feat_check.mjs 38개) · test_lights 3개 더함. 헤드리스 크롬 1440 · 945 · 390 × (로그인 · 방송 전 · 방송 중) 가로 넘침 0 ·
  BGM 200곡 · 장부 엑셀 메뉴 · Ctrl+K 상자 세 폭 넘침 0, 가짜 유튜브로 조종 줄 ▶(탭 그대로 'home') → ENDED 전체 반복 1→2 · 한 곡 반복 그대로 · 끔 마지막에서 멈춤 · 전체 마지막→처음,
  재생목록 주소 → 12곡, Ctrl+K '밍 5' Enter → 밍밍 12→17, 리액션 스위치 → 방송판 `.reaction-mode` + 점수판 등 숨김 → 끄면 원래대로 → 방송 끝 manual=false. 콘솔 오류 0(favicon 404 빼고).
- 검토(10-17) 고친 것: ① Ctrl+K 상자가 확인 상자(.modal-wrap 100)보다 위(120)라 '올클리어' · '룰렛 돌려' 가 묻는 [확인] 을 누를 수 없었다 → 98(더보기 판 95 위 · 확인 상자 아래).
  ② 🔂 한 곡 반복에서 못 트는 곡이면 같은 곡을 몇 번이고 다시 불렀다 → `skipIndex` 로 다음 곡. ③ 나오던 **마지막** 곡을 빼면 바로 앞 곡이 다시 나왔다 →
  `goneIndex`(전체 · 한 곡 반복은 처음으로, 반복 끔은 멈춤). 검사: w2feat_check.mjs 5개 · test_cmdk_under_confirm_box. 헤드리스로 진짜 마우스 · 키보드를 눌러
  리액션 스위치(PC · 폰) · 조종 줄 ▶/⏭ · Ctrl+K '밍밍 5'(점수 +5) · '+1분'(240→300초) · 장부 [⬇ 엑셀] 을 확인, 세 폭 × 로그인 · 방송 전 · 방송 중 가로 넘침 0, 같은 후원(tx) 한 장.

## 10-17 계좌 메모 배우기
운영 실측(송출된 계좌 카드 65건): 기계가 채운 닉네임이 맞은 건 40%, 가장 흔한 실수는 붙여 쓴 메모('하루밍밍화이팅')를 통째로 닉네임에 넣는 name_only(33건).
- 순서(`domain/bank_memo.py` `smart_split` — 옛 `split_memo` 는 그대로 두고 **앞에** 셋): **A 배운 짝**(learned · 확실) → 메모 없이 보냄(no_memo) →
  **B 지난 기록**(known_name · 확실 — donations.name · donor_memory.donor 중 메모 어디든 든 가장 긴 이름, 2자 이상, 선수 · 번외 판 · 운영비 이름 빼고, 두 글자는 앞뒤가 떨어져 있을 때만) →
  **C 선수 이름 떼기**(player_strip · 확인 — 선수 이름과 '아·야·님' 꼬리를 지우고 남은 첫 덩어리, 응원 말이면 마지막 덩어리) → 옛 규칙(known · player_cut · first · message · name_only).
  A·B·C 의 할 말 = 메모 − 닉네임 − 선수 이름 − 입금자 실명. 메모의 선수는 카드 target(0.9 · '메모에 선수 이름') — 그때는 규칙 · AI 예상을 안 부른다. AI 나누기는 옛 길의 first · message 만.
- 후원 콘솔 카드 딱지(bankcore.js BANK_HOW): '✓ 배운 짝' · '✓ 지난 기록'(초록) · '선수 이름 떼고 남은 말 — 확인'(노랑).
- 배우기(`domain/bank_learn.py`, 표 `bank_learn`): 입금자명은 **지문**(sha256 앞 32자)만 — 실명 글자는 표 · 답 · 조각 · 명령 기록 · print 어디에도 없다(그래서 백업에 남아도 된다).
  때: 계좌 카드 [채우기] → [송출] — ① `/api/donation` tx_id `manual_bank_<카드id>[_N]`(로그인 · 장부에 넣기) ② `/api/bank/inbox/<카드id>/used {name}`(시그니처만 보내도).
  카드 id → 카드 holder → 보낸 이름. **한 카드는 첫 이름**(×N · 나눠 보내기), **같은 입금자는 가장 최근 것**. 익명 · 수동송출은 안 배운다. 서버는 표를 메모리에 안 쥔다(입금마다 읽는다).
- 미리 배우기 `v2/tools/import_bank_learning.py` — 옛 bank_inbox.json(id · ref · holder) · 옛 장부(donation_archive · donation_history 의 manual_bank_ tx_id · name) · v2 장부(bank_inbox · donations)를
  **읽기만** 해서 짝을 넣는다. 기본은 세어 보기, `--write` 로 진짜. 건수만 찍는다. **v2 를 켠 채로 돌린다** — 따로 된 표라 켜진 서버가 덮지 않고, 쓰기는 BEGIN IMMEDIATE 한 번(서버 busy_timeout 5초),
  방송 중에 배운 더 최근 짝은 안 덮는다. 명령은 deploy/README.md 3절.
- 검사: v2/tests/test_bank_learn.py(실측 모양 가짜 이름 27경우 · 배우기 · 실명 안 나감 · 도구 가짜 파일 · 가짜 옛 DB · 켜진 서버 옆 쓰기), test_bank.py 의 옛 MemoSplit(옛 bank_memo_test) 그대로 통과.

## 10-17 AI 권한 넓히기
대표님이 고른 세 가지 + 같은 날 추가 요청 "금액은 조금이라도 애매하면 보류로 놓고 나를 호출". 원칙: **AI 가 점수 · 돈을 바꾸는 길은 ③ 하나뿐**(스위치 · 확신 0.9 · 애매함 0),
그 밖에 점수가 바뀌는 길은 늘 사람이 [실행] 을 누른다. 열쇠는 어디에도 안 찍는다. AI 가 막히면(키 없음 · 붐빔 · 한도) 서버 규칙 · 계산으로 조용히 물러난다.
- Claude 부르기: `ai._claude_tools_call`(바깥으로 나가는 곳 — 검사는 막는다) · `ai.ai_tools`(키 없으면 'nokey', 붐비면 한 번 더, 분당 한도 같이 씀).
  anthropic 1.x `messages.create(tools=[…], tool_choice={'type':'tool','name':'propose_commands'})`, **temperature 안 보냄**, 모델 `CLAUDE_MODEL`(기본 claude-haiku-5-5).
- ① 말로 조종(`domain/ai_cmd.py`, `POST /api/ai/command {text, bgm?}`) — 조종실 규칙(commands.js) → 물음 꼴이면 `{kind:'question'}`(예전처럼 /api/ai/chat) →
  서버 규칙(`rule_plan`: '공지 바꿔: …' · '한마디: …' · 'UP: …' · '대결 3분 시작' · '예지 기여도 3' · '밍밍 5점' · '조명 빨강' · '시작 화면 10분' · '룰렛판 띄워' · 'BGM 다음 곡' …) → Claude 도구.
  돌아온 줄은 `check()` 가 **허용 목록 · 칸 이름(모르는 칸 거절) · 값 범위 · 지금 명단(번외 판이면 번외 판) · 대기함 id** 로 다시 만들고, 이상하면 그 줄만 버린다(`dropped` 로 까닭).
  한 번에 6줄까지만 본다. 조종실(대화창 · Ctrl+K)은 카드로 보여 준다(`panels/ai/cards.js`): '🤖 하율에게 +5점 [실행] [취소]' · 여럿이면 [모두 실행] · 10분 지난 카드는 단추를 닫는다.
  [실행] = 조종실 `ctx.run`(→ /api/cmd, 명령 번호 cid) · 슬롯은 `/api/slot/spin` · BGM 은 조종실 브라우저.
- ② 안전한 건 바로 — 조각 `ai_opts {direct: True}`(비공개) · 명령 `ai.set {direct}` · AI 패널 머리 단추 '🤖 안전한 건 AI 가 바로'.
  SAFE 만 서버가 `bus.run(by='ai')`(장부 events.by = 'ai'): 한 번 말에 3개 · 1분에 10개가 넘으면 멈추고 [실행] 카드로. 되돌리기 = 바로 앞 값으로 다시 명령(`undo_of`):
  공지 추가 → notice.remove · 공지 고치기 → 전 글 · 무대 → 전 무대 · 순서표 → 전 단계(go id) · 시작/끝 화면 → 전 모습 · 조명 → lights.set 전 색. 한마디 · UP · 다음 곡은 되돌릴 게 없다.

  | 명령 | 무엇 | 어떻게 |
  |---|---|---|
  | score.add {name, delta ±1~50 \| contrib ±1~100} | 점수 · 기여도 | [실행] |
  | pending.assign {id, name} · pending.ignore {id} | 대기함 배정 · 무시 | [실행] |
  | match.start · match.pause · match.set_time {min 0~180, sec} · match.add_time {sec ±3시간} | 대결 | [실행] |
  | roulette.spin · roulette.stop · slot.spin | 게임 돌리기 · 멈추기 | [실행] |
  | reaction.skip · clip.now · goal.set {target 0~1억} | 시그 넘기기 · 클립 · 목표 | [실행] |
  | notice.add · notice.edit {index, text} · notice.now {text \| index} | 공지 | 바로(SAFE) |
  | cast.say · cast.up {text ≤60} | 화면에 한마디 · UP 자막 | 바로 |
  | show.cue {next \| prev} · show.stage {판 \| null} · screen.set {start \| end \| off} | 순서표 · 무대 띄우기만 · 시작/끝 화면 | 바로 |
  | lights.color {#rrggbb \| RAINBOW \| OFF} · bgm.next · bgm.toggle · bgm.play {title} | 조명 · BGM(조종실 쪽) | 바로 |

  목록 밖(방송 시작/끝 · 되돌리기 · 설정 옮기기 · 시그니처 지우기 · 버전 바꾸기 · 후원 넣기 · 모금함 …)은 AI 가 내도 버린다. show.stage 는 퇴근빵 · 지옥탈출(판 스위치)을 안 받는다.
- ③ AI 배정(`autopilot.py`) — `use_ai_assign`(기본 **끔**) · `assign_max`(기본 100,000 — **미만**만, 규칙 'auto' 에도 같이). 규칙이 'auto' 가 아닌 후원(suggest/unknown)을 AI 에게 **한 번** 묻는다
  (그림자면 늘 — 채점용, 켬이면 스위치가 켜졌을 때만, 애매하면 아예 안 묻는다). 날답 `ai_raw`(0.88 로 깎기 전)를 기억(`_SUGGEST_CACHE`)에 같이 둬 배지 · 자동 진행이 또 안 묻는다.
  AI 가 스스로 주는 조건: 켬 · 스위치 켬 · 확신 ≥ 0.9 · 지금 판 선수 · 한 사람 · 첫 물음의 답(다시 물은 답 · 10초 넘긴 답 · 막힌 답 ✗) · 애매함 0 · 시험/되돌려 온 후원 아님.
  준 것은 by 'autopilot-ai'(기록 줄 · 점수 기록 줄 '🤖 AI 가 줌'), 되돌리면 대기함으로(was_ai) 다시는 자동으로 안 준다. 숫자: ai_agree · ai_disagree · ai_held · ai_done · ai_undone(규칙 채점과 따로).
  조종실 자동 진행 탭: 'AI 가 직접 배정' 스위치(켤 때 한 번 묻는다) · 금액 상한 칸 · 'AI 채점' 줄 + 'AI 맞힌 비율이 쌓이면 켜세요(30건 · 95% 권장)'.
- ⏸ 애매하면 보류(`autopilot.ambiguity`) — 하나라도 걸리면 기계(규칙 · AI)는 안 준다: 메시지에 선수 둘 이상 · 나눔 말(나눠 · 반반 · 각각 · n분의 · 둘 다 …) ·
  메시지 금액(5만원 · 오만원 · 30,000 · 1.5만)/점수(5점)가 실제와 다름 · 만 원 경계(나머지 4,000~6,000) · 상한 이상 · 같은 사람 연속(대기함에 여럿 · 시그 ×N · 계좌 _N) ·
  계좌 입금(tx manual_bank_) · 이력이 여러 선수로 갈림. 카드 `auto.check`(애매함) · `auto.hold`(켬에서 안 준 까닭 전부 — 그림자는 애매함만), 기록 줄에도.
  그림자 채점: 애매해서 보류한 것을 사람이 주면 'held'(⏸ 애매해서 보류)로 따로 센다. 조종실: 카드 주황 테두리 + '⏸ 보류 — 확인해 주세요 · 까닭 한 줄',
  상태 줄 띠(`panels/auto/holdband.js` → alarm.js bandAdd) '🙋 확인할 후원 N건' + [보기](폰은 서랍을 펼친다) — **소리 없음**, 처리하면 내려간다, 자동 진행 끔이면 안 뜬다.
- 검사: v2/tests/test_ai_power.py(허용 목록 밖 · 없는 선수 · 범위 밖 · 모르는 칸 · 이상한 도구 이름/입력 버림 · [실행] 없이 점수 안 바뀜 · 바로 실행 3개/분당 10개 · 되돌리기 ·
  스위치 끔 · 키 없음/붐빔 조용히 물러남 · SDK 모양(temperature 없음) · 애매함 경우마다 보류 · AI 배정 0.95 줌/0.89 · 없는 선수 · 늦음 · 막힘 · 스위치 끔 안 줌 · 그림자 AI 채점 · 금액 읽기).
  헤드리스 크롬(임시 서버 5350 · 임시 DB · AI 꺼짐) 1440 · 390: 대화창 카드 · Ctrl+K 카드 · 보류 카드 · 띠 가로 넘침 0, [모두 실행] → 대결 3분 · 시작 확인.

## 10-17 후원 번호 · 재송출
대표님 "후원 한 건 한 건마다 번호를 붙여서 재송출도 가능하게" + 보충 "내가 몇 번을 알아야 하는 건 아니고, 장부가 헷갈릴까 봐 임의의 숫자만".
그래서 번호는 **장부 줄을 구별하는 조용한 꼬리표**이고, 번호로 부르는 기능(Ctrl+K · AI '12번 다시')은 만들지 않았다(ai_cmd 허용 목록에도 없음).
- 🏷️ **장부 줄 번호** `donations.no`(store.py) — 장부 전체에서 겹치지 않는 숫자. `add_donation` 이 넣는 순간 `MAX(no)+1`(명령은 한 줄로 서서 하나씩) · `UNIQUE` 색인이 한 번 더 지킨다.
  회차마다 1부터가 아니다(대표님 보충 — 겹치지만 않으면 됨, 가장 단순한 쪽). 서버를 다시 켜도 장부에서 이어진다.
  - 투네이션 · 화면에만 소액 · 손 송출 · 계좌 송출 · 다시 보기/테스트 · 다시 송출 기록 — 장부에 들어가는 줄은 전부 번호를 받는다.
    같은 tx 재전송 · 12초 중복은 장부에 안 들어가니 번호도 없다.
  - 예전 줄(칸이 생기기 전 v2 줄 · `import_old_db.py` 로 옮긴 옛 장부)은 서버가 켜질 때 **들어온 순서(at)대로** 이어서 매긴다 —
    장부 탭 모든 줄을 구별할 수 있게. 옛 장부를 서버가 켜진 채 옮기면 다음에 켤 때 매겨진다(재송출은 id 로 하니 그 사이에도 된다).
  - ⚠️ SQLite rowid 를 쓰지 않은 까닭: 이 표는 TEXT 기본 키라 VACUUM(backup_db.py 가 한다)이 rowid 를 다시 매길 수 있다.
  - 번호는 조종실에만: 장부 탭 줄 끝 작은 회색 `#12` · 다시 송출 확인 상자 아래 '장부 #12' · 후원 콘솔 송출 토스트('… · 장부 #12', 계좌 입금이면
    '장부 #12 로 들어갔어요'). `/api/donation` 은 로그인한 손 송출(tx `manual_`)에만 `no` 를 돌려준다 — 리스너 답 모양은 옛 것 그대로.
    공개 조각(popup · queue …)에는 번호가 없다(검사 test_donno Numbers.test_broadcast_snapshot_has_no_numbers).
- ↻ **다시 송출** — 명령 `donation.replay {id}`(로그인) · 주소 `POST /api/donation/replay {id}`(시그니처를 명령 밖에서 금액으로 다시 맞춘다 —
  바로 틀기와 같은 셈, 최저선 미만이면 시그니처 없이, 목록을 못 받으면 팝업만).
  - 방송 화면에만: 후원 팝업(`encore: true` → 카드 위 보라 '↻ 다시 보기' 딱지) + 시그니처 대기줄 줄(`encore: true` → 사진 오른쪽 위 딱지,
    `count_tally=False` 라 ×N 묶음 · 시그 집계에 안 낀다). 1만 원 미만은 맨 위 소액 띠(display_only).
    ⚠️ queue 의 `replay` 칸은 '다 틀기' 회차 번호로 이미 쓰고 있어 새 칸 이름을 `encore` 로 했다.
  - 안 들어가는 것: 대기함 · 점수 · 장부 합계 · 정산 차액 · 후원 순위 · 한 방 최고 · 시그 집계 · 월별 · AI 기억 · 등급 · 자동 진행
    (AFTER_DONATION · ON_ASSIGN 고리를 안 부른다 — 투네이션 '다시 보기' 와 같은 규칙). 장부엔 status `display`(합계 밖) · source `replay` ·
    메모 '↻ #12 다시 송출' 줄 하나.
  - 거절: 없는 id · 다른 회차 404 '그런 후원이 없어요' · 다시 송출 기록 줄 · 대시보드 테스트 줄 409 · 로그인 없으면 401.
  - 조종실(`js/replay.js`): 장부 탭 **이번 방송 · 방송 중** 줄마다 [↻ 다시 송출](폰 36px) → 화면 안 확인 상자(`confirmBox` 가 body 에 요소를 받게 고침,
    기본 손가락은 [취소]) — '영원 ₩30,000' 크게 · '21:03 · “밍밍화이팅”' · '점수 · 정산 · 후원 순위엔 안 들어가요' · 작은 회색 '장부 #12' → [띄우기].
    대기함 카드에도 [↻] 를 달아 봤으나 좁은 오른쪽 칸에서 후원자 이름이 '아…' 로 잘려(1440 사진) 뺐다 — 배정 실수가 더 무섭다.
- 덤: 계좌 카드 [채우기] 안내 글이 실제 단추 글자를 따른다('채웠어요 — 확인하고 [장부에 넣고 송출]', 장부에 넣기를 끄면 [시그니처 송출]).
- 검사: v2/tests/test_donno.py — 번호 이어짐(다시 켜기 흉내) · UNIQUE · 중복 tx/12초 중복 새 번호 없음 · 손 송출 답 no/리스너 답 그대로 ·
  방송판 스냅샷에 번호 없음 · 예전 줄 순서대로 매기기 · 다시 송출이 합계/대기함/점수/순위/최고/집계/월별/정산/고리 그대로 · encore 팝업 · 대기줄 ·
  두 번 눌러도 안 묶임 · 소액은 띠 · 404/409/401 · AI 허용 목록에 없음 · 계좌 안내 글 · replay.js 에 confirm() 없음.
  헤드리스 크롬(임시 서버 5360 · 임시 DB · 끝나고 끔) 1440 · 390: [↻ 다시 송출] → 확인 상자 → [띄우기] · [취소], 가로 넘침 0 · 장부 합계 그대로 ·
  방송판에 두 딱지가 뜨고 화면 어디에도 번호 없음.

## 10-17 안전 꾸러미 — mask
방송판에 나가는 후원 메시지 금칙어 거르기 · 후원마다 [가리기]. **장부 · 대기함(조종실)은 원문 그대로**, 이름(닉네임)은 안 건드린다(닉네임 거르기는 대표님 결정으로 남김).
- 🧩 **보여 주는 사본**(state.py `VIEWS` · `DEPENDS`) — 조각 · 장부는 원문, 내보낼 때만 고친 사본. `State.snapshot(authed, on_air)` · `hub.publish(seq, changed, slices)` 가 쓴다.
  on_air = 로그인 안 한 화면 **또는** 방송판 종류(`hub.ON_AIR_KINDS` overlay · alertbox · sigdisp · slot). ⚠️ 방송판 종류는 이제 로그인돼 있어도(같은 브라우저 쿠키 · ?token=)
  **공개 조각만** 받는다 — 대기함 원문이 OBS 로 가지 않게(방송판은 비공개 조각을 안 쓴다 — grep 확인). 명령 권한(authed)은 그대로.
  `DEPENDS['mask'] = popup · queue · cast · screen · pending` — 금칙어 · 가리기가 바뀌면 원문이 그대로여도 그 조각들을 새 사본으로 다시 보낸다.
- 🙈 `domain/mask.py` — 조각 **mask**(비공개) `{words[], rules{phone, account, url}, hidden[id…](500), ver}`.
  거르는 곳: popup.donation.message(후원 카드 · 소액 띠) · queue.items[].message · msgs[](시그니처 카드 · 출연진 전광판) · cast.fx.message · screen 안의 message/msgs(끝 화면 — 엔딩 크레딧이 메시지를 실으면 저절로).
  규칙: 전화번호(010 · +82 · 02 · 031 · 070, 공백 · 점 · - 섞여도) · 계좌 꼴 숫자(10~16자리, 쉼표 금액은 그대로, 띄어쓰기로 이은 것은 5자리 넘는 덩어리가 있을 때만 — 날짜 · 시각 보호) ·
  인터넷 주소 · 메일('닷컴' 포함) · 금칙어(대소문자 무시, 글자 사이 숫자 · 기호 2개까지 — 띄어쓰기는 안 잡음). 걸린 곳은 ●●●. 거르다 넘어지면 방송판엔 메시지를 비운 사본.
  명령: `mask.word.add {word|words}`(쉼표 · 줄바꿈) · `mask.word.remove` · `mask.word.recommend`(RECOMMENDED 17개 — 기본 목록은 비어 있음) · `mask.word.clear` · `mask.rule {key, on}` · `mask.hide {id, on}`.
  `POST /api/mask/preview {text}`(로그인 · 장부에 안 적음). 새 방송 시작이면 hidden 만 비운다.
- 🔗 가리기 연결: queue 줄에 `don_ids`(msgs 와 같은 차례 — 묶음 ×N 은 그 후원 차례만) · 다시 송출 팝업에 `src`(원래 후원) — 방송판 사본에선 둘 다 뺀다.
  대기줄 줄 id(rq_ — 후원 콘솔 '바로 틀기')도 받는다. 투네이션 · 계좌(manual_bank_) · 손 송출 모두 장부 id 로.
- 📋 조종실에 붙는 것: 대기함 카드(조종실 사본) · `/api/ledger` 줄에 `mask{hits, text}` — 원문(message)은 그대로.
  `js/mask.js` — 기본은 **가린 글**(대표님이 소리 내 읽다 번호 · 욕을 안 읽게) + ⚠ 딱지(누르면 원문 ↔ 가린 글, 이 기기에서만) · [가리기]/[보이기](흐리게 + 🙈).
  대기함 q2 줄 · 장부 '이번 방송' 줄(.rc-msgrow). 설정 > 방송 화면 > 🙈 **메시지 거르기**(`panels/ops/mask.js`, 탭 id ops-mask · pre) — 규칙 스위치 셋 · 금칙어 알약 · 추천 목록 · 모두 지우기(화면 안 확인 상자) · 시험해 보기.
- 📺 방송판: 같은 후원(id)이 글만 바뀌어 오면 다시 띄우지 않고 글자만 — donation.js `retext`(donationCard 에도 · 시그니처가 rq 로 부름) · small-don.js · signature.js(카드 단계) · sigdisp.js(원래 됨).
- 검사: v2/tests/test_mask.py 23개(규칙 · 공개/비공개 · 로그인 안 한/한 방송판 쪽지 전부 · 조종실 원문 · 가리기 즉시 · 묶음 차례 · 다시 송출 · 콘솔 · 계좌 · 이름 그대로 · 새 방송 · 끝 화면 · confirm/소리 없음).
  헤드리스 크롬(임시 서버 5373 · 임시 DB · 끝나고 끔) 1440 · 390: 대기함 ⚠ → 원문 · [가리기] → 출연진 전광판 글 사라짐 → [보이기] · 장부 ⚠ · [가리기] · 설정 탭 추천 넣기 · 더하기 · × · 시험해 보기,
  방송판이 받은 쪽지 13개에 전화 · 주소 · pending · mask 없음, 가로 넘침 0(세 화면 × 두 폭).
- 남은 결정(대표님): 닉네임도 거를지 · 추천 목록 낱말 · '010' 을 한글로 쓴 것(공일공)은 못 잡음 · 숫자만 10자리 넘는 금액(1000000000원)은 계좌로 보고 가림.
