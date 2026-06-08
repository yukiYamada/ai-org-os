#!/usr/bin/env bash
#
# test-deterministic-kind.sh — Phase 5g.A #169 (Kind diversity) の e2e test。
#
# 検証:
#   - kind=deterministic で spawn-mind が成功し body.sh を Mindspace に置く
#   - .mcp.json は配置されない (= MCP は claude-specific)
#   - mind-loop が body.sh を 1 cycle 実行し exit code 0 を観測
#   - kind=api / kind=human では mind-loop が "spec only" で exit 4 する
#   - kind=generic (runtime=claude) は既存挙動と同じ (fake claude stub 経由)
#
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RUNTIME_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
SPAWN="${RUNTIME_DIR}/pillars/lifecycle/spawn-mind.sh"
KILL="${RUNTIME_DIR}/pillars/lifecycle/kill-mind.sh"
LOOP="${RUNTIME_DIR}/pillars/lifecycle/mind-loop.sh"

TEST_ID="dk$$-$(date +%s)"
PASS=0
FAIL=0
FAIL_MSGS=()

# stub host config (= spawn-mind が config.env を要求するため)
TEST_TMP_DIR="$(mktemp -d)"
. "${SCRIPT_DIR}/_lib_host_stub.sh"
stub_host_config_init "${TEST_TMP_DIR}"

# claude スタブ (kind=generic のテストで使う、deterministic では呼ばれない)
cat > "${TEST_TMP_DIR}/fake-claude.sh" <<'STUB'
#!/usr/bin/env bash
echo "fake-claude received args: $@" >&2
sleep 0.1
exit 0
STUB
chmod +x "${TEST_TMP_DIR}/fake-claude.sh"
export AI_ORG_OS_CLAUDE_BIN="${TEST_TMP_DIR}/fake-claude.sh"

# 既存 Guild manifest (default) は generic + designer/implementer/reviewer のみ
# を許容するため、watcher persona を含む Guild を用意する必要がある。
# templates にある default Guild を上書きする overlay を tmp 内に置く。
mkdir -p "${TEST_TMP_DIR}/guilds/default"
cat > "${TEST_TMP_DIR}/guilds/default/manifest.md" <<'MANIFEST'
---
guild: default
schema_version: "0.1"
purpose: deterministic kind e2e test guild
kinds: [generic, deterministic, api, human]
personas: [designer, implementer, reviewer, guildmaster, watcher]
---

Test guild for deterministic kind e2e.
MANIFEST

cleanup() {
  find "${AI_ORG_OS_HOME}/minds" -maxdepth 1 -type d -name "${TEST_ID}-*" -exec rm -rf {} + 2>/dev/null || true
  rm -rf "${TEST_TMP_DIR}"
}
trap cleanup EXIT

assert_exit() {
  local label="$1" expected="$2" actual="$3"
  if [ "${actual}" = "${expected}" ]; then
    PASS=$((PASS + 1)); echo "  [ok]   ${label}: exit ${actual}"
  else
    FAIL=$((FAIL + 1)); FAIL_MSGS+=("${label}: expected ${expected}, got ${actual}")
    echo "  [NG]   ${label}: expected ${expected}, got ${actual}"
  fi
}

assert_file_exists() {
  local label="$1" path="$2"
  if [ -f "${path}" ]; then
    PASS=$((PASS + 1)); echo "  [ok]   ${label}: ${path} exists"
  else
    FAIL=$((FAIL + 1)); FAIL_MSGS+=("${label}: ${path} missing")
    echo "  [NG]   ${label}: ${path} missing"
  fi
}

assert_file_absent() {
  local label="$1" path="$2"
  if [ ! -e "${path}" ]; then
    PASS=$((PASS + 1)); echo "  [ok]   ${label}: ${path} absent"
  else
    FAIL=$((FAIL + 1)); FAIL_MSGS+=("${label}: ${path} present unexpectedly")
    echo "  [NG]   ${label}: ${path} present"
  fi
}

assert_contains() {
  local label="$1" file="$2" needle="$3"
  if [ -f "${file}" ] && grep -q -F "${needle}" "${file}"; then
    PASS=$((PASS + 1)); echo "  [ok]   ${label}: contains '${needle}'"
  else
    FAIL=$((FAIL + 1)); FAIL_MSGS+=("${label}: '${needle}' not found in ${file}")
    echo "  [NG]   ${label}: '${needle}' not found in ${file}"
  fi
}

# ----- case 1: kind=deterministic で spawn -----

