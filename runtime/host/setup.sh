#!/usr/bin/env bash
#
# runtime/host/setup.sh — ai-org-os のホスト側セットアップ
# (Phase 5b-3 #78 で導入、Phase 5b-4 #81 で AI_ORG_OS_HOME 対応)
#
# 1 回叩く: $AI_ORG_OS_HOME (default $HOME/.ai-org-os) を初期化し、
# Mind / Conductor / Inbox / Conduit 等のすべての runtime state がそこに集まる構造を作る。
#
# やること:
#   1. 前提検証 (python3 / claude / pip)
#   2. $AI_ORG_OS_HOME の解決 (env or default)
#   3. ディレクトリ骨格作成:
#       $AI_ORG_OS_HOME/{venv, minds, issues/{inbox,archive},
#                       snapshots, conduit-storage/{inbox,archive}}
#   4. $AI_ORG_OS_HOME/venv/ 作成 + mcp install
#   5. OS ネイティブのパス解決 (Windows: C:/..., Unix: 通常絶対パス)
#   6. $AI_ORG_OS_HOME/config.env を atomic に書き出す
#       AI_ORG_OS_HOME=...
#       HOST_PYTHON_BIN=...
#       HOST_NEXUS_PY=...
#       HOST_SETUP_AT=...
#
# やらないこと:
#   - claude code login (ユーザー責任、ADR-0012 §2 責務 3)
#   - ANTHROPIC_API_KEY 設定 (人間が外から渡す、ADR-0016)
#   - Docker / Realm Container の起動 (ADR-0014 §3 D = 人間制御領域)
#
# 関連:
#   - ADR-0014 §3 (Realm 物理境界)
#   - ADR-0016 (Container = コア / ホスト = Mind)
#   - ADR-0018 (framework / runtime state 物理分離) ← 本 setup の根拠
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RUNTIME_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

# AI_ORG_OS_HOME を解決。env で渡されてればそれ、無ければ $HOME/.ai-org-os/。
# Phase 5b-4 (#81 / ADR-0018) で導入された runtime state の root。
DEFAULT_HOME="${HOME:-${USERPROFILE:-}}/.ai-org-os"
RUNTIME_HOME="${AI_ORG_OS_HOME:-${DEFAULT_HOME}}"

RECREATE_VENV=0
while [ "$#" -gt 0 ]; do
  case "$1" in
    --recreate-venv)
      RECREATE_VENV=1
      shift
      ;;
    -h|--help)
      cat <<HELP
Usage: $0 [--recreate-venv]

Bootstrap host-side prerequisites for ai-org-os.

Environment:
  AI_ORG_OS_HOME    runtime state root (default: \$HOME/.ai-org-os/)

Options:
  --recreate-venv   既存 venv を削除して作り直す (mcp の major upgrade 等)

After running this, you can:
  - bash runtime/pillars/lifecycle/spawn-mind.sh <kind> <persona> <name>
  - cd runtime/realm && docker compose up -d --build
HELP
      exit 0
      ;;
    *)
      echo "[setup] unknown option: $1" >&2
      exit 1
      ;;
  esac
done

echo "[setup] ai-org-os host setup starting"
echo "[setup]   runtime dir  (framework / immutable): ${RUNTIME_DIR}"
echo "[setup]   runtime home (state / mutable):       ${RUNTIME_HOME}"

# ----- 1. 前提検証 -----

if ! command -v python3 >/dev/null 2>&1; then
  echo "[setup][ERROR] python3 not found in PATH." >&2
  echo "[setup][HINT] Install Python 3.10+ first." >&2
  exit 2
fi

PY_VER="$(python3 --version 2>&1 | head -1)"
echo "[setup]   python: ${PY_VER}"

if ! command -v claude >/dev/null 2>&1; then
  echo "[setup][WARN] claude CLI not found in PATH." >&2
  echo "[setup][WARN] Mind processes won't launch until claude is installed and logged in (ADR-0016)." >&2
fi

# ----- 2. ディレクトリ骨格作成 -----

VENV_DIR="${RUNTIME_HOME}/venv"
CONFIG_PATH="${RUNTIME_HOME}/config.env"

echo "[setup]   creating directory structure under ${RUNTIME_HOME}"
mkdir -p "${RUNTIME_HOME}"
mkdir -p "${RUNTIME_HOME}/minds"
mkdir -p "${RUNTIME_HOME}/issues/inbox"
mkdir -p "${RUNTIME_HOME}/issues/archive"
mkdir -p "${RUNTIME_HOME}/snapshots"
mkdir -p "${RUNTIME_HOME}/conduit-storage/inbox"
mkdir -p "${RUNTIME_HOME}/conduit-storage/archive"

