# v2 운영 서버에 올리기 · 갈아타기

> ⚠️ **여기 적힌 일은 하나도 저절로 되지 않는다.** 단계마다 대표님 허락을 받고 한다(받기 · 설치 · 서비스 · 주소 바꾸기).
> ⚠️ **방송 중(수 17:00 ~ 목 03:00)에는 아무것도 하지 않는다.**
> 옛 서버(livemaster · 포트 8080 · 443)는 끝까지 그대로 둔다 — 되돌릴 길이다.

## 무엇이 어디서 도나

| 것 | 옛 것 | v2 |
|---|---|---|
| 서버 | `livemaster` (server.py, 8080) | `livemaster-v2` (`python -m v2.server.app`, 127.0.0.1:5300) |
| 바깥 주소 | `https://엔젤컴퍼니.메인.한국/` | 같은 주소 **:8443** (`Caddyfile.v2`) — DNS 안 건드림 |
| 장부 | Postgres(`DATABASE_URL`) | SQLite `v2/data/lm2.db` + 매일 백업(`livemaster-v2-backup.timer`) |
| 진행봇 | `livemaster-bot` | `livemaster-bot-v2` — **둘을 같이 켜면 채팅이 두 번씩 올라간다** |
| 리스너 | `toon-listener` → 8080 | 같은 리스너, 갈아타는 날 서비스 파일을 **통째로** v2 판(`v2/deploy/toon-listener.service`)으로 → 5300 |

## 0. 지금 상태 (10-07 아침 시험판으로 올림)
- `livemaster-v2` 켜짐(127.0.0.1:5300) · 덧붙임 `/etc/systemd/system/livemaster-v2.service.d/trial.conf` = **LM2_TRIAL=1**(시그니처 보관소 · 리스너 설정 · 서버 버전 바꾸기 잠금).
- Caddy :8443 열림(백업 `/etc/caddy/Caddyfile.bak-before-v2`) · 옛 장부 옮김(후원 1377 · 기억 688 · 별명 393 · 순위 제외 6) · 백업 타이머 켜짐.
- 리스너 · 진행봇은 아직 옛 서버 쪽 — v2 에는 진짜 후원이 안 온다(후원 콘솔로 시험).
- ⚠️ 자동 배포(auto-deploy)는 v2 를 다시 켜지 않는다 — v2 코드를 올린 뒤엔 `sudo systemctl restart livemaster-v2`.
  (10-17 auto-deploy.sh 가 v2 를 알게 고쳤다 — main 에 올라간 뒤부터는 저절로 다시 켠다 · 방송 중엔 기다린다. 아래 6)

## 🩹 감시 장치 (대표님 결정 10-07: 죽은 것은 방송 중에도 다시 켠다)
```bash
sudo cp /opt/livemaster/v2/deploy/livemaster-watchdog.service /opt/livemaster/v2/deploy/livemaster-watchdog.timer /etc/systemd/system/
sudo systemctl daemon-reload && sudo systemctl enable --now livemaster-watchdog.timer
sudo systemctl start livemaster-watchdog.service && journalctl -u livemaster-watchdog -n 5 --no-pager
```
- 1분마다: 옛 서버 · v2 · 리스너가 '켜져 있는데 답을 안 하면' 다시 켠다(3분 기다림 · 1시간에 3번까지 · 넘으면 알림만).
- 하는 일은 `systemctl restart` 뿐 — 코드 · 설정은 안 바꾼다. 기록은 /var/lib/livemaster-watchdog/events.jsonl → 폰 상태판(/health)에 보인다.
- 폰 알림: /etc/livemaster.env 에 `NOTIFY_URL=https://ntfy.sh/<비밀 주제>` (없으면 기록만).

