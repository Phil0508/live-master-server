#!/usr/bin/env bash
# 🚀 우분투 서버(Vultr 서울 등) 위에 방송 서버를 한 번에 세운다.
#
#   sudo bash setup.sh
#
# 여러 번 돌려도 안전하다(이미 된 단계는 건너뛴다).
# 끝나고 나서 /etc/livemaster.env 에 비밀값을 채우고 서비스를 재시작하면 된다.
#
# 🆕 v2(10-17) 도 같이 세우려면 — 선택이다. 안 붙이면 예전과 똑같이 돈다(검사: v2/tests/test_ops_setup.py):
#   sudo bash setup.sh --with-v2        (또는 sudo WITH_V2=1 bash setup.sh)
#   → v2 꾸러미 · v2 서비스(127.0.0.1:5300) · 장부 백업 타이머 · 감시 장치 · Caddy :8443 · 방화벽 8443 ·
#     sudoers(조종실 버전 되돌리기가 v2 도 다시 켜게 — /etc/sudoers.d/livemaster-v2-restart, 옛 파일은 안 건드림).
#   v2 진행봇은 깔기만 한다(옛 진행봇과 같이 켜면 채팅이 두 번 올라간다). 리스너를 v2 로 돌리는 것은 갈아타는 날 —
#   v2/deploy/README.md '갈아타는 날'.

set -euo pipefail

REPO="https://github.com/Phil0508/live-master-server.git"
BRANCH="main"
APP_DIR="/opt/livemaster"
ENV_FILE="/etc/livemaster.env"
APP_USER="livemaster"
PORT="8080"
WITH_V2="${WITH_V2:-0}"
for arg in "$@"; do
  case "$arg" in
    --with-v2) WITH_V2=1 ;;
  esac
done

say() { printf '\n\033[1;36m▶ %s\033[0m\n' "$*"; }

[ "$(id -u)" -eq 0 ] || { echo "sudo 로 실행해주세요"; exit 1; }

say "1/7  패키지 설치"
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq git python3 python3-venv python3-pip curl debian-keyring debian-archive-keyring apt-transport-https

if ! command -v caddy >/dev/null; then
  say "     Caddy 설치 (HTTPS 자동 발급용)"
  curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' \
    | gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
  curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' \
    | tee /etc/apt/sources.list.d/caddy-stable.list >/dev/null
  apt-get update -qq && apt-get install -y -qq caddy
fi

say "2/7  전용 사용자"
id -u "$APP_USER" >/dev/null 2>&1 || useradd --system --create-home --shell /usr/sbin/nologin "$APP_USER"

say "3/7  코드 받기"
if [ -d "$APP_DIR/.git" ]; then
  git -C "$APP_DIR" fetch --quiet origin "$BRANCH"
  git -C "$APP_DIR" reset --hard --quiet "origin/$BRANCH"
else
  git clone --quiet --branch "$BRANCH" "$REPO" "$APP_DIR"
fi
chown -R "$APP_USER:$APP_USER" "$APP_DIR"

say "4/7  파이썬 환경"
[ -d "$APP_DIR/.venv" ] || python3 -m venv "$APP_DIR/.venv"
"$APP_DIR/.venv/bin/pip" install --quiet --upgrade pip
"$APP_DIR/.venv/bin/pip" install --quiet -r "$APP_DIR/requirements.txt"
chown -R "$APP_USER:$APP_USER" "$APP_DIR"

say "5/7  환경변수 파일"
if [ ! -f "$ENV_FILE" ]; then
  cat > "$ENV_FILE" <<'EOF'
# ⚠️ 비밀값이다. 이 파일은 저장소에 올리지 않는다.
#    채운 뒤:  sudo systemctl restart livemaster

HEADLESS=1
PORT=8080

# ⚠️ 반드시 127.0.0.1 로 둘 것. 앞단의 Caddy 가 HTTPS 를 받아 여기로 넘겨준다.
#    0.0.0.0 이면 8080 이 인터넷에 그대로 열려서, 암호화도 없고 Caddy 도 안 거치는
#    우회로가 생긴다(조종실 비밀번호·OTP 가 평문으로 오가고, 후원 주입도 가능해진다).
BIND_HOST=127.0.0.1

