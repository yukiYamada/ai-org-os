# ADR-0017: Warden 監視と「ジョブの監視」を混同しない（責務の二層分離）

> 想定読者:
> - Conductor Pillar / Judgment Pillar の挙動を拡張するメンテナ
> - 「Mind が動かないとき、誰がそれを判定するのか?」を設計する立場
> - guildmaster / 進捗管理 Persona を設計する人
> - Phase 5b 以降の orchestration を設計する人

## Status

**Accepted** — 2026-05-24

## Context（背景）

Phase 5b-1 (#71) で Conductor Pillar (Warden の心拍) が動き始めた直後、Phase 5b-2 の設計討論で実装担当 (筆者) が以下を提案した：

- 「Conductor が Issue を **claim** する」
- 「Conductor が Mind の **作業完了を Observation で判定** して archive する」
- 「Mind の **進捗を Conductor が監視** する」

operator から **「Warden の MCP ならまだしも、Mind の作業としての監視は Mind がやる (という風に組織やルールを構築する) じゃない?」** という指摘で、これが **責務混同** であることが顕在化した。

この混同を ADR で固定しないと:

- Phase 5b-2 以降の orchestration が「Warden が個別ジョブを仕切る」方向に肥大化する
- Mind 側 (Persona / Dispatch) で組織を構築するという ai-org-os の本旨が薄れる
- ADR-0010 §4「観測の 2 種類」が抽象論として残り、実装に落ちない

### 関連する既決事項

- **ADR-0001**: ai-org-os は「開発組織の不変項（公理系）を定義するフレームワーク」。組織のルールは思考の集合で構築する
- **ADR-0010 §4**: 観測は 2 種類 (Warden の自己観測 / Mind の Axiom 制約観測)
- **ADR-0010 §5**: Warden は機能の集合体、Judgment は呼び出し駆動・決定論的
- **ADR-0013 §1**: 失敗カテゴリ (F1〜F4)。F1 = Mind 振る舞い系（無限ループ / リソース食い等）は Warden 判定対象
- **ADR-0015**: Persona 進化戦略。新 Persona は必要性ベース、人間オーソリ

## Decision（決定）

### 1. 監視を「2 つの層」に明確に分離する

| 層 | 担当 | 監視対象 | 判定軸 |
|---|---|---|---|
| **A. Warden 監視** | Pillar 群 (Conductor / Judgment / Observation) | 世界の維持 | Axiom 違反 / リソース枯渇 / failsafe |
| **B. ジョブ監視** | Mind の集合（組織） | 個別の仕事 | 完了 / 失敗 / 引継ぎ |

**A と B は混同しない**。A が B に踏み込むと「Warden が個別ジョブを仕切る」状態になり、組織を Mind の集合で構築するという ai-org-os の本旨に反する。

### 2. Warden 監視 (層 A) の責務範囲

Warden は以下のみを見る：

| 観点 | 例 |
|---|---|
| **Axiom 違反** | 他 Mindspace への書き込み、Pillar 改ざん、なりすまし (ADR-0013 §1 F2) |
| **リソース** | Mind プロセス数、Mindspace 総容量、Conduit storage 容量 |
| **failsafe** | Pillar 自体の停止、Realm 外部依存全断 (ADR-0012 §2 責務 5 / ADR-0013 §1 F3-F4) |
| **環境提供の完了** | Mind が spawn された / Mindspace が作られた / Nexus が立っている |
| **観測公開** | Mind が自身の情報を観測するための API (Axiom 制約付き) を提供する |

Warden は **「Inbox に何件溜まっているか」「Mind が `stale` カテゴリに居る」を観測** はするが、**それに対する「処置」は層 B (Mind の組織) に任せる**。

### 3. ジョブ監視 (層 B) の責務範囲

「個別の仕事をどう進めるか / 完了したか / 誰が次にやるか」は **Mind 同士の運営** で解決する：

| ケース | 解決の主体 |
|---|---|
| Issue を取り込む | 該当 Persona の Mind が `claim_issue` MCP tool で取りに行く |
| 進捗の追跡 | 仕事を担当する Mind が Dispatch で報告、他 Mind が読む |
| 完了の宣言 | 担当 Mind が Dispatch で「完了」を Warden または guildmaster 役の Mind に通知 |
| 引継ぎ | Mind A が別 Mind B に Dispatch で要件を渡す |
| 進捗管理 | **guildmaster Persona** (将来追加候補) の Mind が他 Mind の Dispatch を観察して全体調整 |

**進捗管理 Persona** (e.g., `guildmaster.md`) を Mind として spawn することで、組織レベルの監視が Mind 圏内で完結する。これは ADR-0015 §2 「Persona 追加は必要性ベース」のルートで導入する。

### 4. Conductor (Warden の心拍) は層 A に留まる

Phase 5b-1 で導入した Conductor の責務範囲を **層 A 限定** で固定する：

| やる (層 A) | やらない (層 B、Mind の責務) |
|---|---|
| Inbox の堆積件数を観測 | Issue を claim する |
| snapshot を撮る | Mind の作業状況を判定する |
| Judgment Claude で **Axiom 違反 / failsafe** を判定 | Mind の **ジョブ完了** を判定する |
| Pillar 異常を検知して人間に通知 | 個別 Issue の archive 判断 |
| Mind が exceed-limit したら kill | Mind の「もう仕事が無い」を判定して kill |

Conductor の現状実装（Issue 数を pending として記録する）はこの線引きの内側なので変更不要。

### 5. Mind 側に「自分の仕事を取りに行く」経路を提供する (Phase 5b-2)

層 B が機能するためには Mind が自分で Inbox にアクセスできる必要がある：

- **Conduit Pillar の MCP tool 拡張**: `read_pending_issues()` / `claim_issue(issue_id)` を Mind に提供する
- **identity binding (ADR-0008)** で発信元 Mind を確認し、claim 結果が Mind 識別子付きで archive 側に残る
- Mind は自分の Persona に合った Issue だけを claim するロジックを **Persona 内で定義** する (層 B の典型例)

これが Phase 5b-2 の中核スコープになる。Conductor の改修は不要 (Phase 5b-1 のままで層 A としては足りる)。

### 6. 「Mind が消える / 動かない」の判定主体

これは **層をまたぐ判定** になりがちなので明確化：

| シナリオ | 判定主体 |
|---|---|
| Mind プロセスが死んでいる (mind-loop.sh が停止) | 層 A: Warden (Observation で last_activity_epoch が古い) |
| Mind が `stale` カテゴリで放置 | **層 B**: 他 Mind が Dispatch で「生きてる?」と尋ねる、または guildmaster Mind が判定 |
| Mind が Axiom 違反 (e.g., 他 Mindspace 書込試行) | 層 A: Judgment が判定 → Quarantine / Kill (ADR-0013 §3) |
| Mind が仕事に飽きて何もしない | **層 B**: 組織として運営判断（人間に上げる、別 Mind に再割当、Persona 見直し 等） |

**「動いてない」と「働いていない」は別**。前者は層 A、後者は層 B。

## Consequences（影響）

### 利点

1. **Phase 5b-2 のスコープが小さく明確化**: 「Mind に Inbox MCP tool を渡す」だけになり、Conductor 改修は不要
2. **ai-org-os の本旨が実装に乗る**: 組織は Mind の集合で構築する、Warden は環境を維持するだけ
3. **将来の Persona 追加の方向性が示せる**: guildmaster / retrospector のような「組織運営 Persona」が ADR-0015 ルートで導入可能
4. **Warden / Conductor の肥大化を防ぐ**: 「個別ジョブの世話」が紛れ込まないので Pillar 数の爆発を回避できる
5. **層 A の判定が単純化される**: Judgment Pillar の VALID_ACTIONS は Axiom / failsafe 系のみ、ジョブ完了系を含めない

### 不利益 / リスク

1. **Mind 側に責任が増える**: 「誰が claim するか」「いつ完了とするか」を Persona / Dispatch で表現する必要があり、Persona の設計負荷が上がる
2. **guildmaster Persona の未実装**: 進捗管理を担う Mind が居ない初期は、人間が手で監督する必要がある（ADR-0012 §4 「現状運用と最終形のギャップ」と同じ構造）
3. **「Mind 動いてないが仕事もしてない」状態の発見が遅れる可能性**: 層 B が育つまでは layer A が `stale` を見るだけ。人間運用者が観測 → 介入の経路が初期は必要
4. **層境界の曖昧ケースが残る**: Mind が「異常に多くの Dispatch を送る」場合、層 A (リソース) か層 B (ジョブの暴走) か判定が分かれる。今後 ADR-0013 §1 F1 系で具体化する

### 派生する Issue / 後続作業

- **Phase 5b-2 (TBD issue)**: Conduit Pillar に `read_pending_issues` / `claim_issue` MCP tool を追加。Mind が自分で Inbox を取り込めるように
- **guildmaster Persona の追加** (ADR-0015 §2 ルート): 必要性が実例で示された段階で
- **Judgment Pillar の VALID_ACTIONS 見直し**: `investigate` / `notify-human` が「ジョブ系」と「Axiom 系」を混在させていないか再確認 (本 ADR の §2-4 を踏まえて)
- **observe.py --realm の表示の絞り込み**: Conductor cycle status に「ジョブ系」情報が混じってないか確認
- **ADR-0013 §1 F1 (Mind 振る舞い系) の具体化**: リソース枯渇とジョブ暴走の境界

## 代替案（不採用）

### A. Warden が Issue を claim し、Mind に手渡しする

「Warden 側で Issue を整理 → 適切な Mind に Dispatch で渡す」案。

不採用理由:
- Warden が「どの Mind にどの Issue を渡すか」を判断する = 組織のルールを Warden に内包させる
- 組織は Mind の集合で構築する (ADR-0001) という本旨に反する
- Persona / Dispatch で表現できる協調を、Warden 内部に押し込めることになる
- 「Warden が万能 orchestrator になる」失敗パターン（ADR-0010 §5「Warden は機能の集合体」と矛盾）

### B. Conductor が Mind の作業完了を Observation で判定する

snapshot の差分 / Dispatch 数 / mtime から「この Mind は仕事を終えた」と Conductor が判定する案。

不採用理由:
- 「動いている / 動いていない」は層 A で判定できるが、「働いている / 働いていない」は **判定不可能** (Mind の内部状態は外から見えない、ADR-0010 §4 Mindspace 不可侵)
- 完了は Mind 自身が宣言するもの (Dispatch で報告) という設計の方が情報量が多く正確
- 観測 (層 A) を判定 (層 B) に流用すると、誤検知時のリカバリが面倒（Mind が「まだ仕事中」なのに kill される等）

### C. 層 A / 層 B を統合し、すべて Warden に持たせる

「シンプルさのため Warden に全部やらせる」案。

不採用理由:
- 組織の柔軟性 (Persona の自由度) を失う
- 「ai-org-os = 動的な思考の集合」が「ai-org-os = Warden が仕切る固定 orchestrator」に退化する
- 層 B (Mind の組織化) を ai-org-os の付加価値として失う

### D. ADR 化せず暗黙運用

設計討論で「混同しないように」と口頭合意するだけで明文化しない案。

不採用理由:
- Phase 5b-2 / 5b-3 / 6 と進むたびに同じ混同が再発する (Phase 5b-2 設計開始 5 分後に筆者が踏んだのが好例)
- 新規メンテナが現れたら同じ罠を踏む
- 「Conductor が Issue を claim するの自然じゃない?」という素朴な発想は **誰でも持つ**ので、ADR で明示的に却下する必要がある

## 関連

- [ADR-0001](0001-ai-org-os-as-invariant-framework.md) — 組織は思考の集合で構築する（本 ADR の根拠）
- [ADR-0002](0002-vocabulary-and-meta-meta-structure.md) — Mind / Warden / Guild の定義
- [ADR-0010](0010-observation-philosophy-and-warden-as-collective.md) §4 / §5 — 観測の 2 種類 / Warden = 機能集合体
- [ADR-0011](0011-warden-claude-naming-and-separation.md) — Pillar の編集不可、本 ADR で Pillar 責務範囲を更に絞る
- [ADR-0013](0013-failure-handling-and-failsafe.md) §1 / §3 — 失敗カテゴリと対処、本 ADR で「ジョブ完了」を §1 から明示的に除外
- [ADR-0015](0015-persona-evolution-strategy.md) §2 — guildmaster 等の進捗管理 Persona の追加ルート
- [ADR-0016](0016-mind-auth-and-host-container-boundary.md) — Container/ ホスト境界 (Mind の動作経路)
- Issue #71 (Phase 5b-1) — Conductor 実装、本 ADR で責務範囲が確定
- Phase 5b-2 (TBD) — Conduit Pillar に Mind 向け Inbox MCP tool を追加（本 ADR §5）
