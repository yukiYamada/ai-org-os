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
# Realm 全体に書き込むもの (Phase 5f Step 1 / ADR-0026 §4.5):
#   - $AI_ORG_OS_HOME/logs/minds/<mind>/mind-loop.jsonl
#     構造化 event log (mind_loop.start / mind_loop.end)。observe.py --trace
#     から時系列 join 可能。書き込み失敗は loop を止めない (F3 / ADR-0013 §1)。
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

# Phase 5f Step 4.2 / ADR-0028 §2.1: per-cycle timeout (A axiom)。
# claude が hang したら mind-loop ごと止まる事故 (#134: gm cycle 640s / carol 655s)
# を救う。0 = timeout 無効、正の値 = 秒数。default 300 秒 (= 5 分、典型 cycle body
# が 200 秒程度の Phase 5f 実観察から余裕を持たせた値)。
CYCLE_TIMEOUT="${AI_ORG_OS_MIND_LOOP_CYCLE_TIMEOUT:-300}"
# 連続 timeout streak がこれを超えたら Mind を auto-kill (= ADR-0013 Kill 段階の
# 自動化)。0 = streak 監視無効。default 3 (= 偶発失敗 1-2 回は許容、3 連続 =
# Mind が機能していないとみなす)。
CYCLE_TIMEOUT_STREAK_MAX="${AI_ORG_OS_MIND_LOOP_TIMEOUT_STREAK:-3}"

# Phase 5f Step 4.3 / ADR-0028 §2.2: cycle error streak (A axiom)。
# timeout 以外の異常終了 (exit code != 0、claude API 529 / SDK crash / OS signal 等)
# を観察。連続 streak max で notify-human signal を emit (operator が見にくる経路、
# §2.3 で具体化)。timeout と違い auto-kill **しない** — error は再現性のある operator
# 介入対象であり、自動 kill すると forensics が失われるため。
CYCLE_ERROR_STREAK_MAX="${AI_ORG_OS_MIND_LOOP_ERROR_STREAK:-5}"

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
if ! [[ "${CYCLE_TIMEOUT}" =~ ^[0-9]+$ ]]; then
  echo "[ERROR] AI_ORG_OS_MIND_LOOP_CYCLE_TIMEOUT must be non-negative integer (got '${CYCLE_TIMEOUT}')" >&2
  exit 1
fi
if ! [[ "${CYCLE_TIMEOUT_STREAK_MAX}" =~ ^[0-9]+$ ]]; then
  echo "[ERROR] AI_ORG_OS_MIND_LOOP_TIMEOUT_STREAK must be non-negative integer (got '${CYCLE_TIMEOUT_STREAK_MAX}')" >&2
  exit 1
fi
if ! [[ "${CYCLE_ERROR_STREAK_MAX}" =~ ^[0-9]+$ ]]; then
  echo "[ERROR] AI_ORG_OS_MIND_LOOP_ERROR_STREAK must be non-negative integer (got '${CYCLE_ERROR_STREAK_MAX}')" >&2
  exit 1
fi

# ----- パス解決 -----

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RUNTIME_DIR="$(cd "${SCRIPT_DIR}/../.." && pwd)"
# Phase 5b-4 (#81 / ADR-0018): Mindspace は $AI_ORG_OS_HOME/minds/ 配下。
DEFAULT_RUNTIME_HOME="${HOME:-${USERPROFILE:-}}/.ai-org-os"
RUNTIME_HOME="${AI_ORG_OS_HOME:-${DEFAULT_RUNTIME_HOME}}"
MIND_DIR="${RUNTIME_HOME}/minds/${MIND_NAME}"
LOCK_DIR="${MIND_DIR}/.mind-loop.lock"
PID_FILE="${MIND_DIR}/.mind-loop.pid"
LOG_FILE="${MIND_DIR}/mind-loop.log"
# Phase 5f Step 2 / Fix #136: Nexus.send_dispatch が touch する sentinel ファイル。
# sleep 中に存在を検出したら即時 break して次 cycle へ進む = dispatch 到着 latency
# を cycle period (30s 等) から 1s 以下に短縮する。SIGUSR1 案より cross-platform
# (Windows MSYS bash でも file I/O は確実に動く) で副作用も小さい。
NUDGE_FILE="${MIND_DIR}/.mind-loop.nudge"

