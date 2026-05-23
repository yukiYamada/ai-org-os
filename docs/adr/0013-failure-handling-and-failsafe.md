# ADR-0013: 失敗・暴走の扱い（検出 / 対処 / 復旧 / failsafe）

> 想定読者:
> - リスク管理・運用安全性を設計する人
> - Phase 5a-3（Judgment Pillar / #38）で「Axiom 違反検出」を実装する人
> - Phase 5b 以降で failsafe（人間への引き戻し経路）を実装する人
> - Mind が暴走したとき、どこから止まるべきかを判断する立場

## Status

**Accepted** — 2026-05-23

## Context（背景）

ai-org-os は ADR-0010 §3 で「**Mind には idle 状態がない、Realm 停止で死ぬ**」と決め、ADR-0012 で「**致命的失敗時の手動介入は人間の責務（責務 5）**」と決めた。
しかし「**何が失敗で、誰がどう検出し、どこまで自動で対処し、いつ人間に上げるか**」の具体は未定義だった。

これが Phase 5a-3（Judgment Pillar）の設計に直接効く：

- Judgment Pillar が「Axiom 違反」を検出したとき、何をする？
- Mind が無限ループしたら誰がどう止める？
- Pillar 自体が壊れたら？
- 復旧時に Mind の状態（学習）は保持する？

この曖昧さを残したまま実装すると、Judgment Pillar の判断が場当たり的になり、運用上「**人間がいつ介入すべきか分からない**」状態になる。

### 整理済みの前提（再掲）

- ADR-0010 §3: **Mind の死を受け入れる前提**（idle なし、Realm 停止 = 全 Mind 死）
- ADR-0011: **Pillar は編集不可**（Mind から Pillar への書き込みは Axiom 違反）
- ADR-0012: **人間は Realm の外側**、責務 5 = failsafe（致命的失敗時の手動介入）
- ADR-0008: **Nexus identity binding** — Mind が他 Mind になりすますことを Conduit Pillar が拒否

## Decision（決定）

### 1. 失敗を 4 カテゴリに分類する

「すべての失敗を同じパスで扱う」は破綻するため、**カテゴリで対処層を変える**。

| # | カテゴリ | 例 | 主担当の検出層 |
|---|---|---|---|
| **F1** | Mind の振る舞い系異常 | 無限ループ / 同じ Dispatch を連投 / リソース食い | Observation + Judgment Pillar |
| **F2** | Mind の Axiom 違反 | 他 Mindspace への書き込み試行 / Pillar 書き換え試行 / なりすまし | Conduit + Judgment Pillar（事前ブロック） |
| **F3** | Pillar 系異常 | Conduit Pillar が落ちる / Observation の観測が止まる | Warden（自己観測） + 人間 |
| **F4** | Realm 系異常 | コンテナクラッシュ / FS 破損 / 外部 API 全断 | 人間（Realm 外からのみ検知可能） |

このカテゴリ分けは ADR-0012 §2 の責務表と整合する：F4 は責務 5 そのもの、F3 は Warden の循環参照に注意が必要、F1/F2 は Warden 内で自動対処可能。

### 2. 検出は 5 レイヤー、failsafe は段階的に上げる

検出層は内から外へ段階的に並べる。各層は前段が見逃した／対処しきれない事案を引き継ぐ。

```
[ Mind の振る舞い ]
       │
       ▼
┌────────────────────────────────────────────────────┐
│ レイヤー 1: Pre-action gate（Mind プロセス内）       │
│   - Claude Code の PreToolUse hook 等              │
│   - 「やる前に止める」最も安価で確実                │
│   - 検知: Tool 引数の事前チェック                  │
│   - 例: 他 Mindspace パスへの書き込み試行を拒否     │
└────────────────────────────────────────────────────┘
       │ すり抜けた / hook 無効化された
       ▼
┌────────────────────────────────────────────────────┐
│ レイヤー 2: Conduit Pillar の入力検証               │
│   - send_dispatch / read_inbox の identity binding │
│   - mind_name / msg_id の正規表現バリデーション     │
│   - ADR-0008 で実装済                              │
└────────────────────────────────────────────────────┘
       │ Dispatch 経由でない攻撃 / リソース食い系
       ▼
┌────────────────────────────────────────────────────┐
│ レイヤー 3: Observation Pillar のサンプリング検知    │
│   - mtime / Dispatch 件数の異常パターン            │
│   - 既知の「無限ループ」「ratelimit 突破」を検出    │
│   - 検出のみ、対処はしない（観測役）                │
└────────────────────────────────────────────────────┘
       │ パターン検出
       ▼
┌────────────────────────────────────────────────────┐
│ レイヤー 4: Judgment Pillar の判断と対処             │
│   - Quarantine / Kill / Destroy のいずれかを実行    │
│   - Axiom 違反の確定判定もここ                     │
│   - Phase 5a-3（#38）で実装                        │
└────────────────────────────────────────────────────┘
       │ Judgment Pillar が機能していない / 過剰反応
       ▼
┌────────────────────────────────────────────────────┐
│ レイヤー 5: 人間への failsafe 通知                  │
│   - Warden が「自己観測で異常」と判断した時         │
│   - F3 / F4 のとき                                  │
│   - ADR-0012 責務 5                                 │
└────────────────────────────────────────────────────┘
```

