# ai-org-os

> 想定読者: このリポジトリに到達した全員。

**State: Reset + Meta-meta structure defined (2026-05-22)**

ai-org-os は「**開発組織の不変項（公理系）を定義するフレームワーク**」です。詳細は ADR を参照してください。

- 方向性: [ADR-0001](docs/adr/0001-ai-org-os-as-invariant-framework.md)
- 構造と用語: [ADR-0002](docs/adr/0002-vocabulary-and-meta-meta-structure.md)
- 過去成果物: [`OLD/`](OLD/) 配下にアーカイブ（参照可、新方向と整合しない部分は捨てる前提）

## このリポジトリは何か

「**開発組織とは、どんな思考が揃った集合か**」の不変項（外せない部分）を定義するフレームワーク。

- 組織 = **共通の目的をもった思考の集合体**（= 思考のネットワーク）
- 各思考の実装（AI / 人間の脳 / 将来的なデバイス）は問わない
- 「人間」というカテゴリは組織内に存在しない
- 比喩: **Claude Code の組織版** / **AI 思考のための仮想空間**

## 構造（用語）

| 概念 | 用語 | 役割 |
|---|---|---|
| メタ世界コンテナ | **Realm** | ai-org-os のルール適用範囲 |
| 世界 Claude | **Warden** | Realm の守護者、独自ルールの運営 |
| MCP サーバー | **Nexus** | 思考間通信 + 外部 I/F |
| 組織枠 | **Guild** | 目的を共有する Mind の集合体（論理セグメント） |
| マザー Claude | **Guildmaster** | Guild を運営する思考 |
| 思考 Claude | **Mind** | 思考そのもの、コンテナで動く |
| 私有記憶 | **Mindspace** | Mind 個別の領域、不可侵 |
| 不変項 | **Axiom** | 開発組織の公理 |
| 明示プロセス | **Dispatch** | Mind 間の明示的通信 |

## 不変項（4要素）

1. 組織⇔外の境界
2. 思考⇔思考の境界
3. 思考ごとの記憶（Mindspace）
4. インターフェース

## 次にやること

ADR-0002 で「メタのメタ側」の最低限が固まった。次は具体実装に降りる：

1. Realm の最小実装スケッチ
2. Nexus（MCP サーバー）の最小プロトコル
3. Warden / Guildmaster / Mind の最小規約
4. Axiom の機械検証可能化
5. Issue 投入インターフェース

## ライセンス

[LICENSE](LICENSE) を参照。
