#!/usr/bin/env bash
#
# Phase 5f Step 2 dogfooding kick-off helper.
#
# Step 2 (#124) は「alice (designer) + bob (implementer) + gm-default (guildmaster)
# + carol (reviewer) の 4 Mind を spawn して 5-10 cycle 動かす」operational phase。
# 本 script は **準備の boilerplate を 1 コマンドに集約**して、operator が
# 「動かす」と「観察する」に集中できるようにする。
#
# 用法:
#   ./setup.sh setup [--with-issue] [--start-loops]
#                   - 4 Mind を spawn (alice/bob/gm-default/carol)
#                     --with-issue: テスト用 Issue を Inbox に投入
#                     --start-loops: mind-loop を 4 つ background で起動
#                                    (claude code login が動くこと前提)
#   ./setup.sh status
#                   - 4 Mind の登録状況 + observe.py --realm + observe.py --trace
#                     (直近 1h) を 1 画面に出す
#   ./setup.sh cleanup
#                   - 4 Mind を kill-mind.sh で全消去 (Mindspace / registry / inbox)
#   ./setup.sh -h | --help
#                   - usage を表示
#
# 前提:
#   - bash runtime/host/setup.sh が一度走っている (= $AI_ORG_OS_HOME 配下が整備済)
#   - 別ターミナルで Conductor (docker compose up -d --build) が動いている
#     ことが望ましい (cycle 観察のため)
#   - --start-loops を使うなら claude code login 済
#
# 観察観点 (Step 2 のチェックリスト、Issue #124):
#   - 4 Mind が claim / dispatch / archive を 1 周できるか
#   - Warden の guildmaster 観察と dispatch-prompt が機能するか
#   - 失敗 mode を観察:
#       * 循環ループ (A→B→A→B...)
#       * context drift (Persona と実挙動の乖離)
#       * API quota 枯渇時の Warden 反応
#   - 不具合を見つけたら gh issue を起票 (Step 4 の ADR-0027 候補)
#
# ADR 整合:
#   - ADR-0017: Step 2 で生まれる observation は 層 A (Warden 監視) と層 B
#     (Mind ジョブ) 両方。observe.py --trace は両者を時系列で並べる。
#   - ADR-0026 §7: --trace 経由で 4 Mind dogfooding の流れを後追い可能。
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RUNTIME_DIR="$(cd "${SCRIPT_DIR}/../.." && pwd)"
LIFECYCLE_DIR="${RUNTIME_DIR}/pillars/lifecycle"
INBOX_DIR="${RUNTIME_DIR}/pillars/inbox"
OBSERVATION_DIR="${RUNTIME_DIR}/pillars/observation"

# Step 2 specified 4 roles (Issue #124).
# generic kind + 4 persona + default guild + default workspace。
# workspace は git 不要 = developer-default にしない (= Step 3 で git worktree 化)。
declare -a MIND_NAMES=(alice bob gm-default carol)
declare -a MIND_PERSONAS=(designer implementer guildmaster reviewer)
KIND=generic
GUILD=default

# ----- Usage -----

usage() {
  cat <<USAGE
Phase 5f Step 2 dogfooding kick-off helper.

Subcommands:
  setup [--with-issue] [--start-loops]
        4 Mind (alice/bob/gm-default/carol) を spawn。
          --with-issue   : テスト用 Issue を 1 件 Inbox に投入
          --start-loops  : 4 Mind の mind-loop.sh を background で起動
  status
        4 Mind の登録状況、observe.py --realm、observe.py --trace --since 1h を出す。
  cleanup [--no-preserve]
        4 Mind を kill-mind.sh で消去。
          (default)        : 消去前に Mindspace を \$AI_ORG_OS_HOME/dogfooding-snapshots/
                             <timestamp>/<mind>/ にコピー (= notes/, state.md,
                             mind-loop.log, implementer 成果物 等を forensics 用に保存)
          --no-preserve    : preserve せず直接消す (高速、Issue #134 RCA でいう
                             "notes/ preservation" を skip)

Spawn される Mind:
  alice       persona=designer
  bob         persona=implementer
  gm-default  persona=guildmaster
  carol       persona=reviewer
USAGE
}

