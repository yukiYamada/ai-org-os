#!/usr/bin/env bash
#
# spawn-mind.sh — Mind を 1 個起動する最小スクリプト（Phase 1 + Phase 3）
#
# 用法:
#   ./runtime/pillars/lifecycle/spawn-mind.sh <kind> <persona> <mind-name>
#
# 例:
#   ./runtime/pillars/lifecycle/spawn-mind.sh generic designer my-first-mind
#
# 仕様:
#   - Mindspace = ホスト上のディレクトリ runtime/minds/<mind-name>/
#   - Persona の内容を CLAUDE.md として配置
#   - Nexus（MCP server）への接続設定 .mcp.json を Mindspace に配置（Phase 3 で追加）
#   - その後 cd して claude を起動すれば、Nexus 経由で他 Mind と Dispatch できる
#
# Phase 2 以降:
#   - Docker コンテナで起動
#   - Warden 経由で生成（3段階プロセス: 要求→承認→実行）
#   - リソース制限を enforce
#
set -euo pipefail

START_LOOP=0
GUILD="default"
ARGS=()
while [ "$#" -gt 0 ]; do
  case "$1" in
    --start-loop)
      START_LOOP=1
      shift
      ;;
    --guild)
      if [ "$#" -lt 2 ]; then
        echo "[ERROR] --guild requires a value" >&2
        exit 1
      fi
      GUILD="$2"
      shift 2
      ;;
    --guild=*)
      GUILD="${1#--guild=}"
      shift
      ;;
    -h|--help)
      cat <<HELP
Usage: $0 [--start-loop] [--guild <name>] <kind> <persona> <mind-name>

Options:
  --start-loop      Launch mind-loop.sh in the background after spawning (ADR-0010).
  --guild <name>    Guild to which this Mind belongs (default: "default", ADR-0019).
                    Manifest is looked up at \$AI_ORG_OS_HOME/guilds/<name>/manifest.md
                    first (overlay), then templates/guilds/<name>/manifest.md
                    (ADR-0020). The manifest must list this kind/persona.

Kind / Persona lookup (Phase 5c-1 / ADR-0020):
  \$AI_ORG_OS_HOME/{kinds,personas}/<name>.md (overlay) → templates/{kinds,personas}/<name>.md

Example:
  $0 generic designer my-first-mind                          # default guild
  $0 --guild backend generic designer my-backend-mind        # explicit guild
  $0 --start-loop generic designer my-first-mind             # spawn and start loop
HELP
      exit 0
      ;;
    *)
      ARGS+=("$1")
      shift
      ;;
  esac
done

if [ "${#ARGS[@]}" -ne 3 ]; then
  echo "Usage: $0 [--start-loop] [--guild <name>] <kind> <persona> <mind-name>" >&2
  echo "Example: $0 generic designer my-first-mind" >&2
  exit 1
fi

KIND="${ARGS[0]}"
PERSONA="${ARGS[1]}"
MIND_NAME="${ARGS[2]}"

# Argument validation (regression test for Codex P2 on PR #27).
# Reject inputs that contain characters which would either:
#   - break the JSON we emit into .mcp.json (e.g. " or \), making MCP startup fail silently
#   - allow path traversal when used to look up runtime/kinds/<KIND>.md etc.
# The pattern matches storage.py's _validate_mind_name so the host-side and
# the Python-side rules stay consistent.
_VALID_NAME_RE='^[A-Za-z0-9._-]{1,64}$'
validate_arg() {
  local arg_label="$1"
  local arg_value="$2"
  if [[ ! "${arg_value}" =~ ${_VALID_NAME_RE} ]]; then
    echo "[ERROR] Invalid ${arg_label}: '${arg_value}'" >&2
    echo "[HINT] Must match ${_VALID_NAME_RE} (no quotes, backslashes, spaces, path separators)" >&2
    exit 6
  fi
}
validate_arg "kind" "${KIND}"
validate_arg "persona" "${PERSONA}"
validate_arg "mind-name" "${MIND_NAME}"
validate_arg "guild" "${GUILD}"

