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
WORKSPACE="default"
# Phase 5d-4 (ADR-0022): --workspace が明示されたかを覚えておく。
# 解決順 (引数 > Guild manifest > default) の middle layer 判定に使う。
WORKSPACE_FROM_ARG=0
# Phase 5g.B #171: 既存 preserved snapshot から state.md / notes/ を復元する。
RESTORE_FROM=""
ARGS=()
while [ "$#" -gt 0 ]; do
  case "$1" in
    --start-loop)
      START_LOOP=1
      shift
      ;;
    --restore-from)
      if [ "$#" -lt 2 ]; then
        echo "[ERROR] --restore-from requires a value" >&2
        exit 1
      fi
      RESTORE_FROM="$2"
      shift 2
      ;;
    --restore-from=*)
      RESTORE_FROM="${1#--restore-from=}"
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
    --workspace)
      if [ "$#" -lt 2 ]; then
        echo "[ERROR] --workspace requires a value" >&2
        exit 1
      fi
      WORKSPACE="$2"
      WORKSPACE_FROM_ARG=1
      shift 2
      ;;
    --workspace=*)
      WORKSPACE="${1#--workspace=}"
      WORKSPACE_FROM_ARG=1
      shift
      ;;
    -h|--help)
      cat <<HELP
Usage: $0 [--start-loop] [--guild <name>] [--workspace <name>] [--restore-from <path>] <kind> <persona> <mind-name>

Options:
  --start-loop          Launch mind-loop.sh in the background after spawning (ADR-0010).
  --restore-from <path> Restore state.md + notes/ from a preserved snapshot directory
                        (typically \$AI_ORG_OS_HOME/preserved/<previous-mind-name>/,
                        written by kill-mind --preserve). Persona / Workspace / .mcp.json
                        are still fresh from the binding chosen at this spawn. Phase 5g.B #171.
  --guild <name>        Guild to which this Mind belongs (default: "default", ADR-0019).
                        Manifest is looked up at \$AI_ORG_OS_HOME/guilds/<name>/manifest.md
                        first (overlay), then templates/guilds/<name>/manifest.md
                        (ADR-0020). The manifest must list this kind/persona.
  --workspace <name>    Workspace template for this Mind (ADR-0022).
                        Resolution order: --workspace arg > Guild manifest workspace field > "default".
                        Looked up at \$AI_ORG_OS_HOME/workspaces/<name>.md (overlay)
                        then templates/workspaces/<name>.md. With vcs=git/mode=worktree,
                        the Mindspace gets a git worktree at <Mindspace>/work/.

Kind / Persona lookup (Phase 5c-1 / ADR-0020):
  \$AI_ORG_OS_HOME/{kinds,personas}/<name>.md (overlay) → templates/{kinds,personas}/<name>.md

Example:
  $0 generic designer my-first-mind                          # default guild + default workspace (no git)
  $0 --guild backend generic designer my-backend-mind        # explicit guild
  $0 --workspace developer-default generic designer my-dev   # enable git worktree mode
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
  echo "Usage: $0 [--start-loop] [--guild <name>] [--workspace <name>] <kind> <persona> <mind-name>" >&2
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
# Phase 5e / ADR-0024 §3 / Issue #112: Mind 名として使えない予約語。
# Realm sender (Warden 由来 dispatch 等) と区別不能になるのを防ぐ。
# 値は storage.py の RESERVED_MIND_NAMES と一致させること (二重防御)。
_RESERVED_MIND_NAMES=("warden")
validate_arg() {
  local arg_label="$1"
  local arg_value="$2"
  if [[ ! "${arg_value}" =~ ${_VALID_NAME_RE} ]]; then
    echo "[ERROR] Invalid ${arg_label}: '${arg_value}'" >&2
    echo "[HINT] Must match ${_VALID_NAME_RE} (no quotes, backslashes, spaces, path separators)" >&2
    exit 6
  fi
}
# Mind 名固有の予約語チェック (kind / persona / guild / workspace には適用しない)。
reject_reserved_mind_name() {
  local arg_value="$1"
  local reserved
  for reserved in "${_RESERVED_MIND_NAMES[@]}"; do
    if [ "${arg_value}" = "${reserved}" ]; then
      echo "[ERROR] Mind name '${arg_value}' is reserved for Realm senders (ADR-0024 §3)." >&2
      echo "[HINT] Reserved names: ${_RESERVED_MIND_NAMES[*]}" >&2
      echo "[HINT] Choose another name for the Mind." >&2
      exit 7
    fi
  done
}
validate_arg "kind" "${KIND}"
validate_arg "persona" "${PERSONA}"
validate_arg "mind-name" "${MIND_NAME}"
validate_arg "guild" "${GUILD}"
validate_arg "workspace" "${WORKSPACE}"
reject_reserved_mind_name "${MIND_NAME}"

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

