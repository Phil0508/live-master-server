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
| 리스너 | `toon-listener` → 8080 | 같은 리스너, 갈아타는 날 `toon-listener.service.d/v2.conf` 로 5300 에 보낸다 |

## 0. 지금 상태 (10-07 아침 시험판으로 올림)
- `livemaster-v2` 켜짐(127.0.0.1:5300) · 덧붙임 `/etc/systemd/system/livemaster-v2.service.d/trial.conf` = **LM2_TRIAL=1**(시그니처 보관소 · 리스너 설정 · 서버 버전 바꾸기 잠금).
- Caddy :8443 열림(백업 `/etc/caddy/Caddyfile.bak-before-v2`) · 옛 장부 옮김(후원 1377 · 기억 688 · 별명 393 · 순위 제외 6) · 백업 타이머 켜짐.
- 리스너 · 진행봇은 아직 옛 서버 쪽 — v2 에는 진짜 후원이 안 온다(후원 콘솔로 시험).
- ⚠️ 자동 배포(auto-deploy)는 v2 를 다시 켜지 않는다 — v2 코드를 올린 뒤엔 `sudo systemctl restart livemaster-v2`.

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
- 버전 되돌리기가 v2 도 재시작하도록 sudoers 에 줄을 더한다(옛 `deploy/README.md` 의 `livemaster-restart` 파일):
  `/usr/bin/systemctl restart livemaster-v2, /usr/bin/systemctl restart livemaster-bot-v2` (+ `/bin/systemctl …` 같은 두 줄) → `sudo visudo -c`

## 2. 바깥 주소 열기 (허락 필요: Caddy · 방화벽)

```bash
sudo cp /etc/caddy/Caddyfile /etc/caddy/Caddyfile.bak-before-v2
sudo sh -c 'cat /opt/livemaster/v2/deploy/Caddyfile.v2 >> /etc/caddy/Caddyfile'
sudo caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile
sudo chown caddy:caddy /var/log/caddy/livemaster-v2.log      # ⚠️ validate 를 root 로 돌리면 기록 파일이 root 것으로 생겨 reload 가 실패한다(10-07 겪음 — 옛 설정은 그대로 돌아 방송 주소는 멀쩡했다)
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

## 5. 갈아타는 날 (방송 시작 2시간 전까지 끝낸다)

```bash
sudo mkdir -p /etc/systemd/system/toon-listener.service.d
sudo cp /opt/livemaster/v2/deploy/toon-listener.service.d/v2.conf /etc/systemd/system/toon-listener.service.d/
sudo cp /opt/livemaster/v2/deploy/livemaster-bot-v2.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl disable --now livemaster-bot            # 옛 봇 먼저 끈다(두 번 말하지 않게)
sudo systemctl restart toon-listener                   # 이제 후원이 v2 로 간다
sudo systemctl enable --now livemaster-bot-v2 livemaster-v2-backup.timer
journalctl -u toon-listener -n 20                      # 'connected' · v2 로 보냄 확인
```
- OBS 방송판 소스 주소를 `:8443/overlay/` 로, 조종실 북마크를 `:8443/controller/` 로.
- 자동 배포가 v2 도 다시 켜게 `deploy/auto-deploy.sh` 의 곁다리 목록에 `livemaster-v2 livemaster-bot-v2` 를 더하고,
  `v2/requirements.txt` 가 바뀌면 pip 를 돌리게 한다(아래 6). 이 고침은 **main 에 push 해야** 서버에 닿는다 — "올려" 때만.

## 6. auto-deploy.sh 에 더할 것 (갈아타는 날 같이 올린다)

```bash
# requirements 확인 줄 옆에
if ! run_as git diff --quiet "$LOCAL" "$REMOTE" -- v2/requirements.txt; then NEED_PIP_V2=1; fi
# pip 줄 옆에
[ "${NEED_PIP_V2:-0}" = "1" ] && run_as "$APP_DIR/.venv/bin/pip" install --quiet -r "$APP_DIR/v2/requirements.txt"
# 곁다리 서비스 목록 두 군데(고정 버전 · 새 커밋)
for svc in toon-listener livemaster-bot livemaster-v2 livemaster-bot-v2; do
```
- 배포 잠금: v2 는 방송 중 `GET /api/deploy/ok` 가 409 를 준다. auto-deploy 가 그걸 보고 기다리게 하려면 `git fetch` 앞에
  `curl -sf http://127.0.0.1:5300/api/deploy/ok >/dev/null || { echo '방송 중 — 다음에'; exit 0; }` (v2 가 꺼져 있으면 curl 이 실패해 배포가 멈추므로 `systemctl is-active --quiet livemaster-v2 &&` 로 감쌀 것).

## 되돌리기 (언제든)

```bash
sudo rm /etc/systemd/system/toon-listener.service.d/v2.conf
sudo systemctl daemon-reload && sudo systemctl restart toon-listener
sudo systemctl disable --now livemaster-bot-v2 && sudo systemctl enable --now livemaster-bot
```
OBS · 조종실 주소를 옛 것(:8443 을 뺀 것)으로. 옛 서버는 그동안 계속 떠 있었으므로 바로 쓴다
(단, v2 에서 받은 후원 · 점수는 옛 장부에 없다 — v2 장부 탭에서 보고 손으로 옮긴다).

## 백업 되살리기
```bash
sudo systemctl stop livemaster-v2
cd /opt/livemaster/v2/data && sudo -u livemaster sh -c 'gunzip -c backups/lm2-YYYYMMDD-HHMM.db.gz > lm2.db.new && rm -f lm2.db-wal lm2.db-shm && mv lm2.db.new lm2.db'
sudo systemctl start livemaster-v2
```