# Phase 5a-2: 本スクリプトは runtime/pillars/lifecycle/ 配下。
# Phase 5b-4 (#81 / ADR-0018): Mindspace は $AI_ORG_OS_HOME/minds/<name>/ で
# repo 外、runtime state 扱い。
# Phase 5c-1 (#87 / ADR-0020): kinds / personas / guilds は組織依存物。
# 物理的に templates/ (同梱テンプレ) と $AI_ORG_OS_HOME/<category>/ (実体) の
# 2 layer overlay で解決する。home が無ければ templates にフォールバック。
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RUNTIME_DIR="$(cd "${SCRIPT_DIR}/../.." && pwd)"
REPO_DIR="$(cd "${RUNTIME_DIR}/.." && pwd)"
TEMPLATES_DIR="${REPO_DIR}/templates"
# AI_ORG_OS_HOME を解決 (env or default ~/.ai-org-os)。config.env でも上書きされる。
DEFAULT_RUNTIME_HOME="${HOME:-${USERPROFILE:-}}/.ai-org-os"
RUNTIME_HOME="${AI_ORG_OS_HOME:-${DEFAULT_RUNTIME_HOME}}"
MIND_DIR="${RUNTIME_HOME}/minds/${MIND_NAME}"

# Phase 5c-1 / ADR-0020: 2 layer overlay の path 解決。
# 引数: $1=category (kinds|personas), $2=name. 見つかった path を echo。
# 失敗時は空文字列を echo して return 1。
resolve_overlay_md() {
  local category="$1"
  local name="$2"
  local home_path="${RUNTIME_HOME}/${category}/${name}.md"
  local template_path="${TEMPLATES_DIR}/${category}/${name}.md"
  if [ -f "${home_path}" ]; then
    echo "${home_path}"
    return 0
  fi
  if [ -f "${template_path}" ]; then
    echo "${template_path}"
    return 0
  fi
  echo ""
  return 1
}

KIND_FILE="$(resolve_overlay_md kinds "${KIND}" || true)"
PERSONA_FILE="$(resolve_overlay_md personas "${PERSONA}" || true)"

if [ -z "${KIND_FILE}" ]; then
  echo "[ERROR] Kind '${KIND}' is not registered." >&2
  echo "[HINT] Looked in ${RUNTIME_HOME}/kinds/ (overlay) and ${TEMPLATES_DIR}/kinds/ (templates)." >&2
  echo "[HINT] List bundled templates: ls ${TEMPLATES_DIR}/kinds/" >&2
  exit 2
fi

if [ -z "${PERSONA_FILE}" ]; then
  echo "[ERROR] Persona '${PERSONA}' not found." >&2
  echo "[HINT] Looked in ${RUNTIME_HOME}/personas/ (overlay) and ${TEMPLATES_DIR}/personas/ (templates)." >&2
  echo "[HINT] List bundled templates: ls ${TEMPLATES_DIR}/personas/" >&2
  exit 3
fi

if [ -d "${MIND_DIR}" ]; then
  echo "[ERROR] Mind '${MIND_NAME}' already exists at ${MIND_DIR}" >&2
  echo "[HINT] Choose another name or remove the existing one (= explicit destruction)" >&2
  exit 4
fi

# Phase 5b-3 (#78): ホスト setup フェーズで生成された config.env を読み込む。
# Phase 5b-4 (#81): config.env は $AI_ORG_OS_HOME/config.env に移動。
# config.env が無ければ「setup.sh を先に叩け」と fail。
# テスト用に AI_ORG_OS_HOST_CONFIG env で path を override 可能。
HOST_CONFIG="${AI_ORG_OS_HOST_CONFIG:-${RUNTIME_HOME}/config.env}"
if [ ! -f "${HOST_CONFIG}" ]; then
  echo "[ERROR] host setup not done: ${HOST_CONFIG} not found." >&2
  echo "[HINT] Run host setup first: bash ${RUNTIME_DIR}/host/setup.sh" >&2
  echo "[HINT] (creates host venv + mcp install + resolves OS-native paths)" >&2
  exit 5
