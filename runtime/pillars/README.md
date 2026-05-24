# runtime/pillars/

> 想定読者:
> - Warden の構成要素（Pillar）を読みに来た開発者
> - ai-org-os のコア領域と Mind 領域の境界を確認したい人
> - Phase 5 以降の Warden 実装を担当する人

**Pillar = Warden の内部 Claude / 内部機能の単位**（[ADR-0011](../../docs/adr/0011-warden-claude-naming-and-separation.md)）。

このディレクトリは **ai-org-os コアが提供する Warden 構成要素** の置き場です。
配下のファイルは **編集不可** として扱います（CODEOWNERS / pre-commit / CI で機械的に強制する予定。Phase 5a-2 時点では文書による宣言）。

## 配置（Phase 5b-1 時点）

```
runtime/pillars/
├── observation/   ← Realm 観測：mtime / メッセージ件数 / snapshot 履歴
├── lifecycle/     ← Mind の spawn / kill / list / 外側ループ
├── conduit/       ← Mind 間 Dispatch を仲介する MCP server (旧 Nexus)
├── judgment/      ← Warden 内部 Claude (Anthropic SDK 直叩き、決定論的)
├── registry/      ← Mind Kind カタログ列挙
├── inbox/         ← 人間 → Realm への入力経路
└── conductor/     ← Warden の心拍 (各 Pillar を周期で呼ぶ常駐エンジン)
```

各 Pillar の責務は ADR-0011 §3 「Pillar 一覧」を参照。

| Pillar | 責務 | 起票 Issue / 実装 PR |
|---|---|---|
| Observation | Realm 観測、snapshot 履歴 | Phase 5a-2 (#37) / Observation v0.1 (#42) |
| Lifecycle | Mind spawn / kill / list + 外側ループ | Phase 5a-2 (#37) / Mind loop (#41) |
| Conduit | Mind 間 Dispatch (MCP server) | Phase 5a-2 (#37) |
| Judgment | Anthropic SDK 直叩きの判断 | Phase 5a-3 (#38) |
| Registry | Kind カタログ列挙 | Phase 5a-4 (#39) |
| Inbox | 人間 → Realm 入力経路 | Phase 5a-5 (#40) |
| **Conductor** | **Warden の心拍 (周期実行 orchestrator)** | **Phase 5b-1 (#71)** |

## なぜ「編集不可」なのか

ai-org-os は **「開発組織の不変項を定義するフレームワーク」**。
Pillar は **その不変項を Realm 内で機械的に enforce する Warden の構成要素**であり、
個々の Realm 利用者が編集してよい領域ではない（編集してしまうと不変項が崩れる）。

利用者が編集してよいのは：

- `runtime/minds/<name>/` — 各 Mind の Mindspace（不可侵領域、所有者 Mind のみ）
- `runtime/kinds/`, `runtime/personas/` — 利用者が定義する Mind の種類と人格
- `runtime/realm/` — Realm を起動するための docker 定義（環境設定。**ただし境界に関わるため CODEOWNERS でレビュー必須**）

これらに対して、**Pillar はコアロジック**として位置づけられる。

## 編集が必要になったら

- バグ修正・機能追加: ai-org-os 本体の Issue / PR として提案する（Mind から直接書き換えない）
- 新しい Pillar の追加: ADR を起こしてから本ディレクトリに配置する
- 個別の Realm でカスタムしたい振る舞い: Persona / Kind / Mindspace の側で表現する

## 機械的な保護（Phase 5a-2 時点 → 将来）

保護は **発火タイミングが異なる 3 レイヤー** で構成する。各レイヤーは独立に効く / 独立に迂回されうるので、組み合わせて使うことが前提。

| レイヤー | 発火タイミング | 何を防ぐ | 状態 |
|---|---|---|---|
| **commit-time**: pre-commit hook（リポジトリ同梱、開発者ローカル） | `git commit` 実行時 | 不注意な local commit で pillars が変更されること | 未実装（Phase 5a-3 以降） |
| **merge-time**: CODEOWNERS + Branch protection（GitHub 側） | PR マージ時 | レビューなしで pillars が main に入ること | 本 PR で CODEOWNERS 導入。Branch protection は別途設定（下記注意点参照） |
| **runtime**: Judgment Pillar（Realm 内、実行時） | Realm 内 Mind が pillars/ に書き込みを試みた瞬間 | spawn された Mind 経由での pillars 書き換え（Axiom 違反） | 未実装（Phase 5a-3、#38） |

### Branch protection の運用上の注意点

CODEOWNERS は **「pillars を変更する PR には @yukiYamada のレビューが要る」** という意味になる。
ところが GitHub の仕様により **PR 作者は自分の PR をレビューできない**。
オーナー単独運用の段階では、Branch protection で `Require review from Code Owners` を ON にすると **オーナー自身が出した PR が永久に止まる**。

回避策（どれか必要）:

1. **Branch protection を効かせない** — CODEOWNERS は「変更時に Reviewer 候補を表示する」だけの諮問機能として運用（Phase 5a-2 時点の現実解）
2. **追加レビュアーハンドル** を CODEOWNERS に書く — 他者 / bot を追加して二者構成にする
3. **"Allow specified actors to bypass required pull requests" に @yukiYamada を入れる** — 自 PR は bypass、他者 PR は CODEOWNERS 必須、という運用

Phase 5a-2 時点では **方法 1（諮問機能として運用）** を採用し、Branch protection の有効化は別 Issue で検討する。

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
