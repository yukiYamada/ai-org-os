# ADR-0006: Phase 5（Realm + Warden + Guildmaster の最小組み合わせ）の設計案

> 想定読者:
> - Phase 5 を実装するメンテナ（Realm コンテナ起動スクリプト、Warden / Guildmaster の常駐実体、3 段階プロセスの仲介、Mind Kind Registry の整備を担う）
> - Phase 5 への着手を判断する意思決定者（プロダクトオーナー）
>
> 目的: 朝起きたユーザーが「Phase 5 をいま着手するか / 段階分割するか / そもそも棚上げするか」を、論点と材料を並べた状態で判断できるようにする。

## Status

**Proposed** — 2026-05-22

> 本 ADR は **設計のみ**。**実装は本 ADR の承認後に着手する**。
> Accepted に昇格させるには「推奨案」セクションの選択肢を絞り込む必要がある。

---

## Context（背景）

### これまでの位置

- [ADR-0001](./0001-ai-org-os-as-invariant-framework.md): ai-org-os は「開発組織の不変項（Axiom）を定義するフレームワーク」。組織 = 思考のネットワーク。
- [ADR-0002](./0002-vocabulary-and-meta-meta-structure.md): 用語と階層構造を確定。**Realm / Warden / Nexus / Guild / Guildmaster / Mind / Mindspace / Persona / Axiom / Dispatch**。
- [ADR-0003](./0003-docker-and-phase-2-design.md): Phase 2（Docker 化、Mind の named volume 化）。**Proposed**。
- ADR-0005（Phase 3 = MCP 直行、Nexus 導入）: **Accepted**、実装中（PR #23）。Nexus は Python 製 MCP server、Warden とはプロセス分離。Mind は `send_dispatch` / `read_inbox` / `ack_dispatch` で通信する。Mind Body = Generic Kind 1 種類、Mindspace に Persona を CLAUDE.md として配置。

Phase 3 の完了で、ai-org-os は次の構図に到達する想定：

```
[Host]
  ├─ Nexus (Python MCP server, 常駐)
  ├─ Mind A (Claude CLI コンテナ / プロセス)
  └─ Mind B (Claude CLI コンテナ / プロセス)
     ↑ Mind は Nexus 経由で Dispatch を交わす
```

これは「思考のネットワーク」の最小実装としては十分だが、**ADR-0002 の階層（Realm → Guild → Mind）が依然として存在しない**。具体的には：

- **Realm**（メタ世界コンテナ、ルール適用範囲）が無い → Axiom は文書上のみで、enforce する主体がいない
- **Warden**（守護者 Claude）が無い → 3 段階プロセス（要求→承認→実行）の「実行」を行う主体がいない。Mind の生成は人間が `spawn-mind.sh` を叩いている
- **Guildmaster**（マザー Claude）が無い → Guild という論理セグメントも、その目的維持・Mind 管理も成立していない
- **Guild** という単位が無い → 複数 Mind は並列に存在するが、共通目的の単位として束ねられない

つまり Phase 3 完了時点でも、ai-org-os は **「思考が複数いる」状態**であって、**「組織として運営されている」状態**ではない。

### Phase 5 の達成目標

「**Realm + Warden + 1 Guild + Guildmaster + 2 Mind**」が動く最小構成。具体的には：

1. **Realm として実コンテナが 1 つ立ち上がる**（ルール適用範囲が物理的に存在する）
2. **Warden（Claude）が 1 つ動き**、ルール解釈・Mind Kind 登録・3 段階プロセスの実行を担う
3. **1 つの Guild が論理セグメントとして定義される**（目的を共有する Mind の集合）
4. **Guildmaster（Claude）が 1 つ動き**、その Guild の目的維持・Mind 管理・承認を担う
5. **2 つの Mind がその Guild に所属し、Dispatch（Nexus 経由）で通信する**
6. **「Mind 要求 → Guildmaster 承認 → Warden 実行」の 3 段階が一巡する**（=新しい Mind を増やす要求が Mind から飛び、Guildmaster が承認し、Warden が `spawn-mind` を呼ぶ、までエンドツーエンド）

Phase 5 では **複数 Guild / 認可 / TTL / 高度なリソース制限 / Issue webhook はまだ作らない**。「組織として 1 回回る」を最小コストで証明することに絞る。

### スコープ外（Phase 5 で扱わないこと）

- 複数 Guild（Phase 6 以降）
- 認可機構（Issue #19 で別途扱う）
- MCP Resources / Prompts（Issue #20 で別途扱う）
- メッセージ TTL / dead letter（Issue #21）
- GitHub Issue webhook プロダクション化（Phase 5 では手動投入で十分）
- フェイルオーバ / レプリケーション
- メトリクスダッシュボード

---

## Decision（推奨案 + 候補比較）

> 本 ADR は Proposed のため、ここでは「単一の決定」ではなく **推奨案** と **候補比較** を並べる。
> Accepted に昇格するときに、ユーザーが下の選択肢から 1 案を選んで確定する想定。

### 推奨案サマリ（叩き台、Accepted 化時に調整可）

