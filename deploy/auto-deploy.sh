#!/usr/bin/env bash
# 🔄 GitHub main 을 확인해 새 커밋이 있으면 자동으로 받아 재시작한다 (Render 의 자동배포처럼).
#    systemd 타이머(auto-deploy.timer)가 2분마다 이 스크립트를 부른다.
#    변경이 없으면 아무것도 하지 않고 조용히 끝낸다.
#
# 🆕 v2(10-17) — livemaster-v2 를 켜 둔(enabled) 서버에서만 아래 셋이 더 돈다. 없으면 예전과 똑같다.
#    ① 방송 중이면 기다린다: 새 커밋이 있을 때 v2 에 GET /api/deploy/ok 를 묻고, **409 면** 이번엔 안 올린다(2분 뒤 다시 묻는다).
#       409 가 아닌 답 · 못 닿음(v2 가 꺼짐)은 그대로 올린다 — v2 가 죽었다고 옛 서버 배포까지 막히면 안 된다.
#    ② v2/requirements.txt 가 바뀌었으면 v2 꾸러미를 깐다(옛 서비스를 다 다시 켠 뒤에 — 옛 순서는 그대로).
#    ③ 그다음 v2 · v2 진행봇을 다시 켠다 — **돌고 있을 때만**(try-restart). 일부러 멈춰 둔 v2(옛 장부 옮기는 중)를
#       깨우지 않는다. 죽은 v2 는 감시 장치(livemaster-watchdog)가 켠다.
#    검사: v2/tests/test_ops_autodeploy.py — 가짜 systemctl · git · curl 로 이 파일과 옛 판(ops_fixtures)을 나란히 돌린다.
set -euo pipefail

APP_DIR=/opt/livemaster
APP_USER=livemaster
BRANCH=main
cd "$APP_DIR"

# git·pip 는 코드 주인(livemaster)으로 실행한다. root 로 하면 파일 소유권이 꼬여
# 다음 배포 때 'dubious ownership' 오류가 난다. 재시작만 root(이 서비스)로 한다.
run_as() { sudo -u "$APP_USER" "$@"; }

# 🆕 v2 를 켜 둔 서버인가 — 한 번만 묻는다. 아니면 아래 v2 단계는 전부 건너뛴다.
V2_UNIT=livemaster-v2
V2_BOT_UNIT=livemaster-bot-v2
V2_OK_URL=http://127.0.0.1:5300/api/deploy/ok
HAS_V2=0
if systemctl is-enabled --quiet "$V2_UNIT" 2>/dev/null; then
  HAS_V2=1
fi

# 🆕 v2 · v2 진행봇 다시 켜기 — 돌고 있을 때만(try-restart). 실패해도 옛 배포는 이미 끝났으니 알리기만 한다.
restart_v2() {
  [ "$HAS_V2" = "1" ] || return 0
  if [ ! -f "$APP_DIR/v2/server/app.py" ]; then
    echo "⚠️ 이 버전에는 v2 가 없어 v2 는 다시 켜지 않습니다"
    return 0
  fi
  systemctl try-restart "$V2_UNIT" || echo "⚠️ v2 다시 켜기 실패 — journalctl -u $V2_UNIT 확인"
  if systemctl is-enabled --quiet "$V2_BOT_UNIT" 2>/dev/null; then
    systemctl try-restart "$V2_BOT_UNIT" || echo "⚠️ v2 진행봇 다시 켜기 실패 — journalctl -u $V2_BOT_UNIT 확인"
  fi
}

# 🕹️ 조종실에서 버전을 고정해 뒀으면 main 을 따라가지 않는다.
#    (이 확인이 없으면, 방송 중에 되돌린 버전이 2분 만에 최신으로 도로 올라간다)
#    조종실이 스스로 재시작하지 못했을 때를 대비해, 아직 안 옮겨져 있으면 여기서 맞춰준다.
#    ⚠️ 여기는 배포 잠금(①)을 안 본다 — 버전 되돌리기는 방송 중에 쓰는 비상 단추다.
PIN_FILE="$APP_DIR/DEPLOY_PIN"
if [ -s "$PIN_FILE" ]; then
  PINNED=$(tr -d "[:space:]" < "$PIN_FILE")
  if [ -n "$PINNED" ]; then
    CURRENT=$(run_as git rev-parse HEAD)
    if [ "$CURRENT" != "$PINNED" ]; then
      echo "📌 고정된 버전으로 맞춥니다: ${PINNED:0:8}"
      run_as git fetch --quiet origin "$BRANCH" || true
      if run_as git checkout --quiet --detach "$PINNED"; then
        systemctl restart livemaster
        for svc in toon-listener livemaster-bot; do
          if systemctl is-enabled --quiet "$svc" 2>/dev/null; then
            systemctl restart "$svc"
          fi
        done
        restart_v2
        echo "✅ 고정 버전 적용: ${PINNED:0:8}"
      else
        echo "⚠️ 고정된 버전으로 옮기지 못했습니다: ${PINNED:0:8}"
      fi
    fi
    exit 0
  fi
