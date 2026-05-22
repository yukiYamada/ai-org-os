# Retrospectives

> 想定読者: チーム運営の改善を担う Planner / Reviewer / Retro 担当。L3（学習ループ）の起点ファイル。
> 各エントリは [Product Vision](../../../docs/product_vision.md) の3軸（Build / Maintain / Share）のどこに学習が効くかを意識して記録する。

## R-0000 (Initial)
- 日付: 2026-05-21
- Keep: 構造先行で合意形成しやすい
- Problem: 役割境界の曖昧化リスク
- Try: 各変更で責務ラベル（PO/Arch/Eng/Rev/Retro）を明記する

## R-0001: Vision 整合バッチ〜製品成熟化バッチ振り返り（2026-05-22）

### 期間
2026-05-22 単日、PR #11 / #12 / #13 の3連続バッチ

### 良かったこと（Keep）
- SSOT（`docs/product_vision.md`）を先に固定してから末端ドキュメントを整合させる順序が機能し、3軸（Build / Maintain / Share）への参照を一括で挿入できた（PR #11）。
- サブエージェント並列実行により、25 ファイル規模の Vision 整合を短時間で完了できた。
- 各 PR が単一目的を維持できた（#11: Vision 整合 / #12: L1 充填 / #13: 成熟化）。レビュー観点の混線が起きなかった。
- snapshot model（D-0003）を v0.1 収録と同時に明文化したため、二重管理の意思決定が後追いにならなかった。
- L1 v0.2 でカスタマイズマーカー（Must/Should/May）を入れた結果、受領者の判断負荷が下がる構造になった（Share 軸への寄与）。

### 課題（Problem）
- 1日で3 PR の高速回転は妥当だったが、間にユーザーレビュー時間がなく品質ゲートが薄かった。回帰検出が後段に寄った。
- D-0003 の残課題（起源↔バンドル乖離検出）が次サイクル先送りされていた（本 R-0001 と同タイミングで templates 側に最小組み込みを実施し解消）。
- L3 への学習記録（本ファイル / learnings.md）への反映が後追いになった。学習ループの「証拠」が PR 直後には残らなかった。
- L1 v0.1 で実体収録はしたが、Metrics SSOT の週次計測実績がまだゼロ。指標妥当性が未検証。
- 想定読者ラベルや Vision リンクの抜けが残るファイルがゼロかは未確認（pre-commit 警告のみで検出依存）。

### 試すこと（Try）
- 各 PR 完了直後に最小 retrospective を1〜3行で書き残す（PR description テンプレに「Keep/Problem/Try 1行ずつ」枠を追加検討）。
- 起源（`teams/`, `templates/`）とバンドル（`L1_product-os-bundles/*/`）の diff を週次で手動 grep して再スナップショット候補を検出する運用を開始。retrospective テンプレに必須項目化済。
- Metrics 週次計測を次週から開始し、指標妥当性（取り過ぎ/取らな過ぎ）を1〜2週で見直す。
- 想定読者・Vision リンクの欠落チェックを週次で簡易スキャン（grep ベース）。

### 持ち越しアクション（具体的な backlog タスク化候補）
- L1-V0.2-3 (new): 起源↔バンドル diff の週次手動チェック手順を `projects/ai-org-os/specs/` または運用 doc に追記。
- Metrics-Weekly-1 (new): 第1回 Metrics Weekly Log を翌週に記録し、5指標のうち取得不能なものを洗い出す。
- DocHygiene-1 (new): 想定読者・Vision リンクの欠落を週次で grep スキャンする最小スクリプトを試作。

### 起源↔バンドル乖離チェック（snapshot model 運用）
- 起源側（teams/, templates/）で更新があったファイル: 本 retrospective により `teams/web-service-team/memory/retrospectives.md`, `learnings.md` を更新、`templates/team/memory/retrospectives.md` にチェック項目を追加。
- 対応するバンドル側（L1_product-os-bundles/*/）との diff: memory 系は v0.1 スナップショットでは未収録のため diff 対象なし。templates の retrospective 雛形変更は次回スナップショット時に取り込み予定。
- 再スナップショット候補: No（v0.1 リリース直後、内容物の構造変更は無し）。
- 判断理由: 本サイクルの変更は L3 の運用記録および雛形拡張に限定され、v0.1 バンドルの実体ファイル群（mission/rules/roles/workflow）には影響しないため。

---
- 参照: [Product Vision](../../../docs/product_vision.md)