| 軸 | 推奨 | 理由（要約） |
|---|---|---|
| Realm の実体 | **(a) Docker Compose 1 ファイル** で services として warden / guildmaster / nexus / mind-1 / mind-2 を並べる | Phase 2 推奨と整合、宣言的、Phase 6 で services を増やすだけ |
| Realm 内のサブコンテナ | **Mind のみコンテナ**。Warden / Guildmaster / Nexus は **Realm コンテナ内のプロセス** として同居 | DinD 回避、起動コスト最小、Phase 5 の責務分離は process 境界で十分 |
| Phase 2 必須/任意 | **必須**（Realm 自体が実コンテナを要求する。ただし Mind の named volume 化は段階分割可） | Realm = 実コンテナと ADR-0002 §3 で確定済み |
| Warden 実装 | **(a) 常駐 Python プロセス + Claude CLI を内蔵 subprocess として呼ぶ** | リソース管理ロジック・Mind Kind Registry が Python で書きやすい、Claude は判断時のみ起動 |
| Guildmaster 実装 | **(c) Mind と同じ仕組み**（Guildmaster Persona を装着した永続 Mind として spawn） | Mind 機構の再利用、Persona でルール書ける、Claude CLI 統一 |
| 3 段階プロセス | **Nexus に専用 MCP tools を追加**（`request_spawn`, `approve_spawn`, `execute_spawn`） | Phase 3 の Dispatch 機構の上に明示プロセスとして乗る。痕跡が自動で残る |
| Mind Kind Registry | **静的ロード**（`runtime/kinds/*.md` を Warden 起動時に読み込む） | Phase 1 と同じ。動的追加は Phase 6 |
| リソース管理 | **フックだけ用意**（Warden が Mind の token 消費を集計、閾値超で停止 API を呼ぶフレームは作るが、閾値は緩く） | 本格運用は Phase 6 |
| Issue 投入 | **ファイル投入**（`runtime/inbox/issues/*.md`、Warden が poll） | webhook は Phase 6、`gh issue list` の取り込みは Phase 5.x オプション |
| 段階分割 | **5a → 5b → 5c の 3 段階に分ける** | 推奨。各段階で動く成果物を確認できる |

---

### 1. Phase 2 / Phase 3 との依存関係

ADR-0002 §3「Realm は **ai-org-os のルール適用範囲、実コンテナ**」。これは Phase 5 では譲れない。よって：

#### Phase 3（Nexus + Dispatch）との関係

- **必須前提**。Mind と Mind の通信、および 3 段階プロセスのメッセージング（要求 / 承認 / 実行通知）は Nexus の MCP tools の上に乗るのが自然
- Phase 3 が Accepted・実装中である前提で本 ADR を組み立てる

#### Phase 2（Mind の named volume 化）との関係

「Phase 2 が必須か任意か」の結論：

| 観点 | 必須となる根拠 | 任意としてよい根拠 |
|---|---|---|
| **Realm = 実コンテナ**（ADR-0002 §3） | **Realm 自体は実コンテナが必要**。Docker（または同等）が走っていないと Phase 5 が成立しない | — |
| Mindspace の物理不可侵 | Phase 5 の Axiom 担保品質を上げる | Phase 3 までのホスト fs Mindspace でも論理的には動く |
| 複数 Mind の並走 | named volume にしておけば backup / orphan 整理が楽 | プロセス分離だけでも当面は機能する |
| 開発者体験 | コンテナ前提なら起動 / 停止が一発 | Phase 1 の手軽さが消える |

**結論**:

> **Realm コンテナ自体（=Compose で立てる Realm service）は必須**。Phase 5 が「Realm + Warden + Guildmaster の最小組み合わせ」である以上、Realm を立てない選択はない。
>
> 一方、**ADR-0003 で議論された「Mind の named volume 化」は Phase 5 では必須ではない**。Mind コンテナの Mindspace は bind mount でも named volume でも Phase 5 のゴールは達成できる。**named volume への昇格は Phase 2 を別途完了させる作業として並走させる**ことを推奨。

これにより、Phase 2 と Phase 5 の依存関係は「Phase 5 ⊃ Realm コンテナ ⊃ Docker が必要」「Phase 2（Mind 個別の volume 化）は Phase 5 と独立」という構造になる。

### 2. Realm の実装候補

| 候補 | 利点 | 欠点 | Phase 5 適合 |
|---|---|---|---|
| **(a) Docker Compose 1 ファイル**: services として warden / guildmaster / nexus / mind-1 / mind-2 を並べる | 宣言的、起動 1 コマンド、ADR-0003 推奨と整合 | Mind の動的 spawn を Compose の外でやることになる（Warden が `docker run` を呼ぶ） | **最適** |
| (b) K8s 単一 namespace | スケール / 観測が標準で整う | Phase 5 では明らかに過剰、学習コスト高、Windows ホストで詰みやすい | NG |
| (c) ホスト直接プロセス: コンテナなし、screen / tmux / systemd で並走 | 軽い、依存ゼロ | Realm = 実コンテナの Axiom（ADR-0002 §3）に違反 | NG |
| (d) 混成: Realm 全体は Compose、中の Mind は別 docker run | 動的 spawn が docker run で素直に書ける | Compose と docker run の管理境界が増える | **次善** |