# Phase 5f Step 2 / Fix #144 (case A): cycle 内 inbox re-peek 用の Python 実行点。
# claude -p 起動の直前に inbox を peek し、未読 dispatch があれば prompt 冒頭に
# 概要を挿入する → claude が「empty cycle 判定」で早期 exit する時間を短縮し、
# 既存 dispatch の処理優先度を上げる。
# config.env が無い (= host setup 未実施) 場合は python3 にフォールバック。
CONFIG_ENV="${RUNTIME_HOME}/config.env"
if [ -r "${CONFIG_ENV}" ]; then
  # shellcheck disable=SC1090
  . "${CONFIG_ENV}"
fi
PEEK_PYTHON_BIN="${HOST_PYTHON_BIN:-${AI_ORG_OS_PYTHON:-python3}}"
CONDUIT_DIR="${RUNTIME_DIR}/pillars/conduit"

if [ ! -d "${MIND_DIR}" ]; then
  echo "[ERROR] Mind '${MIND_NAME}' does not exist (looked for ${MIND_DIR})" >&2
  echo "[HINT] Spawn it first: ${SCRIPT_DIR}/spawn-mind.sh <kind> <persona> ${MIND_NAME}" >&2
  exit 2
fi

# 二重起動の atomic ロック。
# `mkdir` は POSIX 上 atomic なので、これを lock として使う。
# Codex P1 PR #61: lock 取得直後に PID を書き、stale 判定は pidfile の有無ではなく
# 「pidfile が指す PID が live でない」ことを根拠にする。
# 旧実装は `mkdir` ← race window → `echo $$ > PID_FILE` の隙間で 2 つ目の loop が
# pidfile 空を「stale」と誤判定して並列実行が起きうる問題があった。
#
# Codex P2 PR #61 (2nd): kill -0 で alive を確認するだけでは、PID 再利用された
# 無関係なプロセスがその PID を持っているケースで永久に exit 3（lock blocked）に
# なる。argv token exact match で「本当に mind-loop か」を確認してから決める。
# kill-mind.sh の verify_loop_owner と同ロジック。
acquire_lock() {
  if ! mkdir "${LOCK_DIR}" 2>/dev/null; then
    return 1
  fi
  # lock 取得直後に PID を書く。後続の検証で pidfile 空が常に「未初期化中」を
  # 意味するように。
  echo "$$" > "${PID_FILE}"
  return 0
}

verify_loop_owner() {
  local pid="$1"
  local mind_name="$2"
  if [ ! -r "/proc/${pid}/cmdline" ]; then
    # /proc 不在環境（macOS/Windows の bash 等）: best-effort。生存しているなら
    # 同一 Mind の loop として扱う（false positive 寄り、stale lock を回避する側）。
    return 0
  fi
  local has_script=0 has_mind=0 arg
  while IFS= read -r -d '' arg; do
    # Windows + MSYS で Python subprocess 経由で bash を呼ぶと argv[1] が
    # backslash 区切りの Windows path になる (例:
    # "C:\Users\...\mind-loop.sh") ため、forward-slash と backslash の両方を
    # 受け入れる (kill-mind.sh の verify_loop_owner と整合)。
    case "${arg}" in
      mind-loop.sh|*/mind-loop.sh|*\\mind-loop.sh) has_script=1 ;;
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

