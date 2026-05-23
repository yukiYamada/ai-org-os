# ADR-0010: 観測の哲学 / Warden は機能の集合体 / Mind の能動性

> 想定読者: Phase 5 を実装するメンテナ、Observatory を進化させる人、Warden / Mind の関係を理解したい全員。

## Status

**Accepted** — 2026-05-23

## Context（背景）

2026-05-23 の壁打ちセッションで、Phase 5（Realm + Warden）着手前に詰めるべき構造的な論点が 2 つあった：

- **議論 A**: Mind の能動性をどう実装するか
- **議論 C**: 観測の哲学（誰が誰を、何のために観測するのか）

これらを経て確定した整理を本 ADR に残し、Phase 5 着手の判断材料 + 既存 ADR（特に ADR-0006）の更新起点とする。

## Decision（決定）

### 1. Mind の能動性 = event-aware self-driven loop

ADR-0002 で「Mind は能動的、ウェイク条件なし」と決めたが、実装が「Claude CLI = 対話入力待ち」だったため矛盾していた。本 ADR で実装方針を確定。

**能動性の定義**:
- ループは止まらない（**内発的**）
- ただし**外部影響**（Dispatch / Issue / Event）でループ内の**考える対象**が変わる
- 各 cycle で「内側の目的」と「外側の状況」を踏まえて、Mind 自身が次の行動を決める
- 人間の思考と同型: 心臓は止まらない、何もない時も考える、外から声をかけられたら考える対象が変わる

**実装方針**:
- **Warden 側**: Anthropic SDK 直叩き（対話不要、決定論的）
- **Mind 側**: Claude CLI + 外側ループ（MCP 経由 Nexus との相性のため CLI 維持）
- ハイブリッド

```bash
# Mind の心臓（外側スクリプト擬似コード）
while true; do
  prompt=$(build_prompt)         # Persona + 現状（inbox / Mindspace）
  claude -p "$prompt" > out.json # 1 cycle = Mind の脳
  sleep $(parse_wait out.json)   # 次まで（Mind 自身が決める / Body 仕様）
done
```

- 外側スクリプト = **心臓 / 呼吸**（持続性）
- Claude = **脳**（1 cycle 分の思考）
- 状態継承 = Mindspace 上のファイル（次の cycle で読まれる）

### 2. cycle 周期は Kind（Body）仕様

「Mind が自分で周期を決める」のではなく、**Kind（Body 性能）が周期を規定**する。
- Generic Kind = 標準周期
- 別の Kind を作る時に周期を変える（高頻度 Body / 省エネ Body）
- 周期内での適応（前 cycle の判断で次 sleep を微調整）は許容

### 3. idle は存在しない

- Mind の内面は**常に**動いている
- 停止するのは Realm がリソース遮断したとき（=Mind の死）のみ
- 「待機しろ」は**外部からの指示**として存在、Mind は自分の Persona の中で「待機モード」を実行する（内的には考えてる）
- **Observatory のラベル「idle / stale」は観測の外形**（=活動が見えない）であって、Mind の内面状態ではない

### 4. 観測は 2 種類

| # | 観測主体 | 範囲 | 制約 | 目的 |
|---|---|---|---|---|
| 1 | **Warden**（世界そのもの） | **全部見える** | なし | 世界の自己認識（世界を人が扱うため） |
| 2 | **Mind**（観測機能を利用する側） | 制限あり | **Axiom 制約下** | 組織の改善活動など |

- **Warden の観測 = 世界の自己認識**。「見えていい」ではなく「**見えるのが世界の定義**」。
- 「Level i〜iv で見える範囲を制限する」発想は誤り（Warden は世界そのものだから無制限）
- 制限が必要なのは Mind 側（2）の観測のみ

### 5. Axiom と Warden の関係（重要）

- **Axiom（Mindspace 不可侵 / 思考⇔思考の境界）は Mind 同士のルール**
- **Warden には Axiom が適用されない**（ルールを管理する主体だから）
- 法律の階層と同型：私法（Axiom）は個人（Mind）同士、公権力（Warden）は必要なら全部見える、ただし上位（人間）に責任を負う
- Warden を監督するレイヤー = ユーザー（人間、Realm の外）

### 6. Warden は単一プロセスではなく機能の集合体

「Warden Claude が中で動く」という従来のイメージ（ADR-0006）は不正確。

**Warden = 世界の自己実装の総和**:
- 観測機能: `observe.py` / ファイル監視
- ライフサイクル機能: `spawn-mind.sh` / `kill-mind.sh` / `list-minds.sh`
- 通信路: Nexus (MCP server)
- 判断機能: Claude API call / 対話セッション（複数並走、機能特化）
- 強制機能: PreToolUse hooks
- Kind Registry: `kinds/` ファイル群
- ...

これらの**集合体**として Warden が成立する。「**1 つの Claude セッションでは足りない**」（ユーザー判断）。

階層：
- **Realm**（境界） = 世界の輪郭、ルール適用範囲
- **Warden**（中身） = 世界の自己実装の総和
- **Mind**（住人） = 世界の中で活動する個体

### 7. Warden 内 Claude は Mind とは別カテゴリ

Warden の判断機能を担う複数の Claude セッションは、Mind ではない。

判別軸：
- **Mind** = ユーザー（Guildmaster / 人間）が定義・編集する、Guild に所属する個
- **Warden 機能の Claude** = **ai-org-os 自体が提供、誰も編集できない**、Warden に属する機能