#### (a) の構造詳細（推奨）

```
realm/                                  ← Realm コンテナのワーキングディレクトリ
├── docker-compose.realm.yml            ← Phase 5 のトップレベル Compose
├── Dockerfile.realm                    ← Warden + Guildmaster + Nexus を内蔵する Realm image
├── warden/
│   ├── warden.py                       ← 常駐プロセス、Mind Kind Registry 管理、3 段階の実行担当
│   └── CLAUDE.md                       ← Warden Persona（判断時 Claude CLI に読ませる）
├── guildmaster/
│   └── CLAUDE.md                       ← Guildmaster Persona（Mind と同じ仕組みで起動）
├── nexus/                              ← Phase 3 の Nexus を取り込む（または共有 image）
└── inbox/issues/                       ← Issue 投入（Phase 5 では人間がファイル投入）
```

#### (d) の余地

Mind の動的 spawn は「Warden が `docker run` を発行」する形で実装される。これは (a) と矛盾しない（Realm Compose は固定 services、Mind は動的に Compose 外で追加）。**(a) を採用しつつ Mind 動的 spawn は docker run** で進める形が現実的。実質 (a)+(d) のハイブリッド。

### 3. Realm の中の構造（コンテナの中にコンテナ問題）

「Realm = 実コンテナ」と決まった以上、その中の Warden / Guildmaster / Mind をどう実装するかを決める必要がある。

| 候補 | 構造 | 利点 | 欠点 |
|---|---|---|---|
| **(α) Realm コンテナ内にプロセスとして同居**: Realm 1 コンテナの中で Warden プロセス、Guildmaster プロセス、Nexus プロセスが並走。Mind だけ別コンテナ | DinD（Docker in Docker）回避、Realm コンテナの起動コスト最小、責務分離は process 境界で十分 | Warden / Guildmaster の障害分離が process レベルに留まる |
| (β) DinD: Realm コンテナの中で docker daemon を動かし、その中で Warden / Guildmaster / Mind コンテナを起動 | 完全な階層、Realm が物理的にすべてを内包 | DinD の運用コストが高い、ホスト Docker との二重管理、CI で不安定 |
| (γ) ネスト Compose: Realm コンテナの中で別の Compose を起動 | (β) と同じ、Compose 階層で構造化 | DinD 同様の欠点 |
| (δ) Realm = 論理境界（Compose ファイルそのものを「Realm」とみなす）、実コンテナは持たない | 軽い | ADR-0002 §3「Realm = 実コンテナ」に違反 |

**推奨**: **(α)**。

**理由**:
- ADR-0002 §3 が要求する「Realm = 実コンテナ」を満たす最小実装
- Warden / Guildmaster / Nexus は Realm コンテナ内の **同居プロセス** として動かす。これは ADR-0002 §8「Nexus は Warden とプロセス分離」と整合する（**process 単位の分離**で十分、別 OS インスタンスは不要）
- Mind だけは別コンテナにする。Mindspace の不可侵性（Phase 2 で論じた named volume）の物理担保が Mind ごとに効く
- DinD を避けることで CI と開発者体験を維持できる

### 4. 各 Claude の実装方針（Body / Persona / 持続性 / 通信）

| Claude | Body（実行環境） | Persona / CLAUDE.md の中身 | 持続性 | 通信手段 |
|---|---|---|---|---|
| **Warden** | Realm コンテナ内の **常駐 Python プロセス + 判断時 Claude CLI subprocess** | `realm/warden/CLAUDE.md`: Axiom 強制、Kind Registry、3 段階の実行責務、リソース管理ポリシー | 24/365、Realm コンテナと同寿命 | **Nexus 経由（MCP client）** + ファイル投入（issue inbox） + docker socket（Mind の spawn / destroy） |
| **Guildmaster** | Realm コンテナ内の **Mind と同じ仕組み（Persona 装着 Mind）** | `realm/guildmaster/CLAUDE.md`: Guild 目的、Mind 管理ポリシー、承認基準、記憶共有プロセスの仲介 | 24/365、Realm コンテナと同寿命 | **Nexus 経由（MCP client）** のみ |
| **Mind** | コンテナ（Phase 2 推奨）または Realm コンテナ内プロセス（フォールバック） | Generic Kind + Persona（既存） | 24/365、明示破棄まで | **Nexus 経由（MCP client）** のみ |

未確定欄について：

#### Warden の Body 候補

| 候補 | 利点 | 欠点 | 推奨 |
|---|---|---|---|
| **(a) Python サブプロセス + Claude CLI**: Python で常駐ループ、判断が必要なときだけ Claude CLI を `subprocess.run` で呼ぶ。Warden 用のディレクトリに CLAUDE.md（Warden Persona）を置く | Python でリソース集計・docker socket 呼び出しを書きやすい。Claude は判断時のみ起動でコスト低 | Claude セッションが毎回新規（コンテキスト引き継ぎを自前で管理） | **推奨** |
| (b) 常駐 Python プロセス + Claude API 直接: Anthropic API を Python から叩く | セッション管理が自由 | API キー管理、ストリーミング / tools 実装を自前。Claude CLI で済むなら不要 | 将来の選択肢 |
| (c) Mind と同じ仕組み: Warden Persona を装着した永続 Mind として spawn | 機構の再利用、Persona で書ける | 常駐 Claude セッションのコスト、docker socket をどう触らせるかが不自然（Mind は通常 docker 制御権を持たない） | NG |