# ----- Subcommands -----

cmd_setup() {
  local with_issue=0
  local start_loops=0
  while [ "$#" -gt 0 ]; do
    case "$1" in
      --with-issue)  with_issue=1; shift ;;
      --start-loops) start_loops=1; shift ;;
      *) echo "[ERROR] unknown setup option: $1" >&2; usage >&2; exit 1 ;;
    esac
  done

  # 前提 check: host setup が走っていること (spawn-mind.sh が config.env を読む)。
  local runtime_home="${AI_ORG_OS_HOME:-${HOME}/.ai-org-os}"
  if [ ! -f "${runtime_home}/config.env" ]; then
    echo "[ERROR] host setup not done: ${runtime_home}/config.env not found" >&2
    echo "[HINT] Run host setup first: bash ${RUNTIME_DIR}/host/setup.sh" >&2
    exit 1
  fi

  # 既存 Mind との衝突を事前 check (failures が部分的に起きるのを防ぐ)。
  local conflict=0
  for i in "${!MIND_NAMES[@]}"; do
    local name="${MIND_NAMES[$i]}"
    local mindspace="${AI_ORG_OS_HOME:-${HOME}/.ai-org-os}/minds/${name}"
    if [ -d "${mindspace}" ]; then
      echo "[ERROR] Mind '${name}' already exists at ${mindspace}" >&2
      conflict=1
    fi
  done
  if [ "${conflict}" -eq 1 ]; then
    echo "[HINT] $0 cleanup でまとめて消すか、kill-mind.sh で個別に消してください" >&2
    exit 1
  fi

  echo "=== Phase 5f Step 2 dogfooding: spawning 4 Minds ==="
  for i in "${!MIND_NAMES[@]}"; do
    local name="${MIND_NAMES[$i]}"
    local persona="${MIND_PERSONAS[$i]}"
    echo
    echo "[spawn] ${name}  kind=${KIND}  persona=${persona}  guild=${GUILD}"
    "${LIFECYCLE_DIR}/spawn-mind.sh" \
      --guild "${GUILD}" \
      "${KIND}" "${persona}" "${name}"
  done

  if [ "${with_issue}" -eq 1 ]; then
    echo
    echo "=== submit test Issue ==="
    "${INBOX_DIR}/submit-issue.sh" \
      "Phase 5f Step 2 dogfooding test" \
      "本 Issue は Step 2 の dogfooding 検証用。 \
designer (alice) が設計案を出し、implementer (bob) が小さなコード片を書き、 \
reviewer (carol) が review し、guildmaster (gm-default) が全体を観察する \
フローが 1 周回ることを目的とする。実 PR は不要。"
  fi

  if [ "${start_loops}" -eq 1 ]; then
    echo
    echo "=== starting 4 mind-loops in background ==="
    for name in "${MIND_NAMES[@]}"; do
      echo "[loop] starting ${name}"
      nohup "${LIFECYCLE_DIR}/mind-loop.sh" "${name}" \
        >> "${HOME}/${name}-mind-loop.out" 2>&1 &
      echo "[loop] ${name} PID=$!  log=${HOME}/${name}-mind-loop.out"
    done
  fi

  cat <<NEXT

=== next steps ===

1) Conductor が走っていることを確認:
   cd ${RUNTIME_DIR}/realm && docker compose ps

2) Mind の状況を一覧:
   ./setup.sh status

3) cycle が進んだら時系列で流れを観察 (PR-E で merge した --trace):
   python ${OBSERVATION_DIR}/observe.py --trace --since 10m

4) 不具合を見つけたら gh issue 起票 (Issue #124 の Step 2 観察観点を参照):
   - 循環ループ / context drift / quota 枯渇 / その他

5) 終わったら掃除:
   ./setup.sh cleanup

NEXT
}

