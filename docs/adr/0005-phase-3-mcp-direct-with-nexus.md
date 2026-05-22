# ADR-0005: Phase 3 = Nexus（MCP サーバー）直行、ファイル経由 + poll はスキップ

> 想定読者: Phase 3 を実装するメンテナ（Python で Nexus を立て、Mind 側 MCP クライアント接続を整備する担当）、および Phase 3 以降の意思決定者。

## Status

**Accepted** — 2026-05-22

## Context（背景）

### これまでの位置

- [ADR-0001](./0001-ai-org-os-as-invariant-framework.md): ai-org-os は「開発組織の不変項（Axiom）を定義するフレームワーク」。組織 = 思考のネットワーク。
- [ADR-0002](./0002-vocabulary-and-meta-meta-structure.md): 用語と階層構造を確定。**Realm / Warden / Nexus / Guild / Guildmaster / Mind / Mindspace / Axiom / Dispatch**。Nexus は MCP サーバーとして実装し、Warden とプロセス分離する、と明文化されている。
- [ADR-0003](./0003-docker-and-phase-2-design.md): Phase 2（Docker 化）の設計案。**Proposed**。
- [ADR-0004](./0004-dispatch-and-phase-3-design.md): Phase 3（Dispatch）の設計案。**Proposed**。推奨は「ファイル経由 + 能動 poll + 共通 `runtime/dispatches/` ディレクトリ」。Nexus（MCP）は Phase 4 に分離する設計。

### 何が変わったか

ADR-0004 の Proposed 状態に対し、プロダクトオーナーとの追加壁打ち（2026-05-22 同日）で **方針が更新された**。要点はひとつ:

> **「Mind から他 Mind に繋ぐには、世界（Nexus）を仲介しないとおかしい。」**

ADR-0002 で「組織 = 思考のネットワーク」「Nexus = 思考間通信と外部 I/F を担う結節点」と定義した時点で、Mind が直接共有ファイルを覗きにいく構造は **Axiom と整合的に見えても、世界観の言語と整合的でない**。共有ファイル経由は「ホワイトボードに張り紙」モデルだが、ADR-0002 が定義したのは「Nexus（世界の結節点）が郵便配達する」モデルである。

ADR-0004 はそれでも「Phase 3 = ファイル + poll」を推奨していた。理由は依存ゼロ・実装最小・痕跡自動だった。だが壁打ちの帰結として:

1. ファイル + poll を一度作っても、Phase 4 で MCP に乗せ換える時には Mind 側の通信レイヤを書き換える必要がある（インターフェースは似ていても、実装の置き換えコストはゼロではない）。
2. 「素朴な実装で手応えを得る」価値より、「世界の構造を正しく実装に映す」価値の方が、本プロジェクトの本質（不変項フレームワーク）と整合する。
3. プロダクトオーナーの直観 = 「世界を仲介しないとおかしい」が、ADR-0002 の世界観と完全に整合する。

よって **Phase 3 と Phase 4 を統合し、Phase 3 で Nexus（MCP サーバー）を実装する**。

### 言語選定の追加論点

実装言語は **Python** を採用する。背景は次の通り:

1. **npm エコシステムの脆弱性インシデント増加**: 近年の supply chain 攻撃（typosquatting、悪意ある依存の混入、postinstall 経由のクレデンシャル流出）が継続的に観察されている。Nexus は「世界の結節点」であり、Mind 間の通信すべてが通過する。ここを侵されると組織全体が侵される。
2. **最小依存で組めること**: Python は標準ライブラリで HTTP / JSON / ファイル I/O / プロセス管理が完結する。MCP の Python SDK（公式）も存在する。最小依存で組めば、攻撃面が小さく保てる。
3. **ai-org-os 内部の他言語との衝突がない**: 現状 `runtime/` 配下は bash スクリプトのみ。Python 導入で他言語との競合は起きない。
4. **Docker 化（Phase 2）との親和性**: Python の公式イメージは枯れていて軽量。Phase 2 でコンテナ化される時にスムーズに乗る。

