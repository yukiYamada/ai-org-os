# ADR-0009: bash-editor / claude-team との関係性と流用方針

> 想定読者:
> - Phase 5 を実装するメンテナ（特に Realm の観測 / 監督ロジックを書く担当）
> - Realm 観測ツール（`runtime/observatory/`）を設計・拡張する担当
> - 外部ツールを ai-org-os に統合するかどうかを判断する意思決定者（プロダクトオーナーおよび将来のメンテナ）

## Status

**Proposed** — 2026-05-23

> 本 ADR は **方針の記録**。**フルスケールの実装は本 ADR の承認後に着手する**。
> ただし本 ADR と同じ PR で、**流用方針を体現する最小実装が `runtime/observatory/` に同梱される**（純粋関数の Python ポート、CLI 1 本）。
> これは「方針を文書だけで終わらせず、即座に流用を開始する」ためのセット。

---

## Context（背景）

### これまでの位置

- [ADR-0001](./0001-ai-org-os-as-invariant-framework.md): ai-org-os は「開発組織の不変項（Axiom）を定義するフレームワーク」。
- [ADR-0002](./0002-vocabulary-and-meta-meta-structure.md): 用語と階層構造を確定。**Realm / Warden / Nexus / Guild / Guildmaster / Mind / Mindspace / Axiom / Dispatch**。
- [ADR-0005](./0005-phase-3-mcp-direct-with-nexus.md): Phase 3 = Nexus（Python MCP server）直行。**Accepted**、PR #23 で実装済。
- [ADR-0006](./0006-phase-5-realm-warden-guildmaster.md): Phase 5（Realm + Warden + Guildmaster）の設計案。**Proposed**。

Phase 3 までは「Mind が複数立ち、Nexus 経由で Dispatch を交わす」状態が成立した。次に控える Phase 5 では Realm という実コンテナ + Warden + Guildmaster が登場し、3 段階ライフサイクル（要求→承認→実行）が初めて enforce される。

### きっかけ

Phase 5 着手前の壁打ちで、プロダクトオーナーが次のように述べた：

> **「いまの世界を観測するツールがいる。」**

Phase 3 までの ai-org-os では、複数 Mind が並走している状態を確認するには `runtime/list-minds.sh` を叩くか、`runtime/nexus/storage/` を直接覗くしかない。Phase 5 で Realm が登場し、3 段階プロセスが回り、`realm/audit/dispatches/` に痕跡が蓄積するようになると、**「世界の今を眺める窓」** が無いまま運用に入ることになる。これは Phase 5 のリスク R4（Mind の能動性をどう観測するか）にも直結する。

ここで、プロダクトオーナー自身が既に書いていた 2 つのリポジトリが俎上に上がった：

#### bash-editor (local-multi-window-bash-editor)

- Node.js / Express + WebSocket + xterm.js + MCP server
- **複数 PTY セッションを 1 ブラウザタブで監視**するローカルツール
- Supervisor / Worker パターン（1 つの監督セッション + 複数の作業セッション）
- **groupId による階層制御**（グループ単位でセッションを束ね、アクセス制御）
- **waiting_confirmation 検知**（出力末尾を解析して「確認待ち」状態を自動検出）
- MCP tools 群（`get_output`, `send_message`, `get_status`, `create_session`, ...）
- HTTP API（`POST /api/message`, `GET /api/sessions/:id/output`, ...）

#### claude-team

- Claude Code の **Supervisor / Worker 分離型** 開発基盤
- openspec-workflow（propose → spec-review → apply → PR）を組み込み
- bash-editor の HTTP API を裏で叩く構成
- **PreToolUse hooks による hard block**（特定の操作を物理的に止める）
- **learned-patterns の自動生成**（実行ログからパターンを蒸留して再利用）

### 用語が衝撃的に対応する

両リポジトリを精読した結果、bash-editor の語彙が ai-org-os の語彙と **驚くほど整合する** ことが分かった：

| bash-editor / claude-team | ai-org-os | 一致度 |
|---|---|---|
| session | **Mind** | ほぼ同義（コンテナで動く独立思考） |
| groupId | **Guild** | 論理セグメントとして Mind を束ねる単位 |
| Supervisor | **Guildmaster** | グループの監督主体 |
| waiting_confirmation 検知 | **Guildmaster の 3 段階プロセス受信** | 「承認待ち」を自動検出する点で同型 |
| MCP tools | **Nexus tools** | プロトコル同一（MCP） |
| `POST /api/message` | **Dispatch** | Mind 間メッセージ送信 |
| Supervisor が複数 Worker を監督 | **Guildmaster が複数 Mind を管理** | パターン同一 |