fi

run_as git fetch --quiet origin "$BRANCH"
LOCAL=$(run_as git rev-parse HEAD)
REMOTE=$(run_as git rev-parse "origin/$BRANCH")
if [ "$LOCAL" = "$REMOTE" ]; then
  exit 0    # 변경 없음
fi

# 🆕 ① 방송 중이면 이번엔 안 올린다 — v2 가 409 로 답할 때만. 파일 · 서비스는 하나도 안 건드리고 끝낸다.
if [ "$HAS_V2" = "1" ] && command -v curl >/dev/null 2>&1; then
  V2_OK_CODE=$(curl -s -o /dev/null -w '%{http_code}' --max-time 5 "$V2_OK_URL" || true)
  if [ "$V2_OK_CODE" = "409" ]; then
    echo "⏸️ 방송 중이라 배포를 미룹니다: ${LOCAL:0:8} → ${REMOTE:0:8} (방송이 끝나면 다음 확인 때 올라갑니다)"
    exit 0
  fi
fi

echo "🔄 새 커밋 감지: ${LOCAL:0:8} → ${REMOTE:0:8}"

# requirements.txt 가 바뀌었을 때만 pip 설치(매번 하면 느리다)
NEED_PIP=0
if ! run_as git diff --quiet "$LOCAL" "$REMOTE" -- requirements.txt; then
  NEED_PIP=1
fi
# 🆕 ② v2 꾸러미도 같은 식으로(v2 를 켜 둔 서버만)
NEED_PIP_V2=0
if [ "$HAS_V2" = "1" ] && ! run_as git diff --quiet "$LOCAL" "$REMOTE" -- v2/requirements.txt; then
  NEED_PIP_V2=1
fi

# HEAD 가 떨어져 있을 수 있다(고정을 쓰다 풀었을 때) — 갈래로 확실히 되돌린다
run_as git checkout --quiet -B "$BRANCH" "origin/$BRANCH"
run_as git reset --hard --quiet "origin/$BRANCH"

if [ "$NEED_PIP" = "1" ]; then
  echo "   requirements.txt 변경 → 패키지 갱신"
  run_as "$APP_DIR/.venv/bin/pip" install --quiet -r "$APP_DIR/requirements.txt"
fi

systemctl restart livemaster
# 곁다리 서비스들도 코드가 바뀌었을 수 있으니 같이 새로고침.
# ⚠️ 켜 두지 않은 것은 건드리지 않는다(is-enabled 로 확인) — 안 쓰는 서비스를
#    배포 때마다 깨우면 로그만 지저분해진다.
for svc in toon-listener livemaster-bot; do
  if systemctl is-enabled --quiet "$svc" 2>/dev/null; then
    systemctl restart "$svc"
  fi
done

# 🆕 ② · ③ v2 — 꾸러미를 못 깔았으면 v2 는 다시 켜지 않는다(새 코드가 없는 부품을 찾다 죽기보다 옛 코드로 도는 게 낫다)
if [ "$NEED_PIP_V2" = "1" ]; then
  echo "   v2/requirements.txt 변경 → v2 패키지 갱신"
  if run_as "$APP_DIR/.venv/bin/pip" install --quiet -r "$APP_DIR/v2/requirements.txt"; then
    restart_v2
  else
    echo "⚠️ v2 패키지 설치 실패 — v2 는 다시 켜지 않았습니다(옛 코드로 계속 돕니다)."
    echo "   손으로: sudo -u $APP_USER $APP_DIR/.venv/bin/pip install -r $APP_DIR/v2/requirements.txt && sudo systemctl restart $V2_UNIT"
  fi
else
  restart_v2
fi
echo "✅ 배포 완료: ${REMOTE:0:8}"