**Warden は (a) を推奨**。Warden は「判断 + 実行（システムコール）」の両方を担うので、Python が骨で、Claude が判断時に呼び出される構造が自然。

#### Guildmaster の Body 候補

| 候補 | 利点 | 欠点 | 推奨 |
|---|---|---|---|
| (a) Python サブプロセス + Claude CLI | Warden と統一 | Guildmaster は「判断」が主、「実行（システムコール）」は Warden に投げるので Python 骨は過剰 | 次善 |
| (b) 常駐 Python プロセス + Claude API 直接 | (a) 同 | (a) 同 | 不要 |
| **(c) Mind と同じ仕組み**: Guildmaster Persona を装着した永続 Mind として spawn | Mind 機構の再利用、Persona でルール書ける、Claude CLI 統一、Guildmaster は MCP tools 経由でしか実行しないので docker socket 不要 | 常駐 Claude セッションのコスト | **推奨** |

**Guildmaster は (c) を推奨**。Guildmaster の責務は「目的維持」「承認」「仲介」であり、これらはすべて Mind が Nexus 経由で行える操作の上位概念。Mind 機構を再利用するのが筋。

**結論**: **Warden = Python + Claude CLI（判断時）/ Guildmaster = Mind と同じ仕組み**。両者を別構造にすることで、Phase 6 以降での進化方向も自然になる（Warden は Python ロジックの追加、Guildmaster は Persona の改稿）。

### 5. 3 段階プロセスの実装

ADR-0002 §6: 「**要求（Mind / Guild） → 承認（Guildmaster） → 実行（Warden）**」。これを Phase 5 で具体化する。

#### 設計

Nexus に 3 つの MCP tools を追加する：

| Tool | 呼び出せる主体 | 受け取る相手 | 動作 |
|---|---|---|---|
| `request_spawn(kind, persona, name, purpose)` | Mind / Guildmaster | Guildmaster の inbox | 要求を Dispatch として Guildmaster 宛に投げる |
| `approve_spawn(request_id, decision, reason)` | Guildmaster | Warden の inbox | 承認結果を Warden に通知 |
| `execute_spawn(approval_id)` | Warden | (システム呼び出し) | `docker run` 等で Mind を起動、結果を要求元に通知 |

destroy も同様に 3 つ追加（`request_destroy` / `approve_destroy` / `execute_destroy`）。

#### 痕跡の残し方

- 各 tool 呼び出しは Nexus が記録する（Phase 3 の dispatch ログ機構を再利用）
- `request_id` / `approval_id` で 3 段階が紐づけられる
- すべての痕跡は Realm 内の永続領域（`realm/audit/dispatches/`）に残す

#### シーケンス図（ASCII）

```
Mind A                Nexus               Guildmaster              Warden
  |                     |                       |                     |
  | request_spawn(...)  |                       |                     |
  |-------------------->|                       |                     |
  |                     | dispatch (req_id=R1)  |                     |
  |                     |---------------------->|                     |
  |                     |                       | (判断: 承認/却下)    |
  |                     |                       |                     |
  |                     |  approve_spawn(R1)    |                     |
  |                     |<----------------------|                     |
  |                     | dispatch (apr_id=A1)  |                     |
  |                     |---------------------------------------------->|
  |                     |                       |                     | (判断: 実行可否)
  |                     |                       |                     | docker run mind-X
  |                     |                       |                     |
  |                     |  execute_spawn(A1) ack|                     |
  |                     |<----------------------------------------------|
  | spawn_complete(R1, mind=mind-X)             |                     |
  |<--------------------|                       |                     |
  |                     |                       |                     |
```

#### 各ステップで痕跡をどう残すか

| ステップ | 痕跡 |
|---|---|
| 要求 | `realm/audit/dispatches/<req_id>.request.md`（YAML frontmatter で from / to / purpose / requested_kind / persona） |
| 承認 | `realm/audit/dispatches/<apr_id>.approval.md`（in_reply_to: req_id、decision、reason） |
| 実行 | `realm/audit/dispatches/<apr_id>.execution.md`（実行結果、container_id、エラーがあれば stderr） |
| 完了通知 | `spawn_complete` Dispatch が要求元の inbox に届く（Phase 3 の機構そのまま） |

これにより 3 段階すべてが Nexus 経由で起こり、Mind 自身もログを読み返せる（Axiom「共有はプロセスを踏む」の証跡）。

### 6. Mind Kind Registry の管理

ADR-0002 §5 で「Mind Kind の登録カタログ管理は Warden」と確定済み。

