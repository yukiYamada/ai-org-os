# ADR-0020: 世界の構成自体と注入される組織依存物の物理分離 (templates レイヤ導入)

> 想定読者:
> - ai-org-os を **テンプレートとして fork して自分の組織を作りたい** 人
> - Guild / Kind / Persona を「組織パッケージ」として独立配布したい人
> - `runtime/` 配下に何が居て / 居ないかを設計するメンテナ
> - Phase 5c-1 (Guild 実装) を担当するメンテナ

## Status

**Accepted** — 2026-05-25

## Context（背景）

ADR-0011 §3 で `runtime/` 配下に **Pillar (編集不可)** と **kinds / personas (編集可)** を共存させた。
ADR-0018 では framework (`runtime/`) と runtime state (`$AI_ORG_OS_HOME/`) を物理分離したが、その際 §5 で「`runtime/kinds/`, `runtime/personas/` は **コード扱い** (git tracked) のまま」と判断し、runtime/ 内に残した。
Phase 5c-1 (ADR-0019 / Guild 実装) でも同じ流儀を踏襲し、`runtime/guilds/default/` に Guild manifest を置いた。

### operator からの指摘 (顕在化)

Phase 5c-1 の実装報告時、operator が:

> またruntimeの中に実体をいれちゃってるの？runtimeは構成要素であって、manifestは実体だよね？
> テンプレートとしてつくりたかったりするなら、別のディレクトリきったほうがいいよね。
> 世界の構成自体と後から変更注入できる依存物はきちんとわけよう

### 何が見落とされていたか

ADR-0011 / ADR-0018 はそれぞれ「**編集権限軸**」「**更新サイクル軸**」で分離した。本来分けるべきもう 1 軸 — **「ai-org-os というシステム自体の構成」か「そのシステムに食わせる組織コンテンツ (依存物)」か** — は未整理だった:

| 軸 | 分けるもの | ADR |
|---|---|---|
| 編集権限 | Pillar (編集不可) vs ユーザー領域 (編集可) | ADR-0011 |
| 更新サイクル | framework (`git pull` で更新) vs runtime state (mutable) | ADR-0018 |
| **本質カテゴリ** | **世界の構成自体** vs **注入される依存物 (組織コンテンツ)** | **本 ADR** |

`kinds/` `personas/` `guilds/` は「ユーザー編集可」かつ「framework に同梱」だったので、ADR-0011 + ADR-0018 の 2 軸では `runtime/` の中に住むことに整合していた。しかし **本質的にはこれらは「組織パッケージ」= ai-org-os が動かす依存物**であって、ai-org-os 自体の構成要素 (Pillar 機構) ではない。同じ `runtime/` 配下に居るのは category error。

加えて ADR-0019 で「Guild = git clone で配れる組織パッケージ」と定義した以上、その物理表現を framework と物理的に混ぜたままでは「**組織だけ独立して配る**」が成立しない。

## Decision（決定）

### 1. 4 カテゴリの物理分離

| カテゴリ | 物理パス | 性質 | 編集者 |
|---|---|---|---|
| **世界の構成** (constitution) | `runtime/pillars/`, `runtime/host/`, `runtime/tests/`, ... | immutable, git tracked, framework upgrade で更新 | ai-org-os 開発者 |
| **同梱テンプレ** (template / 出発点) | `templates/{guilds,kinds,personas}/` | git tracked, 例示・bootstrap 用 | ai-org-os 開発者 |
| **組織依存物の実体** (manifest) | `$AI_ORG_OS_HOME/{guilds,kinds,personas}/` | git tracked **だが repo の外** (利用者が別 repo として持つ / git clone する) | 利用者 (Guildmaster) |
| **runtime state** (動的状態) | `$AI_ORG_OS_HOME/{minds,issues,snapshots,conduit-storage,...}` | mutable, untracked | system 生成 |

ADR-0018 の 2 root から **4 カテゴリ** に拡張。`templates/` が新カテゴリとして加わる。

### 2. ディレクトリ構造 (Phase 5c-1 適用後)

```
ai-org-os/                            ← repo (framework + テンプレ同梱)
├── runtime/                          ← 世界の構成
│   ├── pillars/                      ← Pillar 機構 (ADR-0011 §3 のまま)
│   ├── host/
│   └── tests/
├── templates/                        ← 同梱テンプレ (新規、本 ADR)
│   ├── guilds/
│   │   └── default/                  ← ADR-0019 の default Guild manifest はここ
│   ├── kinds/
│   │   └── generic.md
│   └── personas/
│       ├── designer.md
│       ├── implementer.md
│       └── reviewer.md
└── docs/

$AI_ORG_OS_HOME/                      ← 実行環境 (ADR-0018)
├── guilds/                           ← 利用者の組織 (実体、本 ADR)
│   ├── default/                      ← templates/guilds/default/ を上書き or 同名
│   └── backend/                      ← 利用者が追加した独自 Guild
├── kinds/                            ← 利用者の Kind 拡張 (本 ADR)
├── personas/                         ← 利用者の Persona 拡張 (本 ADR)
├── minds/                            ← runtime state (ADR-0018)
├── issues/
├── snapshots/
├── conduit-storage/
└── conductor-status.json
```