fi
# shellcheck source=/dev/null
. "${HOST_CONFIG}"

# config.env に必要な変数が揃っているか検証
if [ -z "${HOST_PYTHON_BIN:-}" ] || [ -z "${HOST_NEXUS_PY:-}" ]; then
  echo "[ERROR] ${HOST_CONFIG} is missing HOST_PYTHON_BIN or HOST_NEXUS_PY." >&2
  echo "[HINT] Re-run: bash ${RUNTIME_DIR}/host/setup.sh --recreate-venv" >&2
  exit 5
fi

# Mind が Nexus を stdio で起動できるか念のため確認 (file 存在)。
# HOST_PYTHON_BIN は OS ネイティブパス (Windows: C:/..., Unix: /...)。
# `command -v` は POSIX path しか解決できないので、ファイル存在で代用する。
if [ ! -f "${HOST_PYTHON_BIN}" ]; then
  echo "[ERROR] HOST_PYTHON_BIN '${HOST_PYTHON_BIN}' (from config.env) is not a file." >&2
  echo "[HINT] Re-run: bash ${RUNTIME_DIR}/host/setup.sh --recreate-venv" >&2
  exit 5
fi
if [ ! -f "${HOST_NEXUS_PY}" ]; then
  echo "[ERROR] HOST_NEXUS_PY '${HOST_NEXUS_PY}' (from config.env) is not a file." >&2
  echo "[HINT] Re-run: bash ${RUNTIME_DIR}/host/setup.sh" >&2
  exit 5
fi

# --start-loop 指定時は claude バイナリも事前検証する。
# (mind-loop.sh の exit 4 を spawn 時点で先取り。「spawn 成功 / loop 即死」を防ぐ)
if [ "${START_LOOP}" = "1" ]; then
  CLAUDE_BIN="${AI_ORG_OS_CLAUDE_BIN:-claude}"
  if ! command -v "${CLAUDE_BIN}" >/dev/null 2>&1; then
    echo "[ERROR] claude command '${CLAUDE_BIN}' not found in PATH." >&2
    echo "[HINT] Install Claude Code, or set AI_ORG_OS_CLAUDE_BIN to your claude binary path." >&2
    echo "[HINT] Without claude, the --start-loop option cannot run mind-loop.sh." >&2
    exit 8
  fi
fi

# Phase 5c-1 (#88 Codex P2): Kind の registration を Registry Pillar で再検証。
# resolve_overlay_md は file 存在のみで通すため、home overlay (例:
# $AI_ORG_OS_HOME/kinds/<KIND>.md) が parse 不能でも spawn が進んでしまう。
# 一方 registry.py check は overlay shadow consistency を強制するので、
# 「Registry says unregistered なのに spawn は通る」不整合が起きる。
# spawn 前に registry.py check で parse まで含めた検証を行う。
REGISTRY_PY="${RUNTIME_DIR}/pillars/registry/registry.py"
if [ ! -f "${REGISTRY_PY}" ]; then
  echo "[ERROR] registry.py not found at ${REGISTRY_PY}" >&2
  echo "[HINT] Phase 5a-4 implementation may be incomplete; please reinstall ai-org-os." >&2
  exit 10
