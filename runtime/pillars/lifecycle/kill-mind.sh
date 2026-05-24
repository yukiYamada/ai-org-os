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
# Phase 5b-4 (#81 / ADR-0018): Mindspace は $AI_ORG_OS_HOME/minds/ 配下。
RUNTIME_DIR="$(cd "${SCRIPT_DIR}/../.." && pwd)"
DEFAULT_RUNTIME_HOME="${HOME:-${USERPROFILE:-}}/.ai-org-os"
RUNTIME_HOME="${AI_ORG_OS_HOME:-${DEFAULT_RUNTIME_HOME}}"
MIND_DIR="${RUNTIME_HOME}/minds/${MIND_NAME}"

if [ ! -d "${MIND_DIR}" ]; then
  echo "[ERROR] Mind '${MIND_NAME}' does not exist (looked for ${MIND_DIR})" >&2
  echo "[HINT] List existing Minds: ${SCRIPT_DIR}/list-minds.sh" >&2
  exit 2
fi

# Phase 5a-2 / ADR-0010: 外側ループが動いていれば先に停止する。
#
# Codex P1 PR #61 (1st): PID 検証なしで kill すると、再利用された PID を持つ
# 無関係なプロセスを殺してしまう可能性がある。
#
# Codex P1 PR #61 (2nd): mind_name を grep -E の regex に直接埋め込むと、
# valid name に含まれる `.` がワイルドカードになる（abc.def が abcXdef にマッチ）。
# 修正方針: regex を捨て、/proc/<pid>/cmdline の argv token を NUL 区切りで読み、
# exact string 一致で判定する（"mind-loop.sh" を末尾に持つ argv と、mind_name と
# 完全一致する argv の両方が存在することを確認）。
#
# /proc が無い環境（macOS/Windows の一部）では best-effort で kill するが警告する。
verify_loop_owner() {
  local pid="$1"
  local mind_name="$2"
  if [ ! -r "/proc/${pid}/cmdline" ]; then
    echo "[kill-mind] WARNING: /proc not available, cannot verify pid ${pid} identity (best-effort kill)" >&2
    return 0
  fi
  local has_script=0 has_mind=0 arg
  while IFS= read -r -d '' arg; do
    case "${arg}" in
      mind-loop.sh|*/mind-loop.sh) has_script=1 ;;
    esac
    if [ "${arg}" = "${mind_name}" ]; then
      has_mind=1
    fi
  done < "/proc/${pid}/cmdline"
  if [ "${has_script}" -eq 1 ] && [ "${has_mind}" -eq 1 ]; then
    return 0
  fi
  return 1
}

PID_FILE="${MIND_DIR}/.mind-loop.pid"
if [ -f "${PID_FILE}" ]; then
  LOOP_PID="$(cat "${PID_FILE}" 2>/dev/null || echo "")"
  if [ -n "${LOOP_PID}" ] && kill -0 "${LOOP_PID}" 2>/dev/null; then
    if ! verify_loop_owner "${LOOP_PID}" "${MIND_NAME}"; then
      echo "[kill-mind] WARNING: pid ${LOOP_PID} is alive but does not look like a mind-loop for '${MIND_NAME}'" >&2
      echo "[kill-mind] Skipping kill to avoid harming an unrelated process. Mindspace will still be removed." >&2
    else
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
        # 念のため SIGKILL 前にもう一度検証
        if verify_loop_owner "${LOOP_PID}" "${MIND_NAME}"; then
          kill -KILL "${LOOP_PID}" 2>/dev/null || true
        else
          echo "[kill-mind] WARNING: pid ${LOOP_PID} no longer looks like our loop; skipping SIGKILL" >&2
        fi
      fi
    fi
  fi
fi

echo "[kill-mind] Destroying Mind '${MIND_NAME}' (Mindspace at ${MIND_DIR})"
rm -rf "${MIND_DIR}"
echo "[kill-mind] Mind '${MIND_NAME}' is gone. Its Mindspace is irrecoverable."
