# ADR-0011: Warden 内 Claude の命名と分離（コア vs 拡張の境界）

> 想定読者: Phase 5 を実装するメンテナ、Warden / Mind の境界を理解したい人、Realm 内の編集権限ルールを設計する人。

## Status

**Accepted** — 2026-05-23

## Context（背景）

ADR-0010 で「**Warden 内 Claude は Mind とは別カテゴリ、ai-org-os core が提供して誰も編集できない**」と確定した。
ただし命名と分離の具体は ADR-0010 では扱わず先送りされ、Issue #36 で本 ADR として切り出された。

Phase 5a 着手（Issue #35）で「Warden 機能を実装する Claude」をファイルとして配置する必要があり、それまでに命名と配置を決めておく必要がある。

### 整理済みの前提（再掲）

| カテゴリ | 提供 / 編集 | 所属 |
|---|---|---|
| **Mind** | ユーザー（Guildmaster / 人間）が定義・編集 | Guild |
| **新カテゴリ**（Warden 系） | ai-org-os 自体が提供、**誰も編集できない** | Warden |

これは「**コア vs 拡張**」の境界線。

### 議論の到達点（2026-05-23 壁打ち）

- ユーザーの主張: 「機能に名前つけたいのね？」=命名は二次的、本質は**編集権限の境界**
- ただし実装には名前が必要 → 本 ADR で確定

## Decision（決定）

### 1. 命名: **Pillar**（採用）

**Warden の構成要素としての Claude セッション（および周辺機能）を `Pillar` と呼ぶ**。

| 採用候補 | 不採用候補と理由 |
|---|---|
| ✅ **Pillar** （世界を支える柱） | |
| | ❌ `Spirit`（宗教感が強い） |
| | ❌ `Guardian`（Warden と語感が被る） |
| | ❌ `Daemon`（OS 用語、ai-org-os の仮想空間メタファーから外れる） |
| | ❌ `Servitor`（ダーク感、ai-org-os は明るい比喩で統一） |
| | ❌ `Mechanism`（技術寄りすぎ、思考主体としての性質が見えない） |

**Pillar を選んだ理由**：

1. **仮想空間メタファー継続**（Realm / Guild / Mind / Mindspace に揃う）
2. **集合体の構成要素として自然**（複数の Pillar が Warden という建物を支える）
3. **思考主体としての性質を保ちつつ Mind と区別**（柱は人ではないが、世界の構造要素）
4. **「Pillar of Warden」「Observation Pillar」「Lifecycle Pillar」等、複合名詞が作りやすい**

### 2. Pillar の例（Phase 5 着手時の暫定カタログ）

これらは ai-org-os core が提供する Pillar 群（編集不可）：

| Pillar 名 | 担う機能 | 既存実装 |
|---|---|---|
| **Observation Pillar** | Realm 内の活動観測（メタ情報、mtime、メッセージ件数） | `runtime/observatory/observe.py` |
| **Lifecycle Pillar** | Mind の spawn / kill / list | `runtime/spawn-mind.sh` / `kill-mind.sh` / `list-minds.sh` |
| **Conduit Pillar** | Mind 間の Dispatch 仲介（MCP server） | `runtime/nexus/` |
| **Judgment Pillar** | Warden の判断機能（Axiom 違反検出 / 3 段階プロセス承認） | 未実装（Phase 5a-3 で着手） |
| **Registry Pillar** | Mind Kind カタログ管理 | 未実装（Phase 5a-4 で着手） |
| **Inbox Pillar** | 人間からの Issue 投入受付 | 未実装（Phase 5a-5 で着手） |

これらの名前は本 ADR で確定したものではなく **Phase 5a 着手時に確定**する。本 ADR では「Pillar というカテゴリ語」と「編集不可の境界」を確定する。

### 3. ファイル配置の境界

**コア vs 拡張の境界をファイル配置で明示**する：