## 🤖 AI 를 Claude 로 (대표님 결정 10-07: NVIDIA 말고 Claude Haiku 4.5, v2 시험판부터)
- 키는 **대표님이** console.anthropic.com 에서 만든다(가입 · 충전 · 'API 키'). 채팅에 붙여 넣지 말 것.
- 서버에 넣기 — 아래 한 줄을 PC 터미널에서 돌리면 키를 **화면에 안 보이게** 묻고, v2 만 다시 켠다(옛 서버는 이 키를 안 읽는다):
```bash
ssh -t live 'read -rsp "Claude API 키 붙여넣기: " K; echo; sudo sed -i "/^ANTHROPIC_API_KEY=/d" /etc/livemaster.env; printf "\nANTHROPIC_API_KEY=%s\n" "$K" | sudo tee -a /etc/livemaster.env >/dev/null; unset K; sudo systemctl restart livemaster-v2; echo 넣었어요'
```
- 확인: 조종실 AI 패널 머리 글자가 'AI 대기 중 · Claude' → 한 번 물으면 'Claude 연결됨 · 0.7초'. 서버 기록 `journalctl -u livemaster-v2 | grep Claude`.
- 모델 바꾸기: /etc/livemaster.env 에 `CLAUDE_MODEL=…`(기본 claude-haiku-4-5). 끄기: ANTHROPIC_API_KEY 줄을 지우고 v2 재시작 → NVIDIA 로 돌아간다.
- Claude 가 막히면(붐빔 · 연결 실패) NVIDIA 키가 있을 때 NVIDIA 로 넘어간다. 키 · 모델이 틀리면(401 · 404) 다시 안 묻고 도우미가 무엇을 고칠지 말한다.

## 1. 나란히 띄우기 (허락 필요: 받기 · 서비스)

```bash
cd /opt/livemaster
sudo -u livemaster .venv/bin/pip install -r v2/requirements.txt      # fastapi · uvicorn · python-multipart 받기
sudo cp v2/deploy/livemaster-v2.service v2/deploy/livemaster-v2-backup.service v2/deploy/livemaster-v2-backup.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now livemaster-v2
curl -s http://127.0.0.1:5300/api/health | head -c 300; echo            # {"ok":true …} 가 나와야 한다
```
- 비밀번호 · 열쇠는 `/etc/livemaster.env` 의 것을 같이 쓴다(ADMIN_PASSWORD · SESSION_SECRET · Supabase · NVIDIA).
- 버전 되돌리기가 v2 도 재시작하도록 sudoers 에 **따로 된 파일**을 더한다(옛 `livemaster-restart` 파일은 안 건드린다).
  `deploy/setup.sh --with-v2` 가 하는 것과 같다 — 손으로 할 때:
```bash
printf '%s
' 'livemaster ALL=(root) NOPASSWD: /usr/bin/systemctl restart livemaster-v2, /usr/bin/systemctl restart livemaster-bot-v2, /usr/bin/systemctl restart toon-listener, /bin/systemctl restart livemaster-v2, /bin/systemctl restart livemaster-bot-v2, /bin/systemctl restart toon-listener' > /tmp/lm2-sudoers
sudo visudo -cf /tmp/lm2-sudoers && sudo install -m 440 /tmp/lm2-sudoers /etc/sudoers.d/livemaster-v2-restart; rm -f /tmp/lm2-sudoers
```

## 2. 바깥 주소 열기 (허락 필요: Caddy · 방화벽)

```bash
sudo cp /etc/caddy/Caddyfile /etc/caddy/Caddyfile.bak-before-v2
sudo sh -c 'cat /opt/livemaster/v2/deploy/Caddyfile.v2 >> /etc/caddy/Caddyfile'
sudo touch /var/log/caddy/livemaster-v2.log && sudo chown caddy:caddy /var/log/caddy/livemaster-v2.log
sudo -u caddy -H caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile
# ⚠️ validate 를 root 로(sudo caddy validate) 돌리면 기록 파일이 root 것으로 생겨 reload 가 실패한다(10-07 겪음 — 옛 설정은 그대로 돌아 방송 주소는 멀쩡했다).
#    그때는 sudo chown caddy:caddy /var/log/caddy/livemaster-v2.log
sudo systemctl reload caddy
sudo ufw status | grep -q active && sudo ufw allow 8443/tcp
```
폰으로 `https://엔젤컴퍼니.메인.한국:8443/health` — 초록 점이면 된다.

## 3. 옛 기록 · 설정 옮기기

