#!/usr/bin/env bash
#
# test-realm.sh — Phase 5a-1 Realm コンテナの起動テスト。
#
# Docker / docker compose が無い環境では skip（CI でも skip）。
# Docker がある環境でも明示 opt-in（RUN_REALM_TESTS=1）でのみ実行する。
# 理由: build に時間がかかる、ポートを占有しないが image を作る。
#
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RUNTIME_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
REALM_DIR="${RUNTIME_DIR}/realm"

RUN_REALM_TESTS="${RUN_REALM_TESTS:-0}"

if [ "${RUN_REALM_TESTS}" != "1" ]; then
  echo "[skip] Realm container tests are gated by RUN_REALM_TESTS=1 (heavy: requires docker build)."
  exit 0
fi

if ! command -v docker >/dev/null 2>&1; then
  echo "[skip] docker not installed; skipping Realm container tests."
  exit 0
fi

if ! docker compose version >/dev/null 2>&1; then
  echo "[skip] 'docker compose' subcommand not available; skipping."
  exit 0
fi

PASS=0
FAIL=0
FAIL_MSGS=()

cleanup() {
  echo "[cleanup] tearing down realm container..."
  (cd "${REALM_DIR}" && docker compose down --remove-orphans >/dev/null 2>&1) || true
}
trap cleanup EXIT

assert_ok() {
  local label="$1" rc="$2"
  if [ "${rc}" = "0" ]; then
    PASS=$((PASS + 1)); echo "  [ok]   ${label}"
  else
    FAIL=$((FAIL + 1)); FAIL_MSGS+=("${label}: rc=${rc}")
    echo "  [NG]   ${label}: rc=${rc}"
  fi
}

echo "[case] 1. docker compose up でコンテナが立つ"
cd "${REALM_DIR}"
set +e
docker compose up -d --build >/tmp/realm-build.log 2>&1
code=$?
set -e
assert_ok "compose up" "${code}"

if [ "${code}" = "0" ]; then
  sleep 2  # コンテナ起動安定待ち

  echo "[case] 2. コンテナ内で既存ツール (list-minds.sh) が動く"
  # Codex P1 PR #54 修正: list-minds.sh は git で 100644（実行ビット無し）として
  # tracked されているため、bind mount 経由でも実行ビットが無い。
  # `docker exec ... /path/to/script` だと permission denied (exit 126) になるので、
  # 明示的に bash 経由で起動する。
  set +e
  docker exec ai-org-os-realm bash /realm/runtime/pillars/lifecycle/list-minds.sh >/dev/null 2>&1
  rc=$?
  set -e
  assert_ok "list-minds.sh execution" "${rc}"

  echo "[case] 3. コンテナ内で observe.py が動く"
  set +e
  out=$(docker exec ai-org-os-realm python3 /realm/runtime/pillars/observation/observe.py 2>&1)
  rc=$?
  set -e
  assert_ok "observe.py execution" "${rc}"
  if echo "${out}" | grep -qE "Realm Observatory|No minds spawned"; then
    PASS=$((PASS + 1)); echo "  [ok]   observe.py output looks valid"
  else
    FAIL=$((FAIL + 1)); FAIL_MSGS+=("observe.py output unexpected")
    echo "  [NG]   observe.py output unexpected:"
    echo "${out}" | head -5 | sed 's/^/    /'
  fi
fi

echo ""
echo "[summary] passed: ${PASS}, failed: ${FAIL}"
if [ "${FAIL}" -gt 0 ]; then
  for msg in "${FAIL_MSGS[@]}"; do echo "  - ${msg}"; done
  exit 1
fi
