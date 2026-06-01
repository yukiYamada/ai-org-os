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
# 設計上の位置づけ (CLAUDE.md §3.1 / ADR-0017 self-check):
#   - 本スクリプトは **host 側の Warden facility (層 A)** であり、Mind プロセス
#     (層 B) に対して停止信号 + 子孫プロセスツリーの teardown を行う。
#   - 「Mind の作業」を監視するのは Mind 自身だが、「Mind を破棄する」のは
#     Warden 側の責務 (生死は Warden が握る)。よって本スクリプトが Mind の
#     子孫プロセス (claude.exe / subshell 等) を含むツリー全体を kill するのは
#     責務違反ではない。Mind が産んだプロセスは Mind の所有物であり、Mind 個体
#     が消える時に運命を共にする (ADR-0014 / ADR-0023 と同じ精神)。
#
# Process tree teardown (#133):
#   - mind-loop.sh は subshell `(cd ...; claude -p ...)` で claude を起動する。
#     mind-loop の PID にだけ TERM/KILL を送ると、Windows + MSYS bash 環境では
#     subshell の死で claude.exe が orphan 化 (parent=1) し、`rm -rf $MIND_DIR`
#     が "Device or resource busy" で失敗する。
#   - 対処: mind-loop の PID + 全子孫を kill する。
#     POSIX path: `ps -ef` で再帰的に子孫 PID を収集 → kill -KILL でツリー討滅
#     Windows path: `taskkill //T //F //PID <pid>` で Windows カーネルに任せる
#     どちらも best-effort。失敗しても `rm -rf` は試みる (F3 / ADR-0013 §1)。
#
set -euo pipefail

if [ "$#" -ne 1 ]; then
  echo "Usage: $0 <mind-name>" >&2
  echo "Example: $0 my-first-mind" >&2
  exit 1
fi

MIND_NAME="$1"

# MIND_NAME のバリデーション。spawn-mind.sh / mind-loop.sh の _VALID_NAME_RE と
# 同じ規則。緩めるとパス traversal (../escape) で任意ディレクトリに rm -rf や
# process sweep を仕掛けられる。
# (#133 fix と同時に明文化: sweep_orphan_minds_for が MIND_DIR を cwd 一致で
# kill するため、ここで MIND_NAME を絞らないと cwd=/etc 等の process を kill
# する経路が出来てしまう)
_VALID_NAME_RE='^[A-Za-z0-9._-]{1,64}$'
if [[ ! "${MIND_NAME}" =~ ${_VALID_NAME_RE} ]]; then
  echo "[ERROR] Invalid mind-name: '${MIND_NAME}'" >&2
  echo "[HINT] Must match ${_VALID_NAME_RE} (no quotes, backslashes, spaces, path separators)" >&2
  exit 6
fi

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
    # Windows + MSYS で Python subprocess 経由で bash を呼ぶと argv[1] が
    # backslash 区切りの Windows path になる (例:
    # "C:\Users\...\mind-loop.sh") ため、forward-slash と backslash の両方を
    # 受け入れる。比較は token の **末尾** が "mind-loop.sh" であることのみ。
    case "${arg}" in
      mind-loop.sh|*/mind-loop.sh|*\\mind-loop.sh) has_script=1 ;;
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

# ----- #133: process tree teardown (cross-platform) -----
#
# mind-loop.sh の subshell が claude を起動する関係上、mind-loop の PID にだけ
# kill を送ると、Windows + MSYS bash 環境では claude.exe が orphan として残る。
# 結果として `rm -rf $MIND_DIR` が "Device or resource busy" で失敗する。
#
# 本セクションは「PID のプロセスツリーを丸ごと kill する」helper を提供する。
# POSIX path と Windows path の両方を備え、利用可能な方を順に試す best-effort。
# 失敗しても本体の rm は走らせる (F3 / ADR-0013 §1)。

# collect_descendants <root_pid>
#   `ps -ef` の (PID, PPID) で root_pid 配下を再帰的に収集し、行ごとに出力する。
#   root 自身は **含まない** (root は呼び出し側で kill する)。
#   ps -ef が無い環境では何も出力しない (= empty = caller fallback).
#
#   Note: ps -ef は MSYS / Linux / macOS のいずれでも入っている (POSIX 標準)。
#         ただし PPID 列の位置は実装で揺れるため、`-o pid,ppid` を使う。
collect_descendants() {
  local root_pid="$1"
  if ! command -v ps >/dev/null 2>&1; then
    return 0
  fi
  # `ps -eo pid,ppid` で全プロセスを取得。ヘッダ 1 行をスキップ。
  local pairs
  pairs="$(ps -eo pid,ppid 2>/dev/null | awk 'NR>1 {print $1" "$2}')" || return 0
  if [ -z "${pairs}" ]; then
    return 0
  fi
  # BFS: queue に root の直接の子を入れ、次々に展開していく。
  local queue=""
  local pid ppid
  # Initialize queue with root's direct children.
  while IFS=' ' read -r pid ppid; do
    if [ "${ppid}" = "${root_pid}" ]; then
      queue="${queue} ${pid}"
    fi
  done <<< "${pairs}"

  # BFS expansion.
  local processed=""
  while [ -n "${queue# }" ]; do
    # pop head
    local head="${queue# }"
    head="${head%% *}"
    queue="${queue# }"
    queue="${queue#${head}}"
    # Guard against cycles (PID reuse / malformed ps output): skip already-seen.
    case " ${processed} " in
      *" ${head} "*) continue ;;
    esac
    processed="${processed} ${head}"
    echo "${head}"
    # enqueue head's children
    while IFS=' ' read -r pid ppid; do
      if [ "${ppid}" = "${head}" ]; then
        queue="${queue} ${pid}"
      fi
    done <<< "${pairs}"
  done
}