```bash
sudo systemctl stop livemaster-v2                                       # 켜진 서버는 순위 제외 · 등급을 덮어쓴다
cd /opt/livemaster && set -a && . /etc/livemaster.env && set +a
sudo -E -u livemaster .venv/bin/python -m v2.tools.import_old_db --v2-db v2/data/lm2.db          # 세어 보기만
sudo -E -u livemaster .venv/bin/python -m v2.tools.import_old_db --v2-db v2/data/lm2.db --write  # 진짜로
sudo systemctl start livemaster-v2
```
- 옮기는 것: 지난 방송 후원(보관 장부) · 후원자 기억 · 별명 기억 · 순위에서 뺀 이름 · 직접 준 등급. **옛 장부는 읽기만 한다.**
- 설정(공지 · 계좌 · 목표 · 테마 · 게임 판 …)은 옛 조종실 **[💾 백업]** 파일을 v2 조종실 **[옛 설정 옮기기]** 로.

## 4. 연습 방송 (방송 없는 날)

1. OBS 에 브라우저 소스 하나 더: `https://엔젤컴퍼니.메인.한국:8443/overlay/` (1080×1920). 클립을 쓰려면 이 소스에 **'고급 접근 권한'**.
2. v2 조종실 `…:8443/controller/` 로 방송 시작 → **후원 콘솔**로 테스트 후원 → 배정 · 되돌리기 · 시그니처 · 게임 한 바퀴.
3. 점검 탭(🛫)이 전부 초록인지. 폰으로 `/health`.
4. 끝나면 방송 끝 → 장부 탭에서 기록이 남았는지.

## 5. 갈아타는 날 — 점검표 (위에서부터 차례로 · 하나 끝나면 ☑)

> ⛔ **방송(수 17:00 ~ 목 03:00) 중에는 하지 않는다.** 수요일이면 **방송 시작 2시간 전(15:00)까지 다 끝낸다** — 넘으면 다음 주로 미룬다.
> 단계마다 대표님 허락을 받는다. 서버 명령은 `ssh live` 로 들어가서 한다. 막히면 그 자리에서 멈추고 **'되돌리는 길'** 의 같은 번호로 간다.
> 이 날 옛 서버(livemaster · 8080)는 **끄지 않는다** — 되돌릴 길이다.

### ⓪ 준비 (전날까지)
- [ ] **4. 연습 방송**을 한 번 해 봤다(후원 콘솔 → 배정 · 되돌리기 · 시그니처 · 게임 · 클립).
- [ ] 갈아탈 코드가 서버에 있다(`cd /opt/livemaster && git log --oneline -1` 이 main 끝과 같다). auto-deploy.sh 의 v2 단계
      (방송 중 409 면 기다림 · v2 꾸러미 · v2 다시 켜기)도 이 코드에 들어 있다 — **main 에 올린("올려") 뒤에야** 서버에 닿는다.
- [ ] 버전 되돌리기가 v2 도 다시 켜게 sudoers 줄(1번 끝) — `sudo -l -U livemaster | grep livemaster-v2` 가 나오면 된다.
- [ ] 백업 두 벌: `sudo cp /etc/caddy/Caddyfile /etc/caddy/Caddyfile.bak-before-switch` ·
      `sudo cp /etc/systemd/system/toon-listener.service /root/toon-listener.service.before-v2` ·
      `sudo -u livemaster cp /opt/livemaster/v2/data/lm2.db /opt/livemaster/v2/data/lm2.db.before-switch` (v2 를 멈춘 뒤에 — ① 안에서)

### ① 옛 장부 다시 옮기기 (3번과 같다 — 시험판 동안 옛 서버에 쌓인 후원 · 기억을 마저 가져온다)
```bash
sudo systemctl stop livemaster-v2                                       # 켜진 서버는 순위 제외 · 등급을 덮어쓴다
sudo -u livemaster cp /opt/livemaster/v2/data/lm2.db /opt/livemaster/v2/data/lm2.db.before-switch
cd /opt/livemaster && set -a && . /etc/livemaster.env && set +a
sudo -E -u livemaster .venv/bin/python -m v2.tools.import_old_db --v2-db v2/data/lm2.db          # ① 세어 보기만 — 숫자를 본다
sudo -E -u livemaster .venv/bin/python -m v2.tools.import_old_db --v2-db v2/data/lm2.db --write  # ② 진짜로
sudo systemctl start livemaster-v2
curl -s http://127.0.0.1:5300/api/health | head -c 200; echo                                     # {"ok":true …}
```
- [ ] 세어 본 숫자가 말이 된다(10-07 에 옮긴 것은 다시 안 들어간다 — id · tx_id · ref 로 거른다. 새로 쌓인 만큼만 늘어야 한다).
- [ ] v2 를 멈춘 동안 리스너는 아직 옛 서버로 보내고 있으니 후원은 안 잃는다.

