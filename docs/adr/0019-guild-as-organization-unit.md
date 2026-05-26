# ADR-0019: Guild = 組織枠の物理表現と「組織パッケージ」の基礎

> 想定読者:
> - ai-org-os の差別化（組織を配布可能にする）を実装する人
> - Phase 5c (Mind 同士の運営層) を担当する人
> - Guild manifest / Axiom スキーマを設計するメンテナ
> - 「自分の組織を作って配りたい」エコシステム参加者

## Status

**Proposed** — 2026-05-24

## Context（背景）

### 1. 現状: 「組織」の構造体が無い

Phase 5b-4 までで以下が動いている:

- Mind は `spawn-mind.sh` で個体として作成できる
- Inbox に Issue を投入できる、Mind が自発的に `claim_issue` できる
- ADR-0017 で「組織は Mind の集合で構築する」(層 B) が確定

**しかし「組織」の構造体が存在しない。** ADR-0002 で `Guild` (組織枠) / `Guildmaster` (運営 Mind) の語彙だけ定義されたまま、実装には降りていない。結果として:

- 人間が個体名 (`alice`, `bob`) を直接指名して spawn / 依頼するしかない（`docs/manual-e2e-guide.md` の流れ）
- 「ある目的を共有する Mind の集合」を表現できない
- ある Issue を「どの Mind 集合の責任範囲か」を機械的に判定できない

### 2. 差別化の本丸: 「組織を配布する」

operator との 2026-05-24 の対話で言語化された差別化:

| 配布単位 | 何を渡してる | 提供元 |
|---|---|---|
| Skill | 個の能力 / 単一手順 | Claude Code (現状の唯一) |
| Framework (LangGraph 等) | 道具箱 | 多数 |
| **Mind / Manifest / 組織** | **思考主体・組織の構成定義・組織そのもの** | **ai-org-os** |

「Warden 経由の依頼導線」単体は LangGraph supervisor / CrewAI hierarchical と並ぶだけで差別化にならない。本丸は **「組織を `git clone` で配れる」** こと。それには Guild を **配布可能な物理ファイル** として定義する必要がある。

### 3. スタンス

memory `feedback-publish-concept-first` (2026-05-24) に固定済:

- **完成度 60% で発表する**
- 大手が真似してより良い実装を作るなら歓迎
- 「他社が真似したくなる完成度」より「他社が真似したくなる**概念の明確さ**」

本 ADR はこのスタンスに沿って、**最小限で「組織パッケージ」が成立する範囲** を切り出す。

## Decision（決定）

### 1. Guild の物理表現

> **2026-05-25 更新 (ADR-0020)**: 当初 `runtime/guilds/<name>/` に置く設計だったが、
> 「組織依存物は世界の構成 (runtime/) と物理分離する」という ADR-0020 を採用した
> ため、以下のように **templates + AI_ORG_OS_HOME の 2 layer overlay** に変更:
>
> 1. **同梱テンプレ**: `templates/guilds/<name>/` (ai-org-os repo 内、例示用)
> 2. **利用者の実体**: `$AI_ORG_OS_HOME/guilds/<name>/` (利用者所有、別 repo 可)
>
> Pillar は lookup 時、home → templates の順に探し、最初に見つかった manifest を
> 採用する。default Guild は templates 同梱なので、利用者が何もしなくても動く。

```
templates/guilds/<guild-name>/        ← 同梱テンプレ (ADR-0020 fallback 層)
├── manifest.md      # purpose, version, kind list, persona list, schema-version
└── axiom.md         # この Guild の不変項（claim 制約 / Mind 行動規範）

$AI_ORG_OS_HOME/guilds/<guild-name>/  ← 利用者の組織実体 (ADR-0020 overlay 上層)
├── manifest.md
└── axiom.md
```

Guild ディレクトリには **immutable な定義のみ** を置く (`manifest.md` + `axiom.md`)。runtime state (members / claim 履歴等) は一切含めない。

- **default Guild** は `templates/guilds/default/` に framework と同梱する。これは「コアが提供する出発点」(ADR-0011) であり、利用者は `$AI_ORG_OS_HOME/guilds/default/` で上書きするか、別名 Guild を追加して使う
- **ユーザー定義 Guild** は `$AI_ORG_OS_HOME/guilds/<name>/` に置く (Phase 5c-1 で実装、ADR-0018 / ADR-0020 整合)
- Guild ディレクトリは **そのまま `cp -r` / `git clone` で配布可能**: 受け取った人は `$AI_ORG_OS_HOME/guilds/<name>/` に配置すれば動く (本 ADR の「組織パッケージ」概念の物理表現)

#### Membership は派生状態（authoritative source は Mind registry）