| 候補 | 内容 | 利点 | 欠点 |
|---|---|---|---|
| **(a) 静的ロード**: `runtime/kinds/*.md` を Warden 起動時に静的ロード | Phase 1 と同じ、シンプル | Kind を増やすたびに Realm 再起動 |
| (b) 動的登録（ホットリロード）: Warden が `kinds/` を watch | Realm を止めずに Kind 追加可 | watch ロジック、整合性チェックが要る |
| (c) 人間 Issue 経由の動的追加: Issue 投入 → Warden が判断 → kinds/ に追加 | 「Issue 投入が主入力」（ADR-0002）と整合 | Warden の責務が一気に増える |

**推奨**: **(a) 静的ロード**。

**理由**:
- Phase 5 では Kind = Generic 1 種類で十分（Phase 3 完了時点と同じ）
- 動的追加は Phase 6 以降で需要が出てから設計するほうが、判断材料が揃う
- Warden の起動シーケンスに「`kinds/*.md` を全部読んで自分の Registry に入れる」を 1 ステップ加えるだけで済む

### 7. リソース管理の実装

ADR-0002 §7: 「**リソース制約は Realm レイヤーで担保**: 例『1H 800M tokens 超過で停止』など。Warden が裏側で管理」。

| 案 | 内容 | 実装コスト |
|---|---|---|
| **最小（フックだけ）**: Warden が Mind の token 消費を集計するフレームを作り、閾値は緩く（実質ノーオペ）。停止 API（`destroy_mind`）は完全に動く状態にしておく | 集計の入り口だけ作る | 低 |
| 中位（緩い制限）: 1H あたりの token 上限・Mind 数上限を Warden の Persona に書く。Warden が読んで停止判断 | 上記 + Warden Persona の運用ルール | 中 |
| フル（Realm 物理 enforce）: cgroup / docker resource limits で物理担保 | docker 設定 + 計測 | 高 |

**推奨**: **最小（フックだけ）**。Phase 5 ではリソース管理を「実装した」と言える状態にせず、「Phase 6 以降で本格運用できる土台」を作るに留める。

**具体的に Phase 5 で作るもの**：
1. Warden が各 Mind の token 消費を `realm/audit/usage/<mind>.jsonl` に追記する集計ループ
2. Warden Persona に「閾値超過時の停止判断手順」を書く（Phase 5 では閾値を実質無効に設定）
3. `destroy_mind` MCP tool が確実に動く（3 段階プロセスの destroy 側を完成させる）

これにより Phase 6 で「閾値を絞る」だけで本格運用に入れる。

### 8. Issue 投入のインターフェース

ADR-0001 / ADR-0002 で「人間 → Realm → Guild → Mind」の主入力経路を Issue 投入と定義した。Phase 5 で何を実装するか。

| 候補 | 内容 | 利点 | 欠点 |
|---|---|---|---|
| **(a) ファイル投入**: `realm/inbox/issues/*.md` を人間が置く、Warden が poll | 依存ゼロ、Phase 3 ファイル経由 Dispatch と同じ思想 | 自動化が後手 |
| (b) GitHub Issue webhook | Issue を作るだけで Realm に届く | webhook server / 認証 / 公開 endpoint が必要 |
| (c) 直接 Nexus tool: `submit_issue(title, body)` を MCP で公開 | 即時、痕跡が Nexus に統一 | 人間が直接 MCP を叩くインフラが必要 |

**推奨**: **(a) ファイル投入**。

**理由**:
- 「人間 → Realm」の入口は Phase 5 では量が少ない（ユーザー 1 人、頻度低）
- webhook は Phase 6 以降で `gh issue list` 取り込みも含めて統合設計したほうが筋がよい
- ファイル投入なら CI / テストでも投入できる（テスタブル）

Warden が `realm/inbox/issues/` を poll し、未処理の Issue を Guildmaster 宛 Dispatch に変換して投入する。Guildmaster は通常の Dispatch として処理する。

### 9. テストの方針

| カテゴリ | テスト内容 | 環境 |
|---|---|---|
| Realm コンテナ | `docker compose -f docker-compose.realm.yml up -d` で起動、`down` で停止、再起動で状態が保持される | Docker daemon 必須 |
| Warden Persona | 既知の Issue を投入 → 期待する Guildmaster 宛 Dispatch が出ているか | Realm 起動状態 |
| Guildmaster Persona | 既知の request_spawn → 期待する approve / reject 判断 | Realm 起動状態 |
| 3 段階プロセス（E2E） | Mind A から request_spawn → Mind B が spawn される → Mind A に spawn_complete が届く | Realm 起動状態 |
| Mind Kind Registry | Warden 起動時に `kinds/generic.md` がロードされている | Realm 起動状態 |
| リソースフック | Warden が `realm/audit/usage/` に集計を書いている | Realm 起動状態 |

#### CI で動くか

- GitHub Actions の `ubuntu-latest` runner は Docker が動く（Phase 2 推奨と同じ）
- ただし **Realm + 5 services + 動的 Mind spawn の E2E は CI 時間 30 分以上になる可能性**
- Phase 5 の CI 戦略：
  - 各 Persona 単体テストは Claude API を呼ぶため CI で実行しない（手動 / nightly）
  - Realm 起動 / 停止、Warden の Python ロジック、3 段階プロセスの dispatch ログ整合は CI で動かせる
- Claude API キーは CI secret として注入。コスト上限のため nightly に限定する