# Supabase (Render 대시보드의 live-master-server 환경변수에서 그대로 복사)
DATABASE_URL=
SUPABASE_URL=
SUPABASE_SECRET_KEY=

# 관리자 키 — 영문·숫자만(한글은 HTTP 헤더에 못 실어 Bearer 요청이 깨진다).
# 비워두면 저장소에 흔적이 남은 공개된 기본값이 쓰인다. 서버에서 만들려면:
#   openssl rand -hex 24
SESSION_SECRET=

# 조종실 로그인 비밀번호. ⚠️ 비워두면 기본값 '0508' 이 쓰인다(server.py:142).
# 인터넷에 열린 주소라 네 자리 숫자로 두면 안 된다.
ADMIN_PASSWORD=

# 2단계 인증(OTP)은 저장소의 auth_config.json 에서 온다. 여기 넣지 않아도 된다.
# 넣으면 그 값이 이기는데, 지금 쓰는 OTP 앱과 달라지면 로그인이 막히니 건드리지 말 것.
# TOTP_SECRET=

# 🔑 OTP 마스터 코드 — OTP 앱 없이 들어가기 위한 예비 열쇠.
#    여기에 넣은 값을 로그인 화면의 OTP 칸에 그대로 치면 통과한다.
#    ⚠️ 저장소는 공개라 코드에 적을 수 없어 환경변수로만 받는다. 비워두면 기능이 꺼진다.
#    ⚠️ 이 코드는 두 번째 자물쇠를 통째로 대신한다. 짧고 뻔한 값을 쓸수록
#       ADMIN_PASSWORD 하나에만 의지하게 되므로, 그 비밀번호를 길고 어렵게 둘 것.
#    사용되면 서버 로그에 'ip=' 와 함께 남는다(journalctl -u livemaster).
OTP_MASTER_CODE=

# OTP 칸을 비워두면 통과하는 지금 동작을 막는다. 1 로 켠다.
# ⚠️ 켜기 전에 OTP 앱이나 위 마스터 코드로 로그인이 되는지 반드시 먼저 확인할 것.
#    확인 없이 켜면 방송 직전에 조종실에 못 들어간다.
REQUIRE_OTP=

# AI 기입검증·오토파일럿용 (없으면 AI 기능만 조용히 꺼진다)
NVIDIA_API_KEY=

# 깨우기는 VPS 에선 필요 없다(항상 켜져 있으므로). 조종실 스위치도 막아둔다.
SELF_PING=off

# 🔒 후원 접수 잠금. /api/donation 은 이 서버 안(127.0.0.1)에서 오는 요청만 받는다.
#    투네이션 리스너가 여기서 돌기 때문에 평소엔 아무 설정이 필요 없다.
#    ⚠️ 크롬 템퍼몽키를 다시 쓰려면 여기에 아무 값이나 정하고,
#       유저스크립트의 headers 에 "X-Donation-Key": "그 값" 을 넣어야 한다.
#       비워두면 바깥에서 오는 후원은 전부 거절된다(가짜 후원 주입 차단).
DONATION_KEY=

# 🛰️ 대기 모드. 폴백 서버(예: Render)에만 1 로 켠다.
#    켜면 그 서버는 DB 에 쓰지 않고 상태를 바꾸는 요청도 받지 않는다.
#    ⚠️ 이걸 안 켜고 두 서버를 동시에 띄우면 서로의 후원·점수를 지운다.
#       실제로 방송 중에 두 서버가 어긋나 같은 시그니처가 두 번 재생된 적이 있다.
#    운영 서버가 죽어 넘겨받을 때는 이 값을 지우고 재시작한다.
STANDBY=

# 🎧 크롬 없이 후원 받기(toon-listener). 투네이션 알림창 주소를 넣으면
#    서버가 wss://ws.toon.at 에 직접 붙어 후원을 받는다. 비우면 리스너는 조용히 쉰다.
#    통합알림창 > 알림창 URL 의 그 주소(https://toon.at/widget/alertbox/....)
ALERTBOX_URL=
EOF
  chmod 600 "$ENV_FILE"
  echo "     만들었습니다 → $ENV_FILE (아직 비어 있습니다)"
else
  echo "     이미 있습니다 → $ENV_FILE (건드리지 않음)"
fi

