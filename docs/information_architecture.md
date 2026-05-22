# 情報設計（Information Architecture）

> 想定読者: 新規ファイル・既存ファイルの配置判断をするコントリビュータ。

このリポジトリは、似て見えて性質が異なる3概念を明確に分離する。L1 はツールの出力物（商品）、L2 はその出力を維持する基盤、L3 はその基盤が機能している証拠であり次世代出力の原料、という関係にある。

1. L1: このプロダクトで生成・出荷される「学習済み開発集団 OS バンドル」（= 商品）
2. L2: L1 を継続運用可能にするコア規約・強制手段
3. L3: L2 が実運用で機能している学習・改善記録

## トップディレクトリ分離

- `L1_product-os-bundles/`
- `L2_product-core-os/`
- `L3_os-learning-records/`

## 概念定義

### L1: Product OS Bundles
- **ツール出力としての商品**。受け取り側が自社 AI 開発チームとして即運用開始できる、移植可能な学習済みバンドル
- 例: チーム構成パッケージ、学習済み運用バンドル、INSTALL 手順一式
- **空のままにしてはならない**。L1 不在のとき本プロダクトの提供価値は成立しない

### L2: Product Core OS
- L1 バンドルが継続運用される根拠となるコア規約・強制手段
- 例: org 規約、team rules、hook 運用
- L2 で固まらないルールは L1 に混入させない

### L3: OS Learning Records
- 実運用で得た判断・計測・ふりかえり・改善履歴
- 例: backlog、reports、issues、memory logs
- 次世代 L1 バンドルの原料

## Product Vision 3軸との対応

| 層 | Build（立ち上げ） | Maintain（継続運用） | Share（移植・共有） |
|---|---|---|---|
| L1 | ◎ 受け取った瞬間に立ち上がる | ○ バンドル内に運用構造を含む | ◎ 商品そのもの |
| L2 | ○ 立ち上げの土台を提供 | ◎ メンテ性の強制基盤 | ○ バンドルへスナップショット |
| L3 | △ 立ち上げ後に蓄積開始 | ◎ 自己改善ループの一次情報 | ○ 次世代バンドルの原料 |

## 配置の判定規則

- 「再配布可能な商品」なら L1
- 「全員が守る規約・強制手段」なら L2
- 「運用で得た事実記録」なら L3
- いずれにも当てはまらない場合は、Product Vision の3軸に照らして「やらない」または Vision を更新する

## 既存ディレクトリとの対応（移行前提）

- L2 候補: `org/` `.githooks/` `teams/*/rules.md`
- L3 候補: `projects/` `teams/*/memory/`
- L1 候補: 現状なし（最優先で第一弾バンドルを生成する）

## 試験移動の実施ログ

- 2026-05-21: IA-4a として `org/global_rules.md` を `L2_product-core-os/org/global_rules.md` へ試験移動。
- 互換のため `org/global_rules.md` は移行案内のスタブを配置。

## 細分化タスク（進捗反映）

- IA-3a 完了: 3セグメント直下 README の初期文言を Product Vision に整合
- IA-3b: `README.md` にトップセグメント導線を追加（要確認）
- IA-3c: `projects/ai-org-os/backlog.md` に L2/L3 移行チケットを追加（要確認）
- IA-4a 完了: L2 候補1ファイルの試験移動済み
- IA-4b: L3 候補1ファイルの試験移動（未着手）
- IA-5（新規）: 第一弾 L1 バンドル `web-service-team-bundle-vX` の骨子作成

---

参考: [`product_vision.md`](./product_vision.md)