Node.js / TypeScript も MCP の主要実装言語だが、上記 1 を理由に外す。Go も候補だったが、依存の少なさは Python と同等で、社内（プロダクトオーナー）の保守容易性で Python に倒す。

---

## Decision（決定）

### 1. Phase 3 と Phase 4 を統合する

ADR-0004 / ADR-0002 で別フェーズだった「ファイル経由 Dispatch（Phase 3）」と「Nexus = MCP サーバー（Phase 4）」を **1 つのフェーズに統合**する。フェーズ番号は **Phase 3** を継続使用する（Phase 4 という独立フェーズは消える）。

**新しいロードマップ**:

- Phase 1: Mind を 1 個 spawn できる（**実装済**）
- Phase 2: Docker 化 + Mindspace の named volume 化（**Proposed**、ADR-0003）
- **Phase 3: Nexus（MCP サーバー）直行 + Mind が MCP 経由で Dispatch する（本 ADR）**
- Phase 5 以降: Realm / Warden / Guildmaster / リソース管理（別途）

Phase 4 は欠番として残す（番号の再割り当てはしない、履歴整合のため）。

### 2. Mind から他 Mind に繋ぐには Nexus を経由する

Mind が他 Mind に直接アクセスする経路は **作らない**。共有ファイル経由も含めて、すべての Dispatch は Nexus を通過する。

理由: ADR-0002 の世界観で Nexus は「世界の結節点」。Mind は世界に住んでいる以上、世界の API（= Nexus の MCP）を経由して他者に届く。これが Axiom と整合する自然な構造。

### 3. 実装言語は Python

Nexus は Python で実装する。MCP の Python SDK を使う。最小依存（標準ライブラリ + MCP SDK のみ）を初期方針とし、依存追加は都度 ADR / Issue で議論する。

セキュリティ上、Nexus の依存ツリーは定期的にレビューする。攻撃面を小さく保つことを Phase 3 の暗黙の制約とする。

### 4. MCP の最初の機能は Tools のみ

MCP は仕様上 Resources / Tools / Prompts の 3 つを提供できる（ADR-0002 §8 参照）。Phase 3 では **Tools のみ** を実装する。

- **Resources**（Mind が読む情報源）は Phase 5 以降。共有記憶 / Guild 状態 / 外部データの設計が必要で、今やるとスコープが膨らむ。
- **Prompts**（規範テンプレート、Axiom など）も Phase 5 以降。Axiom の機械可読化が前提で、これも別 ADR 案件。
- **Tools**（Mind が実行する操作）だけが、Phase 3 のスコープ = 「Mind ↔ Mind の通信」に必要十分。

### 5. 3 つの Tool を提供する

| Tool | 役割 | 呼び出し主体 |
|---|---|---|
| `send_dispatch` | 指定 Mind に Dispatch を送信する | 送信側 Mind |
| `read_inbox` | 自分宛の未読 Dispatch 一覧を取得する | 受信側 Mind |
| `ack_dispatch` | 指定 Dispatch を「確認した」として archive に移動する | 受信側 Mind |

`read_inbox` は **既読フラグを動かさない**。読んだだけで archive に移ると、Mind の処理途中に落ちた場合に Dispatch を失う。明示 ack 方式で安全側に倒す（後述の 7. 参照）。

### 6. メッセージスキーマは frontmatter + Markdown 本文

```
---
from: mind-designer-01
to: mind-implementer-01
topic: "ADR-0005 のレビュー依頼"
dispatched_at: 2026-05-22T11:30:00Z
msg_id: 2026-05-22T11-30-00Z-abc123
---

# 本文

Phase 3 で MCP 直行に方針更新した。レビューをお願いしたい。
```

ADR-0004 では `dispatch_id / from / to / subject / sent_at / in_reply_to` を提案していたが、本 ADR では最小化し **5 フィールド** に絞る。

| field | 説明 |
|---|---|
| `from` | 送信者 Mind 名 |
| `to` | 受信者 Mind 名 |
| `topic` | 1 行サマリ（旧 subject） |
| `dispatched_at` | ISO 8601 UTC、Nexus が送信受理時に確定する |
| `msg_id` | Nexus が払い出すユニーク ID（タイムスタンプ + ランダム suffix） |