> **2026-05-25 更新 (Phase 5c-2 P1 fix #91 Codex)**: 当初 authoritative source を `$AI_ORG_OS_HOME/minds/<name>/.mind-meta.md` の `guild:` フィールドとしていたが、これは Mind 自身の Mindspace 配下で **Mind が書き換え可能** だったため、caller-controlled flag による権限昇格 (axiom bypass) を許す穴になっていた。authoritative source を **`$AI_ORG_OS_HOME/registry/minds/<name>.md`** (Pillar 管理領域、ADR-0011 で Mind 不可侵) に移した。Mindspace 内 `.mind-meta.md` は informational copy として残るが、authz の根拠としては参照しない。

「現在その Guild に何の Mind が所属しているか」は `members.md` のような **authoritative ファイルを持たない**。所属の真実は **`$AI_ORG_OS_HOME/registry/minds/<name>.md`** の `guild:` フィールドであり、Guild の member 一覧は registry を走査して **集約する** (observe.py / claim_issue / nexus.py の axiom 強制で都度算出)。registry の書き換えは spawn-mind.sh / kill-mind.sh のみが行う (Pillar 管理)。

理由:
- ADR-0018 整合: framework (repo) には mutable state を置けない
- 単一情報源 (single source of truth): Mind 自身の所属を Mind の meta に持つ方が、整合性ズレが起きない (members.md と .mind-meta.md の二重管理を避ける)
- 集約コストは小さい: Mind 数は組織あたり数十〜数百のオーダーで、走査は十分高速

### 2. Manifest フォーマット (v0.1)

```markdown
---
guild: backend
schema_version: 0.1
purpose: バックエンド API の設計・実装・レビュー
kinds: [generic]
personas: [designer, implementer, reviewer]
created_at: 2026-05-24T00:00:00Z
---

# Guild: backend

(自由記述、人間 / Mind が読むための説明)
```

`schema_version` を最初から入れることで将来の lock-in を緩和する。

### 3. Axiom (v0.1 では最小)

```markdown
---
guild: backend
axioms:
  - id: claim-only-own-guild
    rule: Mind は所属 Guild の Issue のみ claim できる
    enforcement: mechanical  # Conduit Pillar で reject
---
```

v0.1 では `claim-only-own-guild` 1 つで十分。Axiom スキーマの本格仕様化は **ADR-0020 候補** として後続。

### 4. Mind の所属

- `spawn-mind.sh` に `--guild <name>` オプション追加 (省略時は `default`)
- `.mind-meta.md` に `guild:` フィールド追加 (= 所属の authoritative source、§1 参照)
- spawn 時に Guild manifest を確認し、指定された **`kind` が `manifest.kinds` に含まれている** こと、および **`persona` が `manifest.personas` に含まれている** ことを検証 (不一致なら spawn を拒否)

### 5. Inbox の Guild 振分け

- `submit-issue.sh` に `--guild <name>` オプション追加 (省略時は `default`)
- Issue frontmatter に `guild:` フィールド追加
- `claim_issue` (Conduit MCP) で **Mind の所属 Guild と Issue の Guild が一致しない場合は reject**
  → これが **Axiom 機械検証の最初の実装** であり、ADR-0017 §3 の層 B 構造化の最初のピース

### 6. Warden は Guild ロジックに踏み込まない (ADR-0017 整合)

- 拒否ロジックは **Conduit Pillar (MCP) で機械的に enforce** ← 「Warden が組織を仕切る」のではなく「規約を機械的に守らせる」
- Conductor / Observation は Guild サマリ (各 Guild の pending 数 / member 数) を出すだけ
- Judgment Pillar は Axiom 違反を Pillar 違反と同じく検出できる (将来拡張)

### 7. observe.py --realm への追加

統合ビューに Guild セクションを追加 (members は `.mind-meta.md` 走査による派生、§1 参照):

```
=== Guilds ===
default: members=2 (alice, bob), pending=3, claimed=1
backend: members=1 (charlie), pending=0, claimed=2
```

### 8. guildmaster Persona は v0.1 では実装しない

語彙としては ADR-0002 / ADR-0017 に残すが、本 ADR では実装対象外:

- 「60% 完成度で発表」スタンスに従い、Guild の物理表現 + claim reject の実演で十分
- 必要性が実例で示された段階で ADR-0015 §2 ルート (Persona 追加) で導入

## Consequences（影響）

### 利点

1. **「組織パッケージ」が成立する** — 差別化の本丸 (org-as-package) が実装に降りる
2. **Axiom 機械検証の最初の実装** — `claim-only-own-guild` という具体例で「公理で組織を守る」が動く
3. **ADR-0017 §3 の層 B が初めて構造を持つ** — 「Mind が pull する」だけだったのが「Guild 内 Mind が pull する」に進化
4. **発表の説得力** — 「組織を `git clone` で配れる」がデモで示せる。READMEに「Skill の上の配布単位」を pitch できる
5. **既存の本旨と整合** — Warden が組織を仕切らず、規約 (Axiom) を機械的に enforce する形

### 不利益 / リスク

1. **既存 API の拡張が必要** — `spawn-mind.sh` / `submit-issue.sh` / `claim_issue` MCP tool に `guild` パラメタが入る。後方互換のため省略時は `default` Guild に fall back
2. **Axiom スキーマの未確定** — v0.1 は `claim-only-own-guild` 1 つだけ。本格スキーマは ADR-0020 候補
3. **Manifest フォーマットの lock-in** — v0.1 で出した fmt を将来変えにくくなる。`schema_version` で緩和するが、最初の選択が長く残る
4. **Guild 間の交差ケース未定義** — 「複数 Guild にまたがる Issue」「default Guild との交差」など corner case は v0.1 では「単一 Guild 所属のみ」と割り切る
5. **「組織を配布」のセキュリティモデル未定義** — 信頼できない Guild manifest を `git clone` するリスク (Axiom が悪意ある内容)。v0.1 は「Realm 運用者が責任を持つ」前提

### 派生する Issue / 後続作業

- **Phase 5c-1**: 本 ADR の実装 (Guild 物理表現 + Mind 所属 + claim reject + observe)
- **Phase 5c-2**: default Guild サンプル / 発表テキスト / README pitch line 更新
- **Phase 5c-3 (後続)**: ユーザー定義 Guild (`$AI_ORG_OS_HOME/guilds/`)
- **ADR-0020 候補**: Axiom スキーマと検証規約 (v0.1 を超える本格化)
- **ADR-0021 候補**: Guild manifest の versioning / dependency / registry
- **guildmaster Persona の追加** (ADR-0015 §2 ルート、必要性が示された段階)
- **発表 (ブログ / OSS announcement)** — 「組織を配る OS」コンセプトを世に置く

## 代替案（不採用）

### A. Guild なし。Mind 直接指名のまま続ける

不採用理由:
- 差別化 (org-as-package) が消える。Skill / Framework との違いが薄く、「bash 起動の大袈裟版」(operator 評) のままになる
- ADR-0017 で確定した「組織は Mind の集合で構築する」が、実装上「集合の単位」が存在しないため空文化する

### B. Guild = Dispatch グラフから創発（構造体を持たない）

Mind 間通信履歴を分析して「事実上の Guild」を抽出する案。

不採用理由:
- 構造体が無いと **配布できない**。「組織を渡す」が成立しない（本 ADR の主目的に反する）
- 動的協調モデルとして将来は価値があるが、第一歩としては配布可能な静的構造が必要
- ADR-0001 の本旨「公理系を定義する」と整合しない（公理は動的に創発するものではない）

### C. Guild manifest を `$AI_ORG_OS_HOME` のみに置く

framework (repo) には何も置かず、すべてユーザー定義とする案。

不採用理由:
- default Guild がないと「Realm を立ち上げただけで動く最小例」を示せない
- 「他のプロジェクトと組み合わせるサンプル」が repo に無いと、最初の体験が成立しない
- ADR-0018 と整合する二段構成 (framework の default / runtime state のユーザー定義) を採用

### D. Warden が Guild ロジックを持つ (claim 拒否を Conductor が判定)

不採用理由:
- ADR-0017 違反。「組織は Mind の集合で構築する」本旨に反する
- 「Warden が万能 orchestrator になる」失敗パターン (ADR-0010 §5 と矛盾)
- Conduit (MCP) で規約を機械的に enforce する方が責務分離が綺麗

### E. ADR を起こさず暗黙運用で Guild ディレクトリを足す

不採用理由:
- 「組織パッケージ」は差別化の本丸 = 公式に宣言すべき設計
- 将来「Guild とは何か」を新規メンテナ / コントリビュータ / 利用者が問うたとき、ADR が無いと毎回口頭説明になる
- 発表時に「ADR-0019 で定義」と参照できる形が必要 (operator スタンス「概念の first mover」と整合)

## 関連

- [ADR-0001](0001-ai-org-os-as-invariant-framework.md) — ai-org-os = 開発組織の不変項を定義するフレームワーク。本 ADR で「配布可能な組織」を初めて実装に降ろす
- [ADR-0002](0002-vocabulary-and-meta-meta-structure.md) — Guild / Guildmaster の語彙定義
- [ADR-0010](0010-observation-philosophy-and-warden-as-collective.md) §5 — Warden = 機能集合体、Guild ロジックは Warden 内部に持たない
- [ADR-0011](0011-warden-claude-naming-and-separation.md) — Pillar 編集不可。Guild は Pillar ではなく **ユーザー編集領域** (Persona と同じ扱い)
- [ADR-0015](0015-persona-evolution-strategy.md) §2 — Persona 追加ルート。guildmaster Persona は将来候補
- [ADR-0017](0017-warden-monitoring-vs-job-monitoring.md) — 層 A / 層 B 分離。本 ADR は **層 B に初めて構造を与える**
- [ADR-0018](0018-runtime-home-separation.md) — framework / runtime state 分離。default Guild は framework、ユーザー Guild は将来 runtime state
- `docs/architecture-overview.md` — 現状俯瞰図 (本 ADR 実装後に更新が必要)
- Issue (TBD) — Phase 5c-1 実装トラッキング
