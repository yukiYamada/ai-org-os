# Planner / Builder / Reviewer 契約（MVP）

## 目的
Issue 2 の最小実装として、3ロールの責務・入出力・ハンドオフ・人間最終承認点を固定する。

## 1) Planner
### 責務（1ページ以内）
- 課題を 30〜90分で終わるタスクへ分解する。
- 受け入れ条件（DoD）と開始条件（DoR）を定義する。
- 影響範囲を `org/team/project` で明記する。

### 入力
- `projects/*/brief.md`
- `projects/*/backlog.md`
- `L2_product-core-os/org/global_rules.md`

### 出力
- タスク定義（目的 / 非ゴール / DoR / DoD / 変更対象ファイル）
- 優先順位付き実行順

## 2) Builder
### 責務（1ページ以内）
- Planner の定義に沿って最小変更で実装する。
- 1目的=1PR を守り、差分を小さく維持する。
- 実施した検証結果を明示する。

### 入力
- Planner のタスク定義
- `projects/*/specs/` と `teams/*/rules.md`

### 出力
- 変更差分
- 検証ログ（実行コマンドと結果）
- 懸念点/保留事項

## 3) Reviewer
### 責務（1ページ以内）
- 仕様適合・Guardrails適合・変更粒度を確認する。
- 差し戻し条件を明示し、再作業の境界を定義する。
- マージ可否を提言し、人間承認へ引き渡す。

### 入力
- PR差分
- Planner のDoD
- Builder の検証ログ

### 出力
- レビュー結果（Approve / Request changes）
- 指摘一覧（必須修正 / 任意改善）

## ハンドオフ手順（標準）
1. Planner → Builder: タスク定義を引き渡す。
2. Builder → Reviewer: 差分と検証ログを引き渡す。
3. Reviewer → Human: マージ可否の提言を引き渡す。

## 例外時フロー
- 仕様矛盾を検知した場合: Builder は実装停止し Planner へ差し戻す。
- Guardrails衝突を検知した場合: Reviewer は即時差し戻しし human approval を要求する。

## 人間の最終承認ポイント
<!-- CUSTOMIZE: approver-role | "Human" を自社の承認者役職へ。例: Tech Lead, VP of Engineering, Product Director -->
- マージ可否: **Human が最終決定**（Reviewerは提言のみ）。
- 外部公開可否: **Human が最終決定**（公開操作前に承認必須）。

## 入出力テンプレート（最小）
### Planner 出力テンプレ
- 目的:
- 非ゴール:
- DoR:
- DoD:
- 変更対象ファイル（最大3）:
- 承認要否（A-01〜A-04）:

### Builder 出力テンプレ
- 実施内容:
- 変更ファイル:
- 検証コマンド:
- 検証結果:
- 懸念点:

### Reviewer 出力テンプレ
- 判定: Approve / Request changes
- 必須修正:
- 任意改善:
- Human承認依頼事項:

## 次タスク（さらに細分化）
- [ ] T2-1a: Planner責務を `product_owner` / `architect` 既存ロールへマッピングする。
- [ ] T2-1b: Builder責務を `engineer` ロール文書へ同期する。
- [ ] T2-1c: Reviewer責務を `reviewer` ロール文書へ同期する。
- [ ] T2-2a: テンプレートを `templates/` 配下へ移植する。
- [ ] T2-3a: 例外時フローの判断例（3ケース）を追加する。
