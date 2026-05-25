---
guild: default
schema_version: 0.1
purpose: ai-org-os の最小組織枠。Realm を立ち上げただけで動く既定の Guild
kinds: [generic]
personas: [designer, implementer, reviewer]
created_at: 2026-05-25T00:00:00Z
---

# Guild: default

> 想定読者:
> - 初めて ai-org-os を立ち上げる利用者
> - Guild 機能を試したいが自分で manifest を書く前段階の人
> - ユーザー定義 Guild の参考にする人

ai-org-os の **既定 Guild**。`--guild` オプションを指定せずに spawn-mind / submit-issue を叩いた場合、Mind / Issue はすべてこの Guild に所属する。

## メンバー構成

- **kinds**: `generic` のみ (現状 ai-org-os が提供する唯一の Kind)
- **personas**: `designer` / `implementer` / `reviewer` (汎用 3 職種)

新規 Persona / Kind を追加した場合は本 manifest の `kinds` / `personas` を更新するか、新しい Guild を `runtime/guilds/<name>/` に作る。

## Axiom

[`axiom.md`](axiom.md) 参照。v0.1 では `claim-only-own-guild` のみ。

## 派生情報 (members 一覧)

「現在この Guild に何の Mind が居るか」は本 manifest に含まれない (ADR-0019 §1)。所属の authoritative source は `$AI_ORG_OS_HOME/minds/<name>/.mind-meta.md` の `guild:` フィールド。一覧は `observe.py --realm` で派生表示される。

## 関連

- ADR-0019 — Guild = 組織枠の物理表現と「組織パッケージ」の基礎
- ADR-0017 — 層 A (Warden) と 層 B (Mind の組織) の分離
- ADR-0018 — framework (本ファイル) と runtime state (`.mind-meta.md`) の物理分離
