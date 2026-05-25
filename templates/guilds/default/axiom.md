---
guild: default
schema_version: 0.1
axioms:
  - id: claim-only-own-guild
    rule: Mind は所属 Guild の Issue のみ claim できる
    enforcement: mechanical
    enforced_by: runtime/pillars/conduit/nexus.py (claim_issue)
---

# Axioms for Guild: default

> 想定読者:
> - Mind が claim 拒否されたとき「なぜ?」を確認する人
> - Axiom 機械検証の最初の実装サンプルを読みたいメンテナ

## v0.1 で enforce される axiom

### `claim-only-own-guild`

**ルール**: Mind は **自分が所属する Guild の Issue のみ** claim できる。

**Why**: 「組織を Mind の集合で構築する」(ADR-0017) の最初の構造化。Guild 間の責任分界を機械的に保つ。

**Enforcement**: `runtime/pillars/conduit/nexus.py` の `claim_issue` MCP tool が、`mind.guild != issue.guild` の場合 `code: forbidden` で reject する。

**例外**: 無し (v0.1 では Guild の cross-claim は一切認めない)。

## 違反時の挙動

`claim_issue` MCP tool が以下を返す:

```json
{
  "ok": false,
  "error": "forbidden: mind '<name>' belongs to guild '<a>', but issue belongs to guild '<b>'",
  "code": "forbidden"
}
```

Mind 側はこれを受けて、自分の Guild の Issue だけを claim するロジックを Persona 内で持つ。

## 関連

- ADR-0019 §3 — Axiom v0.1 フォーマット
- ADR-0008 — identity binding (同じレイヤーで動く別の機械検証)
- ADR-0017 — 層 A / 層 B 分離 (本 Axiom は層 B の最初の構造)
