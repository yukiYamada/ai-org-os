# Architecture (Initial)

> 想定読者: ai-org-os の構造設計に関わる Architect / Engineer / Reviewer。
> このアーキテクチャは [Product Vision](../../../docs/product_vision.md) の 3 軸に従う。

## Core design
- Git as the persistence layer.
- Markdown as the first interface.
- Directories as organizational boundaries.
- Teams as reusable units.
- Projects as work targets.
- Memory as decision, retrospective, and learning logs.

## Three-layer model (L1 / L2 / L3)

ai-org-os の成果物は 3 層で構成され、それぞれ Vision の 3 軸に対応する：

| 層 | ディレクトリ | 役割 | 主に担う軸 |
|---|---|---|---|
| **L1: Product OS Bundles** | `L1_product-os-bundles/` | 移植可能な「学習済み AI 開発チームのバンドル」（本ツールの出力物） | **Share**（および Build の出発点） |
| **L2: Product Core OS** | `L2_product-core-os/` | コア規約・強制手段（guardrails / roles / workflow） | **Maintain**（および Build の足場） |
| **L3: OS Learning Records** | `L3_os-learning-records/` | 運用で得た判断・学習・改善履歴 | **Maintain**（学習ループの証拠）→ 次世代 L1 の原料 |

L1 は本ツールの直接的な商品であり、空のまま L2/L3 を肥大化させないこと。

## Intentional exclusions
Future application/runtime layers (orchestrator, UI, billing, marketplace) may be added later, but are intentionally excluded from the initial commit.

---

関連: [Product Vision](../../../docs/product_vision.md) / [Requirements](./requirements.md)
