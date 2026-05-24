#!/usr/bin/env bash
#
# test-conductor-unit.sh — Conductor Pillar の Python unittest ラッパー。
#
# Anthropic SDK / API key 不要 (client mock 経由)。
#
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONDUCTOR_DIR="$(cd "${SCRIPT_DIR}/../pillars/conductor" && pwd)"

if ! command -v python3 >/dev/null 2>&1 && ! command -v python >/dev/null 2>&1; then
  echo "[skip] python not found; skipping Conductor unit tests."
  exit 0
fi

PYTHON_BIN="$(command -v python3 || command -v python)"

cd "${CONDUCTOR_DIR}"
"${PYTHON_BIN}" -m unittest discover -p 'test_*.py' -v 2>&1
