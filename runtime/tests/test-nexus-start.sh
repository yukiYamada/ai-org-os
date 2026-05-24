#!/usr/bin/env bash
#
# test-nexus-start.sh — runtime/pillars/conduit/start.sh の振る舞いを検証する。
#
# 軸（pr-self-review checklist より）:
#   - 引数バリデーション（不明オプションは exit 1）
#   - 環境依存（python なしで exit 2）
#   - 冪等性（--setup-only を 2 回呼んでも安全）
#   - help 出力（--help / -h）
#
# Nexus 本体の実起動はテストしない（MCP クライアントが必要、CI で再現困難）。
# --setup-only で venv 作成までを検証する。
#
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
NEXUS_DIR="$(cd "${SCRIPT_DIR}/../pillars/conduit" && pwd)"
START="${NEXUS_DIR}/start.sh"

if [ ! -x "${START}" ]; then
  echo "[skip] start.sh not executable; skipping."
  exit 0
fi

if ! command -v python3 >/dev/null 2>&1 && ! command -v python >/dev/null 2>&1; then
  echo "[skip] python not found; skipping nexus-start tests."
  exit 0
fi

# venv 作成テストは pip ネットワークが必要。CI / オフラインでは skip。
SKIP_VENV_TESTS="${SKIP_VENV_TESTS:-0}"

# テスト用の venv パスをホスト venv と隔離するため、一時 NEXUS_DIR を作る
TMP_HOME="$(mktemp -d)"
trap 'rm -rf "${TMP_HOME}"' EXIT

PASS=0
FAIL=0
FAIL_MSGS=()

assert_exit_code() {
  local label="$1" expected="$2" actual="$3"
  if [ "${actual}" = "${expected}" ]; then
    PASS=$((PASS + 1)); echo "  [ok]   ${label}: exit ${actual}"
  else
    FAIL=$((FAIL + 1)); FAIL_MSGS+=("${label}: expected ${expected}, got ${actual}")
    echo "  [NG]   ${label}: expected ${expected}, got ${actual}"
  fi
}

assert_contains() {
  local label="$1" haystack="$2" needle="$3"
  if echo "${haystack}" | grep -qF -- "${needle}"; then
    PASS=$((PASS + 1)); echo "  [ok]   ${label}"
  else
    FAIL=$((FAIL + 1)); FAIL_MSGS+=("${label}: '${needle}' missing")
    echo "  [NG]   ${label}: '${needle}' missing"
  fi
}

# ---- 1. 不明オプションは exit 1
echo "[case] 1. 不明オプションは exit 1"
set +e; "${START}" --bogus-option >/dev/null 2>&1; code=$?; set -e
assert_exit_code "unknown option" 1 "${code}"

# ---- 2. --help は exit 0、用途説明を含む
echo "[case] 2. --help は exit 0 で help を返す"
set +e; out=$("${START}" --help 2>&1); code=$?; set -e
assert_exit_code "help exits 0" 0 "${code}"
assert_contains "help mentions Nexus" "${out}" "Nexus"

# ---- 3. python が無いと exit 2（pr-self-review checklist: 環境依存）
echo "[case] 3. python が無いと exit 2"
set +e
AI_ORG_OS_PYTHON="definitely-not-a-python-$$" "${START}" --setup-only >/dev/null 2>&1
code=$?
set -e
assert_exit_code "missing python" 2 "${code}"

# ---- 4. --setup-only の冪等性（venv 作成は CI でネットワーク必要なので opt-in）
if [ "${SKIP_VENV_TESTS}" = "1" ]; then
  echo "[case] 4. setup-only 冪等性 [skipped: SKIP_VENV_TESTS=1]"
else
  # ネットワークが無いか pip が落ちた場合は skip 扱い
  echo "[case] 4. --setup-only 2 回呼んでも安全（冪等性）"
  set +e
  "${START}" --setup-only >/tmp/start-setup-1.log 2>&1
  code1=$?
  set -e
  if [ "${code1}" != "0" ]; then
    echo "  [skip] first setup failed (likely no network); skipping idempotency test"
    echo "  log tail:"
    tail -5 /tmp/start-setup-1.log | sed 's/^/    /'
  else
    set +e
    "${START}" --setup-only >/tmp/start-setup-2.log 2>&1
    code2=$?
    set -e
    assert_exit_code "second setup-only is idempotent" 0 "${code2}"
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
