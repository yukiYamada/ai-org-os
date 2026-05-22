#!/usr/bin/env bash
#
# test-spawn-mind.sh — spawn-mind.sh の振る舞いを検証する。
#
# 自前 shell test、依存ゼロ。各ケースは独立したテスト用 Mind 名を使い、
# 終了時に必ずクリーンアップする。
#
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RUNTIME_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
SPAWN="${RUNTIME_DIR}/spawn-mind.sh"

# テスト ID（並走時の名前衝突を避けるため PID と時刻を含める）
TEST_ID="t$$-$(date +%s)"
PASS=0
FAIL=0
FAIL_MSGS=()

cleanup() {
  # このテスト ID で始まる Mindspace をすべて削除
  find "${RUNTIME_DIR}/minds" -maxdepth 1 -type d -name "${TEST_ID}-*" -exec rm -rf {} + 2>/dev/null || true
}
trap cleanup EXIT

# ----- assert helpers --------------------------------------------------------

assert_exit_code() {
  local label="$1"
  local expected="$2"
  local actual="$3"
  if [ "${actual}" = "${expected}" ]; then
    PASS=$((PASS + 1))
    echo "  [ok]   ${label}: exit ${actual}"
  else
    FAIL=$((FAIL + 1))
    FAIL_MSGS+=("${label}: expected exit ${expected}, got ${actual}")
    echo "  [NG]   ${label}: expected exit ${expected}, got ${actual}"
  fi
}

assert_file_exists() {
  local label="$1"
  local path="$2"
  if [ -f "${path}" ]; then
    PASS=$((PASS + 1))
    echo "  [ok]   ${label}: exists"
  else
    FAIL=$((FAIL + 1))
    FAIL_MSGS+=("${label}: file not found at ${path}")
    echo "  [NG]   ${label}: missing ${path}"
  fi
}

assert_files_equal() {
  local label="$1"
  local file_a="$2"
  local file_b="$3"
  if cmp -s "${file_a}" "${file_b}"; then
    PASS=$((PASS + 1))
    echo "  [ok]   ${label}: contents match"
  else
    FAIL=$((FAIL + 1))
    FAIL_MSGS+=("${label}: contents differ between ${file_a} and ${file_b}")
    echo "  [NG]   ${label}: contents differ"
  fi
}

assert_file_contains() {
  local label="$1"
  local path="$2"
  local needle="$3"
  if grep -qF -- "${needle}" "${path}" 2>/dev/null; then
    PASS=$((PASS + 1))
    echo "  [ok]   ${label}: contains '${needle}'"
  else
    FAIL=$((FAIL + 1))
    FAIL_MSGS+=("${label}: '${needle}' not found in ${path}")
    echo "  [NG]   ${label}: '${needle}' not found"
  fi
}

# ----- test cases ------------------------------------------------------------

echo "[case] 1. 引数不足は exit 1"
set +e
"${SPAWN}" >/dev/null 2>&1
code=$?
set -e
assert_exit_code "no args" 1 "${code}"

echo "[case] 2. 未登録 Kind は exit 2"
set +e
"${SPAWN}" no-such-kind designer "${TEST_ID}-kind" >/dev/null 2>&1
code=$?
set -e
assert_exit_code "unknown kind" 2 "${code}"

echo "[case] 3. 未登録 Persona は exit 3"
set +e
"${SPAWN}" generic no-such-persona "${TEST_ID}-persona" >/dev/null 2>&1
code=$?
set -e
assert_exit_code "unknown persona" 3 "${code}"

echo "[case] 4. 正常系: spawn 成功 + ファイル配置"
mind="${TEST_ID}-ok"
set +e
"${SPAWN}" generic designer "${mind}" >/dev/null 2>&1
code=$?
set -e
assert_exit_code "happy path" 0 "${code}"
mind_dir="${RUNTIME_DIR}/minds/${mind}"
assert_file_exists "Mindspace CLAUDE.md" "${mind_dir}/CLAUDE.md"
assert_file_exists "Mindspace .mind-meta.md" "${mind_dir}/.mind-meta.md"
assert_file_exists "Mindspace .mcp.json (Nexus 接続)" "${mind_dir}/.mcp.json"
assert_files_equal "CLAUDE.md == designer Persona" \
  "${mind_dir}/CLAUDE.md" \
  "${RUNTIME_DIR}/personas/designer.md"
assert_file_contains "meta has mind_name" "${mind_dir}/.mind-meta.md" "mind_name: ${mind}"
assert_file_contains "meta has kind" "${mind_dir}/.mind-meta.md" "kind: generic"
assert_file_contains "meta has persona" "${mind_dir}/.mind-meta.md" "persona: designer"
assert_file_contains ".mcp.json references nexus server" "${mind_dir}/.mcp.json" '"nexus"'
assert_file_contains ".mcp.json references nexus.py" "${mind_dir}/.mcp.json" "nexus.py"

echo "[case] 5. 既存 Mind 名は exit 4（不可侵: 上書き禁止）"
# ケース 4 で作った Mind を再利用して衝突を起こす
set +e
"${SPAWN}" generic designer "${mind}" >/dev/null 2>&1
code=$?
set -e
assert_exit_code "duplicate name" 4 "${code}"

# ----- summary ---------------------------------------------------------------

echo ""
echo "[summary] passed: ${PASS}, failed: ${FAIL}"
if [ "${FAIL}" -gt 0 ]; then
  echo "[summary] failures:"
  for msg in "${FAIL_MSGS[@]}"; do
    echo "  - ${msg}"
  done
  exit 1
fi
