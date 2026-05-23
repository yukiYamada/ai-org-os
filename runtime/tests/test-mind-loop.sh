#!/usr/bin/env bash
#
# test-mind-loop.sh — runtime/pillars/lifecycle/mind-loop.sh の振る舞いを検証する。
#
# 軸:
#   - claude CLI 未インストール環境でも動くよう、AI_ORG_OS_CLAUDE_BIN にスタブを差す
#   - 引数バリデーション（mind 不在、二重起動、不正 period）
#   - 最大 cycles で自然停止する
#   - SIGTERM で停止する
#   - PID file / log file が正しく作られ、終了時に PID file が掃除される
#   - kill-mind.sh が外側ループを停止できる
#
# テスト中の claude スタブは "fake-claude.sh" を $TMP に作って AI_ORG_OS_CLAUDE_BIN で
# 指定する。短時間で exit して prompt 引数をログするだけのダミー。
#
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RUNTIME_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
SPAWN="${RUNTIME_DIR}/pillars/lifecycle/spawn-mind.sh"
KILL="${RUNTIME_DIR}/pillars/lifecycle/kill-mind.sh"
LOOP="${RUNTIME_DIR}/pillars/lifecycle/mind-loop.sh"

TEST_ID="mt$$-$(date +%s)"
PASS=0
FAIL=0
FAIL_MSGS=()

# claude スタブの設置
STUB_DIR="$(mktemp -d)"
cat > "${STUB_DIR}/fake-claude.sh" <<'STUB'
#!/usr/bin/env bash
# Mind loop test stub. Just echoes the prompt and exits 0.
# Sleep slightly so the cycle isn't instant (helps signal-during-cycle tests).
echo "fake-claude received args: $@"
sleep 0.2
exit 0
STUB
chmod +x "${STUB_DIR}/fake-claude.sh"
export AI_ORG_OS_CLAUDE_BIN="${STUB_DIR}/fake-claude.sh"

cleanup() {
  find "${RUNTIME_DIR}/minds" -maxdepth 1 -type d -name "${TEST_ID}-*" -exec rm -rf {} + 2>/dev/null || true
  rm -rf "${STUB_DIR}"
}
trap cleanup EXIT

assert_exit_code() {
  local label="$1" expected="$2" actual="$3"
  if [ "${actual}" = "${expected}" ]; then
    PASS=$((PASS + 1)); echo "  [ok]   ${label}: exit ${actual}"
  else
    FAIL=$((FAIL + 1)); FAIL_MSGS+=("${label}: expected ${expected}, got ${actual}")
    echo "  [NG]   ${label}: expected ${expected}, got ${actual}"
  fi
}

assert_true() {
  local label="$1" cond="$2"
  if [ "${cond}" = "1" ]; then
    PASS=$((PASS + 1)); echo "  [ok]   ${label}"
  else
    FAIL=$((FAIL + 1)); FAIL_MSGS+=("${label}")
    echo "  [NG]   ${label}"
  fi
}

# ---- 1. mind 不在で exit 2
echo "[case] 1. 存在しない Mind を指定すると exit 2"
set +e
"${LOOP}" "${TEST_ID}-nonexistent" --period 0 --max-cycles 1 >/dev/null 2>&1
code=$?
set -e
assert_exit_code "loop for missing mind" 2 "${code}"

# ---- 2. 不正な --period は exit 1
echo "[case] 2. --period に非数値を渡すと exit 1"
# 先に Mind を作っておく（period バリデーションは引数解析時、Mind 存在チェックの前）
"${SPAWN}" generic designer "${TEST_ID}-vargs" >/dev/null 2>&1 || true
set +e
"${LOOP}" "${TEST_ID}-vargs" --period abc >/dev/null 2>&1
code=$?
set -e
assert_exit_code "invalid period" 1 "${code}"

# ---- 3. --max-cycles で自然停止 + PID file の生成・掃除
echo "[case] 3. --max-cycles=2 で 2 cycle 後に自然停止する"
mind="${TEST_ID}-max"
"${SPAWN}" generic designer "${mind}" >/dev/null 2>&1
mind_dir="${RUNTIME_DIR}/minds/${mind}"
pid_file="${mind_dir}/.mind-loop.pid"
log_file="${mind_dir}/mind-loop.log"

set +e
"${LOOP}" "${mind}" --period 0 --max-cycles 2 >/dev/null 2>&1
code=$?
set -e
assert_exit_code "natural stop after max-cycles" 0 "${code}"