if ! acquire_lock; then
  # lock 取れず。pidfile を見て stale 判定する。
  EXISTING_PID=""
  if [ -f "${PID_FILE}" ]; then
    EXISTING_PID="$(cat "${PID_FILE}" 2>/dev/null || echo "")"
  fi

  # pidfile が空 = lock を握った先住プロセスが PID 書き込み前にクラッシュした、
  # または別 loop が初期化中（race）。安全側に振り、200ms 待って再判定する。
  if [ -z "${EXISTING_PID}" ]; then
    sleep 0.2
    if [ -f "${PID_FILE}" ]; then
      EXISTING_PID="$(cat "${PID_FILE}" 2>/dev/null || echo "")"
    fi
  fi

  if [ -n "${EXISTING_PID}" ] && kill -0 "${EXISTING_PID}" 2>/dev/null; then
    # alive な PID。argv token で「本当に同一 Mind の mind-loop か」を確認する。
    if verify_loop_owner "${EXISTING_PID}" "${MIND_NAME}"; then
      echo "[ERROR] Mind '${MIND_NAME}' already has a loop running (pid ${EXISTING_PID})" >&2
      echo "[HINT] Stop it first: ${SCRIPT_DIR}/kill-mind.sh ${MIND_NAME}" >&2
      exit 3
    fi
    # alive だが mind-loop ではない（PID 再利用された無関係なプロセス）→ stale 扱い
    echo "[mind-loop] pid ${EXISTING_PID} is alive but not a mind-loop for '${MIND_NAME}', treating as stale" >&2
  fi

  # ここまで来た = pidfile が live mind-loop を指していない。stale 確定として reclaim。
  echo "[mind-loop] stale lock detected, reclaiming..." >&2
  rm -rf "${LOCK_DIR}"
  rm -f "${PID_FILE}"
  if ! acquire_lock; then
    echo "[ERROR] Could not acquire lock at ${LOCK_DIR}" >&2
    exit 3
  fi
fi

# ----- 終了ハンドリング -----
#
# lock を取得した後すぐに cleanup trap を仕掛ける。これ以降の exit （claude
# バイナリ不在 / signal / 正常終了）で lock + pidfile を必ず掃除する。
cleanup_on_exit() {
  rm -f "${PID_FILE}"
  rm -rf "${LOCK_DIR}"
}
trap cleanup_on_exit EXIT

RECEIVED_STOP=0
on_signal() {
  RECEIVED_STOP=1
  echo "[mind-loop] received stop signal, exiting after current cycle..." >&2
}
trap on_signal TERM INT

# ----- Phase 5f Step 1 / ADR-0026 §4.5: 構造化 event log -----
#
# event は $AI_ORG_OS_HOME/logs/minds/<mind>/mind-loop.jsonl に 1 行 1 JSON で
# append される。F3 準拠: mkdir / write 失敗は WARN 出して loop は続ける。
# ts は UTC ISO-8601 ms precision (BSD date 等 %3N 非対応環境では .000Z fallback)。
# Mind 名は validate 済 (^[A-Za-z0-9._-]{1,64}$) のため JSON 文字列に安全に
# 埋め込める (escape 不要)。

EVENT_LOGS_DIR="${RUNTIME_HOME}/logs/minds/${MIND_NAME}"
EVENT_LOG_FILE="${EVENT_LOGS_DIR}/mind-loop.jsonl"

_mindloop_iso_ms() {
  local ts
  ts="$(date -u +"%Y-%m-%dT%H:%M:%S.%3NZ" 2>/dev/null || true)"
  if [ -z "${ts}" ] || [[ "${ts}" == *"%3N"* ]]; then
    # BSD date 等で %3N が literal として残るパターン: 秒精度に degrade。
    ts="$(date -u +"%Y-%m-%dT%H:%M:%S.000Z")"
  fi
  printf '%s' "${ts}"
}

# Fix #144 case A: inbox を peek して 1 行サマリを stdout に返す。
# 失敗系 (Nexus import error / Python 不在 / read エラー) は silent skip
# (stdout 空文字)。F3 準拠: peek 失敗は cycle 進行を止めない。Mind 名は
# script 起動時に validate 済なので argv 経由で安全に渡せる。
# 実装は runtime/pillars/conduit/peek_inbox.py を呼ぶ standalone CLI 経由
# (MSYS bash の path translation を確実に動かすため、`python -c` インライン
# 方式ではなく argv 渡しを使う)。
_mindloop_peek_inbox() {
  local mind_name="$1"
  "${PEEK_PYTHON_BIN}" "${CONDUIT_DIR}/peek_inbox.py" "${mind_name}" 2>/dev/null || true
}

