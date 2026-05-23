#!/usr/bin/env bash
#
# mind-loop.sh — Mind の外側ループ（event-aware self-driven loop）
#
# ADR-0010 で確定した「Mind の能動性 = 外側ループ」の最小実装。
# 1 cycle = `claude -p "<assembled prompt>"` を 1 回呼び、結果を Mindspace
# 内のログに追記する。次の cycle までは sleep する。
#
# 用法:
#   ./runtime/pillars/lifecycle/mind-loop.sh <mind-name> [--period SECONDS] [--max-cycles N]
#
# 環境変数:
#   AI_ORG_OS_CLAUDE_BIN   `claude` の代わりに呼ぶバイナリ（テスト時の差し替え用）
#   AI_ORG_OS_LOOP_PERIOD  デフォルト周期（秒）。指定なしで 30 秒
#   AI_ORG_OS_LOOP_MAX_CYCLES  この回数で自然停止（デフォルト 0 = 無限）
#
# 停止方法:
#   - kill-mind.sh が SIGTERM を送る → ループは 1 cycle を完走して終了
#   - Ctrl-C（SIGINT）でも同様
#
# Mindspace に書き込むもの:
#   - .mind-loop.pid    プロセス PID（kill-mind.sh が参照、起動中のみ存在）
#   - mind-loop.log     各 cycle の開始時刻 / 終了時刻 / claude exit code
#
# ADR-0010 §3 との関係:
#   - 「Mind に idle 状態はない」= ループが回り続ける限り Mind は active。
#   - 停止 = ループが止まる = Mind が死ぬ（巻き戻しなし、ADR-0013 §4 と整合）。
#
set -uo pipefail

# ----- 引数とオプション -----

if [ "$#" -lt 1 ]; then
  echo "Usage: $0 <mind-name> [--period SECONDS]" >&2
  exit 1
fi

MIND_NAME="$1"
shift

# MIND_NAME のバリデーション。
# spawn-mind.sh の _VALID_NAME_RE と同じ規則。
# 緩めるとパス traversal (../escape) で任意ディレクトリに PID file / log を書ける。
# Codex P2 PR #27 で spawn-mind.sh に入れた validate_arg と整合させる。
_VALID_NAME_RE='^[A-Za-z0-9._-]{1,64}$'
if [[ ! "${MIND_NAME}" =~ ${_VALID_NAME_RE} ]]; then
  echo "[ERROR] Invalid mind-name: '${MIND_NAME}'" >&2
  echo "[HINT] Must match ${_VALID_NAME_RE} (no quotes, backslashes, spaces, path separators)" >&2
  exit 6
fi

PERIOD="${AI_ORG_OS_LOOP_PERIOD:-30}"
MAX_CYCLES="${AI_ORG_OS_LOOP_MAX_CYCLES:-0}"

while [ "$#" -gt 0 ]; do
  case "$1" in
    --period)
      shift
      if [ "$#" -lt 1 ]; then echo "[ERROR] --period requires an argument" >&2; exit 1; fi
      PERIOD="$1"
      shift
      ;;
    --max-cycles)
      shift
      if [ "$#" -lt 1 ]; then echo "[ERROR] --max-cycles requires an argument" >&2; exit 1; fi
      MAX_CYCLES="$1"
      shift
      ;;
    *)
      echo "[ERROR] Unknown option: $1" >&2
      exit 1
      ;;
  esac
done

# Period の妥当性チェック（負数・非数を弾く）
if ! [[ "${PERIOD}" =~ ^[0-9]+$ ]]; then
  echo "[ERROR] --period must be a non-negative integer (got '${PERIOD}')" >&2
  exit 1
fi
if ! [[ "${MAX_CYCLES}" =~ ^[0-9]+$ ]]; then
  echo "[ERROR] --max-cycles must be a non-negative integer (got '${MAX_CYCLES}')" >&2
  exit 1
fi

# ----- パス解決 -----

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RUNTIME_DIR="$(cd "${SCRIPT_DIR}/../.." && pwd)"
MIND_DIR="${RUNTIME_DIR}/minds/${MIND_NAME}"
LOCK_DIR="${MIND_DIR}/.mind-loop.lock"
PID_FILE="${MIND_DIR}/.mind-loop.pid"
LOG_FILE="${MIND_DIR}/mind-loop.log"

if [ ! -d "${MIND_DIR}" ]; then
  echo "[ERROR] Mind '${MIND_NAME}' does not exist (looked for ${MIND_DIR})" >&2
  echo "[HINT] Spawn it first: ${SCRIPT_DIR}/spawn-mind.sh <kind> <persona> ${MIND_NAME}" >&2
  exit 2
fi