# Phase 5d-4 (ADR-0022): Workspace の解決順 (= 引数 > Guild manifest > default)。
# --workspace 引数が明示されていればそれを使い、無ければ Guild manifest の
# workspace フィールドを問い合わせ、それも空なら "default" にフォールバック。
if [ "${WORKSPACE_FROM_ARG}" = "1" ]; then
  echo "[spawn-mind] Workspace resolved from --workspace: '${WORKSPACE}'"
else
  # guild.py get-workspace は workspace フィールドだけを emit (空 or 値)。
  # Guild が存在しない/malformed のときは stderr に ERROR + exit 3/4 だが、
  # 直前の guild.py validate で正常確認済なのでここでは success path のみ想定。
  GUILD_WS_RAW="$("${HOST_PYTHON_BIN}" "${GUILD_PY}" get-workspace "${GUILD}" 2>/dev/null || true)"
  # CR / LF / 前後空白を除く (Windows + bash で改行が混入することの予防)
  GUILD_WS="$(echo "${GUILD_WS_RAW}" | tr -d '\r\n' | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')"
  if [ -n "${GUILD_WS}" ]; then
    WORKSPACE="${GUILD_WS}"
    # guild.py が返した値も format 検証 (= manifest の typo / 攻撃的注入の防御)
    validate_arg "workspace (from Guild ${GUILD})" "${WORKSPACE}"
    echo "[spawn-mind] Workspace resolved from Guild '${GUILD}' manifest: '${WORKSPACE}'"
  else
    # WORKSPACE は初期値 "default" のまま
    echo "[spawn-mind] Workspace resolved: 'default' (no --workspace, no Guild default)"
  fi
fi

# Phase 5d-2 (ADR-0022): Workspace template の解決と検証。
# vcs=git/mode=worktree なら git worktree を作るための事前確認も行う。
WORKSPACE_PY="${RUNTIME_DIR}/pillars/registry/workspace.py"
if [ ! -f "${WORKSPACE_PY}" ]; then
  echo "[ERROR] workspace.py not found at ${WORKSPACE_PY}" >&2
  echo "[HINT] Phase 5d-1 implementation may be incomplete; please reinstall ai-org-os." >&2
  exit 10
fi
echo "[spawn-mind] Loading workspace template: '${WORKSPACE}'"
WORKSPACE_JSON="$("${HOST_PYTHON_BIN}" "${WORKSPACE_PY}" show "${WORKSPACE}" --json 2>&1)" || {
  echo "[ERROR] Workspace '${WORKSPACE}' is not registered (or malformed)." >&2
  echo "${WORKSPACE_JSON}" >&2
  echo "[HINT] List available workspaces: ${HOST_PYTHON_BIN} ${WORKSPACE_PY} list" >&2
  echo "[HINT] Inspect workspace:         ${HOST_PYTHON_BIN} ${WORKSPACE_PY} show ${WORKSPACE}" >&2
  exit 12
}
# JSON から vcs / mode / repo / branch_prefix を抽出 (yaml parse は workspace.py が済ませた)
WS_VCS="$("${HOST_PYTHON_BIN}" -c "import json,sys; print(json.loads(sys.argv[1]).get('vcs',''))" "${WORKSPACE_JSON}")"
WS_MODE="$("${HOST_PYTHON_BIN}" -c "import json,sys; print(json.loads(sys.argv[1]).get('mode',''))" "${WORKSPACE_JSON}")"
WS_REPO="$("${HOST_PYTHON_BIN}" -c "import json,sys; print(json.loads(sys.argv[1]).get('repo',''))" "${WORKSPACE_JSON}")"
WS_BRANCH_PREFIX="$("${HOST_PYTHON_BIN}" -c "import json,sys; print(json.loads(sys.argv[1]).get('branch_prefix','mind'))" "${WORKSPACE_JSON}")"
# branch_prefix が空なら "mind" を fallback (= worktree branch 名が空 prefix で衝突しないため)
if [ -z "${WS_BRANCH_PREFIX}" ]; then
  WS_BRANCH_PREFIX="mind"
