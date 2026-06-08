---
kind: api
version: 0.1
status: spec
runtime: api
---

# Kind: API (spec only)

> 想定読者: openai / gemini / 他 LLM provider を直接叩く Mind を作りたい人。
>
> **本 Kind は Phase 5g.A #169 の spec 段階**。実装は将来の PR で。spawn は
> `runtime-not-implemented` を返す。

## なぜ API Kind が要るか

`generic` Kind は claude CLI に依存している (= Mind == claude code 前提)。
他 LLM provider を組織に組み込むには、API Kind が必要:

- OpenAI (gpt-4 / gpt-4o / o1) を Mind body にしたい
- Gemini (1.5 pro / 2.0) を Mind body にしたい
- ローカル LLM (Ollama / llama.cpp) を Mind body にしたい

これらは **同じ Persona / Guild / Workspace / Dispatch 仕組み** に乗ったまま
LLM 部分だけを差し替えたい、というニーズに応える。

## Body Spec (spec only)

| 項目 | 値 | 備考 |
|---|---|---|
| **runtime** | Python script that wraps an HTTP API client | provider 別に sub-runtime |
| **execution** | `runtime/pillars/lifecycle/runtime-api.py` (= 未実装) | mind-loop.sh が dispatch |
| **mindspace** | CLAUDE.md を **system prompt** として送る | dispatch は MCP ではなく直接 storage を叩く |
| **tools** | tool use API (= function calling) | provider 別に schema 異なる |
| **secret** | `~/.ai-org-os/secrets/<kind>.env` に API key | spawn 前に存在必須 |
| **lifecycle** | claude と同じ (mind-loop.sh が外側) | cycle body のみが差し替わる |

## 設計上の懸念 (= 実装時に決める)

- **provider 差異**: openai と gemini で tool use schema が違う。1 Kind で
  両対応するか、`kind: openai-api` / `kind: gemini-api` と分けるか
- **system prompt の組み立て**: Persona body をそのまま system prompt に
  入れるか、構造化して送るか
- **inbox / dispatch の取り扱い**: MCP server を使わない場合、storage.py を
  直接呼ぶ shim が要る
- **cost meter**: claude と同じ `mind-loop.jsonl` event に cost 情報を載せる
  ためには provider response の usage を parse する必要がある (= 5g.B #172
  の cost meter と連動)
- **secret 管理**: `.mcp.json` が claude path で MCP server 起動コマンドに
  AI_ORG_OS_MIND_NAME を渡しているのと同じ流儀で、API key を env で渡す枠が要る

## Phase 5g.A における扱い

spec only。spawn-mind.sh は kind=api を見ても spawn は完了するが、
`mind-loop.sh` が「api runtime is not implemented yet」と stderr に
emit して exit 1 する (= 利用者が Mind を spawn しても loop が回らない、
それを明示する)。

## 実装する時の参考

- spec only Persona: [`../personas/api-default.md`](../personas/api-default.md)
  (= spec のみ、実装 PR で具体化)
- 連動する箱庭 v2 (#165): cost meter (#172) と組み合わせて per-cycle cost を
  記録できると organizational economics が見える

## 関連 ADR

- ADR-0021 — A / B / C 軸 (本 Kind は C 層)
- ADR-0022 — kinds / personas / guilds / workspaces
