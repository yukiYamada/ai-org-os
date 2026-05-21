# Workflow

## 標準フロー
1. Product Owner が課題を定義（`brief.md`, `backlog.md`）
2. Architect が要件・構成を具体化（`specs/`）
3. Engineer が実装（`src/`）
4. Reviewer が品質確認（仕様適合・リスク・テスト）
5. 全ロールがボトムアップ改善提案を提出（最小変更案を含む）
6. Retrospective Facilitator が改善会を実施し、学習を記録

## 完了条件（Definition of Done）
- 要件と実装の整合が取れている
- レビューが完了している
- 重要判断が memory に記録されている
- 改善提案（採択/保留/却下）が記録されている

## Metrics Review（週次）
- 自立実行率: 追加指示なしで完了した Issue / 全完了 Issue
- 手戻り率: レビュー差し戻し Issue / 全レビュー Issue
- 承認待ち時間: 人間承認待ちの累積時間
- 提案採択率: 採択提案 / 全提案
- 学習反映率: rules/specs/backlog に反映された learning/decision / 全 learning/decision

### 運用ルール
1. 毎週末に指標を記録する。
2. 目標未達の指標は次サイクル backlog に改善タスク化する。
3. 2週連続で未達ならルール改定候補として扱う。



## 自己改善ループ（このリポジトリ自身を修正対象にする）
1. 週次で `Metrics Review` を実施し、未達指標を特定する。
2. 未達指標ごとに「症状 / 原因仮説 / 最小変更案 / 影響範囲」を `backlog` の提案として起票する。
3. Planner が提案を 30〜60分タスクへ再分解する（1タスク=1目的=1PR、変更ファイルは原則3以下）。
4. Builder が最小差分で修正し、Reviewer が Guardrails 適合を確認する。
5. Human が最終承認し、結果を `decisions.md` と `learnings.md` に記録する。
6. 次週レビューで「改善前後の指標差分」を確認し、未改善なら追加で再分解する。

### 自己改善の完了条件
- 改善タスクに対応する指標が、翌週比較で改善している。
- 改善が確認できない場合、タスクをさらに細分化して再実行している。


## Workspace分離（runtime / staging / archive）
- **runtime**: 現在有効な運用定義（通常は直接編集しない）
- **staging**: 変更作成・検証・レビューの作業領域
- **archive**: 旧版保全領域

### 運用手順（最小）
1. 変更は `staging` 相当で作成する。
2. Reviewer確認とHuman承認後に `runtime` 相当へ昇格する。
3. 置換前の定義は `archive` 相当として記録する。
