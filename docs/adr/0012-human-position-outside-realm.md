# ADR-0012: 人間は Realm の外に居る（人間 = 外部監督者）

> 想定読者:
> - ai-org-os の最終形を考える意思決定者
> - Phase 5a-5（Inbox Pillar / Issue 投入インターフェース）を実装するメンテナ
> - 「人間の介入をどこまで自動化に置き換えるか」を判断する立場
> - 現状の運用（人間がスクリプトを叩く）と最終形のギャップに混乱した実装者

## Status

**Accepted** — 2026-05-23

## パス参照に関する注記

本 ADR で参照する `runtime/pillars/*` 配下のパス（`spawn-mind.sh` / `observe.py` 等）は **Phase 5a-2 / PR #56（Issue #37）の物理移動で配置される** ものを前提とする。
PR #56 マージ前は同等ファイルが旧位置（`runtime/spawn-mind.sh` / `runtime/observatory/observe.py` 等）に存在し、本 ADR の決定はどちらの配置でも有効。レビュー時点でファイルが見つからない場合は ADR-0011 のマッピングを参照のこと。

## Context（背景）

ADR-0002 で「**人間というカテゴリは組織内に存在しない**」と決め、ADR-0010 で「Warden = 世界そのもの／機能の集合体」「Mind には観測上の制約がある」を確定した。

しかし実運用ではユーザー（人間）が頻繁に作業している：

- PR レビュー / マージ判断
- Issue / Discussion での議論
- `runtime/pillars/lifecycle/spawn-mind.sh` を直接叩く
- ADR の起票・更新
- `docker compose up` で Realm を立ち上げる
- Codex / 自動レビュアーへの応答

**「組織内に存在しない」と書いた人間が、これだけ介入している現状はどう整理するのか？**

この矛盾が解消されないまま Phase 5a-3 以降に進むと、Judgment Pillar の設計（「Mind がやってよいこと vs Warden がやること vs 人間がやること」の判定）でブレが出る。Phase 5a-5（Inbox Pillar）の設計でも「人間 → Realm の入力経路」の意味づけがあいまいだと壊れる。

### 整理済みの前提（再掲）

| カテゴリ | 場所 | 編集権限 | 観測制約 |
|---|---|---|---|
| **Mind** | Realm 内、Mindspace 所有 | 自身の Mindspace のみ | Axiom 制約下（他 Mind 不可侵） |
| **Warden / Pillar** | Realm 内、世界の一部 | ai-org-os core が定義、誰も編集不可 | 制約なし（世界そのもの） |
| **人間** | Realm の **外側** | ai-org-os 自体を改変できる唯一の主体 | Realm の外から境界経由でのみ作用 |

## Decision（決定）

### 1. 人間は Realm の外側に居る（恒久確定）

ADR-0002 / ADR-0010 の「人間 = 組織内に存在しない」を **「人間 = Realm の外側に居る外部監督者」** として明示化する。

```
┌─ 人間（外部監督者）───────────────────────────────────┐
│                                                       │
│   ・Axiom 改定権                                       │
│   ・Pillar コードのレビュー / 承認                     │
│   ・Realm の起動・停止                                 │
│   ・Issue / Dispatch の投入                            │
│   ・致命的失敗時の介入                                 │
│                                                       │
│   ┌─ Realm（境界）───────────────────────────────┐   │
│   │                                               │   │
│   │   ┌─ Warden（世界そのもの）───────────────┐  │   │
│   │   │  Observation / Lifecycle / Conduit /  │  │   │
│   │   │  Judgment / Registry / Inbox Pillar   │  │   │
│   │   └────────────────────────────────────────┘  │   │
│   │                                               │   │
│   │   ┌─ Guild ───────────────────────────────┐  │   │
│   │   │   Mind (Mindspace) × N                │  │   │
│   │   └────────────────────────────────────────┘  │   │
│   │                                               │   │
│   └───────────────────────────────────────────────┘   │
│                                                       │
└───────────────────────────────────────────────────────┘
```

人間は **Realm の壁の外側に居る**。Realm の壁を通じて作用するが、Realm の中の構成要素（Mind / Warden）ではない。

### 2. 人間の責務（恒久的に人間に残るもの）

