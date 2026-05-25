#!/usr/bin/env bash
#
# submit-issue.sh — 人間が Realm に Issue を投入する shell ラッパー（Phase 5a-5 / Issue #40）
#
# 用法:
#   ./submit-issue.sh [--guild <name>] "<title>" "<body>" [priority] [submitter]
#
# 例:
#   ./submit-issue.sh "新しい機能の検討" "詳細な依頼内容..."
#   ./submit-issue.sh "障害対応" "ログ確認お願い" p1 alice
#   ./submit-issue.sh --guild backend "API 設計レビュー" "詳細..."
#
# 仕様:
#   - 内部で `python3 inbox.py submit` を呼び出す。
#   - title は 1-200 文字、改行不可。
#   - priority は p0/p1/p2/p3。未指定なら p2。
#   - submitter は [A-Za-z0-9._-]{1,64}。未指定なら human。
#   - guild は [A-Za-z0-9._-]{1,64}。未指定なら default (Phase 5c-1 / ADR-0019)。
#   - 投入された Issue は $AI_ORG_OS_HOME/issues/inbox/<issue_id>.md に書かれる
#     (Phase 5b-4 / ADR-0018、default $HOME/.ai-org-os/issues/inbox/)。
#   - 成功時、stdout に issue_id を出力する。
#
# ADR 整合:
#   - ADR-0012 §3 / ADR-0014 §3 D: 人間 → Warden への入力経路は Inbox Pillar 経由。
#   - ADR-0013 §1 F4: Realm 外部からの入力なので「人間制御チャンネル」。
#   - ADR-0019: 投入 Issue は所属 Guild を frontmatter に持つ。
#
set -euo pipefail

usage() {
  cat <<USAGE
Usage: $0 [--guild <name>] "<title>" "<body>" [priority] [submitter]

Examples:
  $0 "新しい機能の検討" "詳細な依頼内容..."
  $0 "障害対応" "ログ確認お願い" p1 alice
  $0 --guild backend "API 設計レビュー" "詳細..."

Priority:  p0 / p1 / p2 / p3 (default: p2)
Submitter: [A-Za-z0-9._-]{1,64} (default: human)
Guild:     [A-Za-z0-9._-]{1,64} (default: default, ADR-0019)
USAGE
}

# --guild を先に剥がす。--guild は positional の前後どこでも書けるようにする。
GUILD="default"
ARGS=()
while [ "$#" -gt 0 ]; do
  case "$1" in
    --guild)
      if [ "$#" -lt 2 ]; then
        echo "[ERROR] --guild requires a value" >&2
        usage >&2
        exit 1
      fi
      GUILD="$2"
      shift 2
      ;;
    --guild=*)
      GUILD="${1#--guild=}"
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      ARGS+=("$1")
      shift
      ;;
  esac
done

if [ "${#ARGS[@]}" -lt 2 ] || [ "${#ARGS[@]}" -gt 4 ]; then
  usage >&2
  exit 1
fi

TITLE="${ARGS[0]}"
BODY="${ARGS[1]}"
PRIORITY="${ARGS[2]:-p2}"
SUBMITTER="${ARGS[3]:-human}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INBOX_PY="${SCRIPT_DIR}/inbox.py"
RUNTIME_DIR="$(cd "${SCRIPT_DIR}/../.." && pwd)"
GUILD_PY="${RUNTIME_DIR}/pillars/registry/guild.py"

if [ ! -f "${INBOX_PY}" ]; then
  echo "[ERROR] inbox.py not found at ${INBOX_PY}" >&2
  exit 2
fi

PYTHON_BIN="${AI_ORG_OS_PYTHON:-python3}"
if ! command -v "${PYTHON_BIN}" >/dev/null 2>&1; then
  # python3 が無くても python があれば fallback。
  if command -v python >/dev/null 2>&1; then
    PYTHON_BIN="python"
  else
    echo "[ERROR] python command '${PYTHON_BIN}' not found in PATH." >&2
    echo "[HINT] Install Python 3.10+, or set AI_ORG_OS_PYTHON to your python path." >&2
    exit 3
  fi
fi

# Phase 5c-1 (#88 Codex P2): Guild manifest 存在チェック。
# spawn-mind / claim_issue は Guild の exact match を強制するので、
# 投入時に typo (--guild backned 等) が通ると「どの Mind にも claim できない
# 孤児 Issue」が inbox に溜まる。submit 側で Guild の parse 可能性を確認する。
# guild.py show は exit 3=GuildNotFound / exit 4=GuildValidationError を返す。
if [ -f "${GUILD_PY}" ]; then
  if ! "${PYTHON_BIN}" "${GUILD_PY}" show "${GUILD}" >/dev/null 2>&1; then
    echo "[ERROR] Guild '${GUILD}' does not exist or its manifest is malformed." >&2
    echo "[HINT] List available guilds: ${PYTHON_BIN} ${GUILD_PY} list" >&2
    echo "[HINT] Inspect manifest:      ${PYTHON_BIN} ${GUILD_PY} show ${GUILD}" >&2
    exit 4
  fi
else
  # guild.py が無いビルドでは Guild validation を skip。inbox.py 側の
  # 形式チェックには通す。本来 v0.1 では guild.py は必ず存在する想定 (warn のみ)。
  echo "[WARN] guild.py not found at ${GUILD_PY}; skipping Guild existence check." >&2
fi

# Issue 投入。inbox.py は成功時 stdout に issue_id を出力する。
"${PYTHON_BIN}" "${INBOX_PY}" submit \
  --priority "${PRIORITY}" \
  --submitter "${SUBMITTER}" \
  --guild "${GUILD}" \
  --body "${BODY}" \
  "${TITLE}"