実装方針：
- ファイル配置で線引き（`runtime/` 配下のコア機能 vs ユーザー追加分）
- 命名は実装時に決定（本 ADR の範囲外、Pillar / Daemon / Servitor などの候補は議論済みだが未確定）

### 8. Observatory の位置づけ修正

- 現状の `runtime/observatory/observe.py` = **Warden 不在時の代替実装**
- Phase 5 で Warden が登場 → **Observatory は Warden に吸収される**
- ROADMAP.md は「Observatory 単体の進化」想定だったが、本当は「**Warden の観測 API として進化**」
- Mind が観測情報を必要なら、Warden 経由で取得（Warden が提供する形式は MCP tool / Mind テンプレ注入 / 人間向け UI のいずれか）

観測情報の性質は **application log と同じ**：
- アプリ自身は能動的にログ取らない、自動的に抜かれる
- アプリは「ログ取られてる」を意識しなくていい
- 同じく、Mind は「Warden に観測されてる」を意識しなくていい

## Consequences（影響）

### ポジティブ
- Mind の能動性が**実装可能**なレベルで定義された（CLI + 外側ループ）
- 観測の哲学が明確、Phase 5 で Warden を設計するときに迷わない
- Warden = 集合体の整理により、既存ツール（observe / spawn / kill / list / nexus）が**既に Warden の構成要素**として位置づけ直される
- Mind と Warden 内 Claude の編集権限境界が明確（コア vs 拡張）

### ネガティブ
- **ADR-0006（Phase 5 設計）と齟齬**: 「Warden Claude が走る」表現を「Warden = 機能集合体」に更新する必要
- **Observatory ROADMAP の前提が変わる**: 「単体ツールの進化」→「Warden 機能としての進化」へ書き直し
- Warden 内 Claude の命名が未確定（実装時に必要）

### リスク
- Warden = 集合体だと「中心がない」ように見えて、運用責任が曖昧化する可能性
  - 緩和: 集合体内の各機能に明確な責務を割り当てる（Phase 5a 着手時の設計タスク）
- 「Axiom は Mind 同士のルール、Warden は別」が「Warden 暴走時の歯止め」を弱める可能性
  - 緩和: Warden を監督するのは人間（Realm の外）、人間レビューと git history が安全装置

## 議論ログ（時系列、要約）

### 議論 A: Mind の能動性

1. ADR-0002 の「Mind は能動的」と実装の「Claude CLI = 受動的」が矛盾
2. 能動性の定義候補 → 「内発的ループ + 自己決定」をユーザーが採用
3. 「外部影響でループ内の考える対象が変わる」を追加 → **event-aware self-driven loop**
4. 実装方式: ハイブリッド（Warden=SDK / Mind=CLI + 外側ループ）
5. cycle 周期: Body (Kind) 仕様で規定
6. idle なし: Mind は常に考えてる、止まるのは Realm のリソース遮断のみ
7. 「待機しろ」は外部指示、Mind は自分の中で「待機モード」を実行

### 議論 C: 観測の哲学

1. 私が「Observatory のラベル変更」「観測軸を AI 特有に」と実装範囲の話に飛ぶ
2. ユーザー補正: 「観測ツールの話なの？」「もっと哲学の話」「思考と物理デバイスに分けて考えればいい」
3. 観測は 2 種類: Warden の自己認識 / Mind の制約付き観測
4. Warden は世界そのもの、無制限観測が定義
5. Axiom は Mind 同士のルール、Warden は別レイヤー（人間が監督）
6. Warden = 機能の集合体、1 Claude では足りない
7. Warden 内 Claude は Mind と別カテゴリ（編集権限境界）
8. 命名議論は二次的、本 ADR では未確定で良し

## 次にやること

本 ADR の含意を実装に反映する作業：

1. **ADR-0006 (Phase 5) を更新**: Warden = 集合体としての再定義、Phase 5a 段階分割の修正
2. **`runtime/observatory/ROADMAP.md` を更新**: Warden 機能の一部としての進化方向
3. **Warden 内 Claude の命名と分離 ADR**（命名 + ファイル配置）を別 ADR で（必要なら）
4. **Phase 5a 着手時の検討事項**:
   - Warden 内機能の責務マトリクス（observe / spawn / lifecycle / 判断 / 強制）
   - 各機能が独立プロセスか統合プロセスか
   - Mind の外側ループスクリプトの実装

これらは本 ADR の承認後、別 PR で対応する。

## 関連

- [ADR-0002](./0002-vocabulary-and-meta-meta-structure.md) — 用語と階層構造（Realm / Warden / Mind / Axiom）
- [ADR-0005](./0005-phase-3-mcp-direct-with-nexus.md) — Phase 3 = MCP 直行（実装済）
- [ADR-0006](./0006-phase-5-realm-warden-guildmaster.md) — Phase 5 設計（**本 ADR で部分更新が必要**）
- [ADR-0008](./0008-nexus-identity-binding.md) — identity binding（Warden / Mind 認可拡張の基盤）
- [ADR-0009](./0009-relationship-with-bash-editor-and-claude-team.md) — bash-editor / claude-team との関係（観測ツールの参考元）
- `runtime/observatory/` — 現状の観測機能（Warden の一部として位置づけ直し）
