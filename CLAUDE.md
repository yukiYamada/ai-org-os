# CLAUDE.md — ai-org-os に関わる Claude セッション向けガイド

> このファイルは Claude Code が repo を開いた時に自動ロードされる。
> ai-org-os の本旨と、過去のセッションで踏んだ落とし穴を集約する。
> ADR は判断結果、本書は **判断時の心構え**。

## 1. プロジェクト本旨（1 行）

**ai-org-os は「開発組織の不変項（公理系）を定義するフレームワーク」**。
Realm（Docker container）の中に Warden（世界そのもの = Pillar 群）が居て、Mind（思考個体 = ホストの claude プロセス）が動的に生まれ・働き・消える。詳細は `docs/adr/0001-ai-org-os-as-invariant-framework.md` から順に読む。

## 2. 自動ロード優先順位

このファイルが最優先で、その下に:
- `docs/adr/` — 全 ADR、設計判断の確定記録
- `docs/manual-e2e-guide.md` — 運用者向け 10 分体験ガイド
- `runtime/README.md` / `runtime/host/README.md` / `runtime/pillars/README.md` — 各層の責務

判断に迷ったら **ADR を読む**。新規 ADR を起こすときは既存と矛盾しないこと。

## 3. 設計時の必須チェック（過去の踏み外しから）

### 3.1 「Designer 視点で前提を問う」 — 実装着手前

本セッションで 4 連続で踏んだ穴:

| やった | 何を見落としていた | 結果 |
|---|---|---|
| 「Conductor が Issue を claim する」と提案 | Warden 監視 vs ジョブ監視の責務混同 (ADR-0017) | operator から「Warden の MCP ならまだしも、Mind の作業の監視は Mind がやる、じゃない?」 |
| `runtime/host/.venv/` に host venv を作る | framework と runtime state を git tracked dir に同居 (ADR-0018) | operator から「環境とgitでおかしくならない? 別ディレクトリじゃない?」 |
| Phase 5b-4 で path 移動 | Dockerfile CMD と observe.py --realm の path 追従漏れ | Real E2E で初めて検出 |
| `runtime/guilds/default/` に Guild manifest を置く | 世界の構成 (runtime/) と注入される依存物 (組織パッケージ) の混同 (ADR-0020) | operator から「またruntimeの中に実体をいれちゃってるの? runtimeは構成要素であって、manifestは実体だよね?」 |

**共通パターン**: 「とりあえず動かす」優先で **1 段抽象の構造** を見落とす。
**対処**: 実装に手をつける前に、口に出して以下を自問する:
- 「これは ADR-0017 の層 A / 層 B どっち?」(Warden vs Mind の組織化)
- 「これは ADR-0018 の framework / runtime state どっち?」(git tracked vs git untracked)
- 「これは ADR-0011 の Pillar / ユーザー編集領域どっち?」(編集不可 vs 編集可)
- 「これは ADR-0014 の物理境界カテゴリ A / B / C / D どこ?」(内側 / 穴あき / 外部依存 / 人間制御)
- 「これは ADR-0016 の Container / ホストどっち?」(コア / Mind)
- 「これは ADR-0012 の人間責務 1〜5 どれ? それとも Warden / Mind の責務?」
- 「これは ADR-0020 の **世界の構成自体 / 同梱テンプレ / 依存物の実体 / runtime state** どれ?」(`runtime/` / `templates/` / `$AI_ORG_OS_HOME/<category>/` / `$AI_ORG_OS_HOME/{minds,issues,...}`)
- 「これは **A: axiom (機械強制) / B: 宣言的指示 (Persona) / C: 後天的依存注入 (manifest)** どれ?」(ADR-0021)
  - A は **code 側で reject される**、違反は強制的にブロック (例: claim-only-own-guild)
  - B は **文書、機械検証なし**、人間 / レビュー時に発覚 (例: reviewer.md の「リスクを必ず挙げる」)
  - C は **利用者が書き換える構成**、違反概念が無い (例: Guild manifest の `personas: [...]` allowlist)
  - **混同しやすい**: axiom.md に rule を書いたが enforce code が無い → "嘘の axiom"。Persona に「〜すべき」と書いたが Mind が守る保証は無い (機械強制でない)。manifest の allowlist は「ルールっぽいが構成」(別 repo で上書き自由)
- 「これは **ADR-0021 C カテゴリ** のどのサブカテゴリ? **kinds / personas / guilds / workspaces** どれが正しい配置?」(ADR-0022)
  - **kinds** = Mind の種別 (`templates/kinds/<name>.md`)
  - **personas** = Mind の役割・振る舞いガイド (B 宣言と隣接、`templates/personas/<name>.md`)
  - **guilds** = 組織枠 manifest + axiom (`templates/guilds/<name>/`)
  - **workspaces** = Mind の作業環境 (vcs / repo / worktree モード等、`templates/workspaces/<name>.md`)
  - **混同しやすい**: 「git アクセス可否」は Persona の振る舞い (B) ではなく Workspace の物理結線 (C)。「Persona に作業 dir を書く」は責務違反 — Persona は役割、Workspace は環境

