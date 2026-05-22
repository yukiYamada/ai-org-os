# runtime/

> 想定読者: ai-org-os を実際に動かす（Realm を起動する、Mind を生成する、Persona を編集する）人。

このディレクトリは **ai-org-os の動く実体** が住む場所。机上の ADR (`docs/adr/`) に対する**実装側**。

## 構造

```
runtime/
├── kinds/                   ← Kind の定義（Mind の Body 性能）
│   └── generic.md           ← 当面唯一の Kind: Generic
├── personas/                ← Persona の定義（思考の癖）
│   ├── designer.md          ← 設計用
│   ├── implementer.md       ← 実装用
│   └── reviewer.md          ← レビュー用
├── minds/                   ← 生成された Mind 実体（=Mindspace）
│   └── .gitkeep
├── nexus/                   ← Phase 3: MCP server（思考間通信の経路）
│   ├── nexus.py             ← MCP wiring（mcp 依存）
│   ├── storage.py           ← Dispatch ストレージ層（標準ライブラリのみ）
│   ├── test_storage.py      ← storage の unittest（13 テスト）
│   ├── storage/             ← メッセージ実体（.gitignore）
│   │   ├── inbox/
│   │   └── archive/
│   ├── requirements.txt     ← mcp パッケージ 1 つだけ
│   └── README.md
├── tests/                   ← 自前 shell テスト（依存ゼロ）
│   ├── run-tests.sh
│   ├── test-spawn-mind.sh
│   ├── test-kill-mind.sh
│   ├── test-list-minds.sh
│   ├── test-nexus-unit.sh   ← Python unittest を呼ぶラッパー
│   └── test-dispatch-e2e.sh ← send → ack → archive の E2E
├── spawn-mind.sh            ← Mind spawn + .mcp.json 配置（Nexus 接続）
├── kill-mind.sh             ← Mind 破棄（Mindspace ごと消える）
└── list-minds.sh            ← spawn 中の Mind 一覧
```

## 現在のフェーズ

**Phase 1 + Phase 3 統合**: Mind 単体 spawn + Mind 同士の Dispatch（Nexus 経由）が動く。Docker / Realm / Warden / Guild はまだなし。

- Mindspace = ホスト上のディレクトリ
- Mind の起動 = Claude（CLI）をそのディレクトリで起動、`.mcp.json` で Nexus へ自動接続
- Kind / Persona の選択 = `spawn-mind.sh` の引数
- Dispatch = `send_dispatch` / `read_inbox` / `ack_dispatch` の3 MCP tool（[Nexus](./nexus/README.md)）

## 使い方

```bash
# Mind を spawn（Nexus 接続設定が自動配置される）
./runtime/spawn-mind.sh generic designer my-first-mind
./runtime/spawn-mind.sh generic reviewer reviewer-1

# 一覧
./runtime/list-minds.sh

# Mind を起動（CLAUDE.md = Persona と .mcp.json = Nexus 接続が自動読み込み）
cd runtime/minds/my-first-mind
claude
# Mind の中で Claude が send_dispatch / read_inbox / ack_dispatch を呼べる

# 破棄（Mindspace ごと消える、不可逆）
./runtime/kill-mind.sh my-first-mind
```

Nexus を手で動作確認したい場合は [`nexus/README.md`](./nexus/README.md) を参照。

## テスト

依存ゼロ（Python 標準ライブラリのみ）の自前テスト：

```bash
./runtime/tests/run-tests.sh
```

各 `test-*.sh` を順に実行し、PASS/FAIL を表示する。1 つでも失敗があれば exit 1。
GitHub Actions でも `runtime/**` 変更時に自動実行される（`.github/workflows/runtime-tests.yml`）。

現状: **5 ファイル / 41 アサーション全 PASS**（spawn / kill / list / nexus-unit / dispatch-e2e）。

## 次のフェーズ予定

- **Phase 2**: Mindspace の永続化 + コンテナ化（Docker）— [ADR-0003](../docs/adr/0003-docker-and-phase-2-design.md)
- ~~Phase 3: ファイル経由通信~~ → Phase 3 = MCP 直行に変更（[ADR-0005](../docs/adr/0005-phase-3-mcp-direct-with-nexus.md)）
- ~~Phase 4: Nexus 導入~~ → Phase 3 に統合済み（本ブランチで実装）
- **Phase 5**: Realm + Warden + Guildmaster の最小組み合わせ

詳細:
- [ADR-0002](../docs/adr/0002-vocabulary-and-meta-meta-structure.md) — 用語と構造
- [ADR-0005](../docs/adr/0005-phase-3-mcp-direct-with-nexus.md) — Phase 3 = MCP 直行（本実装の根拠）
