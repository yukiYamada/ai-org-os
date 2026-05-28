#!/usr/bin/env bash
#
# kill-mind.sh — Mind を破棄する（Mindspace ごと消す）
#
# 用法:
#   ./runtime/pillars/lifecycle/kill-mind.sh <mind-name>
#
# 例:
#   ./runtime/pillars/lifecycle/kill-mind.sh my-first-mind
#
# Axiom との関係:
#   - 思考が消えれば Mindspace も消える（不可侵原則の系として）
#   - 共有が必要だったものは Dispatch 経由で他 Mind に渡されていたはず
#   - 破棄後の復元は仕組みとして提供しない（不可逆）
#
# Phase 1 の仕様:
#   - Warden の 3 段階プロセス（要求→承認→実行）の「実行」相当のみ簡略実装
#   - Phase 2 以降は Warden を経由する
#
set -euo pipefail

if [ "$#" -ne 1 ]; then
  echo "Usage: $0 <mind-name>" >&2
  echo "Example: $0 my-first-mind" >&2
  exit 1
fi

MIND_NAME="$1"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# Phase 5b-4 (#81 / ADR-0018): Mindspace は $AI_ORG_OS_HOME/minds/ 配下。
RUNTIME_DIR="$(cd "${SCRIPT_DIR}/../.." && pwd)"
DEFAULT_RUNTIME_HOME="${HOME:-${USERPROFILE:-}}/.ai-org-os"
RUNTIME_HOME="${AI_ORG_OS_HOME:-${DEFAULT_RUNTIME_HOME}}"
MIND_DIR="${RUNTIME_HOME}/minds/${MIND_NAME}"

if [ ! -d "${MIND_DIR}" ]; then
  echo "[ERROR] Mind '${MIND_NAME}' does not exist (looked for ${MIND_DIR})" >&2
  echo "[HINT] List existing Minds: ${SCRIPT_DIR}/list-minds.sh" >&2
  exit 2
fi

# Phase 5a-2 / ADR-0010: 外側ループが動いていれば先に停止する。
#
# Codex P1 PR #61 (1st): PID 検証なしで kill すると、再利用された PID を持つ
# 無関係なプロセスを殺してしまう可能性がある。
#
# Codex P1 PR #61 (2nd): mind_name を grep -E の regex に直接埋め込むと、
# valid name に含まれる `.` がワイルドカードになる（abc.def が abcXdef にマッチ）。
# 修正方針: regex を捨て、/proc/<pid>/cmdline の argv token を NUL 区切りで読み、
# exact string 一致で判定する（"mind-loop.sh" を末尾に持つ argv と、mind_name と
# 完全一致する argv の両方が存在することを確認）。
#
# /proc が無い環境（macOS/Windows の一部）では best-effort で kill するが警告する。
verify_loop_owner() {
  local pid="$1"
  local mind_name="$2"
  if [ ! -r "/proc/${pid}/cmdline" ]; then
    echo "[kill-mind] WARNING: /proc not available, cannot verify pid ${pid} identity (best-effort kill)" >&2
    return 0
  fi
  local has_script=0 has_mind=0 arg
  while IFS= read -r -d '' arg; do
    case "${arg}" in
      mind-loop.sh|*/mind-loop.sh) has_script=1 ;;
    esac
    if [ "${arg}" = "${mind_name}" ]; then
      has_mind=1
    fi
  done < "/proc/${pid}/cmdline"
  if [ "${has_script}" -eq 1 ] && [ "${has_mind}" -eq 1 ]; then
    return 0
  fi
  return 1
}

PID_FILE="${MIND_DIR}/.mind-loop.pid"
if [ -f "${PID_FILE}" ]; then
  LOOP_PID="$(cat "${PID_FILE}" 2>/dev/null || echo "")"
  if [ -n "${LOOP_PID}" ] && kill -0 "${LOOP_PID}" 2>/dev/null; then
    if ! verify_loop_owner "${LOOP_PID}" "${MIND_NAME}"; then
      echo "[kill-mind] WARNING: pid ${LOOP_PID} is alive but does not look like a mind-loop for '${MIND_NAME}'" >&2
      echo "[kill-mind] Skipping kill to avoid harming an unrelated process. Mindspace will still be removed." >&2
    else
      echo "[kill-mind] Stopping mind-loop (pid ${LOOP_PID})"
      kill -TERM "${LOOP_PID}" 2>/dev/null || true
      # graceful 終了を待つ
      WAITED=0
      while [ "${WAITED}" -lt 5 ]; do
        if ! kill -0 "${LOOP_PID}" 2>/dev/null; then
          break
        fi
        sleep 1
        WAITED=$((WAITED + 1))
      done
      if kill -0 "${LOOP_PID}" 2>/dev/null; then
        echo "[kill-mind] Loop did not stop in 5s, sending SIGKILL"
        # 念のため SIGKILL 前にもう一度検証
        if verify_loop_owner "${LOOP_PID}" "${MIND_NAME}"; then
          kill -KILL "${LOOP_PID}" 2>/dev/null || true
        else
          echo "[kill-mind] WARNING: pid ${LOOP_PID} no longer looks like our loop; skipping SIGKILL" >&2
        fi
      fi
    fi
  fi
fi

