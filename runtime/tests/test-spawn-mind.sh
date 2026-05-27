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
REPO_DIR="$(cd "${RUNTIME_DIR}/.." && pwd)"
# Phase 5a-2: Lifecycle Pillar is at runtime/pillars/lifecycle/ (ADR-0011).
SPAWN="${RUNTIME_DIR}/pillars/lifecycle/spawn-mind.sh"

# テスト ID（並走時の名前衝突を避けるため PID と時刻を含める）
TEST_ID="t$$-$(date +%s)"
PASS=0
FAIL=0
FAIL_MSGS=()

# Phase 5b-3 (#78): spawn-mind は runtime/host/config.env を要求するため、
# stub config.env を共有 helper 経由で用意する。
TEST_TMP_DIR="$(mktemp -d)"
. "${SCRIPT_DIR}/_lib_host_stub.sh"
stub_host_config_init "${TEST_TMP_DIR}"
STUB_PY="${TEST_TMP_DIR}/stub-python.exe"
STUB_NEXUS="${TEST_TMP_DIR}/stub-nexus.py"

cleanup() {
  # このテスト ID で始まる Mindspace をすべて削除
  find "${AI_ORG_OS_HOME}/minds" -maxdepth 1 -type d -name "${TEST_ID}-*" -exec rm -rf {} + 2>/dev/null || true
  rm -rf "${TEST_TMP_DIR}"
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
mind_dir="${AI_ORG_OS_HOME}/minds/${mind}"
assert_file_exists "Mindspace CLAUDE.md" "${mind_dir}/CLAUDE.md"
assert_file_exists "Mindspace .mind-meta.md" "${mind_dir}/.mind-meta.md"
assert_file_exists "Mindspace .mcp.json (Nexus 接続)" "${mind_dir}/.mcp.json"
# Phase 5c-1 / ADR-0020: Persona は templates/personas/ から overlay 解決される。
# AI_ORG_OS_HOME 配下に personas 実体が無ければ templates が fallback として使われる。
assert_files_equal "CLAUDE.md == designer Persona (templates)" \
  "${mind_dir}/CLAUDE.md" \
  "${REPO_DIR}/templates/personas/designer.md"
assert_file_contains "meta has mind_name" "${mind_dir}/.mind-meta.md" "mind_name: ${mind}"
assert_file_contains "meta has kind" "${mind_dir}/.mind-meta.md" "kind: generic"
assert_file_contains "meta has persona" "${mind_dir}/.mind-meta.md" "persona: designer"
# Phase 5c-1 / ADR-0019: --guild 省略時は default Guild に所属
assert_file_contains "meta has guild=default" "${mind_dir}/.mind-meta.md" "guild: default"
# Phase 5c-2 P1 fix (#91 Codex): Mind registry が authoritative source として
# Mindspace の外に書かれること。Mindspace 内 .mind-meta.md は informational copy。
registry_entry="${AI_ORG_OS_HOME}/registry/minds/${mind}.md"
assert_file_exists "Mind registry entry (authoritative)" "${registry_entry}"
assert_file_contains "registry has mind_name" "${registry_entry}" "mind_name: ${mind}"
assert_file_contains "registry has persona" "${registry_entry}" "persona: designer"
assert_file_contains "registry has guild" "${registry_entry}" "guild: default"
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
if [ -d "${AI_ORG_OS_HOME}/minds/${TEST_ID}-vkind" ] || [ -d "${AI_ORG_OS_HOME}/minds/${TEST_ID}-vpersona" ]; then
  FAIL=$((FAIL + 1))
  FAIL_MSGS+=("invalid args: Mindspace should not be created")
  echo "  [NG]   invalid args: Mindspace was created despite failure"
else
  PASS=$((PASS + 1))
  echo "  [ok]   invalid args: no Mindspace leaked"
fi

echo "[case] 6. config.env が無いと exit 5（Phase 5b-3 / #78: ホスト setup 未済）"
# 旧テストは AI_ORG_OS_PYTHON で missing python を検証していたが、
# Phase 5b-3 で host/config.env 経由に切り替わったため、config.env 不在を検証する。
mind_no_cfg="${TEST_ID}-no-cfg"
set +e
AI_ORG_OS_HOST_CONFIG="/nonexistent/config.env" \
  "${SPAWN}" generic designer "${mind_no_cfg}" >/dev/null 2>&1
code=$?
set -e
assert_exit_code "missing config.env" 5 "${code}"
if [ -d "${AI_ORG_OS_HOME}/minds/${mind_no_cfg}" ]; then
  FAIL=$((FAIL + 1))
  FAIL_MSGS+=("missing config.env: Mindspace should not be created on failure")
  echo "  [NG]   missing config.env: Mindspace leaked"
else
  PASS=$((PASS + 1))
  echo "  [ok]   missing config.env: no Mindspace leaked"
fi

echo "[case] 6b. config.env はあるが HOST_PYTHON_BIN が指すファイルが不在で exit 5"
broken_cfg="${TEST_TMP_DIR}/broken-config.env"
cat > "${broken_cfg}" <<CFG
HOST_PYTHON_BIN=/nonexistent/python.exe
HOST_NEXUS_PY=${STUB_NEXUS}
CFG
mind_bad_py="${TEST_ID}-bad-py"
set +e
AI_ORG_OS_HOST_CONFIG="${broken_cfg}" \
  "${SPAWN}" generic designer "${mind_bad_py}" >/dev/null 2>&1
code=$?
set -e
assert_exit_code "HOST_PYTHON_BIN points to missing file" 5 "${code}"

echo "[case] 6c. config.env はあるが HOST_NEXUS_PY が指すファイルが不在で exit 5"
broken_cfg2="${TEST_TMP_DIR}/broken-config2.env"
cat > "${broken_cfg2}" <<CFG
HOST_PYTHON_BIN=${STUB_PY}
HOST_NEXUS_PY=/nonexistent/nexus.py
CFG
mind_bad_nx="${TEST_ID}-bad-nx"
set +e
AI_ORG_OS_HOST_CONFIG="${broken_cfg2}" \
  "${SPAWN}" generic designer "${mind_bad_nx}" >/dev/null 2>&1
code=$?
set -e
assert_exit_code "HOST_NEXUS_PY points to missing file" 5 "${code}"

echo "[case] 6d. config.env はあるが HOST_PYTHON_BIN 変数が空で exit 5"
empty_cfg="${TEST_TMP_DIR}/empty-config.env"
cat > "${empty_cfg}" <<CFG
HOST_PYTHON_BIN=
HOST_NEXUS_PY=${STUB_NEXUS}
CFG
mind_empty="${TEST_ID}-empty"
set +e
AI_ORG_OS_HOST_CONFIG="${empty_cfg}" \
  "${SPAWN}" generic designer "${mind_empty}" >/dev/null 2>&1
code=$?
set -e
assert_exit_code "HOST_PYTHON_BIN empty" 5 "${code}"

echo "[case] 9. --guild default を明示しても happy path (Phase 5c-1 / ADR-0019)"
mind_g="${TEST_ID}-g-default"
set +e
"${SPAWN}" --guild default generic designer "${mind_g}" >/dev/null 2>&1
code=$?
set -e
assert_exit_code "explicit --guild default" 0 "${code}"
assert_file_contains "meta records explicit guild" \
  "${AI_ORG_OS_HOME}/minds/${mind_g}/.mind-meta.md" "guild: default"

echo "[case] 10. --guild=default も同じく動く"
mind_geq="${TEST_ID}-g-eq"
set +e
"${SPAWN}" --guild=default generic designer "${mind_geq}" >/dev/null 2>&1
code=$?
set -e
assert_exit_code "--guild=default (equals form)" 0 "${code}"

echo "[case] 11. 存在しない Guild は exit 11 (manifest が無い)"
mind_nog="${TEST_ID}-no-guild"
set +e
"${SPAWN}" --guild "no-such-guild-${TEST_ID}" generic designer "${mind_nog}" \
  >/dev/null 2>&1
code=$?
set -e
assert_exit_code "unknown guild" 11 "${code}"
if [ -d "${AI_ORG_OS_HOME}/minds/${mind_nog}" ]; then
  FAIL=$((FAIL + 1))
  FAIL_MSGS+=("unknown guild: Mindspace should not be created")
  echo "  [NG]   unknown guild: Mindspace leaked"
else
  PASS=$((PASS + 1))
  echo "  [ok]   unknown guild: no Mindspace leaked"
fi

echo "[case] 12. --guild が形式違反は exit 6 (validate_arg)"
mind_badg="${TEST_ID}-bad-guild"
set +e
"${SPAWN}" --guild '../escape' generic designer "${mind_badg}" >/dev/null 2>&1
code=$?
set -e
assert_exit_code "guild path traversal" 6 "${code}"

echo "[case] 13. --guild に渡す引数が空文字は exit 6"
mind_emptyg="${TEST_ID}-empty-guild"
set +e
"${SPAWN}" --guild '' generic designer "${mind_emptyg}" >/dev/null 2>&1
code=$?
set -e
assert_exit_code "empty guild" 6 "${code}"

echo "[case] 14. malformed home Kind は Registry 経由で exit 2 (Codex P2 #88)"
# 利用者が $AI_ORG_OS_HOME/kinds/generic.md を frontmatter 壊して
# 上書きしたケース。resolve_overlay_md は file 存在で通すが registry.py check は
# parse 不能を捉えて exit 1 を返し、spawn-mind は exit 2 で fail する。
mind_bad_kind="${TEST_ID}-bad-kind"
mkdir -p "${AI_ORG_OS_HOME}/kinds"
echo "no frontmatter here" > "${AI_ORG_OS_HOME}/kinds/generic.md"
set +e
"${SPAWN}" generic designer "${mind_bad_kind}" >/dev/null 2>&1
code=$?
set -e
assert_exit_code "malformed home kind rejected by Registry" 2 "${code}"
if [ -d "${AI_ORG_OS_HOME}/minds/${mind_bad_kind}" ]; then
  FAIL=$((FAIL + 1))
  FAIL_MSGS+=("malformed home kind: Mindspace should not be created")
  echo "  [NG]   malformed home kind: Mindspace leaked"
else
  PASS=$((PASS + 1))
  echo "  [ok]   malformed home kind: no Mindspace leaked"
fi
# fixture を片付けて以降のテストに影響しないように
rm -f "${AI_ORG_OS_HOME}/kinds/generic.md"
rmdir "${AI_ORG_OS_HOME}/kinds" 2>/dev/null || true

echo "[case] 15. --workspace 省略時は default workspace が使われる (Phase 5d-2 / ADR-0022)"
# default workspace template を home overlay に置く (vcs=none = no worktree)
mkdir -p "${AI_ORG_OS_HOME}/workspaces"
cat > "${AI_ORG_OS_HOME}/workspaces/default.md" <<EOF
---
workspace: default
schema_version: "0.1"
vcs: none
purpose: test default (no git)
---

# Workspace: default (no-op for tests)
EOF
mind_wsd="${TEST_ID}-ws-default"
set +e
"${SPAWN}" generic designer "${mind_wsd}" >/dev/null 2>&1
code=$?
set -e
assert_exit_code "default workspace (omitted)" 0 "${code}"
assert_file_contains "meta records workspace: default" \
  "${AI_ORG_OS_HOME}/minds/${mind_wsd}/.mind-meta.md" "workspace: default"
# work/ subdir は vcs=none では作られない
if [ -d "${AI_ORG_OS_HOME}/minds/${mind_wsd}/work" ]; then
  FAIL=$((FAIL + 1))
  FAIL_MSGS+=("default workspace should not create work/ subdir")
  echo "  [NG]   default workspace: work/ subdir leaked"
else
  PASS=$((PASS + 1))
  echo "  [ok]   default workspace: no work/ subdir (vcs=none)"
fi

echo "[case] 16. --workspace=<unknown> は exit 12"
mind_wsu="${TEST_ID}-ws-unknown"
set +e
"${SPAWN}" --workspace "no-such-ws-${TEST_ID}" generic designer "${mind_wsu}" \
  >/dev/null 2>&1
code=$?
set -e
assert_exit_code "unknown workspace" 12 "${code}"
if [ -d "${AI_ORG_OS_HOME}/minds/${mind_wsu}" ]; then
  FAIL=$((FAIL + 1))
  FAIL_MSGS+=("unknown workspace: Mindspace should not leak")
  echo "  [NG]   unknown workspace: Mindspace leaked"
else
  PASS=$((PASS + 1))
  echo "  [ok]   unknown workspace: no Mindspace leaked"
fi

echo "[case] 17. --workspace が形式違反は exit 6"
mind_wsbad="${TEST_ID}-ws-bad"
set +e
"${SPAWN}" --workspace '../escape' generic designer "${mind_wsbad}" >/dev/null 2>&1
code=$?
set -e
assert_exit_code "workspace path traversal" 6 "${code}"

echo "[case] 18. vcs=git/mode=worktree で実 worktree が作られる (Phase 5d-2)"
# テスト用 fixture: 一時 git repo を作って workspace で指定
TEST_REPO_DIR="${AI_ORG_OS_HOME}/test-repo-${TEST_ID}"
mkdir -p "${TEST_REPO_DIR}"
git -C "${TEST_REPO_DIR}" init -q -b main
git -C "${TEST_REPO_DIR}" -c user.email=t@e -c user.name=t commit \
  --allow-empty -q -m "initial"
cat > "${AI_ORG_OS_HOME}/workspaces/dev-test.md" <<EOF
---
workspace: dev-test
schema_version: "0.1"
vcs: git
repo: ${TEST_REPO_DIR}
mode: worktree
branch_prefix: mind
---

# Workspace: dev-test (git worktree for integration test)
EOF
mind_ws_wt="${TEST_ID}-ws-wt"
set +e
"${SPAWN}" --workspace dev-test generic designer "${mind_ws_wt}" >/dev/null 2>&1
code=$?
set -e
assert_exit_code "worktree workspace spawn" 0 "${code}"
# work/ subdir が git worktree として存在し、branch が mind/<mind_name>
if [ ! -d "${AI_ORG_OS_HOME}/minds/${mind_ws_wt}/work/.git" ] && \
   [ ! -f "${AI_ORG_OS_HOME}/minds/${mind_ws_wt}/work/.git" ]; then
  FAIL=$((FAIL + 1))
  FAIL_MSGS+=("worktree: work/.git not present")
  echo "  [NG]   worktree: work/.git missing"
else
  PASS=$((PASS + 1))
  echo "  [ok]   worktree: work/.git present (worktree)"
fi
expected_branch="mind/${mind_ws_wt}"
actual_branch="$(git -C "${AI_ORG_OS_HOME}/minds/${mind_ws_wt}/work" rev-parse --abbrev-ref HEAD)"
if [ "${actual_branch}" = "${expected_branch}" ]; then
  PASS=$((PASS + 1))
  echo "  [ok]   worktree: on branch ${actual_branch}"
else
  FAIL=$((FAIL + 1))
  FAIL_MSGS+=("worktree branch mismatch: expected=${expected_branch} actual=${actual_branch}")
  echo "  [NG]   worktree: branch=${actual_branch}, want ${expected_branch}"
fi
# Mindspace 直下の Mind メタは従来通り
assert_file_exists "mindspace root CLAUDE.md (Persona)" \
  "${AI_ORG_OS_HOME}/minds/${mind_ws_wt}/CLAUDE.md"
assert_file_contains "meta records workspace: dev-test" \
  "${AI_ORG_OS_HOME}/minds/${mind_ws_wt}/.mind-meta.md" "workspace: dev-test"

echo "[case] 19. 存在しない repo の workspace は exit 13"
cat > "${AI_ORG_OS_HOME}/workspaces/ghost-repo.md" <<EOF
---
workspace: ghost-repo
schema_version: "0.1"
vcs: git
repo: /no/such/repo/${TEST_ID}
mode: worktree
---

# Workspace: ghost-repo (repo does not exist)
EOF
mind_gr="${TEST_ID}-ghost-repo"
set +e
"${SPAWN}" --workspace ghost-repo generic designer "${mind_gr}" >/dev/null 2>&1
code=$?
set -e
assert_exit_code "ghost repo workspace" 13 "${code}"
if [ -d "${AI_ORG_OS_HOME}/minds/${mind_gr}" ]; then
  FAIL=$((FAIL + 1))
  FAIL_MSGS+=("ghost repo: Mindspace should not leak")
  echo "  [NG]   ghost repo: Mindspace leaked"
else
  PASS=$((PASS + 1))
  echo "  [ok]   ghost repo: no Mindspace leaked"
fi

echo "[case] 20. branch 衝突は exit 13 (worktree add 前にチェック)"
# 既に branch を作っておく
git -C "${TEST_REPO_DIR}" branch "mind/${TEST_ID}-conflict-existing" 2>/dev/null || true
mind_conflict="${TEST_ID}-conflict-existing"
set +e
"${SPAWN}" --workspace dev-test generic designer "${mind_conflict}" >/dev/null 2>&1
code=$?
set -e
assert_exit_code "branch conflict" 13 "${code}"
if [ -d "${AI_ORG_OS_HOME}/minds/${mind_conflict}" ]; then
  FAIL=$((FAIL + 1))
  FAIL_MSGS+=("branch conflict: Mindspace should not leak")
  echo "  [NG]   branch conflict: Mindspace leaked"
else
  PASS=$((PASS + 1))
  echo "  [ok]   branch conflict: no Mindspace leaked"
fi
# fixture cleanup
rm -rf "${AI_ORG_OS_HOME}/workspaces" "${TEST_REPO_DIR}"

echo "[case] 21. Guild manifest の workspace フィールドが --workspace 省略時に使われる (Phase 5d-4 / ADR-0022)"
# 自前 Guild manifest を overlay で書き、その workspace フィールドを参照させる
mkdir -p "${AI_ORG_OS_HOME}/guilds/dev-team"
mkdir -p "${AI_ORG_OS_HOME}/workspaces"
cat > "${AI_ORG_OS_HOME}/guilds/dev-team/manifest.md" <<EOF
---
guild: dev-team
schema_version: "0.1"
purpose: test guild with workspace default
kinds: [generic]
personas: [designer, implementer, reviewer]
workspace: team-default
---
EOF
cat > "${AI_ORG_OS_HOME}/workspaces/team-default.md" <<EOF
---
workspace: team-default
schema_version: "0.1"
vcs: none
purpose: test workspace bound to dev-team guild
---
EOF
mind_gws="${TEST_ID}-gws-resolved"
set +e
"${SPAWN}" --guild dev-team generic designer "${mind_gws}" >/dev/null 2>&1
code=$?
set -e
assert_exit_code "guild workspace fallback" 0 "${code}"
assert_file_contains "meta records guild workspace: team-default" \
  "${AI_ORG_OS_HOME}/minds/${mind_gws}/.mind-meta.md" "workspace: team-default"

echo "[case] 22. --workspace 明示が Guild manifest workspace より優先される"
# 別 workspace を用意して --workspace で override する
cat > "${AI_ORG_OS_HOME}/workspaces/explicit-override.md" <<EOF
---
workspace: explicit-override
schema_version: "0.1"
vcs: none
purpose: explicit workspace beats guild default
---
EOF
mind_explicit="${TEST_ID}-explicit-over-guild"
set +e
"${SPAWN}" --guild dev-team --workspace explicit-override generic designer \
  "${mind_explicit}" >/dev/null 2>&1
code=$?
set -e
assert_exit_code "explicit beats guild" 0 "${code}"
assert_file_contains "meta records explicit workspace: explicit-override" \
  "${AI_ORG_OS_HOME}/minds/${mind_explicit}/.mind-meta.md" "workspace: explicit-override"

echo "[case] 23. Guild manifest に workspace 無しなら default が使われる"
# まず default workspace template があることを確認 (case 15 で消されている可能性)
mkdir -p "${AI_ORG_OS_HOME}/workspaces"
cat > "${AI_ORG_OS_HOME}/workspaces/default.md" <<EOF
---
workspace: default
schema_version: "0.1"
vcs: none
purpose: test default fallback
---
EOF
# workspace 無しの Guild を作る
mkdir -p "${AI_ORG_OS_HOME}/guilds/no-ws"
cat > "${AI_ORG_OS_HOME}/guilds/no-ws/manifest.md" <<EOF
---
guild: no-ws
schema_version: "0.1"
purpose: guild without workspace field
kinds: [generic]
personas: [designer, implementer, reviewer]
---
EOF
mind_no_ws="${TEST_ID}-no-ws-fallback"
set +e
"${SPAWN}" --guild no-ws generic designer "${mind_no_ws}" >/dev/null 2>&1
code=$?
set -e
assert_exit_code "no-ws fallback to default" 0 "${code}"
assert_file_contains "meta records default workspace" \
  "${AI_ORG_OS_HOME}/minds/${mind_no_ws}/.mind-meta.md" "workspace: default"

# fixture cleanup (Phase 5d-4 ケース)
rm -rf "${AI_ORG_OS_HOME}/guilds/dev-team" "${AI_ORG_OS_HOME}/guilds/no-ws"
rm -rf "${AI_ORG_OS_HOME}/workspaces"

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
if [ -d "${AI_ORG_OS_HOME}/minds/${mind_no_claude}" ]; then
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
