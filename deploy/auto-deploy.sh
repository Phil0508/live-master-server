#!/usr/bin/env bash
# 🔄 GitHub main 을 확인해 새 커밋이 있으면 자동으로 받아 재시작한다 (Render 의 자동배포처럼).
#    systemd 타이머(auto-deploy.timer)가 2분마다 이 스크립트를 부른다.
#    변경이 없으면 아무것도 하지 않고 조용히 끝낸다.
set -euo pipefail

APP_DIR=/opt/livemaster
APP_USER=livemaster
BRANCH=main
cd "$APP_DIR"

# git·pip 는 코드 주인(livemaster)으로 실행한다. root 로 하면 파일 소유권이 꼬여
# 다음 배포 때 'dubious ownership' 오류가 난다. 재시작만 root(이 서비스)로 한다.
run_as() { sudo -u "$APP_USER" "$@"; }

run_as git fetch --quiet origin "$BRANCH"
LOCAL=$(run_as git rev-parse HEAD)
REMOTE=$(run_as git rev-parse "origin/$BRANCH")
if [ "$LOCAL" = "$REMOTE" ]; then
  exit 0    # 변경 없음
fi

echo "🔄 새 커밋 감지: ${LOCAL:0:8} → ${REMOTE:0:8}"

# requirements.txt 가 바뀌었을 때만 pip 설치(매번 하면 느리다)
NEED_PIP=0
if ! run_as git diff --quiet "$LOCAL" "$REMOTE" -- requirements.txt; then
  NEED_PIP=1
fi

run_as git reset --hard --quiet "origin/$BRANCH"

if [ "$NEED_PIP" = "1" ]; then
  echo "   requirements.txt 변경 → 패키지 갱신"
  run_as "$APP_DIR/.venv/bin/pip" install --quiet -r "$APP_DIR/requirements.txt"
fi

systemctl restart livemaster
# 후원 리스너가 켜져 있으면 코드가 바뀌었을 수 있으니 같이 새로고침
if systemctl is-enabled --quiet toon-listener 2>/dev/null; then
  systemctl restart toon-listener
fi
echo "✅ 배포 완료: ${REMOTE:0:8}"