`in_reply_to` は当面なし。スレッド構造は Phase 5 以降。

本文は Markdown。ai-org-os の文化（ADR / Persona すべて Markdown）と整合。

### 7. 既読管理は明示 ack 方式

受信フローは 2 段階:

1. Mind が `read_inbox` を呼ぶ → 自分宛の Dispatch 一覧（msg_id + frontmatter + 本文）が返る。**この時点では archive されない**。
2. Mind が処理完了したら `ack_dispatch(msg_id)` を呼ぶ → Nexus が当該 Dispatch を inbox から archive へ移動する。

**この方式の利点**:

- Mind が読んだ後にクラッシュ / 中断しても、Dispatch は inbox に残る → 次回 `read_inbox` で再取得できる
- 「読了」と「処理完了」を分離できる（Mind の判断で ack を遅らせられる）
- ADR-0002 §9「共有はプロセスを踏む」と整合（ack も明示プロセス）

**運用上の注意**:

- 受信側が `ack_dispatch` を忘れると inbox に溜まる。Phase 5（Warden）でリソース監視するまでは、Mind 側 Persona に「処理後に ack せよ」と明記する
- 同じ msg_id を 2 度 ack しても冪等（Nexus は archive 済みを無視する）

### 8. 裏側のストレージはファイル、Mind からは MCP しか見えない

Nexus の内部実装としてストレージは **ファイル** を使う:

```
runtime/
└── nexus/
    └── storage/
        ├── inbox/
        │   └── <recipient-mind-name>/
        │       └── <msg-id>.md
        └── archive/
            └── <recipient-mind-name>/
                └── <msg-id>.md
```

ただし **Mind から `runtime/nexus/storage/` は見えない / 触れない**。Nexus プロセスだけが書き読みする。Phase 2 のコンテナ化以降は named volume で Nexus コンテナだけに mount する想定。

Mind は MCP の 3 つの Tool 経由でしか Dispatch に触れない。これにより:

- Mind 視点では「世界に郵便を出した / 世界から郵便を受け取った」だけ。実装が DB に変わっても影響しない
- Phase 5（Warden）が裏で archive を圧縮 / 削除しても Mind は感知しない（ADR-0002 §7「Mind 側から制限は見えない」と整合）
- ストレージ実装の差し替え（ファイル → SQLite → Postgres）が Mind 側変更なしで可能

### Phase 3 のスコープ外（Phase 5 以降）

- Resources / Prompts の提供
- 認証 / 認可（誰が誰に Dispatch を送れるかの権限制御）
- Guildmaster / Guild の論理セグメント
- Warden（リソース管理、ライフサイクル管理）
- 大量メッセージ時のバックプレッシャ
- スレッド構造（`in_reply_to`）
- バイナリ添付
- TTL / 容量管理

---

## ADR-0004 との関係

ADR-0004 と本 ADR の関係は **「completely supersedes」ではない**。次のように整理する:

### 何が supersede されるか

- ADR-0004 の **採用案**（推奨案: ファイル + poll + 共通領域 + 永久 archive）は **本 ADR で却下** された
- ADR-0004 が前提とした「Phase 3 と Phase 4 を分離する」前提も **本 ADR で覆された**

### 何が依然有効か

- ADR-0004 の **論点整理**（通信方式の 4 候補、フォーマットの 4 候補、寿命の 4 候補、保管場所の 3 候補、ウェイクの 4 候補）は **設計判断の参考資料として依然有効**
- 特に「ファイル経由 + poll」のトレードオフ分析（依存ゼロ・痕跡自動・Axiom 整合）は、本 ADR が **裏側のストレージとしてファイルを採用** する根拠の一部にもなっている
- ADR-0004 の Axiom 整合性確認テーブルは、本 ADR にもそのまま適用できる（Nexus 経由でも Mindspace 不可侵 / 共有はプロセス は保たれる）

### 推奨される運用