### ② 옛 설정 옮기기
- [ ] 옛 조종실 **[💾 백업]** 으로 파일을 받는다 → v2 조종실 **[옛 설정 옮기기]** 에 넣는다(공지 · 계좌 · 목표 · 테마 · 게임 판 · 스위치 …).
- [ ] v2 조종실에서 공지 · 목표 · 테마가 옛 것과 같은지 눈으로.

### ③ 시험판 잠금 풀기 (LM2_TRIAL=1 지우기)
시험판 동안 v2 는 옛 것과 **같이 쓰는 것**(시그니처 보관소 · 리스너 설정 · 서버 버전 바꾸기)을 못 바꾸게 잠겨 있었다.
```bash
sudo cp /etc/systemd/system/livemaster-v2.service.d/trial.conf /root/trial.conf.before-switch
sudo rm /etc/systemd/system/livemaster-v2.service.d/trial.conf
sudo systemctl daemon-reload && sudo systemctl restart livemaster-v2
systemctl show livemaster-v2 -p Environment | grep -c LM2_TRIAL         # 0 이어야 한다
```

### ④ 리스너를 v2 로 (서비스 파일 **통째로** 바꾸기)
⚠️ 덧붙임 파일(`toon-listener.service.d/*.conf`)로는 옛 서버에 묶인 것(Requires=livemaster)을 **못 끊는다** — systemd 는 덧붙임에서
의존 목록을 비우지 않는다(빈 `Requires=` 는 그냥 무시). 그래서 v2 판 서비스 파일(`v2/deploy/toon-listener.service`)로 통째 바꾼다.
```bash
sudo rm -f /etc/systemd/system/toon-listener.service.d/v2.conf         # 10-07 에 깔았던 덧붙임이 있으면(효과 없음 — 착각 방지)
grep '^DONATION_URL' /etc/livemaster.env                                # 아무것도 안 나와야 한다(있으면 그 줄이 이긴다 → 지운다)
sudo cp /opt/livemaster/v2/deploy/toon-listener.service /etc/systemd/system/toon-listener.service
sudo systemctl daemon-reload && sudo systemctl restart toon-listener
systemctl show toon-listener -p Requires -p After | grep -c 'livemaster.service'   # 0 (옛 서버에 안 묶임)
journalctl -u toon-listener -n 30 --no-pager | grep 연결됨              # '→ http://127.0.0.1:5300/api/donation'
```
- [ ] 이 순간부터 진짜 후원이 v2 로 간다. 못 보낸 후원은 리스너가 파일(donation_spool.jsonl)에 적어 뒀다 10초마다 다시 보낸다.

### ⑤ 진행봇 바꾸기 — 옛 것 **먼저** 끄고 v2 켜기 (같이 켜면 채팅이 두 번씩 올라간다)
```bash
sudo cp /opt/livemaster/v2/deploy/livemaster-bot-v2.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl disable --now livemaster-bot
sudo systemctl enable --now livemaster-bot-v2 livemaster-v2-backup.timer
systemctl is-active livemaster-bot livemaster-bot-v2                    # inactive · active
journalctl -u livemaster-bot-v2 -n 20 --no-pager
```

