# ADR-0021: axiom と後天的依存注入の分離 (Guild = 指示・監視の権限境界に限定)

> 想定読者:
> - Phase 5c-2 以降で Guildmaster Persona / 新規 axiom を設計するメンテナ
> - Guild manifest にフィールドを追加しようとする人
> - 「これは Guild が機械強制すべきルールか? それとも構成か?」と迷ったセッション

## Status

**Accepted** — 2026-05-25

## Context（背景）

ADR-0019 で Guild を「組織枠の物理表現」「組織パッケージ」と定義し、Phase 5c-1 (PR #88) で物理層 (manifest / axiom / overlay / claim 制約) を実装した。直後の振り返りで operator から次の指摘が来た:

> ルールと後天的な依存注入が混同しやすいところだね。注意しながらすすめよう

そして方針の核となる短い 1 行:

> guild はたぶんその権限、できることの箱だけきめて、のこりは依存注入になるとおもう。
> 指示や監視の「可能かどうか」だけだねぇ。

Phase 5c-1 までは「Guild がルールを持つ」と「Guild が構成を持つ」を厳密に区別せず、manifest に `kinds: [...]` / `personas: [...]` の allowlist と、`axiom.md` の機械強制ルールを **同居** させていた。Phase 5c-2 で Guildmaster Persona / 追加 axiom に着手しようとすると、その曖昧さが直接踏み穴になる:

- 「Mind 数上限を axiom にしようか」 — ルールっぽいが、本質的には運営判断 (= 依存注入)
- 「Persona に『リスクを必ず挙げる』と書いた」 — ルールに見えるが Mind が守る保証はない (= 文書、宣言的指示)
- 「Guild manifest の `personas: [...]` 」 — 機械的に弾く (ルール的挙動) が、利用者が overlay で自由に書き換える (構成的) — ハイブリッド

これらを混同したまま Guildmaster を導入すると、「axiom.md に rule を書いたが enforce code が無い (= 嘘の axiom)」「Persona に強制力のある書き方をしてしまう (= 守られない宣言)」「Guild に運営ポリシーを axiom として固定して overlay 不能にしてしまう」といった事故が起きる。

CLAUDE.md §3.1 のチェックリストに先行で「A: axiom / B: 宣言 / C: 依存注入」の自問項目を入れた (PR #89) が、文書化された判断軸として ADR に残すことで Phase 5c-2 以降のメンテナが踏み穴を回避できる。

## Decision（決定）

### 1. Guild が定義する axiom は「Mind 同士の指示・監視関係の可否」のみ

**Guild の責務を以下に限定する**:

> Guild が機械強制する axiom は、**inter-Mind 関係の「指示」と「監視」の可否** に関するもののみ。

- **指示**: ある Mind が別の Mind に対して、自分の意思で **何かを行わせる** (spawn / kill / claim / dispatch 等) 関係
- **監視**: ある Mind が別の Mind の **状態 / 入出力 / 内部活動を観察できる** 関係
- **可否**: できる / できない の boolean (条件付き許可は将来の拡張、本 ADR の v0.1 ではブール)

例 (v0.1 で実装済 / 将来候補):

| axiom 候補 | カテゴリ | 状態 |
|---|---|---|
| `claim-only-own-guild`: 自 Guild の Issue を自 Guild の Mind に指示する | **指示** の可否 | ✅ Phase 5c-1 で機械強制中 |
| `guildmaster-only-spawn`: spawn-mind は Guildmaster persona の Mind のみ | **指示** の可否 | ⬜ Phase 5c-2 候補 |
| `guildmaster-only-kill`: kill-mind は Guildmaster persona の Mind のみ | **指示** の可否 | ⬜ Phase 5c-2 候補 |
| `guildmaster-can-read-inbox`: 配下 Mind の Dispatch inbox を read_inbox | **監視** の可否 | ⬜ Phase 5c-2 候補 |
| `cross-guild-dispatch-forbidden`: 他 Guild の Mind に send_dispatch | **指示** の可否 | ⬜ 将来 |

### 2. それ以外はすべて「Guild への依存注入」

以下は **axiom ではない**。Guild manifest に書かれるが「構成」「DI」として扱い、利用者が overlay で自由に書き換えてよい:

| Guild に注入される依存物 | カテゴリ | 例 |
|---|---|---|
| `kinds: [...]` allowlist | C (依存注入) | この Guild に入れる Mind の種別 |
| `personas: [...]` allowlist | C (依存注入) | この Guild に揃える職能 |
| `purpose` | C (依存注入) | Guild の目的説明 |
| 運営ポリシー (Mind 数上限 / 評価基準 / レビュー閾値 等) | C (依存注入) | 利用者が運用しながらチューニング |
| Persona の中身 (CLAUDE.md として配布される文書) | B (宣言) | Mind が守る保証はない、人間・レビュー時に発覚 |
| Mind の判断基準 / 振る舞い詳細 | B (宣言) | Persona ドキュメントの一部 |

allowlist (`kinds` / `personas`) は **機械的に弾く** ため「ルールに見える」が、これは「**注入された構成に基づく機械検証**」であって axiom そのものではない。利用者が overlay で `personas: [designer, analyst]` に書き換えれば spawn 可能なものは変わる。axiom は変わらない (claim-only-own-guild は何があっても enforce される)。

### 3. 3 カテゴリ (A / B / C) の判定軸

Guild 周辺の機能を設計するとき、毎回以下のチェックリストを通す:

| カテゴリ | 性質 | 違反したら | enforce 場所 |
|---|---|---|---|
| **A. axiom** (機械強制ルール) | code 側で機械的に reject | 強制的にブロック | Pillar コード (e.g., nexus.py の `code: forbidden`) |
| **B. 宣言的指示** (Persona / 文書) | 文書、機械検証なし | 守られない可能性、人間/レビュー時に発覚 | テンプレート文書 (e.g., `templates/personas/*.md`) |
| **C. 後天的依存注入** (manifest / 構成) | 利用者が overlay で上書き | 違反概念なし (構成変更扱い) | manifest フィールド、`$AI_ORG_OS_HOME/<category>/` |

**A になれる条件**: enforce する code が **必ず Pillar 内に存在** すること。axiom.md に rule を書いただけで enforce code が無いものは **嘘の axiom**。axiom と名乗らせない (B に降格、または機能不足として ADR で議論)。

**B が A に格上げされる条件**: 守られないことの実害が大きく、かつ機械検証可能になった (= 検出ロジックが書ける) 時。CLAUDE.md §3.3 のセキュリティ・整合性系判定とリンク。

**A が C と混じらない条件**: axiom は **Guild の本質** (= 指示・監視関係) を縛る。構成項目 (allowlist 等) を axiom として固定して overlay 不能にしない。

### 4. 既存 ADR との関係

- **ADR-0017** (層 A / 層 B): 層 B (Mind の組織) が機械強制すべきは「Mind 同士の関係性」のみ、という本 ADR の方針は ADR-0017 の精緻化。層 B' (= 各 Mind 内部の振る舞い) は Persona (B) と Pillar コード (A) の責務であって Guild axiom の管轄外
- **ADR-0019** (Guild = 組織枠): §1 の Guild 物理表現は維持。本 ADR は §3 の axiom フォーマットを限定する形で補強する (axiom の対象を「指示・監視」に絞る)
- **ADR-0020** (構成 vs 依存物): 「同梱テンプレ (B) / 依存物の実体 (C) / runtime state」の物理分離は維持。本 ADR は **同じ axis を 1 段上 (= 概念レベル)** で立てる: A (axiom) vs C (依存注入) の区別。物理分離 (ADR-0020) と概念分離 (本 ADR) は **直交軸**

### 5. Phase 5c-2 への接続

Guildmaster Persona を導入する際の本 ADR ベースの設計:

| 要素 | カテゴリ | 配置 |
|---|---|---|
| Guildmaster の **判断ロジック** (どう声をかけるか) | B (Persona) | `templates/personas/guildmaster.md` |
| Guildmaster が spawn-mind を**叩ける**こと | A (axiom) | Guild axiom (`guildmaster-only-spawn`) |
| Guildmaster が配下 Mind の inbox を**監視できる**こと | A (axiom) | Guild axiom (`guildmaster-can-read-inbox`) |
| Mind 数上限 / Persona 構成比 | C (依存注入) | manifest 拡張フィールド or 別 dotfile |
| Guildmaster が「reviewer を増やすべきか」を判断する基準 | B (Persona) | guildmaster.md 内の判断ガイド |

axiom (A) は機械強制 = Pillar コードに enforce 必須。Persona (B) は文書のみ。manifest (C) は overlay 可。

## Consequences（影響）

### 利点

1. **設計判断のブレが減る**: Guild に新機能を入れるとき「A/B/C どれ?」を毎回確認する習慣ができる。CLAUDE.md チェックリストと連動
2. **嘘の axiom が生まれない**: axiom = enforce code 必須、というルールで「axiom.md に書いただけ」を防止
3. **利用者の自由度を保護**: 運営ポリシーを axiom に固定しないので、利用者は自 Guild を overlay で自由に運用できる (= ADR-0019 の「組織を git clone で配れる」が実効性を持つ)
4. **Phase 5c-2 が動かしやすい**: Guildmaster の権限境界 (A) と判断ロジック (B) を分離設計できる。後でロジックだけ差し替える Guild を作れる
5. **ADR-0017 (層 A / 層 B) との接続が綺麗**: 層 B 内部をさらに「Mind 関係 (A axiom) / Mind 内部 (B Persona)」に分解できる

### 不利益 / リスク

1. **「これは A/B/C どれ?」と毎回問う運用コスト**: 慣れるまでオーバーヘッド。チェックリストと ADR で軽減
2. **B (Persona) は機械強制でないので守られない可能性**: 「ルールっぽい」内容を書きたくなる誘惑がある。Persona テンプレ作成時に「これ A に格上げすべきでは?」と自問するクセが必要
3. **「ルールに見えるが構成」(allowlist 等) は引き続き紛らわしい**: 機械的に弾くという挙動は A と区別しにくい。manifest フィールドに「これは構成、上書き自由」コメントを書く運用で緩和
4. **axiom が増えすぎると Mind の自由が削られる**: 「指示・監視の可否」軸でも、過度な axiom は組織の運用を硬直化させる。axiom 追加は ADR 化を必須にしてレビューを通す (Phase 5c-2 以降の運用ルール)

### 派生する Issue / 後続作業

- **Phase 5c-2 (Guildmaster MVP)**: 本 ADR の方針で Guildmaster Persona (B) + 権限境界 axiom 2〜3 個 (A) を設計
- **CLAUDE.md チェックリストの実運用観察**: 半年後に「A/B/C 軸が実際に踏み穴回避に効いたか」を retrospective する
- **manifest フィールドのコメント整備**: 既存 `templates/guilds/default/manifest.md` に「これは構成、利用者が上書き自由」コメントを将来追加 (本 ADR スコープ外)

## 代替案（不採用）

### A. Guild axiom の対象を限定しない (現状維持)

axiom.md に何でも書ける案 (運営ポリシー / Mind 数 / Persona 内容まで axiom 扱い)。

不採用理由:
- 利用者が「これは固定 / これは上書き可」を判別できない (= 組織パッケージ思想の崩壊)
- 機械強制でないものまで axiom と呼ばれる → 「嘘の axiom」量産
- ADR-0017 層 B の責務がぼやける (Mind 関係と Mind 内部の混同)

### B. Persona (B) も Guild axiom 扱いにする

Persona に書かれた行動規範を axiom と見なし、機械強制を試みる案。

不採用理由:
- Persona は自然言語の文書。**機械強制の対象にならない** (= A になれない)
- 強制力を持たせたいなら enforce code を書くべき (= 個別 axiom に格上げ、本 ADR の流れ)
- 「Persona は強制」と誤認させると Mind が制限される一方、強制実装が伴わず形骸化

### C. Mind 数 / リソース管理を axiom にする

Guild の運営パラメータを axiom として固定する案。

不採用理由:
- これらは「**指示・監視の可否**」ではなく「**リソース管理 / 運営判断**」。Guild の本質 (層 B の組織) から外れる
- 利用者の運用条件 (大規模 / 小規模 / 単一人 / チーム) で大きく変わる値を axiom 固定すると overlay が壊れる
- DI として持つ方が組織パッケージ思想と整合 (利用者が overlay で調整)

### D. axiom / DI の区別を CLAUDE.md チェックリスト止まりにする (ADR 化しない)

文書として ADR まで起こさず、運用ルールに留める案 (PR #89 で実施した範囲)。

不採用理由:
- Phase 5c-2 で Guildmaster を導入する瞬間に「Guildmaster の権限は axiom か、Persona か」「Mind 数は何か」と複数の混同パターンが同時に来る → ADR で先に確定しておかないと実装中に判断軸がブレる
- ADR 化することで「**この方針を撤回するには新規 ADR が要る**」という重みが生まれ、設計の安定性が増す

## 関連

- [ADR-0017](0017-warden-monitoring-vs-job-monitoring.md) — 層 A (Warden) / 層 B (Mind 組織) 分離。本 ADR は層 B 内部をさらに axiom (A) / Persona (B) / DI (C) に分解
- [ADR-0019](0019-guild-as-organization-unit.md) — Guild = 組織枠の物理表現。本 ADR は §3 axiom フォーマットの対象を「指示・監視の可否」に限定する形で補強
- [ADR-0020](0020-templates-and-org-manifest-separation.md) — 同梱テンプレ / 実体 / runtime state の物理分離 (3 物理カテゴリ)。本 ADR は概念レベル (A/B/C) の直交軸
- [ADR-0011](0011-warden-claude-naming-and-separation.md) — Pillar 編集権限の境界。axiom enforce code は Pillar 配下 (編集不可)、Persona / manifest は依存物カテゴリ
- CLAUDE.md §3.1 — 設計時の自問チェックリストに A/B/C 軸が含まれる (PR #89 で追加済)
- PR #88 — Phase 5c-1 Guild 物理表現 (本 ADR の前段)
- Phase 5c-2 (未着手) — 本 ADR を最初の commit に同梱して Guildmaster MVP 着手予定
