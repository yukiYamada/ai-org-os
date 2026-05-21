# ai-org-os

AI 開発組織を Git リポジトリとして定義し、運用可能にするための最小構成です。

## 目的

このリポジトリはアプリ本体ではなく、**AI 駆動開発組織の運営構造**を表現します。  
人間は承認・説明責任・実行環境の提供を担い、AI チームは役割・ルール・記憶に基づいて開発を進めます。

## ドッグフーディング原則

- **ai-org-os は、このリポジトリ内で定義された AI 組織自身によって開発されます。**
- このリポジトリは次の 2 つを同時に担います。  
  1. 開発対象プロダクト（ai-org-os）  
  2. プロダクトを開発する運営構造
- 最初のマイルストーンは、**Git ベースの AI 開発組織が自分自身の開発を管理できること**を実証することです。

## 何を管理するか

- 組織全体の方針・原則・共通ルール
- チームごとのミッション・ローカルルール・ワークフロー
- 役割責務（Product Owner / Architect / Engineer / Reviewer / Retrospective Facilitator）
- 意思決定・ふりかえり・学習ログ
- プロジェクト（初期対象: ai-org-os 自身の開発）

## 設計方針

- 永続化の第一層は Git
- 構造は Markdown 中心（AI が読み取り・更新しやすい）
- ルールは「全体」と「チーム局所」に分離
- チームはレトロスペクティブでローカルルールを進化可能
- 将来的な移植（他ユーザー / 他プロジェクトへの転送）を前提

## リポジトリ構成

トップは **README + セグメントディレクトリ** を原則とする。

- `L1_product-os-bundles/`: 学習済み開発集団OSセット（配布・移植可能成果物）
- `L2_product-core-os/`: 本プロダクトのOSコア（規約・強制手段）
- `L3_os-learning-records/`: OS運用で得た学習記録

既存ディレクトリ（`org/`, `teams/`, `projects/`, `templates/`）は段階移行中のため当面併存。
配置判断は `docs/information_architecture.md` を参照。

## 運用の最小サイクル

1. `projects/ai-org-os/brief.md` と `backlog.md` を更新
2. Architect が `projects/ai-org-os/specs/` を更新
3. Engineer が実装し、Reviewer が検証
4. 重要判断を `teams/*/memory/decisions.md` に追記
5. スプリント後に `retrospectives.md` と `learnings.md` を更新し、必要なら `teams/*/rules.md` を改定

## 現在の状態

- 本リポジトリは初期構造のみを提供
- アプリケーション本体（DB/認証/課金/オーケストレーション等）は未導入
- まずは運営構造を固定し、ai-org-os 自身の開発で検証する
