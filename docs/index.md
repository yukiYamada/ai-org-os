---
layout: default
title: ai-org-os
---

# ai-org-os

> **開発組織の不変項（公理系）を定義するフレームワーク**

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](../LICENSE)
[![Version](https://img.shields.io/badge/version-1.0.0-green.svg)](../CHANGELOG.md)

## What is ai-org-os?

ai-org-os は「**開発組織そのものを git clone で配れる**」ことを可能にするフレームワークです。

- **Framework**: 開発組織の不変項（Axiom）を定義・強制する
- **Realm**: Docker container として動作する仮想開発組織環境
- **Mind**: 組織内で働く思考個体（claude プロセス）が動的に生成・作業・消滅する
- **Warden**: Realm を監視し、必要に応じて Mind に働きかける世界そのもの

組織の構成（Persona / Guild / Workspace / Kind）を manifest として宣言することで、Issue 投入から PR 作成までを Mind が自律的に処理します。

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

## Differentiation

既存の AI agent framework との違い:

| 概念 | 従来 | ai-org-os |
|---|---|---|
| 配布単位 | Skill（個） / Framework（道具） | **組織そのもの** |
| 構成 | コード + config | **Manifest（公理＋宣言＋依存注入）** |
| 強制 | optional / best practice | **Axiom（機械強制）** |
| 境界 | 曖昧 | **Trust boundary（L1/L2/L3）** |

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
