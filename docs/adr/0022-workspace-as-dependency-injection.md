# ADR-0022: Mind の作業環境 (Workspace) を C 依存注入として導入する

> 想定読者:
> - Phase 5d 以降で「Mind に実コードを書かせる」段に着手するメンテナ
> - spawn-mind / kill-mind に新引数を追加しようとする人
> - 「Mind が git にアクセスするのは axiom?」と迷ったセッション
> - 別組織パッケージ (ai-org-os fork) を作って独自の開発環境に乗せ替えたい人

## Status

**Accepted** — 2026-05-27

## Context（背景）

ai-org-os の本旨は **「開発組織の不変項を定義するフレームワーク」** (ADR-0001)。だが Phase 5c-3 (PR #92) と Observation v1.0 (PR #95) 完了直後の dogfooding (2026-05-26) で、operator から本質的な指摘が来た:

> 開発チームをつくれる、って環境だから、mind が git にアクセスできないとつらくない？
>
> git にアクセスする、とかできる事態は依存注入に近いんだけど（開発環境をどうするかは本来組織とか mind の話だから）デフォルトのテンプレートとしては用意しておきたいよね。

それまでの実装で揃ったのは:
- **社会的構造** (Guild + Guildmaster + Persona)
- **観測層** (Warden 内部 + Mind 自己観察 + 統合 JSON)
- **機械強制 axiom** (claim-only-own-guild / guildmaster-only-spawn / guildmaster-only-kill / read-others-inbox-only-by-guildmaster)
- **identity binding** (ADR-0008)

しかし Mind が **実コードを書く** 手段が定義されていない。Mindspace (`$AI_ORG_OS_HOME/minds/<name>/`) は CLAUDE.md (Persona) + .mcp.json (Nexus 接続) + .mind-meta.md (informational) を置く Mind 固有領域であり、git 連携 / repo 構造 / branch 規約は持たない。これでは「開発組織」を名乗っても **コードを書けない組織** になってしまう。

ADR-0021 の A/B/C 軸に照らすと:

| 候補 | カテゴリ | 妥当性 |
|---|---|---|
| 「Mind は git を使わねばならない」を axiom 化 | A | ✗ 嘘になる。markdown だけ書く組織、SVN を使う組織、何も VCS を使わない組織もありうる |
| 「PR を出すとき conventional commit に従う」を Persona に書く | B | ⚪ 一部該当 (Persona 内の振る舞いガイド) だが、**作業環境そのもの** の指定にはならない |
| 「この組織は GitHub on `~/dev/foo` で開発する」を依存注入として外から差し込む | C | ✅ 本質的にここ |

→ **Workspace は完全に C カテゴリ**。axiom (A) にすると「開発組織」の意味を framework が決めつけてしまう (= 「組織パッケージ」思想の崩壊、ADR-0019)。Persona (B) は振る舞いガイドであって作業環境の物理指定ではない。

そして「ai-org-os 本体は **デフォルトテンプレートを同梱** し、利用者が overlay で差し替える」という思想は既に kinds / personas / guilds の 3 カテゴリで実装済み (ADR-0020)。**Workspace を 4 つ目のテンプレートカテゴリに加える** のが自然な拡張である。

## Decision（決定）

### 1. Workspace = C 依存注入の新サブカテゴリ

Mind の作業環境を **Workspace** と命名し、ADR-0021 の C カテゴリに属する **4 番目のテンプレートカテゴリ** として正式に追加する。

物理レイアウトは ADR-0020 と同じ 2 層 overlay:

```
templates/workspaces/<name>.md       # 同梱テンプレ (ai-org-os 本体に内包)
$AI_ORG_OS_HOME/workspaces/<name>.md # 利用者 overlay (優先される)
```

Workspace は「**この Mind がどこで / どう開発するか**」を宣言する manifest。Workspace 自体は機械強制 (axiom) ではなく、Pillar コードが解釈する **構成情報**。利用者は overlay で自由に差し替えてよい。

### 2. Workspace template が宣言する項目 (v0.1)

```yaml
---
workspace: <name>            # = ファイル名と一致
schema_version: "0.1"
purpose: <organizational rationale>
vcs: git | none              # VCS の種別。none なら git 操作なし
repo: <path or env var>      # 対象 repo の path (vcs=git 時のみ必須)
mode: worktree | shared      # Mindspace 内に worktree を作る / 親 repo を share する
branch_prefix: <prefix>      # spawn 時の自動 branch 命名 (例: mind/<name>)
allowed_cli: [git, gh, ...]  # Mind が利用可能と想定する CLI 一覧 (ヒント、機械強制ではない)
---

# Workspace: <name>

利用者向けの説明。Mind の CLAUDE.md に追記される (Persona に append される形)。
```

> `vcs: git` + `mode: worktree` がデフォルト推奨。`mode: shared` は 1 つの repo を複数 Mind が同時に触る (= 隔離が崩れる) ので非推奨だが、単発 Mind や教育用途のために残す。

### 3. 物理レイアウト: 「Mindspace = git worktree」モデル (mode=worktree 時)

`spawn-mind.sh --workspace <name>` を渡したとき:

1. Workspace template を 2 層 overlay で解決
2. `vcs: git` + `mode: worktree` なら:
   - `git -C <repo> worktree add <Mindspace> -b <branch_prefix>/<mind_name>` で Mindspace を worktree として作成
   - 既存の Mind ファイル (CLAUDE.md / .mcp.json / .mind-meta.md) は `.git/info/exclude` か Mindspace 内の隔離 subdir (`.mind/`) で worktree の git 管理対象から外す
3. Mind は自分の Mindspace で `git status` / `git diff` / `git commit` を叩くと自分の作業 branch が見える
4. `kill-mind.sh` は Mindspace の rm 前に `git worktree remove --force <Mindspace>` を実行 (登録解除)

この設計の利点:

- **隔離が物理保証される**: 各 Mind は別 worktree 上で別 branch なので、他 Mind の作業中ファイルを覗けない (ADR-0014 Mindspace 不可侵の精神を実装で保証)
- **Mindspace の位置が変わらない**: ADR-0018 (`$AI_ORG_OS_HOME/minds/<name>/`) の合意を破らない、worktree が **Mindspace そのもの**
- **既存 Persona / Nexus 接続が温存される**: CLAUDE.md / .mcp.json は git 管理外なので spawn ごとの上書きが従来通り
- **kill = worktree remove**: Mind の死とともに作業中の untracked 変更が消えるのは **意図的** (組織として「未保存の作業は引き継がない」=「同期は Dispatch / PR 経由で行え」を強制)

### 4. Workspace の解決優先順位 (spawn-mind 時)

spawn-mind が workspace 名を決める順:

1. **`--workspace <name>` 引数** (最優先、明示的注入)
2. **Guild manifest の `workspace: <name>` フィールド** (Guild の組織既定、未指定なら次へ)
3. **`default`** (templates/workspaces/default.md にフォールバック)

これにより:
- 個別 spawn で workspace を明示注入できる (柔軟性)
- Guild ごとに「この組織はこれで開発する」を既定できる (組織パッケージ思想)
- 何も指定しなければ ai-org-os 同梱の default が動く (out-of-the-box experience)

### 5. ai-org-os が同梱するデフォルトテンプレート

| name | vcs | mode | 目的 |
|---|---|---|---|
| `developer-default` | git | worktree | 一般的な開発組織 (GitHub + git/gh CLI + worktree per Mind) |
| `docs-only` | none | — | git なし、Mindspace 内で markdown 編集のみ (例: 文書チームのみの組織) |
| `readonly-analysis` | git | shared (read-only suggested) | 既存 repo を読むだけの分析 Mind (commit/push しない想定、ヒント) |

`developer-default` がほぼ全利用ケースをカバー。残る 2 つは「他にも世界がある」ことを示すための **見本** (Workspace = C 依存注入の証左)。

### 6. Workspace は axiom ではない、機械強制しない

`allowed_cli` / `branch_prefix` 等は **ヒント** であり機械強制しない。Mind が実際にどの CLI を使うか、どの branch 名で commit するかは **Persona (B)** と **Mind の判断** に任せる。framework は:

- worktree の生成・破棄 (= 物理的な配線)
- Mindspace ↔ repo の物理結線

までを行い、その上で **何をどう書くか** は Persona の責務とする。

これは ADR-0021 の方針:

> A (axiom) は「指示・監視の可否」のみ。組織が決めることは axiom にしない。

を Workspace にも貫徹したもの。Workspace は組織 (= 利用者) が決めることだから C にとどめる。

### 7. 既存 ADR との関係

- **ADR-0014** (物理境界): Workspace 導入により Mindspace (カテゴリ A 内側) は **同時に git worktree (カテゴリ C 外部依存への結線)** となる。これは A/C の物理的接続点ができる新しい状態。本 ADR は **この接続が「Mindspace を worktree という形で外側に通じさせる」** ことを認める。Mindspace 不可侵 (他 Mind が覗かない) は worktree 単位で物理保証される (= 強化)
- **ADR-0017** (Warden vs Mind 監視): 層 B (Mind の組織) が「実コードを書く」までを射程に入れる拡張。Warden (層 A) は Workspace の中身 (= コード) には立ち入らず、Mindspace 内の dirent 名 / stat / Conduit storage の frontmatter までしか観察しない (Observation Pillar 自主規制を Workspace でも維持)
- **ADR-0018** (runtime home 分離): Mindspace の物理位置 (`$AI_ORG_OS_HOME/minds/<name>/`) は変えない。Workspace は **Mindspace を worktree 化する** 形で実装され、新しい dir 階層は導入しない
- **ADR-0019** (Guild = 組織枠): Guild manifest に optional `workspace:` フィールドを追加することで「組織既定の開発環境」を表現できる。Guild = 組織パッケージという立場と整合
- **ADR-0020** (構成 vs 依存物): Workspace は完全に「依存物」カテゴリ (templates/ + AI_ORG_OS_HOME overlay)。本 ADR は ADR-0020 の物理分離規則をそのまま流用
- **ADR-0021** (axiom vs DI): C カテゴリの 4 番目のサブカテゴリとして Workspace を追加。A/B/C 軸の判別ルールを Workspace にも適用 (「Workspace は機械強制しない、構成情報として注入される」)

### 8. Phase 5d / 後続作業への接続

本 ADR を最初の commit に同梱する Phase 5d (Workspace MVP) シリーズ:

1. **PR #1**: `templates/workspaces/<name>.md` カテゴリ導入 + `registry.py` 相当の workspace lookup ロジック (parse / overlay / shadow consistency)
2. **PR #2**: `spawn-mind.sh --workspace <name>` 引数 + Mindspace = worktree モデル実装 (vcs=git + mode=worktree)
3. **PR #3**: `kill-mind.sh` で worktree remove も実行 + 失敗時の整合性 (= Mindspace は消えたが worktree 登録は残る、を避ける)
4. **PR #4**: Guild manifest の optional `workspace:` フィールド + デフォルト解決順 (引数 > Guild > default)
5. **PR #5**: `developer-default` / `docs-only` / `readonly-analysis` テンプレ整備
6. **PR #6**: dogfooding (Mind に実コードを書かせる E2E)

各 PR は機械強制系の影響範囲が大きい (spawn / kill の物理動作変更) ので Codex review + self-review + 回帰テストを厳密に通す。

## Consequences（影響）

### 利点

1. **本旨完成への決定打**: ai-org-os が「開発組織のフレームワーク」を本当に名乗れるようになる。Mind に実コードを書かせる物理基盤ができる
2. **組織パッケージ思想の完成**: 別組織 (= 別 fork) は `templates/workspaces/<custom>.md` を作って overlay すれば、まったく違う開発スタックに乗せ替えられる。git 以外も受け入れられる
3. **隔離の物理保証**: worktree per Mind により「他 Mind の作業中ファイルを覗かない」が **branch 隔離レベルで物理的に成立**。Mindspace 不可侵 (ADR-0014) の精神が VCS 層でも保たれる
4. **kill の意味が強化される**: kill = worktree remove なので、未保存の作業は消える。Mind は「進捗を保存したければ Dispatch (= 連絡) か commit + PR で外に出せ」と強制される (= organizational disciplined behavior)
5. **C 軸の 4 つ目として軸が揃う**: kinds / personas / guilds / workspaces の 4 カテゴリで「組織のあらゆる依存物が overlay 可能」が完成する

### 不利益 / リスク

1. **spawn-mind の責務が広がる**: Mindspace 作成 + .mcp.json 配置 + worktree 作成 まで担当する。エラーパスが複雑になる (worktree 作成失敗、branch 衝突、repo path 不在 等)。各失敗で Mindspace 残骸が出ないよう atomic な rollback が必要
2. **kill-mind の責務も広がる**: Mindspace 削除前に worktree 登録解除、worktree 解除失敗時の対処、未 commit の変更の扱い (warn + force remove)。Codex P2 で過去に踏んだ「先消し後消しの順序」(#91) と同じ慎重さが必要
3. **「Mindspace = worktree」の境界が増える物理状態**: Mindspace (カテゴリ A 内側) と repo (カテゴリ C 外部) が **同じファイルシステム位置で接続される**。新しい物理境界カテゴリ (E?) を ADR-0014 に追加するかどうかは別 ADR で判断 (本 ADR スコープ外、必要なら ADR-0014 update)
4. **既存利用者の互換**: 現状 0 利用者だが、`--workspace` 引数省略時のデフォルトを `developer-default` にすると **既存の spawn-mind スクリプト呼び出しが変わる** (突然 git worktree を作ろうとする)。これを避けるために **過渡期は `vcs: none` の `default` テンプレを用意** し、明示的に `--workspace developer-default` を渡したときだけ worktree モードに入る。互換重視
5. **Windows 環境での挙動差**: dogfooding 2026-05-26 で発覚した cp932 問題と同じく、Windows の git CLI 起動 + path 解決で踏む可能性。Phase 5d 各 PR で Windows + Linux 両環境で回帰テストする
6. **Persona (B) との接続点**: Workspace template の末尾を Mind の CLAUDE.md に append する場合、Persona と Workspace の両方が「お前は何者で何をしろ」を語る → 矛盾が出ないように Persona は「役割」、Workspace は「作業環境」と責務分離を Persona ガイドで明示する

### 派生する Issue / 後続作業

- **Phase 5d (Workspace MVP)**: 本 ADR の方針で `templates/workspaces/` + spawn-mind / kill-mind 更新 + Guild manifest 拡張 + デフォルトテンプレ (3 つ)
- **本物の dogfooding**: Workspace 完成後、2-3 Mind 体制で「実 Issue → 実コード変更 → PR」までを Mind だけで回す E2E。これが ai-org-os の真の動作確認
- **Judgment Pillar (#38) 統合**: Workspace 完成後、「観る (Observation) → 判断する (Judgment) → 動かす (Lifecycle + Workspace)」のループが閉じる。これで ai-org-os は「世界として自走する」段階に入る
- **ADR-0014 update 検討**: 「Mindspace ↔ repo 接続点」が新しい物理境界カテゴリ (E) として整理が必要か、別 ADR で判断
- **CLAUDE.md §3.1 チェックリスト更新**: 「これは Workspace template か、Persona か、Guild manifest か?」の自問項目を追加 (本 PR 内で対応)

## 代替案（不採用）

### A. Mind に git アクセスを axiom 化する

「すべての Mind は git CLI を使える / Mindspace は worktree である」を axiom (A) として固定する案。

**不採用理由**:
- 「開発組織」の意味を framework が決めつけてしまう。markdown 編集のみの組織、SVN を使う組織、何も VCS を持たない組織を排除する
- ADR-0019 「組織を git clone で配れる」(= 組織パッケージ) 思想の崩壊。利用者は VCS スタックを自由に選べなくなる
- ADR-0021 「A は指示・監視の可否のみ」の規律違反 (組織が決めることを framework が axiom 化)

### B. Mind に shared repo + branch 命名規約 だけ与える (worktree なし)

Mindspace とは別に `$AI_ORG_OS_HOME/workspace/<repo>` のような共有 repo を 1 つ置き、Mind は branch 名規約で隔離する案。

**不採用理由**:
- 隔離が **命名規約に依存する** ことになり、機械強制が弱い (= Mind が違う branch を上書きするリスク)
- 複数 Mind が同時に同じ working tree を読み書きすると競合が起きる (git index lock 等)
- Mindspace 不可侵 (ADR-0014) の精神が VCS 層に拡張されない
- 「**並走する Mind は別 worktree**」の方が物理的に綺麗で、git の機能でちょうど解決できる

### C. Mind を repo に chdir させて、Mindspace 外で開発させる

Mindspace は Persona / Nexus 接続のみ、実開発は外部 repo を `cd` して行う案。

**不採用理由**:
- Mindspace と作業位置が乖離する → kill 時に「Mind は消えたが repo 上の未 commit 変更は残る」状態が起きる
- Mind の identity binding (`AI_ORG_OS_MIND_NAME` = Mindspace dir 名) と作業位置の関連が薄れる
- Observation Pillar の「Mindspace 内の状態を観察する」が無意味化する (実状態は外部 repo)
- 「**Mindspace = Mind の物理アイデンティティ + 作業場所**」を一致させる方が ADR-0014 / 0017 / 0018 と整合する

### D. Workspace を Persona (B) の一部として書く

Persona ファイル末尾に「あなたの作業 dir は X、branch は Y」と記述する案。

**不採用理由**:
- 機械強制が無いので Mind が守る保証なし (= 隔離が崩れる)
- Persona は「振る舞いガイド」、Workspace は「物理結線」。両者を混ぜると ADR-0021 の B/C 区別が崩れる
- 利用者が overlay する時、Persona を書き換えれば Workspace も巻き込まれてしまう (= 構成変更の単位が大きすぎる)

### E. ADR を起こさず実装を先行させる

Phase 5d 各 PR の中で必要に応じて設計判断を都度行う案。

**不採用理由**:
- ADR-0019 (Guild) / ADR-0020 (templates 分離) / ADR-0021 (A/B/C 軸) の 3 件で、「先に ADR を確定してから実装に入る」の方が後でブレない、と既に学習済 (Phase 5c-1 / 5c-2 の経験)
- Workspace は本旨に直結する重大な追加なので、決定を ADR で残しておく方が将来の retrospective に有効
- 後続 PR レビュー時に「なぜ worktree モデルにしたか」を毎回説明するコストを ADR で 1 回に集約できる

## 関連

- [ADR-0001](0001-ai-org-os-as-invariant-framework.md) — 本旨「開発組織の不変項を定義するフレームワーク」。本 ADR は本旨完成のための最後のピース
- [ADR-0014](0014-realm-physical-boundary.md) — 物理境界。本 ADR は Mindspace (A) と repo (C) の接続点 (= worktree) を新しく許可する
- [ADR-0017](0017-warden-monitoring-vs-job-monitoring.md) — Warden / Mind 分離。本 ADR は層 B (Mind 組織) の射程を「実コードを書く」まで拡張する
- [ADR-0018](0018-runtime-home-separation.md) — runtime state 分離。本 ADR は Mindspace の物理位置を変更しない (worktree 化のみ)
- [ADR-0019](0019-guild-as-organization-unit.md) — Guild = 組織枠。本 ADR は Guild manifest に optional `workspace:` フィールドを追加する
- [ADR-0020](0020-templates-and-org-manifest-separation.md) — 同梱テンプレ / 実体 / runtime state の 3 層分離。本 ADR は Workspace を 4 番目のテンプレートカテゴリとして同様の 2 層 overlay に乗せる
- [ADR-0021](0021-axiom-vs-dependency-injection.md) — A/B/C 軸。本 ADR は C カテゴリの 4 番目のサブカテゴリとして Workspace を追加
- [Issue #96](https://github.com/yukiYamada/ai-org-os/issues/96) — 本 ADR の発議元、設計議論
- 2026-05-26 dogfooding セッション — 本 ADR の必要性が発覚した実機検証 (PR #95 merge 後)
- CLAUDE.md §3.1 — 設計時の自問チェックリスト。本 ADR の方針を反映 (本 PR 内で更新)