echo "[case] 1. spawn-mind with kind=deterministic + persona=watcher"
mind="${TEST_ID}-det"
set +e
"${SPAWN}" deterministic watcher "${mind}" > "${TEST_TMP_DIR}/spawn-det.log" 2>&1
spawn_rc=$?
set -e
assert_exit "spawn-mind deterministic" 0 "${spawn_rc}"
if [ "${spawn_rc}" != "0" ]; then
  echo "  [debug] spawn log:"
  cat "${TEST_TMP_DIR}/spawn-det.log" | sed 's/^/    /'
fi

MIND_DIR="${AI_ORG_OS_HOME}/minds/${mind}"
assert_file_exists "body.sh extracted" "${MIND_DIR}/body.sh"
assert_file_exists "CLAUDE.md installed" "${MIND_DIR}/CLAUDE.md"
assert_file_absent ".mcp.json skipped (non-claude)" "${MIND_DIR}/.mcp.json"

# ----- case 2: mind-loop が body.sh を 1 cycle 実行する -----

echo "[case] 2. mind-loop max_cycles=1 with deterministic kind"
set +e
AI_ORG_OS_LOOP_MAX_CYCLES=1 \
  AI_ORG_OS_LOOP_PERIOD=0 \
  "${LOOP}" "${mind}" > "${TEST_TMP_DIR}/loop-det.log" 2>&1
loop_rc=$?
set -e
assert_exit "mind-loop deterministic" 0 "${loop_rc}"

CYCLE_JSON_DIR="${AI_ORG_OS_HOME}/logs/minds/${mind}/cycles"
CYCLE_JSON="${CYCLE_JSON_DIR}/cycle-00001.json"
assert_file_exists "cycle stdout captured" "${CYCLE_JSON}"
if [ -f "${CYCLE_JSON}" ]; then
  assert_contains "body.sh stdout has 'pending issues:'" "${CYCLE_JSON}" "pending issues:"
fi

# ----- case 3: kind=api は spec only → mind-loop が exit 4 -----

echo "[case] 3. mind-loop with kind=api (spec only) should exit 4"
mind_api="${TEST_ID}-api"
"${SPAWN}" api designer "${mind_api}" > /dev/null 2>&1
set +e
AI_ORG_OS_LOOP_MAX_CYCLES=1 \
  AI_ORG_OS_LOOP_PERIOD=0 \
  "${LOOP}" "${mind_api}" > "${TEST_TMP_DIR}/loop-api.log" 2>&1
api_rc=$?
set -e
assert_exit "mind-loop api spec-only" 4 "${api_rc}"
assert_contains "loop log mentions 'spec only'" "${TEST_TMP_DIR}/loop-api.log" "spec only"

# ----- case 4: kind=human も spec only → exit 4 -----

echo "[case] 4. mind-loop with kind=human (spec only) should exit 4"
mind_h="${TEST_ID}-h"
"${SPAWN}" human designer "${mind_h}" > /dev/null 2>&1
set +e
AI_ORG_OS_LOOP_MAX_CYCLES=1 \
  AI_ORG_OS_LOOP_PERIOD=0 \
  "${LOOP}" "${mind_h}" > "${TEST_TMP_DIR}/loop-h.log" 2>&1
h_rc=$?
set -e
assert_exit "mind-loop human spec-only" 4 "${h_rc}"

# ----- case 5: kind=generic は既存挙動と同じ (= runtime=claude を解決して fake-claude を呼ぶ) -----

echo "[case] 5. mind-loop with kind=generic (= runtime=claude) still works"
mind_g="${TEST_ID}-g"
"${SPAWN}" generic designer "${mind_g}" > /dev/null 2>&1
assert_file_exists ".mcp.json present for claude kind" "${AI_ORG_OS_HOME}/minds/${mind_g}/.mcp.json"
set +e
AI_ORG_OS_LOOP_MAX_CYCLES=1 \
  AI_ORG_OS_LOOP_PERIOD=0 \
  "${LOOP}" "${mind_g}" > "${TEST_TMP_DIR}/loop-g.log" 2>&1
g_rc=$?
set -e
assert_exit "mind-loop claude path" 0 "${g_rc}"

# ----- summary -----

echo ""
echo "[summary] passed: ${PASS}, failed: ${FAIL}"
if [ "${FAIL}" -gt 0 ]; then
  echo "[summary] failures:"
  for m in "${FAIL_MSGS[@]}"; do
    echo "  - ${m}"
  done
  exit 1
fi
exit 0
