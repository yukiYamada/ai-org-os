#!/usr/bin/env bash
#
# test-inbox-unit.sh — Inbox Pillar の Python unittest を呼ぶラッパー。
# inbox.py は標準ライブラリのみで動くので、mcp も他依存も不要。
#
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INBOX_DIR="$(cd "${SCRIPT_DIR}/../pillars/inbox" && pwd)"

if ! command -v python3 >/dev/null 2>&1 && ! command -v python >/dev/null 2>&1; then
  echo "[skip] python not found; skipping Inbox unit tests."
  exit 0
fi

PYTHON_BIN="$(command -v python3 || command -v python)"

cd "${INBOX_DIR}"
# unittest discover で test_*.py を全部拾う（test_inbox 等）。
# inbox.py をモジュールとして import するため CWD は維持。
"${PYTHON_BIN}" -m unittest discover -p 'test_*.py' -v 2>&1