### 10. 段階分割の提案

Phase 5 を 1 PR で実装するのは現実的でない（推奨案で挙げた各論点ごとに数百行のコードが要る）。以下に分割する：

| 段階 | スコープ | 完了の証明 |
|---|---|---|
| **5a** | Realm コンテナ + Warden（Python 常駐）だけ動く。Guildmaster / Mind なし | `docker compose up -d realm` で Realm が起動し、Warden が `realm/inbox/issues/` を poll している |
| **5b** | 5a + Guildmaster（Mind と同じ仕組み）。3 段階のうち「要求 → 承認」までが回る | 既知の Issue を投入 → Guildmaster が承認 Dispatch を出す（実行はまだ手動） |
| **5c** | 5b + Warden の `execute_spawn` 実装。3 段階プロセスが完全に一巡 | Mind A から request_spawn → Mind B が自動的に spawn されて Dispatch を交わす |

**推奨**: **5a / 5b / 5c の 3 段階に分ける**。各段階が独立 PR で、終わるたびに「動く ai-org-os」が一段グレードアップする。

**5a のみで止まるリスク許容**: 5a だけでも「Realm が実コンテナとして立つ」=ADR-0002 §3 の最小要件が満たせる。Phase 6 を別方向（複数 Guild など）に振る選択肢を残せる。

---

## Axiom（不変項）との整合性確認

| Axiom | Phase 5 での扱い | 整合性 |
|---|---|---|
| **組織⇔外の境界**（ADR-0002 §2） | Realm = ルール適用範囲。Realm の外（ホスト）は ai-org-os 外 | **強化**（Phase 4 まで境界は文書のみ、Phase 5 で物理化） |
| **思考⇔思考の境界** | Nexus 経由 Dispatch / 3 段階プロセスが正規ルート | **強化**（3 段階が enforce される） |
| **Mindspace 不可侵** | Mind コンテナ + named volume（Phase 2 と整合） | **保たれる** |
| **インターフェース** | Nexus（MCP）+ Issue inbox（ファイル）が外部 I/F | **保たれる** |
| **共有はプロセスを踏む** | 3 段階プロセスの痕跡が `realm/audit/dispatches/` に残る | **強化** |
| **24/365 稼働** | Realm コンテナ + Warden + Guildmaster が常駐 | **達成** |
| **無制限自由 + Realm 制約** | Mind 側は変わらず Nexus tools を呼ぶだけ。Realm が裏で集計 | **保たれる** |
| **3 段階ライフサイクル** | `request_spawn` → `approve_spawn` → `execute_spawn` で完全実装 | **達成**（Phase 5 のコア成果） |
| **Mind Kind Registry を Warden が管理** | Warden 起動時に `kinds/*.md` を静的ロード | **達成**（最小実装） |

---

## リスク

| # | リスク | 重大度 | 緩和策 |
|---|---|---|---|
| R1 | **実装規模が大きい**（3 つの Claude を同時管理 + Python 常駐 + docker socket 制御） | **高** | 5a / 5b / 5c の段階分割。各段階で動く成果を確認 |
| R2 | **Claude CLI の長時間運用が未知**（24/365 で Claude CLI を回すのが安定するか不明） | **高** | Warden は Python 骨で Claude CLI は判断時のみ呼ぶ設計を推奨。Guildmaster は Mind と同じ仕組みで実証済の経路。それでも未知なので 5a / 5b で観察期間を取る |
| R3 | **リソース管理を Warden で組むのが難しい** | 中 | Phase 5 では「フックだけ」に留める方針を本 ADR で確定。Phase 6 で本格運用 |
| R4 | **「Mind が能動的に動く」を実装する方法が未確立** | **高** | Phase 3 / Phase 5 共通の課題。Mind の Persona に「定期的に inbox を覗き、自分の目的に照らして次の行動を決める」運用ループを書く。Persona 設計を Phase 5 の 1 サブタスクとして扱う |
| R5 | **DinD を避ける設計が破綻するケース**（例: Mind コンテナを Realm 外から制御する必要が出てくる） | 中 | Warden が docker socket をマウントして Realm の外の docker daemon を制御する設計を採用。**Realm コンテナに docker socket を渡すセキュリティリスク**を accept する（Phase 5 のスコープでは許容） |
| R6 | **docker socket のセキュリティリスク**: Realm コンテナがホスト docker を制御可能になる | 中 | Phase 5 では「Realm = 信頼境界の中」と扱う。Phase 6 以降で rootless docker / 別 socket / Podman 等を再検討 |
| R7 | **Guildmaster Persona の判断品質**（承認 / 却下のルールを書ききれるか） | 中 | 最初は「全部承認」に近い緩い Persona から始め、運用で締める。Phase 5 では「Persona がある」「判断が記録される」までを完成とし、判断品質は Phase 6 で熟成 |
| R8 | **Phase 3 の Nexus が不安定だった場合、Phase 5 全体が止まる** | **高** | Phase 5 着手前に Phase 3（PR #23）の完了を確認する。Phase 3 のテストが green な状態を前提とする |
| R9 | **Realm の起動時間** | 中 | Compose で services を並列起動。Warden / Guildmaster の Persona ロード時間を計測 |
| R10 | **Persona の書きすぎ**: Warden / Guildmaster の CLAUDE.md が肥大化、token を浪費 | 中 | Persona の最大トークン数ガイドラインを Phase 5 で決める（暫定: 各 4k token 以内） |