say "6/7  서비스 등록"
install -m 644 "$APP_DIR/deploy/livemaster.service" /etc/systemd/system/livemaster.service
install -m 644 "$APP_DIR/deploy/Caddyfile" /etc/caddy/Caddyfile
mkdir -p /var/log/caddy && chown caddy:caddy /var/log/caddy
# 🎧 후원 리스너도 등록해 둔다. 다만 ALERTBOX_URL 이 채워졌을 때만 켠다
#    (안 채워졌는데 켜면 즉시 종료→재시작을 반복해 로그만 지저분해진다).
install -m 644 "$APP_DIR/deploy/toon-listener.service" /etc/systemd/system/toon-listener.service
# 🔄 자동 배포(2분마다 GitHub main 확인 → 갱신). Render 의 자동배포처럼.
install -m 644 "$APP_DIR/deploy/auto-deploy.service" /etc/systemd/system/auto-deploy.service
install -m 644 "$APP_DIR/deploy/auto-deploy.timer"   /etc/systemd/system/auto-deploy.timer
systemctl daemon-reload
systemctl enable --quiet livemaster caddy
systemctl enable --quiet --now auto-deploy.timer
echo "     자동 배포 켬 (2분마다 main 확인). 끄려면: systemctl disable --now auto-deploy.timer"
if grep -q '^ALERTBOX_URL=.\+' "$ENV_FILE"; then
  systemctl enable --quiet toon-listener
  echo "     후원 리스너 켬 (ALERTBOX_URL 있음)"
else
  systemctl disable --quiet toon-listener 2>/dev/null || true
  echo "     후원 리스너는 쉼 (ALERTBOX_URL 비어있음 - 나중에 켜려면 env 채우고 systemctl enable --now toon-listener)"
fi

say "7/7  방화벽"
# ⚠️ 업체마다 기본값이 정반대다. 오라클은 전부 막혀 있어 열어줘야 하고,
#    Vultr 는 전부 열려 있어 아래 ACCEPT 규칙이 사실상 아무 일도 하지 않는다.
#    그래서 '80/443 만 열었으니 안전하다'고 믿으면 안 된다 —
#    실제 보호는 BIND_HOST=127.0.0.1 로 앱을 밖에서 안 보이게 하는 쪽이 한다.
#    (Vultr 서울 서버에서 8080 이 인터넷에 응답하던 것을 그렇게 막았다)
iptables -C INPUT -p tcp --dport 80 -j ACCEPT 2>/dev/null || iptables -I INPUT 1 -p tcp --dport 80 -j ACCEPT
iptables -C INPUT -p tcp --dport 443 -j ACCEPT 2>/dev/null || iptables -I INPUT 1 -p tcp --dport 443 -j ACCEPT
if command -v netfilter-persistent >/dev/null; then
  netfilter-persistent save >/dev/null
else
  apt-get install -y -qq iptables-persistent >/dev/null 2>&1 || true
  netfilter-persistent save >/dev/null 2>&1 || true
fi

