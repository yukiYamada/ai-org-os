# runtime/pillars/registry/

> 想定読者: Warden 実装者、Mind を spawn する Guildmaster、新しい Kind を定義するメンテナ。

ai-org-os の **Mind Kind Registry 最小実装**。Python 標準ライブラリのみ、依存ゼロ。

`runtime/kinds/*.md` を走査して Kind カタログを構築し、Warden（および将来の Guildmaster）が「どの Kind で Mind を spawn 可能か」を問い合わせる API を提供する。

設計の根拠は以下の ADR：

- [ADR-0002](../../../docs/adr/0002-vocabulary-and-meta-meta-structure.md) — Mind Kind Registry は Warden の責務、Realm の中
- [ADR-0010](../../../docs/adr/0010-observation-philosophy-and-warden-as-collective.md) — Warden は機能の集合体
- [ADR-0011](../../../docs/adr/0011-pillar-vs-extension-architecture.md) — Pillar は ai-org-os コア、編集不可領域
- [ADR-0015](../../../docs/adr/0015-persona-evolution-strategy.md) — 既存 Kind の選択は OK、Kind の動的生成は NG

## 構成

```
runtime/pillars/registry/
├── registry.py          ← list_kinds / get_kind / is_registered + CLI
├── test_registry.py     ← unittest（標準ライブラリ）
└── README.md
```

## 使い方

### CLI

```bash
# 一覧（表）
python3 runtime/pillars/registry/registry.py list

# 一覧（JSON, 機械向け）
python3 runtime/pillars/registry/registry.py list --json

# 詳細
python3 runtime/pillars/registry/registry.py get generic

# 登録チェック（exit 0 = 登録済み, exit 1 = 未登録）
python3 runtime/pillars/registry/registry.py check generic
```

出力例（`list`）:

```
=== Mind Kind Registry ===
  total: 1

NAME                 VERSION    STATUS         PATH
generic              0.1        experimental   /path/to/runtime/kinds/generic.md
```

### Python API

```python
from registry import list_kinds, get_kind, is_registered

# 全 Kind を列挙
for k in list_kinds():
    print(k.name, k.version, k.status)

# 特定 Kind の詳細
info = get_kind("generic")
if info is not None:
    print(info.path)

# Boolean check
if not is_registered("generic"):
    raise RuntimeError("generic kind missing!")
```

`KindInfo` は `@dataclass(frozen=True)` で `name / path / version / status` を持つ。

## spawn-mind.sh との整合

`runtime/pillars/lifecycle/spawn-mind.sh` は既に未登録 Kind を `exit 2` で拒否している（`runtime/kinds/<name>.md` の存在チェック）。Registry はこの判定を**同じファイル基盤**で行うので、両者の判定は一致する。

- spawn-mind.sh: `[ -f "${RUNTIME_DIR}/kinds/${KIND}.md" ]`
- Registry: `is_registered(name)` = `(runtime/kinds/<name>.md が存在) AND (frontmatter が読める)`

Registry の方が厳しい（frontmatter が壊れているファイルは未登録扱い）が、現状は generic.md が唯一の Kind でこれは正常なので差は出ない。

将来的に spawn-mind.sh が Registry を呼ぶ形に変える（Phase 5b 以降）と、判定ロジックを 1 か所に集約できる。

## 不可侵原則との関係

- Mindspace の中身に触れない（runtime/kinds/ のみを読む）
- Kind 定義ファイルは Pillar 領域の所有物（メタデータ）

## セキュリティ

`get_kind(name)` / `is_registered(name)` は名前のバリデーション (`^[A-Za-z0-9._-]{1,64}$`) で path traversal を弾く。spawn-mind.sh の `_VALID_NAME_RE` と同一パターン。

- `get_kind("../etc")` → None（攻撃の足がかりにしない）
- `get_kind("foo/bar")` → None
- `get_kind("a" * 65)` → None

## テスト

```bash
cd runtime/pillars/registry && python3 -m unittest discover -p 'test_*.py'

# または既存テストランナーで全部
./runtime/tests/run-tests.sh
```

## スコープ外（次フェーズ）

本 PR (Phase 5a-4) のスコープは **Warden が Kind を列挙できる** ことだけ。以下は Phase 5b 以降:

- spawn-mind.sh が Registry CLI を呼ぶ形への置き換え
- Kind の Body Spec を機械可読にする（現状は Markdown の表で人間向け）
- Registry の hot reload / watch
- 複数 Kind の追加（generic 以外）

## 関連

- [`../../kinds/generic.md`](../../kinds/generic.md) — 唯一の Kind 定義
- [`../lifecycle/spawn-mind.sh`](../lifecycle/spawn-mind.sh) — 未登録 Kind を `exit 2` で拒否する既存ロジック
- [`../observation/`](../observation/) — 観測 Pillar（同じ依存ゼロ設計）
