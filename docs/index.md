---
layout: default
title: ai-org-os
---

# ai-org-os

> **「開発組織そのものを git clone で配れる」フレームワーク**

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](../LICENSE)
[![Version](https://img.shields.io/badge/version-1.0.0-green.svg)](../CHANGELOG.md)

## What problem does it solve?

**既存の AI agent tools はこうだった**:
- ❌ **個別の Skill を積み上げる** — 「コード書ける agent」「review できる agent」を個別に作る
- ❌ **Framework を組み合わせる** — LangChain + AutoGPT + 自作 glue code で繋ぐ
- ❌ **「誰がどこまで信頼できるか」が曖昧** — agent が main に直 push? レビューは誰?
- ❌ **組織のルールが optional / best practice** — 「PR 経由で merge」は人間が覚えておく

→ **結果**: 1人で使う便利 tool にはなるが、「組織として安全に委任できる単位」にはならない

**ai-org-os はこうする**:
- ✅ **組織そのものを配布単位にする** — Persona (役割) + Guild (枠) + Axiom (強制) を manifest 化
- ✅ **Trust boundary を機械強制** — L1 (Mind 内部) / L2 (Mind 間通信) / L3 (外界) の境界を Axiom で守る
- ✅ **Issue 投入 → PR 作成を無人化** — guildmaster (振り分け) → implementer (実装) → reviewer (査読) → 人間 (merge)
- ✅ **`git clone` で組織を配れる** — 「うちの開発組織」を丸ごと配布・カスタマイズ可能

## What is ai-org-os?

**開発組織の不変項（公理系）を定義・強制するフレームワーク**。

- **Realm**: Docker container として動作する仮想開発組織環境
- **Warden**: Realm を監視し、Mind に働きかける世界そのもの（観察→判断→働きかけループ）
- **Mind**: 組織内で働く思考個体（claude プロセス）が Persona に従って動的に生成・作業・消滅
- **Axiom**: 機械的に強制される不変項（例: claim-only-own-guild, trust-boundary）

組織の構成（Persona / Guild / Workspace / Kind）を manifest として宣言することで、Issue 投入から PR 作成までを Mind が自律的に処理します。

**Dogfooding 実績**: Issue 投入 → guildmaster 振り分け → alice claim → bob 実装 → carol review → **PR #154 が main に merge** (2026-06-03)

## Core Concepts

| 概念 | 説明 |
|---|---|
| **Realm** | ai-org-os のルール適用範囲（Docker container） |
| **Warden** | Realm の守護者、観察→判断→働きかけのループで世界を運営 |
| **Mind** | 思考個体（claude プロセス）、Persona に従って作業 |
| **Mindspace** | Mind 個別の不可侵領域（記憶・状態） |
| **Guild** | 目的を共有する Mind の集合体（論理セグメント） |
| **Axiom** | 機械的に強制される不変項（例: claim-only-own-guild） |
| **Persona** | Mind の役割・振る舞いガイド（宣言的指示） |
| **Dispatch** | Mind 間の明示的通信（topic + body） |

## Features

### Phase 5f: Mind に任せられる Realm (✅ 完了 2026-06-03)

- **多 Mind orchestration**: Persona 駆動で複数 Mind が chain 処理
- **実 PR 作成**: Mind が実コードを書き、PR を作成・人間が merge
- **信頼境界 axiom**: Trust boundary (ADR-0027) に基づく L1/L2/L3 分離
- **失敗ハンドリング**: Per-cycle timeout / error streak / auto_kill / notify-human

**Dogfooding 実績**: Issue 投入 → guildmaster → alice → bob (実装) → carol (review) → PR #154 merge

### Phase 5g.A: Framework foundation v2 (✅ 完了 2026-06-09)

Primitive 完成度を上げ、他人が `git clone` で利用可能に。

- **Persona composition**: `mixins: [...]` で共通 section を集約
- **Schema validation**: C 層 manifest の型検証 + overlay lookup
- **Contract harness**: 宣言的ルールの machine-readable 化 + drift detection
- **Framework versioning**: `runtime/VERSION` + `framework_version: ">=X.Y"` constraint
- **Kind diversity**: `claude` / `deterministic` / `api` / `human` の 4 runtime

### Phase 5g.B: 箱庭 v2 (進行中)

物理基盤 + 観察強化。

- **Observability** (✅): `observe.py --trace / --cost / --status / --chain`
- **L3 notify**: 外部 push 通知（Slack webhook / email 等）
- **Mindspace persistence**: `kill-mind --preserve` + `spawn-mind --restore-from`
- **WSL/Linux 移行** (進行中): OS-level sandbox + 本旨 Linux/Docker 前提との整合

## Quick Start

### Prerequisites

- Docker (for Realm container)
- Git
- Claude Code CLI (for Mind runtime=claude)

### Setup

```bash
# Clone the repository
git clone https://github.com/yukiYamada/ai-org-os.git
cd ai-org-os

# Run setup (creates home directory + default Guild)
./runtime/pillars/setup/setup.sh

# Start Realm (Warden observation loop)
./runtime/pillars/setup/startup.sh

# Spawn first Mind
./runtime/pillars/lifecycle/spawn-mind.sh alice default

# Post an Issue (Mind will claim and process it)
./runtime/pillars/conduit/issue.py create "Fix bug in utility.py" \
  --body "The parse function returns None for empty input"
```

詳細な体験手順: [10分体験ガイド](manual-e2e-guide.md)

## Documentation

- **[ADR (Architecture Decision Records)](adr/)** — 設計判断の確定記録（ADR-0001〜0028）
- **[CLAUDE.md](../CLAUDE.md)** — プロジェクト本旨と設計チェックリスト
- **[CHANGELOG.md](../CHANGELOG.md)** — Framework versioning + SemVer
- **[Architecture Overview](architecture-overview.md)** — 実装の現状を 1 枚で
- **[Manual E2E Guide](manual-e2e-guide.md)** — セットアップから claim までの体験手順

### Key ADRs

| ADR | タイトル | 内容 |
|---|---|---|
| [0001](adr/0001-ai-org-os-as-invariant-framework.md) | Invariant framework | ai-org-os の本質定義 |
| [0002](adr/0002-vocabulary-and-meta-meta-structure.md) | Vocabulary | 用語と構造の整理 |
| [0011](adr/0011-mindspace-inviolability.md) | Mindspace 不可侵 | Mind 個別領域の保護 |
| [0017](adr/0017-warden-vs-mind-orchestration.md) | Warden vs Mind 組織化 | 監視と作業の責務分離 |
| [0021](adr/0021-axiom-persona-manifest-stratification.md) | A/B/C 分類 | Axiom / Persona / Manifest の層分離 |
| [0027](adr/0027-trust-boundary-axiom.md) | Trust boundary | L1/L2/L3 信頼境界 |
| [0028](adr/0028-operational-mapping-after-phase-5f.md) | Operational mapping | Phase 5f 完了後の運用戦略 |

## Roadmap

- ✅ **Phase 5a-5e** (〜2026-05-30): 不変項フレームワーク + Warden 双方向 outer loop
- ✅ **Phase 5f** (〜2026-06-03): Mind に任せられる Realm（多 Mind + 実 PR + 失敗扱い）
- ✅ **Phase 5g.A** (〜2026-06-09): Framework foundation v2（composition + schema + versioning + Kind diversity）
- 🚧 **Phase 5g.B** (進行中): 箱庭 v2（物理基盤 + 観察強化）
- 📋 **Phase 6** (未定): Public release + 外部利用者 onboarding

## Design Philosophy

1. **公理系アプローチ**: 開発組織の不変項を定義・機械強制
2. **思考のネットワーク**: 組織 = 共通目的をもった思考の集合体
3. **境界付き委任**: Trust boundary で責務を明確化
4. **デファクト候補ポジション**: 大手が真似して良いの作るなら歓迎

## Why not just use subagents + skills?

**「サブエージェント + skills で足りるのでは？」への回答**:

ai-org-os は Claude のサブエージェント機能では実装できません。理由:

| 観点 | サブエージェント + Skills | ai-org-os (Realm) |
|---|---|---|
| **存在** | 呼ばれた時だけ動いて消える | **24/7 永続的に動く** |
| **能動性** | 受動的（親が呼ぶ） | **能動的（自発的に動く）** |
| **ルール** | Anthropic / 親のルール下 | **独自ルール（Axiom）を機械強制** |
| **通信** | 親経由のみ | **Mind 間で直接通信（Dispatch）** |
| **記憶** | コンテキスト独立 | **Mindspace の不可侵原則がルール化** |

具体例:
- **サブエージェント**: 「レビューして」と呼ばれたら review して結果を返す → 親が終わったら消える
- **ai-org-os**: Issue が投入されたら guildmaster が気付き → alice に振り分け → bob が実装 → carol が review → PR 作成 → 人間が merge（**親が居ない間も勝手に動く**）

**「呼び出し可能な処理単位」と「住人として存在する主体」は質が違う**。

ai-org-os = **AI 思考のための仮想空間（virtual world）**。Minecraft サーバーやメタバースに近い構造を、AI 開発組織の目的に特化させたもの。

詳細: [ADR-0002 §10](adr/0002-vocabulary-and-meta-meta-structure.md)

## Differentiation

既存の AI agent framework との違い:

| 概念 | 従来 (LangChain / AutoGPT 等) | ai-org-os |
|---|---|---|
| **配布単位** | Skill（個）/ Framework（道具） | **組織そのもの**（Persona + Guild + Axiom） |
| **強制力** | optional / best practice | **Axiom（機械強制）** |
| **信頼境界** | 曖昧（agent が何をやるか不明瞭） | **L1/L2/L3 明示**（Mind 内部 / Mind 間 / 外界） |
| **責務分離** | 1 agent に全部やらせる | **役割分担**（振り分け / 実装 / 査読 / merge） |
| **再現性** | prompt + code の組み合わせ | **Manifest + Framework versioning** |

例: 「PR を main に直 push せず、必ず review 経由で merge」を守らせる

- **従来**: prompt に書く → agent が守るかは運次第 → 事故ったら人間が気付いて直す
- **ai-org-os**: Trust boundary axiom (ADR-0027) で L3 (main branch push) を機械強制 → Mind が PR 作成まで、人間が merge を担当

## Contributing

現在は dogfooding phase（内部検証中）。外部 contribution の受け入れは Phase 6 以降を予定。

## License

[MIT License](../LICENSE)

## Links

- **GitHub**: [yukiYamada/ai-org-os](https://github.com/yukiYamada/ai-org-os)
- **Issues**: [Issue Tracker](https://github.com/yukiYamada/ai-org-os/issues)
- **Discussions**: [GitHub Discussions](https://github.com/yukiYamada/ai-org-os/discussions)

---

*Last updated: 2026-06-20 (Phase 5g.B)*
