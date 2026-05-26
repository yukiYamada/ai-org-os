#!/usr/bin/env bash
#
# test-kill-mind.sh — kill-mind.sh の振る舞いを検証する。
#
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RUNTIME_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
# Phase 5a-2: Lifecycle Pillar is at runtime/pillars/lifecycle/ (ADR-0011).
SPAWN="${RUNTIME_DIR}/pillars/lifecycle/spawn-mind.sh"
KILL="${RUNTIME_DIR}/pillars/lifecycle/kill-mind.sh"

TEST_ID="kt$$-$(date +%s)"
PASS=0
FAIL=0
FAIL_MSGS=()

# Phase 5b-3 (#78): spawn-mind 経由のため stub host config を準備
TEST_TMP_DIR="$(mktemp -d)"
. "${SCRIPT_DIR}/_lib_host_stub.sh"
stub_host_config_init "${TEST_TMP_DIR}"

cleanup() {
  find "${AI_ORG_OS_HOME}/minds" -maxdepth 1 -type d -name "${TEST_ID}-*" -exec rm -rf {} + 2>/dev/null || true
  rm -rf "${TEST_TMP_DIR}"
}
trap cleanup EXIT

assert_exit_code() {
  local label="$1" expected="$2" actual="$3"
  if [ "${actual}" = "${expected}" ]; then
    PASS=$((PASS + 1))
    echo "  [ok]   ${label}: exit ${actual}"
  else
    FAIL=$((FAIL + 1))
    FAIL_MSGS+=("${label}: expected exit ${expected}, got ${actual}")
    echo "  [NG]   ${label}: expected exit ${expected}, got ${actual}"
  fi
}

assert_dir_absent() {
  local label="$1" path="$2"
  if [ ! -e "${path}" ]; then
    PASS=$((PASS + 1))
    echo "  [ok]   ${label}: removed"
  else
    FAIL=$((FAIL + 1))
    FAIL_MSGS+=("${label}: still exists at ${path}")
    echo "  [NG]   ${label}: still exists ${path}"
  fi
}

echo "[case] 1. 引数不足は exit 1"
set +e; "${KILL}" >/dev/null 2>&1; code=$?; set -e
assert_exit_code "no args" 1 "${code}"

echo "[case] 2. 存在しない Mind は exit 2"
set +e; "${KILL}" "${TEST_ID}-ghost" >/dev/null 2>&1; code=$?; set -e
assert_exit_code "missing mind" 2 "${code}"

echo "[case] 3. 正常系: spawn → kill で Mindspace が消える"
mind="${TEST_ID}-target"
"${SPAWN}" generic designer "${mind}" >/dev/null
mind_dir="${AI_ORG_OS_HOME}/minds/${mind}"
if [ ! -d "${mind_dir}" ]; then
  FAIL=$((FAIL + 1))
  FAIL_MSGS+=("setup: spawn failed before kill test")
  echo "  [NG]   setup: spawn failed"
else
  registry_entry="${AI_ORG_OS_HOME}/registry/minds/${mind}.md"
  # 前提: spawn-mind が registry にも書いてる
  if [ ! -f "${registry_entry}" ]; then
    FAIL=$((FAIL + 1))
    FAIL_MSGS+=("setup: registry entry was not created by spawn-mind")
    echo "  [NG]   setup: registry entry missing before kill"
  fi
  set +e; "${KILL}" "${mind}" >/dev/null 2>&1; code=$?; set -e
  assert_exit_code "happy kill" 0 "${code}"
  assert_dir_absent "Mindspace gone" "${mind_dir}"
  # Phase 5c-2 P1 fix (#91): kill-mind は registry エントリも削除する。
  if [ ! -f "${registry_entry}" ]; then
    PASS=$((PASS + 1))
    echo "  [ok]   registry entry removed (authoritative cleanup)"
  else
    FAIL=$((FAIL + 1))
    FAIL_MSGS+=("kill-mind left registry entry behind: ${registry_entry}")
    echo "  [NG]   registry entry not removed"
  fi
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
