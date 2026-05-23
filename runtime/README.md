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
├── pillars/                 ← Warden コア (ADR-0011)、編集不可領域
│   ├── README.md            ← Pillar 全体の説明と編集ポリシー
│   ├── observation/         ← Observation Pillar（Realm 観測）
│   │   ├── observe.py
│   │   ├── mind_status.py
│   │   ├── test_mind_status.py
│   │   ├── ROADMAP.md
│   │   └── README.md
│   ├── lifecycle/           ← Lifecycle Pillar（Mind の spawn / kill / list）
│   │   ├── spawn-mind.sh
│   │   ├── kill-mind.sh
│   │   └── list-minds.sh
│   └── conduit/             ← Conduit Pillar（Phase 3 旧 Nexus、MCP server）
│       ├── nexus.py         ← MCP wiring（mcp 依存）
│       ├── storage.py       ← Dispatch ストレージ層（標準ライブラリのみ）
│       ├── test_storage.py  ← storage の unittest
│       ├── storage/         ← メッセージ実体（.gitignore）
│       │   ├── inbox/
│       │   └── archive/
│       ├── requirements.txt ← mcp パッケージ 1 つだけ
│       ├── start.sh         ← venv 内での動作確認用
│       └── README.md
├── realm/                   ← Phase 5a-1 Realm コンテナ起動定義
├── tests/                   ← 自前 shell テスト（依存ゼロ）
│   ├── run-tests.sh
│   ├── test-spawn-mind.sh
│   ├── test-kill-mind.sh
│   ├── test-list-minds.sh
│   ├── test-nexus-unit.sh   ← Python unittest を呼ぶラッパー
│   └── test-dispatch-e2e.sh ← send → ack → archive の E2E
└── verification/            ← Phase 3 dogfooding 等
```

## 現在のフェーズ

**Phase 1 + Phase 3 統合**: Mind 単体 spawn + Mind 同士の Dispatch（Nexus 経由）が動く。Docker / Realm / Warden / Guild はまだなし。

- Mindspace = ホスト上のディレクトリ
- Mind の起動 = Claude（CLI）をそのディレクトリで起動、`.mcp.json` で Nexus へ自動接続
- Kind / Persona の選択 = `spawn-mind.sh` の引数
- Dispatch = `send_dispatch` / `read_inbox` / `ack_dispatch` の3 MCP tool（[Conduit Pillar](./pillars/conduit/README.md)）

## 使い方

```bash
# Mind を spawn（Nexus 接続設定が自動配置される）
./runtime/pillars/lifecycle/spawn-mind.sh generic designer my-first-mind
./runtime/pillars/lifecycle/spawn-mind.sh generic reviewer reviewer-1

# 一覧
./runtime/pillars/lifecycle/list-minds.sh

# Mind を起動（CLAUDE.md = Persona と .mcp.json = Nexus 接続が自動読み込み）
cd runtime/minds/my-first-mind
claude
# Mind の中で Claude が send_dispatch / read_inbox / ack_dispatch を呼べる

# 破棄（Mindspace ごと消える、不可逆）
./runtime/pillars/lifecycle/kill-mind.sh my-first-mind
```

Nexus（Conduit Pillar）を手で動作確認したい場合は [`pillars/conduit/README.md`](./pillars/conduit/README.md) を参照。

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