# kill_process_tree <root_pid>
#   root_pid + その全子孫プロセスを kill する。試行順:
#     1. Windows: taskkill //T //F //PID を試す (子孫を一気に始末)
#     2. POSIX:   collect_descendants で子孫 PID を集め、SIGKILL を送る
#                 (子→親の順で送って zombie 化を抑える)
#   どちらも best-effort。stderr は dump せず flat な進捗だけ出す。
kill_process_tree() {
  local root_pid="$1"
  if [ -z "${root_pid}" ]; then
    return 0
  fi

  # 1. Windows path: taskkill が PATH に居れば最優先で使う。
  #    //T = kill tree、//F = force、//PID = PID 指定。
  #    MSYS path-translation を回避するため `//` (double-slash) で渡す。
  #    Windows カーネル側でツリーを把握しているので最も信頼できる。
  if command -v taskkill >/dev/null 2>&1; then
    # exit code は無視 (PID が既に死んでいるとエラー終了するが問題なし)。
    taskkill //T //F //PID "${root_pid}" >/dev/null 2>&1 || true
    # taskkill が走れば子孫も止まる。POSIX path もあとで補強として走らせる
    # (taskkill が把握しきれない MSYS フォーク等を救う)。
  fi

  # 2. POSIX path: ps -ef ベースで子孫を集め、SIGKILL を送る。
  #    Windows でも MSYS の bash プロセス側を補強する意味で実行。
  local descendants
  descendants="$(collect_descendants "${root_pid}")"
  if [ -n "${descendants}" ]; then
    # 子→孫の順で出力されるので、reverse して葉から kill する
    # (= zombie を最小化、親が waitpid 出来る前に消える子を減らす)。
    local pid
    local reversed=""
    while IFS= read -r pid; do
      reversed="${pid} ${reversed}"
    done <<< "${descendants}"
    for pid in ${reversed}; do
      kill -KILL "${pid}" 2>/dev/null || true
    done
  fi

  # 3. 最後に root 自身。verify は caller の責務 (mind-loop owner check 後の
  #    流れに乗る)。
  kill -KILL "${root_pid}" 2>/dev/null || true
}

# wait_for_pid_gone <pid> <timeout_seconds>
#   PID が消えるまで poll する。消えたら 0、timeout で 1 を返す。
wait_for_pid_gone() {
  local pid="$1"
  local timeout="$2"
  local waited=0
  while [ "${waited}" -lt "${timeout}" ]; do
    if ! kill -0 "${pid}" 2>/dev/null; then
      return 0
    fi
    sleep 1
    waited=$((waited + 1))
  done
  if kill -0 "${pid}" 2>/dev/null; then
    return 1
  fi
  return 0
}

