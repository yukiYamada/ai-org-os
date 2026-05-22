# Decisions Log

## D-0001
- 日付: 2026-05-21
- 決定: 永続化の第一層として Git を採用
- 背景: 監査性・差分管理・移植性を重視
- 影響: 全運用は Markdown + Git 履歴を基準に行う

## D-0002
- 日付: 2026-05-22
- 決定: `docs/product_vision.md` を全判断の SSOT として確立し、既存全文書をビジョン3軸（Build / Maintain / Share）に整合させる
- 背景:
  - プロダクトの本体が「メンテナンス性の高い自社開発 AI チームを構築・共有可能にするツール」であるという核思想が、README/brief/specs/L1-L3 README/charter/operating_principles 等の末端文書に反映されておらず、視点ズレが累積していた
  - L1 が空のままで L2/L3 ばかり拡張される構造的偏りが顕在化
- 選択肢:
  - (A) 個別に発見都度修正する（漸進） — リスク: 再発し続ける
  - (B) ビジョンを SSOT として明文化し、一括整合させる（採用）
  - (C) ビジョン側を末端実態に合わせて妥協する — リスク: 商品価値の毀損
- 影響:
  - 新たに `docs/product_vision.md` を SSOT として作成
  - README / charter / brief / specs (requirements, architecture) / L1-L3 README / IA / operating_principles / web-service-team mission / CONTRIBUTING / templates を Vision 整合化
  - 運営原則に「6. Vision-First」「7. Reader-Aware Documentation」を追加
  - `.githooks/pre-commit` に「想定読者」記載警告と Vision 変更時の decisions.md 必須警告を追加
  - L1 第一弾バンドル骨子 `L1_product-os-bundles/web-service-team-bundle-v0/` を作成
  - 詳細レポート: `projects/ai-org-os/reports/2026-05-22_vision_alignment.md`

## D-0003
- 日付: 2026-05-22
- 決定: L1 バンドルと本体ファイル（`teams/`, `templates/`）の関係に **snapshot model（リリーススナップショット型）** を採用する
- 背景:
  - v0.1 で実体ファイルをバンドル収録するにあたり、本体と二重管理になるリスクを整理する必要があった
  - 候補1: live sync（本体更新が自動でバンドルに反映） — シンプルだが、バンドルは「商品リリース」であるべきで、本体の途中状態が混入するのは不適切
  - 候補2: バンドルを唯一の正とし、本体は thin shim にする — ドッグフーディングの可読性が落ちる
  - 候補3（採用）: snapshot model — バンドルは特定時点の凍結スナップショット。本体は通常通り進化し、節目で再スナップショット（次バージョン）を取る
- 選択肢:
  - (A) live sync — リスク: 中間状態混入
  - (B) bundle as canonical — リスク: ドッグフーディング崩壊
  - (C) snapshot model（採用） — メリット: バンドルが「商品リリース」として明確、本体の自由度を保てる
- 影響:
  - v0.1 で `teams/web-service-team/` および `templates/` の 14 ファイルをバンドルへスナップショット
  - 起源パスは `manifest.md` の表に明示
  - 起源の更新は自動同期されず、次バージョン（v0.2 以降）で再スナップショットを取る運用
  - 起源と乖離が大きくなる前に、retrospective や Metrics Review で「再スナップショット候補」を検出する仕組みを今後設計する（次タスク化候補）

## 提案採否ログテンプレート
- 提案ID: P-XXXX
- 日付: YYYY-MM-DD
- 提案者: Role名（Planner / Builder / Reviewer など）
- 症状: （何が起きているか）
- 原因仮説: （なぜ起きているか）
- 最小変更案: （差分を最小化した具体案）
- 影響範囲: （org / team / project）
- 判定: 採択 / 保留 / 却下
- 判定理由: （根拠）
- フォローアップ: （次アクション）