fi
echo "[spawn-mind] Verifying Kind registration via Registry Pillar: ${KIND}"
if ! "${HOST_PYTHON_BIN}" "${REGISTRY_PY}" check "${KIND}"; then
  echo "[ERROR] Kind '${KIND}' is not registered (or its overlay file is malformed)." >&2
  echo "[HINT] List registered Kinds: ${HOST_PYTHON_BIN} ${REGISTRY_PY} list" >&2
  echo "[HINT] Inspect Kind:           ${HOST_PYTHON_BIN} ${REGISTRY_PY} get ${KIND}" >&2
  echo "[HINT] If you edited \$AI_ORG_OS_HOME/kinds/${KIND}.md, verify its frontmatter." >&2
  exit 2
fi

# Phase 5c-1 (#87 / ADR-0019): Guild membership 検証。
# 指定 Guild の manifest.md に kind / persona が含まれていなければ spawn を拒否。
# guild.py は Registry Pillar 配下にあり、framework のみ参照 (mutable state を読まない)。
GUILD_PY="${RUNTIME_DIR}/pillars/registry/guild.py"
if [ ! -f "${GUILD_PY}" ]; then
  echo "[ERROR] guild.py not found at ${GUILD_PY}" >&2
  echo "[HINT] Phase 5c-1 implementation may be incomplete; please reinstall ai-org-os." >&2
  exit 10
fi
echo "[spawn-mind] Validating membership: guild='${GUILD}' kind='${KIND}' persona='${PERSONA}'"
if ! "${HOST_PYTHON_BIN}" "${GUILD_PY}" validate \
    --guild "${GUILD}" --kind "${KIND}" --persona "${PERSONA}"; then
  echo "[ERROR] Guild membership validation failed." >&2
  echo "[HINT] List available guilds: ${HOST_PYTHON_BIN} ${GUILD_PY} list" >&2
  echo "[HINT] Inspect manifest:      ${HOST_PYTHON_BIN} ${GUILD_PY} show ${GUILD}" >&2
  exit 11
fi

echo "[spawn-mind] Creating Mindspace: ${MIND_DIR}"
mkdir -p "${MIND_DIR}"

echo "[spawn-mind] Installing Persona '${PERSONA}' as CLAUDE.md"
cp "${PERSONA_FILE}" "${MIND_DIR}/CLAUDE.md"

cat > "${MIND_DIR}/.mind-meta.md" <<EOF
---
mind_name: ${MIND_NAME}
kind: ${KIND}
persona: ${PERSONA}
guild: ${GUILD}
spawned_at: $(date -u +"%Y-%m-%dT%H:%M:%SZ")
phase: 1+3
---

# Mind metadata

このファイルは暫定的なメタデータです。
Phase 5 以降は Warden がより構造化された形で管理します。

guild フィールドは Phase 5c-1 (ADR-0019) で追加。
所属 Guild の authoritative source として nexus.py の claim_issue で参照される。
EOF

# Phase 3 + 5b-3: Nexus (MCP server) への接続設定を Mindspace に配置。
# Claude Code は .mcp.json を読んで MCP サーバーに接続する（stdio）。
# パスはホスト setup フェーズ (host/setup.sh) で OS ネイティブ形式に解決済の
# HOST_PYTHON_BIN / HOST_NEXUS_PY を使う。spawn-mind 側はパス形式を意識しない。
#
# AI_ORG_OS_MIND_NAME env var binds the Nexus stdio subprocess to this Mind's
# identity (Issue #19, ADR-0008). The Nexus then rejects send_dispatch /
# read_inbox / ack_dispatch calls whose from_mind / mind_name does not match
# this binding, preventing one Mind from impersonating another via crafted
# arguments.
echo "[spawn-mind] Installing Nexus MCP config (.mcp.json), bound to '${MIND_NAME}'"
echo "  python: ${HOST_PYTHON_BIN}"
echo "  nexus:  ${HOST_NEXUS_PY}"
cat > "${MIND_DIR}/.mcp.json" <<JSON
{
  "mcpServers": {
    "nexus": {
      "type": "stdio",
      "command": "${HOST_PYTHON_BIN}",
      "args": ["${HOST_NEXUS_PY}"],
      "env": {
        "AI_ORG_OS_MIND_NAME": "${MIND_NAME}",
        "AI_ORG_OS_HOME": "${AI_ORG_OS_HOME:-${RUNTIME_HOME}}"
      }
    }
  }
}
JSON

