# runtime/pillars/

> 想定読者:
> - Warden の構成要素（Pillar）を読みに来た開発者
> - ai-org-os のコア領域と Mind 領域の境界を確認したい人
> - Phase 5 以降の Warden 実装を担当する人

**Pillar = Warden の内部 Claude / 内部機能の単位**（[ADR-0011](../../docs/adr/0011-warden-claude-naming-and-separation.md)）。

このディレクトリは **ai-org-os コアが提供する Warden 構成要素** の置き場です。
配下のファイルは **編集不可** として扱います（CODEOWNERS / pre-commit / CI で機械的に強制する予定。Phase 5a-2 時点では文書による宣言）。

## 配置（Phase 5a-2 時点）

```
runtime/pillars/
├── observation/   ← Observation Pillar（Realm 観測：mtime / メッセージ件数 / kind / persona）
├── lifecycle/     ← Lifecycle Pillar（Mind の spawn / kill / list）
└── conduit/       ← Conduit Pillar（Mind 間 Dispatch を仲介する MCP server＝旧 Nexus）
```

各 Pillar の責務は ADR-0011 §3 「Pillar 一覧」を参照。

将来追加される Pillar（Phase 5a-3 以降）:

| Pillar | 責務 | 関連 Issue |
|---|---|---|
| Judgment | Warden 内部 Claude（Anthropic SDK 直叩き）。Realm 全体の判断を担当 | #38 |
| Registry | Mind Kind / Persona のレジストリを Warden に統合 | #39 |
| Inbox | Realm 外部からの Issue / Dispatch 投入インターフェース | #40 |

## なぜ「編集不可」なのか

ai-org-os は **「開発組織の不変項を定義するフレームワーク」**。
Pillar は **その不変項を Realm 内で機械的に enforce する Warden の構成要素**であり、
個々の Realm 利用者が編集してよい領域ではない（編集してしまうと不変項が崩れる）。

利用者が編集してよいのは：

- `runtime/minds/<name>/` — 各 Mind の Mindspace（不可侵領域、所有者 Mind のみ）
- `runtime/kinds/`, `runtime/personas/` — 利用者が定義する Mind の種類と人格
- `runtime/realm/` — Realm を起動するための docker 定義（環境設定）

これらに対して、**Pillar はコアロジック**として位置づけられる。

## 編集が必要になったら

- バグ修正・機能追加: ai-org-os 本体の Issue / PR として提案する（Mind から直接書き換えない）
- 新しい Pillar の追加: ADR を起こしてから本ディレクトリに配置する
- 個別の Realm でカスタムしたい振る舞い: Persona / Kind / Mindspace の側で表現する

## 機械的な保護（Phase 5a-2 時点 → 将来）

| 保護機構 | 状態 | メモ |
|---|---|---|
| CODEOWNERS で `runtime/pillars/*` をリポジトリオーナー必須レビューに | 本 PR で導入 | GitHub 側設定 (Branch protection) と組み合わせて実効化 |
| pre-commit hook で「Mind から Pillar への書き込み」を検知 | 未実装 | Phase 5a-3 以降の Judgment Pillar が判定 |
| CI で `runtime/pillars/` の変更を別経路に分岐 | 未実装 | 単体テスト必須化など |

## テスト

各 Pillar のテストは `runtime/tests/test-<pillar>-*.sh` に配置されています：

- `runtime/tests/test-spawn-mind.sh`, `test-kill-mind.sh`, `test-list-minds.sh` — Lifecycle Pillar
- `runtime/tests/test-observatory-unit.sh` — Observation Pillar
- `runtime/tests/test-nexus-unit.sh`, `test-nexus-start.sh`, `test-dispatch-e2e.sh` — Conduit Pillar
- `runtime/tests/test-realm.sh` — Realm コンテナ内での Pillar 統合（opt-in、`RUN_REALM_TESTS=1`）

一括実行：

```bash
./runtime/tests/run-tests.sh
```

## 関連

- [ADR-0010](../../docs/adr/0010-observation-philosophy-and-warden-as-collective.md) — Warden は機能の集合体（Pillar が「機能」の単位）
- [ADR-0011](../../docs/adr/0011-warden-claude-naming-and-separation.md) — Pillar 命名 / 編集不可 / Mind との境界
- [ADR-0006](../../docs/adr/0006-phase-5-realm-warden-guildmaster.md) — Phase 5 全体像
