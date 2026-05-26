---
guild: default
schema_version: 0.1
axioms:
  - id: claim-only-own-guild
    rule: Mind は所属 Guild の Issue のみ claim できる
    category: 指示 (instruction)
    enforcement: mechanical
    enforced_by: runtime/pillars/conduit/nexus.py (claim_issue)
  - id: guildmaster-only-spawn
    rule: Mind を spawn できるのは persona=guildmaster の Mind のみ
    category: 指示 (instruction)
    enforcement: mechanical
    enforced_by: runtime/pillars/conduit/nexus.py (spawn_mind)
  - id: guildmaster-only-kill
    rule: Mind を kill できるのは「同 Guild 所属の persona=guildmaster」のみ、自殺は禁止
    category: 指示 (instruction)
    enforcement: mechanical
    enforced_by: runtime/pillars/conduit/nexus.py (kill_mind)
    note: |
      spawn と対称の axiom (Phase 5c-3)。自 Guild 外への kill 不可 + self-kill 不可。
      最後の Guildmaster や独り Mind の撤収は人間が kill-mind.sh で行う (ADR-0012)。
  - id: read-others-inbox-only-by-guildmaster
    rule: 他 Mind の Dispatch inbox を読めるのは「自分と同じ Guild に所属する persona=guildmaster の Mind」のみ
    category: 監視 (observation)
    enforcement: mechanical
    enforced_by: runtime/pillars/conduit/nexus.py (read_inbox, target_mind 指定時)
    note: |
      Guildmaster であっても自 Guild の外の Mind は監視できない (Codex P1 #91)。
      claim-only-own-guild と同じ Guild 隔離の思想。Phase 5c-2 で導入時に
      同 Guild 境界チェックを追加。
---

# Axioms for Guild: default

> 想定読者:
> - Mind が axiom 違反で reject されたとき「なぜ?」を確認する人
> - Guildmaster 運営層の権限境界を理解したい人
> - Axiom 機械検証の実装サンプルを読みたいメンテナ

## 本 Guild に効く axiom 一覧 (Phase 5c-2 時点)

ADR-0021 で定義した通り、Guild axiom は **inter-Mind 関係の「指示」「監視」の可否のみ** を規定する。以下 4 つはすべてこの軸に乗っている。

### `claim-only-own-guild` (指示)

**ルール**: Mind は **自分が所属する Guild の Issue のみ** claim できる。

**Why**: Guild 間の責任分界を機械的に保つ (ADR-0017 層 B の最初の構造)。

**Enforcement**: `runtime/pillars/conduit/nexus.py` の `claim_issue` MCP tool が `mind.guild != issue.guild` の場合 `code: forbidden` で reject。

### `guildmaster-only-spawn` (指示) — Phase 5c-2

**ルール**: 新しい Mind を spawn できるのは **persona が `guildmaster` の Mind のみ**。spawn される Mind は発令 Mind と同じ Guild に所属する。

**Why**: Mind の増減判断は組織の運営判断であり、designer / implementer / reviewer 等の作業 Persona には委ねない。運営層 (Guildmaster) を独立した責務として明示する (ADR-0021 「指示の可否」)。

**Enforcement**: `runtime/pillars/conduit/nexus.py` の `spawn_mind` MCP tool が、発令 Mind の `.mind-meta.md` の `persona:` フィールドを参照し、`guildmaster` でなければ `code: forbidden` で reject。

**注意**: 人間が CLI 経由で叩く `spawn-mind.sh` は ADR-0012 で人間が Realm 外なので本 axiom 適用外 (人間は Realm の外側からこの仕組みを起動・撤収する立場)。

### `guildmaster-only-kill` (指示) — Phase 5c-3

**ルール**: Mind を kill できるのは **「自分と同じ Guild に所属する persona=`guildmaster` の Mind」** のみ。さらに **自分自身を kill することは禁止** (self-kill 不可)。

**Why**: spawn と対称な運営判断 (ADR-0021 「指示の可否」)。同時に 2 つの安全側制約:

1. **同 Guild 境界**: Guildmaster は自 Guild の運営層であって、他 Guild の Mind を撤収する立場ではない (claim-only-own-guild / read-others-inbox-only-by-guildmaster と同じ Guild 隔離思想)。
2. **self-kill 不可**: 自分自身を消す処理は MCP server 自体が subprocess 完了前に死ぬため中途半端な状態を生む。最後の Guildmaster や独りきりの Mind を撤収するのは **人間が `kill-mind.sh` を CLI 直叩き** で行う (ADR-0012、人間は Realm 外)。これにより「組織の最後の Mind は組織自身では消せない」という不変項が成立する。

**Enforcement**: `runtime/pillars/conduit/nexus.py` の `kill_mind` MCP tool が以下 3 段階チェック:
1. 発令 Mind の persona が `guildmaster` か (persona check)
2. `mind_name == target_mind` でないか (self-kill check)
3. 発令 Mind と target Mind が同じ Guild か (same-guild boundary)

いずれかが満たされなければ `code: forbidden`。通れば既存 `kill-mind.sh` を subprocess で呼び出し、shell 側の registry-first 削除順序 (Codex P2 #91) を再利用する。

**注意**: `kill-mind.sh` の CLI 直叩きは ADR-0012 で人間が Realm 外なので本 axiom 適用外 (上述の self-kill / 最後の Guildmaster ケースを救う退路)。

### `read-others-inbox-only-by-guildmaster` (監視) — Phase 5c-2

**ルール**: 自分以外の Mind の Dispatch inbox を読めるのは **自分と同じ Guild に所属する persona=`guildmaster` の Mind のみ**。自分の inbox を読むのは誰でも可 (= 既存の identity binding のみで OK)。

**Why**: 配下 Mind の沈黙 / 詰まりを観察できないと運営層が機能しない。一方で全 Mind が互いを覗ける状態は組織として健全でない (= プライバシーと責任分担)。**さらに Guildmaster であっても自 Guild の外の Mind は監視できない** — claim-only-own-guild と同じ Guild 隔離の思想で、Guildmaster は自 Guild の運営層であって全 Realm の監視者ではない (Codex P1 #91、Phase 5c-2 で boundary 追加)。

**Enforcement**: `runtime/pillars/conduit/nexus.py` の `read_inbox` MCP tool が、`target_mind` が `mind_name` と異なる場合に 2 段階チェック:
1. 発令 Mind の persona が `guildmaster` か (persona check)
2. 発令 Mind と target Mind が同じ Guild か (same-guild boundary)

どちらかが満たされなければ `code: forbidden`。

## 違反時の挙動

各 axiom は MCP tool が以下のような JSON を返す:

```json
{
  "ok": false,
  "code": "forbidden",
  "error": "forbidden: ... (axiom: <axiom-id>)",
  ...
}
```

Mind 側 (Persona) はこの応答を受けて自分のロジックに反映する。

## 利用者が overlay する場合

`$AI_ORG_OS_HOME/guilds/default/axiom.md` を作って本 axiom セットを差し替えることは **技術的には可能だが推奨しない**。axiom は Guild の本質 (= 指示・監視の境界) であり、利用者が外すと組織の整合性が崩れる。axiom を変更する場合は新しい Guild を作る (`$AI_ORG_OS_HOME/guilds/<別名>/`)。

これは ADR-0021 の方針: **axiom (A) は Guild の本質、manifest の他フィールド (purpose / kinds / personas) は依存注入 (C)**。axiom を上書きすると Guild の identity が変わる、と考える。

## 関連

- ADR-0019 §3 — Axiom v0.1 フォーマット (Phase 5c-1)
- ADR-0021 — axiom (A) と依存注入 (C) の分離、Guild axiom は「指示・監視の可否」限定
- ADR-0017 — 層 A / 層 B 分離 (本 Axiom セットは層 B の運営構造)
- ADR-0008 — identity binding (Mind が自分以外を名乗れない、本 axiom より低レイヤ)
- `templates/personas/guildmaster.md` — Guildmaster Persona の判断ガイド (B)
