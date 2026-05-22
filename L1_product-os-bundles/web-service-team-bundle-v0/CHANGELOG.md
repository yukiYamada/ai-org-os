# Changelog: web-service-team-bundle

> 想定読者: バンドル受領者、およびバージョン更新を行うコントリビュータ。

本バンドルのバージョン履歴。Semantic Versioning に厳密に従わず、出荷可能性のマイルストーンを示す。

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

- **v0.2**: カスタマイズポイント（差分マージ指針、置換すべき固有名詞、最小／推奨の境界）を明示。
- **v0.3**: 初回ユーザーフィードバックを反映。`install.md` を実運用ベースで改訂。
- **v1.0**: 外部プロジェクトでの導入実績を 1 件以上得て、後方互換のあるベースラインとして固定する。
