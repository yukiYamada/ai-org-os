# Release Planning: v0.3 (Minimum Viable Release)

> 想定読者: Issue 投入オペレータ、進捗を追う Planner / Reviewer。
>
> このファイルは GitHub Issue 群の SSOT。各 Issue の修正・追加はまずここで行い、その後 gh で同期する。

## 投入ルール
- 各 Issue は `### [TAG] タイトル` 形式。
- メタ情報は ```meta``` コードブロックに記述（key: value 形式）。
- 本文は ```body``` コードブロックに記述（マークダウン）。
- 投入順序は本ファイルの並び順を守ること（番号順）。
- `labels` は GitHub Labels の正式名（コロン込み）を使用する。
- `milestone` は `v0.3 (Minimum Viable Release)` / `v1.0 (External Adoption Baseline)` / `Recurring` のいずれかを正確に書く。

---

## v0.3 DoD Issues（必須、priority:p0）

### [L1-D1] L1 バンドル v0.3 の自己適用検証

```meta
milestone: v0.3 (Minimum Viable Release)
labels: priority:p0, type:dod, track:l1-bundle, axis:share, axis:build
```

```body
## 目的 / Why
docs/release_criteria.md の **L1-D1**: 「L1 バンドル v0.3 の自己適用検証」を達成する。

リリース判定のためには、仮想ターゲットプロジェクトへの install を 1 回実施し、`install.md` / `customize.md` に検証フィードバックを反映する必要がある。

## やること
- 仮想ターゲット（別ディレクトリ or 別ブランチ）を 1 つ作成する
- `L1_product-os-bundles/web-service-team-bundle-v0/install.md` の 5 ステップを実行する
- 各ステップで詰まった点・曖昧だった点をメモする
- フィードバックを `install.md` / `customize.md` に反映する PR を作る
- 検証レポートを `projects/ai-org-os/reports/` に 1 ファイル残す

## 受け入れ条件 (Acceptance Criteria)
- [ ] 仮想ターゲットでの install 完了
- [ ] `install.md` / `customize.md` にフィードバック反映 PR がマージ済み
- [ ] 検証レポート `projects/ai-org-os/reports/YYYY-MM-DD_v0.3_install_validation.md` が存在

## 関連
- DoD: docs/release_criteria.md (L1-D1)
- Vision: docs/product_vision.md（Build / Share 軸）
- 関連バンドル: L1_product-os-bundles/web-service-team-bundle-v0/
```

---

### [L1-D2] 自立稼働判定チェックリスト作成

```meta
milestone: v0.3 (Minimum Viable Release)
labels: priority:p0, type:dod, track:l1-bundle, axis:share
```

```body
## 目的 / Why
docs/release_criteria.md の **L1-D2**: 受領者が「これで自社チームとして回せる」を 10 項目以内で自答できる `self-check.md` をバンドル内に追加する。

これが無いと、受領者は「導入は終わったが運用に乗せられるか」を判定できず、v0.3 の "最低限のリリース" 要件を満たさない。

## やること
- `L1_product-os-bundles/web-service-team-bundle-v0/self-check.md` を新規作成
- Build / Maintain / Share の 3 軸を満遍なくカバーする 10 項目以内のチェックリストにする
- 各項目は YES/NO で答えられる粒度（例: 「Guardrails G-01〜G-08 を自社語彙に置換したか？」）
- バンドル README から self-check.md へ導線を張る

## 受け入れ条件 (Acceptance Criteria)
- [ ] `L1_product-os-bundles/web-service-team-bundle-v0/self-check.md` が存在
- [ ] 項目数 10 以内、すべて YES/NO で答えられる
- [ ] バンドル README / install.md から self-check.md への参照リンクあり

## 関連
- DoD: docs/release_criteria.md (L1-D2)
- Vision: docs/product_vision.md（Share 軸）
```

---

### [L1-D3] バンドル移植後の完結性確保

```meta
milestone: v0.3 (Minimum Viable Release)
labels: priority:p0, type:dod, track:l1-bundle, axis:share
```

