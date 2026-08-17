#!/usr/bin/env bash
# 🚀 우분투 서버(Vultr 서울 등) 위에 방송 서버를 한 번에 세운다.
#
#   sudo bash setup.sh
#
# 여러 번 돌려도 안전하다(이미 된 단계는 건너뛴다).
# 끝나고 나서 /etc/livemaster.env 에 비밀값을 채우고 서비스를 재시작하면 된다.

set -euo pipefail

REPO="https://github.com/Phil0508/live-master-server.git"
BRANCH="main"
APP_DIR="/opt/livemaster"
ENV_FILE="/etc/livemaster.env"
APP_USER="livemaster"
PORT="8080"

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

# AI 기입검증·오토파일럿용 (없으면 AI 기능만 조용히 꺼진다)
NVIDIA_API_KEY=

# 깨우기는 VPS 에선 필요 없다(항상 켜져 있으므로). 조종실 스위치도 막아둔다.
SELF_PING=off
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
systemctl daemon-reload
systemctl enable --quiet livemaster caddy

say "7/7  방화벽 열기"
# Vultr 기본 이미지는 막혀 있지 않아 사실상 확인만 하고 지나간다(여러 번 돌려도 안전).
# ⚠️ 업체 콘솔에 별도 방화벽(오라클 VCN, Vultr Firewall Group 등)을 걸어뒀다면
#    거기서도 80/443 을 열어야 한다. 이 스크립트는 서버 안쪽만 건드린다.
iptables -C INPUT -p tcp --dport 80 -j ACCEPT 2>/dev/null || iptables -I INPUT 1 -p tcp --dport 80 -j ACCEPT
iptables -C INPUT -p tcp --dport 443 -j ACCEPT 2>/dev/null || iptables -I INPUT 1 -p tcp --dport 443 -j ACCEPT
if command -v netfilter-persistent >/dev/null; then
  netfilter-persistent save >/dev/null
else
  apt-get install -y -qq iptables-persistent >/dev/null 2>&1 || true
  netfilter-persistent save >/dev/null 2>&1 || true
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