迷ったら **既存 ADR を読み直す**。新カテゴリが必要なら **新 ADR を起こす**。実装で踏み外す前に。

### 3.2 「operator の素朴な問いを最重視する」

本セッションで重要な軌道修正 2 つ:
- 「Warden の監視と、ジョブの監視を混同しないようにね」 → ADR-0017 起票
- 「環境と git でおかしくならない? 別ディレクトリじゃない?」 → ADR-0018 起票

短い問いが **設計の根本** を突くことが多い。
**対処**: operator が「ん?」「これでいいの?」「やりすぎ?」と言ったら、即「了解、進めます」で flush しない。
**1 度立ち止まって**、「本当に問われているのは何か」「自分が見落とした構造は何か」を考える。

軌道修正のコストは小さい。間違った方向に PR を 3 つ重ねるコストは大きい。

### 3.3 「セキュリティ・整合性系を 1〜2 段階高く見積もる」

`~/.claude/projects/.../memory/feedback_pre_pr_self_review.md` 参照。
PR を出す前の Reviewer 1 巡で、特に以下を厳しめに評価する:

- identity binding / 認可 / 信号送信系 (kill / sudo / DELETE / write to shared path)
- 正規表現に外部入力が混ざる箇所
- 同じデータを 2 経路で生成して両方が表に出る (一貫性チェック必須)
- race / TOCTOU → 検出パスを書いたらその検出後の処理にも race window が無いか

過去 Codex が P1 で flag した実例はすべてここで一度過小評価したもの。

## 4. operator の collaboration スタイル

- **短く明確な指示** を好む。長い議論は嫌う
- **「やろう」「OK」「いいよ」** で確認なく進める → 不要な確認は嫌われる
- **「やりすぎ?」「これおかしくない?」** で軌道修正を入れてくる → 真剣に受ける
- **「サブエージェント使いまくっていい」「並列で行こう」** → 並列実行を活用する
- **「マージしていいよ」** → Codex review 完璧でなくても CI green + self-review なら merge
- 「**既存利用者いないから**」「**作業ディレクトリ自由に使っていい**」 → 大胆な変更も OK

## 5. 進捗の見方

- `git log --oneline -20` で最近のマージ履歴
- `gh issue list --state open` で残作業
- `docs/adr/` 番号順に読めば設計の系譜が分かる
- **Phase 5a-5e 完了** (= ADR-0001〜0025): 不変項フレームワーク + Warden 双方向 outer loop (観察→判断→働きかけ→反応取り込み) が dogfooding で実機証明済み (2026-05-30)
- **Phase 5f = 「Mind に任せられる Realm」**: tracking issue **#124**。4 段階:
  1. Observability 強化 (#122) — 後追い可能性 → **完了 (ADR-0026 + PR-A〜F = #127-131, #139)、observe.py --trace で全 event 時系列復元可**
  2. 多 Mind dogfooding (gm + designer + implementer + reviewer) — **着手済 / 3 run 完了 (2026-06-01〜06-02)**: 4 Mind が Persona 駆動で `gm-default → alice → bob → carol` の Issue claim → design → 実装 → review-request チェーンを 2/3 run で完走、bob は実際にコード (`idle_time.py` / `format_issue_id.py` + tests) を作成。run 3 は case C 副作用で chain 起動が遅れて 1 hop で時間切れ (#147 で Persona 微調整 merged)。観察された不具合 **8 件 issue 起票 (#133-138, #144, +147)**、うち **8 件 fix merged**: #139 rotation, #140 trace UTF-8, #141 kill-mind orphans, #142 nudge sentinel, #143 preserve-notes, #145 peek-inbox (case A), #146 Persona cycle budget (case C), #147 guildmaster 初動 dispatch 例外。残り Open: **#134 (cycle 2 outlier)** = run 3 で gm cycle 2 = 97s に改善したが carol cycle 3 = 655s で **gm 限定でない一般化された outlier** が発見された (H2 claude SDK hang が浮上)、**#138** (Realm Inbox 消化責任、discussion)。Step 2 主成果: Persona-driven orchestration が再現性ある (2/3 run 完走、case C 微調整で 4/4 期待)。
  3. Issue → PR 完全フロー検証 (信頼境界 axiom)
  4. 失敗扱い整理 (#47 → ADR-0027 候補)
- 完了基準: 「人間が Issue 投入 → 30 分放置 → PR が並ぶ → 人間が merge → 次の Issue へ」を 5 連続で事故なく回せる

## 6. 新セッション開始時のお勧めワークフロー

1. `git log --oneline -10` で直近の作業を把握
2. `gh issue list --state open` で open issue を確認
3. 既存 ADR の番号と要旨を頭に入れる (本書 §3 のチェックリストを使うため)
4. 何かやる前に「これは ADR のどれに該当するか」を自問する

---

このファイルは Claude Code が自動ロードする。memory より強制力があり、git tracked で全員に共有される。
更新する判断は重い: 本旨レベルの教訓 / 過去の罠 / operator スタイル 等、**ADR で表現しきれない暗黙知** のみここに書く。
個別の判断は ADR に書く、個別の状態は GitHub Issue で追う。
