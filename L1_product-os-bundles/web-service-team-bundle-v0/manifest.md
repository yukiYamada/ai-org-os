# Manifest: web-service-team-bundle v0.1

> 想定読者: バンドル受領者、およびバンドル出荷側のコントリビュータ。

このバンドルが提供するファイル一覧と、Product Vision の 3 軸（Build / Maintain / Share）への寄与。各実体ファイルは `teams/web-service-team/` または `templates/` のスナップショット（snapshot model: [D-0003](../../teams/web-service-team/memory/decisions.md) 参照）。

| バンドル内パス | 役割 | 寄与する軸 | 起源パス（snapshot 元） | 現状 |
|---|---|---|---|---|
| `README.md` | バンドル概要・前提条件 | Build / Share | — | 収録済み |
| `install.md` | 自社リポジトリへの移植手順 | Build / Share | — | 収録済み |
| `manifest.md` | 本ファイル。構成定義 | Share | — | 収録済み |
| `CHANGELOG.md` | バージョン履歴 | Maintain | — | 収録済み |
| `mission.md` | チームのミッション・判断軸 | Build / Maintain | `teams/web-service-team/mission.md` | **v0.1 収録済み** |
| `rules.md` | チーム運用規約 | Maintain | `teams/web-service-team/rules.md` | **v0.1 収録済み** |
| `workflow.md` | 標準ワークフロー | Build / Maintain | `teams/web-service-team/workflow.md` | **v0.1 収録済み** |
| `roles/product_owner.md` | 役割: Product Owner | Build / Maintain | `teams/web-service-team/roles/product_owner.md` | **v0.1 収録済み** |
| `roles/architect.md` | 役割: Architect | Build / Maintain | `teams/web-service-team/roles/architect.md` | **v0.1 収録済み** |
| `roles/engineer.md` | 役割: Engineer | Build / Maintain | `teams/web-service-team/roles/engineer.md` | **v0.1 収録済み** |
| `roles/reviewer.md` | 役割: Reviewer | Build / Maintain | `teams/web-service-team/roles/reviewer.md` | **v0.1 収録済み** |
| `roles/retrospective_facilitator.md` | 役割: Retrospective Facilitator | Build / Maintain | `teams/web-service-team/roles/retrospective_facilitator.md` | **v0.1 収録済み** |
| `roles/planner_builder_reviewer_contract.md` | 3 ロール契約（MVP） | Build / Maintain | `teams/web-service-team/roles/planner_builder_reviewer_contract.md` | **v0.1 収録済み** |
| `templates/project/brief.md` | プロジェクト brief テンプレ | Build | `templates/project/brief.md` | **v0.1 収録済み** |
| `templates/team/mission.md` | チーム mission テンプレ | Build | `templates/team/mission.md` | **v0.1 収録済み** |
| `templates/team/rules.md` | チーム rules テンプレ | Build | `templates/team/rules.md` | **v0.1 収録済み** |
| `templates/team/workflow.md` | チーム workflow テンプレ | Build | `templates/team/workflow.md` | **v0.1 収録済み** |
| `templates/team/roles/role.md` | ロールテンプレ | Build | `templates/team/roles/role.md` | **v0.1 収録済み** |

## Snapshot 運用について

- 実体ファイルは v0.1 リリース時点（2026-05-22）の起源パス（上表）のスナップショット。
- 起源側の更新は自動同期されない。次バージョン（v0.2 以降）で再スナップショットを取る運用（snapshot model）。
- 詳細な根拠は本リポジトリの `teams/web-service-team/memory/decisions.md` の **D-0003** を参照。

## ファイル内の相対リンクについて

各実体ファイルの `関連: Product Vision` 等の相対リンクは、**バンドルがターゲットリポジトリへデプロイされた後の位置**で正しく解決されるよう設計されている。バンドル内ディレクトリ構造で直接開くと一部リンクが解決しないが、これは想定通り。受領後の移植では `install.md` の手順に従うこと。
