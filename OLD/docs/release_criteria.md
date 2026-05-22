# Release Criteria

> 想定読者: リリース判断を行う意思決定者、進捗を可視化する Planner / Reviewer、貢献計画を立てるコントリビュータ。

このドキュメントは ai-org-os のリリースゲート（DoD）を SSOT として定義する。`backlog.md` および GitHub Issue / Milestone はこの DoD を満たすために存在する。

判断の起点は [Product Vision](./product_vision.md) の 3 軸（Build / Maintain / Share）。

---

## v0.3: Minimum Viable Release（最低限のリリース）

### リリースの定義

**受領者（自社へ ai-org-os を導入する技術リード）が、自社向けの「自立稼働する開発チームの定義」を独立して作成・運用開始できる状態。**

「自立稼働する開発チーム」とは:
- 役割・承認境界・自己改善ループが明確で、AI 主導で日常運用が回る
- 人間の最終承認は維持する（自動化への暴走を防ぐ安全装置）
- 外部依存なく、自社リポジトリ内で完結する

このリリース時点では **外部導入実績の取得は条件としない**（それは v1.0 のゲート）。代わりに、内部での自己適用検証と完結性の検証で代替する。

### DoD（7項目、全達成が v0.3 リリース条件）

1. **L1-D1: L1 バンドル v0.3 の自己適用検証**  
   仮想ターゲットプロジェクトへの install を 1 回実施し、`install.md` / `customize.md` に検証フィードバックを反映済み。

2. **L1-D2: 自立稼働判定チェックリスト**  
   受領者が「これで自社チームとして回せる」を 10 項目以内で自答できる checklist がバンドル内に存在する（`L1_product-os-bundles/web-service-team-bundle-v0/self-check.md` 等）。

3. **L1-D3: 移植後の完結性**  
   バンドル移植後に外部リポジトリ参照を必要としない。`Product Vision` 等の必須参照は同梱 or バンドル内に明確な参照ルールが定義されている。

4. **OBS-D1: 週次 Metrics 実績**  
   `projects/ai-org-os/specs/metrics.md` の 5 指標について、1 週分以上の計測実績が `teams/*/memory/learnings.md` 等に記録され、取得不能指標が明示されている。

5. **QA-D1: 品質ゲートの組込**  
   `.githooks/pre-commit` の有効化（`git config core.hooksPath .githooks`）が `install.md` の必須ステップに含まれ、想定読者・Vision 参照の警告が機能する状態。

6. **PM-D1: タスク可視化**  
   `backlog.md` の全 `[ ]` 項目について、GitHub Issue として可視化されているか、明示的に done（`[x]` + 完了根拠）に整理されている。v0.3 milestone との紐付け済み。

7. **L3-D1: 学習ループの継続**  
   R-0001 以降、retrospective が最低 1 件追加され、起源↔バンドル乖離チェックが必須実施されている。learnings.md に再利用可能な学習エントリが累計 5 件以上。

### 達成判定

各 DoD には対応する GitHub Issue が存在し、close 時に「DoD 達成根拠」を本文末尾に記録する。7 項目すべて close = v0.3 リリース可。

---

## v1.0: External Adoption Baseline（外部導入ベースライン）

v0.3 達成後、以下を追加で満たす。

1. 外部プロジェクトへの導入実績 1 件以上（PR または導入レポート）
2. 後方互換のあるバンドル構造の固定
3. 第二弾バンドル候補の選定理由が `decisions.md` に記録

詳細な DoD は v0.3 達成後に確定する。

---

## Later（中期〜長期）

`docs/roadmap.md` 参照。Vision 更新を伴う変更が必要なので、本ファイルでは DoD 化しない。

---

## 運用ルール

- 本ファイルは月次レビュー対象（時代観や前提が変われば DoD 更新）。
- DoD の追加・削除・変更は `teams/web-service-team/memory/decisions.md` に「背景 / 選択肢 / 決定 / 影響」を残す。
- 各 DoD 項目の進捗は GitHub Milestone のクローズ率で可視化する。

---

参考: [Product Vision](./product_vision.md) / [Roadmap](./roadmap.md) / [Backlog](../projects/ai-org-os/backlog.md)
