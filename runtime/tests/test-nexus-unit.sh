#!/usr/bin/env bash
#
# test-nexus-unit.sh — Nexus storage 層の Python unittest を呼ぶ bash ラッパー。
# mcp パッケージ不要（storage.py は標準ライブラリのみ）。
#
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
NEXUS_DIR="$(cd "${SCRIPT_DIR}/../pillars/conduit" && pwd)"

if ! command -v python3 >/dev/null 2>&1 && ! command -v python >/dev/null 2>&1; then
  echo "[skip] python not found; skipping Nexus unit tests."
  exit 0
fi

PYTHON_BIN="$(command -v python3 || command -v python)"

cd "${NEXUS_DIR}"
"${PYTHON_BIN}" -m unittest test_storage -v 2>&1
