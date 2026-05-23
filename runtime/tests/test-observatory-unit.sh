#!/usr/bin/env bash
#
# test-observatory-unit.sh — Realm Observatory の Python unittest を呼ぶラッパー。
# mind_status.py は標準ライブラリのみで動くので、mcp も他依存も不要。
#
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OBSERVATORY_DIR="$(cd "${SCRIPT_DIR}/../observatory" && pwd)"

if ! command -v python3 >/dev/null 2>&1 && ! command -v python >/dev/null 2>&1; then
  echo "[skip] python not found; skipping Observatory unit tests."
  exit 0
fi

PYTHON_BIN="$(command -v python3 || command -v python)"

cd "${OBSERVATORY_DIR}"
"${PYTHON_BIN}" -m unittest test_mind_status -v 2>&1