ai-org-os が ADR-0002 で「仮想空間メタファー」で組み立てた抽象が、bash-editor が現実に解いた問題（複数 PTY を 1 画面で監督したい）と **同じ構造** にぶつかっていたことを意味する。

### プロダクトオーナーの最終判断

bash-editor / claude-team を本格的に取り込む（fork / submodule / monorepo 化する）かどうかが論点となった。プロダクトオーナーの結論：

> **「無理に取り込む必要はない。使えるものは使う。」**

つまり：

- **fork や submodule 化はしない**（取り込み過ぎは結合度を上げる）
- **部品流用と並行運用に留める**（必要なら関数・パターン・思想レベルで流用、依存追加なし）

本 ADR はこの判断を SSOT として記録し、流用の対象 / 対象外を明示する。

---

## Decision（決定）

### 1. fork / submodule 化はしない

bash-editor / claude-team のいずれも、**ai-org-os リポジトリの subtree / submodule / fork として取り込まない**。

**理由**:

- ai-org-os は ADR-0005 で「最小依存」「Python 中心」「npm 系の supply chain リスクを構造的に回避」と決めた。bash-editor を取り込むと **Node.js / npm 依存ツリー全体が流入する**。
- claude-team は openspec-workflow という強い前提（propose → spec-review → apply → PR）を持つ。これは ai-org-os の Phase 計画と目的領域が異なる（claude-team = 開発ワークフロー支援、ai-org-os = 組織の不変項フレームワーク）。
- fork すると上流追従コストが発生する。ai-org-os の保守者は最小依存方針を維持するために、外部リポジトリの内部変更に追従し続ける義務を負いたくない。
- ADR-0002 で「Realm の境界は組織のアイデンティティ」と定義した以上、外部ツールを境界の内側に引き込む決定は慎重であるべき。

### 2. 部品流用：純粋関数 / パターン / 思想レベル

**取り込まないが、設計知見は最大限活用する**。具体的な流用候補：

| 流用元 | 流用対象 | 流用先 | 形態 |
|---|---|---|---|
| bash-editor `lib/pure.js` | `calcStatus` / `detectConfirmPrompt` / `calcCategory` | `runtime/observatory/` | **純粋関数として Python に移植** |
| bash-editor `lib/group-tree.js` | グループ階層アクセス制御パターン | Phase 5b（Guildmaster の Guild 内権限判定） | **パターン参照（コードは書き直し）** |
| claude-team PreToolUse hooks | hard block パターン（特定操作を物理的に止める） | Phase 6 以降の Axiom enforcement | **思想参照** |
| claude-team learned-patterns | 実行ログからのパターン自動抽出 | Phase 6+ の Axiom refinement / Persona 改稿 | **思想参照** |

#### 2.1. `lib/pure.js` の Python 移植（本 PR で着手）

bash-editor の `lib/pure.js` は **依存ゼロの純粋関数群** で、次の機能を提供する：

- `calcStatus(lastOutputAt, idleThresholdMs)` — セッションが idle / active / stale のどれかを判定
- `detectConfirmPrompt(tail)` — 出力末尾を解析して「確認待ち」状態を検出
- `calcCategory(session)` — セッションをカテゴリ分類

これらは「テキスト + タイムスタンプ」だけから状態を導く純粋関数なので、**言語非依存で書き直せる**。本 PR で `runtime/observatory/pure.py` として Python に移植する。bash-editor の MIT ライセンス（要確認）と整合する範囲で、関数仕様を踏襲しコメントで出典を明記する。

#### 2.2. group-tree のアクセス制御パターン（Phase 5b 参考）

bash-editor の `lib/group-tree.js` は「グループ階層 + 上位グループからのアクセス可否判定」を実装している。Phase 5b で Guildmaster が「自 Guild 内の Mind だけを管理できる、他 Guild には介入できない」という権限境界を実装する際、このアクセス制御パターンを **設計参照** する。**コードはコピーせず、ai-org-os の用語（Guild / Mind）で書き直す**。

#### 2.3. PreToolUse hooks の思想（Phase 6 以降）

claude-team の PreToolUse hooks は「特定の操作（例: 危険なファイル削除）を物理的にブロックする」仕組み。これは ai-org-os の Axiom enforcement と思想的に重なる：「ルール違反を文書で禁じるだけでなく、ランタイムで止める」。