---

## Phase 5 を実装するかの判断軸

朝起きたユーザーが見て判断できるよう、**3 つの問い**で整理する。

### 問い 1: 「組織として運営される」体験が今すぐ要るか？

- **要る** → Phase 5 は最短経路。3 段階プロセスが回る = ADR-0002 で約束した世界が初めて実装される
- **要らない（Phase 3 までの「2 Mind が会話する」で十分）** → Phase 5 は急がない。他の方向（Persona 充実 / Mind Kind 追加）に投資する手もある

### 問い 2: Phase 3（PR #23）はいつ Accepted になるか？

- **すぐ（数日以内）** → Phase 5 に直接接続できる。本 ADR の Accepted も Phase 3 と並行で詰める
- **しばらくかかる** → Phase 5 着手は Phase 3 完了後。本 ADR は Proposed のまま保留

### 問い 3: 段階分割（5a / 5b / 5c）の各段階で止める覚悟があるか？

- **ある** → 5a で「Realm が立つ」だけでも価値があり、Phase 6 を別方向に振れる
- **ない（5c まで一気に行きたい）** → 実装期間 / レビュー負荷を覚悟する必要あり。1 か月単位

**総合**: 「組織体験を急がない」かつ「Phase 3 の Nexus 安定がまだ」なら **Phase 5 は後回し可能**。
それ以外（特に組織体験を急ぐ）なら **Phase 5 に着手すべき。ただし必ず 5a / 5b / 5c に分ける**。

---

## Consequences（影響、Accepted 時に何が起きるか）

### ポジティブ

- ADR-0002 で約束した「Realm → Guild → Mind」の階層が初めて実装される
- 3 段階ライフサイクル（要求 → 承認 → 実行）が enforce される
- Mind の生成 / 破棄が人間 CLI から組織内プロセスへ昇格する
- 24/365 稼働が階層全体で実現する
- リソース管理 / Issue 投入 / Persona 進化など Phase 6 以降の土台が揃う

### ネガティブ

- Realm コンテナ + 内部 process 3 つ + 動的 Mind コンテナ群、と運用対象が一気に増える
- Claude CLI の長時間運用コスト（Persona + Mind すべてが Claude セッションを抱える）
- CI 時間が伸びる（E2E は手動 / nightly に限定する必要）
- docker socket をマウントすることによるセキュリティリスクを許容する判断が要る

### 副作用

- `runtime/` 配下の構造が Phase 1〜3 の「ホスト直接スクリプト」から「Realm 内構造」へ移行する。**`runtime/` と `realm/` を別ディレクトリにするか、`runtime/` を `realm/` にリネームするかは別途決める**（推奨: `realm/` を新設、`runtime/` は Phase 1〜3 の遺産として残す）
- 既存テスト（`runtime/tests/`）は Phase 5 の Realm 起動を前提としないため、別系統（`realm/tests/`）として並走する

---

## 代替案

### 代替案 1: Phase 5 を 1 PR で一気に実装する

**内容**: 5a / 5b / 5c を分割せず、Realm + Warden + Guildmaster + 3 段階プロセスを 1 PR で実装する。

**長所**: 完成形が一度に揃う。中間状態の混乱がない。
**短所**: PR 肥大化、レビュー困難、詰まった時に全部止まる。
**評価**: **非推奨**。Phase 5 の規模では破綻リスクが高い。

### 代替案 2: Guildmaster をスキップして Warden だけ作る

**内容**: 3 段階プロセスの「承認」を Warden が兼任する（=2 段階に降格）。

**長所**: 実装が半減
**短所**: ADR-0002 §5 の責務分離（Warden = ルール / Guildmaster = 目的）を破棄することになる。Phase 6 で Guild が増えた時に Warden が承認も兼ねる構造が破綻する
**評価**: **非推奨**。Phase 5 のコアを削ることになる。

### 代替案 3: Realm を「論理境界」とみなして実コンテナを作らない

**内容**: Realm = Compose ファイルそのもの、実コンテナは持たない。Warden / Guildmaster / Nexus はホスト直接プロセスとして並走。

**長所**: 軽い、起動が速い
**短所**: ADR-0002 §3「Realm = 実コンテナ」に違反。Axiom の物理担保が一段下がる
**評価**: **非推奨**。本 ADR の根幹を曲げる。

### 代替案 4: Phase 5 をスキップして Phase 6 へ

**内容**: Phase 3 の上に複数 Mind を並べ、Persona / Kind を充実させる方向に投資。Realm / Warden / Guildmaster は Phase 7 以降に延期。

**長所**: Phase 5 の大規模実装を回避できる
**短所**: 「組織として運営される」体験が永遠に来ない。ai-org-os が「Mind の集まり」止まりになる
**評価**: 段階分割（5a / 5b / 5c）が機能しない場合のフォールバック案。当面は段階分割を推奨。

---