### ⑥ 바깥 큰 주소(Caddy) 갈아타기 — 은행 확장 · 폰 앱 · 크루 사이트 · 옛 북마크를 그대로 두기 위해
은행 확장 · 폰 앱은 **포트 없는 큰 주소만** 허락하게 만들어져 있어서 :8443 으로 못 보낸다. 그래서 큰 주소 쪽 길잡이(Caddy)가
그 주소들만 v2 로 넘긴다 — 확장 · 폰 앱 · 크루 사이트 · 스트림덱 실물 단추는 **아무것도 안 바꿔도** 된다(`v2/deploy/Caddyfile.switch` 머리말).
```bash
python3 /opt/livemaster/v2/deploy/caddy_switch.py status /etc/caddy/Caddyfile                       # 큰 주소 ← 옛 상태
python3 /opt/livemaster/v2/deploy/caddy_switch.py apply /etc/caddy/Caddyfile /tmp/Caddyfile.new     # 원래 파일은 안 고친다
diff /etc/caddy/Caddyfile /tmp/Caddyfile.new | head -80                                            # 큰 주소 덩어리만 바뀌었나
sudo -u caddy -H caddy validate --config /tmp/Caddyfile.new --adapter caddyfile                    # ⚠️ root 로 돌리지 말 것(아래)
sudo install -m 644 /tmp/Caddyfile.new /etc/caddy/Caddyfile && sudo systemctl reload caddy
```
- ⚠️ **validate 를 root 로(`sudo caddy validate`) 돌리면** 아직 없던 기록 파일이 root 것으로 생겨 다음 reload 가 실패한다(10-07 겪음 — 2번).
  `sudo -u caddy -H` 로 돌린다. 이 조각은 옛 덩어리와 같은 기록 파일(livemaster.log)을 써서 새 기록 파일이 안 생긴다.
- ⚠️ angelcompany.me 홈페이지 · crew · :8443 덩어리는 도구가 한 글자도 안 바꾼다(바꾸기 전후를 맞대 보고 다르면 안 쓴다).
- ⚠️ 은행 입구(`/api/bank/*` · `/download/bankphone.apk`)는 v2 에 은행 갈래가 들어온 뒤에만 답한다 — 확인:
  `curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:5300/api/bank/app` 이 404 면 **이 단계를 미룬다**(확장 신호등이 빨강이 된다).
- [ ] 확인(PC 에서):
  `curl -sI https://엔젤컴퍼니.메인.한국/controller | grep -i '^location'` → `…:8443/controller/` ·
  `curl -s https://엔젤컴퍼니.메인.한국/api/signatures/board | head -c 120` → `{"status":"success","rows":[…` ·
  `curl -s https://엔젤컴퍼니.메인.한국/api/oraksil/donors | head -c 120` · 폰으로 `https://엔젤컴퍼니.메인.한국/privacy`

### ⑦ (권장) 옛 서버를 '구경만'(STANDBY) 으로
옛 서버는 되돌릴 길이라 끄지 않지만, 누가 옛 화면에서 단추를 눌러도 아무것도 안 바뀌게 한다(비상용 템퍼몽키 후원도 503).
⚠️ `/etc/livemaster.env` 의 `STANDBY=` 를 고치지 말 것 — v2 와 같이 읽는 파일이다. 옛 서버에만 붙는 덧붙임 + 따로 된 파일로:
```bash
echo 'STANDBY=1' | sudo tee /etc/livemaster-old.env >/dev/null
sudo mkdir -p /etc/systemd/system/livemaster.service.d
printf '[Service]\nEnvironmentFile=/etc/livemaster-old.env\n' | sudo tee /etc/systemd/system/livemaster.service.d/standby.conf >/dev/null
sudo systemctl daemon-reload && sudo systemctl restart livemaster
journalctl -u livemaster -n 30 --no-pager | grep -i standby
```
(덧붙임의 EnvironmentFile 은 /etc/livemaster.env **다음에** 읽혀서 그쪽이 이긴다 — `Environment=STANDBY=1` 은 env 파일의 빈 `STANDBY=` 에 진다.)
리스너는 ④ 에서 옛 서버와 떨어졌으니 옛 서버를 다시 켜도 후원이 안 끊긴다.

### ⑧ 방송 PC · 회사 PC · 스트림덱 (사람이 손으로)
- [ ] **OBS 방송판 소스** 주소 → `https://엔젤컴퍼니.메인.한국:8443/overlay/` (1080×1920). 클립을 쓰는 소스는 속성에서 **'고급 접근 권한'**(페이지 권한 → 고급) 을 켠다 —
      안 켜면 [✂ 클립] 이 OBS 리플레이를 못 저장한다. 옛 소스(알림창 · 전광판 · 슬롯 · 옛 방송판)는 **한 장면에 옛 것과 새 것을 같이 두지 않는다**(소리 · 팝업이 두 번).
