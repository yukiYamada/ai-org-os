# Changelog: web-service-team-bundle

> 想定読者: バンドル受領者、およびバージョン更新を行うコントリビュータ。

本バンドルのバージョン履歴。Semantic Versioning に厳密に従わず、出荷可能性のマイルストーンを示す。

## v0.2 (2026-05-22)

- **`customize.md` を追加**: Must / Should / May のレベル分け、優先順序（PR 分割指針）、置換マーカーの読み方を明示。
- **実体ファイルに `<!-- CUSTOMIZE: ... -->` マーカーを最小埋め込み**: `mission.md` / `rules.md` / `workflow.md` / `roles/` 6 ファイルへ最大 3 個までのマーカーを追加。本文は不変、構造も不変、追加のみ。
- `manifest.md` を v0.2 へ更新（`customize.md` を提供ファイル一覧へ、カスタマイズマーカーの存在を注記）。
- `README.md` を v0.2 へ更新（含まれるもの一覧へ `customize.md` を追加）。
- `install.md` にステップ 6（カスタマイズ実施）を追加。
- **v0.2 で達成**: 受領者が「何を書き換えるべきか」を 10 分以内で把握できる状態。

## v0.1 (2026-05-22)

- **実体ファイルを収録（snapshot model）**: `teams/web-service-team/` および `templates/` から 14 ファイルを v0.1 リリース時点のスナップショットとしてバンドル内へ収録。
  - `mission.md` / `rules.md` / `workflow.md`
  - `roles/` 配下 6 ファイル（product_owner / architect / engineer / reviewer / retrospective_facilitator / planner_builder_reviewer_contract）
  - `templates/project/brief.md` / `templates/team/{mission, rules, workflow}.md` / `templates/team/roles/role.md`
- `manifest.md` を v0.1 状態へ更新（起源パスと収録状況を明示）。
- 採用された運用モデル: snapshot model（バンドルは起源の凍結スナップショット、自動同期なし、次バージョンで再スナップショット）。詳細は本リポジトリの `teams/web-service-team/memory/decisions.md` の **D-0003**。

## v0 (2026-05-22)

- 骨子作成: `README.md` / `manifest.md` / `install.md` / `CHANGELOG.md` を配置。
- 実体ファイル未収録。
- 目的: L1（プロダクト出力）が空である状態を解消し、第一弾バンドルの輪郭を確定すること。

## 今後の予定

- **v0.3**: 初回ユーザーフィードバックを反映。`install.md` を実運用ベースで改訂。差分マージ指針を追加。
- **v1.0**: 外部プロジェクトでの導入実績を 1 件以上得て、後方互換のあるベースラインとして固定する。