# ログに cycle 1 / cycle 2 / reached max-cycles の痕跡があるはず
grep -q "cycle 1" "${log_file}" 2>/dev/null && grep -q "cycle 2" "${log_file}" 2>/dev/null
[ $? -eq 0 ] && cyc_ok=1 || cyc_ok=0
assert_true "log contains cycle 1 and cycle 2" "${cyc_ok}"

# PID file は終了時に消えているはず（trap cleanup_pid_file EXIT）
[ ! -f "${pid_file}" ] && pid_ok=1 || pid_ok=0
assert_true "pid file removed after natural stop" "${pid_ok}"

# claude スタブの出力痕跡（fake-claude received args）が log に居る
grep -q "fake-claude received args" "${log_file}" 2>/dev/null && stub_ok=1 || stub_ok=0
assert_true "stub claude was invoked" "${stub_ok}"

# ---- 4. SIGTERM で停止する（kill-mind.sh 経由）
echo "[case] 4. kill-mind.sh が外側ループを停止する"
mind="${TEST_ID}-sig"
"${SPAWN}" generic designer "${mind}" >/dev/null 2>&1
mind_dir="${RUNTIME_DIR}/minds/${mind}"
pid_file="${mind_dir}/.mind-loop.pid"

# 長めのループを背景で起動（period=1 で max 無限）。テストが暴走しないよう
# max-cycles=20 を保険として設定（period 1s × 20 = 20s 上限）。
"${LOOP}" "${mind}" --period 1 --max-cycles 20 >/dev/null 2>&1 &
loop_pid=$!

# loop プロセスが PID file を書くまで待つ（最大 3 秒）
waited=0
while [ "${waited}" -lt 3 ]; do
  if [ -f "${pid_file}" ]; then break; fi
  sleep 0.5
  waited=$((waited + 1))
done

assert_true "pid file created during loop" "$([ -f "${pid_file}" ] && echo 1 || echo 0)"

# kill-mind.sh で停止 (Mindspace も消える)
"${KILL}" "${mind}" >/dev/null 2>&1
kill_rc=$?
assert_exit_code "kill-mind.sh exit ok" 0 "${kill_rc}"

# loop プロセスが SIGTERM で死んだか確認（最大 7 秒待つ: kill-mind.sh が 5s grace + 余白）
waited=0
while [ "${waited}" -lt 7 ]; do
  if ! kill -0 "${loop_pid}" 2>/dev/null; then break; fi
  sleep 1
  waited=$((waited + 1))
done

if kill -0 "${loop_pid}" 2>/dev/null; then
  # 念のため掃除（テストが残骸を残さないよう）
  kill -KILL "${loop_pid}" 2>/dev/null || true
  assert_true "loop process terminated after kill-mind.sh" 0
else
  assert_true "loop process terminated after kill-mind.sh" 1
fi

# Mindspace は kill-mind.sh で消されているはず
[ ! -d "${mind_dir}" ] && md_ok=1 || md_ok=0
assert_true "Mindspace removed after kill-mind.sh" "${md_ok}"

# ---- 5. 二重起動を拒否する（exit 3）
echo "[case] 5. 同じ Mind に loop を二重起動すると exit 3"
mind="${TEST_ID}-dup"
"${SPAWN}" generic designer "${mind}" >/dev/null 2>&1
mind_dir="${RUNTIME_DIR}/minds/${mind}"

# 1 回目: バックグラウンド起動
"${LOOP}" "${mind}" --period 1 --max-cycles 10 >/dev/null 2>&1 &
first_pid=$!
# pid file の書き込みを待つ
waited=0
while [ "${waited}" -lt 3 ]; do
  if [ -f "${mind_dir}/.mind-loop.pid" ]; then break; fi
  sleep 0.5
  waited=$((waited + 1))
done

# 2 回目: 即時 exit 3 を期待
set +e
"${LOOP}" "${mind}" --period 0 --max-cycles 1 >/dev/null 2>&1
dup_rc=$?
set -e
assert_exit_code "duplicate loop start" 3 "${dup_rc}"

# 1 回目を片付け
kill -TERM "${first_pid}" 2>/dev/null || true
# 待つ
waited=0
while [ "${waited}" -lt 5 ]; do
  if ! kill -0 "${first_pid}" 2>/dev/null; then break; fi
  sleep 1
  waited=$((waited + 1))
done
kill -KILL "${first_pid}" 2>/dev/null || true
rm -rf "${mind_dir}"

# ---- summary ----
echo ""
echo "[summary] passed: ${PASS}, failed: ${FAIL}"
if [ "${FAIL}" -gt 0 ]; then
  echo "[summary] failures:"
  for msg in "${FAIL_MSGS[@]}"; do
    echo "  - ${msg}"
  done
  exit 1
fi