| # | 責務 | 理由（なぜ Warden に委譲できないか） |
|---|---|---|
| 1 | **Axiom（不変項）の改定** | 不変項そのものを定義するのは ai-org-os というフレームワークの上位レイヤー。Warden が自分の存在条件を書き換えるのは循環参照 |
| 2 | **Pillar コードのレビュー / 承認** | Pillar = Warden の構成要素。Warden 自身が自分のコードを承認するのは循環参照（ADR-0011 で「編集不可」と定義した境界の維持） |
| 3 | **Realm の起動・停止** | Realm の存在自体を決めるのは Realm の外側でしかありえない（容器の中から容器を作れない） |
| 4 | **Realm への外部入力**（Issue / 要求の投入） | 組織の目的は外部から与えられる。Phase 5a-5（Inbox Pillar、#40）はこの境界の実装 |
| 5 | **致命的失敗時の手動介入** | Warden が自己破綻したとき、外側からしか回復できない（Phase 5b 以降に詳細化、#47 と接続） |

これらは **Warden がどれだけ高度化しても人間に残る** 責務である。1〜3 は構造的に循環参照のため自動化不可能。4 は「外部目的の流入経路」として境界の定義そのもの。5 は failsafe としての必須性。

### 3. 人間と Realm の接点（境界経由のチャンネル）

人間は Realm に対して直接書き込まない。**境界に置かれたチャンネル経由でのみ作用する**。

| チャンネル | 方向 | 実装 | フェーズ |
|---|---|---|---|
| **GitHub PR / CODEOWNERS** | 人間 → ai-org-os コア | `.github/CODEOWNERS`（ADR-0011） | Phase 5a-2 で導入済 |
| **Realm Lifecycle**（docker compose up/down） | 人間 → Realm 起動・停止 | `runtime/realm/docker-compose.yml` | Phase 5a-1 で導入済 |
| **Inbox Pillar** | 人間 → Warden（Issue / Dispatch 投入） | `runtime/pillars/inbox/`（仮） | Phase 5a-5（#40） |
| **Observation の人間向け出力** | Warden → 人間 | `runtime/pillars/observation/observe.py`（Phase 5a-2 / #56 で配置、旧 `runtime/observatory/observe.py`） | Phase 5a-2 で実装 |
| **致命的失敗の通知** | Warden → 人間 | 未定義 | Phase 5b 以降（#47） |

**Mind が人間と直接やり取りすることはない**（境界経由ですらない）。Mind から見える人間の作用は、すべて Inbox Pillar が Warden 経由で取り次いだ Dispatch として現れる。これは ADR-0010「Mind の Axiom 制約」と整合する。

### 4. 現状の運用と最終形のギャップ（重要、混乱を防ぐため明文化）

**現状（Phase 3 + 5a-1〜2）と最終形（Phase 5b 以降）で人間の介入度が違う**ことを明示する。これを暗黙にしておくと、現状の運用を見て「ai-org-os の最終形」と誤解する読者が出る。

| 現状（暫定） | 最終形（恒久） |
|---|---|
| 人間が `spawn-mind.sh` を直接叩く | Warden が Lifecycle Pillar 経由で spawn 判断（人間は Inbox 経由で要求のみ） |
| 人間が Mind の Dispatch を直接読む（デバッグ） | Observation Pillar の出力を経由してのみ閲覧 |
| 人間が Issue を本リポジトリに直書き | Inbox Pillar 経由で要求が Warden に流入 |
| 人間が Codex の指摘に手で対応 | Judgment Pillar が一次レビューを通し、人間は最終承認のみ |

**現状の人間の介入は「Warden 未実装」「Phase 移行中」の暫定であって、最終形ではない**。

ただし「責務 1〜5（Axiom 改定 / Pillar レビュー / Realm 起動停止 / 外部入力 / failsafe）」は最終形でも残る。**減らせるものと減らせないものを区別する**。

### 5. 自動化の限界線

「人間の関与をどこまで減らせるか」への回答：

- **減らせる**: 日常的な Mind 操作（spawn / kill / Dispatch 観察 / Issue 受理 / Codex 一次対応）
- **減らせない**: 責務 1〜5（§2 の表）。これらは構造的・境界的に人間以外が担えない

