# ai-org-os

> 想定読者: 自社で AI 開発チームを立ち上げたい／他者へ共有・提供したい事業会社の意思決定者・リード・テックリード。

**ai-org-os は、メンテナンス性の高い自社開発 AI チームを構築し、共有可能にするツールです。**

これからは自社開発が AI 駆動で加速する時代であり、自社開発能力そのものが事業資産になります。本ツールは、その能力を Git リポジトリ上の運営構造として表現・運用・移植できるようにします。単発のコード生成ツール、LLM ラッパー、開発外注プラットフォームではありません。

詳細なビジョンは [docs/product_vision.md](docs/product_vision.md) を参照してください。

## 対象ユーザー

- **第一義**: 自社開発を加速させたい事業会社の意思決定者・リード・テックリード
- **第二義**: 自社の AI 開発組織を他者へ提供する立場の人（コンサル、エージェンシー、社内プラットフォームチーム）

## 提供価値（3軸）

1. **Build（構築）**: 自社の AI 開発チームを最小ステップで立ち上げられる
2. **Maintain（メンテナンス）**: 立ち上げた AI チームを継続運用・自己改善できる構造を持つ
3. **Share（共有・移植）**: 構築・改善した AI チームを、他社・他プロジェクトへ移植可能な成果物として配布できる

## 成果物のかたち（L1/L2/L3）

| 層 | ディレクトリ | 役割 |
|---|---|---|
| **L1: Product OS Bundles** | `L1_product-os-bundles/` | 移植可能な「学習済み AI 開発チームのバンドル」（このツールの直接的な商品） |
| **L2: Product Core OS** | `L2_product-core-os/` | コア規約・強制手段（メンテナンス性を担保する基盤） |
| **L3: OS Learning Records** | `L3_os-learning-records/` | 運用で得た判断・学習・改善履歴（学習ループが回っている証拠） |

既存ディレクトリ（`org/`, `teams/`, `projects/`, `templates/`）は段階移行中のため当面併存します。配置判断は [docs/information_architecture.md](docs/information_architecture.md) を参照。

## ドッグフーディング原則

- 本リポジトリ自身による開発は、ツールの**検証手段であって目的ではありません**。
- 最初のマイルストーンは、Git ベースの AI 開発組織が自分自身の開発を管理できることを実証することです。
- 人間は承認・説明責任・実行環境の提供を担い、AI チームは役割・ルール・記憶に基づいて開発を進めます。

## 設計方針

- 永続化の第一層は Git
- 構造は Markdown 中心（AI が読み取り・更新しやすい）
- ルールは「全体」と「チーム局所」に分離
- チームはレトロスペクティブでローカルルールを進化可能
- 移植可能なバンドル（L1）出力を前提とする

## 運用の最小サイクル

1. `projects/ai-org-os/brief.md` と `backlog.md` を更新
2. Architect が `projects/ai-org-os/specs/` を更新
3. Engineer が実装し、Reviewer が検証
4. 重要判断を `teams/*/memory/decisions.md` に追記
5. スプリント後に `retrospectives.md` と `learnings.md` を更新し、必要なら `teams/*/rules.md` を改定

## 現在の状態

- 本リポジトリは初期構造のみを提供
- L1 バンドル第一弾のリファレンス実装として `web-service` ドメインを想定（未充填）
- アプリケーション本体（DB/認証/課金/オーケストレーション等）は非ゴール
- まずは運営構造を固定し、ai-org-os 自身の開発で検証する

---

関連: [Product Vision](docs/product_vision.md) / [Information Architecture](docs/information_architecture.md)
