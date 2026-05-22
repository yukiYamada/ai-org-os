# Backlog

> 想定読者: プロジェクト進行を判断する Planner / Reviewer / 意思決定者。
> 全タスクは [Product Vision](../../docs/product_vision.md) の3軸（Build / Maintain / Share）のいずれかに寄与すること。

## 最優先（Top Priority: L1 バンドル充填）
**根拠**: Vision 上、L1 が空のままだとプロダクト価値ゼロ。骨子は v0 で配置済み、次は実体収録。
- [x] **L1-V0.1-1**: `teams/web-service-team/mission.md` をバンドルへ収録（Share）— v0.1 完了
- [x] **L1-V0.1-2**: `teams/web-service-team/rules.md` をバンドルへ収録（Maintain / Share）— v0.1 完了
- [x] **L1-V0.1-3**: `teams/web-service-team/roles/*` をバンドルへ収録（Build / Maintain）— v0.1 完了（6 ファイル）
- [x] **L1-V0.1-4**: `teams/web-service-team/workflow.md` をバンドルへ収録（Build / Maintain）— v0.1 完了
- [x] **L1-V0.1-5**: バンドルと本体の二重管理を防ぐ運用ルールを decisions.md に記録（Maintain）— D-0003（snapshot model）として確定

## 次サイクル（L1 バンドル v0.2 以降）
- [ ] **L1-V0.2-1**: カスタマイズポイント（差分マージ指針 / 置換すべき固有名詞 / 最小と推奨の境界）を `install.md` に明示
- [ ] **L1-V0.2-2**: 起源と乖離が大きくなった際の「再スナップショット候補」検出を retrospective / Metrics Review に組み込む（D-0003 影響欄の次タスク化候補）

## Todo（既存・Vision 軸を付与して保持）
- [ ] Define organization charter.（→ 完了済み。`org/charter.md` を Vision 整合へ更新済）
- [ ] Define global rules.（→ 完了済。`L2_product-core-os/org/global_rules.md`）
- [ ] Define web-service-team mission.（→ 完了済。Vision 整合化済）
- [ ] Define role responsibilities.（→ 完了済。`teams/web-service-team/roles/`）
- [ ] Define decision log format.（Maintain）
- [ ] Define retrospective format.（Maintain）
- [ ] Define project brief format.（→ 完了済。テンプレ Vision 整合化済）
- [ ] Define how team-local rules improve over time.（Maintain）
- [ ] Define criteria for extracting/transferring a team.（Share）
- [ ] Decide the first executable feature after the documentation structure is stable.（Build）


## Todo (AIのみ開発組織MVP: 2026-05-21)
- [x] Issue 1: Guardrails（やってはいけないこと）を定義する
- [x] Issue 2: Roles（やるひと）を定義する
- [x] Issue 3: Workspace（作業場所）を定義する
- [x] Issue 4: Research Loop（情報収集）を定義する
- [x] Epic DoD: 4 Issueを30〜90分タスクで実行開始する
- [x] Issue 5: Metrics（状態監視）を定義する — projects/ai-org-os/specs/metrics.md に集約
- [ ] Issue 6: Information Architecture（Starter/Governance/Runtime Memory 分離）を運用開始する

## 整合メモ（AI主導開発組織MVP）
- 旧Todo（charter/rules/roles/decision/retro/brief）は、Issue 1〜4で段階的に具体化して処理する。
- 運用前提は「AI主導 + 人間最終承認」とする。
- **2026-05-22 ビジョン整合バッチ**: 全文書を `docs/product_vision.md`（3軸: Build/Maintain/Share）に整合させる一括修正を実施。詳細は `reports/2026-05-22_vision_alignment.md`。

## Proposals (Bottom-up)
- [x] IA-SEG-01: L2候補（org/.githooks/rules）から1ファイル試験移動してリンク影響を確認（`org/global_rules.md`）
- [ ] IA-SEG-02: L3候補（projects/memory）から1ファイル試験移動して運用差分を記録
- [ ] P-0002: 自己改善ループを週次で実行し、未達指標を30〜60分タスクへ再分解する
- [ ] Metrics Review を週次実行する
- [ ] P-0001: （例）Issueテンプレへ「提案欄」を追加し、改善提案の提出漏れを防ぐ

## In Progress
- [ ] IA運用1週レビュー（配置違反件数/移動コストを確認）
- [ ] Guardrails運用1週レビュー（G-01〜G-08/A-01〜A-04の調整）
- [ ] Roles運用1週レビュー（責務衝突/ハンドオフ詰まりの確認）
- [ ] Workspace運用1週レビュー（staging経由率/差し戻し理由を確認）
- [ ] Research Loop運用1週レビュー（根拠不足指摘率/矛盾保留件数を確認）

## Done
- [x] Initialize self-hosting repository structure.
