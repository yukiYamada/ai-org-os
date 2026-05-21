# 情報設計（Information Architecture）

このリポジトリは、似て見えて性質が異なる3概念を明確に分離する。

1. L1: このプロダクトで生成される「学習済み開発集団OSセット」
2. L2: このプロダクト自体のOS（規約・コア）
3. L3: このプロダクトがOS運用で学習した記録

## トップディレクトリ分離（第一段階）

- `L1_product-os-bundles/`
- `L2_product-core-os/`
- `L3_os-learning-records/`

> まずはトップに概念セグメントを固定し、既存資産は小分け移行で追従する。

## 概念定義

### L1: Product OS Bundles
- 配布・移植可能な「学習済みOSセット」の成果物
- 例: チーム構成パッケージ、学習済み運用バンドル

### L2: Product Core OS
- 提供必須のコア規約・運用制約・強制手段
- 例: org規約、team rules、hook運用

### L3: OS Learning Records
- 実運用で得た判断・計測・ふりかえり・改善履歴
- 例: backlog、reports、issues、memory logs

## 配置の判定規則

- 「再配布可能な成果物」なら L1
- 「全員が守る規約」なら L2
- 「運用で得た事実記録」なら L3

## 既存ディレクトリとの対応（移行前提）

- L2候補: `org/` `.githooks/` `teams/*/rules.md`
- L3候補: `projects/` `teams/*/memory/`
- L1候補: 現状なし（今後生成）

## 試験移動の実施ログ

- 2026-05-21: IA-4aとして `org/global_rules.md` を `L2_product-core-os/org/global_rules.md` へ試験移動。
- 互換のため `org/global_rules.md` は移行案内のスタブを配置。

## 細分化タスク（変更量を抑えた段階適用）

- IA-3a（30分）: 3セグメント直下READMEの初期文言をレビューして確定
- IA-3b（30分）: `README.md` にトップセグメント導線を追加
- IA-3c（45分）: `projects/ai-org-os/backlog.md` に移行チケット（L2/L3）を追加
- IA-4a（45分）: L2候補ファイルのうち1ファイルのみ試験移動（リンク修正含む）
- IA-4b（45分）: L3候補ファイルのうち1ファイルのみ試験移動（リンク修正含む）
