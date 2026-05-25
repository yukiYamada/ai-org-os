---
kind: generic
version: 0.1
status: experimental
---

# Kind: Generic

> 想定読者: Mind を生成する Guildmaster / Warden、および Kind スキーマを設計するメンテナ。

Kind は Mind の **Body 性能**（=動かす器のスペック）を定義する。当面 ai-org-os では Generic 1 種類のみ。

## Body Spec

| 項目 | 値 | 備考 |
|---|---|---|
| **runtime** | Claude（CLI または Code 等） | 中で動く実体 |
| **execution** | ホスト直接実行（Phase 1）→ Docker コンテナ（Phase 2） | 段階的に隔離度を上げる |
| **mindspace** | ホスト上のディレクトリ | Phase 2 で named volume へ |
| **tools** | Claude 標準ツール一式 | 後で MCP 経由のツールも追加 |
| **resources** | 無制限（Phase 1） | Phase 2 以降 Warden が制限を適用 |
| **lifecycle** | 起動・停止のみ（Phase 1） | Phase 3 以降 Mind 自身の "death" を扱う |

## Phase 1 における Body の振る舞い

- Mind の生成 = `runtime/minds/<mind-name>/` ディレクトリ作成
- Mindspace 初期化 = Persona ファイルを `CLAUDE.md` としてコピー
- Mind の起動 = そのディレクトリで Claude を起動
- Mind の停止 = プロセス kill / Claude セッション終了

## Phase 2 以降の拡張ポイント

- Dockerfile を `runtime/kinds/generic.Dockerfile` として追加
- リソース制限（CPU / Memory / token rate）を Warden が enforce
- Tools の Set を kind 定義に明示（MCP 経由でロード）

## 不変条件（Axiom と整合する原則）

- Body は **Mindspace の不可侵性**を物理的に担保する（他 Mind から読み書き不能）
- Body は **思考の能動性**を阻害しない（=ウェイク条件を内蔵しない）
- Body は **生成 / 破棄の3段階プロセス**を経由する（直接生成は禁止）

## 関連

- 用語: [ADR-0002](../../docs/adr/0002-vocabulary-and-meta-meta-structure.md)
- Persona 例: [`../personas/designer.md`](../personas/designer.md)
