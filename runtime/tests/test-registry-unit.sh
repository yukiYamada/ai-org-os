#!/usr/bin/env bash
#
# test-registry-unit.sh — Registry Pillar の Python unittest を呼ぶラッパー。
# registry.py は標準ライブラリのみで動くので、依存追加は不要。
#
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REGISTRY_DIR="$(cd "${SCRIPT_DIR}/../pillars/registry" && pwd)"

if ! command -v python3 >/dev/null 2>&1 && ! command -v python >/dev/null 2>&1; then
  echo "[skip] python not found; skipping Registry unit tests."
  exit 0
fi

PYTHON_BIN="$(command -v python3 || command -v python)"

cd "${REGISTRY_DIR}"
# unittest discover で test_*.py を全部拾う。
# registry.py をモジュールとして import するため CWD は維持。
"${PYTHON_BIN}" -m unittest discover -p 'test_*.py' -v 2>&1
