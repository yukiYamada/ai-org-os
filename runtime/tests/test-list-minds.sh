#!/usr/bin/env bash
#
# test-list-minds.sh — list-minds.sh の振る舞いを検証する。
#
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RUNTIME_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
# Phase 5a-2: Lifecycle Pillar is at runtime/pillars/lifecycle/ (ADR-0011).
SPAWN="${RUNTIME_DIR}/pillars/lifecycle/spawn-mind.sh"
KILL="${RUNTIME_DIR}/pillars/lifecycle/kill-mind.sh"
LIST="${RUNTIME_DIR}/pillars/lifecycle/list-minds.sh"

TEST_ID="lt$$-$(date +%s)"
PASS=0
FAIL=0
FAIL_MSGS=()

cleanup() {
  find "${RUNTIME_DIR}/minds" -maxdepth 1 -type d -name "${TEST_ID}-*" -exec rm -rf {} + 2>/dev/null || true
}
trap cleanup EXIT

assert_exit_code() {
  local label="$1" expected="$2" actual="$3"
  if [ "${actual}" = "${expected}" ]; then
    PASS=$((PASS + 1)); echo "  [ok]   ${label}: exit ${actual}"
  else
    FAIL=$((FAIL + 1)); FAIL_MSGS+=("${label}: expected exit ${expected}, got ${actual}")
    echo "  [NG]   ${label}: expected exit ${expected}, got ${actual}"
  fi
}

assert_contains() {
  local label="$1" haystack="$2" needle="$3"
  if echo "${haystack}" | grep -qF -- "${needle}"; then
    PASS=$((PASS + 1)); echo "  [ok]   ${label}: contains '${needle}'"
  else
    FAIL=$((FAIL + 1)); FAIL_MSGS+=("${label}: missing '${needle}'")
    echo "  [NG]   ${label}: missing '${needle}'"
  fi
}

echo "[case] 1. list は引数なしで exit 0"
set +e; out=$("${LIST}" 2>&1); code=$?; set -e
assert_exit_code "no args" 0 "${code}"

echo "[case] 2. spawn した Mind が一覧に出る"
mind="${TEST_ID}-listed"
"${SPAWN}" generic designer "${mind}" >/dev/null
set +e; out=$("${LIST}" 2>&1); code=$?; set -e
assert_exit_code "list after spawn" 0 "${code}"
assert_contains "name shown" "${out}" "${mind}"
assert_contains "kind shown" "${out}" "generic"
assert_contains "persona shown" "${out}" "designer"
assert_contains "header NAME" "${out}" "NAME"
assert_contains "header SPAWNED_AT" "${out}" "SPAWNED_AT"

echo "[case] 3. kill 後は一覧から消える"
"${KILL}" "${mind}" >/dev/null
set +e; out=$("${LIST}" 2>&1); code=$?; set -e
assert_exit_code "list after kill" 0 "${code}"
if echo "${out}" | grep -qF -- "${mind}"; then
  FAIL=$((FAIL + 1)); FAIL_MSGS+=("killed mind still appears: ${mind}")
  echo "  [NG]   killed mind still appears"
else
  PASS=$((PASS + 1)); echo "  [ok]   killed mind not listed"
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