```body
## 目的 / Why
docs/release_criteria.md の **L1-D3**: バンドル移植後に外部リポ参照を必要としない状態を作る。

現状、`Product Vision` 等への参照が外部リポ前提になっている可能性があり、move 後に「リンク切れ＝運用不能」を招く。

## やること
- バンドル内の全マークダウンを grep し、`../../docs/` / `../../org/` 等の外部相対参照を列挙
- 必須参照（Vision, charter 等）は同梱するか、`docs/embedded/` 配下にコピー
- バンドル内に「参照ルール」を明文化（同梱 / コピー / リンク禁止の方針）
- 移植テストとして、バンドルだけを別ディレクトリへコピーしてリンク切れを確認

## 受け入れ条件 (Acceptance Criteria)
- [ ] バンドル外への相対参照が 0 件、または明示的に許可されたもののみ
- [ ] バンドル内に参照ルールを記述したファイルが存在（README or customize.md 内）
- [ ] 別ディレクトリへのコピーテストでリンク切れ 0 件

## 関連
- DoD: docs/release_criteria.md (L1-D3)
- Vision: docs/product_vision.md（Share 軸）
- 関連: L1-D1（同時に検証可能）
```

---

### [OBS-D1] 週次 Metrics 計測実績 1 週分以上

```meta
milestone: v0.3 (Minimum Viable Release)
labels: priority:p0, type:dod, track:l3-learning, axis:maintain
```

```body
## 目的 / Why
docs/release_criteria.md の **OBS-D1**: `projects/ai-org-os/specs/metrics.md` の 5 指標を 1 週分以上計測し、取得不能指標を明示する。

計測実績が無いと「自己改善ループが回っている」根拠を示せず、Maintain 軸の DoD が成立しない。

## やること
- `projects/ai-org-os/specs/metrics.md` の 5 指標を確認
- 1 週分の値を `teams/web-service-team/memory/learnings.md` に記録（Metrics Weekly Log）
- 取得不能だった指標について「なぜ取れないか / 代替案」を明示
- 翌週以降の継続記録方法を 1 行で決める

## 受け入れ条件 (Acceptance Criteria)
- [ ] `teams/web-service-team/memory/learnings.md` に Metrics Weekly Log が 1 件以上
- [ ] 5 指標すべてに対し「値」または「取得不能の理由」が記録されている
- [ ] 翌週以降の継続方法が決まっている（担当 / 頻度 / 保存先）

## 関連
- DoD: docs/release_criteria.md (OBS-D1)
- 関連バックログ: backlog.md `Metrics-Weekly-1`
- Vision: docs/product_vision.md（Maintain 軸）
```

---

### [QA-D1] pre-commit hook を install 手順に組込

```meta
milestone: v0.3 (Minimum Viable Release)
labels: priority:p0, type:dod, track:process, axis:maintain
```

```body
## 目的 / Why
docs/release_criteria.md の **QA-D1**: `.githooks/pre-commit` の有効化を `install.md` の必須ステップに含め、想定読者・Vision 参照の警告が機能する状態を作る。

これが無いと受領者が hook を有効化し忘れ、ドキュメント衛生が初日から崩れる。

## やること
- `L1_product-os-bundles/web-service-team-bundle-v0/install.md` に `git config core.hooksPath .githooks` ステップを追加
- 新規 clone 想定で hook が動くことを確認（1 commit テスト）
- hook がブロックする条件（想定読者欠落 / Vision リンク欠落 等）を install.md に短く記載
- スキップ手順（緊急時の `--no-verify` 運用）は警告付きで記載

## 受け入れ条件 (Acceptance Criteria)
- [ ] `install.md` に hook 有効化ステップが必須として記載
- [ ] テストコミットで hook が想定通り発火することを確認
- [ ] スキップ運用の警告文が記載

## 関連
- DoD: docs/release_criteria.md (QA-D1)
- 関連ファイル: .githooks/pre-commit
- Vision: docs/product_vision.md（Maintain 軸）
```

---

### [PM-D1] backlog 全項目の GitHub Issue 可視化