# 二重起動の atomic ロック。
# 旧実装は (1) PID file の存在チェック → (2) kill -0 → (3) PID file 書き込み の TOCTOU
# があった。`mkdir` は POSIX 上 atomic なので、これを lock として使う。
# lock が取れなかった = 別 loop が走っている → exit 3。
# stale lock（前回が SIGKILL 等で落ちて lock が残った場合）は PID file 経由でチェック。
if ! mkdir "${LOCK_DIR}" 2>/dev/null; then
  # lock 取れず → 既存 loop が居るか、stale lock か判定
  EXISTING_PID=""
  if [ -f "${PID_FILE}" ]; then
    EXISTING_PID="$(cat "${PID_FILE}" 2>/dev/null || echo "")"
  fi
  if [ -n "${EXISTING_PID}" ] && kill -0 "${EXISTING_PID}" 2>/dev/null; then
    echo "[ERROR] Mind '${MIND_NAME}' already has a loop running (pid ${EXISTING_PID})" >&2
    echo "[HINT] Stop it first: ${SCRIPT_DIR}/kill-mind.sh ${MIND_NAME}" >&2
    exit 3
  fi
  # stale lock: 前回の loop が SIGKILL で落ちた等。lock を奪って続行。
  echo "[mind-loop] stale lock detected (no live process), reclaiming..." >&2
  rm -rf "${LOCK_DIR}"
  rm -f "${PID_FILE}"
  if ! mkdir "${LOCK_DIR}" 2>/dev/null; then
    echo "[ERROR] Could not acquire lock at ${LOCK_DIR}" >&2
    exit 3
  fi
fi

# ----- claude バイナリ解決 -----

CLAUDE_BIN="${AI_ORG_OS_CLAUDE_BIN:-claude}"
if ! command -v "${CLAUDE_BIN}" >/dev/null 2>&1; then
  echo "[ERROR] claude command '${CLAUDE_BIN}' not found in PATH" >&2
  echo "[HINT] Install Claude Code, or set AI_ORG_OS_CLAUDE_BIN to your claude binary path" >&2
  echo "[HINT] For tests, AI_ORG_OS_CLAUDE_BIN can point to a stub script" >&2
  exit 4
fi

# ----- 終了ハンドリング -----

# このループプロセスのために予約する trap。SIGTERM / SIGINT で
# 進行中の cycle を完走してから loop を抜ける（強制終了ではない）。
# 強制終了が必要なときは SIGKILL を使う（pid file は残るが arena 上問題ない）。
RECEIVED_STOP=0
on_signal() {
  RECEIVED_STOP=1
  echo "[mind-loop] received stop signal, exiting after current cycle..." >&2
}
trap on_signal TERM INT

cleanup_on_exit() {
  rm -f "${PID_FILE}"
  rm -rf "${LOCK_DIR}"
}
trap cleanup_on_exit EXIT

# ----- PID file 書き込み -----

echo "$$" > "${PID_FILE}"

# ----- ループ本体 -----

CYCLE=0
echo "[mind-loop] Mind '${MIND_NAME}' starting loop (period=${PERIOD}s, max_cycles=${MAX_CYCLES})" \
  | tee -a "${LOG_FILE}"
echo "[mind-loop] pid=$$ pidfile=${PID_FILE}" | tee -a "${LOG_FILE}"

while :; do
  CYCLE=$((CYCLE + 1))
  STARTED_AT="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"
  echo "[mind-loop][cycle ${CYCLE}] start ${STARTED_AT}" >> "${LOG_FILE}"

  # cycle に渡す prompt は最小: cycle 番号と Mind 名のみ。
  # 本実装の主目的は「ループが回ること」「停止できること」「ログが残ること」の検証。
  # Persona / inbox 状況を取り込む高度なプロンプト組み立ては #41 後続の改善で対応。
  PROMPT="cycle ${CYCLE} for mind ${MIND_NAME}. Check inbox via Nexus and act per your Persona."

  # claude をブロッキング呼び出し。標準出力 / エラーをログに混ぜる。
  # CLAUDE.md (Persona) と .mcp.json (Nexus) は Mindspace 内に置かれているので、
  # cwd を Mindspace にすれば自動的に読まれる。
  set +e
  (
    cd "${MIND_DIR}"
    "${CLAUDE_BIN}" -p "${PROMPT}" 2>&1
  ) >> "${LOG_FILE}"
  RC=$?
  set -e

  FINISHED_AT="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"
  echo "[mind-loop][cycle ${CYCLE}] end ${FINISHED_AT} exit=${RC}" >> "${LOG_FILE}"

  # 終了条件: signal 受信 / max-cycles 到達
  if [ "${RECEIVED_STOP}" = "1" ]; then
    echo "[mind-loop] stopping due to signal after cycle ${CYCLE}" | tee -a "${LOG_FILE}"
    break
  fi
  if [ "${MAX_CYCLES}" -gt 0 ] && [ "${CYCLE}" -ge "${MAX_CYCLES}" ]; then
    echo "[mind-loop] reached max-cycles ${MAX_CYCLES}, stopping" | tee -a "${LOG_FILE}"
    break
  fi

  # sleep を 1 秒刻みで分割し、signal 受信時に即時抜けられるようにする。
  # 単一の `sleep ${PERIOD}` だと SIGTERM 後に次 cycle 突入してから止まる挙動になる。
  if [ "${PERIOD}" -gt 0 ]; then
    SLEPT=0
    while [ "${SLEPT}" -lt "${PERIOD}" ]; do
      sleep 1
      SLEPT=$((SLEPT + 1))
      if [ "${RECEIVED_STOP}" = "1" ]; then
        break
      fi
    done
    if [ "${RECEIVED_STOP}" = "1" ]; then
      echo "[mind-loop] stopping during sleep after cycle ${CYCLE}" | tee -a "${LOG_FILE}"
      break
    fi
  fi
done

echo "[mind-loop] Mind '${MIND_NAME}' loop ended (total cycles: ${CYCLE})" | tee -a "${LOG_FILE}"
