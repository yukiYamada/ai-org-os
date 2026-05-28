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

echo "[case] 4. worktree モードで spawn した Mind を kill すると worktree も解除される (Phase 5d-3 / ADR-0022)"
# Workspace template + 一時 git repo を用意して spawn-mind を worktree モードで叩く
mkdir -p "${AI_ORG_OS_HOME}/workspaces"
TEST_REPO_DIR="${AI_ORG_OS_HOME}/test-repo-${TEST_ID}"
mkdir -p "${TEST_REPO_DIR}"
git -C "${TEST_REPO_DIR}" init -q -b main
git -C "${TEST_REPO_DIR}" -c user.email=t@e -c user.name=t commit --allow-empty -q -m "initial"
cat > "${AI_ORG_OS_HOME}/workspaces/dev-test.md" <<EOF
---
workspace: dev-test
schema_version: "0.1"
vcs: git
repo: ${TEST_REPO_DIR}
mode: worktree
branch_prefix: mind
---

# Workspace: dev-test (kill test)
EOF
mind_wt="${TEST_ID}-wt"
"${SPAWN}" --workspace dev-test generic designer "${mind_wt}" >/dev/null
mind_wt_dir="${AI_ORG_OS_HOME}/minds/${mind_wt}"
# 事前確認: worktree が作られている
if [ ! -f "${mind_wt_dir}/work/.git" ]; then
  FAIL=$((FAIL + 1))
  FAIL_MSGS+=("setup: work/.git marker missing before kill")
  echo "  [NG]   setup: work/.git marker missing"
else
  # git の worktree list にも登録されている (branch 名で match: path 表記が
  # OS によって異なる = Windows の MSYS bash と git CLI で /c/... vs C:/...
  # と食い違うため、branch 名で代用する)
  expected_branch="mind/${mind_wt}"
  wt_count_before=$(git -C "${TEST_REPO_DIR}" worktree list --porcelain | grep -c "^branch refs/heads/${expected_branch}$" || true)
  if [ "${wt_count_before}" = "1" ]; then
    PASS=$((PASS + 1))
    echo "  [ok]   setup: worktree registered in repo (branch=${expected_branch})"
  else
    FAIL=$((FAIL + 1))
    FAIL_MSGS+=("setup: worktree not registered (branch=${expected_branch}, count=${wt_count_before})")
    echo "  [NG]   setup: worktree not registered (count=${wt_count_before})"
  fi
  # kill
  set +e; "${KILL}" "${mind_wt}" >/dev/null 2>&1; code=$?; set -e
  assert_exit_code "worktree kill" 0 "${code}"
  assert_dir_absent "Mindspace gone (worktree mode)" "${mind_wt_dir}"
  # worktree registration も消えている (同じく branch 名で照合)
  wt_count_after=$(git -C "${TEST_REPO_DIR}" worktree list --porcelain | grep -c "^branch refs/heads/${expected_branch}$" || true)
  if [ "${wt_count_after}" = "0" ]; then
    PASS=$((PASS + 1))
    echo "  [ok]   worktree registration cleaned up (count=0)"
  else
    FAIL=$((FAIL + 1))
    FAIL_MSGS+=("worktree registration orphan (count=${wt_count_after})")
    echo "  [NG]   worktree registration orphan (count=${wt_count_after})"
  fi
fi

echo "[case] 5. workspace template が削除されていても worktree cleanup できる (self-describing marker 経由)"
# 別 worktree モード Mind を spawn してから workspace template を消す
mind_dr="${TEST_ID}-detached"
"${SPAWN}" --workspace dev-test generic designer "${mind_dr}" >/dev/null
mind_dr_dir="${AI_ORG_OS_HOME}/minds/${mind_dr}"
rm -f "${AI_ORG_OS_HOME}/workspaces/dev-test.md"  # template 削除
set +e; "${KILL}" "${mind_dr}" >/dev/null 2>&1; code=$?; set -e
assert_exit_code "detached-template kill" 0 "${code}"
assert_dir_absent "Mindspace gone (template deleted)" "${mind_dr_dir}"
# worktree registration も消えている (marker file から直接 repo を逆引きできた)
expected_dr_branch="mind/${mind_dr}"
wt_count_dr=$(git -C "${TEST_REPO_DIR}" worktree list --porcelain | grep -c "^branch refs/heads/${expected_dr_branch}$" || true)
if [ "${wt_count_dr}" = "0" ]; then
  PASS=$((PASS + 1))
  echo "  [ok]   worktree cleaned up without template (branch=${expected_dr_branch})"
else
  FAIL=$((FAIL + 1))
  FAIL_MSGS+=("detached-template: worktree orphan (count=${wt_count_dr})")
  echo "  [NG]   worktree orphan (count=${wt_count_dr})"
fi