# Usage: _mindloop_emit_event <event_name> [<extra_json_fields>]
# extra は leading comma 付きの JSON フラグメント
# (例: ',"cycle":1,"pid":12345')。空なら拡張 field なし。
_mindloop_emit_event() {
  local event="$1"
  local extra="${2:-}"
  if ! mkdir -p "${EVENT_LOGS_DIR}" 2>/dev/null; then
    echo "[mind-loop] WARN: failed to mkdir ${EVENT_LOGS_DIR}" >&2
    return 0
  fi
  local ts
  ts="$(_mindloop_iso_ms)"
  if ! printf '{"ts":"%s","event":"%s","actor":"%s"%s}\n' \
        "${ts}" "${event}" "${MIND_NAME}" "${extra}" \
        >> "${EVENT_LOG_FILE}" 2>/dev/null; then
    echo "[mind-loop] WARN: failed to write ${EVENT_LOG_FILE}" >&2
    return 0
  fi
  return 0
}

# ----- claude バイナリ解決 -----

CLAUDE_BIN="${AI_ORG_OS_CLAUDE_BIN:-claude}"
if ! command -v "${CLAUDE_BIN}" >/dev/null 2>&1; then
  echo "[ERROR] claude command '${CLAUDE_BIN}' not found in PATH" >&2
  echo "[HINT] Install Claude Code, or set AI_ORG_OS_CLAUDE_BIN to your claude binary path" >&2
  echo "[HINT] For tests, AI_ORG_OS_CLAUDE_BIN can point to a stub script" >&2
  exit 4
fi

# Phase 5f Step 4.2 / ADR-0028 §2.1: per-cycle timeout 用に `timeout` を resolve。
# GNU coreutils `timeout` を期待 (Linux + Git Bash on Windows でデフォルト)。
# 不在なら CYCLE_TIMEOUT を強制 0 (= timeout 無効) にして cycle は wrap せず実行。
TIMEOUT_BIN="$(command -v timeout 2>/dev/null || true)"
if [ "${CYCLE_TIMEOUT}" -gt 0 ] && [ -z "${TIMEOUT_BIN}" ]; then
  echo "[mind-loop] WARN: \`timeout\` binary not found; per-cycle timeout disabled" >&2
  CYCLE_TIMEOUT=0
fi

# ----- ループ本体 -----

CYCLE=0
echo "[mind-loop] Mind '${MIND_NAME}' starting loop (period=${PERIOD}s, max_cycles=${MAX_CYCLES})" \
  | tee -a "${LOG_FILE}"
echo "[mind-loop] pid=$$ pidfile=${PID_FILE}" | tee -a "${LOG_FILE}"