cmd_status() {
  echo "=== Mind registry ==="
  for name in "${MIND_NAMES[@]}"; do
    local entry="${AI_ORG_OS_HOME:-${HOME}/.ai-org-os}/registry/minds/${name}.md"
    if [ -f "${entry}" ]; then
      echo "  [+] ${name}  (registry entry exists)"
    else
      echo "  [-] ${name}  (not registered)"
    fi
  done
  echo
  echo "=== observe.py --realm ==="
  python "${OBSERVATION_DIR}/observe.py" --realm || true
  echo
  echo "=== observe.py --trace --since 1h ==="
  python "${OBSERVATION_DIR}/observe.py" --trace --since 1h || true
}

cmd_cleanup() {
  local preserve=1
  while [ "$#" -gt 0 ]; do
    case "$1" in
      --no-preserve) preserve=0; shift ;;
      --preserve)    preserve=1; shift ;;  # explicit (currently the default)
      *) echo "[ERROR] unknown cleanup option: $1" >&2; usage >&2; exit 1 ;;
    esac
  done

  local runtime_home="${AI_ORG_OS_HOME:-${HOME}/.ai-org-os}"
  local snapshot_dir=""
  if [ "${preserve}" -eq 1 ]; then
    # Issue #134 RCA top recommendation: cleanup 前に Mindspace を退避して
    # cycle 内行動 (notes/, state.md, mind-loop.log, implementer 成果物 等) を
    # forensics 用に保存する。snapshot は ${AI_ORG_OS_HOME}/dogfooding-snapshots/
    # 配下 — runtime state (ADR-0018) の subset。
    local ts
    ts="$(date -u +"%Y%m%dT%H%M%SZ")"
    snapshot_dir="${runtime_home}/dogfooding-snapshots/${ts}"
    mkdir -p "${snapshot_dir}" 2>/dev/null || {
      echo "[WARN] failed to mkdir ${snapshot_dir}, skipping preserve" >&2
      preserve=0
    }
  fi

  echo "=== cleaning up 4 Minds ==="
  if [ "${preserve}" -eq 1 ]; then
    echo "  preserve -> ${snapshot_dir}"
  fi
  for name in "${MIND_NAMES[@]}"; do
    echo
    local mindspace="${runtime_home}/minds/${name}"
    if [ "${preserve}" -eq 1 ] && [ -d "${mindspace}" ]; then
      # cp -r で Mindspace 全体を保存。.mind-loop.pid 等の runtime metadata も
      # 含めるが、disk は安いし forensic context として有用。失敗は WARN のみ
      # (= cleanup 本体は止めない、F3-like)。
      local mind_snapshot="${snapshot_dir}/${name}"
      if cp -r "${mindspace}" "${mind_snapshot}" 2>/dev/null; then
        echo "[preserve] ${name} -> ${mind_snapshot}"
      else
        echo "[preserve] WARN: copy ${name} -> ${mind_snapshot} failed" >&2
      fi
    fi
    echo "[kill] ${name}"
    # kill-mind.sh は非存在 Mind に対して exit 非 0 を返す可能性があるため
    # || true で continue。verbose に何が起きたかは kill-mind 側の出力に任せる。
    "${LIFECYCLE_DIR}/kill-mind.sh" "${name}" || true
  done
  echo
  echo "[done] cleanup completed (some skips are OK if a Mind was already gone)"
  if [ "${preserve}" -eq 1 ] && [ -n "${snapshot_dir}" ] && [ -d "${snapshot_dir}" ]; then
    echo "[preserve] snapshot dir: ${snapshot_dir}"
    echo "[preserve] inspect: ls ${snapshot_dir}"
  fi
}

# ----- main -----

if [ "$#" -lt 1 ]; then
  usage >&2
  exit 1
fi

subcmd="$1"
shift

case "${subcmd}" in
  setup)   cmd_setup "$@" ;;
  status)  cmd_status ;;
  cleanup) cmd_cleanup "$@" ;;
  -h|--help) usage ;;
  *) echo "[ERROR] unknown subcommand: ${subcmd}" >&2; usage >&2; exit 1 ;;
esac