ただし claude-team は Claude Code hooks に依存しており、ai-org-os の Mind は MCP 経由でしか動かない。**hooks 機構そのものは流用できないが、「ランタイム enforcement」という思想は Phase 6 以降の Warden に取り込む**。

#### 2.4. learned-patterns の思想（Phase 6+）

claude-team の learned-patterns は「成功 / 失敗パターンを実行ログから抽出し、次回以降に再利用する」仕組み。ai-org-os では Phase 6 以降で「Axiom の解釈を運用ログから refinement する」「Persona を運用ログから改稿する」という方向に進化させる余地がある。**実装ではなく思想として記録**。

### 3. 並行運用：bash-editor を「外部観測ツール」として位置づける

bash-editor を ai-org-os の **外部ツール** として、必要なときに併用する。

具体的には：

- ai-org-os 本体（Realm / Nexus / Mind）は Python で完結し、bash-editor に依存しない
- ただし **Phase 3 dogfooding 検証や Phase 5 の Realm 観測時**に、複数 Mind の出力を 1 画面で眺めたい場合は、bash-editor をホスト側で起動して併用してよい
- 併用手順は `runtime/verification/phase-3-dogfooding/README.md` に「方式 E: bash-editor 併用」として追記する余地を残す（**本 ADR の PR では追記しない**、別 PR）

これにより、bash-editor を「持っていれば便利、無くても動く」位置に保ち、結合度を最小化する。

### 4. Realm 観測ツール（`runtime/observatory/`）の方針

ai-org-os 独自の Realm 観測ツールは、**最小 Python 実装** で作る：

- 配置: `runtime/observatory/`
- 言語: Python（ADR-0005 の Python 中心方針と整合）
- 依存: 標準ライブラリ + 既存 Nexus が使っている SDK のみ。**新規依存追加なし**
- 初期インターフェース: **CLI 1 本**（`python -m observatory status` 等）。Web UI / WebSocket / xterm.js は当面作らない
- 機能の出発点:
  - 既存 Mind の状態一覧（`runtime/list-minds.sh` の上位互換）
  - 各 Mind の最終 Dispatch 時刻と idle / active 判定（`pure.py` の `calcStatus` を使う）
  - Phase 5 完了後は `realm/audit/dispatches/` を読んで 3 段階プロセスの進捗を表示

将来 Web UI が必要になっても、CLI を先に整備しておけば自動化（CI / nightly 監査）にそのまま乗る。Web UI 化は本 ADR では決定せず、別 ADR / Issue で検討する。

### 5. 本 PR の範囲

本 ADR と同じ PR で、流用方針を体現する最小実装を含める：

- `runtime/observatory/` を新設
- `runtime/observatory/pure.py` — bash-editor `lib/pure.js` の Python 移植（純粋関数のみ）
- `runtime/observatory/__main__.py` — 最小 CLI（`status` サブコマンドだけでよい）
- `runtime/observatory/README.md` — 使い方と本 ADR への参照

これにより「方針を文書だけで終わらせず、即座に流用を開始する」セットになる。

---

## 用語の対応表（参照用）

bash-editor / claude-team の用語を ai-org-os 用語に翻訳するときの早見表。`docs/glossary/` が将来できたら統合する想定。

| bash-editor / claude-team | ai-org-os | 注記 |
|---|---|---|
| session | Mind | コンテナで動く独立した思考主体 |
| sessionId | Mind 名（ユニーク文字列） | Nexus が払い出す identity（ADR-0008） |
| groupId | Guild | 論理セグメント、実コンテナを持たない |
| Supervisor session | Guildmaster | Guild の監督主体 |
| Worker session | Mind | Guildmaster に管理される側 |
| `POST /api/message` | `send_dispatch` MCP tool | Mind 間メッセージ送信 |
| `GET /api/sessions/:id/output` | `read_inbox` 相当（観測用途） | 直接の対応は無いが、観測 API として近い |
| `waiting_confirmation` 検知 | Guildmaster の `approve_spawn` 受信 | 「承認待ち」を検出する点で同型 |
| MCP tools | Nexus tools | プロトコル同一 |
| group hierarchy | Guild 階層（Phase 6 以降） | Phase 5 では単一 Guild のみ |
| Supervisor の hard block | Warden の Axiom enforcement | Phase 6 以降で参考 |
| learned-patterns | Axiom refinement の素材 | Phase 6+ で思想参照 |

---