while :; do
  CYCLE=$((CYCLE + 1))
  # Fix #136: cycle 開始時に nudge file を consume。前 cycle で sleep loop が
  # nudge を検知して break した場合、ここで file を消すことで「同じ nudge が
  # 次 sleep でも検知される (= 無限 burst)」を防ぐ。cycle body 中に到着した
  # nudge は **直後の sleep loop で検知され break → cycle 開始 → ここで消費**
  # の流れになるので timing race は無い (= 消費は cycle 単位、message 単位
  # ではない点に注意: 1 cycle で複数の dispatch が処理されることがある)。
  rm -f "${NUDGE_FILE}" 2>/dev/null || true

  STARTED_AT="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"
  START_EPOCH="$(date -u +%s)"
  echo "[mind-loop][cycle ${CYCLE}] start ${STARTED_AT}" >> "${LOG_FILE}"
  # ADR-0026 §4.5: mind_loop.start event。pid は $$ (loop プロセス自身)。
  _mindloop_emit_event "mind_loop.start" ",\"cycle\":${CYCLE},\"pid\":$$"

  # cycle に渡す prompt は最小: cycle 番号と Mind 名のみ。
  # 本実装の主目的は「ループが回ること」「停止できること」「ログが残ること」の検証。
  # Persona / inbox 状況を取り込む高度なプロンプト組み立ては #41 後続の改善で対応。
  PROMPT="cycle ${CYCLE} for mind ${MIND_NAME}. Check inbox via Nexus and act per your Persona."

  # Fix #144 case A: claude 起動直前に inbox 状況を peek し、prompt 冒頭に概要を
  # 挿入する。claude は依然として read_inbox MCP tool で全文を読むが、ここで
  # 「empty / non-empty」を示しておくと cycle 1 で空 inbox に対する確認時間と、
  # cycle 2+ で「あなた宛 dispatch が既に届いている」の signal を明示化できる。
  # peek 失敗 (= python 不在 / Nexus 故障) は silent fallback (= 既存 prompt のまま)。
  PEEK_SUMMARY="$(_mindloop_peek_inbox "${MIND_NAME}")"
  if [ -n "${PEEK_SUMMARY}" ]; then
    PROMPT="cycle ${CYCLE} for mind ${MIND_NAME}. INBOX: ${PEEK_SUMMARY}. Check inbox via Nexus and act per your Persona."
  fi

  # claude をブロッキング呼び出し。標準出力 / エラーをログに混ぜる。
  # CLAUDE.md (Persona) と .mcp.json (Nexus) は Mindspace 内に置かれているので、
  # cwd を Mindspace にすれば自動的に読まれる。
  # Phase 5f Step 4.2 / ADR-0028 §2.1: CYCLE_TIMEOUT > 0 なら GNU coreutils
  # `timeout --kill-after=10` で wrap。SIGTERM 後 10 秒猶予→ SIGKILL。
  set +e
  if [ "${CYCLE_TIMEOUT}" -gt 0 ]; then
    (
      cd "${MIND_DIR}"
      "${TIMEOUT_BIN}" --kill-after=10 "${CYCLE_TIMEOUT}" "${CLAUDE_BIN}" -p "${PROMPT}" 2>&1
    ) >> "${LOG_FILE}"
  else
    (
      cd "${MIND_DIR}"
      "${CLAUDE_BIN}" -p "${PROMPT}" 2>&1
    ) >> "${LOG_FILE}"
  fi
  RC=$?
  set -e

  FINISHED_AT="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"
  END_EPOCH="$(date -u +%s)"
  DURATION_S=$((END_EPOCH - START_EPOCH))

  # ADR-0028 §2.1: timeout exit code 検出。GNU coreutils timeout の規約:
  #   124 = SIGTERM (timeout expired)
  #   137 = 128 + 9 = SIGKILL (kill-after 期限切れ)
  TIMED_OUT=0
  if [ "${CYCLE_TIMEOUT}" -gt 0 ]; then
    if [ "${RC}" = "124" ] || [ "${RC}" = "137" ]; then
      TIMED_OUT=1
      echo "[mind-loop][cycle ${CYCLE}] TIMEOUT after ${CYCLE_TIMEOUT}s (exit=${RC})" >> "${LOG_FILE}"
      echo "[mind-loop] WARN: cycle ${CYCLE} timed out after ${CYCLE_TIMEOUT}s (exit=${RC})" >&2
    fi
  fi

  # ADR-0028 §2.2: error 検出 (timeout 以外の non-zero exit)。
  # claude が exit code 1 を返すケースも error として記録するが、Persona の判断
  # ロジックに踏み込まない (= notify-human で operator に raise するのみ)。
  IS_ERROR=0
  if [ "${TIMED_OUT}" = "0" ] && [ "${RC}" != "0" ]; then
    IS_ERROR=1
  fi

  # streak 管理: 連続 timeout なら increment、成功なら reset。error も同様に独立 streak。
  if [ "${TIMED_OUT}" = "1" ]; then
    CYCLE_TIMEOUT_STREAK=$((${CYCLE_TIMEOUT_STREAK:-0} + 1))
  else
    CYCLE_TIMEOUT_STREAK=0
  fi
  if [ "${IS_ERROR}" = "1" ]; then
    CYCLE_ERROR_STREAK=$((${CYCLE_ERROR_STREAK:-0} + 1))
  else
    CYCLE_ERROR_STREAK=0
  fi

  echo "[mind-loop][cycle ${CYCLE}] end ${FINISHED_AT} exit=${RC}" >> "${LOG_FILE}"
  # ADR-0026 §4.5: mind_loop.end event。timeout でも end は emit (= cycle は終わった)。
  if [ "${TIMED_OUT}" = "1" ]; then
    # ADR-0028 §2.1: mind_loop.timeout event を追加で emit (= 通常 end の補足)。
    _mindloop_emit_event "mind_loop.timeout" \
      ",\"cycle\":${CYCLE},\"timeout_s\":${CYCLE_TIMEOUT},\"signal\":\"$([ "${RC}" = "137" ] && echo SIGKILL || echo SIGTERM)\",\"streak\":${CYCLE_TIMEOUT_STREAK}"
  fi
  if [ "${IS_ERROR}" = "1" ]; then
    # ADR-0028 §2.2: mind_loop.error event。exit_code をそのまま入れる (operator が
    # フィルタで重要度判定可)。
    _mindloop_emit_event "mind_loop.error" \
      ",\"cycle\":${CYCLE},\"exit_code\":${RC},\"streak\":${CYCLE_ERROR_STREAK}"
  fi
  _mindloop_emit_event "mind_loop.end" \
    ",\"cycle\":${CYCLE},\"exit_code\":${RC},\"duration_s\":${DURATION_S}"

  # ADR-0028 §2.1: streak 上限到達で Mind を auto-kill (= ADR-0013 Kill 段階)。
  # 0 ならこの機能は無効 (= 永続させる、operator が手で kill する想定)。
  if [ "${CYCLE_TIMEOUT_STREAK_MAX}" -gt 0 ] && [ "${CYCLE_TIMEOUT_STREAK}" -ge "${CYCLE_TIMEOUT_STREAK_MAX}" ]; then
    echo "[mind-loop] Mind '${MIND_NAME}' auto-kill: ${CYCLE_TIMEOUT_STREAK} consecutive cycle timeouts >= ${CYCLE_TIMEOUT_STREAK_MAX}" | tee -a "${LOG_FILE}" >&2
    _mindloop_emit_event "mind_loop.auto_kill" \
      ",\"cycle\":${CYCLE},\"reason\":\"timeout_streak\",\"streak\":${CYCLE_TIMEOUT_STREAK},\"max\":${CYCLE_TIMEOUT_STREAK_MAX}"
    exit 5
  fi

  # ADR-0028 §2.2: error streak 上限到達で notify-human signal を発火。
  # auto-kill しない — error は operator が forensic 確認すべき再現性のある事象。
  # 後続 §2.3 (Step 4.4) で notify channel が L1 jsonl + L2 stderr で具体化される。
  # 本 PR では event emit + stderr WARN まで (= L2)。
  if [ "${CYCLE_ERROR_STREAK_MAX}" -gt 0 ] && [ "${CYCLE_ERROR_STREAK}" -ge "${CYCLE_ERROR_STREAK_MAX}" ]; then
    echo "[mind-loop] Mind '${MIND_NAME}' notify-human: ${CYCLE_ERROR_STREAK} consecutive cycle errors >= ${CYCLE_ERROR_STREAK_MAX} (= operator 介入推奨)" | tee -a "${LOG_FILE}" >&2
    _mindloop_emit_event "mind_loop.error_streak_exceeded" \
      ",\"cycle\":${CYCLE},\"streak\":${CYCLE_ERROR_STREAK},\"max\":${CYCLE_ERROR_STREAK_MAX}"
    # streak counter は reset しない (= 毎 cycle 通知が再発火する。これは意図的、
    # operator が見に来るまで signal を出し続ける)。
  fi

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
  # Fix #136: nudge file 検出時も break して dispatch 到着への応答 latency を短縮。
  if [ "${PERIOD}" -gt 0 ]; then
    SLEPT=0
    while [ "${SLEPT}" -lt "${PERIOD}" ]; do
      sleep 1
      SLEPT=$((SLEPT + 1))
      if [ "${RECEIVED_STOP}" = "1" ]; then
        break
      fi
      # Fix #136: dispatch 到着で nudge file が touch されたら sleep を抜ける。
      # nudge は次 cycle 開始時に削除されるので、ここでは存在だけ確認 (read-only)。
      if [ -e "${NUDGE_FILE}" ]; then
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
