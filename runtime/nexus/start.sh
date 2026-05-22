#!/usr/bin/env bash
#
# start.sh — Nexus を手動起動する（venv 作成 + 依存インストール + サーバー起動）。
#
# 通常運用では Mind 内の Claude が `.mcp.json` 経由で stdio として
# Nexus を自動起動するため、本スクリプトは不要。
# 以下のような場面で使う:
#   - Nexus 単体の動作確認
#   - 別 transport（将来の HTTP/SSE）で常駐させたい
#   - venv に依存を閉じ込めてホストの Python 環境を汚さない
#
# 用法:
#   ./runtime/nexus/start.sh                  # 起動（デフォルトの stdio transport）
#   ./runtime/nexus/start.sh --setup-only     # venv 作成と依存インストールまで
#   ./runtime/nexus/start.sh --recreate-venv  # 既存 venv を破棄して作り直し
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="${SCRIPT_DIR}/.venv"
REQUIREMENTS="${SCRIPT_DIR}/requirements.txt"
NEXUS_PY="${SCRIPT_DIR}/nexus.py"

PYTHON_BIN="${AI_ORG_OS_PYTHON:-python3}"
SETUP_ONLY=0
RECREATE=0

# ----- args ------------------------------------------------------------------
for arg in "$@"; do
  case "${arg}" in
    --setup-only)
      SETUP_ONLY=1
      ;;
    --recreate-venv)
      RECREATE=1
      ;;
    -h|--help)
      sed -n '2,20p' "$0" | sed 's/^# \{0,1\}//'
      exit 0
      ;;
    *)
      echo "[start.sh][ERROR] unknown argument: ${arg}" >&2
      echo "[HINT] try --help" >&2
      exit 1
      ;;
  esac
done

# ----- python check (環境依存検証: pr-self-review checklist 項目 2) -----------
if ! command -v "${PYTHON_BIN}" >/dev/null 2>&1; then
  echo "[start.sh][ERROR] python command '${PYTHON_BIN}' not found in PATH." >&2
  echo "[HINT] Install Python 3.10+ or set AI_ORG_OS_PYTHON to your python path." >&2
  exit 2
fi

if [ ! -f "${NEXUS_PY}" ]; then
  echo "[start.sh][ERROR] nexus.py not found at ${NEXUS_PY}" >&2
  exit 3
fi

if [ ! -f "${REQUIREMENTS}" ]; then
  echo "[start.sh][ERROR] requirements.txt not found at ${REQUIREMENTS}" >&2
  exit 4
fi

# ----- venv 作成 + 依存インストール（冪等: pr-self-review checklist 項目 1） --
if [ "${RECREATE}" = "1" ] && [ -d "${VENV_DIR}" ]; then
  echo "[start.sh] Removing existing venv: ${VENV_DIR}"
  rm -rf "${VENV_DIR}"
fi

if [ ! -d "${VENV_DIR}" ]; then
  echo "[start.sh] Creating venv at ${VENV_DIR}"
  "${PYTHON_BIN}" -m venv "${VENV_DIR}"
fi

# venv の python を使う（path に . を含まない安全な activate 代替）
VENV_PYTHON="${VENV_DIR}/bin/python"
if [ ! -x "${VENV_PYTHON}" ]; then
  # Windows (Git Bash) フォールバック
  VENV_PYTHON="${VENV_DIR}/Scripts/python.exe"
fi
if [ ! -x "${VENV_PYTHON}" ]; then
  echo "[start.sh][ERROR] venv python not found under ${VENV_DIR}" >&2
  exit 5
fi

echo "[start.sh] Installing requirements (idempotent)"
"${VENV_PYTHON}" -m pip install --upgrade pip >/dev/null
"${VENV_PYTHON}" -m pip install -r "${REQUIREMENTS}"

if [ "${SETUP_ONLY}" = "1" ]; then
  echo "[start.sh] Setup complete. To run Nexus: ${VENV_PYTHON} ${NEXUS_PY}"
  exit 0
fi

# ----- 起動 ------------------------------------------------------------------
echo "[start.sh] Launching Nexus (stdio transport)"
echo "[start.sh] To exit: Ctrl-C"
exec "${VENV_PYTHON}" "${NEXUS_PY}"