if [ "$WITH_V2" = "1" ]; then
  say "+    v2 (선택 — --with-v2)"
  if [ ! -f "$APP_DIR/v2/requirements.txt" ]; then
    echo "     ⚠️ 받은 코드에 v2 가 없습니다($APP_DIR/v2) — v2 단계는 건너뜁니다"
    WITH_V2=0
  else
    "$APP_DIR/.venv/bin/pip" install --quiet -r "$APP_DIR/v2/requirements.txt"
    mkdir -p "$APP_DIR/v2/data"
    chown -R "$APP_USER:$APP_USER" "$APP_DIR"
    for unit in livemaster-v2.service livemaster-v2-backup.service livemaster-v2-backup.timer \
                livemaster-watchdog.service livemaster-watchdog.timer livemaster-bot-v2.service; do
      install -m 644 "$APP_DIR/v2/deploy/$unit" "/etc/systemd/system/$unit"
    done
    systemctl daemon-reload
    # 켜 두기만(enable) — 비밀값을 채운 뒤 아래 안내대로 켠다. 감시 장치를 지금 켜면 비밀값 없는 서버를 다시 켜려 든다.
    systemctl enable --quiet livemaster-v2 livemaster-v2-backup.timer livemaster-watchdog.timer
    echo "     v2 서비스 · 백업 타이머 · 감시 장치 등록(진행봇 v2 는 깔기만 — 갈아타는 날 켠다)"

    # 🌐 Caddy :8443 — 6/7 에서 깐 Caddyfile 끝에 v2 덩어리를 붙인다(이미 있으면 그대로)
    if ! grep -q ':8443 {' /etc/caddy/Caddyfile; then
      { echo; cat "$APP_DIR/v2/deploy/Caddyfile.v2"; } >> /etc/caddy/Caddyfile
      echo "     Caddy 에 :8443 덩어리 붙임"
    fi
    # ⚠️ 기록 파일을 caddy 것으로 먼저 만든다 — 'caddy validate' 를 root 로 돌리면 이 파일이 root 것으로 생겨
    #    reload 가 실패한다(10-07 겪음). 확인은 sudo -u caddy -H caddy validate … 로.
    touch /var/log/caddy/livemaster-v2.log
    chown caddy:caddy /var/log/caddy/livemaster-v2.log
    iptables -C INPUT -p tcp --dport 8443 -j ACCEPT 2>/dev/null || iptables -I INPUT 1 -p tcp --dport 8443 -j ACCEPT
    netfilter-persistent save >/dev/null 2>&1 || true

    # 🕹️ 조종실 버전 되돌리기가 v2 · v2 진행봇 · 리스너를 다시 켤 수 있게 — 그 재시작만 허락한다.
    #    옛 /etc/sudoers.d/livemaster-restart 는 안 건드린다. 문법이 틀리면 깔지 않는다(sudo 전체가 막히는 사고 방지).
    SUDOERS_TMP=$(mktemp)
    cat > "$SUDOERS_TMP" <<'SUDOERS'
livemaster ALL=(root) NOPASSWD: /usr/bin/systemctl restart livemaster-v2, \
                                /usr/bin/systemctl restart livemaster-bot-v2, \
                                /usr/bin/systemctl restart toon-listener, \
                                /bin/systemctl restart livemaster-v2, \
                                /bin/systemctl restart livemaster-bot-v2, \
                                /bin/systemctl restart toon-listener
SUDOERS
    if visudo -cqf "$SUDOERS_TMP"; then
      install -m 440 "$SUDOERS_TMP" /etc/sudoers.d/livemaster-v2-restart
      echo "     sudoers 줄 넣음 → /etc/sudoers.d/livemaster-v2-restart"
    else
      echo "     ⚠️ sudoers 문법 확인 실패 — 넣지 않았습니다(버전 되돌리기 뒤에는 sudo systemctl restart livemaster-v2 를 손으로)"
    fi
    rm -f "$SUDOERS_TMP"
  fi
fi

cat <<EOF

────────────────────────────────────────────────────────────
설치는 끝났습니다. 남은 것 세 가지:

  1) 비밀값 채우기      sudo nano $ENV_FILE
  2) 서버 켜기          sudo systemctl restart livemaster caddy
  3) 확인               curl -s localhost:$PORT/api/ping
                        sudo journalctl -u livemaster -n 30 --no-pager

⚠️ 업체 콘솔에 방화벽 그룹을 따로 걸어뒀다면 거기서도 80/443 을 열어야
   바깥에서 접속됩니다. 이건 서버 안에서 할 수 없습니다.
   (Vultr 는 방화벽 그룹을 지정하지 않았다면 그냥 열려 있습니다)
────────────────────────────────────────────────────────────
EOF
if [ "$WITH_V2" = "1" ]; then
  cat <<EOF
🆕 v2 도 깔았습니다. 비밀값을 채운 뒤:
  4) v2 켜기            sudo systemctl restart livemaster-v2
                        sudo systemctl start livemaster-v2-backup.timer livemaster-watchdog.timer
  5) 확인               curl -s 127.0.0.1:5300/api/health | head -c 300
                        sudo -u caddy -H caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile
                        sudo systemctl reload caddy
                        폰으로 https://엔젤컴퍼니.메인.한국:8443/health
  ⚠️ 업체 콘솔에 방화벽 그룹이 있으면 거기서 8443 도 열어야 합니다.
  리스너 · 진행봇을 v2 로 돌리는 것은 갈아타는 날 — v2/deploy/README.md '갈아타는 날'.
────────────────────────────────────────────────────────────
EOF
fi