### 3. パス解決ルール: AI_ORG_OS_HOME 優先 → templates フォールバック

Guild / Kind / Persona の lookup は以下の順:

1. `$AI_ORG_OS_HOME/<category>/<name>/` が存在すればそれを使う (= 利用者の実体)
2. 無ければ `templates/<category>/<name>/` を使う (= ai-org-os 同梱の例示)
3. どちらにも無ければ `not found`

これにより:

- 何も触らない利用者: templates 経由で default Guild / generic Kind / 3 つの Persona が即動く
- カスタマイズしたい利用者: `$AI_ORG_OS_HOME/<category>/<name>/` に同名で置けばその場で上書き (templates は無視される)
- 完全新規組織を作る利用者: `$AI_ORG_OS_HOME/guilds/my-org/` だけ作れば独立した組織パッケージとして成立 (templates は使わない)
- 「組織パッケージ」を git clone で配る: `git clone <org-repo> $AI_ORG_OS_HOME/guilds/<name>` で配置完了

bootstrap copy (= templates を最初に `$AI_ORG_OS_HOME/` に全コピー) は採用しない。**lazy fallback** によって「テンプレ ≠ 実体」がランタイムで明示される。

### 4. 影響を受ける既存 ADR

| ADR | 該当箇所 | 本 ADR による更新 |
|---|---|---|
| **ADR-0011** | §3 ファイル配置の `runtime/kinds/`, `runtime/personas/` | 本 ADR で **撤回**。`templates/{kinds,personas}/` + `$AI_ORG_OS_HOME/{kinds,personas}/` に再配置 |
| **ADR-0018** | §5 「`runtime/kinds/`, `runtime/personas/` は **コード扱い** (git tracked) のまま」 | 本 ADR で **撤回**。組織依存物は別カテゴリとして物理分離 |
| **ADR-0019** | §1 Guild manifest 配置 (`runtime/guilds/<name>/`) | 本 ADR で **更新**。`templates/guilds/<name>/` + `$AI_ORG_OS_HOME/guilds/<name>/` に再配置 |

§3.1 の Designer 自問チェックリスト (CLAUDE.md) には本 ADR の軸を追加する: 「これは ADR-0020 の **構成 / テンプレ / 実体 / runtime state** どれ?」

### 5. ユーザー操作モデル (例)

**ケース A: 試しに触る人**
```
$ git clone <ai-org-os>
$ runtime/host/setup.sh
$ runtime/pillars/lifecycle/spawn-mind.sh generic designer alice
   → templates/guilds/default/manifest.md と templates/personas/designer.md が使われる
   → $AI_ORG_OS_HOME/minds/alice/ が作られる
```

**ケース B: 独自 Guild を作る人**
```
$ mkdir -p $AI_ORG_OS_HOME/guilds/backend
$ vi $AI_ORG_OS_HOME/guilds/backend/manifest.md
$ runtime/pillars/lifecycle/spawn-mind.sh --guild backend generic designer bob
```

**ケース C: 既存の組織パッケージを clone で配布する人**
```
$ git clone https://example.com/my-team-org.git $AI_ORG_OS_HOME/guilds/my-team
$ runtime/pillars/lifecycle/spawn-mind.sh --guild my-team generic designer carol
```

### 6. 機械的担保

- `templates/` 配下は ADR-0011 の Pillar 編集制御 (CODEOWNERS / pre-commit / CI) の対象**外**。テンプレ更新は通常の PR で OK。
- ただし本ファイル群を**実行時に書き換える**コード (`spawn-mind.sh` 等) が出てこないことを CI でチェックすることを推奨 (Phase 5c-2 以降の課題)。
- `$AI_ORG_OS_HOME/<category>/<name>/` は利用者所有。framework 側は read のみ。

## Consequences（影響）

### 利点

1. **「組織を git clone で配れる」(ADR-0019 §核心) が成立**: 組織パッケージが framework から物理的に独立、別 repo として配布可能
2. **テンプレ vs 実体が明示**: 「default Guild の manifest を直したい」と思った時に「これはテンプレ (= ai-org-os に投げ返す PR) なのか、自分の実体 (= 自分の repo) なのか」が path で一目瞭然
3. **framework upgrade が完全に non-destructive**: `git pull` で利用者の組織は一切影響を受けない (templates の更新は read-only fallback として届くだけ)
4. **既存利用者の移行コストほぼゼロ**: lazy fallback により、`$AI_ORG_OS_HOME/<category>/` が空でも templates 経由で従来通り動く
5. **3 軸が揃った設計**: 編集権限 (ADR-0011) / 更新サイクル (ADR-0018) / 本質カテゴリ (本 ADR) の 3 軸が独立に整理され、新規ファイルの配置判断が機械的に決まる