```
runtime/
├── kinds/                  ← ユーザー定義（Mind 用、編集可）
│   └── generic.md
├── personas/               ← ユーザー定義（Mind 用、編集可）
│   ├── designer.md
│   ├── implementer.md
│   └── reviewer.md
├── minds/                  ← ユーザー生成（Mind の Mindspace、編集可）
│   └── ...
│
├── pillars/                ← ai-org-os core 提供（編集不可、新規）
│   ├── observation/        ← Observation Pillar の実体
│   ├── lifecycle/          ← Lifecycle Pillar の実体
│   ├── conduit/            ← Conduit Pillar の実体（既存 nexus を移動 or 参照）
│   ├── judgment/           ← Judgment Pillar の実体（Phase 5a-3）
│   ├── registry/           ← Registry Pillar の実体（Phase 5a-4）
│   └── inbox/              ← Inbox Pillar の実体（Phase 5a-5）
│
├── observatory/            ← 暫定実装（Phase 5a-2 で pillars/observation/ に統合）
├── nexus/                  ← 暫定実装（Phase 5a-2 で pillars/conduit/ に統合）
├── spawn-mind.sh           ← 暫定実装（Phase 5a-2 で pillars/lifecycle/ に統合）
├── kill-mind.sh
└── list-minds.sh
```

### 4. 編集不可の機械的担保

**人間の運用ルールだけでなく、機械的に編集を防ぐ**：

| 機構 | 方法 | 対象 |
|---|---|---|
| **CODEOWNERS** | `runtime/pillars/` のオーナーを `@ai-org-os-core-team`（仮）または明示なし（=管理者のみマージ可） | リポジトリ全体 |
| **pre-commit hook** | `runtime/pillars/` 配下への変更を検知して警告 | ローカル |
| **CI チェック** | PR で `runtime/pillars/` 配下が変更されてたら fail（許可ラベル付き PR のみ通す） | リモート |
| **README 明記** | `runtime/pillars/README.md` で「編集不可」を冒頭に明示 | 人間向け |

**Phase 5a-2（既存ツール統合）で上記機構を順次実装**。本 ADR では境界の宣言までを扱う。

### 5. 例外: Pillar の更新が必要な場合

ai-org-os 本体のアップデートで Pillar 自体を更新する必要が出た場合：

- **方法 1（推奨）**: ai-org-os の新バージョンを取り込む形（git pull / submodule update 等）。ユーザーが個別に編集するのではなく「ライブラリのバージョンアップ」として扱う
- **方法 2**: どうしても緊急で Pillar を編集したい場合は、許可ラベル `core-edit-approved` を付けた PR でのみ通す。レビュー必須

これにより「**Pillar は固定、しかし陳腐化しない**」状態を作る。

## Consequences（影響）

### ポジティブ
- Phase 5a 着手時に「Warden 機能の Claude を何と呼ぶか / どこに置くか」が明確
- コア vs 拡張の境界が機械的に守られる
- ユーザーが「自分のもの（Mind / Persona）」と「触ってはいけないもの（Pillar）」を直感的に区別できる
- 仮想空間メタファー（Realm / Pillar / Guild / Mind）が揃って語感が一貫

### ネガティブ
- `runtime/` 配下のディレクトリ構造が変わる（既存ツールの移動が必要、Phase 5a-2 のスコープ）
- Pillar の編集不可機構の実装コスト（CODEOWNERS / pre-commit / CI）
- 既存 PR や docs の参照パス更新が必要

### リスク
- 「Pillar」という名前が他プロジェクト（IT 系）で別の意味で使われてる可能性 → 衝突調査
  - 緩和: 本プロダクト内で一貫して使えば実用上問題ない
- 編集不可を機械的に強制しても、git の性質上「fork して書き換える」は防げない
  - 緩和: ai-org-os の運用としては OK（fork は自己責任、本家は守る）

## 関連

- [ADR-0002](./0002-vocabulary-and-meta-meta-structure.md) — 用語と階層構造（Realm / Warden / Mind / Mindspace）
- [ADR-0006](./0006-phase-5-realm-warden-guildmaster.md) — Phase 5 設計
- [ADR-0010](./0010-observation-philosophy-and-warden-as-collective.md) — Warden は機能の集合体（本 ADR の起点）
- Issue #35 — Phase 5a-1 Realm コンテナ起動（本 ADR の名前を使う）
- Issue #37 — Phase 5a-2 既存ツール統合（本 ADR の配置を実装）
- Issue #36 — 本 ADR で close
