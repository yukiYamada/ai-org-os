#!/usr/bin/env bash
#
# spawn-mind.sh — Mind を 1 個起動する最小スクリプト（Phase 1）
#
# 用法:
#   ./runtime/spawn-mind.sh <kind> <persona> <mind-name>
#
# 例:
#   ./runtime/spawn-mind.sh generic designer my-first-mind
#
# Phase 1 の仕様:
#   - Docker / Realm / Warden / Nexus はまだなし
#   - Mindspace = ホスト上のディレクトリ runtime/minds/<mind-name>/
#   - Persona の内容を CLAUDE.md として配置
#   - Claude CLI を起動する場所まで（実起動は人間が手で確認する）
#
# Phase 2 以降:
#   - Docker コンテナで起動
#   - Warden 経由で生成（3段階プロセス: 要求→承認→実行）
#   - リソース制限を enforce
#
set -euo pipefail

if [ "$#" -ne 3 ]; then
  echo "Usage: $0 <kind> <persona> <mind-name>" >&2
  echo "Example: $0 generic designer my-first-mind" >&2
  exit 1
fi

KIND="$1"
PERSONA="$2"
MIND_NAME="$3"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
KIND_FILE="${SCRIPT_DIR}/kinds/${KIND}.md"
PERSONA_FILE="${SCRIPT_DIR}/personas/${PERSONA}.md"
MIND_DIR="${SCRIPT_DIR}/minds/${MIND_NAME}"

if [ ! -f "${KIND_FILE}" ]; then
  echo "[ERROR] Kind '${KIND}' is not registered (looked for ${KIND_FILE})" >&2
  echo "[HINT] List available Kinds: ls ${SCRIPT_DIR}/kinds/" >&2
  exit 2
fi

if [ ! -f "${PERSONA_FILE}" ]; then
  echo "[ERROR] Persona '${PERSONA}' not found (looked for ${PERSONA_FILE})" >&2
  echo "[HINT] List available Personas: ls ${SCRIPT_DIR}/personas/" >&2
  exit 3
fi

if [ -d "${MIND_DIR}" ]; then
  echo "[ERROR] Mind '${MIND_NAME}' already exists at ${MIND_DIR}" >&2
  echo "[HINT] Choose another name or remove the existing one (= explicit destruction)" >&2
  exit 4
fi

echo "[spawn-mind] Creating Mindspace: ${MIND_DIR}"
mkdir -p "${MIND_DIR}"

echo "[spawn-mind] Installing Persona '${PERSONA}' as CLAUDE.md"
cp "${PERSONA_FILE}" "${MIND_DIR}/CLAUDE.md"

cat > "${MIND_DIR}/.mind-meta.md" <<EOF
---
mind_name: ${MIND_NAME}
kind: ${KIND}
persona: ${PERSONA}
spawned_at: $(date -u +"%Y-%m-%dT%H:%M:%SZ")
phase: 1
---

# Mind metadata

このファイルは Phase 1 の暫定的なメタデータです。
Phase 2 以降は Warden がより構造化された形で管理します。
EOF

echo "[spawn-mind] Mind '${MIND_NAME}' is ready at ${MIND_DIR}"
echo ""
echo "Next step (manual, Phase 1):"
echo "  cd ${MIND_DIR}"
echo "  claude   # or 'claude code' depending on your CLI"
echo ""
echo "The Mind's CLAUDE.md (=its Persona) will be loaded automatically."