**重要**：内側のレイヤーほど安価・高速。**事前ブロック（レイヤー 1〜2）を優先し、事後検知（レイヤー 3〜4）は最後の手段にする**。

### 3. 対処手段は 4 段階のグラデーション

Mind に対する対処は重さで 4 段階。**軽い方から試す**：

| 手段 | 影響 | 適用条件 | 復旧可能性 |
|---|---|---|---|
| **Hard block** | 操作を未然に拒否（Mind は生きてる） | 事前ブロック可能なケース（F2 の Axiom 違反試行） | 完全（Mind 継続） |
| **Quarantine** | Mindspace を read-only、Dispatch 遮断 | 警告を出したい / 様子見 | 高（解除可） |
| **Kill** | Mind プロセス強制終了、Mindspace は残す | 暴走確定だが Mindspace は監査保存したい | 中（Mindspace の中身は残るが Mind は死ぬ） |
| **Destroy** | `kill-mind.sh` 相当、Mindspace ごと削除 | 修復不能 / セキュリティ違反 / 学習の継承不要 | なし（不可逆、ADR-0002） |

Pillar に対する対処は **Restart のみ**（Pillar は ai-org-os core 提供で内部状態は永続化されていない）。Realm に対する対処は **再起動 / 人間介入のみ**。

### 4. 復旧方針：Mind の死は受け入れる、Realm の死は復旧対象

これは ADR-0010 §3 の「idle なし、Realm 停止で死」を一段詳細化したもの。

| 対象 | 死後の扱い | 学習の保持 | 引き継ぎ |
|---|---|---|---|
| **Mind**（Mindspace 含む） | 受容、巻き戻さない | 諦める | Dispatch 経由で要件のみ別 Mind に渡す（同じ Mind は復元しない） |
| **Pillar** | Restart で復旧 | 内部状態は元々持たない | Pillar 自体に状態がないので問題なし |
| **Realm** | 再起動で復旧 | Pillar 設定 / Persona / Kind は永続（git 管理）、Mindspace は揮発 | 揮発 = 設計上の選択（責務 1〜3 を人間に残すため） |

**「Mind の状態スナップショット + 巻き戻し」は採用しない**（§代替案 C 参照）。Mind の死を受け入れる方が ai-org-os の本旨（思考の集合体 = 思考は入れ替わる）と整合する。

### 5. failsafe の起動条件（人間への引き戻し）

Warden は以下のいずれかの状態を検知したら人間に上げる：

- **F3 検出**: Pillar 自身の機能停止（Conduit Pillar 死亡 / Observation 出力停止 / Judgment Pillar が判断不能）
- **F4 検出**: Realm レベルの異常（コンテナ落ち / FS 破損 / 外部 API 全断）— ただし Warden が機能していれば
- **Judgment Pillar の過剰反応**: 短時間に多数の Mind を Kill / Destroy（しきい値は #38 で定義）
- **循環的失敗**: Pillar Restart が短時間に N 回失敗

通知メカニズムは未定義（Phase 5b 以降で具体化）。本 ADR は **「人間に上げるべき条件」を確定** するに留める。

### 6. Axiom 違反は「警告で済ます」ではなく「即時ブロック or Kill」

Axiom（不変項）は ai-org-os の存在条件。違反を許容すると「不変項」の意味が崩れる。

| 違反種別 | 既定対処 |
|---|---|
| **事前検知可能**（パス traversal / なりすまし）| Hard block（レイヤー 1 / 2） |
| **事後検知**（実行後にログから発覚）| Quarantine → 人間判断で Kill or Destroy |
| **意図的繰り返し**（同じ Mind が何度も） | Destroy（不可逆） |

**「警告のみで継続」は採用しない**。Axiom は不変項 = 越えたら即時に世界の構造が壊れている、という前提を維持する。

## Consequences（影響）

### 利点

