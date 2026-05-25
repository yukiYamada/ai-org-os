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
# test_storage: std lib only, always runs.
# test_nexus_tool: nexus.py 経由で MCP tool 層を検証。mcp パッケージが
#   無ければファイル内で skip するため、ホスト python に mcp が入って
#   いない環境でも safe (Phase 5c-1 / ADR-0019)。
"${PYTHON_BIN}" -m unittest test_storage test_nexus_tool -v 2>&1
