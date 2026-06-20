---
layout: default
title: Architecture Decision Records
---

# Architecture Decision Records (ADR)

ai-org-os の設計判断の確定記録。ADR は時系列順に並び、後の ADR は前の ADR を前提とする。

> **読み方**: 新規参入者は ADR-0001 → 0002 の順に読むことを推奨。各 ADR は独立せず、前の判断を積み上げる形で記述されている。

---

## Core Foundation (不変項フレームワークの定義)

| ADR | タイトル | 内容 |
|---|---|---|
| [0001](0001-ai-org-os-as-invariant-framework.md) | ai-org-os as Invariant Framework | **本質定義**: 開発組織の不変項（公理系）を定義するフレームワーク |
| [0002](0002-vocabulary-and-meta-meta-structure.md) | Vocabulary and Meta-meta Structure | 用語整理（Realm / Warden / Mind / Mindspace 等） |
| [0003](0003-docker-and-phase-2-design.md) | Docker and Phase 2 Design | Docker container としての Realm 実装方針 |

---

## Communication & Identity (通信と識別)

| ADR | タイトル | 内容 |
|---|---|---|
| [0004](0004-dispatch-and-phase-3-design.md) | Dispatch and Phase 3 Design | Mind 間の明示的通信（Dispatch） |
| [0005](0005-phase-3-mcp-direct-with-nexus.md) | MCP Direct with Nexus | Nexus（MCP サーバー）の設計 |
| [0007](0007-phase-3-reliability-properties.md) | Phase 3 Reliability Properties | 通信の信頼性特性 |
| [0008](0008-nexus-identity-binding.md) | Nexus Identity Binding | Mind の identity と認可 |

---

## Realm & Warden (世界と守護者)

| ADR | タイトル | 内容 |
|---|---|---|
| [0006](0006-phase-5-realm-warden-guildmaster.md) | Phase 5: Realm, Warden, Guildmaster | Realm の構造と Warden の役割 |
| [0010](0010-observation-philosophy-and-warden-as-collective.md) | Observation Philosophy | Warden の観察哲学 |
| [0013](0013-warden-as-framework-immutability.md) | Warden as Framework Immutability | Warden は framework code、編集不可（ADR-0011 とセット） |

---

## Mindspace & Boundaries (記憶と境界)

| ADR | タイトル | 内容 |
|---|---|---|
| [0011](0011-mindspace-inviolability.md) | **Mindspace Inviolability** | Mind 個別領域の不可侵原則（最重要 axiom） |
| [0012](0012-human-in-the-realm.md) | Human in the Realm | 人間の 5 責務（setup / monitor / intervene / judge / learn） |
| [0014](0014-physical-boundary-taxonomy.md) | Physical Boundary Taxonomy | 物理境界の 4 カテゴリ（A/B/C/D） |
| [0016](0016-container-vs-host-partitioning.md) | Container vs Host Partitioning | Container（コア） vs Host（Mind） の分割 |

---

## Organization & Orchestration (組織化とオーケストレーション)

| ADR | タイトル | 内容 |
|---|---|---|
| [0015](0015-guildmaster-vs-operational-concern.md) | Guildmaster vs Operational Concern | Guildmaster の役割再定義 |
| [0017](0017-warden-vs-mind-orchestration.md) | **Warden vs Mind Orchestration** | 監視（Warden）と作業（Mind）の責務分離 |
| [0019](0019-realm-inbox-unified-dispatch-routing.md) | Realm Inbox | 統合 dispatch routing（Realm Inbox 導入） |

---

## Configuration & Dependencies (構成と依存注入)

| ADR | タイトル | 内容 |
|---|---|---|
| [0018](0018-framework-vs-runtime-state.md) | Framework vs Runtime State | git tracked（framework） vs untracked（runtime state） |
| [0020](0020-runtime-config-templates-dependencies.md) | Runtime / Config / Templates / Dependencies | 4 カテゴリ分離（構成 / 同梱 / 依存物 / state） |
| [0021](0021-axiom-persona-manifest-stratification.md) | **Axiom / Persona / Manifest Stratification** | A 層（機械強制） / B 層（宣言指示） / C 層（依存注入） |
| [0022](0022-c-layer-subcategory-kinds-personas-guilds-workspaces.md) | C Layer Subcategory | C 層の 4 サブカテゴリ（Kind / Persona / Guild / Workspace） |

---

## Framework Foundation v2 (Phase 5g.A)

| ADR | タイトル | 内容 |
|---|---|---|
| [0023](0023-persona-composition-primitive.md) | Persona Composition | `mixins: [...]` による Persona 共通 section 集約 |
| [0024](0024-c-layer-schema-validation.md) | C Layer Schema Validation | manifest の型検証 + overlay lookup |
| [0025](0025-persona-contract-harness.md) | Persona Contract Harness | 宣言的ルールの machine-readable 化 + drift detection |
| [0026](0026-framework-versioning-discipline.md) | Framework Versioning | `runtime/VERSION` + SemVer + migration discipline |

---

## Trust & Operations (信頼境界と運用)

| ADR | タイトル | 内容 |
|---|---|---|
| [0027](0027-trust-boundary-axiom.md) | **Trust Boundary Axiom** | L1（内側） / L2（外部依存） / L3（人間） の信頼境界 |
| [0028](0028-operational-mapping-after-phase-5f.md) | Operational Mapping | Phase 5f 完了後の運用戦略（timeout / error / notify） |

---

## External Relations (外部連携)

| ADR | タイトル | 内容 |
|---|---|---|
| [0009](0009-relationship-with-bash-editor-and-claude-team.md) | Relationship with bash-editor and Claude Team | 外部ツールとの関係整理 |

---

## 読み順の推奨

### 初めての人（5 分で概要把握）

1. [ADR-0001](0001-ai-org-os-as-invariant-framework.md) — 本質定義
2. [ADR-0002](0002-vocabulary-and-meta-meta-structure.md) — 用語整理
3. [ADR-0021](0021-axiom-persona-manifest-stratification.md) — A/B/C 分類

### 実装者（設計意図を理解する）

1. ADR-0001〜0003 — Foundation
2. ADR-0011 — Mindspace 不可侵（最重要）
3. ADR-0017 — Warden vs Mind 分離
4. ADR-0021 — A/B/C 分類
5. ADR-0027 — Trust boundary
6. ADR-0028 — Operational mapping

### 全体を通読する場合

番号順（0001 → 0028）に読むと、設計判断の系譜が分かる。

---

*Total: 28 ADRs (as of 2026-06-20)*
