---
kind: deterministic
version: 0.1
status: experimental
runtime: deterministic
---

# Kind: Deterministic

> 想定読者: Mind を生成する Guildmaster / Warden、および「LLM を呼ばずに
> 動かしたい Mind」(= lint watcher / test runner / file scanner 等) を組む人。

Kind は Mind の **Body 性能** (= 動かす器のスペック) を定義する。本 Kind は
**決定的 script を Mind body にする** Kind であり、LLM を呼ばないため API key
不要、credit 消費ゼロ、再現性が完全に保証される。

## なぜ deterministic Kind が要るか

`generic` Kind (= claude) は LLM 呼び出しのため:

- 確率的 (= 同じ入力で違う出力)
- credit 消費
- API key 必須
- 応答 latency が大きい

一方、組織には **決定的に走ってほしい役割** がある:

- **lint watcher**: PR / commit を観察して lint 結果を dispatch する
- **test runner**: 指定 trigger で test を走らせて結果を dispatch する
- **file scanner**: 特定パターンのファイルを inbox queue から検出する
- **metric collector**: 一定間隔で Realm metric を集約する

これらは LLM ではなく **shell script / python script** が body 実装になる。
deterministic Kind はそれを表現する。

## Body Spec

| 項目 | 値 | 備考 |
|---|---|---|
| **runtime** | shell script (bash) or python script | LLM 不要 |
| **execution** | `runtime/pillars/lifecycle/runtime-deterministic.sh` が 1 cycle 担当 | mind-loop.sh が dispatch |
| **mindspace** | Persona = `CLAUDE.md` ではなく **`body.sh` を実行** する経路 | `.mcp.json` 不要 |
| **tools** | shell から呼べるもの全部 (= MCP は使わない) | dispatch は `inbox.py` / `submit-issue.sh` 等を直接呼ぶ |
| **resources** | host が許す範囲 | Phase 2 で Warden が制限 |
| **lifecycle** | claude と同じ (= spawn / kill / mind-loop.sh が外側を回す) | cycle body のみが差し替わる |

## Phase 5g.A における Body の振る舞い

1. **spawn**: `spawn-mind.sh <deterministic> <persona> <mind-name>`
   - `.mcp.json` は配置しない (= MCP server に接続しない)
   - Persona は CLAUDE.md として配置 (= 人間メンテナが Mind の意図を読むため)
   - Mindspace 直下に `body.sh` を Persona から取り出して配置する (Persona が
     code-fenced bash block を持つ規約、§Persona convention 参照)
2. **mind-loop.sh の cycle body**:
   - `Kind.runtime == "deterministic"` を見て `runtime-deterministic.sh` に
     委譲する
   - `runtime-deterministic.sh` は Mindspace 内 `body.sh` を 1 回実行
   - exit code / stdout / stderr を `mind-loop.jsonl` event に記録 (claude
     path と同じ schema)
3. **kill-mind**: claude path と同じ (= SIGTERM、Mindspace 削除)

## Persona convention (deterministic 用)

deterministic Kind の Mind は **Persona の特定セクション** から body script を
取り出して実行する。Persona は人間 (= LLM ではない) が読むためのドキュメントを
兼ねる:

```markdown
# Persona: file-scanner

> deterministic Kind 用 Persona。1 cycle で
> `~/.ai-org-os/issues/inbox/` を走査して issue 数を dispatch する。

## body

\`\`\`bash
#!/usr/bin/env bash
set -euo pipefail
count=$(ls "${AI_ORG_OS_HOME}/issues/inbox/" 2>/dev/null | wc -l)
echo "inbox count: ${count}"
exit 0
\`\`\`
```

spawn-mind.sh は Persona の最初の ` ```bash ... ``` ` ブロックを `body.sh`
として Mindspace に書き出す。

## 不変条件

- LLM を呼ばない (= 確率的挙動を持ち込まない)
- Mindspace 不可侵性は同じ (= 他 Mind から読み書き不能)
- 思考の能動性 = 外側ループは同じ (= ADR-0010 §3 の "idle なし")
- 1 cycle 完走したら exit。`runtime-deterministic.sh` がループしない (= mind-loop.sh が回す)

## 関連 ADR

- ADR-0001 — フレームワーク定義 (Mind / Kind の概念)
- ADR-0011 — Pillar 編集不可
- ADR-0021 — A axiom / B 宣言 / C 後天的依存注入 (本 Kind は C 層)
- ADR-0022 — kinds / personas / guilds / workspaces の責務

## 関連ファイル

- Reference Persona: [`../personas/watcher.md`](../personas/watcher.md)
- Cycle body runner: `runtime/pillars/lifecycle/runtime-deterministic.sh`