- [ ] **조종실 북마크** → `https://엔젤컴퍼니.메인.한국:8443/controller/` (옛 주소로 열어도 ⑥ 덕분에 여기로 넘어온다). 폰 시그 관리 → `…:8443/mobile`.
- [ ] **회사 PC 클립 도우미**: 옛 도우미를 끄고, v2 조종실 → ✂️ 클립 탭 → **[⬇ 도우미 받기]** 로 v2 판을 받아 풀고 `start_clip_helper.bat` —
      v2 판은 서버 주소 · 읽기 열쇠가 박혀 있다(옛 도우미는 v2 목록을 못 읽는다).
- [ ] **스트림덱** 'Website' 단추 주소의 앞부분을 `https://엔젤컴퍼니.메인.한국:8443/api/streamdeck/…?token=…` 로(뒤 `?token=` 은 그대로 — 같은 열쇠).
      ⑥ 을 했으면 옛 주소도 v2 로 가지만, :8443 으로 바꿔 두면 ⑥ 을 되돌려도 v2 를 부른다. 가상 단추판은 `…:8443/streamdeck/`.
- [ ] **은행 확장 · 폰 앱은 그대로** — 주소를 바꾸지 않는다(⑥ 이 큰 주소에서 v2 로 넘긴다). 확장 신호등이 초록인지만 본다.
- [ ] 크루 사이트(crew.angelcompany.me)는 그대로 — 시그리스트 · 오락실 순위가 나오는지 한 번 열어 본다.

### ⑨ 마지막 확인 (방송 2시간 전까지)
- [ ] v2 조종실 점검 탭(🛫) 전부 초록 · 폰으로 `https://엔젤컴퍼니.메인.한국:8443/health` 초록.
- [ ] 후원 콘솔로 테스트 후원 한 번 → OBS 방송판에 팝업 · 장부 탭에 줄(테스트는 '화면에만' 으로).
- [ ] `systemctl is-active livemaster-v2 toon-listener livemaster-bot-v2 livemaster-watchdog.timer livemaster-v2-backup.timer caddy` → 전부 active.
- [ ] `systemctl is-active livemaster-bot` → inactive (옛 진행봇이 꺼져 있다).
- [ ] 백업 바깥 올리기(선택): 아래 '💾 장부 바깥 백업'.

## 6. 자동 배포 (auto-deploy.sh) — 10-17 v2 를 안다
- livemaster-v2 를 **켜 둔(enabled)** 서버에서만 더 돈다(아니면 예전과 똑같다 — 검사 `v2/tests/test_ops_autodeploy.py`):
  ① 새 커밋이 있을 때 v2 `GET /api/deploy/ok` 가 **409(방송 중)** 면 아무것도 안 건드리고 2분 뒤 다시 묻는다. v2 가 꺼져 답이 없으면 그대로 배포한다.
  ② `v2/requirements.txt` 가 바뀌었으면 v2 꾸러미를 깐다 ③ v2 · v2 진행봇을 **돌고 있을 때만** 다시 켠다(try-restart — ① 처럼 일부러 멈춘 v2 는 안 깨운다).
- 조종실 버전 고정(DEPLOY_PIN) 길은 비상 단추라 ① 을 안 본다.
- 서버를 처음부터 세울 때는 `sudo bash deploy/setup.sh --with-v2` — v2 서비스 · 백업 · 감시 · Caddy :8443 · sudoers 까지(안 붙이면 예전 그대로).

## 💾 장부 바깥 백업 (선택 — 기본 꺼짐)
서버 안 백업(`v2/data/backups/`, 14개)은 매일 저절로. 서버가 통째로 사라질 때를 위해 Supabase 보관소에도 올릴 수 있다.
1. **먼저** Supabase → Storage → New bucket → 이름 `backups` · **Public 끔(비공개)**. 장부에는 후원자 이름 · 메시지가 있다 —
   버킷이 없거나 공개면 도구가 **안 올리고** 실패로 끝낸다(서버 안 백업은 그래도 남는다).