- ADR-0004 の Status を **「Superseded by ADR-0005」** に更新する別 PR を起こす（本 ADR と分離）
- ADR-0004 を削除はしない。設計トレードオフの記録として保持する
- 将来「やはりファイル + poll が必要」と判断した場合の参照点として残す

---

## Consequences（影響）

### ポジティブ

- Mind ↔ Mind 通信が **ADR-0002 の世界観そのまま** に実装される。「世界の結節点」が物理的に存在する
- Phase 4 という独立フェーズが消え、ロードマップが 1 段階短縮される
- MCP を採用することで、痕跡の機械可読化・認可機構の標準化が Phase 5 で乗せやすくなる
- Mind 側の実装が「MCP クライアント」一本になり、後で実装差し替え（ファイル → DB）が Mind を巻き込まない
- Python + 最小依存方針により、npm エコシステムの脆弱性問題から構造的に距離を置ける
- Nexus が単一の通過点になることで、将来「全 Dispatch の監査ログ」「Axiom 違反検出」が一箇所で実装できる

### ネガティブ

- Phase 3 の実装コストが ADR-0004 の推奨案より大きい（MCP サーバー + Mind 側 MCP クライアント設定 + 3 Tool 実装）
- Python という新規言語が `runtime/` に入る。bash スクリプトのみだった構成に Python プロセスが加わる
- Mind の Persona に「MCP 経由で `send_dispatch` / `read_inbox` / `ack_dispatch` を呼ぶ」運用が乗る。手動でファイルを書いて検証、が効かなくなる
- Nexus が落ちると Dispatch が全停止する（ADR-0002 §8 で言及済みの SPOF 懸念が現実化する）
- 開発の初動が遅れる（Phase 3 が「素朴な数百行」から「MCP サーバー実装」に変わる）

### リスク

| # | リスク | 緩和策 |
|---|---|---|
| R1 | Nexus が SPOF（単一点障害）になる | Phase 3 では受け入れる。Phase 5 で冗長化・再起動戦略を別 ADR で扱う |
| R2 | MCP Python SDK の API 変更 / メンテ停止 | 依存を最小化、SDK を薄くラップして差し替え可能にする |
| R3 | Mind 側の MCP クライアント設定が複雑化 | `spawn-mind.sh` で Nexus への接続設定（URL / トークン）を自動配備 |
| R4 | Python 依存ツリーの脆弱性 | 依存追加は ADR で議論、定期的に `pip-audit` 等で監査 |
| R5 | ストレージ実装（ファイル）がスケールしない | Phase 5 でストレージ層を差し替え可能な設計にしておく（Mind からは見えない実装詳細） |
| R6 | `read_inbox` / `ack_dispatch` の競合（複数の同名 Mind が立つ等） | Mind 名のユニーク性は spawn 時に Nexus 側で検証。重複 spawn は拒否 |
| R7 | 認証なしで誰でも `send_dispatch` できてしまう | Phase 3 では受け入れる（ローカル運用前提）。Phase 5 で認可機構を導入 |
| R8 | ADR-0004 の論点（ファイル + poll の素朴な手応え）を経ずに MCP に行く | 裏側ストレージはファイルなので、デバッグ時は `runtime/nexus/storage/` を直接覗いて検証できる。手応えは半分残る |

---

## 議論ログ（Discussion log）

### Step 1: ADR-0004 の推奨案を眺める

ADR-0004 は「ファイル + poll + 共通領域 + 永久 archive」を推奨案として提示し、Proposed 状態で着手判断をユーザーに委ねた。

### Step 2: プロダクトオーナーの違和感

ユーザー: 「Mind から他 Mind に繋ぐには、世界（Nexus）を仲介しないとおかしい」

→ ADR-0002 の世界観（組織 = 思考のネットワーク、Nexus = 結節点）と、ADR-0004 の推奨案（Mind が共有ディレクトリを直接覗く）の **言語の不一致** に気づく。

### Step 3: Phase 3 と Phase 4 の統合

「ファイル + poll を一度作って、後で MCP に置き換える」のコストと、「最初から MCP で行く」のコストを比較。前者は Mind 側の通信レイヤを 2 度書くことになり、後者の方が長期で安い。→ **統合の意思決定**。