# Phase 5c-2 P1/P2 fix (#91 Codex): registry を先に消す。
# registry が authoritative source (persona / guild) なので、先に invalidate
# する。順序を逆にすると、削除途中で中断された場合 (signal / crash / forced
# stop) に Mindspace は無いが registry は残る = 「registry あり = 生きてる」
# と axiom check が判定する一方 Mindspace 不在で Dispatch が受け取れない、
# という stale "live" mind が出来てしまう。
# 「registry 先消し」によって中断時は registry 無 → 即 forbidden (#91 2 回目
# 修正と整合) となり、Mindspace 残骸があっても axiom 上は安全側に倒れる。
REGISTRY_ENTRY="${RUNTIME_HOME}/registry/minds/${MIND_NAME}.md"
if [ -f "${REGISTRY_ENTRY}" ]; then
  if ! rm -f "${REGISTRY_ENTRY}"; then
    echo "[ERROR] Failed to remove registry entry ${REGISTRY_ENTRY}; aborting kill" >&2
    echo "[HINT] Mindspace is still intact at ${MIND_DIR}" >&2
    exit 5
  fi
  echo "[kill-mind] Removed registry entry (authoritative): ${REGISTRY_ENTRY}"
fi

# Phase 5d-3 (ADR-0022): git worktree のクリーンアップ。
# Mindspace 直下に `work/` subdir があり、その中の `.git` が file (= worktree
# marker) なら spawn-mind が作った worktree。そこに記録されている repo path
# を読んで `git worktree remove --force` で登録解除する。
# 設計の意図:
# - workspace.py は不要 (= template が削除/移動済でも cleanup できる、
#   self-describing な worktree marker file から repo を逆引きする)
# - registry 削除 *後* に worktree remove を試みる (registry-first invariant
#   を守る、Codex P2 #91 の原則)
# - worktree remove 失敗 (repo 消失等) は WARN で続行 (= Mindspace rm を
#   block しない、kill の最終目的は Mindspace の物理削除)
# - rm -rf Mindspace の *前* に worktree remove する必要がある:
#   git は path 経由で .git/worktrees/<name>/ 登録を辿るため、Mindspace を
#   先に消すと git は path から repo を見つけられず、登録が orphan する
WORK_DIR="${MIND_DIR}/work"
WORK_GIT_MARKER="${WORK_DIR}/.git"
if [ -f "${WORK_GIT_MARKER}" ]; then
  # worktree marker file は最初の行に `gitdir: <repo>/.git/worktrees/<name>`
  # の形式で repo の git dir path を持つ (git linked-worktree の標準形式)
  GITDIR_LINE="$(head -1 "${WORK_GIT_MARKER}" 2>/dev/null || true)"
  if [[ "${GITDIR_LINE}" == gitdir:* ]]; then
    # `gitdir: <path>` から <path> を抽出 (前後 whitespace を除去)
    WORK_GITDIR="${GITDIR_LINE#gitdir:}"
    WORK_GITDIR="${WORK_GITDIR# }"
    # GITDIR_PATH = <repo>/.git/worktrees/<name>
    # → repo path は dir 2 段上 (<repo>)
    WORK_REPO_GITDIR="$(dirname "$(dirname "${WORK_GITDIR}")")"
    WORK_REPO="$(dirname "${WORK_REPO_GITDIR}")"
    if [ -d "${WORK_REPO}/.git" ] || [ -f "${WORK_REPO}/.git" ]; then
      echo "[kill-mind] Removing git worktree: ${WORK_DIR} (repo: ${WORK_REPO})"
      if ! git -C "${WORK_REPO}" worktree remove --force "${WORK_DIR}" 2>&1; then
        echo "[WARN] git worktree remove failed; '${WORK_REPO}/.git/worktrees/' may have an orphan entry." >&2
        echo "[HINT] After kill, run: git -C ${WORK_REPO} worktree prune" >&2
      fi
    else
      echo "[WARN] worktree marker points at ${WORK_REPO} but that is no longer a git repo." >&2
      echo "[HINT] Skipping worktree cleanup; Mindspace will still be removed." >&2
    fi
  else
    echo "[WARN] ${WORK_GIT_MARKER} does not look like a git worktree marker (no 'gitdir:' line)." >&2
    echo "[HINT] Skipping worktree cleanup; Mindspace will still be removed." >&2
  fi
fi

# Phase 5d-7 (ADR-0023 / #104): Mind と運命を共にする dispatch 履歴の削除。
# ADR-0023 で確定した原則「Mind identity = spawn-kill 期間に限定、同名再
# spawn は別 Mind」に従い、conduit-storage/{inbox,archive}/<mind>/ も Mind の
# 所有物として削除する。これにより:
# - 再 spawn 時に古い dispatch が紛れ込まない (= dogfooding 2026-05-28 で
#   検出された混乱の解消)
# - Mindspace と dispatch 履歴が同じ life cycle を持つ semantic 統一
# 順序: registry 削除の **後** に置く (= registry-first invariant を守りつつ、
# Mindspace rm より前に走らせて「死後にも観測 file が残る」状態を避ける)。
# 失敗時は WARN + 続行 (= kill の本旨 = Mindspace 削除を block しない)。
CONDUIT_INBOX_DIR="${RUNTIME_HOME}/conduit-storage/inbox/${MIND_NAME}"
CONDUIT_ARCHIVE_DIR="${RUNTIME_HOME}/conduit-storage/archive/${MIND_NAME}"
for dispatch_dir in "${CONDUIT_INBOX_DIR}" "${CONDUIT_ARCHIVE_DIR}"; do
  if [ -d "${dispatch_dir}" ]; then
    if ! rm -rf "${dispatch_dir}"; then
      echo "[WARN] Failed to remove dispatch dir ${dispatch_dir}; manual cleanup may be needed." >&2
    else
      echo "[kill-mind] Removed dispatch dir: ${dispatch_dir}"
    fi
  fi
done

echo "[kill-mind] Destroying Mindspace at ${MIND_DIR}"
rm -rf "${MIND_DIR}"

echo "[kill-mind] Mind '${MIND_NAME}' is gone. Its Mindspace and dispatch history are irrecoverable."
