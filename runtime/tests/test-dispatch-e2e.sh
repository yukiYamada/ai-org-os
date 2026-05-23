#!/usr/bin/env bash
#
# test-dispatch-e2e.sh — Dispatch の end-to-end（storage 層ベース）。
#
# Python の Nexus class を直接呼んで、send → inbox 出現 → ack → archive 移動
# の流れをホストファイルシステムで検証する。
# MCP サーバーは起動しない（MCP クライアントが必要なので CI で再現困難）。
# storage 層を直接呼ぶことで Dispatch の振る舞いを保証する。
#
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
NEXUS_DIR="$(cd "${SCRIPT_DIR}/../pillars/conduit" && pwd)"

if ! command -v python3 >/dev/null 2>&1 && ! command -v python >/dev/null 2>&1; then
  echo "[skip] python not found; skipping dispatch e2e."
  exit 0
fi

PYTHON_BIN="$(command -v python3 || command -v python)"

# tmp ディレクトリ作成（共有ストレージとして使う）
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "${TMP_DIR}"' EXIT

PASS=0
FAIL=0
FAIL_MSGS=()

assert() {
  local label="$1" ok="$2"
  if [ "${ok}" = "1" ]; then
    PASS=$((PASS + 1)); echo "  [ok]   ${label}"
  else
    FAIL=$((FAIL + 1)); FAIL_MSGS+=("${label}")
    echo "  [NG]   ${label}"
  fi
}

# Python ワンライナーで Nexus class を使って E2E
echo "[case] E2E: send → read → ack → archive"

RESULT=$(cd "${NEXUS_DIR}" && "${PYTHON_BIN}" - <<PY 2>&1
import sys, json
from pathlib import Path
sys.path.insert(0, ".")
from storage import Nexus

tmp = Path("${TMP_DIR}")
nx = Nexus(storage_dir=tmp)

# 1. send
r1 = nx.send_dispatch(from_mind="alice", to_mind="bob", topic="hi", body="hello bob")
assert r1["ok"], "send failed"
msg_id = r1["msg_id"]

# 2. read (1 件あるはず)
r2 = nx.read_inbox(mind_name="bob")
assert r2["count"] == 1, f"expected 1 message, got {r2['count']}"
assert "hello bob" in r2["messages"][0]["content"], "body missing"

# 3. inbox にファイルがある（archive にはまだない）
inbox_path = tmp / "inbox" / "bob" / f"{msg_id}.md"
archive_path = tmp / "archive" / "bob" / f"{msg_id}.md"
assert inbox_path.exists(), "inbox file not found"
assert not archive_path.exists(), "archive should be empty"

# 4. ack
r3 = nx.ack_dispatch(mind_name="bob", msg_id=msg_id)
assert r3["ok"], f"ack failed: {r3}"

# 5. archive に移動
assert not inbox_path.exists(), "inbox should be empty after ack"
assert archive_path.exists(), "archive file not found"

# 6. read で 0 件
r4 = nx.read_inbox(mind_name="bob")
assert r4["count"] == 0, f"expected 0 after ack, got {r4['count']}"

# 7. alice の inbox は変化していない（他 Mind に影響しない）
r5 = nx.read_inbox(mind_name="alice")
assert r5["count"] == 0, "alice inbox should be empty"

print("E2E_OK")
PY
)

if echo "${RESULT}" | grep -q "E2E_OK"; then
  assert "send → read → ack → archive full cycle" 1
else
  echo "${RESULT}" | sed 's/^/    /'
  assert "send → read → ack → archive full cycle" 0
fi

echo ""
echo "[summary] passed: ${PASS}, failed: ${FAIL}"
if [ "${FAIL}" -gt 0 ]; then
  echo "[summary] failures:"
  for msg in "${FAIL_MSGS[@]}"; do
    echo "  - ${msg}"
  done
  exit 1
fi