## 議論ログ（Discussion log）

本 ADR は壁打ちセッションを経ずに設計担当（私）が初稿を書き起こした。承認プロセスの中で議論を追記する。

### Step 1（初稿、設計担当）

- ADR-0001 / ADR-0002 / ADR-0003 / ADR-0005 と Phase 3 実装（進行中）を踏まえ、Phase 5 の達成目標と論点を網羅
- 推奨案を以下に倒した：
  - Realm = Docker Compose 1 ファイル
  - 中の構造 = Warden / Guildmaster / Nexus は Realm コンテナ内プロセス、Mind だけ別コンテナ（(α) DinD 回避）
  - Warden = Python 常駐 + Claude CLI subprocess
  - Guildmaster = Mind と同じ仕組み（Persona 装着）
  - 3 段階プロセス = Nexus に MCP tools 追加
  - Mind Kind Registry = 静的ロード
  - リソース管理 = フックだけ
  - Issue 投入 = ファイル投入
  - 段階分割 = 5a / 5b / 5c
- Phase 2 必須 / 任意の結論を「**Realm コンテナ自体は必須、Mind の named volume 化は別途**」と明示
- 最大リスクとして R1（実装規模）/ R2（Claude CLI 長時間運用）/ R4（Mind の能動性実装）を挙げた

### Step 2（朝のユーザー判断、想定）

- 推奨案の各論点に対して採用 / 不採用を決める
- 段階分割（5a / 5b / 5c）を採用するか、別の切り方にするかを確定
- Accepted に昇格させるか、Proposed のまま改稿するかを決める

---

## 次にやること（Accepted 時の Issue 化候補）

### 5a スコープ

1. `realm/` ディレクトリ新設、`runtime/` との関係整理
2. `realm/Dockerfile.realm` 作成（Python + Claude CLI + Nexus を内蔵）
3. `realm/docker-compose.realm.yml` 作成（最小: realm service 1 個）
4. `realm/warden/warden.py` 常駐ループ実装（issue inbox poll + Kind Registry ロード）
5. `realm/warden/CLAUDE.md`（Warden Persona）執筆
6. `realm/inbox/issues/` 投入インターフェース整備
7. `realm/audit/` 痕跡領域整備
8. 5a 用テスト: Realm 起動 / Warden が issue を Dispatch に変換する

### 5b スコープ

9. `realm/guildmaster/CLAUDE.md`（Guildmaster Persona）執筆
10. Guildmaster を Realm コンテナ内で永続 Mind として起動する仕組み
11. Nexus に `request_spawn` / `approve_spawn` MCP tools を追加（実行はまだ未実装）
12. 5b 用テスト: Mind から request_spawn を投げ、Guildmaster が approve Dispatch を出す

### 5c スコープ

13. Nexus に `execute_spawn` MCP tool を追加（Warden が受信）
14. Warden が docker socket 経由で Mind コンテナを起動する実装
15. 完了通知（`spawn_complete`）を要求元 Mind に送る経路
16. destroy 側 3 つの MCP tools 追加（`request_destroy` / `approve_destroy` / `execute_destroy`）
17. 5c 用 E2E テスト: 3 段階プロセスの一巡
18. README / docs 更新

これらは Accepted 後に個別 Issue として切り出す。

---

## 関連

- [ADR-0001: ai-org-os を「開発組織の不変項」を定義するフレームワークとして再定義する](./0001-ai-org-os-as-invariant-framework.md)
- [ADR-0002: 用語と「メタのメタ」構造の確定](./0002-vocabulary-and-meta-meta-structure.md)
- [ADR-0003: Phase 2（Docker 化）の設計案](./0003-docker-and-phase-2-design.md)
- ADR-0005: Phase 3 = MCP 直行（Nexus 導入）、Accepted（実装中、PR #23）
- [`runtime/spawn-mind.sh`](../../runtime/spawn-mind.sh) — Phase 1 実装、Phase 5 では Warden 内部に取り込まれる
- [`runtime/kinds/generic.md`](../../runtime/kinds/generic.md) — Generic Kind、Phase 5 で Warden が静的ロード
- [`runtime/personas/`](../../runtime/personas/) — 既存 Persona、Warden / Guildmaster Persona は Phase 5 で新設
- [`runtime/README.md`](../../runtime/README.md) — runtime の現状と Phase 計画
- Issue #19: 認可機構（Phase 5 スコープ外）
- Issue #20: MCP Resources / Prompts（Phase 5 スコープ外）
- Issue #21: メッセージ TTL / dead letter（Phase 5 スコープ外）
- PR #23: Phase 3（Nexus + Dispatch）の実装、Phase 5 の前提

---

> **改めて**: 本 ADR は **Proposed**。**実装は本 ADR の承認後に着手する**。
> Accepted に昇格させるには、上記「推奨案」の各論点をユーザーが確認し、代替案との比較で最終案を確定する必要がある。
> 特に **「段階分割（5a / 5b / 5c）を採用するか」「Realm 内のサブ構造 (α)〜(γ) のどれを採るか」「Guildmaster を Mind と同じ仕組みで作るか」** は本 ADR の中核となる選択で、ユーザー判断を要する。
