#!/usr/bin/env bash
#
# test-warden-e2e.sh — Warden 全体 (Conductor + Inbox + Observation + Judgment)
# の End-to-End スモークテスト (Phase 5b-1 / #71)。
#
# シナリオ:
#   1. Inbox に Issue を 1 件投入 (inbox.py submit)
#   2. Conductor を 2 cycle 動かす (env で max=2, period=0)
#   3. conductor-status.json が書かれていて pending Issue が認識されている
#   4. snapshot ファイルが生成されている
#   5. observe.py --realm が各セクションを含む
#
# Anthropic SDK の API は叩かない (Mind 0 件なら Judgment は skipped で OK)。
#
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RUNTIME_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

if ! command -v python3 >/dev/null 2>&1; then
  echo "[skip] python3 not found; skipping Warden E2E."
  exit 0
fi

TMP_DIR="$(mktemp -d)"
TMP_ISSUES="${TMP_DIR}/issues"
TMP_SNAPSHOTS="${TMP_DIR}/snapshots"
TMP_STATUS="${TMP_DIR}/conductor-status.json"

cleanup() {
  rm -rf "${TMP_DIR}"
}
trap cleanup EXIT

PASS=0
FAIL=0
FAIL_MSGS=()

assert() {
  local label="$1" cond="$2"
  if [ "${cond}" = "1" ]; then
    PASS=$((PASS + 1))
    echo "  [ok]   ${label}"
  else
    FAIL=$((FAIL + 1))
    FAIL_MSGS+=("${label}")
    echo "  [NG]   ${label}"
  fi
}

echo "[case] 1. inbox.py submit で Issue を投入"
issue_id="$(python3 "${RUNTIME_DIR}/pillars/inbox/inbox.py" \
              --issues-dir "${TMP_ISSUES}" \
              submit "smoke test issue" --body "hello warden" --priority p2 \
              --submitter "e2e-test" 2>&1 | tail -1)"
echo "  submitted: ${issue_id}"
if [ -f "${TMP_ISSUES}/inbox/${issue_id}.md" ]; then
  assert "issue file in inbox" 1
else
  assert "issue file in inbox" 0
fi

echo "[case] 2. Conductor を 2 cycle (period=0, max=2) 走らせる"
# env で path / cycle 数を差し替え。conductor.py が __main__ で env を読む。
AI_ORG_OS_CONDUCTOR_PERIOD=0 \
AI_ORG_OS_CONDUCTOR_MAX_CYCLES=2 \
AI_ORG_OS_CONDUCTOR_STATUS_PATH="${TMP_STATUS}" \
AI_ORG_OS_CONDUCTOR_ISSUES_DIR="${TMP_ISSUES}" \
AI_ORG_OS_CONDUCTOR_SNAPSHOTS_DIR="${TMP_SNAPSHOTS}" \
  python3 "${RUNTIME_DIR}/pillars/conductor/conductor.py" 2>&1 | sed 's/^/  /'
rc=${PIPESTATUS[0]}
if [ "${rc}" -eq 0 ]; then
  assert "conductor exit 0" 1
else
  assert "conductor exit 0 (got ${rc})" 0
fi

echo "[case] 3. conductor-status.json が書かれた"
if [ -f "${TMP_STATUS}" ]; then
  assert "status JSON exists" 1
else
  assert "status JSON exists" 0
fi

status_check="$(python3 - "${TMP_STATUS}" <<'PY' 2>&1
import json, sys
from pathlib import Path
p = Path(sys.argv[1])
if not p.is_file():
    print("MISSING")
else:
    d = json.loads(p.read_text(encoding="utf-8"))
    cycle = d.get("last_cycle", {})
    print(
        f"total={d.get('total_cycles')}",
        f"cycle={cycle.get('cycle')}",
        f"pending={cycle.get('pending_issues')}",
        f"snap={'yes' if cycle.get('snapshot_path') else 'no'}",
        f"judgment={cycle.get('judgment_status')}",
    )
PY
)"
echo "  ${status_check}"
if echo "${status_check}" | grep -q "total=2"; then
  assert "total_cycles == 2" 1
else
  assert "total_cycles == 2" 0
fi
if echo "${status_check}" | grep -q "pending=1"; then
  assert "pending_issues == 1 (smoke issue 未 claim)" 1
else
  assert "pending_issues == 1 (smoke issue 未 claim)" 0
fi

echo "[case] 4. snapshot ファイルが生成されている"
snap_count="$(find "${TMP_SNAPSHOTS}" -maxdepth 1 -name '*.json' -type f 2>/dev/null | wc -l | tr -d ' ')"
if [ "${snap_count}" -gt 0 ]; then
  assert "snapshot json under tmp_snapshots (${snap_count} files)" 1
else
  assert "snapshot json under tmp_snapshots (${snap_count} files)" 0
fi

echo "[case] 5. observe.py --realm が動作する (各セクションを含む)"
realm_out="$(python3 "${RUNTIME_DIR}/pillars/observation/observe.py" --realm 2>&1)"
if echo "${realm_out}" | grep -qE "Realm Observatory"; then
  assert "--realm: Realm Observatory section" 1
else
  assert "--realm: Realm Observatory section" 0
fi
if echo "${realm_out}" | grep -qE "Inbox Queue"; then
  assert "--realm: Inbox Queue section" 1
else
  assert "--realm: Inbox Queue section" 0
fi
if echo "${realm_out}" | grep -qE "Conductor"; then
  assert "--realm: Conductor section" 1
else
  assert "--realm: Conductor section" 0
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
