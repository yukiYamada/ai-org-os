# Kind templates

このディレクトリは ai-org-os に同梱される **Kind テンプレ** を置く場所。
Kind は **Mind の Body 性能** (= 動かす器のスペック) を定義する (ADR-0002 /
ADR-0022)。

## 同梱 Kind 一覧 (Phase 5g.A #169)

| Kind | runtime | status | 概要 |
|---|---|---|---|
| [generic.md](generic.md) | `claude` | experimental | claude code を呼ぶ既存 default |
| [deterministic.md](deterministic.md) | `deterministic` | experimental | 決定的 script を Mind body にする (LLM 不要、credit 0) |
| [api.md](api.md) | `api` | **spec only** | openai / gemini API を直接叩く Mind (将来実装) |
| [human.md](human.md) | `human` | **spec only** | human-in-the-loop seat (将来実装) |

## frontmatter スキーマ

```yaml
---
kind: <name>          # 必須、ファイル名 stem と一致
version: <semver>     # 必須
status: <experimental|stable|spec|deprecated>  # 必須
runtime: <runtime>    # 任意 (Phase 5g.A #169)、未指定なら "claude"
framework_version: ">=X.Y"  # 任意 (Phase 5g.A #170)
---
```

### runtime field (Phase 5g.A #169)

`runtime` は **Mind body 実装の discriminator**。`runtime/pillars/lifecycle/`
の `mind-loop.sh` がこの field を読んで cycle body を dispatch する:

| 値 | 意味 | mind-loop.sh の挙動 |
|---|---|---|
| `claude` (default) | claude code を呼ぶ | `claude -p --output-format json <prompt>` を 1 cycle で実行 |
| `deterministic` | 決定的 script | Mindspace 直下 `body.sh` を 1 cycle で 1 回実行 |
| `api` | 外部 LLM API | **未実装** (mind-loop が exit 4) |
| `human` | 人間応答 | **未実装** (mind-loop が exit 4) |

未指定 / 未知値は `claude` に倒す (= 後方互換)。未知値の場合は WARN を
stderr に。

## Kind diversity をなぜ作るか

`generic` (= claude) だけだと「Mind == claude code」が暗黙の前提になり、
framework としての適用範囲が狭い。3 種類を spec として明示することで:

- **deterministic**: lint watcher / test runner / metric collector 等、LLM
  不要な役割を Mind として組織図に組み込める
- **api**: 異 provider (= openai / gemini / 自前 LLM) を選択肢に入れる
  道を残す
- **human**: 人間 seat を Mind と同じ抽象で扱う (= dispatch を非同期で
  受け取る、ADR-0017 layer B)

## 新 Kind を追加する手順

1. このディレクトリに `<name>.md` を作る (frontmatter は上記スキーマに従う)
2. `runtime:` field を 4 値のどれかに設定 (= 未対応値は WARN される)
3. spawn-mind.sh / mind-loop.sh は runtime ごとに dispatch するので、
   既存 4 値以外を入れる場合は両 script の `case "${KIND_RUNTIME}"` を拡張
4. Reference Persona を `../personas/` に置く (= 利用者が「この Kind を
   使うとどんな Mind になるか」を読める)
5. `runtime/pillars/registry/test_registry.py` の `TestKindRuntime` に
   assertion を追加

## 関連 ADR

- ADR-0001 — フレームワーク本旨
- ADR-0002 — Mind / Kind の用語
- ADR-0011 — Pillar 編集不可
- ADR-0020 — `templates/` (同梱) vs `$AI_ORG_OS_HOME/` (実体) の overlay
- ADR-0021 — A axiom / B 宣言 / C 後天的依存注入 (本ディレクトリは C 層)
- ADR-0022 — kinds / personas / guilds / workspaces の責務