2. `/etc/livemaster.env` 에 `LM2_BACKUP_UPLOAD=1` 한 줄(서비스 파일은 안 고친다 — 그 안의 기본값 0 을 env 파일이 이긴다).
3. 확인: `sudo systemctl start livemaster-v2-backup && journalctl -u livemaster-v2-backup -n 5 --no-pager` → '올렸습니다'.
끄기: 그 줄을 지우거나 0.

## 되돌리는 길 (언제든 — 갈아탄 순서의 **거꾸로**)
> 옛 서버는 그동안 계속 떠 있었으므로 바로 쓴다. 단 **v2 에서 받은 후원 · 점수는 옛 장부에 없다** — v2 장부 탭에서 보고 옛 조종실에 손으로 옮긴다.
> 방송 중이라도 되돌리기는 한다(그게 되돌리기의 쓸모다). 순서만 지킨다: 옛 서버 풀기 → 리스너 → 진행봇 → 주소 · 화면.

1. **옛 서버 STANDBY 풀기**(⑦ 을 했다면 — 먼저. '구경만' 인 옛 서버는 후원을 503 으로 돌려보낸다):
   `sudo rm /etc/systemd/system/livemaster.service.d/standby.conf && sudo systemctl daemon-reload && sudo systemctl restart livemaster`
2. **리스너를 옛 서버로** (후원이 어디로 가는지가 제일 중요)
   ```bash
   systemctl is-active livemaster                                        # active 여야 한다(아니면 sudo systemctl start livemaster)
   sudo cp /root/toon-listener.service.before-v2 /etc/systemd/system/toon-listener.service   # 백업이 없으면 /opt/livemaster/deploy/toon-listener.service
   sudo systemctl daemon-reload && sudo systemctl restart toon-listener
   journalctl -u toon-listener -n 20 --no-pager | grep 연결됨           # '→ http://127.0.0.1:8080/api/donation'
   ```
3. **진행봇**: `sudo systemctl disable --now livemaster-bot-v2 && sudo systemctl enable --now livemaster-bot` (v2 봇 **먼저** 끈다).
4. **Caddy 큰 주소**(⑥ 을 했다면):
   ```bash
   sudo cp /etc/caddy/Caddyfile.bak-before-switch /etc/caddy/Caddyfile && sudo systemctl reload caddy      # 가장 빠른 길
   # 백업이 없으면: python3 /opt/livemaster/v2/deploy/caddy_switch.py revert /etc/caddy/Caddyfile /tmp/Caddyfile.old
   #               sudo -u caddy -H caddy validate --config /tmp/Caddyfile.old --adapter caddyfile
   #               sudo install -m 644 /tmp/Caddyfile.old /etc/caddy/Caddyfile && sudo systemctl reload caddy
   ```
   은행 확장 · 폰 앱 · 크루 사이트는 다시 옛 서버를 부른다(주소는 그대로라 아무것도 안 바꿔도 된다). 302 는 브라우저가 오래 기억하지 않는다.
5. **OBS 소스 · 조종실 북마크 · 스트림덱** 을 옛 주소(:8443 을 뺀 것)로. 회사 PC 는 옛 클립 도우미를 다시 켠다.
6. (필요하면) **시험판 잠금 다시**: `sudo cp /root/trial.conf.before-switch /etc/systemd/system/livemaster-v2.service.d/trial.conf && sudo systemctl daemon-reload && sudo systemctl restart livemaster-v2`
7. (필요하면) **v2 장부를 옮기기 전으로**: v2 멈춤 → `lm2.db.before-switch` 를 `lm2.db` 로(아래 '백업 되살리기' 와 같은 식, -wal · -shm 지우기) → v2 켜기.
   v2 는 꺼도 된다(`sudo systemctl stop livemaster-v2`) — 리스너는 2 에서 이미 옛 서버로 갔다.

## 백업 되살리기
```bash
sudo systemctl stop livemaster-v2
cd /opt/livemaster/v2/data && sudo -u livemaster sh -c 'gunzip -c backups/lm2-YYYYMMDD-HHMM.db.gz > lm2.db.new && rm -f lm2.db-wal lm2.db-shm && mv lm2.db.new lm2.db'
sudo systemctl start livemaster-v2
```
