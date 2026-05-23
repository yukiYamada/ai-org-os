#!/usr/bin/env bash
#
# kill-mind.sh — Mind を破棄する（Mindspace ごと消す）
#
# 用法:
#   ./runtime/pillars/lifecycle/kill-mind.sh <mind-name>
#
# 例:
#   ./runtime/pillars/lifecycle/kill-mind.sh my-first-mind
#
# Axiom との関係:
#   - 思考が消えれば Mindspace も消える（不可侵原則の系として）
#   - 共有が必要だったものは Dispatch 経由で他 Mind に渡されていたはず
#   - 破棄後の復元は仕組みとして提供しない（不可逆）
#
# Phase 1 の仕様:
#   - Warden の 3 段階プロセス（要求→承認→実行）の「実行」相当のみ簡略実装
#   - Phase 2 以降は Warden を経由する
#
set -euo pipefail

if [ "$#" -ne 1 ]; then
  echo "Usage: $0 <mind-name>" >&2
  echo "Example: $0 my-first-mind" >&2
  exit 1
fi

MIND_NAME="$1"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# Phase 5a-2: 本スクリプトは runtime/pillars/lifecycle/ 配下。runtime/minds/ は
# RUNTIME_DIR 経由で参照する。
RUNTIME_DIR="$(cd "${SCRIPT_DIR}/../.." && pwd)"
MIND_DIR="${RUNTIME_DIR}/minds/${MIND_NAME}"

if [ ! -d "${MIND_DIR}" ]; then
  echo "[ERROR] Mind '${MIND_NAME}' does not exist (looked for ${MIND_DIR})" >&2
  echo "[HINT] List existing Minds: ${SCRIPT_DIR}/list-minds.sh" >&2
  exit 2
fi

# Phase 5a-2 / ADR-0010: 外側ループが動いていれば先に停止する。
# pid file に書かれた PID に SIGTERM を送り、最大 5 秒待ってから SIGKILL に上げる。
# pid file が無いか、PID が既に死んでいれば skip。
PID_FILE="${MIND_DIR}/.mind-loop.pid"
if [ -f "${PID_FILE}" ]; then
  LOOP_PID="$(cat "${PID_FILE}" 2>/dev/null || echo "")"
  if [ -n "${LOOP_PID}" ] && kill -0 "${LOOP_PID}" 2>/dev/null; then
    echo "[kill-mind] Stopping mind-loop (pid ${LOOP_PID})"
    kill -TERM "${LOOP_PID}" 2>/dev/null || true
    # graceful 終了を待つ
    WAITED=0
    while [ "${WAITED}" -lt 5 ]; do
      if ! kill -0 "${LOOP_PID}" 2>/dev/null; then
        break
      fi
      sleep 1
      WAITED=$((WAITED + 1))
    done
    if kill -0 "${LOOP_PID}" 2>/dev/null; then
      echo "[kill-mind] Loop did not stop in 5s, sending SIGKILL"
      kill -KILL "${LOOP_PID}" 2>/dev/null || true
    fi
  fi
fi

echo "[kill-mind] Destroying Mind '${MIND_NAME}' (Mindspace at ${MIND_DIR})"
rm -rf "${MIND_DIR}"
echo "[kill-mind] Mind '${MIND_NAME}' is gone. Its Mindspace is irrecoverable."
