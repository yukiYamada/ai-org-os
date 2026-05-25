#!/usr/bin/env bash
#
# test-submit-issue.sh — submit-issue.sh (Inbox Pillar の shell wrapper) の
# Guild validation を検証する (Phase 5c-1 / #88 Codex P2)。
#
# 軸:
#   - --guild <unknown> は exit 4 (claim 不能な孤児 Issue を作らせない)
#   - --guild default (templates 同梱) は exit 0
#   - --guild 省略時 (default fallback) も exit 0
#
# AI_ORG_OS_HOME を tmp に向けて副作用を repo に残さない。
#
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RUNTIME_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
SUBMIT="${RUNTIME_DIR}/pillars/inbox/submit-issue.sh"

if [ ! -x "${SUBMIT}" ]; then
  # 実行ビットが落ちている可能性 (Windows / cross-checkout)。bash 経由で起動する。
  if [ ! -f "${SUBMIT}" ]; then
    echo "[ERROR] submit-issue.sh not found at ${SUBMIT}" >&2
    exit 99
  fi
fi

if ! command -v python3 >/dev/null 2>&1 && ! command -v python >/dev/null 2>&1; then
  echo "[skip] python not found; skipping submit-issue tests."
  exit 0
fi

TMP_HOME="$(mktemp -d)"
trap 'rm -rf "${TMP_HOME}"' EXIT
export AI_ORG_OS_HOME="${TMP_HOME}"

PASS=0
FAIL=0
FAIL_MSGS=()

assert_exit_code() {
  local label="$1" expected="$2" got="$3"
  if [ "${expected}" = "${got}" ]; then
    PASS=$((PASS + 1))
    echo "  [ok]   ${label}: exit ${got}"
  else
    FAIL=$((FAIL + 1))
    FAIL_MSGS+=("${label}: expected ${expected}, got ${got}")
    echo "  [NG]   ${label}: expected ${expected}, got ${got}"
  fi
}

# Phase 5c-1: --guild 指定で template 同梱の "default" は通る
echo "[case] 1. --guild default で投入成功 (exit 0)"
set +e
bash "${SUBMIT}" --guild default "smoke title 1" "smoke body" p2 e2e-test \
  >/dev/null 2>&1
code=$?
set -e
assert_exit_code "valid guild (default)" 0 "${code}"

# Phase 5c-1: --guild 省略 = default 扱い
echo "[case] 2. --guild 省略時も投入成功 (default fallback)"
set +e
bash "${SUBMIT}" "smoke title 2" "smoke body" p2 e2e-test >/dev/null 2>&1
code=$?
set -e
assert_exit_code "no --guild (default)" 0 "${code}"

# Phase 5c-1 (#88 Codex P2): unknown guild は claim 不能になるので投入拒否
echo "[case] 3. --guild <unknown> は exit 4 (claim 孤児防止)"
set +e
bash "${SUBMIT}" --guild "no-such-guild-zzz" "would-be orphan" "body" p2 e2e-test \
  >/dev/null 2>&1
code=$?
set -e
assert_exit_code "unknown guild rejected" 4 "${code}"

# Phase 5c-1 (#88): malformed manifest を持つ Guild も exit 4
echo "[case] 4. malformed manifest を持つ Guild も exit 4"
HOME_GUILDS="${TMP_HOME}/guilds/broken"
mkdir -p "${HOME_GUILDS}"
cat > "${HOME_GUILDS}/manifest.md" <<'EOF'
---
guild: broken
schema_version: 9.9
kinds: [generic]
personas: [designer]
---
EOF
set +e
bash "${SUBMIT}" --guild broken "title" "body" p2 e2e-test >/dev/null 2>&1
code=$?
set -e
assert_exit_code "malformed guild rejected" 4 "${code}"

# Phase 5c-1: 利用者が作った home Guild (parse 可) は通る
echo "[case] 5. home overlay Guild (parse 可) は投入成功"
HOME_GUILDS_OK="${TMP_HOME}/guilds/my-team"
mkdir -p "${HOME_GUILDS_OK}"
cat > "${HOME_GUILDS_OK}/manifest.md" <<'EOF'
---
guild: my-team
schema_version: 0.1
purpose: test team guild
kinds: [generic]
personas: [designer]
---
EOF
set +e
bash "${SUBMIT}" --guild my-team "for my-team" "body" p2 e2e-test \
  >/dev/null 2>&1
code=$?
set -e
assert_exit_code "home overlay guild accepted" 0 "${code}"

echo ""
echo "[summary] passed: ${PASS}, failed: ${FAIL}"
if [ "${FAIL}" -gt 0 ]; then
  echo "[summary] failures:"
  for msg in "${FAIL_MSGS[@]}"; do
    echo "  - ${msg}"
  done
  exit 1
fi
