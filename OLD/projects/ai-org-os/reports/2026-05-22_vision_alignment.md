# Vision 整合バッチレポート（2026-05-22）

> 想定読者: 本リポジトリのコントリビュータ、および同種の整合作業を将来行う Planner / Reviewer。

## 1. 背景

ai-org-os の本体は「メンテナンス性の高い自社開発 AI チームを構築・共有可能にするツール」である（プロダクトオーナーによる明示的補正）。しかし、リポジトリ内の主要文書（README / brief / specs / L1-L3 README / charter / operating_principles 等）は「このリポジトリ自身の組織構造を記述する」レベルにとどまっており、ツールとしての視点が末端まで反映されていなかった。

結果として：
- L1 が空のまま L2/L3 ばかり拡張される構造的偏り
- 想定読者が曖昧で、外部に渡せるバンドル設計が進んでいない
- 新規貢献者が「これは何のツールか」を README から読み取れない

## 2. 実施したこと

### 2.1 SSOT の確立
- 新規作成: `docs/product_vision.md`
  - 時代観 / プロダクト本体定義 / 提供価値3軸（Build / Maintain / Share）/ 想定ユーザー / 差別化軸 / L1-L3 の意味 / 判断軸 / 非ゴール / 運用ルール

### 2.2 上位文書の Vision 整合化（並列で実施）
- `README.md`: 「ツール紹介」視点に書き直し、3軸と L1-L3 を明示
- `org/charter.md`: 「Web Service Domain」縛りを外し、ツール本体組織として再定義。web-service は L1 第一弾バンドルのリファレンス実装と位置づけ
- `projects/ai-org-os/brief.md`: Problem/Goal/Users/Scope を Vision に整合
- `projects/ai-org-os/specs/requirements.md`: 既存7項目に加え、L1 バンドル出力（Share）と自己改善ループ（Maintain）を追加
- `projects/ai-org-os/specs/architecture.md`: L1/L2/L3 と 3軸の対応表を追加

### 2.3 L1/L2/L3 セグメント README と IA の整合
- `L1_product-os-bundles/README.md`: 「ツールの直接的な商品」として位置づけ、バンドル必須構成を列挙、「L1 空 = 価値ゼロ」を警告として記載
- `L2_product-core-os/README.md`: 「L1 が継続運用される強制基盤」として再定義
- `L3_os-learning-records/README.md`: 「L2 が機能している証拠 / 次世代 L1 の原料」として位置づけ
- `docs/information_architecture.md`: 3軸対応表を新設、IA-3a/4a の完了を反映、IA-5（L1 バンドル骨子）を新規追加

### 2.4 運営原則・チーム・テンプレ整合
- `org/operating_principles.md`: 既存5原則に Why を併記し、「5. Portable Team Design」を「Portability-First」に強化、「6. Vision-First」「7. Reader-Aware Documentation」を新設
- `teams/web-service-team/mission.md`: 「L1 バンドル第一弾のリファレンス実装」位置づけと「移植可能性維持」を追加
- `templates/project/brief.md`, `templates/team/mission.md`, `templates/team/roles/role.md`: 想定読者と 3軸寄与・移植可能性・ハンドオフ先・人間承認ポイントを項目追加
- `CONTRIBUTING.md`: 変更前チェックリスト（3軸寄与 / 想定読者 / L1-L3 配置 / 1目的=1PR）を新設

### 2.5 L1 第一弾バンドル骨子の配置
- `L1_product-os-bundles/web-service-team-bundle-v0/` を新設
  - `README.md`: バンドル概要・前提条件
  - `manifest.md`: 提供ファイル一覧と 3軸寄与
  - `install.md`: 5ステップの移植手順
  - `CHANGELOG.md`: v0〜v1.0 のロードマップ
- v0 は骨子のみ。実体ファイルは v0.1 で別 PR として収録（1目的=1PR）

### 2.6 backlog の Vision 軸付与
- `projects/ai-org-os/backlog.md`: 最優先セクションを新設し、L1-V0.1 シリーズタスク（実体ファイル収録）を 5 タスクで起票。既存タスクには軸を付与

## 3. 再発防止策

### 3.1 機械的チェック（`.githooks/pre-commit` 拡張）
- 新規 `.md` ドキュメントの冒頭10行に「想定読者」記載がない場合に警告
- `docs/product_vision.md` 変更時に `memory/decisions.md` 更新が含まれない場合に警告
- 既存の機密情報ブロックと変更ファイル数警告は維持

### 3.2 運営原則による恒久ルール化
- **6. Vision-First**: 仕様・ドキュメント・ルールの新規/変更は 3軸に寄与することを確認してから着手
- **7. Reader-Aware Documentation**: 全主要ドキュメントは冒頭に想定読者を明示

### 3.3 CONTRIBUTING の変更前チェックリスト
- 3軸寄与 / 想定読者 / L1-L3 配置 / 1目的=1PR を自答する形式

### 3.4 テンプレートへの強制項目
- project brief / team mission / role に「Vision の3軸への寄与」「想定読者」「移植可能性」を必須項目化

## 4. 検証

- 全修正対象ファイルを再読し、Vision の3軸が反映されていること、想定読者が冒頭に記載されていることを確認済
- L1 バンドル骨子は 50 行以下／ファイルを維持
- 既存の有用な内容（ドッグフーディング、guardrails、運用サイクル等）は破壊していない

## 5. 残課題（次サイクル）

- [ ] L1-V0.1 シリーズ: web-service-team の実体ファイルをバンドルへ収録
- [ ] L1 バンドルと本体ファイルの二重管理を防ぐ運用ルールを decisions.md に記録
- [ ] 次回 retrospective でこの一括整合のプロセスを振り返り、Wave 単位の整合バッチを定型化するか判断
- [ ] `org/global_rules.md`（スタブ）を含む既存リンクの一括 grep チェック（リンク切れ確認）

## 6. ベストプラクティス（このバッチから抽出）

- **SSOT を先に固定する**: 末端を直す前にビジョンを書く。判断軸が共有されていない状態で末端を直すと、整合が再発する
- **並列実行で広く一気に**: 末端文書は独立性が高いので、サブエージェント並列で広く一気に整合させると、整合期間中の中間状態を最小化できる
- **機械的チェックで再発を物理的に防ぐ**: 運営原則を増やすだけでは守られない。pre-commit hook で警告化することで、忘却に対する保険を作る
- **新規骨子は実体と分離して PR する**: L1 骨子と実体を同時に作ろうとすると複数目的が混在する。骨子のみ先に通すと、レビューが軽くなる

---

関連: [Product Vision](../../../docs/product_vision.md) / [Information Architecture](../../../docs/information_architecture.md)
