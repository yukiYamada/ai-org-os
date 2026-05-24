#!/usr/bin/env bash
#
# list-minds.sh — 現在 spawn されている Mind の一覧を表示する
#
# 用法:
#   ./runtime/pillars/lifecycle/list-minds.sh
#
# 出力フォーマット (table-ish):
#   NAME              KIND       PERSONA      SPAWNED_AT
#   my-first-mind     generic    designer     2026-05-22T11:09:51Z
#
# Phase 1 の仕様:
#   - ホスト上の runtime/minds/*/.mind-meta.md を読んで一覧化
#   - 0 件のときは「No minds spawned.」と表示して exit 0
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# Phase 5b-4 (#81 / ADR-0018): Mindspace は $AI_ORG_OS_HOME/minds/ 配下。
RUNTIME_DIR="$(cd "${SCRIPT_DIR}/../.." && pwd)"
DEFAULT_RUNTIME_HOME="${HOME:-${USERPROFILE:-}}/.ai-org-os"
RUNTIME_HOME="${AI_ORG_OS_HOME:-${DEFAULT_RUNTIME_HOME}}"
MINDS_DIR="${RUNTIME_HOME}/minds"

# .mind-meta.md を持つディレクトリだけを「正規の Mind」として扱う
mapfile -t mind_dirs < <(find "${MINDS_DIR}" -mindepth 1 -maxdepth 1 -type d 2>/dev/null | sort)

# .mind-meta.md がないディレクトリは無視（=spawn 経由じゃない手動作成ゴミ）
valid_minds=()
for d in "${mind_dirs[@]:-}"; do
  [ -z "${d}" ] && continue
  if [ -f "${d}/.mind-meta.md" ]; then
    valid_minds+=("${d}")
  fi
done

if [ "${#valid_minds[@]}" -eq 0 ]; then
  echo "No minds spawned."
  exit 0
fi

# 値抽出ヘルパ: meta の `key: value` 形式から value を取得
read_meta() {
  local file="$1"
  local key="$2"
  # frontmatter / 本文どちらにあっても拾えるよう grep 単純抽出
  grep -E "^${key}:" "${file}" | head -n 1 | sed -E "s/^${key}:[[:space:]]*//"
}

printf "%-20s %-12s %-14s %s\n" "NAME" "KIND" "PERSONA" "SPAWNED_AT"
for d in "${valid_minds[@]}"; do
  meta="${d}/.mind-meta.md"
  name="$(basename "${d}")"
  kind="$(read_meta "${meta}" "kind")"
  persona="$(read_meta "${meta}" "persona")"
  spawned="$(read_meta "${meta}" "spawned_at")"
  printf "%-20s %-12s %-14s %s\n" "${name}" "${kind:-?}" "${persona:-?}" "${spawned:-?}"
done
