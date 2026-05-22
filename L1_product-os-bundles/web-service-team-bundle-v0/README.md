# web-service-team-bundle v0 (骨子)

> 想定読者: このバンドルを自社へ導入したい技術リード／テックリード。

## バンドル概要

Web サービスドメインの小規模 AI 開発チームを、自社リポジトリで立ち上げるためのリファレンス実装バンドル。`teams/web-service-team/` の構成を「移植可能な配布物」として整えたもの。

## 含まれるもの（予定）

- `mission.md`: チームのミッションと判断軸
- `rules.md`: チーム運用規約（org の global_rules を補完）
- `roles/`: 役割定義（責務・権限・引き継ぎ条件）
- `workflow.md`: 標準ワークフロー
- 最小テンプレ（brief / レビュー / 議事）

## 含まれないもの

- L2 (Product Core OS): コア規約は別配布。本バンドルはそのスナップショットを取り込む前提。
- L3 (OS Learning Records): 運用ログ・学習履歴は導入後に蓄積する。

## 前提条件

- Git が利用可能であること
- Markdown 編集環境があること
- 最終承認者（人間）が 1 名以上いること

## バージョン

**v0**: 骨子のみ。実体ファイル（mission.md 等の本文）は未収録。実体は v0.1 で追加予定（`CHANGELOG.md` 参照）。

## 関連

- Product Vision: [`../../docs/product_vision.md`](../../docs/product_vision.md)
- 移植手順: [`install.md`](./install.md)
- ファイル構成: [`manifest.md`](./manifest.md)
- 変更履歴: [`CHANGELOG.md`](./CHANGELOG.md)
