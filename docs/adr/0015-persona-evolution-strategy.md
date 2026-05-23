# ADR-0015: Persona の進化戦略（追加 / 改定 / 自動生成 / 観測）

> 想定読者:
> - Persona を新規追加するか判断する立場
> - Phase 5 以降で Persona を実装に組み込む人
> - Registry Pillar (#39) を実装するメンテナ
> - Mind の品質低下（Persona drift）を観測する仕組みを作る人

## Status

**Accepted** — 2026-05-24

## ADR 間の依存に関する注記

本 ADR は ADR-0012（PR #57）と **並行作成** されている。本書内で参照する `0012-human-position-outside-realm.md` は PR #57 がマージされて初めて main に存在する。両 PR は独立して accepted 状態だが、main 上でリンクが解決するのは両方マージ後である。

## Context（背景）

現在 Persona は 3 種類のみ：

- `runtime/personas/designer.md` — 設計判断
- `runtime/personas/implementer.md` — 実装
- `runtime/personas/reviewer.md` — レビュー

これで足りるか、どう増やすか、自動生成は可能か、Persona の品質をどう見るか — 議論が #45 として残っていた。

ADR-0012 で「人間 = Realm 外、責務 2 は Pillar コードのレビュー・承認」と決め、ADR-0011 で「Pillar は編集不可、Persona は利用者編集領域」と決めた。Persona は **Pillar ではなく利用者領域** だが、それでも「Persona の決定権は誰にあるか」「自動生成して良いか」は未確定。

Phase 5a-4（Registry Pillar / #39）の設計に直接効くため、本 ADR で固定する。

### 整理済みの前提

- ADR-0002: Persona = 思考の癖（Kind と分離した「思考の方向性」）
- ADR-0010: 観測の 2 種類（Warden 自己観測 vs Mind 制約観測）、Mind の Axiom 制約
- ADR-0011: `runtime/personas/` は利用者編集領域、`runtime/pillars/` は編集不可
- ADR-0012: 人間 = Realm 外、責務 2 は Pillar のレビュー・承認（Persona 改定は責務 2 に類似する）

## Decision（決定）

### 1. Persona は 1 Mind ＝ 1 Persona（固定、変更不可）

Mind は spawn 時に Persona を 1 つ受け取り、**その Mind の生涯を通じて変わらない**。

- 別 Persona が必要なら別 Mind を spawn（=別の思考個体）
- Persona の途中切り替えは禁止（思考の同一性が崩れる、Mindspace の整合性も崩れる）
- Persona のスタックや継承（複数 Persona を持つ Mind）も禁止（責任の所在が不明確になる）

これは ADR-0002 の「Mind = 思考そのもの」と整合する。**思考が変わるなら別の Mind**。

### 2. Persona の追加は「必要性ベース、人間オーソリ」

新しい Persona の追加は次の条件をすべて満たした場合のみ：

1. **必要性が実例で示されている**: 既存 3 Persona では表現できない思考の癖を、最低 1 件の実 Issue / 実タスクで実演している
2. **人間が ADR or PR で承認**: ADR-0012 責務 2 と類似。Persona の追加は組織の「思考レパートリー」を変える行為であり、人間オーソリが要る
3. **既存 Persona との重複がない**: 既存改定で代替できないことを示す（後述 §3）

**先回りで増やさない（YAGNI）**。例えば `researcher.md` / `planner.md` / `retrospector.md` は **必要性が実証されてから** 追加する。今は不要。

### 3. 既存 Persona の改定は CODEOWNERS + ADR 不要

既存 Persona Markdown ファイルの改善（文言調整、例示追加、行動規範の明文化等）は：

- CODEOWNERS で `runtime/personas/` をオーナーレビュー必須にする（PR #56 の CODEOWNERS と同じ機構を拡張、別 Issue 化候補）
- ADR は不要（既存 Persona の精緻化は組織の思考レパートリーを変えない）
- ただし「Persona の責務範囲が変わる」改定は新 Persona の追加扱い（§2 の条件適用）

### 4. Persona の自動生成は採用しない

Warden が Issue や要求から Persona を自動生成する案 (Registry Pillar の野心バージョン) は不採用。

理由：

- ADR-0012 責務 2 の精神（不変項に関わるレビューは人間）と整合させるため
- Persona は組織の「思考レパートリー」= 組織のアイデンティティに直結する
- 自動生成すると組織の同一性が時間で揺らぐ（Mind の同一性は維持できるが、組織レベルの同一性が崩れる）
- ADR-0001 の「組織の不変項」枠組みと整合しない

Warden が Issue から **「この Issue は designer か implementer か reviewer か」を判定して spawn 時に選ぶ** 案は OK（既存 Persona の選択は思考レパートリーを変えない）。これは Phase 5a-4 (#39 Registry Pillar) のスコープ。

### 5. Persona の品質観測（drift 検知）

Persona は「Mind の行動規範」だが、Mind が実際に Persona 通り動いているかは外から観測しないと分からない（ADR-0010 §4 の Warden 観測の対象）。

Observation Pillar の派生機能として **Persona drift 観測** を Phase 5b 以降で導入する：

| 観測軸 | 検知方法 | 例 |
|---|---|---|
| **Persona 逸脱** | Dispatch 内容の傾向分析 | reviewer Persona の Mind が「コードを書き始めた」(implementer の領域) |
| **Persona 不活性** | Dispatch 件数 / mtime | designer Persona の Mind が長時間設計判断を出さない |
| **Persona 衝突** | 2 Mind の応答が同質化 | designer と reviewer が同じ視点で同じ結論を出す（思考の多様性が失われている） |

この機能は **Phase 5b 以降の Observation v0.2-v1.0 (#43)** の範囲。本 ADR では観測軸の定義のみ確定し、実装は #43 に委ねる。

### 6. Persona 同士の関係 — 補完であって依存ではない

3 Persona (designer / implementer / reviewer) は **補完関係** にある：

- designer が判断軸を示す → implementer が具体化する → reviewer が穴を指摘する
- 1 Persona だけでは組織として機能しない（思考の多様性が要る）

ただし **「ある Persona は別 Persona を前提としない」** ことを明示する：

- designer の Mind は reviewer が居なくても designer の仕事を完遂できる
- 別 Persona の Mind が居なくても、その Persona の Mind が壊れることはない
- 補完関係は組織レベルの設計（Guild を作るときの Persona 構成）であって、Persona 自体の依存ではない

これは ADR-0002 の「Mindspace 不可侵 / Dispatch 経由通信」と整合する（Mind 同士は疎結合）。

## Consequences（影響）

### 利点

1. **Persona の決定権が明確化**: §2 / §4 で「人間オーソリ、自動生成しない」と固定。Phase 5a-4 (#39) の設計判断がブレない
2. **「必要性ベース」で先回り作成を抑制**: §2 の YAGNI。`runtime/personas/` が肥大化するのを防ぐ
3. **既存 Persona 改定の手続きが軽量化**: §3。CODEOWNERS で済む（ADR 不要）
4. **Persona drift 観測の方向性が確定**: §5。Observation v0.2-v1.0 (#43) の設計指針
5. **1 Mind = 1 Persona の固定**: §1。Persona スタック / 継承 / 切替の禁止により実装複雑性を抑制

### 不利益 / リスク

1. **必要性の実証コスト**: §2 の条件 1 で「実 Issue で実演」を求めるため、新 Persona 追加は遅くなる。これは意図された保守的設計
2. **Persona drift 観測の実装難易度**: §5 の「Persona 逸脱」「同質化」は LLM ベースの判定が必要になりうる（Observation Pillar の Anthropic SDK 直叩きが要る）。Phase 5b 以降で詳細化
3. **「Persona 自動生成しない」が将来制約になる可能性**: 自律性が極めて高い組織を目指す立場からは制約。ただし ADR-0012 §5 の「自動化の限界線」と整合する（人間に残す責務の一部）

### 派生する Issue / 後続作業

- **#39 (Registry Pillar)**: §4 の「既存 Persona の選択」（思考レパートリーを変えない自動化）の実装範囲
- **#43 (Observation v0.2-v1.0)**: §5 の Persona drift 観測軸の実装
- **CODEOWNERS 拡張**: §3 のために `runtime/personas/` をオーナーレビュー対象に追加（別 Issue 化候補）
- **Persona 追加プロセスのテンプレート化**: §2 の条件を満たす Issue / PR テンプレ（別 Issue 化候補）

## 代替案（不採用）

### A. Persona は実装側で増やす（YAGNI 違反、先回り）

researcher / planner / retrospector / debugger / architect 等を予め揃えておく案。

不採用理由：
- 必要性が実証されていないので「思考レパートリーの肥大化」になる
- 使われない Persona が `runtime/personas/` に並ぶと、新規 Mind を spawn する人が混乱する（どれを選ぶか分からない）
- 必要になってから追加（§2）の方が、Persona の質も高くなる（実例で磨かれる）

### B. Persona は Mind が動的に切り替えられる

Mind が状況に応じて Persona を切り替える案。

不採用理由：
- 「思考の同一性」が崩れる（ADR-0002 の Mind = 思考そのもの と矛盾）
- Mindspace の蓄積が「どの Persona の蓄積か」分からなくなる
- 別 Persona が必要なら別 Mind を spawn（§1）で十分

### C. Persona は Warden が自動生成する

Warden が Issue から動的に Persona を作る案。

不採用理由：
- §4 で詳述。組織のアイデンティティが時間で揺らぐ
- ADR-0012 責務 2 と矛盾（Persona の追加は人間オーソリが本旨）

### D. Persona の責務範囲は固定（後発改定なし）

Persona Markdown を一度書いたら変更不可とする案。

不採用理由：
- 実運用で Persona の文言改善は必須（曖昧な行動規範を明文化する等）
- §3 で「責務範囲を変えない改定」は ADR 不要、CODEOWNERS のみ、と軽量化することで実用と整合性を両立

### E. Persona は階層（継承）構造を持つ

`base.md` を継承する `designer.md` のような構造にする案。

不採用理由：
- §1 と矛盾（1 Mind = 1 Persona、スタックや継承は禁止）
- 階層化すると Persona drift 観測（§5）の判定が複雑化
- 重複は §3 の改定で解決すべきで、構造で解決すべきではない

## 関連

- [ADR-0001](0001-ai-org-os-as-invariant-framework.md) — 組織の不変項（Persona は不変項に近い）
- [ADR-0002](0002-vocabulary-and-meta-meta-structure.md) — Persona / Mind の定義
- [ADR-0010](0010-observation-philosophy-and-warden-as-collective.md) §4 — 観測の 2 種類（§5 の根拠）
- [ADR-0011](0011-warden-claude-naming-and-separation.md) — `runtime/personas/` は利用者編集領域
- [ADR-0012](0012-human-position-outside-realm.md) §2 — 責務 2（Persona オーソリの根拠）
- Issue #39 (Registry Pillar) — §4 の Persona 選択自動化の実装範囲
- Issue #43 (Observation v0.2-v1.0) — §5 の Persona drift 観測の実装
- Issue #45（Discussion D）— 本 ADR の起票元
- `runtime/personas/designer.md`, `implementer.md`, `reviewer.md` — 現状の 3 Persona
