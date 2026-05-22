#!/usr/bin/env bash
#
# spawn-mind.sh — Mind を 1 個起動する最小スクリプト（Phase 1 + Phase 3）
#
# 用法:
#   ./runtime/spawn-mind.sh <kind> <persona> <mind-name>
#
# 例:
#   ./runtime/spawn-mind.sh generic designer my-first-mind
#
# 仕様:
#   - Mindspace = ホスト上のディレクトリ runtime/minds/<mind-name>/
#   - Persona の内容を CLAUDE.md として配置
#   - Nexus（MCP server）への接続設定 .mcp.json を Mindspace に配置（Phase 3 で追加）
#   - その後 cd して claude を起動すれば、Nexus 経由で他 Mind と Dispatch できる
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

# Phase 3: Nexus 接続のための python の存在を事前検証する。
# 検証せずに .mcp.json を書くと、Mind 起動時 (claude 実行時) に MCP 接続が失敗して
# 「spawn は成功したのに Nexus が使えない」という壊れた Mind が生まれる。
PYTHON_BIN="${AI_ORG_OS_PYTHON:-python3}"
if ! command -v "${PYTHON_BIN}" >/dev/null 2>&1; then
  echo "[ERROR] python command '${PYTHON_BIN}' not found in PATH." >&2
  echo "[HINT] Install Python 3.10+, or set AI_ORG_OS_PYTHON to your python path." >&2
  echo "[HINT] Without python, the spawned Mind cannot start the Nexus MCP server." >&2
  exit 5
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
phase: 1+3
---

# Mind metadata

このファイルは暫定的なメタデータです。
Phase 5 以降は Warden がより構造化された形で管理します。
EOF

# Phase 3: Nexus (MCP server) への接続設定を Mindspace に配置
# Claude Code は .mcp.json を読んで MCP サーバーに接続する（stdio）
# PYTHON_BIN は上方で存在検証済み。
#
# AI_ORG_OS_MIND_NAME env var binds the Nexus stdio subprocess to this Mind's
# identity (Issue #19, ADR-0008). The Nexus then rejects send_dispatch /
# read_inbox / ack_dispatch calls whose from_mind / mind_name does not match
# this binding, preventing one Mind from impersonating another via crafted
# arguments.
NEXUS_PY="${SCRIPT_DIR}/nexus/nexus.py"
echo "[spawn-mind] Installing Nexus MCP config (.mcp.json) using '${PYTHON_BIN}', bound to '${MIND_NAME}'"
cat > "${MIND_DIR}/.mcp.json" <<JSON
{
  "mcpServers": {
    "nexus": {
      "type": "stdio",
      "command": "${PYTHON_BIN}",
      "args": ["${NEXUS_PY}"],
      "env": {
        "AI_ORG_OS_MIND_NAME": "${MIND_NAME}"
      }
    }
  }
}
JSON

echo "[spawn-mind] Mind '${MIND_NAME}' is ready at ${MIND_DIR}"
echo ""
echo "Next step (manual):"
echo "  cd ${MIND_DIR}"
echo "  claude   # CLAUDE.md (Persona) と .mcp.json (Nexus 接続) が自動的に読まれます"
echo ""
echo "Nexus が提供する tool:"
echo "  - send_dispatch / read_inbox / ack_dispatch"
echo "  Mind は他 Mind の Mindspace を直接触れません。すべての通信は Nexus 経由です（Axiom）。"