最終形でも人間は **「Realm の上位境界としての監督者」** という位置を保つ。「人間ゼロの完全自律組織」は ai-org-os の到達目標ではない。

## Consequences（影響）

### 利点

1. **Inbox Pillar（Phase 5a-5 / #40）の設計指針が明確化**: 「人間 → Warden への入力経路」という境界の定義そのもの、と意味づけられる
2. **Judgment Pillar（Phase 5a-3 / #38）の判定軸がクリアに**: 「Mind がやってよい / Warden がやる / 人間がやる」を §2 の責務表に照らして判定できる
3. **現状の運用と最終形のギャップが顕在化**: 読者が「今のやり方 = 最終形」と誤解しない。Phase 移行の動機が記録される
4. **「人間ゼロ」議論に終止符**: ai-org-os は人間ゼロを目指さないと宣言。期待値ズレを防ぐ
5. **責務 5（failsafe）が独立トピックに**: #47（失敗・暴走の扱い）の議論で「人間に戻すパス」の必要性を明示できる

### 不利益 / リスク

1. **「組織内に人間が居ない」という ADR-0002 の表現が誤解を招く可能性** — 本 ADR で「Realm の外側に居る」と再定義することで補正するが、ADR-0002 自体の文言は変えない（ADR は不変、refine は新 ADR で）
2. **境界チャンネルの実装コスト** — Inbox Pillar の実装が遅れると、人間の介入が他チャンネルに漏れ続ける（既知）
3. **「責務 5（failsafe）」の具体化が未着手** — #47 待ち。本 ADR では責務の存在だけ確定し、メカニズムは別 ADR に委ねる

### 派生する Issue / 後続作業

- #40（Phase 5a-5: Inbox Pillar）— 人間 → Warden チャンネルの実装、本 ADR の §3 が設計指針
- #47（Discussion F: 失敗・暴走の扱い）— 責務 5（failsafe）の具体化、本 ADR が前提
- #38（Phase 5a-3: Judgment Pillar）— §2 の責務表が判定ルールの原則
- 既存運用の段階的移行 — 「人間が直接叩く」を「Inbox 経由」に置き換える作業の TODO 化（別 Issue 化候補）

## 代替案（不採用）

### A. 人間を「特殊な Mind」として組織内に取り込む

`runtime/minds/human/` のような扱いにして Dispatch チャンネルだけで作用させる案。

不採用理由：
- 責務 1（Axiom 改定）が人間にしかないことを表現できない
- Mind は Axiom に縛られる側だが、人間は Axiom を**書く側** — 同じカテゴリにできない
- 「Realm を起動する者は Realm 内に居られない」という物理的事実とも矛盾

### B. 人間を Warden の一部として扱う

「人間は Warden の構成要素（Pillar）の一種」とする案。

不採用理由：
- Warden は ai-org-os core が提供する「編集不可」の存在（ADR-0011）。人間は Warden を編集できる立場なので語義矛盾
- Warden は Realm 内に居るが、人間は Realm の外側に居る（責務 3 の物理的事実）
- Warden = 世界そのもの、人間 = 世界の上位監督者、と区別したほうが構造が綺麗

### C. 「人間の関与をゼロにする完全自律」を最終形とする

完全自動化を目標にする案。

不採用理由：
- 責務 1〜3 は循環参照のため構造的に自動化不可能（§2 の表）
- ai-org-os の本旨は「組織の不変項の定義」であって「人間ゼロの実現」ではない
- 自律と監督は両立する（むしろ監督があるから自律できる）

## 関連

- [ADR-0001](0001-ai-org-os-as-invariant-framework.md) — ai-org-os の本旨（不変項定義フレームワーク）
- [ADR-0002](0002-vocabulary-and-meta-meta-structure.md) — 「人間というカテゴリは組織内に存在しない」の初出
- [ADR-0010](0010-observation-philosophy-and-warden-as-collective.md) — Warden = 機能の集合体、Mind の Axiom 制約
- [ADR-0011](0011-warden-claude-naming-and-separation.md) — Pillar の編集不可境界（責務 2 の根拠）
- Issue #40（Phase 5a-5）— Inbox Pillar 実装、本 ADR §3 が設計指針
- Issue #47（Discussion F）— failsafe（責務 5）の具体化議論
- Issue #46（Discussion E）— 本 ADR の起票元