```meta
milestone: v0.3 (Minimum Viable Release)
labels: priority:p0, type:dod, track:process, axis:maintain
```

```body
## 目的 / Why
docs/release_criteria.md の **PM-D1**: `backlog.md` の全 `[ ]` 項目を、GitHub Issue として可視化するか、明示的に done に整理する。

このファイル（release_planning_v0.3.md）の Issue 群を gh で投入する作業そのものが本タスクの中心。

## やること
- `docs/release_planning_v0.3.md`（このファイル）に列挙された 23 Issue を gh で全て作成
- 各 Issue を `v0.3 (Minimum Viable Release)` / `v1.0 (External Adoption Baseline)` / `Recurring` milestone に紐付け
- `backlog.md` の各 `[ ]` 項目に、対応 Issue 番号 or done 根拠を併記
- 未紐付け項目が 0 件であることを確認

## 受け入れ条件 (Acceptance Criteria)
- [ ] 23 Issue すべて作成済み、milestone 紐付け済み
- [ ] `backlog.md` の `[ ]` 項目すべてに Issue 番号 or done 根拠が併記
- [ ] 未紐付けの `[ ]` 項目が 0 件

## 関連
- DoD: docs/release_criteria.md (PM-D1)
- SSOT: docs/release_planning_v0.3.md
- Vision: docs/product_vision.md（Maintain 軸）
```

---

### [L3-D1] 学習ループの継続記録

```meta
milestone: v0.3 (Minimum Viable Release)
labels: priority:p0, type:dod, track:l3-learning, axis:maintain
```

```body
## 目的 / Why
docs/release_criteria.md の **L3-D1**: R-0001 以降の retrospective を 1 件以上追加し、learnings.md エントリ累計 5 件以上、起源↔バンドル乖離チェックを必須化する。

学習ループが「1 回だけ」では Maintain 軸の継続性を示せない。

## やること
- `teams/web-service-team/memory/retrospectives.md` に R-0002 以降を 1 件以上追加
- 各 retrospective で「起源↔バンドル乖離チェック」セクションを必須実施
- `teams/web-service-team/memory/learnings.md` のエントリを累計 5 件以上に増やす
- 学習エントリは再利用可能（次回のチームでも参照される粒度）であることを確認

## 受け入れ条件 (Acceptance Criteria)
- [ ] retrospective R-0002 以降が 1 件以上記録
- [ ] 各 retrospective に起源↔バンドル乖離チェック結果が記載
- [ ] learnings.md のエントリ累計 5 件以上

## 関連
- DoD: docs/release_criteria.md (L3-D1)
- 関連: backlog.md `L1-V0.2-2`（完了済）
- Vision: docs/product_vision.md（Maintain 軸）
```

---

## v0.3 supporting Issues（priority:p1）

### [L1-V0.2-3] 起源↔バンドル diff の週次手動チェック手順を docify

```meta
milestone: v0.3 (Minimum Viable Release)
labels: priority:p1, track:l1-bundle, axis:maintain
```

```body
## 目的 / Why
backlog.md `L1-V0.2-3`（R-0001 持ち越し）。retrospective 内のチェックだけでは属人化するため、独立した手順書として固定化する。

## やること
- `projects/ai-org-os/specs/` または運用 doc に「起源↔バンドル diff 週次チェック手順」を追加
- 手順は 5 ステップ以内（diff 取得 / 差分分類 / 再スナップショット判定 / 記録先 / 担当）
- retrospective テンプレから本手順書へのリンクを張る

## 受け入れ条件 (Acceptance Criteria)
- [ ] 手順書ファイルが存在し、5 ステップ以内で記述
- [ ] retrospective テンプレからリンク
- [ ] 1 回試走して所要時間を記録

## 関連
- 起票: backlog.md `L1-V0.2-3`
- 関連: D-0003（snapshot model）
- Vision: docs/product_vision.md（Maintain 軸）
```

---

### [DocHygiene-1] 想定読者・Vision リンク欠落の grep スクリプト試作

