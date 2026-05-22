# runtime/

> 想定読者: ai-org-os を実際に動かす（Realm を起動する、Mind を生成する、Persona を編集する）人。

このディレクトリは **ai-org-os の動く実体** が住む場所。机上の ADR (`docs/adr/`) に対する**実装側**。

## 構造

```
runtime/
├── kinds/              ← Kind の定義（Mind の Body 性能）
│   └── generic.md      ← 当面唯一の Kind: Generic
├── personas/           ← Persona の定義（思考の癖）
│   ├── designer.md     ← 設計用
│   ├── implementer.md  ← 実装用
│   └── reviewer.md     ← レビュー用
├── minds/              ← 生成された Mind 実体（=Mindspace）
│   └── .gitkeep
├── tests/              ← 自前 shell テスト（依存ゼロ）
│   ├── run-tests.sh
│   ├── test-spawn-mind.sh
│   ├── test-kill-mind.sh
│   └── test-list-minds.sh
├── spawn-mind.sh       ← Mind を spawn する
├── kill-mind.sh        ← Mind を破棄する（Mindspace ごと消える）
└── list-minds.sh       ← spawn 中の Mind を一覧する
```

## 現在のフェーズ

**Phase 1（最小実装）**: Mind を1個動かすだけ。Docker / Realm / Warden / Nexus はまだなし。

- Mindspace = ホスト上のディレクトリ
- Mind の起動 = Claude（CLI）をそのディレクトリで起動
- Kind / Persona の選択 = `spawn-mind.sh` の引数

## 使い方

```bash
# Mind を spawn
./runtime/spawn-mind.sh generic designer my-first-mind

# 一覧
./runtime/list-minds.sh
# NAME              KIND       PERSONA      SPAWNED_AT
# my-first-mind     generic    designer     2026-05-22T11:09:51Z

# Persona 装着済みで起動（Phase 1 では手動）
cd runtime/minds/my-first-mind
claude

# 破棄（Mindspace ごと消える、不可逆）
./runtime/kill-mind.sh my-first-mind
```

## テスト

依存ゼロの自前 shell テスト：

```bash
./runtime/tests/run-tests.sh
```

各 `test-*.sh` を順に実行し、PASS/FAIL を表示する。1 つでも失敗があれば exit 1。
GitHub Actions でも `runtime/**` 変更時に自動実行される（`.github/workflows/runtime-tests.yml`）。

## 次のフェーズ予定

- Phase 2: Mindspace の永続化 + コンテナ化（Docker）
- Phase 3: 2 Mind + Dispatch（ファイル経由通信）
- Phase 4: Nexus 導入（MCP サーバー、Dispatch を MCP 経由に）
- Phase 5: Realm + Warden + Guildmaster の最小組み合わせ

詳細は [ADR-0002](../docs/adr/0002-vocabulary-and-meta-meta-structure.md) 参照。
