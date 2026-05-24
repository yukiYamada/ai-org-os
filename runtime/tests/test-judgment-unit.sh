#!/usr/bin/env bash
#
# test-judgment-unit.sh — Judgment Pillar の Python unittest を呼ぶラッパー。
#
# 軸:
#   - anthropic SDK 未インストール環境でも動く（client を mock するため）
#   - API key 不要（実 API は叩かない）
#
# 実 API を使った統合テストは将来 RUN_ANTHROPIC_TESTS=1 で別枠を設ける。
#
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
JUDGMENT_DIR="$(cd "${SCRIPT_DIR}/../pillars/judgment" && pwd)"

if ! command -v python3 >/dev/null 2>&1 && ! command -v python >/dev/null 2>&1; then
  echo "[skip] python not found; skipping Judgment unit tests."
  exit 0
fi

PYTHON_BIN="$(command -v python3 || command -v python)"

cd "${JUDGMENT_DIR}"
"${PYTHON_BIN}" -m unittest discover -p 'test_*.py' -v 2>&1
