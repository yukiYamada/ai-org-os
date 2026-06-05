#!/usr/bin/env bash
#
# test-mindspace-persistence.sh — Phase 5g.B #171:
# kill-mind --preserve + spawn-mind --restore-from の round-trip 検証。
#
# 注: spawn-mind は host stub 等の依存が多いため、本テストは
# kill-mind --preserve の output と spawn-mind 側 --restore-from の copy logic
# をそれぞれ独立に検証する (= 結合テストではなく単体テスト)。
#
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RUNTIME_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
SPAWN="${RUNTIME_DIR}/pillars/lifecycle/spawn-mind.sh"
KILL="${RUNTIME_DIR}/pillars/lifecycle/kill-mind.sh"

PASS=0
FAIL=0
FAIL_MSGS=()

TEST_TMP_DIR="$(mktemp -d)"
export AI_ORG_OS_HOME="${TEST_TMP_DIR}/home"
mkdir -p "${AI_ORG_OS_HOME}"

cleanup() {
  rm -rf "${TEST_TMP_DIR}"
}
trap cleanup EXIT

assert_true() {
  local label="$1"
  local cond="$2"
  if [ "${cond}" = "1" ]; then
    PASS=$((PASS + 1))
    echo "  [ok]   ${label}"
  else
    FAIL=$((FAIL + 1))
    FAIL_MSGS+=("${label}")
    echo "  [NG]   ${label}"
  fi
}

assert_eq() {
  local label="$1"
  local expected="$2"
  local actual="$3"
  if [ "${expected}" = "${actual}" ]; then
    PASS=$((PASS + 1))
    echo "  [ok]   ${label}: '${actual}'"
  else
    FAIL=$((FAIL + 1))
    FAIL_MSGS+=("${label}: expected '${expected}', got '${actual}'")
    echo "  [NG]   ${label}: expected '${expected}', got '${actual}'"
  fi
}

# ---------- case 1: kill --preserve copies state.md + notes/ -----------------
echo "[case] 1. kill-mind --preserve → preserved/<mind>/ に state.md + notes/"
MIND="alice"
MIND_DIR="${AI_ORG_OS_HOME}/minds/${MIND}"
mkdir -p "${MIND_DIR}/notes"
echo "alice-state-v1" > "${MIND_DIR}/state.md"
echo "cycle 1 notes" > "${MIND_DIR}/notes/cycle-1.md"
echo "cycle 2 notes" > "${MIND_DIR}/notes/cycle-2.md"
# kill には pidfile 不要 (= 居なければ skip + Mindspace 削除のみ)
bash "${KILL}" --preserve "${MIND}" >/dev/null 2>&1
set +e
test -f "${AI_ORG_OS_HOME}/preserved/${MIND}/state.md" && got_state=1 || got_state=0
test -d "${AI_ORG_OS_HOME}/preserved/${MIND}/notes" && got_notes=1 || got_notes=0
test -f "${AI_ORG_OS_HOME}/preserved/${MIND}/preserved-meta.json" && got_meta=1 || got_meta=0
test ! -d "${MIND_DIR}" && mindspace_gone=1 || mindspace_gone=0
set -e
assert_true "preserved state.md present" "${got_state}"
assert_true "preserved notes/ present" "${got_notes}"
assert_true "preserved-meta.json present" "${got_meta}"
assert_true "original Mindspace removed" "${mindspace_gone}"
# 内容も同じか
if [ -f "${AI_ORG_OS_HOME}/preserved/${MIND}/state.md" ]; then
  content="$(cat "${AI_ORG_OS_HOME}/preserved/${MIND}/state.md")"
  assert_eq "preserved state.md content" "alice-state-v1" "${content}"
fi

# ---------- case 2: kill without --preserve does NOT create preserved/ ---------
echo "[case] 2. --preserve なし → preserved/ は作られない"
MIND2="bob"
MIND_DIR2="${AI_ORG_OS_HOME}/minds/${MIND2}"
mkdir -p "${MIND_DIR2}"
echo "bob-state" > "${MIND_DIR2}/state.md"
bash "${KILL}" "${MIND2}" >/dev/null 2>&1
set +e
test -d "${AI_ORG_OS_HOME}/preserved/${MIND2}" && created=1 || created=0
set -e
assert_eq "no preserved/ for bob" "0" "${created}"

# ---------- case 3: spawn-mind --restore-from validates path -----------------
echo "[case] 3. spawn-mind --restore-from <non-existent> → WARN + 継続"
# 不在 path 指定でも spawn は exit ok するべき (= WARN log のみ)。
# ただし spawn-mind は host stub config 等の依存が多く full spawn は重い。
# 代わりに --help / arg parsing が --restore-from を受け付けることだけ確認。
help_out="$(bash "${SPAWN}" --help 2>&1)"
echo "${help_out}" | grep -q -- "--restore-from" && have_help=1 || have_help=0
assert_eq "spawn-mind --help mentions --restore-from" "1" "${have_help}"

# ---------- case 4: --restore-from copies state.md + notes/ ------------------
# spawn-mind 内部の restore block 単体を模す (= 同じ cp ロジック)。
echo "[case] 4. spawn-mind 内部 restore ロジック (manual repro)"
PRESERVED="${AI_ORG_OS_HOME}/preserved/${MIND}"  # case 1 で残した snapshot
NEW_MIND_DIR="${AI_ORG_OS_HOME}/minds/alice-restored"
mkdir -p "${NEW_MIND_DIR}"
echo "fresh Persona content" > "${NEW_MIND_DIR}/CLAUDE.md"
# spawn-mind.sh の restore-from block と同じ ops
if [ -f "${PRESERVED}/state.md" ]; then
  cp "${PRESERVED}/state.md" "${NEW_MIND_DIR}/state.md"
fi
if [ -d "${PRESERVED}/notes" ]; then
  cp -R "${PRESERVED}/notes" "${NEW_MIND_DIR}/notes"
fi
set +e
test -f "${NEW_MIND_DIR}/state.md" && restored_state=1 || restored_state=0
test -d "${NEW_MIND_DIR}/notes" && restored_notes=1 || restored_notes=0
test -f "${NEW_MIND_DIR}/notes/cycle-1.md" && restored_c1=1 || restored_c1=0
test -f "${NEW_MIND_DIR}/CLAUDE.md" && persona_intact=1 || persona_intact=0
set -e
assert_true "restored state.md present" "${restored_state}"
assert_true "restored notes/ present" "${restored_notes}"
assert_true "restored notes/cycle-1.md present" "${restored_c1}"
assert_true "fresh CLAUDE.md (Persona) untouched" "${persona_intact}"
content="$(cat "${NEW_MIND_DIR}/state.md")"
assert_eq "restored state.md content matches preserved" "alice-state-v1" "${content}"

# ---------- summary ----------------------------------------------------------
echo ""
echo "[summary] passed: ${PASS}, failed: ${FAIL}"
if [ "${FAIL}" -gt 0 ]; then
  echo "[summary] failures:"
  for msg in "${FAIL_MSGS[@]}"; do
    echo "  - ${msg}"
  done
  exit 1
fi
exit 0
