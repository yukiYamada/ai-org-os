#!/usr/bin/env bash
#
# submit-issue.sh — 人間が Realm に Issue を投入する shell ラッパー（Phase 5a-5 / Issue #40）
#
# 用法:
#   ./submit-issue.sh "<title>" "<body>" [priority] [submitter]
#
# 例:
#   ./submit-issue.sh "新しい機能の検討" "詳細な依頼内容..."
#   ./submit-issue.sh "障害対応" "ログ確認お願い" p1 alice
#
# 仕様:
#   - 内部で `python3 inbox.py submit` を呼び出す。
#   - title は 1-200 文字、改行不可。
#   - priority は p0/p1/p2/p3。未指定なら p2。
#   - submitter は [A-Za-z0-9._-]{1,64}。未指定なら human。
#   - 投入された Issue は runtime/issues/inbox/<issue_id>.md に書かれる。
#   - 成功時、stdout に issue_id を出力する。
#
# ADR 整合:
#   - ADR-0012 §3 / ADR-0014 §3 D: 人間 → Warden への入力経路は Inbox Pillar 経由。
#   - ADR-0013 §1 F4: Realm 外部からの入力なので「人間制御チャンネル」。
#
set -euo pipefail

usage() {
  cat <<USAGE
Usage: $0 "<title>" "<body>" [priority] [submitter]

Examples:
  $0 "新しい機能の検討" "詳細な依頼内容..."
  $0 "障害対応" "ログ確認お願い" p1 alice

Priority: p0 / p1 / p2 / p3 (default: p2)
Submitter: [A-Za-z0-9._-]{1,64} (default: human)
USAGE
}

if [ "$#" -lt 2 ] || [ "$#" -gt 4 ]; then
  usage >&2
  exit 1
fi

case "$1" in
  -h|--help)
    usage
    exit 0
    ;;
esac

TITLE="$1"
BODY="$2"
PRIORITY="${3:-p2}"
SUBMITTER="${4:-human}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INBOX_PY="${SCRIPT_DIR}/inbox.py"

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

# Issue 投入。inbox.py は成功時 stdout に issue_id を出力する。
"${PYTHON_BIN}" "${INBOX_PY}" submit \
  --priority "${PRIORITY}" \
  --submitter "${SUBMITTER}" \
  --body "${BODY}" \
  "${TITLE}"