```meta
milestone: v0.3 (Minimum Viable Release)
labels: priority:p1, track:process, axis:maintain
```

```body
## 目的 / Why
backlog.md `DocHygiene-1`（R-0001 持ち越し）。pre-commit hook（QA-D1）の補完として、リポジトリ全体を週次でスキャンする最小スクリプトを試作する。

## やること
- `.githooks/` または `projects/ai-org-os/scripts/` 配下に grep ベースのスクリプトを 1 本作成
- 検出対象: 「想定読者:」行の欠落 / Vision 参照リンクの欠落
- 出力は警告のみ（ブロックしない）
- 週次運用のトリガー（手動 / cron / CI どれにするか）を 1 行決める

## 受け入れ条件 (Acceptance Criteria)
- [ ] スクリプトが存在し、サンプル実行で欠落を検出
- [ ] 運用トリガーが決まっている
- [ ] 偽陽性が許容範囲内（手動レビューで判断可能）

## 関連
- 起票: backlog.md `DocHygiene-1`
- 関連: QA-D1（pre-commit hook）
- Vision: docs/product_vision.md（Maintain 軸）
```

---

### [Issue6] Information Architecture を運用開始

```meta
milestone: v0.3 (Minimum Viable Release)
labels: priority:p1, track:process, axis:maintain
```

```body
## 目的 / Why
backlog.md `Issue 6`: Information Architecture（Starter / Governance / Runtime Memory 分離）を運用開始する。

L1/L2/L3 の分離方針は決まっているが、新規ファイル配置時のルールが運用化されていない。

## やること
- `docs/information_architecture.md` を参照しながら、Starter / Governance / Runtime Memory の境界を運用ルールとして明文化
- 新規ファイル追加時の判断フロー（3 問程度）を作る
- 1 週間運用し、配置違反件数と移動コストを Recurring レビューで確認（[Recur-IA] と連動）

## 受け入れ条件 (Acceptance Criteria)
- [ ] 判断フローが docs 内に存在
- [ ] 1 週間運用してレビュー実施
- [ ] 配置違反件数 / 移動コストが記録されている

## 関連
- 起票: backlog.md `Issue 6`
- 関連: docs/information_architecture.md, [Recur-IA]
- Vision: docs/product_vision.md（Maintain 軸）
```

---

### [Def-DecisionLog] Decision log format の正式定義

```meta
milestone: v0.3 (Minimum Viable Release)
labels: priority:p1, track:docs, axis:maintain
```

```body
## 目的 / Why
backlog.md `Define decision log format`。現状 D-XXXX 形式で運用中だが、フォーマット仕様が文章化されていない。受領者が同じ運用を再現できるよう仕様化する。

## やること
- 現行 `teams/web-service-team/memory/decisions.md` の運用実態を観察
- 必須項目（背景 / 選択肢 / 決定 / 影響）を仕様としてテンプレ化
- ID 採番ルール（D-XXXX）と保管場所を明記
- バンドルテンプレ（`templates/team/memory/decisions.md` 等）に反映

## 受け入れ条件 (Acceptance Criteria)
- [ ] フォーマット仕様が docs / templates のいずれかに存在
- [ ] サンプル decision が 1 件含まれる
- [ ] バンドル側テンプレが仕様準拠

## 関連
- 起票: backlog.md `Define decision log format`
- Vision: docs/product_vision.md（Maintain 軸）
```

---

### [Def-Retro] Retrospective format テンプレ整備

```meta
milestone: v0.3 (Minimum Viable Release)
labels: priority:p1, track:docs, axis:maintain
```

```body
## 目的 / Why
backlog.md `Define retrospective format`。R-0001 で運用開始しているが、追加項目検討と R-XXXX 形式の仕様化が未着手。

## やること
- 現行 `templates/team/memory/retrospectives.md` を確認
- 追加項目候補（例: メトリクススナップショット / 起源↔バンドル乖離チェック / 学習エントリへの昇格判定）を検討
- 採用項目を仕様として明記、ID 採番ルール（R-XXXX）も明文化
- バンドル側テンプレに反映

## 受け入れ条件 (Acceptance Criteria)
- [ ] retrospective format 仕様が docs / templates に存在
- [ ] 必須セクションが列挙されている
- [ ] バンドルテンプレが仕様準拠

## 関連
- 起票: backlog.md `Define retrospective format`
- 関連: L3-D1, L1-V0.2-2
- Vision: docs/product_vision.md（Maintain 軸）
```

