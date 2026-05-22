# CONTRIBUTING

> 想定読者: ai-org-os のコア規約（L2）またはリファレンス実装（L1 候補）へ変更を加えようとするメンテナ・コントリビューター（AI / 人間問わず）。

本プロジェクトは現在 **experimental / private-first** です。

## 現在の貢献方針

- まずは組織運営構造（Markdown）の明確化を優先
- 大規模実装より、運用可能な最小変更を歓迎
- 変更時は、どの運用課題を解決するかを明記

## 変更前チェックリスト

変更を始める前に、以下を自答してください。1つでも No なら、まずビジョン側 or 設計側を見直すこと。

- [ ] `docs/product_vision.md` の3軸（Build / Maintain / Share）のいずれかに寄与しているか？
- [ ] 想定読者を変更対象ドキュメントの冒頭に明示したか？
- [ ] L1（バンドル）/ L2（コア規約）/ L3（学習履歴）のどこに置くべきか判断できているか？
- [ ] 1目的 = 1PR を守っているか？（複数目的が混在していないか）

## 変更提案の基本

1. 対象ファイルを最小化する
2. 変更理由を短く記載する
3. 意思決定がある場合は `teams/*/memory/decisions.md` に残す
4. ルール変更時は影響範囲（org / team / bundle）を記載

## 注意

- この段階では公開コントリビューションフローは未整備です。
- 正式な開発規約は今後の運用で確定します。


## Guardrails強制（Git Hook）

Guardrailsの実効性を上げるため、ローカルHookを利用します。

- 初回設定: `git config core.hooksPath .githooks`
- 詳細: `docs_guardrails_hooks.md`

---

関連: [`docs/product_vision.md`](docs/product_vision.md)