## 流用しないもの（明示）

「使えるものは使う」の裏返しとして、**取り込まないもの** を明示する：

| 対象 | 取り込まない理由 |
|---|---|
| bash-editor の WebSocket / xterm.js / Web UI 全体 | Web フロント実装は ai-org-os の最小依存方針と齟齬。Realm 観測は当面 CLI で十分。Web UI が必要になっても Python 系で別途設計する |
| bash-editor の Express / Node.js ランタイム | npm 依存ツリーの流入は ADR-0005 の方針に反する |
| bash-editor の MCP server 実装そのもの | ai-org-os は Nexus（Python MCP server）を既に持つ。MCP server を 2 つに分ける合理性がない |
| claude-team の openspec-workflow 全体 | propose → spec-review → apply → PR は claude-team の目的（開発ワークフロー支援）に最適化されており、ai-org-os の目的（組織不変項フレームワーク）と領域が異なる |
| claude-team の Claude Code hooks 設定 | ai-org-os の Mind は MCP 経由で動く。Claude Code hooks 機構は ai-org-os の Mind には適用できない |
| 両リポジトリの Node.js ランタイム依存 | ADR-0005 の Python 中心 / 最小依存方針と齟齬 |
| 両リポジトリのテストハーネス | ai-org-os は `runtime/tests/` に bash スクリプトで揃えている。テスト基盤を二重化する必要なし |

---

## Consequences（影響）

### ポジティブ

- **車輪の再発明を回避**: bash-editor の `pure.js` 設計（idle/active/confirm 判定）を Python で再利用、設計検討の時間を節約
- **依存追加ゼロ**: Python 標準ライブラリ + 既存 Nexus SDK のみ。ADR-0005 のセキュリティ方針が保たれる
- **設計知見の流用**: Supervisor / Worker パターン、group-tree のアクセス制御、PreToolUse hooks の思想は、Phase 5 以降の設計判断を加速する
- **並行運用が可能**: 必要なときに bash-editor を外部ツールとして立てれば、Web UI / xterm.js も使える。「持っていれば便利、無くても動く」の柔軟性
- **方針の SSOT 化**: 「fork するの？しないの？」を毎回議論せずに済む

### ネガティブ

- **自動追従できない**: bash-editor / claude-team の最新変更は ai-org-os に自動で反映されない。流用元が改善されても、こちらが手動でポートしない限り取り込まれない
- **二重メンテのリスク**: bash-editor で `pure.js` のバグが直っても、`runtime/observatory/pure.py` には自動反映されない。コメントで出典を明記して定期的に diff を取る運用が必要
- **「使えるものは使う」の判断が属人化**: どの部品を流用すべきかの判断は、毎回設計者が両リポジトリを読み解いて行う必要がある。新規メンテナの参入コストが上がる
- **境界の曖昧さ**: 「外部ツールとして併用してよい」と書くと、いつのまにか bash-editor 前提の運用が広がるリスク

### リスク

| # | リスク | 緩和策 |
|---|---|---|
| R1 | 流用先（bash-editor）の設計思想とのズレが時間と共に広がる | 半年ごとに両リポジトリの最新版を読み返し、差分を本 ADR にメモする運用 |
| R2 | bash-editor が将来 archive / abandon された場合、流用元へのリンクが切れる | bash-editor / claude-team のスナップショット（コミットハッシュ）を本 ADR に固定で記録する（次節） |
| R3 | 「使えるものは使う」が広く解釈され、なし崩しに依存が増える | 流用は必ず本 ADR の「Decision §2」に列挙された対象に限定。新規流用は別 ADR で追加する |
| R4 | `pure.py` が `pure.js` から乖離して観測結果が食い違う | `runtime/observatory/pure.py` のテストを bash-editor の `pure.js` テストと同じケースで揃える（テストデータレベルでの整合性確認） |
| R5 | プロダクトオーナー以外がこの判断の背景を知らずに「なぜ取り込まないのか」を再議論する | 本 ADR を関連 ADR の必読に追加し、Phase 5 関連 PR のレビューで参照させる |

---

## 流用元スナップショット（2026-05-23 時点）

将来の参照のため、本 ADR を書いた時点での流用元の状態を記録する。コミットハッシュは本 ADR を Accept する際に確認・追記する（**TODO: Accepted 化時に埋める**）。

| リポジトリ | パス | スナップショット |
|---|---|---|
| local-multi-window-bash-editor | (external repository) | （Accepted 時に commit hash を記入） |
| claude-team | (external repository) | （Accepted 時に commit hash を記入） |

