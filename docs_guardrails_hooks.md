# Guardrails Hooks 導入ガイド（最小）

## 目的
Guardrails の「強制力が弱い」課題を補うため、ローカル Git Hook で最低限の自動チェックを実施する。

## 対象
- `G-05 機密情報の平文保存禁止`
- `G-08 大粒変更の一括投入禁止（警告）`

## セットアップ（3ステップ）
1. Hookパス設定
   - `git config core.hooksPath .githooks`
2. 実行権限確認
   - `chmod +x .githooks/pre-commit`
3. 動作確認
   - `git commit --allow-empty -m "hook動作確認"`

## 現在の仕様
- **ブロック**: 機密情報パターン検出時（コミット中断）
- **警告**: ステージ済み変更ファイルが4件以上
- **警告**: 新規 `.md` ドキュメントの冒頭10行に「想定読者」記載がない場合（運営原則 7. Reader-Aware Documentation）
- **警告**: `docs/product_vision.md` 変更時に `decisions.md` 更新が含まれない場合（運営原則 6. Vision-First）

## 次タスク（さらに細分化）
- [ ] H1-1: `commit-msg` hookで「1目的」チェック（例: プレフィックス規約）
- [ ] H1-2: docs変更時の必須追記（Why/Impact）をテンプレ化
- [ ] H1-3: CI側で同等チェックを再実行し、ローカル回避を補完
- [ ] H1-4: 誤検知パターンの除外リスト設計
