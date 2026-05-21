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