### 不利益 / リスク

1. **ディレクトリ移動 PR の規模**: `runtime/kinds/`, `runtime/personas/`, `runtime/guilds/` を `templates/` に `git mv` し、参照箇所 (Pillar コード / shell / Dockerfile / tests / docs) を全部更新する必要あり
2. **lookup 2 段階の覚えるコスト**: 「これは templates? それとも `$AI_ORG_OS_HOME`?」を一瞬考える必要がある (CLI で `--show-source` のような diagnostic を将来追加すると緩和)
3. **テンプレと実体が同名のとき注意**: 利用者が `$AI_ORG_OS_HOME/guilds/default/` を作ると templates の default は完全に隠れる。意図しない override に気付きにくい (将来的に observe.py で「source: home / template」を表示すると緩和)
4. **テスト fixture 修正**: ADR-0018 で `$AI_ORG_OS_HOME` 経由になっていたテストはそのままだが、`templates/` 直 read を前提とするテスト (test_registry の `TestRealRuntimeKinds` 等) は path を書き換える必要

### 派生する Issue / 後続作業

- **Phase 5c-1 本 PR 内**: ディレクトリ移動 + パス解決変更 + 影響 ADR (0011 / 0018 / 0019) への追記 / 撤回マーク + CLAUDE.md §3.1 チェックリスト更新
- **Phase 5c-2 以降**: `observe.py --realm` で各 Guild / Kind / Persona の source (template vs home) を表示
- **将来**: `templates/` 自体を別 repo (ai-org-os-templates) に切り出す案も検討余地あり (今はやらない、依存関係を増やさない)

## 代替案（不採用）

### A. 現状維持 (`runtime/{kinds,personas,guilds}/` に置き続ける)

不採用理由:
- カテゴリミスを引き継ぐ → 将来 Guild / Kind / Persona を独立配布したくなった時に大規模 refactor が必要
- ADR-0019 「組織を git clone で配れる」が物理表現できない
- operator 指摘そのもの: 「runtimeは構成要素であって、manifestは実体」

### B. templates/ を作らず、ai-org-os 自体に default 系を bundle しない

利用者は必ず自分で default Guild / generic Kind / Persona を作る、という案。

不採用理由:
- bootstrap が重い (試しに触る人が `spawn-mind.sh` 1 発で動かせない)
- 「ai-org-os を試す」の入口が遠ざかる
- v0.1 として配布できる完成度に達しない

### C. `runtime/templates/` のように runtime/ 内に置く

物理パス的には簡単な案。

不採用理由:
- `runtime/` の意味がまた曖昧になる (= 元の問題に戻る)
- 「templates と実体は別物」が path から読めない
- 外部から「組織パッケージだけ取り出す」が見えにくい (templates/ が独立トップだから視認性高い)

### D. bootstrap copy 方式 (`setup.sh` で templates → `$AI_ORG_OS_HOME/` に全コピー)

利用者は最初から実体だけ触る、という案。

不採用理由:
- 「テンプレ ≠ 実体」がランタイムで見えなくなる (どっちもファイルとして存在する状態)
- ai-org-os の framework upgrade で templates が更新されても、利用者の `$AI_ORG_OS_HOME/` には届かない (copy 一度きり)
- 「templates をベースに自分用に少し変えた」場合、原本との diff が取れない
- 利用者は「実体は自分で書く / 必要なら clone してくる」が組織パッケージ思想

### E. XDG_DATA_HOME / `$AI_ORG_OS_TEMPLATES_DIR` のように env 経由で完全カスタマイズ

unconfigured な利用者でも templates パスを env で差し替え可、とする案。

不採用理由:
- 過剰 (env を 2 つ覚える必要、エラー診断も複雑化)
- ADR-0018 で「単一 root `$AI_ORG_OS_HOME` でメンタルモデルを単純化」と決めた方針と矛盾
- 必要になったら後付け可能 (今やる理由がない)

## 関連

- [ADR-0011](0011-warden-claude-naming-and-separation.md) — Pillar / 編集権限の境界 (本 ADR で §3 を一部撤回 / 更新)
- [ADR-0017](0017-warden-monitoring-vs-job-monitoring.md) — 層 A / 層 B 分離 (本 ADR は層 B 側で扱うコンテンツの物理表現)
- [ADR-0018](0018-runtime-home-separation.md) — framework / runtime state 分離 (本 ADR で §5 を一部撤回 / 更新)
- [ADR-0019](0019-guild-as-organization-unit.md) — Guild = 組織パッケージ (本 ADR がその物理表現を完成させる)
- `CLAUDE.md` §3.1 — Designer 視点のチェックリスト (本 ADR の軸を追加)
- Phase 5c-1 (`runtime/guilds/default/` を作ろうとしたきっかけ、本 ADR で配置を訂正)