---

### [Def-TeamRuleEvolution] Team-local rules の進化プロセス定義

```meta
milestone: v0.3 (Minimum Viable Release)
labels: priority:p1, track:docs, axis:maintain
```

```body
## 目的 / Why
backlog.md `Define how team-local rules improve over time`。retrospective → rules.md 改定の手順が暗黙知のため、受領者が再現できない。

## やること
- retrospective から rules.md 改定までのフローを 3〜5 ステップで定義
- 改定提案 → レビュー → 採用 → 反映 → decisions.md 記録の流れを明文化
- 影響範囲（バンドルへの再スナップショットが必要か等）も判断基準として記載
- バンドル内（customize.md 等）に運用手順として収録

## 受け入れ条件 (Acceptance Criteria)
- [ ] 進化プロセスのフロー図 or 手順書が存在
- [ ] decisions.md への記録ルールが含まれる
- [ ] バンドル内に収録

## 関連
- 起票: backlog.md `Define how team-local rules improve over time`
- Vision: docs/product_vision.md（Maintain 軸）
```

---

### [Def-TeamExtraction] Team extraction criteria 定義

```meta
milestone: v0.3 (Minimum Viable Release)
labels: priority:p1, track:docs, axis:share
```

```body
## 目的 / Why
backlog.md `Define criteria for extracting/transferring a team`。チームを L1 バンドルとして切り出す基準が未定義のため、第二弾バンドル選定（[Bundle2-Select]）の判断ができない。

## やること
- バンドル化に必要な最低条件を列挙（成熟度 / ドキュメント網羅率 / 学習エントリ件数 等）
- 抽出フロー（snapshot → 完結性確認 → self-check 通過）を 5 ステップで定義
- 第二弾バンドル候補に適用できる粒度で書く
- `docs/` または `projects/ai-org-os/specs/` に配置

## 受け入れ条件 (Acceptance Criteria)
- [ ] 抽出基準と抽出フローが文書化
- [ ] チェック項目が 5〜10 個程度
- [ ] [Bundle2-Select] で使える状態

## 関連
- 起票: backlog.md `Define criteria for extracting/transferring a team`
- 関連: [Bundle2-Select]
- Vision: docs/product_vision.md（Share 軸）
```

---

### [Def-FirstExecFeature] First executable feature の決定

```meta
milestone: v0.3 (Minimum Viable Release)
labels: priority:p1, track:docs, axis:build
```

```body
## 目的 / Why
backlog.md `Decide the first executable feature after the documentation structure is stable`。documentation-first を超えた次の実行可能機能を決める。

## やること
- 現状の成熟度（v0.3 DoD 達成度）を踏まえ、次の実行可能機能候補を 3 つ列挙
- ICE スコア（Impact / Confidence / Ease）で評価
- 選定理由を `teams/web-service-team/memory/decisions.md` に D-XXXX として記録
- 採用候補は v1.0 milestone の Issue として別途起票

## 受け入れ条件 (Acceptance Criteria)
- [ ] 候補 3 件以上が ICE 評価付きで提示
- [ ] decisions.md に選定理由が記録
- [ ] 採用案が v1.0 Issue として登録 or 明示的に保留

## 関連
- 起票: backlog.md `Decide the first executable feature ...`
- Vision: docs/product_vision.md（Build 軸）
```

---

## v1.0 Issues（milestone=v1.0, priority:p1）

### [L1-V1.0] L1 v1.0: 外部プロジェクトへの導入実績 1 件取得

```meta
milestone: v1.0 (External Adoption Baseline)
labels: priority:p1, track:l1-bundle, axis:share
```