fi
echo "[spawn-mind]   workspace: vcs=${WS_VCS} mode=${WS_MODE} repo=${WS_REPO:-(none)} branch_prefix=${WS_BRANCH_PREFIX}"

# vcs=git/mode=worktree の事前確認: repo が git 管理下にあるか
WS_WANT_WORKTREE=0
if [ "${WS_VCS}" = "git" ] && [ "${WS_MODE}" = "worktree" ]; then
  WS_WANT_WORKTREE=1
  if [ -z "${WS_REPO}" ]; then
    echo "[ERROR] Workspace '${WORKSPACE}' has vcs=git/mode=worktree but no repo path." >&2
    echo "[HINT] Add 'repo: <path>' to the workspace template." >&2
    exit 13
  fi
  if [ ! -d "${WS_REPO}" ]; then
    echo "[ERROR] Workspace repo '${WS_REPO}' does not exist." >&2
    exit 13
  fi
  if ! git -C "${WS_REPO}" rev-parse --git-dir >/dev/null 2>&1; then
    echo "[ERROR] Workspace repo '${WS_REPO}' is not a git repository." >&2
    exit 13
  fi
  # branch 名衝突チェック (既存 branch があると worktree add が exit 128 する)
  WS_BRANCH="${WS_BRANCH_PREFIX}/${MIND_NAME}"
  if git -C "${WS_REPO}" rev-parse --verify --quiet "refs/heads/${WS_BRANCH}" >/dev/null 2>&1; then
    echo "[ERROR] Branch '${WS_BRANCH}' already exists in repo '${WS_REPO}'." >&2
    echo "[HINT] Either delete the branch first, or pick a different Mind name." >&2
    exit 13
  fi
fi

echo "[spawn-mind] Creating Mindspace: ${MIND_DIR}"
mkdir -p "${MIND_DIR}"

# Phase 5d-2 (ADR-0022): worktree モードなら Mindspace 直下に work/ subdir を作る。
# Mindspace 直下は Mind メタ (CLAUDE.md / .mcp.json / .mind-meta.md) のまま、
# work/ subdir のみが target repo の worktree。これにより target repo に
# CLAUDE.md があっても衝突しない (ADR-0022 §3 確定版)。
if [ "${WS_WANT_WORKTREE}" = "1" ]; then
  WS_WORK_DIR="${MIND_DIR}/work"
  WS_BRANCH="${WS_BRANCH_PREFIX}/${MIND_NAME}"
  echo "[spawn-mind] Creating git worktree: ${WS_WORK_DIR} (branch ${WS_BRANCH})"
  if ! git -C "${WS_REPO}" worktree add -b "${WS_BRANCH}" "${WS_WORK_DIR}" 2>&1; then
    echo "[ERROR] git worktree add failed." >&2
    echo "[HINT] Rolling back Mindspace ${MIND_DIR}" >&2
    rm -rf "${MIND_DIR}"
    exit 14
  fi
fi

echo "[spawn-mind] Installing Persona '${PERSONA}' as CLAUDE.md"
cp "${PERSONA_FILE}" "${MIND_DIR}/CLAUDE.md"

SPAWNED_AT="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"

cat > "${MIND_DIR}/.mind-meta.md" <<EOF
---
mind_name: ${MIND_NAME}
kind: ${KIND}
persona: ${PERSONA}
guild: ${GUILD}
workspace: ${WORKSPACE}
spawned_at: ${SPAWNED_AT}
phase: 1+3
---

# Mind metadata

