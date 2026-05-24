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
# Phase 5a-2: Lifecycle Pillar is at runtime/pillars/lifecycle/ (ADR-0011).
SPAWN="${RUNTIME_DIR}/pillars/lifecycle/spawn-mind.sh"

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
# Issue #19 (ADR-0008): .mcp.json must bind the Nexus session to this Mind's identity.
assert_file_contains ".mcp.json binds AI_ORG_OS_MIND_NAME" "${mind_dir}/.mcp.json" "AI_ORG_OS_MIND_NAME"
assert_file_contains ".mcp.json binds the correct mind name" "${mind_dir}/.mcp.json" "${mind}"

echo "[case] 5. 既存 Mind 名は exit 4（不可侵: 上書き禁止）"
# ケース 4 で作った Mind を再利用して衝突を起こす
set +e
"${SPAWN}" generic designer "${mind}" >/dev/null 2>&1
code=$?
set -e
assert_exit_code "duplicate name" 4 "${code}"

echo "[case] 7. 不正な引数は exit 6（Codex P2 PR #27 指摘の再発防止）"
# 不正な MIND_NAME のさまざまな失敗パターン。
# spawn-mind.sh は KIND/PERSONA/MIND_NAME すべてに validate_arg を適用する。
# JSON injection 防止（"abc / a"b / a\b）、path traversal 防止（../escape）、
# 制御文字防止（タブ、空文字、空白）、長さ上限（65 字超）を 1 つずつ確認。

# パターン 1: JSON 文字を含む mind-name
set +e
"${SPAWN}" generic designer 'a"b' >/dev/null 2>&1; code=$?
set -e
assert_exit_code "mind-name with double quote" 6 "${code}"

# パターン 2: バックスラッシュ含む
set +e
"${SPAWN}" generic designer 'a\b' >/dev/null 2>&1; code=$?
set -e
assert_exit_code "mind-name with backslash" 6 "${code}"

# パターン 3: パストラバーサル
set +e
"${SPAWN}" generic designer '../escape' >/dev/null 2>&1; code=$?
set -e
assert_exit_code "mind-name with path traversal" 6 "${code}"

# パターン 4: 空白を含む
set +e
"${SPAWN}" generic designer 'a b' >/dev/null 2>&1; code=$?
set -e
assert_exit_code "mind-name with space" 6 "${code}"

# パターン 5: 空文字
set +e
"${SPAWN}" generic designer '' >/dev/null 2>&1; code=$?
set -e
assert_exit_code "empty mind-name" 6 "${code}"

# パターン 6: 長さ超過（65 字）
long_name="$(printf 'a%.0s' {1..65})"
set +e
"${SPAWN}" generic designer "${long_name}" >/dev/null 2>&1; code=$?
set -e
assert_exit_code "mind-name too long (65)" 6 "${code}"

# パターン 7: KIND も検証されること
set +e
"${SPAWN}" '../etc' designer "${TEST_ID}-vkind" >/dev/null 2>&1; code=$?
set -e
assert_exit_code "kind with path traversal" 6 "${code}"

# パターン 8: PERSONA も検証されること
set +e
"${SPAWN}" generic 'a"b' "${TEST_ID}-vpersona" >/dev/null 2>&1; code=$?
set -e
assert_exit_code "persona with double quote" 6 "${code}"

# パターン 9: 早期失敗の確認（Mindspace が作られていない）
if [ -d "${RUNTIME_DIR}/minds/${TEST_ID}-vkind" ] || [ -d "${RUNTIME_DIR}/minds/${TEST_ID}-vpersona" ]; then
  FAIL=$((FAIL + 1))
  FAIL_MSGS+=("invalid args: Mindspace should not be created")
  echo "  [NG]   invalid args: Mindspace was created despite failure"
else
  PASS=$((PASS + 1))
  echo "  [ok]   invalid args: no Mindspace leaked"
fi

echo "[case] 6. python が PATH に無いと exit 5（Nexus 接続不能を事前検知）"
# Codex P2 (PR #23) 指摘の再発防止。
# AI_ORG_OS_PYTHON に存在しないコマンドを指定し、command -v で弾かれることを検証。
mind_no_py="${TEST_ID}-no-py"
set +e
AI_ORG_OS_PYTHON="definitely-not-a-real-binary-${TEST_ID}" \
  "${SPAWN}" generic designer "${mind_no_py}" >/dev/null 2>&1
code=$?
set -e
assert_exit_code "missing python" 5 "${code}"
# 副作用が起きていないこと: Mindspace が作られていないはず（早期失敗）
if [ -d "${RUNTIME_DIR}/minds/${mind_no_py}" ]; then
  FAIL=$((FAIL + 1))
  FAIL_MSGS+=("missing python: Mindspace should not be created on failure")
  echo "  [NG]   missing python: Mindspace was created despite failure"
else
  PASS=$((PASS + 1))
  echo "  [ok]   missing python: no Mindspace leaked"
fi

echo "[case] 8. --start-loop で claude が無いと exit 8（PR #61 self-review fix）"
# --start-loop は spawn 時点で claude バイナリを事前検証する。
# claude を definitely-not-a-real-binary に差し替え、--start-loop で exit 8 が返ることを検証。
mind_no_claude="${TEST_ID}-no-claude"
set +e
AI_ORG_OS_CLAUDE_BIN="definitely-not-a-real-claude-${TEST_ID}" \
  "${SPAWN}" --start-loop generic designer "${mind_no_claude}" >/dev/null 2>&1
code=$?
set -e
assert_exit_code "missing claude with --start-loop" 8 "${code}"
# 副作用が起きていないこと: --start-loop なしでは検証されないので、Mindspace 生成前に
# claude チェックが走ることが重要（python 検証と対称）。Mindspace は作られていないはず。
if [ -d "${RUNTIME_DIR}/minds/${mind_no_claude}" ]; then
  FAIL=$((FAIL + 1))
  FAIL_MSGS+=("missing claude --start-loop: Mindspace should not be created")
  echo "  [NG]   missing claude --start-loop: Mindspace was created despite failure"
else
  PASS=$((PASS + 1))
  echo "  [ok]   missing claude --start-loop: no Mindspace leaked"
fi

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