両リポジトリは ai-org-os の外部にある。本 ADR の決定により、ai-org-os が両者に依存することはない。

---

## 議論ログ（Discussion log）

### Step 1: 「世界を観測するツールがいる」

プロダクトオーナーが Phase 5 着手前に発言：「いまの世界を観測するツールがいる」。

Phase 3 までの ai-org-os では Mind の状態を眺める手段が `runtime/list-minds.sh` と `runtime/nexus/storage/` の直接観察しかなく、Phase 5 で Realm + 3 段階プロセスが登場すると観測の負荷が一気に増えると判断。

### Step 2: 自作 2 リポジトリの存在

設計担当（私）が両リポジトリの取り込み検討を依頼された。bash-editor は「複数 PTY を 1 ブラウザタブで監視」、claude-team は「Claude Code の Supervisor / Worker 分離型開発基盤」。

### Step 3: 用語の衝撃的な対応

両リポジトリを精読した結果、bash-editor の語彙が ai-org-os の語彙と強く重なることを発見：

- session ≒ Mind
- groupId ≒ Guild
- Supervisor ≒ Guildmaster
- waiting_confirmation 検知 ≒ Guildmaster の 3 段階プロセス受信
- MCP tools ≒ Nexus tools
- `POST /api/message` ≒ Dispatch

ai-org-os が抽象的に組み立てた仮想空間メタファーが、bash-editor が現実問題として解いた構造と一致していた。

### Step 4: 取り込みの是非を議論

選択肢：
- (a) fork して取り込む
- (b) submodule 化する
- (c) monorepo 化する
- (d) 部品流用 + 並行運用に留める

(a)〜(c) は Node.js / npm 依存ツリーの流入を伴い、ADR-0005 の最小依存方針と衝突。また claude-team の openspec-workflow は ai-org-os の目的領域と異なる。

### Step 5: プロダクトオーナーの最終判断

> **「無理に取り込む必要はない。使えるものは使う。」**

(d) を採用。本 ADR でその方針を SSOT として記録する。

### Step 6: 「方針記録 + 即座に流用開始」のセット

本 ADR の PR に `runtime/observatory/` の最小実装（`pure.py` の Python 移植 + 最小 CLI）を同梱することで、ADR が文書で終わらず、流用が即座に開始される構成にする。

---

## 関連

- [ADR-0001: ai-org-os を「開発組織の不変項」を定義するフレームワークとして再定義する](./0001-ai-org-os-as-invariant-framework.md)
- [ADR-0002: 用語と「メタのメタ」構造の確定](./0002-vocabulary-and-meta-meta-structure.md) — 用語の対応表の上位ソース
- [ADR-0005: Phase 3 = Nexus（MCP サーバー）直行](./0005-phase-3-mcp-direct-with-nexus.md) — Python 中心 / 最小依存方針の出典
- [ADR-0006: Phase 5（Realm + Warden + Guildmaster）の設計案](./0006-phase-5-realm-warden-guildmaster.md) — Realm 観測ツールが Phase 5 で本格化する文脈
- [ADR-0007: Phase 3 reliability properties](./0007-phase-3-reliability-properties.md)
- [ADR-0008: Nexus セッションを Mind の identity に bind する](./0008-nexus-identity-binding.md)
- 外部リポジトリ（参照のみ、依存しない）:
  - `local-multi-window-bash-editor` — Node.js + Express + WebSocket + xterm.js + MCP server
  - `claude-team` — Claude Code Supervisor/Worker + openspec-workflow + bash-editor 連携
- 本 PR で同梱されるファイル:
  - `runtime/observatory/pure.py`（bash-editor `lib/pure.js` の Python 移植）
  - `runtime/observatory/__main__.py`（最小 CLI）
  - `runtime/observatory/README.md`（使い方と本 ADR への参照）

---

> **改めて**: 本 ADR は **Proposed**。**フルスケールの実装（Web UI、Realm 統合、Phase 5 Audit 連携）は本 ADR の承認後に着手する**。
> ただし本 ADR と同じ PR で **流用方針を体現する最小実装が `runtime/observatory/` に同梱される**ことで、方針記録と流用開始をワンセットで進める。
> Accepted に昇格させるには、「流用対象（pure.js / group-tree / PreToolUse / learned-patterns）の取捨が妥当か」「並行運用の境界（外部ツールとして併用）の線引きが妥当か」を確認する必要がある。