echo "[spawn-mind] Mind '${MIND_NAME}' is ready at ${MIND_DIR}"

if [ "${START_LOOP}" = "1" ]; then
  # --start-loop は mind-loop.sh をバックグラウンド起動する。
  # nohup + setsid 相当で親プロセス（spawn-mind.sh）の終了に追従させない。
  # 詳細な loop 仕様は mind-loop.sh / ADR-0010 を参照。
  LOOP_SCRIPT="${SCRIPT_DIR}/mind-loop.sh"
  if [ ! -f "${LOOP_SCRIPT}" ]; then
    echo "[ERROR] mind-loop.sh not found at ${LOOP_SCRIPT}" >&2
    echo "[HINT] The Mind was spawned successfully but the loop could not be started." >&2
    exit 7
  fi
  echo "[spawn-mind] Starting external loop (mind-loop.sh) in background"
  # setsid があれば使う、無ければ nohup で代替（コンテナの coreutils 限定環境向け）
  if command -v setsid >/dev/null 2>&1; then
    setsid bash "${LOOP_SCRIPT}" "${MIND_NAME}" </dev/null >/dev/null 2>&1 &
  else
    nohup bash "${LOOP_SCRIPT}" "${MIND_NAME}" </dev/null >/dev/null 2>&1 &
  fi
  LOOP_PID=$!
  disown "${LOOP_PID}" 2>/dev/null || true

  # Codex P1 PR #61: 起動成功を検証する。
  # mind-loop.sh は lock 取得直後に PID file を書くため、これをシグナルにする。
  # 最大 1 秒（5 回 × 200ms）待つ。
  LOOP_PID_FILE="${MIND_DIR}/.mind-loop.pid"
  verified=0
  for _ in 1 2 3 4 5; do
    sleep 0.2
    if [ -f "${LOOP_PID_FILE}" ]; then
      verified=1
      break
    fi
  done
  if [ "${verified}" -ne 1 ]; then
    echo "[ERROR] mind-loop.sh did not initialize within 1s (pid file ${LOOP_PID_FILE} not found)" >&2
    echo "[HINT] Mind '${MIND_NAME}' was spawned but its loop is not running." >&2
    if [ -f "${MIND_DIR}/mind-loop.log" ]; then
      echo "[HINT] Last 10 lines of mind-loop.log:" >&2
      tail -10 "${MIND_DIR}/mind-loop.log" >&2 || true
    fi
    echo "[HINT] Retry manually: ${SCRIPT_DIR}/mind-loop.sh ${MIND_NAME}" >&2
    exit 9
  fi
  echo "[spawn-mind] Loop started in background (pid ${LOOP_PID}, verified via pid file)"
  echo "  - Log:    ${MIND_DIR}/mind-loop.log"
  echo "  - PID:    ${LOOP_PID_FILE} (managed by mind-loop.sh)"
  echo "  - Stop:   ${SCRIPT_DIR}/kill-mind.sh ${MIND_NAME}"
else
  echo ""
  echo "Next step (manual):"
  echo "  cd ${MIND_DIR}"
  echo "  claude   # CLAUDE.md (Persona) と .mcp.json (Nexus 接続) が自動的に読まれます"
  echo ""
  echo "Or start the external loop (ADR-0010):"
  echo "  ${SCRIPT_DIR}/mind-loop.sh ${MIND_NAME}"
fi
echo ""
echo "Nexus が提供する tool:"
echo "  - send_dispatch / read_inbox / ack_dispatch"
echo "  Mind は他 Mind の Mindspace を直接触れません。すべての通信は Nexus 経由です（Axiom）。"
