# Persona templates

このディレクトリは ai-org-os に同梱される **Persona テンプレ** (= ADR-0021 の
C 層 — 利用者の Guild から参照される依存物の実体) を置く場所です。
Persona は Mindspace に CLAUDE.md として配置され、Mind に「思考の癖」を与えます。

- `designer.md` — 設計判断 (複数案 / トレードオフ)
- `implementer.md` — 実装判断 (最小差分 / テスト先行)
- `reviewer.md` — レビュー判断 (仕様適合 / リスク列挙)
- `guildmaster.md` — Guild 運営 (spawn / kill / 観察)

mixin (= 共通 section の集約) は `templates/persona-mixins/` 配下。

## frontmatter スキーマ

各 Persona は frontmatter (= ファイル先頭の `---` で挟まれた領域) に最低限の
メタデータを宣言します:

```yaml
---
persona: <name>          # 必須、ファイル名 stem と一致
version: <semver>        # 必須
status: <experimental|stable|deprecated>  # 必須
mixins: [<mixin1>, ...]  # 任意 (Phase 5g.A #166)
---
```

## Persona Contract (Phase 5g.A #168)

Persona prose は B 宣言 (= ADR-0021、機械強制されない LLM 向け文書) ですが、
**「PR を merge してはいけない」のような重要なルール** は machine-readable に
再宣言できます。これを **Persona Contract** と呼びます。

contract field は frontmatter に **任意で** 追加します:

```yaml
---
persona: reviewer
version: 0.1
status: experimental
mixins: [mindspace-info]
inbound_topics: [review-request]
outbound_topics: [review-reply]
forbidden_ops: [gh pr merge, gh pr review --approve, gh pr close, ...]
cycle_budget_seconds_max: 60
trust_layer: L1
---
```

| field | 意味 |
|---|---|
| `inbound_topics` | この Persona が dispatch として受け取る topic 一覧 |
| `outbound_topics` | この Persona が dispatch として送る topic 一覧 |
| `forbidden_ops` | この Persona が実行してはいけない operation (= ADR-0027 L1 の machine-readable 化) |
| `cycle_budget_seconds_max` | 1 cycle 上限目安 (= #144 / #134 由来の数値化) |
| `trust_layer` | ADR-0027 の信頼境界 layer (L1 / L2 / L3) |

### なぜ contract が要るか

Persona prose の文章を更新したが「`gh pr merge` を禁止」のリストから 1 項目を
うっかり消した、というような **silent regression** を CI で検知するため。

contract は prose の subset を機械可読化したもので、test harness が:

1. contract に書いた `forbidden_ops` がすべて prose body に substring として
   現れることを確認 (= drift detection)
2. virtual dispatch を投げて Persona が宣言通りの inbound / outbound を扱うか
   確認 (= LLM を呼ばない deterministic 検証)

を実施します。

### Persona を書いたら test を書く

新しい Persona を追加するときは、以下を必ず宣言してください:

- `cycle_budget_seconds_max`: 全 Persona 必須 (= governance、Phase 5f #134 由来)
- `inbound_topics` / `outbound_topics`: dispatch を扱う Persona は宣言推奨
- `forbidden_ops`: 信頼境界に関わる Persona (= L1 を持つもの) は宣言推奨

そして `runtime/pillars/registry/test_persona_contract.py` の
`TestRealPersonas` に新 Persona の assertion を追加してください。

### CLI

```bash
# contract を表示
python runtime/pillars/registry/persona_contract.py show reviewer

# contract と body の drift を検査 (= CI で実行)
python runtime/pillars/registry/persona_contract.py check reviewer
# → exit 0 = no drift / exit 1 = drift / exit 2 = error
```

### 演習: regression が CI で red になる demo

以下を手元で試すと、test harness が drift を検知することが確認できます:

```bash
# (1) reviewer.md の forbidden_ops から "gh pr merge" を一時的に削除
# (2) test を走らせる
$ cd runtime/pillars/registry && python -m unittest test_persona_contract -v
# → test_reviewer_forbids_pr_merge / test_no_template_persona_has_drift が red
# (3) git checkout templates/personas/reviewer.md で復元
```

逆方向の drift (= prose から `gh pr merge` を削除したが contract は残したまま)
も同じく `test_no_template_persona_has_drift` で検知されます。

## 関連 ADR

- ADR-0020 — 世界の構成 vs 同梱テンプレ vs 依存物の実体
- ADR-0021 — A axiom / B 宣言 / C 後天的依存注入
- ADR-0022 — kinds / personas / guilds / workspaces の責務
- ADR-0027 — 信頼境界 L1 / L2 / L3
- ADR-0028 — 機械強制 (per-cycle timeout / error streak / notify-human)
