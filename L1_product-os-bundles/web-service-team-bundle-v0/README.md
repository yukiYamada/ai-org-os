# web-service-team-bundle v0.1

> 想定読者: このバンドルを自社へ導入したい技術リード／テックリード。

## バンドル概要

Web サービスドメインの小規模 AI 開発チームを、自社リポジトリで立ち上げるためのリファレンス実装バンドル。`teams/web-service-team/` および `templates/` の v0.1 時点スナップショット（snapshot model）。

## 含まれるもの（v0.1）

- `mission.md`: チームのミッションと判断軸
- `rules.md`: チーム運用規約（org の global_rules を補完）
- `workflow.md`: 標準ワークフロー
- `roles/`: 役割定義 6 ファイル（product_owner / architect / engineer / reviewer / retrospective_facilitator / planner_builder_reviewer_contract）
- `templates/`: project brief、team mission/rules/workflow、role の各テンプレ

詳細は `manifest.md` を参照。

## 含まれないもの

- L2 (Product Core OS): コア規約は別配布。本バンドルはそのスナップショットを取り込む前提。
- L3 (OS Learning Records): 運用ログ・学習履歴は導入後に蓄積する。

## 前提条件

- Git が利用可能であること
- Markdown 編集環境があること
- 最終承認者（人間）が 1 名以上いること

## バージョン

**v0.1**: 実体ファイル 14 点を snapshot model で収録。差分マージ指針・カスタマイズポイントは v0.2 で明示予定。

## 関連

- Product Vision: [`../../docs/product_vision.md`](../../docs/product_vision.md)
- 移植手順: [`install.md`](./install.md)
- ファイル構成: [`manifest.md`](./manifest.md)
- 変更履歴: [`CHANGELOG.md`](./CHANGELOG.md)