# sweep_orphan_minds_for <mind_name>
#   mind-loop の subshell が claude を起動した後 orphan 化したケース
#   (#133: parent=init=1 になり kill_process_tree の PPID 連鎖から外れる) に
#   備えて、Mind に紐づく orphan を後始末する。
#
#   識別方法 (security 重視、CLAUDE.md §3.3):
#     - POSIX: /proc/<pid>/cwd が ${MIND_DIR} の絶対 path と一致する process を
#              選ぶ。cwd は kernel-managed なので caller が偽装できない (= 安全)。
#     - Windows / /proc 不在環境: ./proc が無いので argv での識別に fallback。
#              ただし mind-loop.sh の PROMPT は固定文字列を含むので、それと
#              MIND_NAME の組み合わせで match する。
#
#   見つかった PID は kill_process_tree で討滅する。失敗しても下流の rm は走る。
sweep_orphan_minds_for() {
  local mind_name="$1"
  local mind_dir_abs="${MIND_DIR}"
  local found_any=0

  # POSIX path: /proc 経由で cwd を見る。
  if [ -d /proc ] && [ -r /proc ]; then
    local pid_entry
    for pid_entry in /proc/[0-9]*; do
      [ -e "${pid_entry}" ] || continue
      local pid="${pid_entry##*/}"
      # 自分自身 / parent は除外 (rm -rf する shell が cwd を持っていても切ない)
      [ "${pid}" = "$$" ] && continue
      [ "${pid}" = "${PPID:-0}" ] && continue
      local cwd_target
      cwd_target="$(readlink "${pid_entry}/cwd" 2>/dev/null || true)"
      if [ -z "${cwd_target}" ]; then
        continue
      fi
      # 完全一致のみ (prefix match だと sibling Mind に誤爆する)
      if [ "${cwd_target}" = "${mind_dir_abs}" ]; then
        echo "[kill-mind] Found orphan process pid=${pid} cwd=${cwd_target}"
        kill_process_tree "${pid}"
        found_any=1
      fi
    done
  fi

  # /proc fallback: Windows / macOS で /proc が無い場合。
  # ここでは ps の `-o pid,command` で argv を引いて mind 名 + "mind-loop" or
  # "cycle .* for mind <name>" の組み合わせを探す。
  # ただし argv は caller が偽装できるため、これは best-effort。識別失敗は
  # silent に諦める (= 同名 mind を spawn しないという運用前提に依存)。
  if [ "${found_any}" -eq 0 ] && [ ! -d /proc ]; then
    if command -v ps >/dev/null 2>&1; then
      # `ps -ef` の最終列以降が command。awk で pid と残りを分離。
      # MSYS bash の `ps -ef` は COMMAND 列に full argv が出る。
      local line pid_field cmd_field
      while IFS= read -r line; do
        # 列分解: PID は 2 番目 (UID PID PPID ...)、COMMAND は残り。
        pid_field="$(printf '%s' "${line}" | awk '{print $2}')"
        cmd_field="$(printf '%s' "${line}" | awk '{$1=$2=$3=$4=$5=$6=""; print}')"
        [ -z "${pid_field}" ] && continue
        case "${cmd_field}" in
          *"cycle "*"for mind ${mind_name}"*)
            echo "[kill-mind] Found orphan process (argv match) pid=${pid_field}"
            kill_process_tree "${pid_field}"
            found_any=1
            ;;
        esac
      done < <(ps -ef 2>/dev/null | tail -n +2)
    fi
  fi

  return 0
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
      # graceful 終了を待つ (loop 本体は SIGTERM 受信時に「現 cycle 完了後に
      # exit」する設計、最大 5s 待つ)。
      if ! wait_for_pid_gone "${LOOP_PID}" 5; then
        echo "[kill-mind] Loop did not stop in 5s, escalating to process-tree kill"
        # 念のため SIGKILL 前にもう一度検証
        if verify_loop_owner "${LOOP_PID}" "${MIND_NAME}"; then
          # #133 fix: 単純な kill -KILL では subshell 配下の claude.exe が
          # orphan として残る (Windows + MSYS の親子関係が PE / fork で
          # 切れるため)。プロセスツリー丸ごと teardown する。
          kill_process_tree "${LOOP_PID}"
        else
          echo "[kill-mind] WARNING: pid ${LOOP_PID} no longer looks like our loop; skipping SIGKILL" >&2
        fi
      else
        # SIGTERM で loop が graceful 停止した場合でも、subshell の claude が
        # 既に orphan (parent=1) になっている可能性がある。残骸を掃除する。
        echo "[kill-mind] Loop stopped gracefully; sweeping orphan descendants if any"
      fi
    fi
  fi
fi
# #133: loop PID が既に死んでいた (mind-loop が crash した) / kill した直後にも、
# orphan の claude が残っている可能性があるので Mindspace の cwd を持つ process を
# 掃除する。PID file が無い場合でも走らせる (= mind-loop crash + orphan child
# のリカバリ pass)。
sweep_orphan_minds_for "${MIND_NAME}" || true

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
# #133: 子孫プロセスのファイルハンドル保持で rm -rf が失敗するケースに備え、
# 失敗時は clear な WARN + manual cleanup hint を出して non-zero exit する
# (F3 / ADR-0013 §1: 検出と続行を両立させつつ、上位 (dogfooding script) が
# 反応できる exit code を提供する)。
if ! rm -rf "${MIND_DIR}" 2>&1; then
  echo "[ERROR] Failed to remove Mindspace at ${MIND_DIR}" >&2
  echo "[HINT] A descendant process may still be holding files open. Check:" >&2
  echo "[HINT]   ps -ef | grep '${MIND_NAME}'" >&2
  if command -v tasklist >/dev/null 2>&1; then
    echo "[HINT]   tasklist | findstr claude" >&2
  fi
  echo "[HINT] Then re-run kill-mind, or kill the stragglers manually + rm -rf ${MIND_DIR}" >&2
  exit 7
fi

echo "[kill-mind] Mind '${MIND_NAME}' is gone. Its Mindspace and dispatch history are irrecoverable."