> Phase 5c-2 P1 fix (#91): 本ファイルは Mind 自身が読み書きできる informational
> copy です。authz の根拠 (persona / guild の authoritative source) は
> \$AI_ORG_OS_HOME/registry/minds/${MIND_NAME}.md にあります。
> 本ファイルを書き換えても axiom 強制には影響しません (caller-controlled
> flag による権限昇格の防止)。

guild フィールドは Phase 5c-1 (ADR-0019) で追加。
workspace フィールドは Phase 5d-2 (ADR-0022) で追加。
EOF

# Phase 5c-2 P1 fix (#91 Codex): Mind の persona / guild の authoritative
# source は **Mindspace の外** (\$AI_ORG_OS_HOME/registry/minds/<name>.md) に
# 置く。Mindspace 内 .mind-meta.md は Mind が書き換え可能なため authz の
# 根拠にできない (権限昇格防止)。registry は Pillar 管理領域。
REGISTRY_MINDS_DIR="${RUNTIME_HOME}/registry/minds"
mkdir -p "${REGISTRY_MINDS_DIR}"
REGISTRY_ENTRY="${REGISTRY_MINDS_DIR}/${MIND_NAME}.md"
REGISTRY_TMP="${REGISTRY_ENTRY}.tmp.$$"

# atomic write: tmp に書いて rename。並行 spawn でも entry が中途半端な
# 状態で観測されないように。
cat > "${REGISTRY_TMP}" <<EOF
---
mind_name: ${MIND_NAME}
kind: ${KIND}
persona: ${PERSONA}
guild: ${GUILD}
workspace: ${WORKSPACE}
spawned_at: ${SPAWNED_AT}
---

# Mind registry entry (authoritative)

Pillar 管理領域。Mind 自身は書き換えてはならない (ADR-0011)。spawn-mind.sh /
kill-mind.sh のみが本ファイルを書き換える。

このファイルが axiom 強制 (guildmaster-only-spawn / claim-only-own-guild /
read-others-inbox-only-by-guildmaster) の根拠データとして nexus.py から
参照される。workspace フィールドは Phase 5d-2 (ADR-0022) で追加。
kill-mind は本フィールドを参照して worktree のクリーンアップ要否を判定する。
EOF
mv "${REGISTRY_TMP}" "${REGISTRY_ENTRY}"
echo "[spawn-mind] Mind registry entry: ${REGISTRY_ENTRY}"

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

# Phase 5g.B #171: --restore-from が指定されていたら preserved snapshot から
# state.md / notes/ を Mindspace に copy する。CLAUDE.md / .mcp.json / workspace
# は復元しない (= Persona / Workspace から fresh、operator が選んだ binding を尊重)。
# 復元元 path が存在しない / 内容無し → WARN + 継続 (fresh spawn と等価)。
if [ -n "${RESTORE_FROM}" ]; then
  if [ ! -d "${RESTORE_FROM}" ]; then
    echo "[spawn-mind] WARN: --restore-from '${RESTORE_FROM}' is not a directory, skipping" >&2
  else
    RESTORED_ANY=0
    if [ -f "${RESTORE_FROM}/state.md" ]; then
      cp "${RESTORE_FROM}/state.md" "${MIND_DIR}/state.md" 2>/dev/null \
        && { echo "[restore] state.md <- ${RESTORE_FROM}/state.md"; RESTORED_ANY=1; } \
        || echo "[restore] WARN: copy state.md failed" >&2
    fi
    if [ -d "${RESTORE_FROM}/notes" ]; then
      cp -R "${RESTORE_FROM}/notes" "${MIND_DIR}/notes" 2>/dev/null \
        && { echo "[restore] notes/ <- ${RESTORE_FROM}/notes/"; RESTORED_ANY=1; } \
        || echo "[restore] WARN: copy notes/ failed" >&2
    fi
    if [ "${RESTORED_ANY}" = "0" ]; then
      echo "[spawn-mind] WARN: --restore-from '${RESTORE_FROM}' had no state.md or notes/, Mindspace stays fresh" >&2
    fi
  fi
fi

echo "[spawn-mind] Mind '${MIND_NAME}' is ready at ${MIND_DIR}"
if [ "${WS_WANT_WORKTREE}" = "1" ]; then
  echo "[spawn-mind]   workspace: '${WORKSPACE}' (vcs=git, worktree at ${MIND_DIR}/work on branch ${WS_BRANCH})"
fi

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
  if [ "${WS_WANT_WORKTREE}" = "1" ]; then
    echo ""
    echo "Code work directory (git worktree):"
    echo "  cd ${MIND_DIR}/work    # on branch ${WS_BRANCH}, target repo = ${WS_REPO}"
  fi
  echo ""
  echo "Or start the external loop (ADR-0010):"
  echo "  ${SCRIPT_DIR}/mind-loop.sh ${MIND_NAME}"
fi
echo ""
echo "Nexus が提供する tool:"
echo "  - send_dispatch / read_inbox / ack_dispatch"
echo "  Mind は他 Mind の Mindspace を直接触れません。すべての通信は Nexus 経由です（Axiom）。"