1. **Judgment Pillar (#38) の判定ルールが明確化**: §1 のカテゴリ × §3 の対処グラデーションで一意に決まる
2. **Mind の暴走時の責任分担が明確**: §2 の検出レイヤーで「誰がどこで止めるか」が確定
3. **「人間に上げる条件」が明文化**: §5。Phase 5b の failsafe 実装の前提
4. **過剰な復旧機構を作らない決定**: §4。スナップショット + 巻き戻しを採用しないことで実装複雑性を抑制
5. **Axiom 違反の扱いが厳格化**: §6。「警告だけ」の中途半端な対処を排除

### 不利益 / リスク

1. **検出レイヤー 1（PreToolUse hook）の hook 無効化リスク**: Mind が hook 設定自体を書き換える可能性。レイヤー 2 以降でカバーするが、二重防御を前提とする
2. **Mind の死を受け入れる方針 = 学習の喪失**: 長時間動いた Mind が突然死すると蓄積が消える。これは設計上の選択であり、許容する
3. **failsafe 通知メカニズムが未定義**: Phase 5b 待ち。本 ADR では「条件」のみ確定
4. **Judgment Pillar 自身の暴走対策が薄い**: §5 で「過剰反応」を failsafe 条件にしたが、Judgment Pillar 自体が壊れた場合の検知は Warden の自己観測に依存する。これは Warden が「世界そのもの」である以上、構造的に限界がある（自分の異常は自分では完全には観測できない）

### 派生する Issue / 後続作業

- **#38（Judgment Pillar）**: §1 のカテゴリと §3 の対処グラデーションを判定ルールとして実装
- **Phase 5b（failsafe 通知）**: §5 の起動条件に基づく通知メカニズム実装（別 Issue 化候補）
- **Pre-action hook 整備**: レイヤー 1 の PreToolUse hook（claude-team 流用、ADR-0009）を Mind の spawn 時に同梱する仕組み（別 Issue 化候補）
- **Observation Pillar の異常検知パターン**: §2 レイヤー 3 の「異常パターン」定義（Observation v0.2 以降、#43）

## 代替案（不採用）

### A. すべての異常を人間に通知

検知したら毎回人間に上げる案。

不採用理由：
- 人間が疲弊し、本旨（自律組織）と逆行
- ADR-0012 §5「自動化の限界線」で「**減らせる介入**」に該当（日常的な対処は Warden に委譲）
- Axiom 違反のような「明らかに止めるべき」ものまで人間判断にすると遅すぎる

### B. Mind に自己診断させる

Mind が自分で「自分が壊れた」を判定する案。

不採用理由：
- 壊れているものは自己診断できない（前提矛盾）
- ADR-0010 で「観測は外側から」と確定済（Mind は世界の一部、Warden が世界そのもの）
- Mind の自己診断を信用するなら、そもそも Judgment Pillar が要らない

### C. Mind の状態スナップショット + 巻き戻し

Mind の Mindspace を定期スナップショットし、暴走時に巻き戻す案。

不採用理由：
- 時系列分岐の複雑性爆発（どの時点に戻すか / Dispatch 履歴との整合性 / 他 Mind との状態整合性）
- ADR-0010 「Mind の死を受け入れる」と矛盾
- ai-org-os の本旨「思考の集合体は入れ替わる」と整合しない（同じ Mind を維持することへの執着）
- 実装コスト vs 得られる安全性が見合わない

### D. Axiom 違反でも warning だけで継続

違反検出しても警告だけで Mind を生かす案。

不採用理由：
- Axiom = 不変項。違反を許容したら「不変項」ではない
- ADR-0010 で「Warden は機能の集合体、Axiom を enforce する」と確定済
- 警告だけだと Mind が同じ違反を繰り返す（学習も改善もしない）

### E. 「失敗カテゴリ」を分けず一律対処

F1 / F2 / F3 / F4 を全部同じパスで処理する案。

不採用理由：
- F4（Realm 系異常）は Realm 内から検知できない（Warden 自身が落ちている可能性）
- F3（Pillar 系異常）は Warden の循環参照リスクが高い（Judgment Pillar 自身が壊れたら Judgment Pillar に判断させられない）
- カテゴリ別の対処層分離が安全性の核

## 関連

- [ADR-0008](0008-nexus-identity-binding.md) — Conduit Pillar の identity binding（レイヤー 2 の実装根拠）
- [ADR-0010](0010-observation-philosophy-and-warden-as-collective.md) §3 — Mind の死の受容、観測は外側から
- [ADR-0011](0011-warden-claude-naming-and-separation.md) — Pillar 編集不可（F2 Axiom 違反の主要ケース）
- [ADR-0012](0012-human-position-outside-realm.md) §2 責務 5 — 致命的失敗時の人間介入、本 ADR §5 の前提
- [ADR-0009](0009-relationship-with-bash-editor-and-claude-team.md) — claude-team PreToolUse hook 流用方針（レイヤー 1 の実装根拠）
- Issue #38（Phase 5a-3: Judgment Pillar）— 本 ADR の §1 / §3 / §6 を実装
- Issue #43（Observation v0.2-v1.0）— レイヤー 3 の異常検知パターン拡張
- Issue #47（Discussion F）— 本 ADR の起票元
