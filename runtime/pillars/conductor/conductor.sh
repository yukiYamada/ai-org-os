#!/usr/bin/env bash
#
# conductor.sh — Conductor Pillar 起動ラッパー (docker-compose CMD 用)。
#
# Realm container 内で python3 conductor.py を起動するだけのシム。
# python の場所が distro 依存で振れることへの吸収レイヤー。
#
# 環境変数:
#   AI_ORG_OS_PYTHON              python の差し替え (デフォルト: python3)
#   AI_ORG_OS_CONDUCTOR_PERIOD    cycle 周期秒 (デフォルト: 30)
#   AI_ORG_OS_CONDUCTOR_MAX_CYCLES  上限 cycle 数 (デフォルト: 0 = 無限、テスト用)
#   ANTHROPIC_API_KEY             Judgment Pillar 用。未設定でも Conductor は
#                                 動く (fallback ルート、ADR-0013 §1 F3 整合)
#
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONDUCTOR_PY="${SCRIPT_DIR}/conductor.py"

PYTHON_BIN="${AI_ORG_OS_PYTHON:-python3}"

if ! command -v "${PYTHON_BIN}" >/dev/null 2>&1; then
  echo "[conductor.sh] ERROR: ${PYTHON_BIN} not found in PATH" >&2
  exit 2
fi

if [ ! -f "${CONDUCTOR_PY}" ]; then
  echo "[conductor.sh] ERROR: conductor.py not found at ${CONDUCTOR_PY}" >&2
  exit 3
fi

echo "[conductor.sh] launching ${PYTHON_BIN} ${CONDUCTOR_PY}"
exec "${PYTHON_BIN}" "${CONDUCTOR_PY}"
