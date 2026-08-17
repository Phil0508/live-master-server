#!/usr/bin/env bash
# 🚀 오라클 클라우드(우분투) 위에 방송 서버를 한 번에 세운다.
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

# 관리자 키 — 영문·숫자만. 비워두면 공개된 기본값이 쓰여 위험하다.
SESSION_SECRET=

# AI 기입검증·오토파일럿용 (없으면 AI 기능만 조용히 꺼진다)
NVIDIA_API_KEY=

# 깨우기는 오라클에선 필요 없다(항상 켜져 있으므로). 조종실 스위치도 막아둔다.
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

say "7/7  방화벽 열기 (오라클 우분투는 기본이 전부 막혀 있다)"
# ⚠️ 여기서 막혀서 '분명 서버는 떴는데 접속이 안 되는' 상황이 제일 흔하다.
#    오라클 콘솔의 VCN 보안 목록에서도 80/443 을 따로 열어야 한다(이 스크립트로는 불가).
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

⚠️ 오라클 콘솔에서 VCN 보안 목록에 80/443 인그레스 규칙을 추가해야
   바깥에서 접속됩니다. 이건 서버 안에서 할 수 없습니다.
────────────────────────────────────────────────────────────
EOF
