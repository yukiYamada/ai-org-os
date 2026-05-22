# 運営原則

> 想定読者: ai-org-os のコア規約（L2）を運用・改訂する立場の人（メンテナ、テックリード、移植先で本リポジトリを fork する人）。

これらは `docs/product_vision.md` が掲げる3軸（Build / Maintain / Share）を実現するための、ai-org-os 全体に効く規約である。各原則には「なぜそれが必要か（Why）」を併記する。

## 1. Document First
議論より先に最小の文書化を行い、前提を同期する。
- **Why**: AI と人間が同じ前提で判断するためには、暗黙知ではなく明示された文書が必要だから（Maintain）。

## 2. Decision Logging
意思決定は「背景 / 選択肢 / 決定 / 影響」を `teams/*/memory/decisions.md` に残す。
- **Why**: 学習ループ（L3）の原料であり、後続の AI/人間が判断を再現・修正できるようにするため（Maintain）。

## 3. Review Before Merge
実装は必ずレビューを通し、責務分離を保つ。
- **Why**: 自己改善する組織の安全装置。AI が暴走した変更を人間が遮断できる最後の境界（Maintain）。

## 4. Retrospective-driven Evolution
チームルールは固定せず、定期的に振り返って改善する。
- **Why**: 「学習ループが回っている証拠」（L3）を継続的に積み上げ、次世代バンドル（L1）の原料にするため（Maintain / Share）。

## 5. Portability-First（旧: Portable Team Design）
役割・運営・記憶をテンプレート化し、**L1 バンドルとして配布可能な粒度を維持する**。チーム固有の事情はバンドル外へ切り出し、コアは移植可能に保つ。
- **Why**: ai-org-os の商品本体は L1 バンドルであり、移植不能な構造はプロダクトとして成立しないから（Share）。

## 6. Vision-First
仕様・ドキュメント・ルールの新規追加および変更は、`docs/product_vision.md` の3軸（Build / Maintain / Share）のいずれかに寄与することを確認してから着手する。3軸に寄与しない変更は**やらない**か、**ビジョン側を更新する**。
- **Why**: SSOT であるビジョンと末端文書が乖離すると、組織全体の判断軸が壊れるから（Build / Maintain / Share すべて）。

## 7. Reader-Aware Documentation
全ての主要ドキュメント（README, brief, mission, role, principles, specs 等）は冒頭に「想定読者」を1行で明示し、その読者にとっての価値で書く。
- **Why**: 文書の受け手が AI か人間か、構築者か運用者か共有先かで必要な情報が変わる。読者を曖昧にすると Build / Maintain / Share いずれにも刺さらない文書が量産されるから。

---

関連: [`../docs/product_vision.md`](../docs/product_vision.md)
