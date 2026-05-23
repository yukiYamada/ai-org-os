# Nexus

> 想定読者: Mind を spawn する人、Nexus の動作を確認するメンテナ、Phase 3 の実装を読む人。

**Nexus は ai-org-os の MCP server**。Mind 同士の Dispatch を仲介する「世界の経路」。
Mind は他 Mind の Mindspace を直接触らず、Nexus を通してメッセージを送受信する。

詳細な決定背景: [ADR-0005](../../../docs/adr/0005-phase-3-mcp-direct-with-nexus.md)

## 提供する tool

| tool | 役割 |
|---|---|
| `send_dispatch(from_mind, to_mind, topic, body)` | 送信。recipient の inbox に書く |
| `read_inbox(mind_name)` | 自分宛 inbox を一覧（未読のみ） |
| `ack_dispatch(mind_name, msg_id)` | 処理済みとして archive に移す |

## ストレージ（裏側、Mind からは見えない）

```
runtime/pillars/conduit/storage/
├── inbox/<recipient>/<msg-id>.md       未読
└── archive/<recipient>/<msg-id>.md     ack 済み
```

メッセージは Markdown + frontmatter（`from / to / topic / dispatched_at / msg_id`）+ 本文。

## 起動方法

### A. Mind 内の Claude から自動的に起動される（推奨、stdio）

`spawn-mind.sh` が Mind ごとに `.mcp.json` を配置するので、Mind 内で `claude` を起動すると Nexus が stdio 経由で自動接続される。

### B. 手動で動作確認（開発時のみ）

`runtime/pillars/conduit/start.sh` を使うと **venv に閉じ込めて起動**できる（ホスト Python 環境を汚さない）。

```bash
# 起動（venv 自動作成 + 依存インストール + stdio サーバー起動）
./runtime/pillars/conduit/start.sh

# 依存だけ準備して起動はしない
./runtime/pillars/conduit/start.sh --setup-only

# venv を作り直す（依存更新時など）
./runtime/pillars/conduit/start.sh --recreate-venv

# venv なしで直接（自己責任）
pip install -r runtime/pillars/conduit/requirements.txt
python runtime/pillars/conduit/nexus.py
```

stdio なので、MCP クライアント（Claude Code 等）からサブプロセスとして起動する想定。`start.sh` で起動した場合は別ターミナルから接続することになる。

## セキュリティ方針

- **依存最小**: `mcp` 1 つだけ。残りは標準ライブラリで完結（npm/pypi 系のサプライチェーン攻撃面積を最小化）
- **入力検証**: `mind_name` / `msg_id` は正規表現で制限（`[A-Za-z0-9._-]` のみ）。パス逸脱を防ぐ
- **副作用の局所化**: storage 配下にのみ書き込み
- **Identity binding** (Issue #19, [ADR-0008](../../../docs/adr/0008-nexus-identity-binding.md)):
  - `spawn-mind.sh` が `.mcp.json` に `AI_ORG_OS_MIND_NAME=<mind>` を注入
  - Nexus 起動時にこれを identity として保持
  - send / read / ack で `from_mind` / `mind_name` が identity と不一致なら `PermissionError`（MCP 応答は `{ok: false, code: "forbidden"}`）
  - 効果: ある Mind が他 Mind を**なりすませない**。Axiom（Mindspace 不可侵）が機械的に担保される

## 動作確認

```bash
./runtime/tests/run-tests.sh
```

`test-nexus-storage.sh`（直接関数テスト）と `test-dispatch-e2e.sh`（2 Mind 経由の往復テスト）が含まれる。

## Phase 3 のスコープと非スコープ

- スコープ: 上記 3 tool、ファイルベースストレージ、stdio transport、**identity binding（なりすまし防止）**
- 非スコープ（別 Phase / 別 ADR で扱う）:
  - ~~認可（誰がどの Mind を名乗れるか）~~ → **stdio 範囲は ADR-0008 で実装済**、HTTP transport 化時に再設計
  - Resources / Prompts（MCP の他 2 要素） — Phase 5 / Warden 責務（ADR-0006）
  - HTTP / SSE transport
  - 配送保証・順序保証・TTL・dead letter — [ADR-0007](../../../docs/adr/0007-phase-3-reliability-properties.md) で「現状妥協」確定