```body
## 目的 / Why
docs/release_criteria.md v1.0 条件 1: 外部プロジェクトへの導入実績 1 件以上（PR or 導入レポート）を取得する。

v0.3 の自己適用検証だけでは「他者でも回る」根拠が弱い。

## やること
- 導入候補プロジェクト / チームを 2〜3 件リストアップ
- 1 件への導入を実行（PR / 導入レポートいずれか）
- 導入時のフィードバックを `projects/ai-org-os/reports/` に記録
- バンドル側の改善点を Issue として起票

## 受け入れ条件 (Acceptance Criteria)
- [ ] 外部 1 件への導入完了（PR or レポートのいずれか）
- [ ] フィードバックレポートが存在
- [ ] 改善点 Issue が 0 件以上起票

## 関連
- DoD: docs/release_criteria.md (v1.0 条件 1)
- 関連: L1-D1（自己適用検証の延長）
- Vision: docs/product_vision.md（Share 軸）
```

---

### [Bundle2-Select] 第二弾バンドル候補選定

```meta
milestone: v1.0 (External Adoption Baseline)
labels: priority:p1, track:l1-bundle, axis:share
```

```body
## 目的 / Why
docs/release_criteria.md v1.0 条件 3: 第二弾バンドル候補の選定理由を `decisions.md` に記録する。

L1 が 1 種類だけでは「移植可能性」を示せない。

## やること
- バンドル候補を 3 件以上列挙（例: data-team / platform-team / agency-internal-team 等）
- [Def-TeamExtraction] の抽出基準で各候補を評価
- ICE スコアで 1 案を選定
- 選定理由を `teams/web-service-team/memory/decisions.md` に D-XXXX として記録

## 受け入れ条件 (Acceptance Criteria)
- [ ] 候補 3 件以上が ICE 評価付きで提示
- [ ] 選定 1 案が決定
- [ ] decisions.md に選定理由が記録

## 関連
- DoD: docs/release_criteria.md (v1.0 条件 3)
- 関連: [Def-TeamExtraction]
- Vision: docs/product_vision.md（Share 軸）
```

---

### [Template-V2] テンプレ v2: 記入済み事例つきへ昇格

```meta
milestone: v1.0 (External Adoption Baseline)
labels: priority:p1, track:l1-bundle, axis:share, axis:build
```

```body
## 目的 / Why
受領者が空テンプレから書き始めるのは認知負荷が高い。記入済み事例を 1 件以上同梱した v2 テンプレへ昇格させる。

## やること
- 現行 `templates/` 配下の各ファイルに対し、記入済み事例を 1 件追加（コメント or サンプルセクション）
- 事例は web-service-team の実運用から抽出
- 記入済み事例と空テンプレの切り替え方法を customize.md に記載
- バンドル install.md にもサンプル参照導線を張る

## 受け入れ条件 (Acceptance Criteria)
- [ ] 主要テンプレ（mission / rules / roles / workflow / memory）すべてに記入済み事例
- [ ] customize.md に空テンプレへの戻し方が記載
- [ ] install.md からサンプル参照リンク

## 関連
- 関連: L1-D1, L1-D2
- Vision: docs/product_vision.md（Share / Build 軸）
```

---

## Recurring Issues（milestone=Recurring, priority:p1, type:recurring）

### [Recur-IA] IA 運用 1 週レビュー

```meta
milestone: Recurring
labels: priority:p1, type:recurring, track:process, axis:maintain
```

```body
## 目的 / Why
backlog.md In Progress `IA 運用 1 週レビュー`。配置違反件数 / 移動コストを継続観測する。

## やること
- 直近 1 週間の新規ファイル配置を確認
- 配置違反（Starter / Governance / Runtime Memory の境界違反）を集計
- 移動が必要だった場合のコスト（修正ファイル数 / リンク影響）を記録
- 判断フロー（[Issue6]）の改定提案があれば retrospective に起票

## 受け入れ条件 (Acceptance Criteria)
- [ ] 配置違反件数が記録
- [ ] 移動コストが記録
- [ ] 改善提案の有無を判定

## 関連
- 起票: backlog.md In Progress
- 関連: [Issue6], docs/information_architecture.md
- Vision: docs/product_vision.md（Maintain 軸）
```