### Step 4: 言語選定

Node.js / TypeScript も候補だったが、npm エコシステムの supply chain 攻撃インシデントの増加を理由に却下。**Python を採用**、最小依存とセキュリティ重視。

### Step 5: MCP 機能の絞り込み

Resources / Tools / Prompts のうち、Phase 3 のスコープ（Mind ↔ Mind 通信）に必要十分なのは **Tools のみ**。Resources / Prompts は Phase 5 以降に分離。

### Step 6: Tool 3 種と既読管理

`send_dispatch` / `read_inbox` / `ack_dispatch` の 3 つで Dispatch の送受信が成立する。既読管理は明示 ack（受信者が ack して archive に移動）。

### Step 7: ストレージとアクセス境界

裏側ストレージはファイル、しかし **Mind からは MCP しか見えない**。Phase 5 でのストレージ差し替えを Mind に影響させない設計に。

---

## 次にやること（Phase 3 実装 PR の中身、別 Issue 化候補）

Accepted 後、以下を Issue として切り出す。本 ADR を実装の起点とする。

1. **`runtime/nexus/` ディレクトリ初期化** — Python パッケージ構造、`pyproject.toml` または `requirements.txt`（最小依存）
2. **MCP サーバー骨格** — MCP Python SDK を導入、stdio / HTTP のどちらで提供するか決定（Phase 2 のコンテナ化と整合する側）
3. **`send_dispatch` Tool 実装** — frontmatter 生成、`msg_id` 払い出し、`runtime/nexus/storage/inbox/<to>/` への書き込み
4. **`read_inbox` Tool 実装** — `inbox/<self>/` の列挙、frontmatter + 本文の返却、archive はしない
5. **`ack_dispatch` Tool 実装** — `inbox` → `archive` への移動、冪等性保証
6. **`spawn-mind.sh` 改修** — spawn 時に Nexus へ Mind 名を登録、Mind 側に MCP 接続設定を配備
7. **`kill-mind.sh` 改修** — kill 時に Nexus へ通知、未読は `archive/orphans/` 相当へ退避（ストレージ層の責務）
8. **`test-nexus.sh` 新設** — Mind 2 個 spawn → 双方向 Dispatch → ack → archive 確認の E2E テスト
9. **`runtime/README.md` 更新** — Phase 3 の Quick Start（Nexus 起動、Mind 接続）
10. **ADR-0004 の Status 更新 PR** — `Superseded by ADR-0005` に変更（本 ADR と分離した PR で実施）
11. **依存監査ルーチン** — `pip-audit` 等を CI に組み込む（脆弱性検知）
12. **Persona への追記** — Mind が MCP Tool を呼ぶ運用ガイド、ack 忘れ防止の指針

---

## 関連

- [ADR-0001: ai-org-os を「開発組織の不変項」を定義するフレームワークとして再定義する](./0001-ai-org-os-as-invariant-framework.md)
- [ADR-0002: 用語と「メタのメタ」構造の確定](./0002-vocabulary-and-meta-meta-structure.md)
- [ADR-0003: Phase 2（Docker 化）の設計案](./0003-docker-and-phase-2-design.md)
- [ADR-0004: Phase 3（Dispatch = 思考間通信）の設計案](./0004-dispatch-and-phase-3-design.md) — 本 ADR により superseded
- [`runtime/spawn-mind.sh`](../../runtime/spawn-mind.sh) — Phase 1 実装、Phase 3 で改修対象
- [`runtime/kill-mind.sh`](../../runtime/kill-mind.sh) — Phase 1 実装、Phase 3 で改修対象
- [`runtime/README.md`](../../runtime/README.md) — runtime の現状と Phase 計画
- 関連ファイル（Phase 3 で新規作成予定）: `runtime/nexus/`（Python パッケージ）、`runtime/nexus/storage/`（裏側ストレージ）、`runtime/tests/test-nexus.sh`

---

> **実装は本 ADR を起点に進む。** ADR-0004 は設計トレードオフの記録として残置し、Status を別 PR で `Superseded by ADR-0005` に更新する。