# ----- 3. venv 作成 -----

if [ "${RECREATE_VENV}" = "1" ] && [ -d "${VENV_DIR}" ]; then
  echo "[setup]   removing existing venv at ${VENV_DIR}"
  rm -rf "${VENV_DIR}"
fi

if [ ! -d "${VENV_DIR}" ]; then
  echo "[setup]   creating venv at ${VENV_DIR}"
  python3 -m venv "${VENV_DIR}"
else
  echo "[setup]   reusing existing venv at ${VENV_DIR}"
fi

# venv の python と pip の実体を OS 別に解決
if [ -x "${VENV_DIR}/Scripts/python.exe" ]; then
  VENV_PY="${VENV_DIR}/Scripts/python.exe"
  VENV_PIP="${VENV_DIR}/Scripts/pip.exe"
elif [ -x "${VENV_DIR}/bin/python" ]; then
  VENV_PY="${VENV_DIR}/bin/python"
  VENV_PIP="${VENV_DIR}/bin/pip"
else
  echo "[setup][ERROR] venv python not found under ${VENV_DIR}" >&2
  exit 3
fi

# ----- 4. mcp install -----

echo "[setup]   installing mcp into venv (quiet)"
"${VENV_PIP}" install --quiet --disable-pip-version-check "mcp>=1.0"

# mcp が import できることを確認
if ! "${VENV_PY}" -c "import mcp" 2>/dev/null; then
  echo "[setup][ERROR] mcp import failed after install" >&2
  exit 4
fi
echo "[setup]   mcp install ok"

# ----- 5. OS ネイティブのパス解決 -----

# pathlib.Path.as_posix() で forward-slash 形式の絶対パス。
# Windows: C:/Users/.../python.exe (Claude Code on Windows が受理可能)
# Unix:    /home/.../python (通常通り)
HOST_PYTHON_BIN="$("${VENV_PY}" - <<'PY'
from pathlib import Path
import sys
print(Path(sys.executable).resolve().as_posix())
PY
)"

HOST_RUNTIME_DIR_RESOLVED="$(python3 - "${RUNTIME_DIR}" <<'PY'
from pathlib import Path
import sys
print(Path(sys.argv[1]).resolve().as_posix())
PY
)"

HOST_RUNTIME_HOME_RESOLVED="$(python3 - "${RUNTIME_HOME}" <<'PY'
from pathlib import Path
import sys
print(Path(sys.argv[1]).resolve().as_posix())
PY
)"

HOST_NEXUS_PY="${HOST_RUNTIME_DIR_RESOLVED}/pillars/conduit/nexus.py"

if [ ! -f "${HOST_NEXUS_PY}" ]; then
  echo "[setup][ERROR] nexus.py not found at expected path: ${HOST_NEXUS_PY}" >&2
  exit 5
fi

# ----- 6. config.env を atomic に書き出す -----

SETUP_AT="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"
TMP_CONFIG="${CONFIG_PATH}.tmp.$$"

cat > "${TMP_CONFIG}" <<CONFIG
# Generated by runtime/host/setup.sh — do not edit by hand.
# Re-run setup.sh to regenerate. --recreate-venv で venv を作り直す。
#
# Phase 5b-4 (#81 / ADR-0018) で AI_ORG_OS_HOME ベースに統一された。

AI_ORG_OS_HOME=${HOST_RUNTIME_HOME_RESOLVED}
HOST_PYTHON_BIN=${HOST_PYTHON_BIN}
HOST_RUNTIME_DIR=${HOST_RUNTIME_DIR_RESOLVED}
HOST_NEXUS_PY=${HOST_NEXUS_PY}
HOST_SETUP_AT=${SETUP_AT}
CONFIG

mv -f "${TMP_CONFIG}" "${CONFIG_PATH}"

echo "[setup] OK. ${CONFIG_PATH} written:"
sed 's/^/[setup]   /' "${CONFIG_PATH}"

echo ""
echo "[setup] Next steps:"
echo "[setup]   1. (任意) export ANTHROPIC_API_KEY=... if you want Judgment Pillar to use real Claude"
echo "[setup]   2. cd runtime/realm && docker compose up -d --build   (Conductor が回り始める)"
echo "[setup]   3. bash runtime/pillars/inbox/submit-issue.sh \"title\" \"body\""
echo "[setup]   4. bash runtime/pillars/lifecycle/spawn-mind.sh generic designer alice"
echo "[setup]   5. cd \"\${AI_ORG_OS_HOME:-\$HOME/.ai-org-os}/minds/alice\" && claude   (Mind が走り出す)"