---

### [Recur-Guardrails] Guardrails 運用 1 週レビュー

```meta
milestone: Recurring
labels: priority:p1, type:recurring, track:process, axis:maintain
```

```body
## 目的 / Why
backlog.md In Progress `Guardrails 運用 1 週レビュー`。G-01〜G-08 / A-01〜A-04 の調整を継続的に行う。

## やること
- 直近 1 週間で Guardrails が機能した / 機能しなかった事例を収集
- 過剰ブロック / すり抜けがあれば原因を分析
- G-XX / A-XX のうち調整候補を列挙
- 改定案を decisions.md に下書き

## 受け入れ条件 (Acceptance Criteria)
- [ ] 事例（機能 / 不機能）が記録
- [ ] 調整候補が列挙
- [ ] 改定案の有無を判定

## 関連
- 起票: backlog.md In Progress
- Vision: docs/product_vision.md（Maintain 軸）
```

---

### [Recur-Roles] Roles 運用 1 週レビュー

```meta
milestone: Recurring
labels: priority:p1, type:recurring, track:process, axis:maintain
```

```body
## 目的 / Why
backlog.md In Progress `Roles 運用 1 週レビュー`。責務衝突 / ハンドオフ詰まりを継続観測する。

## やること
- 直近 1 週間で発生した責務衝突を列挙
- ハンドオフが詰まったポイント（誰から誰への引き渡しで停滞したか）を記録
- 役割定義（`teams/web-service-team/roles/`）の改定候補を判定
- 必要なら decisions.md に下書き

## 受け入れ条件 (Acceptance Criteria)
- [ ] 衝突 / 詰まり事例が記録
- [ ] 改定候補の有無を判定

## 関連
- 起票: backlog.md In Progress
- 関連: teams/web-service-team/roles/
- Vision: docs/product_vision.md（Maintain 軸）
```

---

### [Recur-Workspace] Workspace 運用 1 週レビュー

```meta
milestone: Recurring
labels: priority:p1, type:recurring, track:process, axis:maintain
```

```body
## 目的 / Why
backlog.md In Progress `Workspace 運用 1 週レビュー`。staging 経由率 / 差し戻し理由を継続観測する。

## やること
- 直近 1 週間の作業について、staging を経由した割合を集計
- 差し戻しが発生した場合の理由を分類（仕様不備 / 規約違反 / 品質不足 等）
- Workspace 運用ルールの調整候補を判定
- 必要なら改定提案を下書き

## 受け入れ条件 (Acceptance Criteria)
- [ ] staging 経由率が記録
- [ ] 差し戻し理由が分類
- [ ] 改定候補の有無を判定

## 関連
- 起票: backlog.md In Progress
- Vision: docs/product_vision.md（Maintain 軸）
```

---

### [Recur-Research] Research Loop 運用 1 週レビュー

```meta
milestone: Recurring
labels: priority:p1, type:recurring, track:process, axis:maintain
```

```body
## 目的 / Why
backlog.md In Progress `Research Loop 運用 1 週レビュー`。根拠不足指摘率 / 矛盾保留件数を継続観測する。

## やること
- 直近 1 週間の意思決定で「根拠不足」と指摘された件数を集計
- 矛盾が見つかり保留扱いになった件数を集計
- Research Loop のルール（情報源優先順位 / 根拠記載必須項目）の調整候補を判定
- 必要なら改定提案を下書き

## 受け入れ条件 (Acceptance Criteria)
- [ ] 根拠不足指摘率が記録
- [ ] 矛盾保留件数が記録
- [ ] 改定候補の有無を判定

## 関連
- 起票: backlog.md In Progress
- Vision: docs/product_vision.md（Maintain 軸）
```

---

## 参考リンク

- [Product Vision](./product_vision.md)
- [Release Criteria](./release_criteria.md)
- [Roadmap](./roadmap.md)
- [Backlog](../projects/ai-org-os/backlog.md)
