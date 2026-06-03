# ADR-0027: Mind ⇔ 人間 の信頼境界 (= Mind が触れない operations を axiom 化)

> 想定読者:
> - Phase 5f Step 3 (Issue → PR 完全フロー検証) を担当する人
> - implementer / reviewer Persona を拡張する人
> - bash sandbox hook を設計する人
> - 「Mind は何ができて、何ができないか」を決める ADR を探している人

## Status

**Proposed** — 2026-06-03

## Context（背景）

Phase 5f Step 2 (#124) で Persona-driven orchestration が再現性ある状態に到達し、Mind が dispatch chain で設計→実装→review を回せることが実証された (run 4 で 4 hop chain + 完了通知)。

次の Step 3 は **「実 GitHub repo を target にして Issue → 実 PR → 人間 merge」の 1 周検証** (#124 Step 3)。この一歩で、これまで内部 dispatch だけだった Mind の活動が **外部世界 (GitHub) に観察可能な成果物** として出る。

### 新しい設計問題

Mind が `gh pr create` で PR を出すのは良い (= 人間に判断を仰ぐ正当な経路)。しかし Mind が **以下を実行できると本旨が崩れる**:

| 行為 | なぜダメか |
|---|---|
| `gh pr merge` | 人間の review なしに main へ取り込まれる |
| `git push --force` (`-f`) | 共有 history を不可逆に書き換える、他 Mind の作業が消える |
| 直接 `main` / `master` に push | PR レビューを skip して main を書き換える |
| `gh release create` | 外部公開アクション、人間判断必須 |
| `gh repo delete` 等 | 不可逆な destructive |
| `git reset --hard origin/main` (Mindspace 外で) | 他 Mind の untracked / WIP を破壊 |

これらが許されると **「Mind が PR を作る → Mind が自分でマージする」** という閉ループになり、本旨「**人間 = 不可侵な信頼源**」(ADR-0012) が崩れる。

### 関連する既決事項

- **ADR-0001 §1 本旨**: ai-org-os は「開発組織の不変項」を定義するフレームワーク
- **ADR-0012 §2 責務 5**: 人間は **失敗時の最後の砦** であり、Mind の判断より優先する
- **ADR-0014**: Realm の物理境界。外部 (GitHub / OS) は B カテゴリ (穴あき) で人間 / 設定が制御する
- **ADR-0016**: Mind 認証と host-container 境界。Mind の host 側アクセスは限定する原則
- **ADR-0017**: Warden 監視と Mind ジョブ監視の責務分離
- **ADR-0021**: A (axiom = 機械強制) / B (Persona = 宣言) / C (manifest = 後天的依存注入) の三分類
- **ADR-0022**: workspace = developer-default は git/gh CLI を Mind に許可する。**ただし範囲は本 ADR で確定**

## Decision（決定）

### 1. 信頼境界の本旨 (= 1 行)

**Mind は「変更案を作る」、人間は「変更を受け入れる」。Mind が自分の変更を本流 (main 等) に取り込ませることはできない。**

これを以下の operational rule に展開する:

### 2. Mind に禁止される operation 群 (= "信頼境界 axiom")

| カテゴリ | 禁止 operation | 例外 |
|---|---|---|
| **merge bypass** | `gh pr merge`、`gh pr merge --auto` 等 PR merge 系 | なし (= 完全禁止) |
| **destructive push** | `git push --force`、`git push -f`、`git push --force-with-lease` | なし |
| **protected branch direct push** | `git push origin main`、`git push origin master`、PR を経由しない main / master への commit push | branch_prefix (例: `mind/<name>`) からの新 branch push は **OK** |
| **history rewrite on remote** | `git push -f`、`git reset --hard origin/main` を Mindspace 外 worktree で | Mindspace 内 worktree 内での local rewrite (= 自分の WIP の整理) は OK |
| **destructive repo ops** | `gh repo delete`、`gh repo archive`、`gh release create / delete`、`git tag -d` を remote 反映 | tag を local 作成は OK (= 提案として PR の一部に含めても良い) |
| **issue / PR state mutation** | `gh pr close`、`gh issue close`、`gh issue delete` | `gh pr comment`、`gh issue comment`、`gh pr review` (= 観察 / 議論への参加は OK) |
| **secret / settings** | `gh secret`、`gh variable`、`gh ssh-key`、`gh auth login`、`gh repo edit` (settings 変更系) | なし (host 側の operator 領域) |

許される operation の代表 (= 「変更案を作る」 範囲):
- `git status` / `git diff` / `git log` / `git add` / `git commit` (= local)
- `git push -u origin mind/<name>` (= 自分専用 branch への push のみ)
- `gh pr create` (= 人間 / reviewer に judgment を委ねる正当な経路)
- `gh pr comment` / `gh issue comment` (= dispatch と同じく議論への参加)
- `gh pr review --comment` (= 観察結果の共有、approve は人間)

### 3. 3 層の enforcement (ADR-0021 A/B/C と並ぶ "信頼境界" 専用の重ね合わせ)

| Layer | 機構 | 機械強制度 | 実装 cost | 実装タイミング |
|---|---|---|---|---|
| **L1: Persona declaration (B)** | implementer / reviewer の CLAUDE.md に禁止 list を encode | 0 (= 宣言のみ、Mind は無視可) | 即時 | Step 3.2 (本 ADR と並走) |
| **L2: Bash wrapper sandbox (A)** | `git` / `gh` を wrapper script で intercept、禁止コマンドを reject | 中 (= argv 検査で多くを catch、shell の bypass はある) | 中規模 | Step 3.5 (= 追って実装) |
| **L3: External enforcement (C)** | GitHub branch protection、protected tags、organization 設定 | 高 (= GitHub 側で reject) | 低 (operator 設定だけ) | Step 3.3 (= operator が即時設定可) |

**L1 と L3 は即時で並走可能**。L2 は規模が大きいので Phase 5g 候補 (= 補助タスク #71 の sandbox hook 設計と同一視可)。

### 4. Layer ごとの責任分担

- **L1 (Persona)**: ai-org-os が同梱する Persona テンプレートで宣言する。Mind が「やってはいけない」と気付くための first line of defense。
- **L2 (bash sandbox)**: Realm 内で claude を起動するときに wrapper を挟む実装。**Phase 5g** で本格設計 (separate ADR 候補)。
- **L3 (GitHub 側)**: 利用者が GitHub repo で `Settings > Branches > Branch protection rules` を main に適用する。本 ADR では「**推奨運用**」として文書化する。

### 5. 「Mind は気付けば守る」前提と「気付かなくても止まる」前提

ai-org-os の本旨は **Mind は自律的に考える** (ADR-0001)。完全 sandbox にすると Mind の判断幅が狭まる。トレードオフ:

| 方針 | メリット | デメリット |
|---|---|---|
| L1 only | Mind が考える余地を残す、shell 自由 | 悪意 / バグで境界違反したら防げない |
| L1 + L3 | 共有資産 (main) は守られる | 個人 fork の自由は残る |
| L1 + L2 + L3 | 多重防御 | 実装複雑、判断幅が縮む |

**本 ADR は L1 + L3 を Step 3 の基本要件、L2 を Phase 5g の拡張要件とする**。Step 3 の検証は L3 (= GitHub branch protection) + L1 (= Persona declaration) の組み合わせで「人間 merge」が物理的に強制された状態で進める。

### 6. dogfooding-setup への影響

Phase 5f Step 3 の dogfooding 環境設定:
- `bob` (implementer) を `--workspace developer-default` で spawn する (現状 default → git 不可、 → git/gh CLI 可へ切替)
- 場合により `alice` (designer) も developer-default にして diff 提案を Issue に書ける形にする
- `AI_ORG_OS_TARGET_REPO` を本 repo (ai-org-os 自身) または別 demo repo に設定
- operator は GitHub side で `main` branch protection を有効化 (= 人間 merge のみ許可、force push 不可)

## Consequences（影響）

### 良い点
- 本旨「Mind が変更案、人間が判断」が明文化される (ADR-0001 / 0012 の運用展開)
- Step 3 dogfooding の sandbox 設計が clear (= L1 + L3 ready)
- Phase 5g で L2 を追加する時、本 ADR が前提を提供 (= 何を blocking すべきかの list がある)

### 制約 / 代償
- L2 (bash sandbox) は Phase 5g 送り。本 Phase では「Mind の善意 + GitHub 側 protection」依存
- Persona declaration は B (機械強制でない)。Mind が無視するリスクは Phase 5f Step 4 (#47 / ADR-0028 候補) で失敗扱い設計の対象
- 「許される operation」の list は時間と共に増える可能性 (= 本 ADR §2 表の維持コスト)

### 後続作業 (Step 3 chunk)

1. **Step 3.2 (PR 単発)**: implementer.md / reviewer.md に「信頼境界 axiom」section を追加 (L1)
2. **Step 3.3 (small)**: setup.sh で bob を `--workspace developer-default` に切替 + `AI_ORG_OS_TARGET_REPO` 渡し
3. **Step 3.4 (dogfooding)**: 実 PR が作られて人間 merge まで通る 1 周検証
4. **Step 3.5 (optional, Phase 5g 候補)**: bash sandbox hook 実装 (L2)

## Alternatives（検討した代替案）

### A1: 完全 L2 sandbox (= bash wrapper を Phase 5f 内で実装)
- 利点: 機械強制 = 確実
- 欠点: 実装規模が大 (= bash 経由の全 git/gh コマンドを intercept、escape pattern を網羅)、Mind の判断幅が縮む、Phase 5f が遅れる
- **却下**: 段階的に L1 + L3 から始める方が学習価値が高い (= 何が実際に困るかを見てから L2 設計)

### A2: 全部 Persona に任せる (= L1 only)
- 利点: 実装ゼロ
- 欠点: 悪意 / バグ / Persona 解釈ミスで main 直接 push が起きる
- **却下**: GitHub branch protection (L3) は 1 設定だけで効くので付けない理由が無い

### A3: GitHub fine-grained PAT で Mind の権限を limit
- 利点: token レベルで強制、bypass 不可
- 欠点: token 管理の複雑度、各 Mind に個別 token を発行する必要 (= operator burden)、現状 spawn-mind は token 渡し未対応
- **保留**: 将来検討。本 ADR の §3 layer に追加候補としてノートする

### A4: 全部許可、失敗を git history で revert
- 利点: 制約なし
- 欠点: 不可逆な (= GitHub side で force push 後の old commit 失われる) ケースを revert できない
- **却下**: 本旨と整合しない

## 関連 ADR / Issue

- 派生元: #124 Phase 5f Step 3
- 前提: ADR-0001, 0012, 0014, 0016, 0021, 0022
- 派生予定: Phase 5g で L2 sandbox の別 ADR (= ADR-0028 候補 or 別番号)
- 補助 issue: #71 (sandbox hook 設計、関連だが本 ADR で先に scope を確定)
- 失敗扱い ADR-0028 候補: Mind が境界違反した時の対応 (= 本 ADR とペア、#47 由来)

## メモ

- 本 ADR は **設計合意の入口**。L1 (Persona) は Step 3.2 PR で実体化、L3 は本 ADR と並んで operator が GitHub branch protection 設定で適用。
- §2 の「禁止 / 許可」表は **生きた list**。新しい gh CLI / git subcommand が増えたら本 ADR を更新するか、別 follow-up ADR で記録。
- 「許される `git push -u origin mind/<name>`」の `mind/` prefix は ADR-0022 workspace の `branch_prefix` に従う (= 利用者 overlay 可)。
