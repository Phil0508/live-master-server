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