echo "[case] 6. malformed marker file は WARN で続行 (Mindspace は消える)"
# template を作り直して spawn、marker file を破壊して kill
cat > "${AI_ORG_OS_HOME}/workspaces/dev-test.md" <<EOF
---
workspace: dev-test
schema_version: "0.1"
vcs: git
repo: ${TEST_REPO_DIR}
mode: worktree
---
EOF
mind_mal="${TEST_ID}-malformed"
"${SPAWN}" --workspace dev-test generic designer "${mind_mal}" >/dev/null
mind_mal_dir="${AI_ORG_OS_HOME}/minds/${mind_mal}"
# marker を壊す (gitdir: 行を非標準形式に書き換え)
echo "not-a-gitdir-line" > "${mind_mal_dir}/work/.git"
set +e; "${KILL}" "${mind_mal}" >/dev/null 2>&1; code=$?; set -e
assert_exit_code "malformed marker kill" 0 "${code}"
assert_dir_absent "Mindspace gone (malformed marker)" "${mind_mal_dir}"
# 後始末: orphan な worktree registration が残っているはずなので prune
git -C "${TEST_REPO_DIR}" worktree prune 2>/dev/null || true

# fixture cleanup
rm -rf "${AI_ORG_OS_HOME}/workspaces" "${TEST_REPO_DIR}"

echo "[case] 7. kill 時に conduit-storage/{inbox,archive}/<mind>/ も削除される (Phase 5d-7 / ADR-0023 / #104)"
# Mind を spawn し、conduit-storage の inbox / archive に dispatch を
# 手動で書く (= 他 Mind から送られた状態を模倣)。kill 後に両 dir が消える
# ことを確認する。
mind_ds="${TEST_ID}-with-dispatch"
"${SPAWN}" generic designer "${mind_ds}" >/dev/null
mind_ds_dir="${AI_ORG_OS_HOME}/minds/${mind_ds}"
if [ ! -d "${mind_ds_dir}" ]; then
  FAIL=$((FAIL + 1))
  FAIL_MSGS+=("setup: spawn failed for ${mind_ds}")
  echo "  [NG]   setup: spawn failed"
else
  inbox_dir="${AI_ORG_OS_HOME}/conduit-storage/inbox/${mind_ds}"
  archive_dir="${AI_ORG_OS_HOME}/conduit-storage/archive/${mind_ds}"
  mkdir -p "${inbox_dir}" "${archive_dir}"
  # 模擬 dispatch (dispatch-format.md に倣う最小 frontmatter)
  cat > "${inbox_dir}/20260528T120000Z-from-other-000a.md" <<EOF
---
from: other-mind
to: ${mind_ds}
topic: stale dispatch
dispatched_at: 2026-05-28T12:00:00Z
msg_id: 20260528T120000Z-from-other-000a
---
hi
EOF
  cat > "${archive_dir}/20260528T110000Z-from-other-000b.md" <<EOF
---
from: other-mind
to: ${mind_ds}
topic: old acked
dispatched_at: 2026-05-28T11:00:00Z
msg_id: 20260528T110000Z-from-other-000b
---
old
EOF
  if [ ! -f "${inbox_dir}/20260528T120000Z-from-other-000a.md" ] || \
     [ ! -f "${archive_dir}/20260528T110000Z-from-other-000b.md" ]; then
    FAIL=$((FAIL + 1))
    FAIL_MSGS+=("setup: dispatch fixture not created")
    echo "  [NG]   setup: dispatch fixture missing"
  else
    PASS=$((PASS + 1))
    echo "  [ok]   setup: dispatch dirs populated"
  fi
  # kill (ADR-0023 で追加された経路で dispatch も削除されるはず)
  set +e; "${KILL}" "${mind_ds}" >/dev/null 2>&1; code=$?; set -e
  assert_exit_code "kill with dispatch history" 0 "${code}"
  assert_dir_absent "Mindspace gone" "${mind_ds_dir}"
  # ADR-0023 §2: dispatch 履歴も削除される (本 PR で追加)
  assert_dir_absent "conduit-storage/inbox/<mind>/ gone" "${inbox_dir}"
  assert_dir_absent "conduit-storage/archive/<mind>/ gone" "${archive_dir}"
fi

echo "[case] 8. dispatch 履歴の無い Mind を kill しても失敗しない (Phase 5d-7)"
# 何も dispatch していない quiet Mind を kill しても rm -rf の対象が無く
# ても OK であることを確認 (= 存在しない dir に対して失敗しない)。
mind_quiet="${TEST_ID}-quiet"
"${SPAWN}" generic designer "${mind_quiet}" >/dev/null
mind_quiet_dir="${AI_ORG_OS_HOME}/minds/${mind_quiet}"
set +e; "${KILL}" "${mind_quiet}" >/dev/null 2>&1; code=$?; set -e
assert_exit_code "kill quiet mind (no dispatch)" 0 "${code}"
assert_dir_absent "Mindspace gone (quiet)" "${mind_quiet_dir}"

echo ""
echo "[summary] passed: ${PASS}, failed: ${FAIL}"
if [ "${FAIL}" -gt 0 ]; then
  echo "[summary] failures:"
  for msg in "${FAIL_MSGS[@]}"; do
    echo "  - ${msg}"
  done
  exit 1
fi
